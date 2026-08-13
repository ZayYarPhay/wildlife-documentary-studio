import secrets
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.worker import WorkerJob
from app.schemas.worker import (
    WorkerClaim,
    WorkerClaimRequest,
    WorkerFailure,
    WorkerJobRead,
    WorkerProgress,
    WorkerQueueHealth,
)
from app.services.worker_queue import (
    claim_next_job,
    complete_worker_job,
    fail_worker_job,
    queue_health,
    update_worker_progress,
    validate_worker_asset_access,
)

router = APIRouter(tags=["gpu-worker"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def require_worker_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().worker_auth_token
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=401,
            detail="Valid worker bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )


WorkerAuth = Annotated[None, Depends(require_worker_token)]


def job_or_404(job_id: int, db: Session) -> WorkerJob:
    job = db.get(WorkerJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Worker job not found")
    return job


@router.get("/api/worker/queue/health", response_model=WorkerQueueHealth)
def worker_queue_health(_: WorkerAuth, db: DatabaseSession) -> WorkerQueueHealth:
    return queue_health(db)


@router.post("/api/worker/jobs/claim", response_model=WorkerClaim)
def claim_worker_job(
    payload: WorkerClaimRequest, _: WorkerAuth, db: DatabaseSession
) -> WorkerClaim | Response:
    try:
        claimed = claim_next_job(payload.worker_id, payload.accepted_job_types, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return claimed if claimed is not None else Response(status_code=204)


@router.post("/api/worker/jobs/{job_id}/progress", response_model=WorkerJobRead)
def report_worker_progress(
    job_id: int, payload: WorkerProgress, _: WorkerAuth, db: DatabaseSession
) -> WorkerJob:
    try:
        return update_worker_progress(
            job_or_404(job_id, db), payload.worker_id, payload.progress, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/worker/jobs/{job_id}/complete", response_model=WorkerJobRead)
async def report_worker_completion(
    job_id: int,
    _: WorkerAuth,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
    worker_id: Annotated[str, Form(min_length=1, max_length=200)],
    result_json: Annotated[str, Form()] = "{}",
) -> WorkerJob:
    try:
        completed = await complete_worker_job(
            job_or_404(job_id, db), worker_id, file, result_json, db
        )
        from app.services.workflow import resume_remote_workflow

        background_tasks.add_task(resume_remote_workflow, completed.project_id)
        return completed
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/worker/jobs/{job_id}/fail", response_model=WorkerJobRead)
def report_worker_failure(
    job_id: int, payload: WorkerFailure, _: WorkerAuth, db: DatabaseSession
) -> WorkerJob:
    try:
        failed = fail_worker_job(
            job_or_404(job_id, db),
            payload.worker_id,
            payload.error_message,
            payload.diagnostics,
            db,
        )
        from app.services.workflow import fail_remote_workflow

        fail_remote_workflow(failed.project_id, payload.error_message, db)
        return failed
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/worker/assets/{asset_id}")
def download_worker_input(
    asset_id: int, worker_id: str, _: WorkerAuth, db: DatabaseSession
) -> FileResponse:
    try:
        asset = validate_worker_asset_access(asset_id, worker_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    path = Path(asset.local_path or "")
    return FileResponse(path, filename=path.name)
