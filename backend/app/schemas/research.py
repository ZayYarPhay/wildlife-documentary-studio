from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ResearchSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: HttpUrl
    source_name: str
    retrieved_at: datetime
    metadata_json: dict[str, Any]


class ResearchFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: str
    claim: str
    confidence: float
    approved: bool
    notes: str | None
    source: ResearchSourceRead


class ResearchFactUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    claim: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    approved: bool | None = None
    notes: str | None = None


class ResearchBundle(BaseModel):
    project_id: int
    status: str
    provider: str
    is_mock: bool
    facts: list[ResearchFactRead]
    warning: str | None = None
