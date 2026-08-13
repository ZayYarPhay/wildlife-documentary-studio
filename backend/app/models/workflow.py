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


class WorkflowMode(str, enum.Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


class WorkflowRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    VOICE_WAITING = "VOICE_WAITING"
    FAILED = "FAILED"
    RENDER_READY = "RENDER_READY"
    CANCELED = "CANCELED"


class WorkflowStepStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("project_id", "active_key", name="uq_project_active_workflow"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    mode: Mapped[WorkflowMode] = mapped_column(Enum(WorkflowMode))
    status: Mapped[WorkflowRunStatus] = mapped_column(Enum(WorkflowRunStatus), index=True)
    active_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_operation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    current_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )
    progress: Mapped[float] = mapped_column(Float, default=0)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["WorkflowStep"]] = relationship(
        cascade="all, delete-orphan", order_by="WorkflowStep.order"
    )


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("workflow_run_id", "name", name="uq_workflow_step_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    order: Mapped[int] = mapped_column(Integer)
    status: Mapped[WorkflowStepStatus] = mapped_column(Enum(WorkflowStepStatus))
    progress: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    operation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
