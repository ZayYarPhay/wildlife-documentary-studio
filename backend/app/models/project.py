import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RESEARCHING = "RESEARCHING"
    RESEARCH_REVIEW = "RESEARCH_REVIEW"
    SCRIPTING = "SCRIPTING"
    SCRIPT_REVIEW = "SCRIPT_REVIEW"
    SCENE_PLANNING = "SCENE_PLANNING"
    SCENE_REVIEW = "SCENE_REVIEW"
    FAILED = "FAILED"


class ProjectPhase(str, enum.Enum):
    FOUNDATION = "FOUNDATION"
    RESEARCH = "RESEARCH"
    RESEARCH_REVIEW = "RESEARCH_REVIEW"
    SCRIPT = "SCRIPT"
    SCRIPT_REVIEW = "SCRIPT_REVIEW"
    SCENES = "SCENES"
    SCENE_REVIEW = "SCENE_REVIEW"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    animal_topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auto_topic: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(50))
    requested_duration_seconds: Mapped[int] = mapped_column(Integer)
    output_resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
    documentary_tone: Mapped[str] = mapped_column(
        String(100), default="cinematic wildlife documentary"
    )
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.DRAFT)
    current_phase: Mapped[ProjectPhase] = mapped_column(
        Enum(ProjectPhase), default=ProjectPhase.FOUNDATION
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
