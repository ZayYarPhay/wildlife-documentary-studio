import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image
from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import ProjectPhase, ProjectStatus
from app.models.scene import Scene, ScenePrompt
from app.models.worker import WorkerJob, WorkerJobStatus
from app.schemas.worker import (
    ImageWorkerParameters,
    ImageWorkerPayload,
    VideoWorkerParameters,
    VideoWorkerPayload,
    WorkerAssetReference,
    WorkerCallbackMetadata,
    WorkerClaim,
    WorkerPayload,
    WorkerQueueHealth,
)
from app.services.video_generation import validate_video_output

ALLOWED_JOB_TYPES = {"AI_IMAGE", "AI_VIDEO"}
IMAGE_MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def worker_mode_enabled() -> bool:
    mode = get_settings().generation_execution_mode.lower()
    if mode not in {"local", "worker"}:
        raise ValueError("GENERATION_EXECUTION_MODE must be local or worker")
    return mode == "worker"


def enqueue_generation_job(job: GenerationJob, db: Session) -> WorkerJob:
    if job.job_type not in ALLOWED_JOB_TYPES:
        raise ValueError("Only AI_IMAGE and AI_VIDEO jobs may be sent to workers")
    existing = db.scalar(select(WorkerJob).where(WorkerJob.generation_job_id == job.id))
    if existing is not None:
        return existing
    scene = db.scalar(
        select(Scene).where(Scene.id == job.scene_id).options(selectinload(Scene.project))
    )
    prompt = db.get(ScenePrompt, job.prompt_id)
    if scene is None or prompt is None or scene.project_id != job.project_id:
        raise ValueError("Generation job references an invalid scene or prompt")
    width, height = _dimensions(scene.project.output_resolution)
    if job.job_type == "AI_IMAGE":
        input_ids = list(job.request_json.get("reference_asset_ids", []))
        _validate_input_assets(scene.id, input_ids, db)
        parameters = ImageWorkerParameters(width=width, height=height, seed=job.seed)
    else:
        source_id = int(job.request_json.get("source_asset_id", 0))
        input_ids = [source_id]
        _validate_input_assets(scene.id, input_ids, db)
        parameters = VideoWorkerParameters(
            width=width,
            height=height,
            duration=float(job.request_json["duration"]),
            fps=int(job.request_json["fps"]),
        )
    worker_job = WorkerJob(
        generation_job_id=job.id,
        project_id=job.project_id,
        scene_id=scene.id,
        job_type=job.job_type,
        status=WorkerJobStatus.QUEUED,
        payload_json={},
        result_json={},
    )
    db.add(worker_job)
    db.flush()
    callback_metadata = WorkerCallbackMetadata(
        progress_path=f"/api/worker/jobs/{worker_job.id}/progress",
        complete_path=f"/api/worker/jobs/{worker_job.id}/complete",
        fail_path=f"/api/worker/jobs/{worker_job.id}/fail",
    )
    if job.job_type == "AI_IMAGE":
        payload: WorkerPayload = ImageWorkerPayload(
            job_id=job.id,
            project_id=job.project_id,
            scene_id=scene.id,
            job_type="AI_IMAGE",
            provider=job.provider,
            prompt=prompt.image_prompt,
            negative_prompt=prompt.negative_prompt,
            input_asset_ids=input_ids,
            parameters=parameters,
            callback_metadata=callback_metadata,
        )
    else:
        payload = VideoWorkerPayload(
            job_id=job.id,
            project_id=job.project_id,
            scene_id=scene.id,
            job_type="AI_VIDEO",
            provider=job.provider,
            prompt=prompt.video_prompt,
            input_asset_ids=input_ids,
            parameters=parameters,
            callback_metadata=callback_metadata,
        )
    worker_job.payload_json = payload.model_dump(mode="json")
    job.status = "PENDING"
    job.progress = 0
    db.commit()
    db.refresh(worker_job)
    return worker_job


