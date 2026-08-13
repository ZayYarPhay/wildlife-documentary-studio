import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.jobs import GenerationJob
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.research import ResearchFact
from app.models.scene import Scene, ScenePrompt, SceneStatus, VisualStrategy
from app.models.script import Script

SHOT_TYPES = [
    "establishing aerial",
    "wide",
    "medium",
    "close-up",
    "tracking",
    "eye level",
    "macro/detail",
    "static observation",
    "low angle",
]
CAMERA_MOTIONS = ["static observation", "slow push", "gentle pan", "follow shot", "locked-off"]
STRATEGIES = [
    VisualStrategy.STOCK_VIDEO,
    VisualStrategy.STOCK_VIDEO,
    VisualStrategy.AI_IMAGE_MOTION,
    VisualStrategy.AI_VIDEO,
    VisualStrategy.STOCK_VIDEO,
    VisualStrategy.AI_IMAGE_MOTION,
    VisualStrategy.STOCK_VIDEO,
    VisualStrategy.AI_VIDEO,
    VisualStrategy.AI_IMAGE_MOTION,
    VisualStrategy.AI_VIDEO,
]


def split_narration(text: str, words_per_minute: int, target_seconds: float = 7) -> list[str]:
    target_words = max(8, round(words_per_minute * target_seconds / 60))
    max_words = max(target_words + 4, round(words_per_minute * 10 / 60))
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.extend(
                " ".join(words[i : i + target_words]) for i in range(0, len(words), target_words)
            )
            continue
        if current and len(current) + len(words) > max_words:
            chunks.append(" ".join(current))
            current = []
        current.extend(words)
        if len(current) >= target_words:
            chunks.append(" ".join(current))
            current = []
    if current:
        if chunks and len(current) < max(4, target_words // 2):
            chunks[-1] = f"{chunks[-1]} {' '.join(current)}"
        else:
            chunks.append(" ".join(current))
    return chunks


def retime_scenes(scenes: list[Scene]) -> None:
    cursor = 0.0
    for index, scene in enumerate(sorted(scenes, key=lambda item: item.order), start=1):
        scene.order = index
        scene.start_time = round(cursor, 3)
        cursor += scene.target_duration
        scene.end_time = round(cursor, 3)


def prompt_values(scene: Scene) -> tuple[str, str, str]:
    image = (
        f"{scene.species}; {scene.animal_behavior}; {scene.environment}; "
        f"{scene.shot_type} wildlife documentary shot; {scene.visual_description}; natural anatomy"
    )
    negative = "text, watermark, logo, extra limbs, distorted anatomy, fantasy elements, collars"
    video = (
        f"Preserve the same {scene.species} and environment. {scene.camera_motion}. "
        "Natural restrained wildlife motion; no morphing, no new animals."
    )
    return image, negative, video


@dataclass
class ScenePlanResult:
    scenes: list[Scene]
    script_id: int


class ScenePlanner:
    def generate(self, project: Project, db: Session) -> ScenePlanResult:
        script = db.scalar(
            select(Script)
            .where(Script.project_id == project.id, Script.approved.is_(True))
            .order_by(Script.version.desc())
        )
        if script is None:
            raise ValueError("Approve a script version before generating scenes")

        job = GenerationJob(
            project_id=project.id,
            job_type="SCENE_PLAN",
            provider="deterministic-planner",
            status="RUNNING",
            progress=0.1,
        )
        project.status = ProjectStatus.SCENE_PLANNING
        project.current_phase = ProjectPhase.SCENES
        db.add(job)
        db.commit()

        try:
            scenes_data = self._plan(project, script, db)
            db.execute(delete(Scene).where(Scene.project_id == project.id))
            db.flush()
            scenes: list[Scene] = []
            for data in scenes_data:
                scene = Scene(project_id=project.id, script_id=script.id, **data)
                db.add(scene)
                db.flush()
                image, negative, video = prompt_values(scene)
                db.add(
                    ScenePrompt(
                        scene_id=scene.id,
                        image_prompt=image,
                        negative_prompt=negative,
                        video_prompt=video,
                        version=1,
                    )
                )
                scenes.append(scene)
            job.status = "COMPLETED"
            job.progress = 1
            project.status = ProjectStatus.SCENE_REVIEW
            project.current_phase = ProjectPhase.SCENE_REVIEW
            db.commit()
        except Exception as exc:
            db.rollback()
            persisted_job = db.get(GenerationJob, job.id)
            persisted_project = db.get(Project, project.id)
            if persisted_job:
                persisted_job.status = "FAILED"
                persisted_job.error_message = str(exc)
            if persisted_project:
                persisted_project.status = ProjectStatus.FAILED
                persisted_project.current_phase = ProjectPhase.SCENES
            db.commit()
            raise
        return ScenePlanResult(scenes=scenes, script_id=script.id)

    @staticmethod
    def _plan(project: Project, script: Script, db: Session) -> list[dict]:
        settings = get_settings()
        chunks = split_narration(script.full_text, settings.narration_words_per_minute)
        if not chunks:
            raise ValueError("Approved script contains no narration")
        facts = list(
            db.scalars(
                select(ResearchFact).where(
                    ResearchFact.project_id == project.id, ResearchFact.approved.is_(True)
                )
            )
        )
        habitat = next(
            (fact.claim for fact in facts if fact.category in {"habitat", "geographic range"}),
            "Environment to be verified from approved research",
        )
        behavior = next(
            (
                fact.claim
                for fact in facts
                if fact.category in {"daily behavior", "hunting/feeding", "social behavior"}
            ),
            "Behavior described by the approved narration",
        )
        species = project.animal_topic or "Selected wildlife subject"
        durations = [
            len(chunk.split()) / settings.narration_words_per_minute * 60 for chunk in chunks
        ]
        cursor = 0.0
        result = []
        for index, (chunk, duration) in enumerate(zip(chunks, durations, strict=True), start=1):
            start = cursor
            cursor += duration
            result.append(
                {
                    "order": index,
                    "narration_text": chunk,
                    "start_time": round(start, 3),
                    "end_time": round(cursor, 3),
                    "target_duration": round(duration, 3),
                    "species": species,
                    "environment": habitat[:500],
                    "animal_behavior": behavior[:300],
                    "visual_description": f"A factual visual accompaniment for: {chunk[:350]}",
                    "shot_type": SHOT_TYPES[(index - 1) % len(SHOT_TYPES)],
                    "camera_motion": CAMERA_MOTIONS[(index - 1) % len(CAMERA_MOTIONS)],
                    "visual_strategy": STRATEGIES[(index - 1) % len(STRATEGIES)],
                    "status": SceneStatus.READY,
                }
            )
        return result

    @staticmethod
    def regenerate_scene(scene: Scene, db: Session) -> Scene:
        scene.shot_type = (
            SHOT_TYPES[(SHOT_TYPES.index(scene.shot_type) + 1) % len(SHOT_TYPES)]
            if scene.shot_type in SHOT_TYPES
            else SHOT_TYPES[0]
        )
        scene.camera_motion = (
            CAMERA_MOTIONS[(CAMERA_MOTIONS.index(scene.camera_motion) + 1) % len(CAMERA_MOTIONS)]
            if scene.camera_motion in CAMERA_MOTIONS
            else CAMERA_MOTIONS[0]
        )
        scene.visual_strategy = STRATEGIES[
            (STRATEGIES.index(scene.visual_strategy) + 1) % len(STRATEGIES)
        ]
        scene.visual_description = f"Alternative visual treatment: {scene.narration_text[:350]}"
        image, negative, video = prompt_values(scene)
        version = max((prompt.version for prompt in scene.prompts), default=0) + 1
        db.add(
            ScenePrompt(
                scene_id=scene.id,
                image_prompt=image,
                negative_prompt=negative,
                video_prompt=video,
                version=version,
            )
        )
        db.commit()
        db.refresh(scene)
        return scene
