import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from test_image_generation import ai_scene
from test_timeline import timeline_project
from test_video_generation import selected_image

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset
from app.models.scene import Scene, VisualStrategy
from app.models.worker import WorkerJob, WorkerJobStatus
from app.services.image_generation import submit_image_job
from app.services.worker_queue import enqueue_generation_job


def worker_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().worker_auth_token}"}


def queued_image_job(client) -> tuple[dict, int, int]:
    project, scene_data = ai_scene(client)
    db = SessionLocal()
    try:
        scene = db.scalar(
            select(Scene)
            .where(Scene.id == scene_data["id"])
            .options(selectinload(Scene.project), selectinload(Scene.prompts))
        )
        prompt = scene.prompts[-1]
        generation = submit_image_job(scene, prompt, db, seed=123)
        worker = enqueue_generation_job(generation, db)
        return project, generation.id, worker.id
    finally:
        db.close()


def result_png(width: int = 1920, height: int = 1080) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), (30, 70, 45)).save(output, "PNG")
    return output.getvalue()


def test_worker_auth_claim_payload_progress_completion_and_duplicate_delivery(client):
    project, generation_id, worker_job_id = queued_image_job(client)
    unauthorized = client.post(
        "/api/worker/jobs/claim",
        json={"worker_id": "gpu-1", "accepted_job_types": ["AI_IMAGE"]},
    )
    assert unauthorized.status_code == 401
    claim = client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "gpu-1", "accepted_job_types": ["AI_IMAGE"]},
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["job"]["id"] == worker_job_id
    assert body["payload"]["schema_version"] == 1
    assert body["payload"]["job_type"] == "AI_IMAGE"
    assert body["payload"]["parameters"] == {"width": 1920, "height": 1080, "seed": 123}
    assert body["payload"]["callback_metadata"] == {
        "progress_path": f"/api/worker/jobs/{worker_job_id}/progress",
        "complete_path": f"/api/worker/jobs/{worker_job_id}/complete",
        "fail_path": f"/api/worker/jobs/{worker_job_id}/fail",
    }
    serialized = str(body["payload"]).lower()
    assert "local_path" not in serialized and "shell" not in serialized

    wrong_owner = client.post(
        f"/api/worker/jobs/{worker_job_id}/progress",
        headers=worker_headers(),
        json={"worker_id": "gpu-2", "progress": 0.4},
    )
    assert wrong_owner.status_code == 409
    progress = client.post(
        f"/api/worker/jobs/{worker_job_id}/progress",
        headers=worker_headers(),
        json={"worker_id": "gpu-1", "progress": 0.4},
    )
    assert progress.status_code == 200 and progress.json()["status"] == "RUNNING"

    completed = client.post(
        f"/api/worker/jobs/{worker_job_id}/complete",
        headers=worker_headers(),
        data={"worker_id": "gpu-1", "result_json": '{"model":"test-worker","logs":"ok"}'},
        files={"file": ("result.png", result_png(), "image/png")},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    db = SessionLocal()
    try:
        generation = db.get(GenerationJob, generation_id)
        assert generation.status == "COMPLETED" and generation.output_asset_id is not None
        asset_id = generation.output_asset_id
        asset = db.get(MediaAsset, asset_id)
        assert Path(asset.local_path).is_file()
        assert asset.metadata_json["worker_job_id"] == worker_job_id
    finally:
        db.close()

    duplicate = client.post(
        f"/api/worker/jobs/{worker_job_id}/complete",
        headers=worker_headers(),
        data={"worker_id": "gpu-1", "result_json": "{}"},
        files={"file": ("duplicate.png", result_png(), "image/png")},
    )
    assert duplicate.status_code == 200
    db = SessionLocal()
    try:
        assets = [
            asset
            for asset in db.scalars(
                select(MediaAsset).where(MediaAsset.project_id == project["id"])
            )
            if asset.metadata_json.get("worker_job_id") == worker_job_id
        ]
        assert len(assets) == 1 and assets[0].id == asset_id
    finally:
        db.close()


def test_normal_image_api_enqueues_in_worker_execution_mode(client, monkeypatch):
    _, scene = ai_scene(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/image-prompts/generate").json()
    monkeypatch.setattr(get_settings(), "generation_execution_mode", "worker")
    submitted = client.post(
        f"/api/scenes/{scene['id']}/images/generate",
        json={"prompt_id": prompt["id"], "seed": 44},
    )
    assert submitted.status_code == 202
    assert submitted.json()["status"] == "PENDING"
    db = SessionLocal()
    try:
        worker_job = db.scalar(
            select(WorkerJob).where(
                WorkerJob.generation_job_id == submitted.json()["id"]
            )
        )
        assert worker_job is not None and worker_job.status == WorkerJobStatus.QUEUED
    finally:
        db.close()


def test_worker_failure_and_expired_lease_recovery(client):
    _, generation_id, worker_job_id = queued_image_job(client)
    client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "dead-worker", "accepted_job_types": ["AI_IMAGE"]},
    )
    db = SessionLocal()
    try:
        worker_job = db.get(WorkerJob, worker_job_id)
        worker_job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    reclaimed = client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "replacement", "accepted_job_types": ["AI_IMAGE"]},
    )
    assert reclaimed.status_code == 200
    assert reclaimed.json()["job"]["attempts"] == 2
    failed = client.post(
        f"/api/worker/jobs/{worker_job_id}/fail",
        headers=worker_headers(),
        json={
            "worker_id": "replacement",
            "error_message": "GPU out of memory",
            "diagnostics": {"device": "mock"},
        },
    )
    assert failed.status_code == 200 and failed.json()["status"] == "FAILED"
    db = SessionLocal()
    try:
        generation = db.get(GenerationJob, generation_id)
        assert generation.status == "FAILED"
        assert generation.error_message == "GPU out of memory"
    finally:
        db.close()


