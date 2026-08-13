from types import SimpleNamespace

from app.services.stock_media import build_stock_queries, score_candidate


def project_payload():
    return {
        "title": "Stock search",
        "animal_topic": "Snow leopard",
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": 120,
        "output_resolution": "1920x1080",
        "documentary_tone": "calm nature",
    }


def ready_scene(client):
    project = client.post("/api/projects", json=project_payload()).json()
    research = client.post(f"/api/projects/{project['id']}/research/generate").json()
    client.post(f"/api/research/facts/{research['facts'][0]['id']}/approve")
    script = client.post(f"/api/projects/{project['id']}/script/generate").json()["current"]
    client.post(f"/api/scripts/{script['id']}/approve")
    scene = client.post(f"/api/projects/{project['id']}/scenes/generate").json()["scenes"][0]
    return project, scene


def test_short_query_generation():
    scene = SimpleNamespace(
        species="Snow leopard",
        environment="High Himalayan alpine terrain with cold dry air",
        animal_behavior="Walking carefully across a rocky ridge",
        shot_type="close-up tracking shot",
    )
    queries = build_stock_queries(scene)
    assert queries[0] == "snow leopard"
    assert 2 <= len(queries) <= 4
    assert all(len(query.split()) <= 6 for query in queries)


def test_transparent_ranking_prefers_landscape_1080p():
    scene = SimpleNamespace(
        species="Snow leopard",
        environment="Himalayan mountain",
        animal_behavior="walking ridge",
        target_duration=7,
    )
    landscape = {
        "width": 1920,
        "height": 1080,
        "duration": 10,
        "metadata_json": {"title": "snow leopard walking Himalayan mountain ridge"},
    }
    portrait = {
        "width": 1080,
        "height": 1920,
        "duration": 3,
        "metadata_json": {"title": "snow leopard"},
    }
    landscape_score, breakdown = score_candidate(scene, landscape)
    portrait_score, _ = score_candidate(scene, portrait)
    assert landscape_score > portrait_score
    assert set(breakdown) == {"keyword", "landscape", "resolution", "duration"}


def test_mock_search_deduplicates_ranks_and_preserves_license(client):
    _, scene = ready_scene(client)
    response = client.post(f"/api/scenes/{scene['id']}/stock/search")
    assert response.status_code == 200
    body = response.json()
    assert body["is_mock"] is True
    assert len(body["queries"]) >= 2
    provider_ids = [asset["provider_asset_id"] for asset in body["assets"]]
    assert len(provider_ids) == len(set(provider_ids))
    assert provider_ids.count("shared-landscape-001") == 1
    assert body["assets"] == sorted(
        body["assets"], key=lambda asset: (-asset["relevance_score"], asset["id"])
    )
    assert all(asset["license"] is None for asset in body["assets"])
    assert all(
        "confirm provider terms" in asset["attribution_requirements"] for asset in body["assets"]
    )
    assert "score_breakdown" in body["assets"][0]["metadata_json"]


def test_select_reject_and_search_again_are_idempotent(client):
    _, scene = ready_scene(client)
    first = client.post(f"/api/scenes/{scene['id']}/stock/search").json()
    asset = first["assets"][0]
    selected = client.post(f"/api/media-assets/{asset['id']}/select")
    assert selected.status_code == 200
    assert selected.json()["status"] == "SELECTED"
    current = client.get(f"/api/scenes/{scene['id']}/stock").json()
    assert current["selected_asset_id"] == asset["id"]

    again = client.post(f"/api/scenes/{scene['id']}/stock/search").json()
    assert len(again["assets"]) == len(first["assets"])
    assert again["selected_asset_id"] == asset["id"]

    rejected = client.post(f"/api/media-assets/{asset['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert client.get(f"/api/scenes/{scene['id']}/stock").json()["selected_asset_id"] is None


def test_provider_failure_preserves_existing_candidates(client):
    _, scene = ready_scene(client)
    initial = client.post(f"/api/scenes/{scene['id']}/stock/search").json()
    initial_ids = [asset["id"] for asset in initial["assets"]]
    client.patch(f"/api/scenes/{scene['id']}", json={"species": "__fail__"})
    failed = client.post(f"/api/scenes/{scene['id']}/stock/search")
    assert failed.status_code == 502
    preserved = client.get(f"/api/scenes/{scene['id']}/stock").json()
    assert [asset["id"] for asset in preserved["assets"]] == initial_ids
