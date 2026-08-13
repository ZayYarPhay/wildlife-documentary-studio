from pathlib import Path

import pytest
from test_image_generation import ai_scene

from app.services.video_generation import build_video_prompt, validate_video_output


def selected_image(client):
    project, scene = ai_scene(client)
    client.patch(f"/api/scenes/{scene['id']}", json={"visual_strategy": "AI_VIDEO"})
    image_prompt = client.post(f"/api/scenes/{scene['id']}/image-prompts/generate").json()
    client.post(
        f"/api/scenes/{scene['id']}/images/generate",
        json={"prompt_id": image_prompt["id"], "seed": 42},
    )
    image = client.get(f"/api/scenes/{scene['id']}/images").json()["assets"][0]
    client.post(f"/api/media-assets/{image['id']}/select")
    return project, scene, image


def test_structured_motion_prompt_and_versioning(client):
    _, scene, _ = selected_image(client)
    response = client.post(f"/api/scenes/{scene['id']}/video-prompts/generate")
    assert response.status_code == 201
    prompt = response.json()
    assert "Desired action:" in prompt["video_prompt"]
    assert "Natural shoulder" in prompt["video_prompt"]
    assert "no morphing" in prompt["video_prompt"]
    edited = client.post(
        f"/api/scenes/{scene['id']}/video-prompts",
        json={"video_prompt": prompt["video_prompt"] + " Keep the movement especially subtle."},
    )
    assert edited.status_code == 201
    assert edited.json()["version"] == prompt["version"] + 1


def test_selected_image_becomes_validated_video_and_can_be_approved(client):
    _, scene, image = selected_image(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/video-prompts/generate").json()
    response = client.post(
        f"/api/scenes/{scene['id']}/videos/generate",
        json={"prompt_id": prompt["id"], "source_asset_id": image["id"], "duration": 1, "fps": 12},
    )
    assert response.status_code == 202
    bundle = client.get(f"/api/scenes/{scene['id']}/videos").json()
    assert bundle["jobs"][0]["status"] == "COMPLETED"
    assert len(bundle["assets"]) == 1
    video = bundle["assets"][0]
    assert video["type"] == "AI_VIDEO"
    assert video["duration"] == pytest.approx(1, abs=0.2)
    assert video["metadata_json"]["source_asset_id"] == image["id"]
    assert video["metadata_json"]["validation"]["size_bytes"] > 1024
    preview = client.get(video["preview_url"].replace("http://localhost:8000", ""))
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "video/mp4"
    selected = client.post(f"/api/media-assets/{video['id']}/select").json()
    assert selected["status"] == "SELECTED"
    assert (
        client.get(f"/api/scenes/{scene['id']}/videos").json()["selected_asset_id"] == video["id"]
    )


def test_regeneration_preserves_approved_video(client):
    _, scene, image = selected_image(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/video-prompts/generate").json()
    payload = {"prompt_id": prompt["id"], "source_asset_id": image["id"], "duration": 1, "fps": 12}
    client.post(f"/api/scenes/{scene['id']}/videos/generate", json=payload)
    first = client.get(f"/api/scenes/{scene['id']}/videos").json()["assets"][0]
    client.post(f"/api/media-assets/{first['id']}/select")
    second = client.post(f"/api/scenes/{scene['id']}/videos/generate", json=payload)
    assert second.status_code == 202
    bundle = client.get(f"/api/scenes/{scene['id']}/videos").json()
    assert len(bundle["assets"]) == 2
    assert bundle["selected_asset_id"] == first["id"]


def test_failure_retry_and_fallback_do_not_break_project(client):
    project, scene, image = selected_image(client)
    prompt = client.post(
        f"/api/scenes/{scene['id']}/video-prompts",
        json={"video_prompt": "[fail] keep natural wildlife motion without morphing"},
    ).json()
    payload = {"prompt_id": prompt["id"], "source_asset_id": image["id"], "duration": 1, "fps": 12}
    client.post(f"/api/scenes/{scene['id']}/videos/generate", json=payload)
    first = client.get(f"/api/scenes/{scene['id']}/videos").json()
    assert first["jobs"][0]["status"] == "FAILED"
    assert first["fallback_recommendations"] == []
    retry = client.post(f"/api/video-jobs/{first['jobs'][0]['id']}/retry")
    assert retry.status_code == 202
    after = client.get(f"/api/scenes/{scene['id']}/videos").json()
    assert after["jobs"][0]["retry_count"] == 1
    assert after["fallback_recommendations"] == ["AI_IMAGE_MOTION", "STOCK_VIDEO"]
    assert "Mock video generation failure" in after["jobs"][0]["error_message"]
    exhausted = client.post(f"/api/video-jobs/{after['jobs'][0]['id']}/retry")
    assert exhausted.status_code == 409
    project_state = client.get(f"/api/projects/{project['id']}").json()
    assert project_state["status"] == "VIDEO_REVIEW"
    chosen = client.post(
        f"/api/scenes/{scene['id']}/video-fallback", json={"strategy": "AI_IMAGE_MOTION"}
    )
    assert chosen.status_code == 200
    scene_state = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"][0]
    assert scene_state["visual_strategy"] == "AI_IMAGE_MOTION"


def test_requires_selected_local_ai_image(client):
    _, scene, image = selected_image(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/video-prompts/generate").json()
    client.post(f"/api/media-assets/{image['id']}/reject")
    response = client.post(
        f"/api/scenes/{scene['id']}/videos/generate",
        json={"prompt_id": prompt["id"], "source_asset_id": image["id"], "duration": 1},
    )
    assert response.status_code == 422


def test_output_validation_rejects_non_mp4():
    root = Path("test-video-validation").resolve()
    root.mkdir(exist_ok=True)
    bad = root / "fake.txt"
    try:
        bad.write_text("not video")
        with pytest.raises(RuntimeError, match="not MP4"):
            validate_video_output(str(bad), root, expected_duration=1)
    finally:
        bad.unlink(missing_ok=True)
        root.rmdir()


def test_prompt_builder_is_provider_neutral():
    class MinimalScene:
        species = "Bengal tiger"
        animal_behavior = "walking through vegetation"
        environment = "tall forest vegetation"
        camera_motion = "slow tracking"
        shot_type = "medium shot"
        target_duration = 5

    prompt = build_video_prompt(MinimalScene())
    assert "Bengal tiger" in prompt
    assert "Natural shoulder" in prompt
    assert not any(name in prompt.lower() for name in ["gemini", "veo", "runway"])
