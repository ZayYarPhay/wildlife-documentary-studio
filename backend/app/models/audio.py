import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.project import utcnow


class AudioAssetKind(str, enum.Enum):
    MUSIC = "MUSIC"
    AMBIENT = "AMBIENT"


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[AudioAssetKind] = mapped_column(Enum(AudioAssetKind), index=True)
    path: Mapped[str] = mapped_column(String(1000))
    public_url: Mapped[str] = mapped_column(String(2000))
    original_filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    license: Mapped[str] = mapped_column(String(500))
    attribution: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AudioSettings(Base):
    __tablename__ = "audio_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    subtitles_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    subtitle_font_size: Mapped[int] = mapped_column(Integer, default=42)
    subtitle_position: Mapped[str] = mapped_column(String(20), default="BOTTOM")
    subtitle_outline: Mapped[bool] = mapped_column(Boolean, default=True)
    subtitle_background: Mapped[bool] = mapped_column(Boolean, default=False)
    subtitle_safe_margin: Mapped[int] = mapped_column(Integer, default=60)
    music_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    music_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True
    )
    music_volume: Mapped[float] = mapped_column(Float, default=0.18)
    music_fade_in: Mapped[float] = mapped_column(Float, default=2.0)
    music_fade_out: Mapped[float] = mapped_column(Float, default=2.0)
    ducking_ratio: Mapped[float] = mapped_column(Float, default=8.0)
    ambient_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ambient_volume: Mapped[float] = mapped_column(Float, default=0.12)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    music_asset: Mapped[AudioAsset | None] = relationship(foreign_keys=[music_asset_id])
