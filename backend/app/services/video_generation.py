import asyncio
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import ProjectPhase, ProjectStatus
from app.models.scene import Scene, ScenePrompt, VisualStrategy
from app.providers.base import VideoGenerationProvider
from app.providers.mock_video import MockVideoGenerationProvider


def build_video_prompt(scene: Scene) -> str:
    return " ".join(
        [
            f"A {scene.species} begins in the pose and composition shown in the reference image.",
            f"Desired action: {scene.animal_behavior}.",
            f"Habitat continuity: {scene.environment}; only subtle natural environmental movement.",
            f"Camera: {scene.camera_motion}, maintaining the {scene.shot_type} framing.",
            f"Duration: approximately {min(scene.target_duration, get_settings().video_generation_max_duration_seconds):g} seconds.",
            "Natural shoulder, limb, breathing, fur and weight-shift motion appropriate to the species.",
            "Photorealistic wildlife-documentary timing; restrained movement unless the described behavior requires speed.",
            (
                "Preserve anatomy, markings, identity, lighting and habitat; no morphing, warping, extra limbs, "
                "new animals, sudden cuts, text or watermark."
            ),
        ]
    )


def get_video_provider() -> VideoGenerationProvider:
    name = get_settings().video_generation_provider.lower()
    if name == "mock":
        return MockVideoGenerationProvider()
    raise ValueError(f"Unsupported video generation provider: {name}")


def create_video_prompt_version(
    scene: Scene, db: Session, video_prompt: str | None = None
) -> ScenePrompt:
    latest = db.scalar(
        select(ScenePrompt)
        .where(ScenePrompt.scene_id == scene.id)
        .order_by(ScenePrompt.version.desc())
    )
    version = (
        db.scalar(select(func.max(ScenePrompt.version)).where(ScenePrompt.scene_id == scene.id))
        or 0
    ) + 1
    prompt = ScenePrompt(
        scene_id=scene.id,
        image_prompt=latest.image_prompt if latest else "",
        negative_prompt=latest.negative_prompt if latest else "",
        video_prompt=(video_prompt or build_video_prompt(scene)).strip(),
        version=version,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def submit_video_job(
    scene: Scene,
    prompt: ScenePrompt,
    source_asset: MediaAsset,
    db: Session,
    *,
    duration: float | None = None,
    fps: int | None = None,
    retry_count: int = 0,
) -> GenerationJob:
    if scene.visual_strategy != VisualStrategy.AI_VIDEO:
        raise ValueError("AI video generation requires the AI_VIDEO scene strategy")
    if source_asset.scene_id != scene.id or source_asset.type != MediaAssetType.AI_IMAGE:
        raise ValueError("Source must be an AI image belonging to this scene")
    preferred = (
        db.get(MediaAsset, scene.preferred_media_asset_id)
        if scene.preferred_media_asset_id is not None
        else None
    )
    source_is_approved = scene.preferred_media_asset_id == source_asset.id or (
        preferred is not None
        and preferred.type == MediaAssetType.AI_VIDEO
        and preferred.metadata_json.get("source_asset_id") == source_asset.id
    )
    if not source_is_approved and retry_count == 0:
        raise ValueError("Approve/select the source AI image before generating video")
    if not source_asset.local_path or not Path(source_asset.local_path).is_file():
        raise ValueError("The selected source image file is unavailable")
    settings = get_settings()
    source_path = Path(source_asset.local_path).resolve()
    media_root = Path(settings.media_root).resolve()
    if not source_path.is_relative_to(media_root) or source_path.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }:
        raise ValueError("Source image must be a supported file inside managed media storage")
    requested_duration = min(
        duration or scene.target_duration, settings.video_generation_max_duration_seconds
    )
    requested_fps = fps or settings.video_generation_fps
    provider = get_video_provider()
    job = GenerationJob(
        project_id=scene.project_id,
        scene_id=scene.id,
        job_type="AI_VIDEO",
        provider=getattr(provider, "name", provider.__class__.__name__),
        status="PENDING",
        progress=0,
        retry_count=retry_count,
        prompt_id=prompt.id,
        request_json={
            "source_asset_id": source_asset.id,
            "duration": requested_duration,
            "fps": requested_fps,
            "resolution": scene.project.output_resolution,
            "provider_options": {},
            "fallback_recommendations": [],
        },
    )
    scene.project.status = ProjectStatus.VIDEO_GENERATING
    scene.project.current_phase = ProjectPhase.VIDEOS
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def run_video_job(job_id: int, provider: VideoGenerationProvider | None = None) -> None:
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
        source_asset = db.get(MediaAsset, job.request_json.get("source_asset_id"))
        if prompt is None or scene is None or source_asset is None:
            raise RuntimeError("Video job references a missing scene, prompt or source image")
        width, height = _target_dimensions(job.request_json["resolution"])
        settings = get_settings()
        output_dir = Path(settings.media_root) / str(scene.project_id) / "videos" / str(scene.id)
        active_provider = provider or get_video_provider()
        result = await asyncio.wait_for(
            active_provider.generate(
                source_asset.local_path,
                prompt.video_prompt,
                duration=job.request_json["duration"],
                fps=job.request_json["fps"],
                width=width,
                height=height,
                output_dir=str(output_dir),
                job_id=job.id,
                provider_options=job.request_json.get("provider_options", {}),
            ),
            timeout=settings.video_generation_timeout_seconds,
        )
        validation = validate_video_output(
            result["local_path"],
            output_dir,
            expected_duration=float(job.request_json["duration"]),
        )
        db.refresh(job)
        if job.status == "CANCELED":
            return
        filename = result["filename"]
        relative_url = f"{scene.project_id}/videos/{scene.id}/{filename}"
        public_url = f"{settings.public_media_base_url.rstrip('/')}/{relative_url}"
        metadata = dict(result.get("metadata_json") or {})
        metadata.update(
            {
                "prompt_id": prompt.id,
                "prompt_version": prompt.version,
                "source_asset_id": source_asset.id,
                "fps": result.get("fps", job.request_json["fps"]),
                "validation": validation,
            }
        )
        asset = MediaAsset(
            project_id=scene.project_id,
            scene_id=scene.id,
            provider=getattr(active_provider, "name", active_provider.__class__.__name__),
            provider_asset_id=str(result["provider_asset_id"]),
            type=MediaAssetType.AI_VIDEO,
            preview_url=public_url,
            download_url=public_url,
            source_page_url=None,
            creator=None,
            license=None,
            attribution_requirements=None,
            width=validation["width"],
            height=validation["height"],
            duration=validation["duration"],
            local_path=result["local_path"],
            metadata_json=metadata,
            relevance_score=1,
            status=MediaAssetStatus.CANDIDATE,
        )
        db.add(asset)
        db.flush()
        job.output_asset_id = asset.id
        job.status = "COMPLETED"
        job.progress = 1
        job.completed_at = datetime.now(UTC)
        scene.project.status = ProjectStatus.VIDEO_REVIEW
        scene.project.current_phase = ProjectPhase.VIDEO_REVIEW
        db.commit()
    except Exception as exc:  # noqa: BLE001 - diagnostics must survive provider/validation failures
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None and job.status != "CANCELED":
            job.status = "FAILED"
            job.error_message = str(exc)
            job.completed_at = datetime.now(UTC)
            request = dict(job.request_json)
            if job.retry_count >= get_settings().video_generation_max_retries:
                request["fallback_recommendations"] = ["AI_IMAGE_MOTION", "STOCK_VIDEO"]
            job.request_json = request
            scene = db.scalar(
                select(Scene).where(Scene.id == job.scene_id).options(selectinload(Scene.project))
            )
            if scene is not None:
                scene.project.status = ProjectStatus.VIDEO_REVIEW
                scene.project.current_phase = ProjectPhase.VIDEO_REVIEW
            db.commit()
    finally:
        db.close()


