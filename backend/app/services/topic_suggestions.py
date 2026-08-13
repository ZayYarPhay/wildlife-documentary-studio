import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import Project
from app.providers.base import TopicSuggestionProvider
from app.providers.mock_topics import MockTopicSuggestionProvider
from app.schemas.topic import (
    TopicCategory,
    TopicSuggestion,
    TopicSuggestionBundle,
    TopicSuggestionRequest,
    TopicSurpriseRequest,
    VisualPreference,
)


def get_topic_provider() -> TopicSuggestionProvider:
    name = get_settings().topic_suggestion_provider.lower()
    if name == "mock":
        return MockTopicSuggestionProvider()
    raise ValueError(f"Unsupported topic suggestion provider: {name}")


class TopicSuggestionService:
    def __init__(self, provider: TopicSuggestionProvider | None = None):
        self.provider = provider or get_topic_provider()

    async def suggest(self, request: TopicSuggestionRequest, db: Session) -> TopicSuggestionBundle:
        recent = self._recent_topics(db)
        raw = await asyncio.wait_for(
            self.provider.suggest(
                request.category.value,
                recent,
                request.count,
                duration_seconds=request.duration_seconds,
                visual_preference=request.visual_preference.value,
            ),
            timeout=get_settings().topic_suggestion_timeout_seconds,
        )
        suggestions = self._normalize(raw, request, recent)
        if not suggestions:
            raise RuntimeError("Topic provider returned no usable suggestions")
        return TopicSuggestionBundle(
            provider=getattr(self.provider, "name", self.provider.__class__.__name__),
            is_mock=bool(getattr(self.provider, "is_mock", False)),
            suggestions=suggestions,
            excluded_recent_topics=recent,
            warning=(
                "Mock suggestions are curated development data. Stock availability is an estimate, "
                "not a live provider search."
                if getattr(self.provider, "is_mock", False)
                else None
            ),
        )

    async def surprise(self, request: TopicSurpriseRequest, db: Session) -> TopicSuggestionBundle:
        categories = [request.category] if request.category else list(TopicCategory)
        recent = self._recent_topics(db)
        offset = len(recent) % len(categories)
        ordered = categories[offset:] + categories[:offset]
        for category in ordered:
            bundle = await self.suggest(
                TopicSuggestionRequest(
                    category=category,
                    count=1,
                    duration_seconds=request.duration_seconds,
                    visual_preference=request.visual_preference,
                ),
                db,
            )
            if bundle.suggestions and not bundle.suggestions[0].recently_used:
                return bundle
        return await self.suggest(
            TopicSuggestionRequest(
                category=ordered[0],
                count=1,
                duration_seconds=request.duration_seconds,
                visual_preference=request.visual_preference,
            ),
            db,
        )

    @staticmethod
    def categories() -> list[dict[str, str]]:
        descriptions = {
            "MAMMALS": "Land and tree-dwelling mammals with broad footage availability.",
            "BIRDS": "Flight, migration, courtship and nesting stories.",
            "REPTILES": "Ancient adaptations across deserts, rivers and islands.",
            "OCEAN": "Marine wildlife, underwater behavior and migration.",
            "INSECTS": "Macro-scale societies, life cycles and survival strategies.",
            "RARE_ANIMALS": "Conservation-led stories with potentially limited footage.",
            "PREDATORS": "Hunting ecology without sensationalizing animal behavior.",
        }
        return [
            {
                "value": item.value,
                "label": item.value.replace("_", " ").title(),
                "description": descriptions[item.value],
            }
            for item in TopicCategory
        ]

    @staticmethod
    def _recent_topics(db: Session) -> list[str]:
        limit = get_settings().topic_recent_project_limit
        topics = db.scalars(
            select(Project.animal_topic)
            .where(Project.animal_topic.is_not(None))
            .order_by(Project.created_at.desc(), Project.id.desc())
            .limit(limit)
        )
        seen: set[str] = set()
        result = []
        for topic in topics:
            normalized = str(topic).strip()
            if normalized and normalized.casefold() not in seen:
                seen.add(normalized.casefold())
                result.append(normalized)
        return result

    @staticmethod
    def _normalize(
        raw: list[dict[str, Any]], request: TopicSuggestionRequest, recent: list[str]
    ) -> list[TopicSuggestion]:
        used = {item.casefold() for item in recent}
        unique: set[str] = set()
        suggestions: list[TopicSuggestion] = []
        for item in raw:
            topic = str(item.get("topic", "")).strip()
            key = topic.casefold()
            if not topic or key in unique:
                continue
            unique.add(key)
            score = max(0, min(100, int(item.get("stock_score", 50))))
            availability = "HIGH" if score >= 80 else "MEDIUM" if score >= 55 else "LOW"
            difficulty, reasons = _difficulty(
                score, request.duration_seconds, request.visual_preference, request.category
            )
            suggestions.append(
                TopicSuggestion(
                    topic=topic,
                    scientific_name=item.get("scientific_name"),
                    category=request.category,
                    hook=str(item.get("hook", "")).strip(),
                    stock_availability=availability,
                    stock_score=score,
                    production_difficulty=difficulty,
                    difficulty_reasons=reasons,
                    recommended_visual_mix=_visual_mix(score, request.visual_preference),
                    recently_used=key in used,
                )
            )
        return sorted(suggestions, key=lambda item: (item.recently_used, -item.stock_score))[
            : request.count
        ]


def _difficulty(
    stock_score: int,
    duration_seconds: int,
    preference: VisualPreference,
    category: TopicCategory,
) -> tuple[str, list[str]]:
    points = 0
    reasons: list[str] = []
    if stock_score < 55:
        points += 2
        reasons.append("Limited stock footage is likely")
    elif stock_score < 80:
        points += 1
        reasons.append("Some scenes may need generated visuals")
    else:
        reasons.append("Strong stock-footage potential")
    if duration_seconds > 600:
        points += 1
        reasons.append("Long duration needs more distinct visual coverage")
    if category == TopicCategory.RARE_ANIMALS:
        points += 1
        reasons.append("Rare species require careful sourcing and conservation context")
    if preference == VisualPreference.ECONOMY and stock_score < 55:
        points += 1
        reasons.append("Economy mode has fewer AI fallback options")
    elif preference == VisualPreference.MAX_AI:
        reasons.append("Max AI mode increases GPU time and review work")
    level = "EASY" if points == 0 else "MEDIUM" if points <= 2 else "HARD"
    return level, reasons[:5]


def _visual_mix(stock_score: int, preference: VisualPreference) -> dict[str, int]:
    if preference == VisualPreference.ECONOMY:
        stock = 75 if stock_score >= 70 else 55
        video = 5
    elif preference == VisualPreference.MAX_AI:
        stock = 25 if stock_score >= 70 else 15
        video = 45
    else:
        stock = 55 if stock_score >= 70 else 35
        video = 20 if stock_score >= 70 else 30
    return {"stock": stock, "ai_image_motion": 100 - stock - video, "ai_video": video}
