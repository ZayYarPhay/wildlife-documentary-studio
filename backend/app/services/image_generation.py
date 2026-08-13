import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import ProjectPhase, ProjectStatus
from app.models.scene import Scene, ScenePrompt, VisualStrategy
from app.providers.base import ImageGenerationProvider
from app.providers.mock_image import MockImageGenerationProvider

DEFAULT_NEGATIVE_PROMPT = (
    "deformed anatomy, extra limbs, duplicate animals, incorrect fur or markings, "
    "fantasy features, text, watermark, logo, human clothing, collars, impossible habitat"
)


def build_image_prompt(scene: Scene) -> tuple[str, str]:
    """Build a provider-neutral, structured wildlife documentary prompt."""
    prompt = "\n".join(
        [
            f"Subject/species: {scene.species}.",
            "Animal count: one primary animal unless the scene description explicitly requires more.",
            f"Behavior: {scene.animal_behavior}.",
            f"Habitat: {scene.environment}.",
            "Time and weather: natural conditions consistent with the described habitat; do not invent extremes.",
            f"Framing and lens: {scene.shot_type}; production-ready 16:9 composition.",
            f"Scene direction: {scene.visual_description}.",
            (
                "Style: photorealistic wildlife-documentary realism, physically accurate anatomy, "
                "natural available lighting and restrained cinematic color."
            ),
            (
                "Visual continuity: preserve species-specific proportions, coat, markings, habitat, "
                "screen direction, and the same identifiable animal across related shots."
            ),
        ]
    )
    return prompt, DEFAULT_NEGATIVE_PROMPT


def get_image_provider() -> ImageGenerationProvider:
    name = get_settings().image_generation_provider.lower()
    if name == "mock":
        return MockImageGenerationProvider()
    raise ValueError(f"Unsupported image generation provider: {name}")


