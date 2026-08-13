from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.audio import AudioAssetKind


class AudioAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    scene_id: int | None
    kind: AudioAssetKind
    public_url: HttpUrl
    original_filename: str
    mime_type: str
    size_bytes: int
    duration: float
    source_name: str
    source_url: str | None
    license: str
    attribution: str | None
    created_at: datetime


class AudioSettingsUpdate(BaseModel):
    subtitles_enabled: bool = True
    subtitle_font_size: int = Field(42, ge=18, le=96)
    subtitle_position: str = Field("BOTTOM", pattern="^(TOP|MIDDLE|BOTTOM)$")
    subtitle_outline: bool = True
    subtitle_background: bool = False
    subtitle_safe_margin: int = Field(60, ge=0, le=300)
    music_enabled: bool = False
    music_asset_id: int | None = None
    music_volume: float = Field(0.18, ge=0, le=1)
    music_fade_in: float = Field(2, ge=0, le=30)
    music_fade_out: float = Field(2, ge=0, le=30)
    ducking_ratio: float = Field(8, ge=2, le=20)
    ambient_enabled: bool = False
    ambient_volume: float = Field(0.12, ge=0, le=1)

    @model_validator(mode="after")
    def music_selection(self) -> "AudioSettingsUpdate":
        if self.music_enabled and self.music_asset_id is None:
            raise ValueError("Select a music asset before enabling music")
        return self


class AudioSettingsRead(AudioSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int


class AudioBundle(BaseModel):
    project_id: int
    settings: AudioSettingsRead
    assets: list[AudioAssetRead]
    srt_url: str | None
    mix_plan: dict
