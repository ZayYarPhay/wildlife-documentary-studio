import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.project import utcnow


class MediaAssetType(str, enum.Enum):
    STOCK_VIDEO = "STOCK_VIDEO"
    STOCK_IMAGE = "STOCK_IMAGE"
    AI_IMAGE = "AI_IMAGE"
    AI_VIDEO = "AI_VIDEO"
    AUDIO = "AUDIO"
    MUSIC = "MUSIC"
    SFX = "SFX"


class MediaAssetStatus(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint(
            "scene_id", "provider", "provider_asset_id", name="uq_scene_provider_asset"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    provider_asset_id: Mapped[str] = mapped_column(String(300))
    type: Mapped[MediaAssetType] = mapped_column(Enum(MediaAssetType))
    preview_url: Mapped[str] = mapped_column(String(2000))
    download_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_page_url: Mapped[str] = mapped_column(String(2000))
    creator: Mapped[str | None] = mapped_column(String(300), nullable=True)
    license: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attribution_requirements: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[MediaAssetStatus] = mapped_column(
        Enum(MediaAssetStatus), default=MediaAssetStatus.CANDIDATE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
