from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetType
from app.models.scene import Scene, ScenePrompt
from app.schemas.image_generation import (
    GenerationJobRead,
    ImageGenerateRequest,
    ImageGenerationBundle,
    ImagePromptCreate,
)
from app.schemas.scene import ScenePromptRead
from app.services.image_generation import (
    create_prompt_version,
    run_image_job,
    submit_image_job,
)
from app.services.worker_queue import (
    cancel_worker_job,
    enqueue_generation_job,
    worker_mode_enabled,
)

router = APIRouter(tags=["images"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def scene_or_404(scene_id: int, db: Session) -> Scene:
    scene = db.scalar(
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.project), selectinload(Scene.prompts))
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


def image_bundle(scene: Scene, db: Session) -> ImageGenerationBundle:
    assets = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scene_id == scene.id, MediaAsset.type == MediaAssetType.AI_IMAGE)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
        )
    )
    jobs = list(
        db.scalars(
            select(GenerationJob)
            .where(GenerationJob.scene_id == scene.id, GenerationJob.job_type == "AI_IMAGE")
            .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        )
    )
    provider = get_settings().image_generation_provider
    return ImageGenerationBundle(
        scene_id=scene.id,
        provider=provider,
        is_mock=provider.lower() == "mock",
        selected_asset_id=scene.preferred_media_asset_id,
        prompts=[ScenePromptRead.model_validate(item) for item in reversed(scene.prompts)],
        jobs=jobs,
        assets=assets,
        warning=(
            "Mock images are local placeholders and are not AI-generated production artwork."
            if provider.lower() == "mock" and (assets or jobs)
            else None
        ),
    )


@router.get("/api/scenes/{scene_id}/images", response_model=ImageGenerationBundle)
def get_images(scene_id: int, db: DatabaseSession) -> ImageGenerationBundle:
    return image_bundle(scene_or_404(scene_id, db), db)


@router.post(
    "/api/scenes/{scene_id}/image-prompts/generate",
    response_model=ScenePromptRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_image_prompt(scene_id: int, db: DatabaseSession) -> ScenePrompt:
    return create_prompt_version(scene_or_404(scene_id, db), db)


@router.post(
    "/api/scenes/{scene_id}/image-prompts",
    response_model=ScenePromptRead,
    status_code=status.HTTP_201_CREATED,
)
def save_image_prompt(
    scene_id: int, payload: ImagePromptCreate, db: DatabaseSession
) -> ScenePrompt:
    return create_prompt_version(
        scene_or_404(scene_id, db), db, payload.image_prompt, payload.negative_prompt
    )


@router.post(
    "/api/scenes/{scene_id}/images/generate",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_image(
    scene_id: int,
    payload: ImageGenerateRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> GenerationJob:
    scene = scene_or_404(scene_id, db)
    prompt = (
        db.get(ScenePrompt, payload.prompt_id)
        if payload.prompt_id is not None
        else (scene.prompts[-1] if scene.prompts else None)
    )
    if prompt is None or prompt.scene_id != scene.id:
        raise HTTPException(status_code=422, detail="Select a prompt belonging to this scene")
    try:
        job = submit_image_job(
            scene,
            prompt,
            db,
            seed=payload.seed,
            reference_asset_ids=payload.reference_asset_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if worker_mode_enabled():
        enqueue_generation_job(job, db)
    else:
        background_tasks.add_task(run_image_job, job.id)
    return job


@router.post(
    "/api/image-jobs/{job_id}/retry",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_image_job(
    job_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> GenerationJob:
    old_job = db.get(GenerationJob, job_id)
    if old_job is None or old_job.job_type != "AI_IMAGE":
        raise HTTPException(status_code=404, detail="Image generation job not found")
    if old_job.status not in {"FAILED", "CANCELED"}:
        raise HTTPException(status_code=409, detail="Only failed or canceled jobs can be retried")
    scene = scene_or_404(old_job.scene_id or 0, db)
    prompt = db.get(ScenePrompt, old_job.prompt_id)
    if prompt is None:
        raise HTTPException(status_code=409, detail="The job prompt no longer exists")
    job = submit_image_job(
        scene,
        prompt,
        db,
        seed=old_job.seed,
        reference_asset_ids=list(old_job.request_json.get("reference_asset_ids", [])),
        retry_count=old_job.retry_count + 1,
    )
    if worker_mode_enabled():
        enqueue_generation_job(job, db)
    else:
        background_tasks.add_task(run_image_job, job.id)
    return job


@router.post("/api/image-jobs/{job_id}/cancel", response_model=GenerationJobRead)
def cancel_image_job(job_id: int, db: DatabaseSession) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None or job.job_type != "AI_IMAGE":
        raise HTTPException(status_code=404, detail="Image generation job not found")
    if job.status not in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail="Only pending or running jobs can be canceled")
    job.status = "CANCELED"
    cancel_worker_job(job.id, db)
    db.commit()
    db.refresh(job)
    return job
