from test_stock_media import ready_scene

from app.services.image_generation import DEFAULT_NEGATIVE_PROMPT, build_image_prompt


def ai_scene(client):
    project, scene = ready_scene(client)
    updated = client.patch(
        f"/api/scenes/{scene['id']}", json={"visual_strategy": "AI_IMAGE_MOTION"}
    )
    assert updated.status_code == 200
    return project, updated.json()


def test_structured_prompt_and_versioning(client):
    _, scene = ai_scene(client)
    generated = client.post(f"/api/scenes/{scene['id']}/image-prompts/generate")
    assert generated.status_code == 201
    prompt = generated.json()
    assert prompt["version"] == 2
    assert "Subject/species:" in prompt["image_prompt"]
    assert "Behavior:" in prompt["image_prompt"]
    assert "production-ready 16:9" in prompt["image_prompt"]
    assert "Visual continuity:" in prompt["image_prompt"]
    assert prompt["negative_prompt"] == DEFAULT_NEGATIVE_PROMPT

    edited = client.post(
        f"/api/scenes/{scene['id']}/image-prompts",
        json={
            "image_prompt": prompt["image_prompt"] + "\nLighting: soft dawn sidelight.",
            "negative_prompt": prompt["negative_prompt"],
        },
    )
    assert edited.status_code == 201
    assert edited.json()["version"] == 3
    history = client.get(f"/api/scenes/{scene['id']}/images").json()["prompts"]
    assert [item["version"] for item in history] == [3, 2, 1]


def test_mock_job_creates_and_selects_persistent_image(client):
    _, scene = ai_scene(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/image-prompts/generate").json()
    response = client.post(
        f"/api/scenes/{scene['id']}/images/generate",
        json={"prompt_id": prompt["id"], "seed": 12345},
    )
    assert response.status_code == 202
    bundle = client.get(f"/api/scenes/{scene['id']}/images").json()
    assert bundle["is_mock"] is True
    assert bundle["jobs"][0]["status"] == "COMPLETED"
    assert bundle["jobs"][0]["progress"] == 1
    assert bundle["jobs"][0]["seed"] == 12345
    assert len(bundle["assets"]) == 1
    asset = bundle["assets"][0]
    assert asset["type"] == "AI_IMAGE"
    assert asset["width"] == 1920 and asset["height"] == 1080
    assert asset["metadata_json"]["prompt_version"] == 2
    assert asset["local_path"].endswith(".png")
    assert asset["preview_url"] != asset["download_url"]
    assert client.get(asset["preview_url"].replace("http://localhost:8000", "")).status_code == 200
    assert client.get(f"/api/scenes/{scene['id']}/stock").json()["assets"] == []

    selected = client.post(f"/api/media-assets/{asset['id']}/select")
    assert selected.status_code == 200
    assert selected.json()["status"] == "SELECTED"
    assert (
        client.get(f"/api/scenes/{scene['id']}/images").json()["selected_asset_id"] == asset["id"]
    )


def test_regeneration_preserves_history_and_approved_selection(client):
    _, scene = ai_scene(client)
    prompt = client.post(f"/api/scenes/{scene['id']}/image-prompts/generate").json()
    client.post(
        f"/api/scenes/{scene['id']}/images/generate",
        json={"prompt_id": prompt["id"], "seed": 10},
    )
    first = client.get(f"/api/scenes/{scene['id']}/images").json()["assets"][0]
    client.post(f"/api/media-assets/{first['id']}/select")
    client.post(
        f"/api/scenes/{scene['id']}/images/generate",
        json={"prompt_id": prompt["id"], "seed": 11},
    )
    bundle = client.get(f"/api/scenes/{scene['id']}/images").json()
    assert len(bundle["assets"]) == 2
    assert len(bundle["jobs"]) == 2
    assert bundle["selected_asset_id"] == first["id"]


def test_failed_generation_has_diagnostics_and_retry(client):
    _, scene = ai_scene(client)
    prompt = client.post(
        f"/api/scenes/{scene['id']}/image-prompts",
        json={
            "image_prompt": "[fail] realistic snow leopard portrait",
            "negative_prompt": "bad anatomy",
        },
    ).json()
    failed = client.post(
        f"/api/scenes/{scene['id']}/images/generate", json={"prompt_id": prompt["id"]}
    )
    assert failed.status_code == 202
    first_job = client.get(f"/api/scenes/{scene['id']}/images").json()["jobs"][0]
    assert first_job["status"] == "FAILED"
    assert "Mock image generation failure" in first_job["error_message"]
    assert client.get(f"/api/scenes/{scene['id']}/images").json()["assets"] == []

    retried = client.post(f"/api/image-jobs/{first_job['id']}/retry")
    assert retried.status_code == 202
    jobs = client.get(f"/api/scenes/{scene['id']}/images").json()["jobs"]
    assert jobs[0]["retry_count"] == 1
    assert jobs[0]["id"] != first_job["id"]
    assert jobs[1]["error_message"] == first_job["error_message"]


def test_stock_strategy_cannot_generate_ai_image(client):
    _, scene = ready_scene(client)
    prompt = scene["prompts"][-1]
    response = client.post(
        f"/api/scenes/{scene['id']}/images/generate", json={"prompt_id": prompt["id"]}
    )
    assert response.status_code == 422


def test_prompt_builder_does_not_invent_age_or_sex():
    class MinimalScene:
        species = "Snow leopard"
        animal_behavior = "crossing a ridge"
        environment = "Himalayan alpine slope"
        shot_type = "wide tracking shot"
        visual_description = "The animal moves through rocks"

    prompt, _ = build_image_prompt(MinimalScene())
    assert "male" not in prompt.lower()
    assert "female" not in prompt.lower()
    assert "juvenile" not in prompt.lower()
