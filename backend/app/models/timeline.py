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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.project import utcnow


class TimelineTrack(str, enum.Enum):
    VISUAL = "VISUAL"
    VOICE = "VOICE"
    MUSIC = "MUSIC"
    AMBIENT = "AMBIENT"
    SUBTITLE = "SUBTITLE"


class Timeline(Base):
    __tablename__ = "timelines"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_timeline_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    voice_track_id: Mapped[int] = mapped_column(ForeignKey("voice_tracks.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float] = mapped_column(Float)
    output_resolution: Mapped[str] = mapped_column(String(20))
    fps: Mapped[int] = mapped_column(Integer)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    render_plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["TimelineItem"]] = relationship(
        cascade="all, delete-orphan", order_by="TimelineItem.order"
    )


class TimelineItem(Base):
    __tablename__ = "timeline_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    timeline_id: Mapped[int] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[TimelineTrack] = mapped_column(Enum(TimelineTrack), index=True)
    order: Mapped[int] = mapped_column(Integer)
    scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    voice_track_id: Mapped[int | None] = mapped_column(
        ForeignKey("voice_tracks.id", ondelete="SET NULL"), nullable=True
    )
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    source_in: Mapped[float] = mapped_column(Float, default=0)
    source_out: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition: Mapped[str] = mapped_column(String(50), default="CUT")
    effect: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