def validate_video_output(
    local_path: str, output_dir: Path, *, expected_duration: float
) -> dict[str, Any]:
    path = Path(local_path).resolve(strict=True)
    safe_root = output_dir.resolve(strict=True)
    if not path.is_relative_to(safe_root) or path.suffix.lower() != ".mp4":
        raise RuntimeError("Provider output is outside the job directory or is not MP4")
    if path.stat().st_size < 1024:
        raise RuntimeError("Generated video is empty or too small")
    ffprobe = shutil.which(get_settings().ffprobe_path)
    if ffprobe is None:
        raise RuntimeError("FFprobe is required to validate generated video")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Generated video failed FFprobe validation")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    if not streams or streams[0].get("codec_type") != "video":
        raise RuntimeError("Generated output has no video stream")
    duration = float(payload.get("format", {}).get("duration", 0))
    if duration <= 0 or abs(duration - expected_duration) > max(1, expected_duration * 0.2):
        raise RuntimeError("Generated video duration is outside tolerance")
    return {
        "width": int(streams[0]["width"]),
        "height": int(streams[0]["height"]),
        "duration": round(duration, 3),
        "frame_rate": streams[0].get("avg_frame_rate"),
        "size_bytes": path.stat().st_size,
    }


def _target_dimensions(resolution: str) -> tuple[int, int]:
    try:
        width, height = (int(value) for value in resolution.lower().split("x", maxsplit=1))
    except (TypeError, ValueError):
        return 1920, 1080
    if width <= 0 or height <= 0:
        return 1920, 1080
    return width - (width % 2), height - (height % 2)
