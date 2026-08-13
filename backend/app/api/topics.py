from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.topic import (
    TopicSuggestionBundle,
    TopicSuggestionRequest,
    TopicSurpriseRequest,
)
from app.services.topic_suggestions import TopicSuggestionService

router = APIRouter(prefix="/api/topics", tags=["topics"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/categories")
def topic_categories() -> list[dict[str, str]]:
    return TopicSuggestionService.categories()


@router.post("/suggest", response_model=TopicSuggestionBundle)
async def suggest_topics(
    payload: TopicSuggestionRequest, db: DatabaseSession
) -> TopicSuggestionBundle:
    try:
        return await TopicSuggestionService().suggest(payload, db)
    except (TimeoutError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Topic suggestion failed: {exc}") from exc


@router.post("/surprise", response_model=TopicSuggestionBundle)
async def surprise_topic(
    payload: TopicSurpriseRequest, db: DatabaseSession
) -> TopicSuggestionBundle:
    try:
        return await TopicSuggestionService().surprise(payload, db)
    except (TimeoutError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Topic suggestion failed: {exc}") from exc