def test_video_api_serializes_only_managed_input_references(client, monkeypatch):
    _, scene, image = selected_image(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/video-prompts/generate").json()
    monkeypatch.setattr(get_settings(), "generation_execution_mode", "worker")
    submitted = client.post(
        f"/api/scenes/{scene['id']}/videos/generate",
        json={
            "prompt_id": prompt["id"],
            "source_asset_id": image["id"],
            "duration": 1,
            "fps": 12,
        },
    )
    assert submitted.status_code == 202
    claim = client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "video-worker", "accepted_job_types": ["AI_VIDEO"]},
    )
    assert claim.status_code == 200
    payload = claim.json()["payload"]
    assert payload["job_type"] == "AI_VIDEO"
    assert payload["input_asset_ids"] == [image["id"]]
    assert payload["parameters"]["duration"] == 1
    assert "local_path" not in str(payload).lower()
    reference = claim.json()["input_assets"][0]
    download = client.get(reference["download_url"], headers=worker_headers())
    assert download.status_code == 200 and len(download.content) > 1000


def test_worker_queue_health_and_empty_claim(client):
    health = client.get("/api/worker/queue/health", headers=worker_headers())
    assert health.status_code == 200
    assert health.json()["execution_mode"] == "local"
    assert health.json()["token_is_default"] is True
    empty = client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "idle-worker", "accepted_job_types": ["AI_IMAGE", "AI_VIDEO"]},
    )
    assert empty.status_code == 204


def test_worker_rejects_wrong_dimensions_and_preserves_active_job(client):
    _, generation_id, worker_job_id = queued_image_job(client)
    client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "gpu-validate", "accepted_job_types": ["AI_IMAGE"]},
    )
    rejected = client.post(
        f"/api/worker/jobs/{worker_job_id}/complete",
        headers=worker_headers(),
        data={"worker_id": "gpu-validate", "result_json": "{}"},
        files={"file": ("wrong.png", result_png(320, 180), "image/png")},
    )
    assert rejected.status_code == 422
    db = SessionLocal()
    try:
        assert db.get(WorkerJob, worker_job_id).status == WorkerJobStatus.CLAIMED
        assert db.get(GenerationJob, generation_id).output_asset_id is None
    finally:
        db.close()


def test_remote_worker_completion_resumes_auto_workflow(client, monkeypatch):
    project, scenes, _ = timeline_project(client)
    db = SessionLocal()
    try:
        first = db.get(Scene, scenes[0]["id"])
        old_asset = db.get(MediaAsset, first.preferred_media_asset_id)
        first.preferred_media_asset_id = None
        first.visual_strategy = VisualStrategy.AI_IMAGE_MOTION
        db.delete(old_asset)
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(get_settings(), "generation_execution_mode", "worker")
    client.post(
        f"/api/projects/{project['id']}/workflow/start",
        json={"mode": "AUTO", "policy": {"generate_ai_video": False}},
    )
    paused = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert paused["status"] == "PAUSED" and paused["current_step"] == "IMAGES"
    claim = client.post(
        "/api/worker/jobs/claim",
        headers=worker_headers(),
        json={"worker_id": "workflow-worker", "accepted_job_types": ["AI_IMAGE"]},
    ).json()
    worker_job_id = claim["job"]["id"]
    completed = client.post(
        f"/api/worker/jobs/{worker_job_id}/complete",
        headers=worker_headers(),
        data={"worker_id": "workflow-worker", "result_json": '{"model":"workflow-mock"}'},
        files={"file": ("result.png", result_png(), "image/png")},
    )
    assert completed.status_code == 200
    workflow = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert workflow["status"] == "RENDER_READY"
    assert workflow["progress"] == 100
