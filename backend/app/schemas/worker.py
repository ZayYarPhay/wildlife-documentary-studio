from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.worker import WorkerJobStatus


class ImageWorkerParameters(BaseModel):
    width: int = Field(ge=64, le=8192)
    height: int = Field(ge=64, le=8192)
    seed: int | None = None


class VideoWorkerParameters(BaseModel):
    width: int = Field(ge=64, le=8192)
    height: int = Field(ge=64, le=8192)
    duration: float = Field(gt=0, le=60)
    fps: int = Field(ge=1, le=120)


class WorkerCallbackMetadata(BaseModel):
    progress_path: str = Field(max_length=500)
    complete_path: str = Field(max_length=500)
    fail_path: str = Field(max_length=500)


class ImageWorkerPayload(BaseModel):
    schema_version: Literal[1] = 1
    job_id: int
    project_id: int
    scene_id: int
    job_type: Literal["AI_IMAGE"]
    provider: str = Field(max_length=100)
    prompt: str = Field(min_length=1, max_length=30_000)
    negative_prompt: str = Field(default="", max_length=10_000)
    input_asset_ids: list[int] = Field(default_factory=list, max_length=10)
    parameters: ImageWorkerParameters
    callback_metadata: WorkerCallbackMetadata


class VideoWorkerPayload(BaseModel):
    schema_version: Literal[1] = 1
    job_id: int
    project_id: int
    scene_id: int
    job_type: Literal["AI_VIDEO"]
    provider: str = Field(max_length=100)
    prompt: str = Field(min_length=1, max_length=30_000)
    negative_prompt: str = ""
    input_asset_ids: list[int] = Field(min_length=1, max_length=1)
    parameters: VideoWorkerParameters
    callback_metadata: WorkerCallbackMetadata


WorkerPayload = Annotated[ImageWorkerPayload | VideoWorkerPayload, Field(discriminator="job_type")]


class WorkerAssetReference(BaseModel):
    asset_id: int
    download_url: str
    media_type: str


class WorkerJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    generation_job_id: int
    project_id: int
    scene_id: int
    job_type: str
    status: WorkerJobStatus
    progress: float
    attempts: int
    claimed_by: str | None
    lease_expires_at: datetime | None
    payload_json: dict
    result_json: dict
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class WorkerClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    accepted_job_types: list[Literal["AI_IMAGE", "AI_VIDEO"]] = Field(
        default_factory=lambda: ["AI_IMAGE", "AI_VIDEO"], min_length=1, max_length=2
    )


class WorkerClaim(BaseModel):
    job: WorkerJobRead
    payload: WorkerPayload
    input_assets: list[WorkerAssetReference]


class WorkerProgress(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    progress: float = Field(ge=0, le=1)


class WorkerFailure(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    error_message: str = Field(min_length=1, max_length=4000)
    diagnostics: dict = Field(default_factory=dict)


class WorkerQueueHealth(BaseModel):
    status: str
    execution_mode: str
    queued: int
    claimed: int
    running: int
    failed: int
    stale_recoverable: int
    token_is_default: bool
