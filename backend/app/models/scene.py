import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.project import Project


class VisualStrategy(str, enum.Enum):
    STOCK_VIDEO = "STOCK_VIDEO"
    AI_IMAGE_MOTION = "AI_IMAGE_MOTION"
    AI_VIDEO = "AI_VIDEO"


class SceneStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer)
    narration_text: Mapped[str] = mapped_column(Text)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    target_duration: Mapped[float] = mapped_column(Float)
    species: Mapped[str] = mapped_column(String(200))
    environment: Mapped[str] = mapped_column(String(500))
    animal_behavior: Mapped[str] = mapped_column(String(300))
    visual_description: Mapped[str] = mapped_column(Text)
    shot_type: Mapped[str] = mapped_column(String(100))
    camera_motion: Mapped[str] = mapped_column(String(100))
    visual_strategy: Mapped[VisualStrategy] = mapped_column(Enum(VisualStrategy))
    status: Mapped[SceneStatus] = mapped_column(Enum(SceneStatus), default=SceneStatus.READY)
    preferred_media_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompts: Mapped[list["ScenePrompt"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan", order_by="ScenePrompt.version"
    )
    project: Mapped["Project"] = relationship()


class ScenePrompt(Base):
    __tablename__ = "scene_prompts"
    __table_args__ = (UniqueConstraint("scene_id", "version", name="uq_scene_prompt_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    image_prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text)
    video_prompt: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)

    scene: Mapped[Scene] = relationship(back_populates="prompts")
