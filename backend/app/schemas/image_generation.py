from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.media import MediaAssetRead
from app.schemas.scene import ScenePromptRead


class ImagePromptCreate(BaseModel):
    image_prompt: str = Field(min_length=10)
    negative_prompt: str = Field(min_length=3)


class ImageGenerateRequest(BaseModel):
    prompt_id: int | None = None
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    reference_asset_ids: list[int] = Field(default_factory=list, max_length=8)


class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    scene_id: int | None
    job_type: str
    provider: str
    status: str
    progress: float
    retry_count: int
    prompt_id: int | None
    output_asset_id: int | None
    seed: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ImageGenerationBundle(BaseModel):
    scene_id: int
    provider: str
    is_mock: bool
    selected_asset_id: int | None
    prompts: list[ScenePromptRead]
    jobs: list[GenerationJobRead]
    assets: list[MediaAssetRead]
    warning: str | None = None
