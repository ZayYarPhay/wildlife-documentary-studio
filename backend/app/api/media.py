from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.media import MediaAsset
from app.models.scene import Scene
from app.schemas.media import MediaAssetRead, StockSearchBundle
from app.services.stock_media import StockMediaService, build_stock_queries

router = APIRouter(tags=["media"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def scene_or_404(scene_id: int, db: Session) -> Scene:
    scene = db.scalar(
        select(Scene).where(Scene.id == scene_id).options(selectinload(Scene.project))
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


def asset_or_404(asset_id: int, db: Session) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


def bundle(scene: Scene, db: Session) -> StockSearchBundle:
    assets = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scene_id == scene.id)
            .order_by(MediaAsset.relevance_score.desc(), MediaAsset.id)
        )
    )
    provider = get_settings().stock_media_provider
    is_mock = provider.lower() == "mock"
    queries = (
        list(assets[0].metadata_json.get("search_queries", []))
        if assets
        else build_stock_queries(scene)
    )
    return StockSearchBundle(
        scene_id=scene.id,
        provider=provider,
        is_mock=is_mock,
        queries=queries,
        selected_asset_id=scene.preferred_media_asset_id,
        assets=assets,
        warning=(
            "Mock candidates are UI/test placeholders. License is intentionally unconfirmed."
            if is_mock and assets
            else None
        ),
    )


@router.post("/api/scenes/{scene_id}/stock/search", response_model=StockSearchBundle)
async def search_stock(scene_id: int, db: DatabaseSession) -> StockSearchBundle:
    scene = scene_or_404(scene_id, db)
    try:
        await StockMediaService().search(scene, db)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stock provider failed: {exc}") from exc
    return bundle(scene_or_404(scene_id, db), db)


@router.get("/api/scenes/{scene_id}/stock", response_model=StockSearchBundle)
def get_stock(scene_id: int, db: DatabaseSession) -> StockSearchBundle:
    return bundle(scene_or_404(scene_id, db), db)


@router.post("/api/media-assets/{asset_id}/select", response_model=MediaAssetRead)
def select_asset(asset_id: int, db: DatabaseSession) -> MediaAsset:
    asset = asset_or_404(asset_id, db)
    scene = scene_or_404(asset.scene_id, db)
    return StockMediaService.select_asset(asset, scene, db)


@router.post("/api/media-assets/{asset_id}/reject", response_model=MediaAssetRead)
def reject_asset(asset_id: int, db: DatabaseSession) -> MediaAsset:
    asset = asset_or_404(asset_id, db)
    scene = scene_or_404(asset.scene_id, db)
    return StockMediaService.reject_asset(asset, scene, db)
