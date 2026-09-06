"""FastAPI routes for the product workbench."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from coursebook_agent.product.models import DatasetCreate, SnapshotCreate, ZhiyunImportRequest
from coursebook_agent.product.projections import project_artifact, project_run
from coursebook_agent.product.service import ProductService

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
        return {
            "course": course or {"course_id": course_id, "name": f"课程 {course_id}"},
            "lectures": lectures,
            "content_types": [
                {"key": "transcript", "name": "课堂字幕", "description": "带时间点的课堂字幕文本"},
                {"key": "courseware", "name": "智云课件页", "description": "课堂录制中的 PPT 页面图片与时间点，不是原始 PPTX"},
            ],
        }
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
