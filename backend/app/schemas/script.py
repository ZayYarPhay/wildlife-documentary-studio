from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScriptSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    title: str
    text: str
    estimated_duration_seconds: float
    source_fact_ids: list[int]


class ScriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    tone: str
    full_text: str
    estimated_words: int
    estimated_duration_seconds: float
    length_status: str
    approved: bool
    created_at: datetime
    sections: list[ScriptSectionRead]


class ScriptBundle(BaseModel):
    project_id: int
    status: str
    provider: str
    is_mock: bool
    target_word_min: int
    target_word_max: int
    current: ScriptRead | None
    versions: list[ScriptRead]
    warning: str | None = None


class ScriptUpdate(BaseModel):
    full_text: str | None = Field(default=None, min_length=1)
    tone: str | None = Field(default=None, min_length=1, max_length=100)


class ScriptSectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1)


class SectionRegenerateRequest(BaseModel):
    mode: Literal["regenerate", "shorten", "expand"] = "regenerate"
