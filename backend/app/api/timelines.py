from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.project import Project
from app.models.timeline import Timeline, TimelineItem
from app.schemas.timeline import TimelineBundle, TimelineItemRead, TimelineItemUpdate, TimelineRead
from app.services.timeline import build_timeline, load_timeline, validate_timeline

router = APIRouter(tags=["timelines"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def timeline_or_404(timeline_id: int, db: Session) -> Timeline:
    timeline = db.scalar(
        select(Timeline).where(Timeline.id == timeline_id).options(selectinload(Timeline.items))
    )
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    return timeline


def timeline_bundle(project_id: int, db: Session) -> TimelineBundle:
    versions = list(
        db.scalars(
            select(Timeline)
            .where(Timeline.project_id == project_id)
            .options(selectinload(Timeline.items))
            .order_by(Timeline.version.desc())
        )
    )
    return TimelineBundle(
        project_id=project_id, current=versions[0] if versions else None, versions=versions
    )


@router.get("/api/projects/{project_id}/timeline", response_model=TimelineBundle)
def get_timeline(project_id: int, db: DatabaseSession) -> TimelineBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return timeline_bundle(project_id, db)


@router.post("/api/projects/{project_id}/timeline/build", response_model=TimelineBundle)
def rebuild_timeline(project_id: int, db: DatabaseSession) -> TimelineBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        build_timeline(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return timeline_bundle(project_id, db)


@router.patch("/api/timeline-items/{item_id}", response_model=TimelineItemRead)
def update_timeline_item(
    item_id: int, payload: TimelineItemUpdate, db: DatabaseSession
) -> TimelineItem:
    item = db.get(TimelineItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    values = payload.model_dump(exclude_unset=True)
    start = values.get("start_time", item.start_time)
    end = values.get("end_time", item.end_time)
    source_in = values.get("source_in", item.source_in)
    source_out = values.get("source_out", item.source_out)
    if end <= start:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")
    if source_out is not None and source_out < source_in:
        raise HTTPException(status_code=422, detail="source_out must not be before source_in")
    for key, value in values.items():
        setattr(item, key, value)
    timeline = db.get(Timeline, item.timeline_id)
    if timeline is None:
        raise HTTPException(status_code=409, detail="Timeline no longer exists")
    db.flush()
    validate_timeline(timeline, db)
    db.commit()
    db.refresh(item)
    return item


@router.post("/api/timelines/{timeline_id}/validate", response_model=TimelineRead)
def validate_existing_timeline(timeline_id: int, db: DatabaseSession) -> Timeline:
    timeline = timeline_or_404(timeline_id, db)
    validate_timeline(timeline, db)
    db.commit()
    return load_timeline(timeline.id, db)
