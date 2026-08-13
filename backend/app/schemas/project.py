from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.project import ProjectPhase, ProjectStatus


class ProjectBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    animal_topic: str | None = Field(default=None, max_length=200)
    auto_topic: bool = False
    language: str = Field(min_length=1, max_length=50)
    requested_duration_seconds: int = Field(ge=120, le=900)
    output_resolution: str = Field(default="1920x1080", pattern=r"^\d{3,5}x\d{3,5}$")
    documentary_tone: str = Field(
        default="cinematic wildlife documentary", min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def validate_topic(self) -> "ProjectBase":
        if not self.auto_topic and not (self.animal_topic and self.animal_topic.strip()):
            raise ValueError("animal_topic is required unless auto_topic is enabled")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    animal_topic: str | None = Field(default=None, max_length=200)
    auto_topic: bool | None = None
    language: str | None = Field(default=None, min_length=1, max_length=50)
    requested_duration_seconds: int | None = Field(default=None, ge=120, le=900)
    output_resolution: str | None = Field(default=None, pattern=r"^\d{3,5}x\d{3,5}$")
    documentary_tone: str | None = Field(default=None, min_length=1, max_length=100)


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ProjectStatus
    current_phase: ProjectPhase
    created_at: datetime
    updated_at: datetime
