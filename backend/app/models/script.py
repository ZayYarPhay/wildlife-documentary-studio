from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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

if TYPE_CHECKING:
    from app.models.project import Project


class Script(Base):
    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_script_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    tone: Mapped[str] = mapped_column(String(100))
    full_text: Mapped[str] = mapped_column(Text)
    estimated_words: Mapped[int] = mapped_column(Integer)
    estimated_duration_seconds: Mapped[float] = mapped_column(Float)
    length_status: Mapped[str] = mapped_column(String(30), default="ON_TARGET")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sections: Mapped[list["ScriptSection"]] = relationship(
        back_populates="script",
        cascade="all, delete-orphan",
        order_by="ScriptSection.order",
    )
    project: Mapped["Project"] = relationship()


class ScriptSection(Base):
    __tablename__ = "script_sections"
    __table_args__ = (UniqueConstraint("script_id", "order", name="uq_script_section_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    estimated_duration_seconds: Mapped[float] = mapped_column(Float)
    source_fact_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    script: Mapped[Script] = relationship(back_populates="sections")
