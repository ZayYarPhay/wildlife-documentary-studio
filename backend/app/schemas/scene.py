from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.scene import SceneStatus, VisualStrategy


class ScenePromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_prompt: str
    negative_prompt: str
    video_prompt: str
    version: int


class SceneBase(BaseModel):
    narration_text: str = Field(min_length=1)
    target_duration: float = Field(ge=1, le=120)
    species: str = Field(min_length=1, max_length=200)
    environment: str = Field(min_length=1, max_length=500)
    animal_behavior: str = Field(min_length=1, max_length=300)
    visual_description: str = Field(min_length=1)
    shot_type: str = Field(min_length=1, max_length=100)
    camera_motion: str = Field(min_length=1, max_length=100)
    visual_strategy: VisualStrategy


class SceneCreate(SceneBase):
    order: int | None = Field(default=None, ge=1)


class SceneUpdate(BaseModel):
    narration_text: str | None = Field(default=None, min_length=1)
    target_duration: float | None = Field(default=None, ge=1, le=120)
    species: str | None = Field(default=None, min_length=1, max_length=200)
    environment: str | None = Field(default=None, min_length=1, max_length=500)
    animal_behavior: str | None = Field(default=None, min_length=1, max_length=300)
    visual_description: str | None = Field(default=None, min_length=1)
    shot_type: str | None = Field(default=None, min_length=1, max_length=100)
    camera_motion: str | None = Field(default=None, min_length=1, max_length=100)
    visual_strategy: VisualStrategy | None = None
    status: SceneStatus | None = None


class SceneRead(SceneBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    script_id: int
    order: int
    start_time: float
    end_time: float
    status: SceneStatus
    prompts: list[ScenePromptRead]


class SceneBundle(BaseModel):
    project_id: int
    status: str
    total_duration: float
    target_duration: float
    duration_difference: float
    scenes: list[SceneRead]


class SceneReorder(BaseModel):
    scene_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "SceneReorder":
        if len(self.scene_ids) != len(set(self.scene_ids)):
            raise ValueError("scene_ids must be unique")
        return self
