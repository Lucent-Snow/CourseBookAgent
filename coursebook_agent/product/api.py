"""FastAPI routes for the product workbench."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from coursebook_agent.product.models import DatasetCreate, SnapshotCreate, ZhiyunImportRequest
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


@router.post("/datasets/{dataset_id}/imports/zhiyun", status_code=201)
def import_zhiyun(dataset_id: str, request: ZhiyunImportRequest):
    try:
        resources = service().import_zhiyun_course(dataset_id, request.course_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": resources}


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
