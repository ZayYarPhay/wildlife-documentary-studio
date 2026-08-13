from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.project import Project
from app.models.research import ResearchFact
from app.schemas.research import ResearchBundle, ResearchFactRead, ResearchFactUpdate
from app.services.research import ResearchOrchestrator, normalize_claim

router = APIRouter(tags=["research"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def fact_or_404(fact_id: int, db: Session) -> ResearchFact:
    fact = db.scalar(
        select(ResearchFact)
        .where(ResearchFact.id == fact_id)
        .options(selectinload(ResearchFact.source))
    )
    if fact is None:
        raise HTTPException(status_code=404, detail="Research fact not found")
    return fact


def bundle(project_id: int, db: Session, provider: str = "configured") -> ResearchBundle:
    facts = list(
        db.scalars(
            select(ResearchFact)
            .where(ResearchFact.project_id == project_id)
            .options(selectinload(ResearchFact.source))
            .order_by(ResearchFact.category, ResearchFact.id)
        )
    )
    is_mock = any(bool(fact.source.metadata_json.get("mock")) for fact in facts)
    return ResearchBundle(
        project_id=project_id,
        status="review" if facts else "idle",
        provider="mock" if is_mock else provider,
        is_mock=is_mock,
        facts=facts,
        warning=(
            "Development placeholders only. Replace the mock provider and verify sources before approval."
            if is_mock
            else None
        ),
    )


@router.post("/api/projects/{project_id}/research/generate", response_model=ResearchBundle)
async def generate_research(project_id: int, db: DatabaseSession) -> ResearchBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = await ResearchOrchestrator().generate(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Research provider failed: {exc}") from exc
    return bundle(project_id, db, result.provider)


@router.get("/api/projects/{project_id}/research", response_model=ResearchBundle)
def get_research(project_id: int, db: DatabaseSession) -> ResearchBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return bundle(project_id, db)


@router.patch("/api/research/facts/{fact_id}", response_model=ResearchFactRead)
def update_fact(fact_id: int, payload: ResearchFactUpdate, db: DatabaseSession) -> ResearchFact:
    fact = fact_or_404(fact_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "claim" in changes:
        changes["claim"] = changes["claim"].strip()
        changes["normalized_claim"] = normalize_claim(changes["claim"])
    for key, value in changes.items():
        setattr(fact, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An equivalent fact already exists") from exc
    db.refresh(fact)
    return fact


@router.delete("/api/research/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(fact_id: int, db: DatabaseSession) -> Response:
    fact = fact_or_404(fact_id, db)
    db.delete(fact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/research/facts/{fact_id}/approve", response_model=ResearchFactRead)
def approve_fact(fact_id: int, db: DatabaseSession) -> ResearchFact:
    fact = fact_or_404(fact_id, db)
    fact.approved = True
    db.commit()
    db.refresh(fact)
    return fact
