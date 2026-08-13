from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from test_api import payload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import RenderJob
from app.models.project import Project, ProjectStatus
from app.models.thumbnail import ThumbnailAsset, ThumbnailConcept


def completed_project(client, topic: str = "Snow leopard") -> dict:
    project_data = client.post(
        "/api/projects", json=payload(title=f"{topic} Story", animal_topic=topic)
    ).json()
    root = Path(get_settings().media_root).resolve() / str(project_data["id"]) / "renders"
    root.mkdir(parents=True, exist_ok=True)
    output = root / "final.mp4"
    output.write_bytes(b"validated-final-render-placeholder")
    db = SessionLocal()
    try:
        project = db.get(Project, project_data["id"])
        project.status = ProjectStatus.COMPLETED
        db.add(
            RenderJob(
                project_id=project.id,
                status="COMPLETED",
                progress=1,
                output_path=str(output),
                settings_json={},
                validation_json={"output": {"valid": True}},
                finished_at=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()
    return project_data


def test_thumbnail_requires_completed_managed_final_render(client):
    project_data = client.post("/api/projects", json=payload()).json()
    before = client.get(f"/api/projects/{project_data['id']}/thumbnails")
    assert before.status_code == 200 and before.json()["final_render_ready"] is False
    blocked = client.post(f"/api/projects/{project_data['id']}/thumbnails/concepts")
    assert blocked.status_code == 409
    assert "final MP4" in blocked.json()["error"]["message"]


def test_three_concepts_and_default_no_text_thumbnail_generation(client):
    project_data = completed_project(client)
    concepts_response = client.post(f"/api/projects/{project_data['id']}/thumbnails/concepts")
    assert concepts_response.status_code == 200
    bundle = concepts_response.json()
    assert len(bundle["concepts"]) == 3
    assert [item["concept_order"] for item in bundle["concepts"]] == [1, 2, 3]
    assert all("exactly one Snow leopard" in item["prompt"] for item in bundle["concepts"])
    assert all("No text" in item["prompt"] for item in bundle["concepts"])
    generated = client.post(
        f"/api/projects/{project_data['id']}/thumbnails/generate",
        json={"title_overlay": False, "seed": 101},
    )
    assert generated.status_code == 202
    result = client.get(f"/api/projects/{project_data['id']}/thumbnails").json()
    assert len(result["assets"]) == 3
    assert all(item["status"] == "COMPLETED" for item in result["assets"])
    assert all(item["title_overlay"] is False for item in result["assets"])
    assert all(item["metadata_json"]["default_no_text"] is True for item in result["assets"])
    db = SessionLocal()
    try:
        for item in result["assets"]:
            asset = db.get(ThumbnailAsset, item["id"])
            path = Path(asset.local_path)
            assert path.is_file()
            with Image.open(path) as image:
                assert image.size == (1280, 720) and image.format == "PNG"
    finally:
        db.close()
    download = client.get(f"/api/thumbnail-assets/{result['assets'][0]['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"


def test_optional_title_overlay_approval_and_history(client):
    project_data = completed_project(client, "Orca")
    first = client.post(f"/api/projects/{project_data['id']}/thumbnails/concepts").json()
    concept_ids = [item["id"] for item in first["concepts"]]
    missing_text = client.post(
        f"/api/projects/{project_data['id']}/thumbnails/generate",
        json={"concept_ids": [concept_ids[0]], "title_overlay": True},
    )
    assert missing_text.status_code == 422
    client.post(
        f"/api/projects/{project_data['id']}/thumbnails/generate",
        json={
            "concept_ids": concept_ids[:2],
            "title_overlay": True,
            "overlay_text": "Families of the Sea",
        },
    )
    assets = client.get(f"/api/projects/{project_data['id']}/thumbnails").json()["assets"]
    assert len(assets) == 2
    assert all(item["metadata_json"]["default_no_text"] is False for item in assets)
    first_approval = client.post(f"/api/thumbnail-assets/{assets[0]['id']}/approve")
    assert first_approval.status_code == 200
    client.post(f"/api/thumbnail-assets/{assets[1]['id']}/approve")
    selected = client.get(f"/api/projects/{project_data['id']}/thumbnails").json()
    assert selected["approved_thumbnail_id"] == assets[1]["id"]
    assert sum(item["status"] == "APPROVED" for item in selected["assets"]) == 1

    second = client.post(f"/api/projects/{project_data['id']}/thumbnails/concepts").json()
    assert len(second["concepts"]) == 3
    assert all(item["version"] == 2 for item in second["concepts"])
    assert len(second["assets"]) == 2
    db = SessionLocal()
    try:
        assert db.query(ThumbnailConcept).filter_by(project_id=project_data["id"]).count() == 6
    finally:
        db.close()


def test_failed_thumbnail_retry_preserves_attempt(client):
    project_data = completed_project(client, "Barn owl")
    concept = client.post(f"/api/projects/{project_data['id']}/thumbnails/concepts").json()[
        "concepts"
    ][0]
    db = SessionLocal()
    try:
        stored = db.get(ThumbnailConcept, concept["id"])
        stored.prompt += " [fail]"
        db.commit()
    finally:
        db.close()
    client.post(
        f"/api/projects/{project_data['id']}/thumbnails/generate",
        json={"concept_ids": [concept["id"]]},
    )
    failed = client.get(f"/api/projects/{project_data['id']}/thumbnails").json()["assets"][0]
    assert failed["status"] == "FAILED" and "failure" in failed["error_message"].lower()
    db = SessionLocal()
    try:
        stored = db.get(ThumbnailConcept, concept["id"])
        stored.prompt = stored.prompt.replace(" [fail]", "")
        db.commit()
    finally:
        db.close()
    retry = client.post(f"/api/thumbnail-assets/{failed['id']}/retry")
    assert retry.status_code == 202
    history = client.get(f"/api/projects/{project_data['id']}/thumbnails").json()["assets"]
    assert len(history) == 2
    assert history[0]["status"] == "COMPLETED" and history[0]["retry_count"] == 1
    assert history[1]["status"] == "FAILED"


def test_cross_project_concepts_are_rejected(client):
    first = completed_project(client, "Cheetah")
    second = completed_project(client, "Manta ray")
    concept_id = client.post(f"/api/projects/{first['id']}/thumbnails/concepts").json()["concepts"][
        0
    ]["id"]
    response = client.post(
        f"/api/projects/{second['id']}/thumbnails/generate",
        json={"concept_ids": [concept_id]},
    )
    assert response.status_code == 409
    db = SessionLocal()
    try:
        assert db.query(ThumbnailAsset).filter_by(project_id=second["id"]).count() == 0
    finally:
        db.close()
