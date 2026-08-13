from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.jobs import RenderJob
from app.models.project import Project
from app.schemas.export import ExportBundle, ExportSettings, PreflightReport, RenderJobRead
from app.services.rendering import preflight_project, run_render_job, submit_render_job

router = APIRouter(tags=["export"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _project(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _job(job_id: int, db: Session) -> RenderJob:
    job = db.get(RenderJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job


def _bundle(project: Project, db: Session) -> ExportBundle:
    jobs = list(
        db.scalars(
            select(RenderJob)
            .where(RenderJob.project_id == project.id)
            .order_by(RenderJob.created_at.desc(), RenderJob.id.desc())
        )
    )
    current = jobs[0] if jobs else None
    settings = (
        ExportSettings.model_validate(current.settings_json)
        if current and current.settings_json
        else ExportSettings(fps=get_settings().timeline_fps)
    )
    return ExportBundle(
        project_id=project.id,
        preflight=preflight_project(project, db, settings),
        current=current,
        jobs=jobs,
        download_url=(
            f"/api/render-jobs/{current.id}/download"
            if current and current.status == "COMPLETED" and current.output_path
            else None
        ),
    )


@router.get("/api/projects/{project_id}/export", response_model=ExportBundle)
def get_export(project_id: int, db: DatabaseSession) -> ExportBundle:
    return _bundle(_project(project_id, db), db)


@router.post("/api/projects/{project_id}/export/preflight", response_model=PreflightReport)
def run_preflight(project_id: int, payload: ExportSettings, db: DatabaseSession) -> PreflightReport:
    return preflight_project(_project(project_id, db), db, payload)


@router.post(
    "/api/projects/{project_id}/export/render",
    response_model=RenderJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_render(
    project_id: int,
    payload: ExportSettings,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> RenderJob:
    try:
        job = submit_render_job(_project(project_id, db), payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_render_job, job.id)
    return job


@router.post("/api/render-jobs/{job_id}/cancel", response_model=RenderJobRead)
def cancel_render(job_id: int, db: DatabaseSession) -> RenderJob:
    job = _job(job_id, db)
    if job.status not in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail="Only active renders can be canceled")
    job.cancel_requested = True
    if job.status == "PENDING":
        job.status = "CANCELED"
    db.commit()
    db.refresh(job)
    return job


@router.post(
    "/api/render-jobs/{job_id}/retry",
    response_model=RenderJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_render(job_id: int, background_tasks: BackgroundTasks, db: DatabaseSession) -> RenderJob:
    old = _job(job_id, db)
    if old.status not in {"FAILED", "CANCELED"}:
        raise HTTPException(
            status_code=409, detail="Only failed or canceled renders can be retried"
        )
    if old.retry_count >= get_settings().render_max_retries:
        raise HTTPException(status_code=409, detail="Render retry limit reached")
    project = _project(old.project_id, db)
    try:
        job = submit_render_job(
            project,
            ExportSettings.model_validate(old.settings_json),
            db,
            retry_count=old.retry_count + 1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(run_render_job, job.id)
    return job


@router.get("/api/render-jobs/{job_id}/download")
def download_render(job_id: int, db: DatabaseSession) -> FileResponse:
    job = _job(job_id, db)
    if job.status != "COMPLETED" or not job.output_path:
        raise HTTPException(status_code=409, detail="Render output is not ready")
    path = Path(job.output_path).resolve()
    root = (Path(get_settings().media_root).resolve() / str(job.project_id) / "renders").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Render output file is missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.delete("/api/render-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_render(job_id: int, db: DatabaseSession) -> Response:
    job = _job(job_id, db)
    if job.status in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail="Cancel an active render before deleting it")
    if job.output_path:
        path = Path(job.output_path).resolve()
        root = (
            Path(get_settings().media_root).resolve() / str(job.project_id) / "renders"
        ).resolve()
        if path.is_relative_to(root):
            path.unlink(missing_ok=True)
    db.delete(job)
    db.commit()
    return Response(status_code=204)
