from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.project import Project
from app.models.workflow import WorkflowRun
from app.schemas.workflow import WorkflowBundle, WorkflowRunRead, WorkflowStart
from app.services.workflow import (
    cancel_workflow,
    create_workflow_run,
    load_workflow_run,
    prepare_resume,
    prepare_retry,
    request_pause,
    run_workflow,
    workflow_runs,
)

router = APIRouter(tags=["workflow"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def run_or_404(run_id: int, db: Session) -> WorkflowRun:
    try:
        return load_workflow_run(run_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def bundle(project_id: int, db: Session) -> WorkflowBundle:
    runs = workflow_runs(project_id, db)
    return WorkflowBundle(project_id=project_id, current=runs[0] if runs else None, runs=runs)


@router.get("/api/projects/{project_id}/workflow", response_model=WorkflowBundle)
def get_workflow(project_id: int, db: DatabaseSession) -> WorkflowBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return bundle(project_id, db)


@router.post(
    "/api/projects/{project_id}/workflow/start",
    response_model=WorkflowRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_workflow(
    project_id: int,
    payload: WorkflowStart,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> WorkflowRun:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        run = create_workflow_run(project, payload.mode, payload.policy, db)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Could not start workflow: {exc}") from exc
    if run.status.value == "PENDING":
        background_tasks.add_task(run_workflow, run.id)
    return run


@router.post("/api/workflows/{run_id}/pause", response_model=WorkflowRunRead)
def pause_workflow(run_id: int, db: DatabaseSession) -> WorkflowRun:
    try:
        return request_pause(run_or_404(run_id, db), db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/workflows/{run_id}/resume", response_model=WorkflowRunRead)
def resume_workflow(
    run_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> WorkflowRun:
    try:
        run = prepare_resume(run_or_404(run_id, db), db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_workflow, run.id)
    return run


@router.post("/api/workflows/{run_id}/retry", response_model=WorkflowRunRead)
def retry_workflow(
    run_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> WorkflowRun:
    try:
        run = prepare_retry(run_or_404(run_id, db), db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_workflow, run.id)
    return run


@router.post("/api/workflows/{run_id}/cancel", response_model=WorkflowRunRead)
def cancel_run(run_id: int, db: DatabaseSession) -> WorkflowRun:
    try:
        return cancel_workflow(run_or_404(run_id, db), db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
