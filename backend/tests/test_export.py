from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from test_api import payload
from test_timeline import timeline_project

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import GenerationJob, RenderJob
from app.models.project import Project, ProjectStatus
from app.models.timeline import Timeline, TimelineItem, TimelineTrack
from app.schemas.export import ExportSettings
from app.services.production import recover_stale_generation_jobs
from app.services.rendering import (
    preflight_project,
    recover_stale_render_jobs,
    run_render_job,
    submit_render_job,
)


def test_preflight_reports_actionable_errors(client):
    project_data = client.post("/api/projects", json=payload()).json()
    response = client.post(
        f"/api/projects/{project_data['id']}/export/preflight",
        json={"subtitles_enabled": False},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["ready"] is False
    error_codes = {item["code"] for item in report["checks"] if item["status"] == "ERROR"}
    assert {"TIMELINE", "VOICE", "VISUAL_FILES"} <= error_codes


def test_tiny_ffmpeg_export_is_valid_and_downloadable(client):
    project_data, _, _ = timeline_project(client)
    timeline_data = client.post(
        f"/api/projects/{project_data['id']}/timeline/build"
    ).json()["current"]
    db = SessionLocal()
    try:
        timeline = db.get(Timeline, timeline_data["id"])
        visuals = list(
            db.scalars(
                select(TimelineItem)
                .where(
                    TimelineItem.timeline_id == timeline.id,
                    TimelineItem.track == TimelineTrack.VISUAL,
                )
                .order_by(TimelineItem.order)
            )
        )
        assert visuals
        for extra in visuals[1:]:
            db.delete(extra)
        visuals[0].start_time = 0
        visuals[0].end_time = 1
        voice = db.scalar(
            select(TimelineItem).where(
                TimelineItem.timeline_id == timeline.id,
                TimelineItem.track == TimelineTrack.VOICE,
            )
        )
        voice.start_time = 0
        voice.end_time = 1
        voice.source_out = 1
        timeline.duration = 1
        timeline.valid = True
        timeline.warnings_json = []
        project = db.get(Project, project_data["id"])
        export = ExportSettings(fps=12, preset="ultrafast", crf=30, subtitles_enabled=False)
        report = preflight_project(project, db, export)
        assert report.ready
        job = submit_render_job(project, export, db)
        job_id = job.id
    finally:
        db.close()

    run_render_job(job_id)

    db = SessionLocal()
    try:
        job = db.get(RenderJob, job_id)
        assert job.status == "COMPLETED"
        assert job.progress == 1
        assert job.duration is not None and abs(job.duration - 1) <= 0.5
        assert job.width == 1920 and job.height == 1080
        assert job.validation_json["output"]["has_video"] is True
        assert job.validation_json["output"]["has_audio"] is True
        assert Path(job.output_path).is_file() and job.file_size_bytes > 0
        assert db.get(Project, project_data["id"]).status == ProjectStatus.COMPLETED
    finally:
        db.close()
    download = client.get(f"/api/render-jobs/{job_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"


def test_duplicate_storage_maintenance_and_safe_delete(client):
    project_data, _, _ = timeline_project(client)
    client.post(f"/api/projects/{project_data['id']}/timeline/build")
    maintenance = client.post(
        f"/api/projects/{project_data['id']}/media/maintenance",
        json={"cleanup_unused": False},
    )
    assert maintenance.status_code == 200
    assert maintenance.json()["usage_bytes"] > 0
    assert maintenance.json()["proxies_created"] >= 1
    storage = client.get(f"/api/projects/{project_data['id']}/storage").json()
    assert storage["file_count"] > 0
    assert storage["missing_asset_ids"] == []

    duplicate = client.post(f"/api/projects/{project_data['id']}/duplicate")
    assert duplicate.status_code == 201
    copy_data = duplicate.json()
    assert copy_data["title"].endswith("(Copy)")
    assert copy_data["status"] == "DRAFT"
    copy_root = Path(get_settings().media_root).resolve() / str(copy_data["id"])
    copy_root.mkdir(parents=True)
    (copy_root / "orphan.tmp").write_text("safe cleanup", encoding="utf-8")
    assert client.delete(f"/api/projects/{copy_data['id']}").status_code == 204
    assert not copy_root.exists()


def test_stale_jobs_recover_with_diagnostics(client):
    project_data = client.post("/api/projects", json=payload()).json()
    db = SessionLocal()
    try:
        old = datetime.now(UTC) - timedelta(hours=1)
        generation = GenerationJob(
            project_id=project_data["id"],
            job_type="AI_IMAGE",
            provider="mock",
            status="RUNNING",
            progress=0.4,
            retry_count=0,
            request_json={},
            updated_at=old,
        )
        render = RenderJob(
            project_id=project_data["id"],
            status="RUNNING",
            progress=0.5,
            settings_json={},
            validation_json={},
            updated_at=old,
        )
        db.add_all([generation, render])
        db.commit()
        assert recover_stale_generation_jobs(db) == 1
        assert recover_stale_render_jobs(db) == 1
        db.refresh(generation)
        db.refresh(render)
        assert generation.status == "FAILED" and "retry" in generation.error_message.lower()
        assert render.status == "FAILED" and "retry" in render.error_message.lower()
    finally:
        db.close()
