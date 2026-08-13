from pydantic import BaseModel, Field

from app.schemas.image_generation import GenerationJobRead
from app.schemas.media import MediaAssetRead
from app.schemas.scene import ScenePromptRead


class VideoPromptCreate(BaseModel):
    video_prompt: str = Field(min_length=10)


class VideoGenerateRequest(BaseModel):
    prompt_id: int
    source_asset_id: int
    duration: float | None = Field(default=None, ge=1, le=30)
    fps: int | None = Field(default=None, ge=12, le=60)


class VideoGenerationBundle(BaseModel):
    scene_id: int
    provider: str
    is_mock: bool
    selected_asset_id: int | None
    selected_image_asset_id: int | None
    prompts: list[ScenePromptRead]
    jobs: list[GenerationJobRead]
    assets: list[MediaAssetRead]
    fallback_recommendations: list[str]
    warning: str | None = None
