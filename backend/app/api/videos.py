from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetType
from app.models.scene import Scene, ScenePrompt, VisualStrategy
from app.schemas.image_generation import GenerationJobRead
from app.schemas.scene import ScenePromptRead
from app.schemas.video_generation import (
    VideoGenerateRequest,
    VideoGenerationBundle,
    VideoPromptCreate,
)
from app.services.video_generation import (
    create_video_prompt_version,
    run_video_job,
    submit_video_job,
)

router = APIRouter(tags=["videos"])
DatabaseSession = Annotated[Session, Depends(get_db)]


class VideoFallbackRequest(BaseModel):
    strategy: Literal["AI_IMAGE_MOTION", "STOCK_VIDEO"]


def scene_or_404(scene_id: int, db: Session) -> Scene:
    scene = db.scalar(
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.project), selectinload(Scene.prompts))
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


def video_bundle(scene: Scene, db: Session) -> VideoGenerationBundle:
    assets = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scene_id == scene.id, MediaAsset.type == MediaAssetType.AI_VIDEO)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
        )
    )
    jobs = list(
        db.scalars(
            select(GenerationJob)
            .where(GenerationJob.scene_id == scene.id, GenerationJob.job_type == "AI_VIDEO")
            .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        )
    )
    preferred = (
        db.get(MediaAsset, scene.preferred_media_asset_id)
        if scene.preferred_media_asset_id is not None
        else None
    )
    selected_image_id = (
        preferred.id
        if preferred is not None and preferred.type == MediaAssetType.AI_IMAGE
        else None
    )
    if selected_image_id is None and jobs:
        selected_image_id = jobs[0].request_json.get("source_asset_id")
    fallbacks = list(jobs[0].request_json.get("fallback_recommendations", [])) if jobs else []
    provider = get_settings().video_generation_provider
    return VideoGenerationBundle(
        scene_id=scene.id,
        provider=provider,
        is_mock=provider.lower() == "mock",
        selected_asset_id=(
            scene.preferred_media_asset_id
            if preferred is not None and preferred.type == MediaAssetType.AI_VIDEO
            else None
        ),
        selected_image_asset_id=selected_image_id,
        prompts=[ScenePromptRead.model_validate(item) for item in reversed(scene.prompts)],
        jobs=jobs,
        assets=assets,
        fallback_recommendations=fallbacks,
        warning=(
            "Mock videos are local image holds for lifecycle testing, not AI-generated motion."
            if provider.lower() == "mock" and (assets or jobs)
            else None
        ),
    )


@router.get("/api/scenes/{scene_id}/videos", response_model=VideoGenerationBundle)
def get_videos(scene_id: int, db: DatabaseSession) -> VideoGenerationBundle:
    return video_bundle(scene_or_404(scene_id, db), db)


@router.post(
    "/api/scenes/{scene_id}/video-prompts/generate",
    response_model=ScenePromptRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_video_prompt(scene_id: int, db: DatabaseSession) -> ScenePrompt:
    return create_video_prompt_version(scene_or_404(scene_id, db), db)


@router.post(
    "/api/scenes/{scene_id}/video-prompts",
    response_model=ScenePromptRead,
    status_code=status.HTTP_201_CREATED,
)
def save_video_prompt(
    scene_id: int, payload: VideoPromptCreate, db: DatabaseSession
) -> ScenePrompt:
    return create_video_prompt_version(scene_or_404(scene_id, db), db, payload.video_prompt)


@router.post(
    "/api/scenes/{scene_id}/videos/generate",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_video(
    scene_id: int,
    payload: VideoGenerateRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
) -> GenerationJob:
    scene = scene_or_404(scene_id, db)
    prompt = db.get(ScenePrompt, payload.prompt_id)
    source = db.get(MediaAsset, payload.source_asset_id)
    if prompt is None or prompt.scene_id != scene.id:
        raise HTTPException(status_code=422, detail="Select a video prompt belonging to this scene")
    if source is None:
        raise HTTPException(status_code=422, detail="Source image not found")
    try:
        job = submit_video_job(
            scene, prompt, source, db, duration=payload.duration, fps=payload.fps
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(run_video_job, job.id)
    return job


@router.post(
    "/api/video-jobs/{job_id}/retry",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_video_job(
    job_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> GenerationJob:
    old = db.get(GenerationJob, job_id)
    if old is None or old.job_type != "AI_VIDEO":
        raise HTTPException(status_code=404, detail="Video generation job not found")
    if old.status not in {"FAILED", "CANCELED"}:
        raise HTTPException(status_code=409, detail="Only failed or canceled jobs can be retried")
    if old.retry_count >= get_settings().video_generation_max_retries:
        raise HTTPException(status_code=409, detail="Retry limit reached; choose a fallback")
    scene = scene_or_404(old.scene_id or 0, db)
    prompt = db.get(ScenePrompt, old.prompt_id)
    source = db.get(MediaAsset, old.request_json.get("source_asset_id"))
    if prompt is None or source is None:
        raise HTTPException(status_code=409, detail="The prompt or source image no longer exists")
    job = submit_video_job(
        scene,
        prompt,
        source,
        db,
        duration=old.request_json.get("duration"),
        fps=old.request_json.get("fps"),
        retry_count=old.retry_count + 1,
    )
    background_tasks.add_task(run_video_job, job.id)
    return job


@router.post("/api/scenes/{scene_id}/video-fallback", response_model=VideoGenerationBundle)
def choose_video_fallback(
    scene_id: int, payload: VideoFallbackRequest, db: DatabaseSession
) -> VideoGenerationBundle:
    scene = scene_or_404(scene_id, db)
    latest = db.scalar(
        select(GenerationJob)
        .where(GenerationJob.scene_id == scene.id, GenerationJob.job_type == "AI_VIDEO")
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
    )
    recommendations = latest.request_json.get("fallback_recommendations", []) if latest else []
    if payload.strategy not in recommendations:
        raise HTTPException(status_code=409, detail="Fallback is not available for this scene yet")
    scene.visual_strategy = VisualStrategy(payload.strategy)
    db.commit()
    return video_bundle(scene_or_404(scene.id, db), db)
