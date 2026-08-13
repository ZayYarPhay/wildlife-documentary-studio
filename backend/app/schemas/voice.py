from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.voice import VoiceTrackStatus


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    start_time: float
    end_time: float
    text: str
    confidence: float | None


class TranscriptSegmentUpdate(BaseModel):
    text: str = Field(min_length=1)


class SceneVoiceAlignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scene_id: int
    recommended_start: float
    recommended_end: float
    confidence: float
    mismatch: bool
    visual_adjustment: str
    manually_edited: bool


class SceneVoiceAlignmentUpdate(BaseModel):
    recommended_start: float = Field(ge=0)
    recommended_end: float = Field(gt=0)

    @model_validator(mode="after")
    def valid_range(self) -> "SceneVoiceAlignmentUpdate":
        if self.recommended_end <= self.recommended_start:
            raise ValueError("recommended_end must be after recommended_start")
        return self


class VoiceTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    public_url: HttpUrl
    original_filename: str
    mime_type: str
    size_bytes: int
    duration: float
    language: str
    status: VoiceTrackStatus
    alignment_confidence: float | None
    mismatch_warning: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    segments: list[TranscriptSegmentRead]
    alignments: list[SceneVoiceAlignmentRead]


class VoiceBundle(BaseModel):
    project_id: int
    provider: str
    is_mock: bool
    active: VoiceTrackRead | None
    tracks: list[VoiceTrackRead]
    warning: str | None = None
