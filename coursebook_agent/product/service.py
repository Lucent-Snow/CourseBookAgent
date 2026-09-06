"""SQLite-backed service for datasets, resources, snapshots, and presets."""

from __future__ import annotations

import hashlib
import json
import mimetypes
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
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
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

    def add_file(self, dataset_id: str, filename: str, content: bytes, mime_type: str | None = None) -> Resource:
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
                "INSERT INTO resources VALUES (?, ?, ?, ?, 'upload', NULL, ?, ?)",
                (resource_id, dataset_id, kind, Path(filename).stem, now, now),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (revision_id, resource_id, filename, mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                 len(content), digest, str(blob_path), str(text_path) if status == "ready" else None,
                 status, error, len(text), page_count, json.dumps(metadata, ensure_ascii=False), now),
            )
            db.execute("UPDATE datasets SET updated_at = ? WHERE dataset_id = ?", (now, dataset_id))
        return self.get_resource(resource_id)

    def import_zhiyun_course(self, dataset_id: str, course_id: str) -> list[Resource]:
        self.get_dataset(dataset_id)
        source = ZhiyunSource()
        course = source.get_course(course_id)
        lectures = source.list_lectures(course_id)
        imported: list[Resource] = []
        for lecture in lectures:
            segments = source.get_transcript(lecture)
            text = "\n".join(
                f"[{segment.start_sec}-{segment.end_sec}] {segment.text}" for segment in segments
            )
            content = text.encode("utf-8")
            digest = hashlib.sha256(content).hexdigest()
            blob_path = self.blob_dir / digest
            if not blob_path.exists():
                blob_path.write_bytes(content)
            resource_id, revision_id, now = _id("res"), _id("rev"), _now()
            text_path = self.text_dir / f"{revision_id}.txt"
            atomic_write_text(text_path, text)
            metadata = {
                "course_id": course_id,
                "course_name": course.name,
                "lecture_id": lecture.lecture_id,
                "lecture_index": lecture.index,
                "duration": lecture.duration,
                "teacher": course.teacher,
                "term": course.term,
            }
            with self._connect() as db:
                db.execute(
                    "INSERT INTO resources VALUES (?, ?, 'transcript', ?, 'zhiyun', ?, ?, ?)",
                    (resource_id, dataset_id, lecture.title, f"{course_id}:{lecture.lecture_id}", now, now),
                )
                db.execute(
                    "INSERT INTO revisions VALUES (?, ?, 1, ?, 'text/plain', ?, ?, ?, ?, 'ready', NULL, ?, NULL, ?, ?)",
                    (revision_id, resource_id, f"{lecture.index:02d}-{lecture.title}.txt", len(content), digest,
                     str(blob_path), str(text_path), len(text), json.dumps(metadata, ensure_ascii=False), now),
                )
            imported.append(self.get_resource(resource_id))
        with self._connect() as db:
            db.execute("UPDATE datasets SET updated_at = ? WHERE dataset_id = ?", (_now(), dataset_id))
        return imported

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

    def _resource_from_row(self, row: sqlite3.Row) -> Resource:
        with self._connect() as db:
            revision = db.execute("SELECT * FROM revisions WHERE resource_id = ? ORDER BY version DESC LIMIT 1", (row["resource_id"],)).fetchone()
        return Resource(**dict(row), current_revision=self._revision_from_row(revision) if revision else None)

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
                WorkflowStep(key="prepare", name="整理课程资料", description="解析并组织本次输入资料", agent_role="material_editor"),
                WorkflowStep(key="plan", name="规划课程内容", description="生成全书结构与章节指令", agent_role="book_editor"),
                WorkflowStep(key="write", name="撰写章节内容", description="按章节并行生成教辅草稿", agent_role="chapter_writer", parallel=True),
                WorkflowStep(key="synthesize", name="统一全书内容", description="统一术语、前言与章节衔接", agent_role="chief_editor"),
                WorkflowStep(key="quality", name="检查并生成产物", description="检查来源与质量并渲染成稿", agent_role="quality_reviewer"),
            ],
            default_config={"concurrency": 3, "review": True, "retry_attempts": 2, "preview_intermediate": True},
            output_kind="coursebook",
        )]
