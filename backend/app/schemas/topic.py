from enum import Enum

from pydantic import BaseModel, Field


class TopicCategory(str, Enum):
    MAMMALS = "MAMMALS"
    BIRDS = "BIRDS"
    REPTILES = "REPTILES"
    OCEAN = "OCEAN"
    INSECTS = "INSECTS"
    RARE_ANIMALS = "RARE_ANIMALS"
    PREDATORS = "PREDATORS"


class VisualPreference(str, Enum):
    ECONOMY = "ECONOMY"
    BALANCED = "BALANCED"
    MAX_AI = "MAX_AI"


class TopicSuggestionRequest(BaseModel):
    category: TopicCategory
    count: int = Field(default=3, ge=1, le=6)
    duration_seconds: int = Field(default=300, ge=120, le=900)
    visual_preference: VisualPreference = VisualPreference.BALANCED


class TopicSurpriseRequest(BaseModel):
    category: TopicCategory | None = None
    duration_seconds: int = Field(default=300, ge=120, le=900)
    visual_preference: VisualPreference = VisualPreference.BALANCED


class TopicSuggestion(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    scientific_name: str | None = Field(default=None, max_length=200)
    category: TopicCategory
    hook: str = Field(min_length=10, max_length=500)
    stock_availability: str = Field(pattern="^(HIGH|MEDIUM|LOW)$")
    stock_score: int = Field(ge=0, le=100)
    production_difficulty: str = Field(pattern="^(EASY|MEDIUM|HARD)$")
    difficulty_reasons: list[str] = Field(min_length=1, max_length=5)
    recommended_visual_mix: dict[str, int]
    recently_used: bool = False


class TopicSuggestionBundle(BaseModel):
    provider: str
    is_mock: bool
    suggestions: list[TopicSuggestion]
    excluded_recent_topics: list[str]
    warning: str | None = None