def create_prompt_version(
    scene: Scene, db: Session, image_prompt: str | None = None, negative_prompt: str | None = None
) -> ScenePrompt:
    generated_image, generated_negative = build_image_prompt(scene)
    latest_version = (
        db.scalar(select(func.max(ScenePrompt.version)).where(ScenePrompt.scene_id == scene.id))
        or 0
    )
    prompt = ScenePrompt(
        scene_id=scene.id,
        image_prompt=(image_prompt or generated_image).strip(),
        negative_prompt=(negative_prompt or generated_negative).strip(),
        video_prompt="",
        version=latest_version + 1,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def submit_image_job(
    scene: Scene,
    prompt: ScenePrompt,
    db: Session,
    *,
    seed: int | None = None,
    reference_asset_ids: list[int] | None = None,
    retry_count: int = 0,
) -> GenerationJob:
    if scene.visual_strategy not in {VisualStrategy.AI_IMAGE_MOTION, VisualStrategy.AI_VIDEO}:
        raise ValueError("AI image generation requires AI_IMAGE_MOTION or AI_VIDEO strategy")
    references = reference_asset_ids or []
    if references:
        valid_ids = set(
            db.scalars(
                select(MediaAsset.id).where(
                    MediaAsset.scene_id == scene.id, MediaAsset.id.in_(references)
                )
            )
        )
        if valid_ids != set(references):
            raise ValueError("Reference assets must belong to this scene")
    provider = get_image_provider()
    job = GenerationJob(
        project_id=scene.project_id,
        scene_id=scene.id,
        job_type="AI_IMAGE",
        provider=getattr(provider, "name", provider.__class__.__name__),
        status="PENDING",
        progress=0,
        retry_count=retry_count,
        prompt_id=prompt.id,
        seed=seed,
        request_json={"reference_asset_ids": references},
    )
    scene.project.status = ProjectStatus.IMAGE_GENERATING
    scene.project.current_phase = ProjectPhase.IMAGES
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def run_image_job(job_id: int, provider: ImageGenerationProvider | None = None) -> None:
    """Run outside the request transaction using a fresh database session."""
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None or job.status == "CANCELED":
            return
        job.status = "RUNNING"
        job.progress = 0.1
        db.commit()

        prompt = db.get(ScenePrompt, job.prompt_id)
        scene = db.scalar(
            select(Scene).where(Scene.id == job.scene_id).options(selectinload(Scene.project))
        )
        if prompt is None or scene is None:
            raise RuntimeError("Generation job references a missing scene or prompt")
        settings = get_settings()
        width, height = _target_dimensions(scene.project.output_resolution)
        output_dir = Path(settings.media_root) / str(scene.project_id) / "images" / str(scene.id)
        active_provider = provider or get_image_provider()
        result = await asyncio.wait_for(
            active_provider.generate(
                prompt.image_prompt,
                negative_prompt=prompt.negative_prompt,
                width=width,
                height=height,
                seed=job.seed,
                output_dir=str(output_dir),
                job_id=job.id,
                reference_asset_ids=job.request_json.get("reference_asset_ids", []),
            ),
            timeout=settings.image_generation_timeout_seconds,
        )
        db.refresh(job)
        if job.status == "CANCELED":
            return
        filename = result["filename"]
        thumbnail_filename = result.get("thumbnail_filename", filename)
        relative_url = f"{scene.project_id}/images/{scene.id}/{filename}"
        preview_relative_url = f"{scene.project_id}/images/{scene.id}/{thumbnail_filename}"
        public_url = f"{settings.public_media_base_url.rstrip('/')}/{relative_url}"
        preview_url = f"{settings.public_media_base_url.rstrip('/')}/{preview_relative_url}"
        metadata = dict(result.get("metadata_json") or {})
        metadata.update(
            {
                "prompt_id": prompt.id,
                "prompt_version": prompt.version,
                "seed": result.get("seed"),
                "negative_prompt": prompt.negative_prompt,
            }
        )
        asset = MediaAsset(
            project_id=scene.project_id,
            scene_id=scene.id,
            provider=getattr(active_provider, "name", active_provider.__class__.__name__),
            provider_asset_id=str(result["provider_asset_id"]),
            type=MediaAssetType.AI_IMAGE,
            preview_url=preview_url,
            download_url=public_url,
            source_page_url=None,
            creator=None,
            license=None,
            attribution_requirements=None,
            width=result.get("width"),
            height=result.get("height"),
            duration=None,
            local_path=result["local_path"],
            metadata_json=metadata,
            relevance_score=1,
            status=MediaAssetStatus.CANDIDATE,
        )
        db.add(asset)
        db.flush()
        job.output_asset_id = asset.id
        job.seed = result.get("seed")
        job.status = "COMPLETED"
        job.progress = 1
        job.completed_at = datetime.now(UTC)
        scene.project.status = ProjectStatus.IMAGE_REVIEW
        scene.project.current_phase = ProjectPhase.IMAGE_REVIEW
        db.commit()
    except Exception as exc:  # noqa: BLE001 - provider errors become durable job diagnostics
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None and job.status != "CANCELED":
            job.status = "FAILED"
            job.error_message = str(exc)
            job.completed_at = datetime.now(UTC)
            if job.scene_id:
                scene = db.scalar(
                    select(Scene)
                    .where(Scene.id == job.scene_id)
                    .options(selectinload(Scene.project))
                )
                if scene is not None:
                    scene.project.status = ProjectStatus.IMAGE_REVIEW
                    scene.project.current_phase = ProjectPhase.IMAGE_REVIEW
            db.commit()
    finally:
        db.close()


def _target_dimensions(resolution: str) -> tuple[int, int]:
    try:
        width, height = (int(value) for value in resolution.lower().split("x", maxsplit=1))
    except (TypeError, ValueError):
        return 1920, 1080
    if width <= 0 or height <= 0:
        return 1920, 1080
    return width, height