def claim_next_job(worker_id: str, accepted: list[str], db: Session) -> WorkerClaim | None:
    invalid = set(accepted) - ALLOWED_JOB_TYPES
    if invalid:
        raise ValueError("Worker requested an unsupported job type")
    now = datetime.now(UTC)
    db.execute(
        update(WorkerJob)
        .where(
            WorkerJob.status.in_([WorkerJobStatus.CLAIMED, WorkerJobStatus.RUNNING]),
            WorkerJob.lease_expires_at < now,
        )
        .values(
            status=WorkerJobStatus.QUEUED,
            claimed_by=None,
            lease_expires_at=None,
            error_message="Previous worker lease expired; job requeued",
        )
    )
    db.commit()
    candidate_ids = list(
        db.scalars(
            select(WorkerJob.id)
            .where(WorkerJob.status == WorkerJobStatus.QUEUED, WorkerJob.job_type.in_(accepted))
            .order_by(WorkerJob.created_at, WorkerJob.id)
            .limit(10)
        )
    )
    claimed = None
    lease = now + timedelta(seconds=get_settings().worker_lease_seconds)
    for job_id in candidate_ids:
        changed = db.execute(
            update(WorkerJob)
            .where(WorkerJob.id == job_id, WorkerJob.status == WorkerJobStatus.QUEUED)
            .values(
                status=WorkerJobStatus.CLAIMED,
                claimed_by=worker_id,
                lease_expires_at=lease,
                attempts=WorkerJob.attempts + 1,
                progress=0,
                error_message=None,
            )
        )
        if changed.rowcount:
            db.commit()
            claimed = db.get(WorkerJob, job_id)
            break
        db.rollback()
    if claimed is None:
        return None
    generation_job = db.get(GenerationJob, claimed.generation_job_id)
    if generation_job:
        generation_job.status = "RUNNING"
        generation_job.progress = 0.01
        db.commit()
    payload = TypeAdapter(WorkerPayload).validate_python(claimed.payload_json)
    references = [
        WorkerAssetReference(
            asset_id=asset_id,
            download_url=f"/api/worker/assets/{asset_id}?worker_id={worker_id}",
            media_type=_asset_media_type(db.get(MediaAsset, asset_id)),
        )
        for asset_id in payload.input_asset_ids
    ]
    return WorkerClaim(job=claimed, payload=payload, input_assets=references)


def update_worker_progress(
    worker_job: WorkerJob, worker_id: str, progress: float, db: Session
) -> WorkerJob:
    _validate_claim(worker_job, worker_id)
    worker_job.status = WorkerJobStatus.RUNNING
    worker_job.progress = progress
    worker_job.lease_expires_at = datetime.now(UTC) + timedelta(
        seconds=get_settings().worker_lease_seconds
    )
    generation_job = db.get(GenerationJob, worker_job.generation_job_id)
    if generation_job:
        generation_job.status = "RUNNING"
        generation_job.progress = progress
    db.commit()
    db.refresh(worker_job)
    return worker_job


