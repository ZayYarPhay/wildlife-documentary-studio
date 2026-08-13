from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.thumbnail import ThumbnailStatus


class ThumbnailConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    concept_order: int
    name: str
    description: str
    prompt: str
    negative_prompt: str
    created_at: datetime


class ThumbnailAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    concept_id: int
    provider: str
    status: ThumbnailStatus
    public_url: str | None
    width: int
    height: int
    seed: int | None
    title_overlay: bool
    overlay_text: str | None
    retry_count: int
    metadata_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class ThumbnailGenerateRequest(BaseModel):
    concept_ids: list[int] = Field(default_factory=list, max_length=3)
    title_overlay: bool = False
    overlay_text: str | None = Field(default=None, max_length=120)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_overlay(self) -> "ThumbnailGenerateRequest":
        if self.title_overlay and not (self.overlay_text and self.overlay_text.strip()):
            raise ValueError("Overlay text is required when title overlay is enabled")
        return self


class ThumbnailBundle(BaseModel):
    project_id: int
    final_render_ready: bool
    provider: str
    is_mock: bool
    concepts: list[ThumbnailConceptRead]
    assets: list[ThumbnailAssetRead]
    approved_thumbnail_id: int | None
    warning: str | None = None
