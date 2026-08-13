import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.project import utcnow


class VoiceTrackStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    READY = "READY"
    FAILED = "FAILED"
    APPLIED = "APPLIED"


class VoiceTrack(Base):
    __tablename__ = "voice_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(1000))
    public_url: Mapped[str] = mapped_column(String(2000))
    original_filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float] = mapped_column(Float)
    language: Mapped[str] = mapped_column(String(50))
    status: Mapped[VoiceTrackStatus] = mapped_column(Enum(VoiceTrackStatus))
    alignment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mismatch_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        cascade="all, delete-orphan", order_by="TranscriptSegment.start_time"
    )
    alignments: Mapped[list["SceneVoiceAlignment"]] = relationship(cascade="all, delete-orphan")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    voice_track_id: Mapped[int] = mapped_column(
        ForeignKey("voice_tracks.id", ondelete="CASCADE"), index=True
    )
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class SceneVoiceAlignment(Base):
    __tablename__ = "scene_voice_alignments"
    __table_args__ = (
        UniqueConstraint("voice_track_id", "scene_id", name="uq_voice_scene_alignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    voice_track_id: Mapped[int] = mapped_column(
        ForeignKey("voice_tracks.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    recommended_start: Mapped[float] = mapped_column(Float)
    recommended_end: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    visual_adjustment: Mapped[str] = mapped_column(String(100))
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False)
