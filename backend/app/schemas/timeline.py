from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.timeline import TimelineTrack


class TimelineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    track: TimelineTrack
    order: int
    scene_id: int | None
    asset_id: int | None
    voice_track_id: int | None
    start_time: float
    end_time: float
    source_in: float
    source_out: float | None
    transition: str
    effect: str | None
    metadata_json: dict[str, Any]


class TimelineItemUpdate(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)
    source_in: float | None = Field(default=None, ge=0)
    source_out: float | None = Field(default=None, ge=0)
    transition: str | None = Field(default=None, max_length=50)
    effect: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def valid_ranges(self) -> "TimelineItemUpdate":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        if (
            self.source_in is not None
            and self.source_out is not None
            and self.source_out < self.source_in
        ):
            raise ValueError("source_out must not be before source_in")
        return self


class TimelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    voice_track_id: int
    version: int
    duration: float
    output_resolution: str
    fps: int
    valid: bool
    warnings_json: list[dict[str, Any]]
    render_plan_json: dict[str, Any]
    created_at: datetime
    items: list[TimelineItemRead]


class TimelineBundle(BaseModel):
    project_id: int
    current: TimelineRead | None
    versions: list[TimelineRead]
