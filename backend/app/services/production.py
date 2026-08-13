import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.jobs import GenerationJob, RenderJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import Project, ProjectStatus
from app.models.scene import Scene
from app.schemas.export import MediaMaintenanceReport, ProjectStorageReport


def project_storage_report(project_id: int, db: Session) -> ProjectStorageReport:
    root = _project_root(project_id)
    files = [path for path in root.rglob("*") if path.is_file()] if root.is_dir() else []
    missing = [
        asset.id
        for asset in db.scalars(select(MediaAsset).where(MediaAsset.project_id == project_id))
        if asset.local_path and not _is_managed_file(Path(asset.local_path), root)
    ]
    return ProjectStorageReport(
        project_id=project_id,
        usage_bytes=sum(path.stat().st_size for path in files),
        file_count=len(files),
        missing_asset_ids=missing,
        generation_job_count=db.scalar(
            select(func.count(GenerationJob.id)).where(GenerationJob.project_id == project_id)
        )
        or 0,
        render_job_count=db.scalar(
            select(func.count(RenderJob.id)).where(RenderJob.project_id == project_id)
        )
        or 0,
    )


def maintain_project_media(
    project_id: int, cleanup_unused: bool, db: Session
) -> MediaMaintenanceReport:
    root = _project_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    selected_ids = set(
        db.scalars(
            select(Scene.preferred_media_asset_id).where(
                Scene.project_id == project_id, Scene.preferred_media_asset_id.is_not(None)
            )
        )
    )
    removed_ids: list[int] = []
    removed_files = 0
    proxies = 0
    assets = list(db.scalars(select(MediaAsset).where(MediaAsset.project_id == project_id)))
    for asset in assets:
        if cleanup_unused and _is_unused_generation(asset, selected_ids):
            if asset.local_path:
                path = Path(asset.local_path).resolve()
                if path.is_relative_to(root) and path.is_file():
                    path.unlink()
                    removed_files += 1
            for job in db.scalars(
                select(GenerationJob).where(GenerationJob.output_asset_id == asset.id)
            ):
                job.output_asset_id = None
            removed_ids.append(asset.id)
            db.delete(asset)
            continue
        if (
            asset.id in selected_ids
            and asset.local_path
            and _is_managed_file(Path(asset.local_path), root)
        ):
            proxy = _ensure_proxy(asset, root)
            if proxy:
                metadata = dict(asset.metadata_json)
                metadata["proxy_path"] = str(proxy)
                metadata["proxy_url"] = (
                    f"{get_settings().public_media_base_url.rstrip('/')}/{project_id}/proxies/{proxy.name}"
                )
                asset.metadata_json = metadata
                proxies += 1
    db.commit()
    report = project_storage_report(project_id, db)
    return MediaMaintenanceReport(
        **report.model_dump(),
        removed_asset_ids=removed_ids,
        removed_files=removed_files,
        proxies_created=proxies,
    )


def recover_stale_generation_jobs(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().job_stale_seconds)
    jobs = list(
        db.scalars(
            select(GenerationJob).where(
                GenerationJob.status.in_(["PENDING", "RUNNING"]),
                GenerationJob.updated_at < cutoff,
            )
        )
    )
    for job in jobs:
        job.status = "FAILED"
        job.error_message = "Generation process was interrupted or timed out; retry is safe."
        project = db.get(Project, job.project_id)
        if project and project.status not in {ProjectStatus.COMPLETED, ProjectStatus.RENDERING}:
            project.status = ProjectStatus.FAILED
    if jobs:
        db.commit()
    return len(jobs)


def delete_project_storage(project_id: int) -> None:
    root = _project_root(project_id)
    media_root = Path(get_settings().media_root).resolve()
    if root.parent != media_root:
        raise RuntimeError("Refusing to delete project storage outside managed media root")
    if root.exists():
        shutil.rmtree(root)


def _ensure_proxy(asset: MediaAsset, root: Path) -> Path | None:
    source = Path(asset.local_path or "").resolve()
    proxy_dir = root / "proxies"
    proxy_dir.mkdir(parents=True, exist_ok=True)
    if asset.type in {MediaAssetType.AI_IMAGE, MediaAssetType.STOCK_IMAGE}:
        output = proxy_dir / f"asset-{asset.id}.jpg"
        if output.is_file() and output.stat().st_mtime >= source.stat().st_mtime:
            return None
        with Image.open(source) as image:
            proxy_image = image.convert("RGB")
            proxy_image.thumbnail((640, 360))
            proxy_image.save(output, "JPEG", quality=82)
        return output.resolve()
    if asset.type in {MediaAssetType.AI_VIDEO, MediaAssetType.STOCK_VIDEO}:
        output = proxy_dir / f"asset-{asset.id}.jpg"
        if output.is_file() and output.stat().st_mtime >= source.stat().st_mtime:
            return None
        ffmpeg = shutil.which(get_settings().ffmpeg_path)
        if ffmpeg is None:
            return None
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                "0",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return output.resolve() if completed.returncode == 0 and output.is_file() else None
    return None


def _is_unused_generation(asset: MediaAsset, selected_ids: set[int]) -> bool:
    return (
        asset.type in {MediaAssetType.AI_IMAGE, MediaAssetType.AI_VIDEO}
        and asset.id not in selected_ids
        and asset.status != MediaAssetStatus.SELECTED
    )


def _project_root(project_id: int) -> Path:
    return (Path(get_settings().media_root).resolve() / str(project_id)).resolve()


def _is_managed_file(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(root) and resolved.is_file()
