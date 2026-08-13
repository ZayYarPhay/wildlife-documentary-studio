from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExportSettings(BaseModel):
    fps: int = Field(default=24, ge=12, le=60)
    crf: int = Field(default=20, ge=15, le=35)
    preset: Literal["ultrafast", "veryfast", "faster", "fast", "medium", "slow"] = "medium"
    subtitles_enabled: bool = True
    audio_mix_enabled: bool = True


class PreflightCheck(BaseModel):
    code: str
    label: str
    status: Literal["PASS", "WARNING", "ERROR"]
    detail: str


class PreflightReport(BaseModel):
    project_id: int
    timeline_id: int | None
    ready: bool
    checks: list[PreflightCheck]
    estimated_required_bytes: int
    free_bytes: int


class RenderJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    timeline_id: int | None
    status: str
    progress: float
    retry_count: int
    cancel_requested: bool
    settings_json: dict[str, Any]
    validation_json: dict[str, Any]
    logs: str | None
    output_path: str | None
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    file_size_bytes: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ExportBundle(BaseModel):
    project_id: int
    preflight: PreflightReport
    current: RenderJobRead | None
    jobs: list[RenderJobRead]
    download_url: str | None


class ProjectStorageReport(BaseModel):
    project_id: int
    usage_bytes: int
    file_count: int
    missing_asset_ids: list[int]
    generation_job_count: int
    render_job_count: int


class MediaMaintenanceReport(ProjectStorageReport):
    removed_asset_ids: list[int]
    removed_files: int
    proxies_created: int
