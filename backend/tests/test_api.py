def payload(**overrides):
    data = {
        "title": "Snow Leopard",
        "animal_topic": "Snow leopard",
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": 300,
        "output_resolution": "1920x1080",
    }
    data.update(overrides)
    return data


def test_health_reports_media_tools(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "ffmpeg" in response.json()["media_tools"]


def test_project_crud(client):
    created = client.post("/api/projects", json=payload())
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert len(client.get("/api/projects").json()) == 1
    fetched = client.get(f"/api/projects/{project_id}")
    assert fetched.json()["animal_topic"] == "Snow leopard"

    updated = client.patch(f"/api/projects/{project_id}", json={"title": "Ghost of the Mountains"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Ghost of the Mountains"

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_duration_bounds(client):
    assert (
        client.post("/api/projects", json=payload(requested_duration_seconds=119)).status_code
        == 422
    )
    assert (
        client.post("/api/projects", json=payload(requested_duration_seconds=901)).status_code
        == 422
    )


def test_topic_required_unless_auto(client):
    assert client.post("/api/projects", json=payload(animal_topic=None)).status_code == 422
    response = client.post("/api/projects", json=payload(animal_topic=None, auto_topic=True))
    assert response.status_code == 201
