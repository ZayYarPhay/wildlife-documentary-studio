from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.project import Project
from app.schemas.export import MediaMaintenanceReport, ProjectStorageReport
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.production import (
    delete_project_storage,
    maintain_project_media,
    project_storage_report,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])
DatabaseSession = Annotated[Session, Depends(get_db)]


class MediaMaintenanceRequest(BaseModel):
    cleanup_unused: bool = False


def get_project_or_404(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DatabaseSession) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.updated_at.desc())))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DatabaseSession) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: DatabaseSession) -> Project:
    return get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: DatabaseSession) -> Project:
    project = get_project_or_404(project_id, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    if not project.auto_topic and not (project.animal_topic and project.animal_topic.strip()):
        raise HTTPException(
            status_code=422, detail="animal_topic is required unless auto_topic is enabled"
        )
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/duplicate", response_model=ProjectRead, status_code=201)
def duplicate_project(project_id: int, db: DatabaseSession) -> Project:
    source = get_project_or_404(project_id, db)
    duplicate = Project(
        title=f"{source.title} (Copy)"[:200],
        animal_topic=source.animal_topic,
        auto_topic=source.auto_topic,
        language=source.language,
        requested_duration_seconds=source.requested_duration_seconds,
        output_resolution=source.output_resolution,
        documentary_tone=source.documentary_tone,
    )
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)
    return duplicate


@router.get("/{project_id}/storage", response_model=ProjectStorageReport)
def get_project_storage(project_id: int, db: DatabaseSession) -> ProjectStorageReport:
    get_project_or_404(project_id, db)
    return project_storage_report(project_id, db)


@router.post("/{project_id}/media/maintenance", response_model=MediaMaintenanceReport)
def maintain_media(
    project_id: int, payload: MediaMaintenanceRequest, db: DatabaseSession
) -> MediaMaintenanceReport:
    get_project_or_404(project_id, db)
    return maintain_project_media(project_id, payload.cleanup_unused, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: DatabaseSession) -> Response:
    project = get_project_or_404(project_id, db)
    db.delete(project)
    db.commit()
    delete_project_storage(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
