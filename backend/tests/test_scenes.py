from app.services.scene_planner import split_narration


def project_payload():
    return {
        "title": "Scene plan",
        "animal_topic": "Snow leopard",
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": 120,
        "output_resolution": "1920x1080",
        "documentary_tone": "cinematic wildlife documentary",
    }


def ready_project(client):
    project = client.post("/api/projects", json=project_payload()).json()
    research = client.post(f"/api/projects/{project['id']}/research/generate").json()
    client.post(f"/api/research/facts/{research['facts'][0]['id']}/approve")
    script = client.post(f"/api/projects/{project['id']}/script/generate").json()["current"]
    client.post(f"/api/scripts/{script['id']}/approve")
    return project, script


def test_narration_splits_at_useful_size():
    text = " ".join(["A short factual sentence about wildlife."] * 20)
    chunks = split_narration(text, 140)
    assert len(chunks) > 2
    assert all(chunk.strip() for chunk in chunks)
    assert max(len(chunk.split()) for chunk in chunks) <= 24


def test_generate_order_duration_strategy_and_no_script_damage(client):
    project, script = ready_project(client)
    original_text = script["full_text"]
    response = client.post(f"/api/projects/{project['id']}/scenes/generate")
    assert response.status_code == 200
    plan = response.json()
    scenes = plan["scenes"]
    assert len(scenes) > 2
    assert [scene["order"] for scene in scenes] == list(range(1, len(scenes) + 1))
    assert abs(plan["total_duration"] - script["estimated_duration_seconds"]) < 0.1
    assert all(
        scene["visual_strategy"] in {"STOCK_VIDEO", "AI_IMAGE_MOTION", "AI_VIDEO"}
        for scene in scenes
    )
    assert all(scene["end_time"] > scene["start_time"] for scene in scenes)
    assert all(scene["prompts"] for scene in scenes)
    unchanged = client.get(f"/api/projects/{project['id']}/script").json()["current"]
    assert unchanged["full_text"] == original_text
    assert unchanged["approved"] is True


def test_scene_crud_reorder_and_regeneration(client):
    project, _ = ready_project(client)
    plan = client.post(f"/api/projects/{project['id']}/scenes/generate").json()
    scenes = plan["scenes"]
    first = scenes[0]
    last = scenes[-1]

    edited = client.patch(
        f"/api/scenes/{first['id']}",
        json={"visual_description": "Edited visual", "target_duration": 8},
    )
    assert edited.status_code == 200
    assert edited.json()["visual_description"] == "Edited visual"

    regenerated = client.post(f"/api/scenes/{first['id']}/regenerate")
    assert regenerated.status_code == 200
    assert len(regenerated.json()["prompts"]) == 2
    assert regenerated.json()["narration_text"] == first["narration_text"]

    new_scene = client.post(
        f"/api/projects/{project['id']}/scenes",
        json={
            "order": 2,
            "narration_text": "Manual bridge narration.",
            "target_duration": 5,
            "species": "Snow leopard",
            "environment": "Verified environment pending",
            "animal_behavior": "Static observation",
            "visual_description": "A restrained bridge visual",
            "shot_type": "wide",
            "camera_motion": "locked-off",
            "visual_strategy": "STOCK_VIDEO",
        },
    )
    assert new_scene.status_code == 201
    assert new_scene.json()["order"] == 2

    current = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    reversed_ids = [scene["id"] for scene in reversed(current)]
    reordered = client.post(
        f"/api/projects/{project['id']}/scenes/reorder", json={"scene_ids": reversed_ids}
    )
    assert reordered.status_code == 200
    assert reordered.json()["scenes"][0]["id"] == last["id"]
    assert reordered.json()["scenes"][0]["start_time"] == 0

    delete_id = new_scene.json()["id"]
    assert client.delete(f"/api/scenes/{delete_id}").status_code == 204
    after_delete = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    assert delete_id not in {scene["id"] for scene in after_delete}
    assert [scene["order"] for scene in after_delete] == list(range(1, len(after_delete) + 1))


def test_requires_approved_script_and_valid_reorder(client):
    project = client.post("/api/projects", json=project_payload()).json()
    assert client.post(f"/api/projects/{project['id']}/scenes/generate").status_code == 422

    project, _ = ready_project(client)
    plan = client.post(f"/api/projects/{project['id']}/scenes/generate").json()
    bad = client.post(
        f"/api/projects/{project['id']}/scenes/reorder",
        json={"scene_ids": [plan["scenes"][0]["id"]]},
    )
    assert bad.status_code == 422
