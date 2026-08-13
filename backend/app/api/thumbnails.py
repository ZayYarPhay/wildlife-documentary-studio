from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.project import Project
from app.models.thumbnail import ThumbnailAsset, ThumbnailStatus
from app.schemas.thumbnail import (
    ThumbnailAssetRead,
    ThumbnailBundle,
    ThumbnailGenerateRequest,
)
from app.services.thumbnails import (
    approve_thumbnail,
    create_thumbnail_concepts,
    run_thumbnail_asset,
    submit_thumbnail_assets,
    thumbnail_bundle,
)

router = APIRouter(tags=["thumbnails"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _project(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _asset(asset_id: int, db: Session) -> ThumbnailAsset:
    asset = db.get(ThumbnailAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return asset


@router.get("/api/projects/{project_id}/thumbnails", response_model=ThumbnailBundle)
def get_thumbnails(project_id: int, db: DatabaseSession) -> ThumbnailBundle:
    return thumbnail_bundle(_project(project_id, db), db)


@router.post("/api/projects/{project_id}/thumbnails/concepts", response_model=ThumbnailBundle)
async def generate_thumbnail_concepts(project_id: int, db: DatabaseSession) -> ThumbnailBundle:
    project = _project(project_id, db)
    try:
        await create_thumbnail_concepts(project, db)
    except (TimeoutError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return thumbnail_bundle(project, db)


@router.post(
    "/api/projects/{project_id}/thumbnails/generate",
    response_model=ThumbnailBundle,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_thumbnails(
    project_id: int,
    payload: ThumbnailGenerateRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> ThumbnailBundle:
    project = _project(project_id, db)
    try:
        assets = submit_thumbnail_assets(project, payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    for asset in assets:
        background_tasks.add_task(run_thumbnail_asset, asset.id)
    return thumbnail_bundle(project, db)


@router.post(
    "/api/thumbnail-assets/{asset_id}/retry",
    response_model=ThumbnailAssetRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_thumbnail(
    asset_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> ThumbnailAsset:
    old = _asset(asset_id, db)
    if old.status not in {ThumbnailStatus.FAILED, ThumbnailStatus.REJECTED}:
        raise HTTPException(
            status_code=409, detail="Only failed or rejected thumbnails can be retried"
        )
    if old.retry_count >= get_settings().thumbnail_max_retries:
        raise HTTPException(status_code=409, detail="Thumbnail retry limit reached")
    project = _project(old.project_id, db)
    request = ThumbnailGenerateRequest(
        concept_ids=[old.concept_id],
        title_overlay=old.title_overlay,
        overlay_text=old.overlay_text,
        seed=old.seed,
    )
    try:
        new_asset = submit_thumbnail_assets(project, request, db, retry_count=old.retry_count + 1)[
            0
        ]
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_thumbnail_asset, new_asset.id)
    return new_asset


@router.post("/api/thumbnail-assets/{asset_id}/approve", response_model=ThumbnailAssetRead)
def approve_thumbnail_asset(asset_id: int, db: DatabaseSession) -> ThumbnailAsset:
    try:
        return approve_thumbnail(_asset(asset_id, db), db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/thumbnail-assets/{asset_id}/reject", response_model=ThumbnailAssetRead)
def reject_thumbnail_asset(asset_id: int, db: DatabaseSession) -> ThumbnailAsset:
    asset = _asset(asset_id, db)
    if asset.status not in {ThumbnailStatus.COMPLETED, ThumbnailStatus.APPROVED}:
        raise HTTPException(status_code=409, detail="Only completed thumbnails can be rejected")
    asset.status = ThumbnailStatus.REJECTED
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/api/thumbnail-assets/{asset_id}/download")
def download_thumbnail(asset_id: int, db: DatabaseSession) -> FileResponse:
    asset = _asset(asset_id, db)
    if not asset.local_path or asset.status in {ThumbnailStatus.PENDING, ThumbnailStatus.FAILED}:
        raise HTTPException(status_code=409, detail="Thumbnail file is not ready")
    path = Path(asset.local_path).resolve()
    root = (
        Path(get_settings().media_root).resolve() / str(asset.project_id) / "thumbnails"
    ).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail file is missing")
    return FileResponse(path, media_type="image/png", filename=path.name)
