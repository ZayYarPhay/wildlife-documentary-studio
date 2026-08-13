from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.models.media import MediaAssetStatus, MediaAssetType


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    scene_id: int
    provider: str
    provider_asset_id: str
    type: MediaAssetType
    preview_url: HttpUrl
    download_url: HttpUrl | None
    source_page_url: HttpUrl
    creator: str | None
    license: str | None
    attribution_requirements: str | None
    width: int | None
    height: int | None
    duration: float | None
    local_path: str | None
    metadata_json: dict[str, Any]
    relevance_score: float
    status: MediaAssetStatus
    created_at: datetime


class StockSearchBundle(BaseModel):
    scene_id: int
    provider: str
    is_mock: bool
    queries: list[str]
    selected_asset_id: int | None
    assets: list[MediaAssetRead]
    warning: str | None = None
