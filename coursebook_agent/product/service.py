"""SQLite-backed service for datasets, resources, snapshots, and presets."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from coursebook_agent.config import config
from coursebook_agent.product.models import (
    Dataset,
    DatasetCreate,
    InputSnapshot,
    Resource,
    ResourcePreview,
    ResourceRevision,
    SnapshotCreate,
    WorkflowPreset,
    WorkflowStep,
)
from coursebook_agent.product.parsers import parse_document, resource_kind
from coursebook_agent.sources.zhiyun import ZhiyunSource
from coursebook_agent.storage import atomic_write_text


class _ClosingConnection(sqlite3.Connection):
    """SQLite context manager that also releases the Windows file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ProductService:
    def __init__(self, root: Path | None = None):
        self.root = root or config.data_dir / "product"
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_dir = self.root / "blobs"
        self.text_dir = self.root / "text"
        self.blob_dir.mkdir(exist_ok=True)
        self.text_dir.mkdir(exist_ok=True)
        self.db_path = self.root / "product.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', '1');
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resources (
                    resource_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'zhiyun',
                    source_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL REFERENCES resources(resource_id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    blob_path TEXT NOT NULL,
                    text_path TEXT,
                    parse_status TEXT NOT NULL,
                    parse_error TEXT,
                    text_chars INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(resource_id, version)
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
                    label TEXT NOT NULL DEFAULT '',
                    resource_revision_ids_json TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            self._ensure_column(db, "resources", "provider", "TEXT NOT NULL DEFAULT 'zhiyun'")

    def _ensure_column(self, db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if existing is None:
            return
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_dataset(self, request: DatasetCreate) -> Dataset:
        dataset_id = _id("ds")
        now = _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO datasets VALUES (?, ?, ?, ?, ?)",
                (dataset_id, request.name.strip(), request.description.strip(), now, now),
            )
        return self.get_dataset(dataset_id)

    def list_datasets(self) -> list[Dataset]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT d.*,
                       COUNT(r.resource_id) AS resource_count,
                       SUM(CASE WHEN rv.parse_status = 'ready' THEN 1 ELSE 0 END) AS ready_count
                FROM datasets d
                LEFT JOIN resources r ON r.dataset_id = d.dataset_id
                LEFT JOIN revisions rv ON rv.revision_id = (
                    SELECT revision_id FROM revisions WHERE resource_id = r.resource_id
                    ORDER BY version DESC LIMIT 1
                )
                GROUP BY d.dataset_id ORDER BY d.updated_at DESC
            """).fetchall()
        items = []
        for row in rows:
            data = dict(row)
            data["ready_count"] = data["ready_count"] or 0
            items.append(Dataset(**data))
        return items

    def get_dataset(self, dataset_id: str) -> Dataset:
        datasets = {item.dataset_id: item for item in self.list_datasets()}
        if dataset_id not in datasets:
            raise KeyError("资料集不存在")
        return datasets[dataset_id]

    def delete_dataset(self, dataset_id: str) -> None:
        with self._connect() as db:
            result = db.execute("DELETE FROM datasets WHERE dataset_id = ?", (dataset_id,))
            if not result.rowcount:
                raise KeyError("资料集不存在")

    def add_file(self, dataset_id: str, filename: str, content: bytes, mime_type: str | None = None, title: str = "") -> Resource:
        self.get_dataset(dataset_id)
        if not filename or not content:
            raise ValueError("文件不能为空")
        digest = hashlib.sha256(content).hexdigest()
        blob_path = self.blob_dir / digest
        if not blob_path.exists():
            blob_path.write_bytes(content)
        kind = resource_kind(filename)
        resource_id = _id("res")
        revision_id = _id("rev")
        now = _now()
        status, error, text, page_count, metadata = "ready", None, "", None, {}
        try:
            parsed = parse_document(filename, content)
            text, page_count, metadata = parsed.text, parsed.page_count, parsed.metadata
        except Exception as exc:
            status, error = "failed", str(exc)
        text_path = self.text_dir / f"{revision_id}.txt"
        if status == "ready":
            atomic_write_text(text_path, text)
        with self._connect() as db:
            db.execute(
                "INSERT INTO resources (resource_id, dataset_id, kind, title, source_type, provider, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, 'upload', 'zhiyun', NULL, ?, ?)",
                (resource_id, dataset_id, kind, title.strip() or Path(filename).stem, now, now),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (revision_id, resource_id, filename, mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                 len(content), digest, str(blob_path), str(text_path) if status == "ready" else None,
                 status, error, len(text), page_count, json.dumps(metadata, ensure_ascii=False), now),
            )
            db.execute("UPDATE datasets SET updated_at = ? WHERE dataset_id = ?", (now, dataset_id))
        return self.get_resource(resource_id)

    def import_zhiyun_course(
        self, dataset_id: str, course_id: str, *, lecture_ids: list[str] | None = None,
        content_types: list[str] | None = None, refresh: bool = False,
    ) -> tuple[list[Resource], list[str]]:
        self.get_dataset(dataset_id)
        source = ZhiyunSource()
        courses = source.list_courses(refresh=refresh)
        course = next((item for item in courses if item.course_id == str(course_id)), None)
        lectures = source.list_lectures(course_id, refresh=refresh)
        if not course:
            from coursebook_agent.models import Course
            course = Course(course_id=str(course_id), name=f"课程 {course_id}")
        selected = set(lecture_ids or [])
        if selected:
            available = {lecture.lecture_id for lecture in lectures}
            missing = selected - available
            if missing:
                raise ValueError(f"所选讲次不存在：{', '.join(sorted(missing))}")
            lectures = [lecture for lecture in lectures if lecture.lecture_id in selected]
        kinds = list(dict.fromkeys(content_types or ["transcript"]))
        if not kinds or any(kind not in {"transcript", "courseware"} for kind in kinds):
            raise ValueError("请选择字幕或智云课件")
        imported: list[Resource] = []
        warnings: list[str] = []
        for lecture in lectures:
            metadata = {
                "course_id": course_id, "course_name": course.name,
                "lecture_id": lecture.lecture_id, "lecture_index": lecture.index,
                "duration": lecture.duration, "teacher": course.teacher, "term": course.term,
            }
            if "transcript" in kinds:
                try:
                    segments = source.get_transcript(lecture, refresh=refresh)
                    text = "\n".join(f"[{item.start_sec}-{item.end_sec}] {item.text}" for item in segments)
                    imported.append(self._add_zhiyun_resource(
                        dataset_id, "transcript", lecture.title, f"{lecture.index:02d}-{lecture.title}.txt",
                        text, metadata, f"{course_id}:{lecture.lecture_id}:transcript",
                    ))
                except Exception as exc:
                    warnings.append(f"{lecture.title}的课堂字幕导入失败：{exc}")
            if "courseware" in kinds:
                try:
                    pages = source.get_courseware(lecture, refresh=refresh)
                    if not pages:
                        warnings.append(f"{lecture.title}没有可用的智云课件页")
                    else:
                        text = "\n".join(
                            f"[第 {index} 页 · {page.get('created_sec', 0)} 秒] {page.get('title') or '课件页'}\n{page.get('image_url')}"
                            for index, page in enumerate(pages, start=1)
                        )
                        page_metadata = {**metadata, "page_count": len(pages), "pages": pages}
                        imported.append(self._add_zhiyun_resource(
                            dataset_id, "courseware", f"{lecture.title} · 智云课件",
                            f"{lecture.index:02d}-{lecture.title}-课件.txt", text, page_metadata,
                            f"{course_id}:{lecture.lecture_id}:courseware", page_count=len(pages),
                        ))
                except Exception as exc:
                    warnings.append(f"{lecture.title}的智云课件页导入失败：{exc}")
        with self._connect() as db:
            db.execute("UPDATE datasets SET updated_at = ? WHERE dataset_id = ?", (_now(), dataset_id))
        return imported, warnings

    def _add_zhiyun_resource(
        self, dataset_id: str, kind: str, title: str, filename: str, text: str,
        metadata: dict, source_ref: str, page_count: int | None = None,
    ) -> Resource:
        content = text.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        blob_path = self.blob_dir / digest
        if not blob_path.exists():
            blob_path.write_bytes(content)
        resource_id, revision_id, now = _id("res"), _id("rev"), _now()
        text_path = self.text_dir / f"{revision_id}.txt"
        atomic_write_text(text_path, text)
        with self._connect() as db:
            db.execute(
                "INSERT INTO resources (resource_id, dataset_id, kind, title, source_type, provider, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, 'zhiyun', 'zhiyun', ?, ?, ?)",
                (resource_id, dataset_id, kind, title, source_ref, now, now),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, 1, ?, 'text/plain', ?, ?, ?, ?, 'ready', NULL, ?, ?, ?, ?)",
                (revision_id, resource_id, filename, len(content), digest, str(blob_path), str(text_path),
                 len(text), page_count, json.dumps(metadata, ensure_ascii=False), now),
            )
        return self.get_resource(resource_id)

    def import_xuezai_uploads(
        self,
        dataset_id: str,
        course_id: int,
        upload_ids: list[int] | None = None,
        refresh: bool = False,
    ) -> tuple[list[Resource], list[str]]:
        self.get_dataset(dataset_id)
        from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource

        source = XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai")
        imported: list[Resource] = []
        warnings: list[str] = []
        # Probe the source first. If login is not valid we surface the
        # message as a warning instead of silently returning an empty list,
        # so the operator knows why no uploads came back.
        try:
            courses = source.list_my_courses(refresh=refresh)
        except XueZaiError as exc:
            warnings.append(f"学在浙大未登录或会话失效：{exc}")
            courses = []
        course = next((item for item in courses if item.course_id == int(course_id)), None)
        try:
            uploads = source.list_course_uploads(int(course_id), refresh=refresh)
        except XueZaiError as exc:
            warnings.append(f"学在浙大课件列表读取失败：{exc}")
            uploads = []
        if course is None:
            from coursebook_agent.sources.xuezai.assist import XueZaiCourse
            course = XueZaiCourse(course_id=int(course_id), name=f"课程 {course_id}")
        selected = {int(value) for value in (upload_ids or [])}
        if selected:
            available = {upload.upload_id for upload in uploads}
            missing = selected - available
            if missing:
                raise ValueError(f"所选课件不存在：{', '.join(str(item) for item in sorted(missing))}")
            uploads = [upload for upload in uploads if upload.upload_id in selected]
        if not uploads:
            return imported, warnings
        for upload in uploads:
            try:
                content = source.download_upload(upload)
            except XueZaiError as exc:
                warnings.append(f"{upload.filename}下载失败：{exc}")
                continue
            resource = self._add_xuezai_resource(
                dataset_id, course, upload, content,
            )
            imported.append(resource)
        with self._connect() as db:
            db.execute("UPDATE datasets SET updated_at = ? WHERE dataset_id = ?", (_now(), dataset_id))
        return imported, warnings

    def _add_xuezai_resource(self, dataset_id: str, course, upload, content: bytes) -> Resource:
        digest = hashlib.sha256(content).hexdigest()
        blob_path = self.blob_dir / digest
        if not blob_path.exists():
            blob_path.write_bytes(content)
        resource_id, revision_id, now = _id("res"), _id("rev"), _now()
        kind = resource_kind(upload.filename) or "xuezai_upload"
        mime_type = upload.content_type or mimetypes.guess_type(upload.filename)[0] or "application/octet-stream"
        status, error, text, page_count, metadata = "ready", None, "", None, {
            "provider": "xue_zai_zju",
            "course_id": course.course_id,
            "course_name": course.name,
            "upload_id": upload.upload_id,
            "reference_id": upload.reference_id,
            "module": upload.module,
        }
        try:
            parsed = parse_document(upload.filename, content)
            text, page_count, metadata = parsed.text, parsed.page_count, {**parsed.metadata, **metadata}
        except Exception as exc:
            status, error = "failed", str(exc)
            kind = "xuezai_upload"
        text_path = self.text_dir / f"{revision_id}.txt"
        if status == "ready" and text:
            atomic_write_text(text_path, text)
        with self._connect() as db:
            db.execute(
                "INSERT INTO resources (resource_id, dataset_id, kind, title, source_type, provider, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, 'xuezai', 'xue_zai_zju', ?, ?, ?)",
                (resource_id, dataset_id, kind, upload.filename, f"{course.course_id}:{upload.upload_id}", now, now),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (revision_id, resource_id, upload.filename, mime_type, len(content), digest, str(blob_path),
                 str(text_path) if status == "ready" else None, status, error, len(text), page_count,
                 json.dumps(metadata, ensure_ascii=False), now),
            )
        return self.get_resource(resource_id)

    def list_resources(self, dataset_id: str) -> list[Resource]:
        self.get_dataset(dataset_id)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM resources WHERE dataset_id = ? ORDER BY updated_at DESC", (dataset_id,)).fetchall()
        return [self._resource_from_row(row) for row in rows]

    def get_resource(self, resource_id: str) -> Resource:
        with self._connect() as db:
            row = db.execute("SELECT * FROM resources WHERE resource_id = ?", (resource_id,)).fetchone()
        if not row:
            raise KeyError("资料不存在")
        return self._resource_from_row(row)

    def get_revision(self, revision_id: str) -> ResourceRevision:
        with self._connect() as db:
            row = db.execute("SELECT * FROM revisions WHERE revision_id = ?", (revision_id,)).fetchone()
        if not row:
            raise KeyError("资料版本不存在")
        return self._revision_from_row(row)

    def text_path_for(self, revision: ResourceRevision) -> Path | None:
        """Resolve the parsed-text path for a revision from its metadata."""
        with self._connect() as db:
            row = db.execute(
                "SELECT text_path FROM revisions WHERE revision_id = ?",
                (revision.revision_id,),
            ).fetchone()
        if not row or not row["text_path"]:
            return None
        return Path(row["text_path"])

    def blob_path_for(self, revision: ResourceRevision) -> Path | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT blob_path FROM revisions WHERE revision_id = ?",
                (revision.revision_id,),
            ).fetchone()
        if not row or not row["blob_path"]:
            return None
        return Path(row["blob_path"])

    # ── run lifecycle ─────────────────────────────────────────────
    # Runs are stored on disk in data/jobs/{run_id}.json; the API deletes
    # them so the front-end can clean up. We don't store them in SQLite
    # because the generation pipeline already owns the file.

    def list_runs_by_dataset(self, dataset_id: str) -> list[dict]:
        runs: list[dict] = []
        job_dir = config.data_dir / "jobs"
        if not job_dir.exists():
            return runs
        for path in job_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("dataset_id") != dataset_id:
                continue
            runs.append({
                "job_id": data.get("job_id") or path.stem,
                "status": data.get("status"),
                "phase": data.get("step"),
                "progress": data.get("progress", 0),
                "message": data.get("message", ""),
                "course_id": data.get("course_id") or None,
                "snapshot_id": (data.get("request") or {}).get("snapshot_id"),
                "preset_id": (data.get("request") or {}).get("preset_id") or "coursebook",
                "dataset_id": dataset_id,
                "artifact_available": data.get("book") is not None,
                "updated_at": data.get("events", [{}])[-1].get("at") if data.get("events") else None,
                "created_at": data.get("events", [{}])[0].get("at") if data.get("events") else None,
            })
        runs.sort(key=lambda r: (r.get("created_at") or ""), reverse=True)
        return runs

    def delete_run(self, job_id: str) -> bool:
        path = config.data_dir / "jobs" / f"{job_id}.json"
        if path.exists():
            path.unlink()
        checkpoint_dir = config.data_dir / "jobs" / job_id
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
        return True

    def _resource_from_row(self, row: sqlite3.Row) -> Resource:
        with self._connect() as db:
            revision = db.execute("SELECT * FROM revisions WHERE resource_id = ? ORDER BY version DESC LIMIT 1", (row["resource_id"],)).fetchone()
        keys = row.keys() if hasattr(row, "keys") else []
        provider = row["provider"] if "provider" in keys else None
        # If the column was migrated late and existing rows have corrupt
        # values (e.g. an ISO timestamp stored there), fall back to the
        # legacy "zhiyun" default.
        if provider not in {"zhiyun", "xue_zai_zju"}:
            provider = "zhiyun"
        data = {
            "resource_id": row["resource_id"],
            "dataset_id": row["dataset_id"],
            "kind": row["kind"],
            "title": row["title"],
            "source_type": row["source_type"],
            "provider": provider,
            "source_ref": row["source_ref"] if "source_ref" in keys else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        return Resource(**data, current_revision=self._revision_from_row(revision) if revision else None)

    def _revision_from_row(self, row: sqlite3.Row) -> ResourceRevision:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json"))
        data.pop("blob_path", None)
        data.pop("text_path", None)
        return ResourceRevision(**data)

    def preview_revision(self, revision_id: str, limit: int = 12000) -> ResourcePreview:
        with self._connect() as db:
            row = db.execute("SELECT * FROM revisions WHERE revision_id = ?", (revision_id,)).fetchone()
        if not row:
            raise KeyError("资料版本不存在")
        text = ""
        if row["text_path"] and Path(row["text_path"]).exists():
            text = Path(row["text_path"]).read_text(encoding="utf-8")[:limit]
        return ResourcePreview(revision=self._revision_from_row(row), text=text)

    def create_snapshot(self, dataset_id: str, request: SnapshotCreate) -> InputSnapshot:
        self.get_dataset(dataset_id)
        revision_ids = list(dict.fromkeys(request.resource_revision_ids))
        placeholders = ",".join("?" for _ in revision_ids)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT rv.revision_id, rv.sha256 FROM revisions rv
                    JOIN resources r ON r.resource_id = rv.resource_id
                    WHERE r.dataset_id = ? AND rv.revision_id IN ({placeholders})""",
                (dataset_id, *revision_ids),
            ).fetchall()
        if len(rows) != len(revision_ids):
            raise ValueError("快照包含不属于该资料集的版本")
        by_id = {row["revision_id"]: row["sha256"] for row in rows}
        digest = hashlib.sha256("\n".join(f"{item}:{by_id[item]}" for item in revision_ids).encode()).hexdigest()
        snapshot_id, now = _id("snap"), _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                (snapshot_id, dataset_id, request.label.strip(), json.dumps(revision_ids), digest, now),
            )
        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> InputSnapshot:
        with self._connect() as db:
            row = db.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if not row:
            raise KeyError("输入快照不存在")
        ids = json.loads(row["resource_revision_ids_json"])
        return InputSnapshot(
            snapshot_id=row["snapshot_id"], dataset_id=row["dataset_id"], label=row["label"],
            resource_revision_ids=ids, resource_count=len(ids), sha256=row["sha256"], created_at=row["created_at"],
        )

    def list_snapshots(self, dataset_id: str) -> list[InputSnapshot]:
        self.get_dataset(dataset_id)
        with self._connect() as db:
            rows = db.execute("SELECT snapshot_id FROM snapshots WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)).fetchall()
        return [self.get_snapshot(row["snapshot_id"]) for row in rows]

    @staticmethod
    def workflow_presets() -> list[WorkflowPreset]:
        return [WorkflowPreset(
            preset_id="coursebook",
            name="课程教辅书",
            description="把课程资料整理为有结构、可复习、可追溯的课程教辅草稿。",
            supported_resource_kinds=["zhiyun_course", "transcript", "pptx", "pdf", "docx", "markdown", "text"],
            steps=[
                WorkflowStep(key="parse", name="解析所有资料", description="把本次快照中的每份资料按结构解析为可引用的最小单元", agent_role="material_editor"),
                WorkflowStep(key="describe", name="生成资料说明", description="为每份资料生成 description，让主 Agent 不读原文也能看到全局", agent_role="material_editor"),
                WorkflowStep(key="plan", name="规划全书章节与 Tag", description="主 Agent 基于所有 description 规划章节、为每份资料打 Tag", agent_role="book_editor"),
                WorkflowStep(key="assemble", name="按 Tag 装章节上下文", description="把 chapter / global Tag 资料分别装入对应章节上下文", agent_role="book_editor"),
                WorkflowStep(key="write", name="章节 Agent 并发生成", description="一个章节 Agent 负责一个 ChapterContext，按章节并行生成教辅草稿", agent_role="chapter_writer", parallel=True),
                WorkflowStep(key="synthesize", name="统一全书内容", description="统一术语、前言与章节衔接", agent_role="chief_editor"),
                WorkflowStep(key="render", name="渲染并输出", description="把 CourseBook 渲染为 Markdown 并写出", agent_role="quality_reviewer"),
            ],
            default_config={"concurrency": 3, "review": True, "retry_attempts": 2, "preview_intermediate": True},
            output_kind="coursebook",
        )]