async def complete_worker_job(
    worker_job: WorkerJob,
    worker_id: str,
    upload: UploadFile,
    result_json: str,
    db: Session,
) -> WorkerJob:
    if worker_job.status == WorkerJobStatus.COMPLETED:
        return worker_job
    _validate_claim(worker_job, worker_id)
    generation_job = db.get(GenerationJob, worker_job.generation_job_id)
    scene = db.scalar(
        select(Scene).where(Scene.id == worker_job.scene_id).options(selectinload(Scene.project))
    )
    if generation_job is None or scene is None:
        raise ValueError("Worker job references missing generation state")
    try:
        metadata = json.loads(result_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("result_json must be valid JSON") from exc
    if not isinstance(metadata, dict):
        raise TypeError("result_json must be an object")
    settings = get_settings()
    if worker_job.job_type == "AI_IMAGE":
        suffix = IMAGE_MIME_SUFFIXES.get((upload.content_type or "").lower())
        if suffix is None:
            raise ValueError("Image worker results must be PNG, JPEG or WebP")
        output_dir = Path(settings.media_root) / str(scene.project_id) / "images" / str(scene.id)
        path = output_dir / f"worker-{uuid4().hex}{suffix}"
        await _save_upload(upload, path, settings.worker_result_max_bytes)
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            expected = worker_job.payload_json["parameters"]
            if width != expected["width"] or height != expected["height"]:
                raise ValueError("Worker image dimensions do not match the requested output")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        relative = f"{scene.project_id}/images/{scene.id}/{path.name}"
        public_url = f"{settings.public_media_base_url.rstrip('/')}/{relative}"
        asset = MediaAsset(
            project_id=scene.project_id,
            scene_id=scene.id,
            provider=f"worker:{generation_job.provider}",
            provider_asset_id=f"worker-job-{worker_job.id}",
            type=MediaAssetType.AI_IMAGE,
            preview_url=public_url,
            download_url=public_url,
            source_page_url=None,
            width=width,
            height=height,
            duration=None,
            local_path=str(path.resolve()),
            metadata_json={"worker_job_id": worker_job.id, **_safe_result_metadata(metadata)},
            relevance_score=1,
            status=MediaAssetStatus.CANDIDATE,
        )
        scene.project.status = ProjectStatus.IMAGE_REVIEW
        scene.project.current_phase = ProjectPhase.IMAGE_REVIEW
    else:
        if (upload.content_type or "").lower() != "video/mp4":
            raise ValueError("Video worker results must be MP4")
        output_dir = Path(settings.media_root) / str(scene.project_id) / "videos" / str(scene.id)
        path = output_dir / f"worker-{uuid4().hex}.mp4"
        await _save_upload(upload, path, settings.worker_result_max_bytes)
        try:
            validation = validate_video_output(
                str(path), output_dir, expected_duration=worker_job.payload_json["parameters"]["duration"]
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        relative = f"{scene.project_id}/videos/{scene.id}/{path.name}"
        public_url = f"{settings.public_media_base_url.rstrip('/')}/{relative}"
        asset = MediaAsset(
            project_id=scene.project_id,
            scene_id=scene.id,
            provider=f"worker:{generation_job.provider}",
            provider_asset_id=f"worker-job-{worker_job.id}",
            type=MediaAssetType.AI_VIDEO,
            preview_url=public_url,
            download_url=public_url,
            source_page_url=None,
            width=validation["width"],
            height=validation["height"],
            duration=validation["duration"],
            local_path=str(path.resolve()),
            metadata_json={
                "worker_job_id": worker_job.id,
                "source_asset_id": worker_job.payload_json["input_asset_ids"][0],
                "validation": validation,
                **_safe_result_metadata(metadata),
            },
            relevance_score=1,
            status=MediaAssetStatus.CANDIDATE,
        )
        scene.project.status = ProjectStatus.VIDEO_REVIEW
        scene.project.current_phase = ProjectPhase.VIDEO_REVIEW
    db.add(asset)
    db.flush()
    generation_job.status = "COMPLETED"
    generation_job.progress = 1
    generation_job.output_asset_id = asset.id
    generation_job.completed_at = datetime.now(UTC)
    worker_job.status = WorkerJobStatus.COMPLETED
    worker_job.progress = 1
    worker_job.result_json = _safe_result_metadata(metadata)
    worker_job.completed_at = datetime.now(UTC)
    worker_job.lease_expires_at = None
    db.commit()
    db.refresh(worker_job)
    return worker_job


def fail_worker_job(
    worker_job: WorkerJob,
    worker_id: str,
    error_message: str,
    diagnostics: dict[str, Any],
    db: Session,
) -> WorkerJob:
    _validate_claim(worker_job, worker_id)
    worker_job.status = WorkerJobStatus.FAILED
    worker_job.error_message = error_message
    worker_job.result_json = _safe_result_metadata({"diagnostics": diagnostics})
    worker_job.completed_at = datetime.now(UTC)
    worker_job.lease_expires_at = None
    generation_job = db.get(GenerationJob, worker_job.generation_job_id)
    if generation_job:
        generation_job.status = "FAILED"
        generation_job.error_message = error_message
        generation_job.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(worker_job)
    return worker_job


def cancel_worker_job(generation_job_id: int, db: Session) -> None:
    worker_job = db.scalar(
        select(WorkerJob).where(WorkerJob.generation_job_id == generation_job_id)
    )
    if worker_job and worker_job.status not in {WorkerJobStatus.COMPLETED, WorkerJobStatus.FAILED}:
        worker_job.status = WorkerJobStatus.CANCELED
        worker_job.lease_expires_at = None
        db.commit()


def validate_worker_asset_access(asset_id: int, worker_id: str, db: Session) -> MediaAsset:
    jobs = list(
        db.scalars(
            select(WorkerJob).where(
                WorkerJob.claimed_by == worker_id,
                WorkerJob.status.in_([WorkerJobStatus.CLAIMED, WorkerJobStatus.RUNNING]),
            )
        )
    )
    if not any(asset_id in job.payload_json.get("input_asset_ids", []) for job in jobs):
        raise ValueError("Asset is not assigned to this worker")
    asset = db.get(MediaAsset, asset_id)
    if asset is None or not asset.local_path:
        raise ValueError("Worker input asset is unavailable")
    path = Path(asset.local_path).resolve()
    root = Path(get_settings().media_root).resolve()
    if not path.is_file() or not path.is_relative_to(root):
        raise ValueError("Worker input asset is outside managed storage")
    return asset


def queue_health(db: Session) -> WorkerQueueHealth:
    counts = dict(
        db.execute(
            select(WorkerJob.status, func.count(WorkerJob.id)).group_by(WorkerJob.status)
        ).all()
    )
    now = datetime.now(UTC)
    stale = db.scalar(
        select(func.count(WorkerJob.id)).where(
            WorkerJob.status.in_([WorkerJobStatus.CLAIMED, WorkerJobStatus.RUNNING]),
            WorkerJob.lease_expires_at < now,
        )
    ) or 0
    settings = get_settings()
    return WorkerQueueHealth(
        status="ok",
        execution_mode=settings.generation_execution_mode,
        queued=counts.get(WorkerJobStatus.QUEUED, 0),
        claimed=counts.get(WorkerJobStatus.CLAIMED, 0),
        running=counts.get(WorkerJobStatus.RUNNING, 0),
        failed=counts.get(WorkerJobStatus.FAILED, 0),
        stale_recoverable=stale,
        token_is_default=settings.worker_auth_token == "change-me-in-production",
    )


def _validate_input_assets(scene_id: int, asset_ids: list[int], db: Session) -> None:
    if not asset_ids:
        return
    media_root = Path(get_settings().media_root).resolve()
    assets = list(
        db.scalars(select(MediaAsset).where(MediaAsset.id.in_(asset_ids), MediaAsset.scene_id == scene_id))
    )
    invalid_asset = len(assets) != len(set(asset_ids))
    for asset in assets:
        if not asset.local_path:
            invalid_asset = True
            break
        path = Path(asset.local_path).resolve()
        if not path.is_relative_to(media_root) or not path.is_file():
            invalid_asset = True
            break
    if invalid_asset:
        raise ValueError("Worker input assets must belong to the scene and exist in managed storage")


def _validate_claim(worker_job: WorkerJob, worker_id: str) -> None:
    if worker_job.status not in {WorkerJobStatus.CLAIMED, WorkerJobStatus.RUNNING}:
        raise ValueError("Worker job is not active")
    if worker_job.claimed_by != worker_id:
        raise ValueError("Worker does not own this job lease")


async def _save_upload(upload: UploadFile, path: Path, maximum: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > maximum:
                    raise ValueError("Worker result exceeds the configured size limit")
                output.write(chunk)
        if size == 0:
            raise ValueError("Worker result is empty")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _safe_result_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {"seed", "runtime_seconds", "model", "diagnostics", "logs"}
    safe = {key: value for key, value in metadata.items() if key in allowed}
    if "logs" in safe:
        safe["logs"] = str(safe["logs"])[-4000:]
    return safe


def _asset_media_type(asset: MediaAsset | None) -> str:
    if asset is None:
        return "application/octet-stream"
    return "image/png" if asset.type in {MediaAssetType.AI_IMAGE, MediaAssetType.STOCK_IMAGE} else "video/mp4"


def _dimensions(resolution: str) -> tuple[int, int]:
    try:
        width, height = (int(item) for item in resolution.lower().split("x", maxsplit=1))
    except (AttributeError, TypeError, ValueError):
        return 1920, 1080
    if width < 64 or height < 64:
        return 1920, 1080
    return width - width % 2, height - height % 2
