from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.workflow import WorkflowMode, WorkflowRunStatus, WorkflowStepStatus


class WorkflowPolicy(BaseModel):
    auto_approve_research: bool = True
    auto_approve_script: bool = True
    auto_select_media: bool = True
    generate_ai_video: bool = True
    fallback_missing_stock_to_image: bool = True


class WorkflowStart(BaseModel):
    mode: WorkflowMode = WorkflowMode.AUTO
    policy: WorkflowPolicy = Field(default_factory=WorkflowPolicy)


class WorkflowStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    order: int
    status: WorkflowStepStatus
    progress: float
    attempts: int
    operation: str | None
    error_message: str | None
    metadata_json: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    mode: WorkflowMode
    status: WorkflowRunStatus
    current_step: str | None
    current_operation: str | None
    current_job_id: int | None
    progress: float
    pause_requested: bool
    policy_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    steps: list[WorkflowStepRead]


class WorkflowBundle(BaseModel):
    project_id: int
    current: WorkflowRunRead | None
    runs: list[WorkflowRunRead]
