"""FastAPI routes for the product workbench."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from coursebook_agent.config import config
from coursebook_agent.product.models import (
    DatasetCreate,
    ProviderInspection,
    SnapshotCreate,
    XueZaiImportRequest,
    ZhiyunImportRequest,
)
from coursebook_agent.product.projections import project_artifact, project_run
from coursebook_agent.product.service import ProductService


class UnifiedLoginRequest(BaseModel):
    username: str
    password: str
    webvpn: bool = False

router = APIRouter(prefix="/api/product", tags=["product-workbench"])


def service() -> ProductService:
    return ProductService()


def _call(operation):
    try:
        return operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/datasets")
def list_datasets():
    return {"data": service().list_datasets()}


@router.post("/datasets", status_code=201)
def create_dataset(request: DatasetCreate):
    return service().create_dataset(request)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    product = service()
    return _call(lambda: {
        "dataset": product.get_dataset(dataset_id),
        "resources": product.list_resources(dataset_id),
        "snapshots": product.list_snapshots(dataset_id),
    })


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str):
    _call(lambda: service().delete_dataset(dataset_id))


@router.post("/datasets/{dataset_id}/resources", status_code=201)
async def upload_resource(
    dataset_id: str,
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    content = await file.read()
    resource = _call(lambda: service().add_file(dataset_id, file.filename or title, content, file.content_type))
    if title.strip():
        # Title editing is intentionally deferred; preserve the uploaded filename as source evidence.
        resource.title = title.strip()
    return resource


@router.get("/imports/zhiyun/courses")
def list_zhiyun_courses(refresh: bool = False):
    from coursebook_agent.sources.zhiyun import ZhiyunSource

    try:
        return {"data": ZhiyunSource().list_courses(refresh=refresh)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/imports/zhiyun/courses/{course_id}")
def inspect_zhiyun_course(course_id: str, refresh: bool = False):
    from coursebook_agent.sources.zhiyun import ZhiyunSource

    try:
        source = ZhiyunSource()
        courses = source.list_courses(refresh=refresh)
        course = next((item for item in courses if item.course_id == course_id), None)
        lectures = source.list_lectures(course_id, refresh=refresh)
        return ProviderInspection(
            provider="zhiyun",
            course={"course_id": course_id, "name": course.name if course else f"课程 {course_id}",
                    "teacher": course.teacher if course else None, "term": course.term if course else None},
            lectures=[lecture.model_dump() for lecture in lectures],
            uploads=[],
            content_types=[
                {"key": "transcript", "name": "课堂字幕", "description": "带时间点的课堂字幕文本"},
                {"key": "courseware", "name": "智云课件页", "description": "课堂录制中的 PPT 页面图片与时间点，不是原始 PPTX"},
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/imports/zhiyun", status_code=201)
def import_zhiyun(dataset_id: str, request: ZhiyunImportRequest):
    try:
        resources, warnings = service().import_zhiyun_course(
            dataset_id, request.course_id, lecture_ids=request.lecture_ids,
            content_types=request.content_types, refresh=request.refresh,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": resources, "warnings": warnings}


@router.get("/imports/xuezai/auth")
def xuezai_auth_status():
    from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource

    try:
        return XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").auth_status()
    except XueZaiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/imports/xuezai/auth", status_code=201)
def xuezai_login(request: UnifiedLoginRequest):
    from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource

    try:
        return XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").login(request.username, request.password)
    except XueZaiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/imports/xuezai/auth", status_code=204)
def xuezai_logout():
    from coursebook_agent.sources.xuezai.assist import XueZaiSource

    XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").logout()
    return None


@router.get("/auth/providers")
def provider_auth_status():
    """Return the connected status of every provider."""
    from coursebook_agent.sources.xuezai.assist import XueZaiSource

    zhiyun_status: dict[str, object]
    try:
        zhiyun_status = {"authenticated": bool(config.zhiyun.has_credentials), "username": ""}
        if config.zhiyun.session_file.exists():
            import json as _json
            payload = _json.loads(config.zhiyun.session_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                zhiyun_status["authenticated"] = bool(payload.get("zhiyun_jwt") or config.zhiyun.jwt)
                zhiyun_status["username"] = payload.get("username", "")
    except (OSError, ValueError):
        zhiyun_status = {"authenticated": False, "username": ""}
    try:
        xuezai = XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").auth_status()
    except Exception:  # noqa: BLE001 — best-effort status, surface 502 only on the dedicated endpoints
        xuezai = {"authenticated": False, "username": ""}
    return {"zhiyun": zhiyun_status, "xue_zai_zju": xuezai}


@router.post("/auth/login", status_code=201)
def unified_login(request: UnifiedLoginRequest):
    """Log in once and obtain sessions for both providers.

    Zhiyun uses the existing JWT exchange; 学在浙大 uses the CAS public key
    RSA flow.  Both providers share the same university credentials.
    """
    from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource
    from coursebook_agent.sources.zhiyun import ZhiyunError, ZhiyunSource

    results: dict[str, object] = {}
    zhiyun_error: str | None = None
    xuezai_error: str | None = None
    try:
        zhiyun_status = ZhiyunSource().login(request.username, request.password, webvpn=request.webvpn)
        results["zhiyun"] = {"authenticated": True, "username": zhiyun_status.get("username", request.username)}
    except ZhiyunError as exc:
        zhiyun_error = str(exc)
        results["zhiyun"] = {"authenticated": False, "username": ""}
    try:
        xuezai = XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").login(request.username, request.password)
        results["xue_zai_zju"] = xuezai
    except XueZaiError as exc:
        xuezai_error = str(exc)
        results["xue_zai_zju"] = {"authenticated": False, "username": ""}
    if zhiyun_error and xuezai_error:
        raise HTTPException(status_code=502, detail=f"智云：{zhiyun_error}；学在浙大：{xuezai_error}")
    response: dict[str, object] = {"providers": results, "username": request.username}
    if zhiyun_error:
        response["warnings"] = [f"智云课堂登录未成功：{zhiyun_error}"]
    if xuezai_error:
        response.setdefault("warnings", []).append(f"学在浙大登录未成功：{xuezai_error}")
    return response


@router.get("/imports/xuezai/courses")
def list_xuezai_courses(refresh: bool = False):
    from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource

    try:
        return {"data": [course.model_dump() if hasattr(course, "model_dump") else {
            "course_id": course.course_id, "name": course.name, "teacher": course.teacher, "term": course.term,
        } for course in XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai").list_my_courses(refresh=refresh)]}
    except XueZaiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/imports/xuezai/courses/{course_id}")
def inspect_xuezai_course(course_id: int, refresh: bool = False):
    from coursebook_agent.sources.xuezai.assist import XueZaiError, XueZaiSource

    try:
        source = XueZaiSource(cache_dir=config.data_dir / "cache" / "xuezai")
        courses = source.list_my_courses(refresh=refresh)
        course = next((item for item in courses if item.course_id == course_id), None)
        uploads = source.list_course_uploads(course_id, refresh=refresh)
        inspection = ProviderInspection(
            provider="xue_zai_zju",
            course={"course_id": str(course_id), "name": course.name if course else f"课程 {course_id}",
                    "teacher": course.teacher if course else None, "term": course.term if course else None},
            lectures=[],
            uploads=[upload.__dict__ for upload in uploads],
            content_types=[
                {"key": "xuezai_upload", "name": "原始课件文件", "description": "下载 PDF、PPTX、DOCX 等原始文件，存入资料集"},
            ],
        )
        return inspection
    except XueZaiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/imports/xuezai", status_code=201)
def import_xuezai(dataset_id: str, request: XueZaiImportRequest):
    try:
        resources, warnings = service().import_xuezai_uploads(
            dataset_id, course_id=request.course_id, upload_ids=request.upload_ids, refresh=request.refresh,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": resources, "warnings": warnings}


@router.get("/datasets/{dataset_id}/resources")
def list_resources(dataset_id: str):
    return {"data": _call(lambda: service().list_resources(dataset_id))}


@router.get("/resource-revisions/{revision_id}/preview")
def preview_resource(revision_id: str, limit: int = 12000):
    return _call(lambda: service().preview_revision(revision_id, min(max(limit, 1), 50000)))


@router.post("/datasets/{dataset_id}/snapshots", status_code=201)
def create_snapshot(dataset_id: str, request: SnapshotCreate):
    return _call(lambda: service().create_snapshot(dataset_id, request))


@router.get("/datasets/{dataset_id}/snapshots")
def list_snapshots(dataset_id: str):
    return {"data": _call(lambda: service().list_snapshots(dataset_id))}


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str):
    return _call(lambda: service().get_snapshot(snapshot_id))


@router.get("/workflow-presets")
def list_workflow_presets():
    return {"data": ProductService.workflow_presets()}


@router.get("/runs")
def list_run_projections():
    from coursebook_agent.app import jobs

    return {"data": [project_run(state) for state in reversed(list(jobs.values()))]}


@router.get("/runs/{run_id}")
def get_run_projection(run_id: str):
    from coursebook_agent.app import _get_job

    return _call(lambda: project_run(_get_job(run_id)))


@router.get("/artifacts")
def list_artifacts():
    from coursebook_agent.app import jobs

    return {"data": [artifact for state in reversed(list(jobs.values())) if (artifact := project_artifact(state))]}


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    from coursebook_agent.app import _get_job

    def resolve():
        state = _get_job(artifact_id)
        artifact = project_artifact(state)
        if not artifact:
            raise KeyError("产物不存在")
        return {"artifact": artifact, "book": state.book}

    return _call(resolve)
