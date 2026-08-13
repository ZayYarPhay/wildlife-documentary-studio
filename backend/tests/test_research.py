def project_payload(topic="Snow leopard"):
    return {
        "title": "Wildlife Research",
        "animal_topic": topic,
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": 300,
        "output_resolution": "1920x1080",
    }


def create_project(client, topic="Snow leopard"):
    response = client.post("/api/projects", json=project_payload(topic))
    assert response.status_code == 201
    return response.json()


def test_generate_deduplicates_and_links_sources(client):
    project = create_project(client)
    response = client.post(f"/api/projects/{project['id']}/research/generate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review"
    assert body["is_mock"] is True
    assert len(body["facts"]) == 2
    assert all(fact["source"]["url"].startswith("https://") for fact in body["facts"])

    retry = client.post(f"/api/projects/{project['id']}/research/generate")
    assert retry.status_code == 200
    assert len(retry.json()["facts"]) == 2


def test_fact_review_actions(client):
    project = create_project(client)
    facts = client.post(f"/api/projects/{project['id']}/research/generate").json()["facts"]
    fact_id = facts[0]["id"]

    edited = client.patch(
        f"/api/research/facts/{fact_id}",
        json={"claim": "Reviewer-edited claim", "confidence": 0.8, "notes": "Checked"},
    )
    assert edited.status_code == 200
    assert edited.json()["claim"] == "Reviewer-edited claim"

    approved = client.post(f"/api/research/facts/{fact_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["approved"] is True

    assert client.delete(f"/api/research/facts/{fact_id}").status_code == 204
    remaining = client.get(f"/api/projects/{project['id']}/research").json()["facts"]
    assert len(remaining) == 1


def test_provider_failure_preserves_previous_research(client):
    project = create_project(client)
    generated = client.post(f"/api/projects/{project['id']}/research/generate")
    assert generated.status_code == 200
    original_ids = [fact["id"] for fact in generated.json()["facts"]]

    client.patch(f"/api/projects/{project['id']}", json={"animal_topic": "__fail__"})
    failed = client.post(f"/api/projects/{project['id']}/research/generate")
    assert failed.status_code == 502

    preserved = client.get(f"/api/projects/{project['id']}/research")
    assert [fact["id"] for fact in preserved.json()["facts"]] == original_ids


def test_research_requires_topic(client):
    project = create_project(client)
    client.patch(
        f"/api/projects/{project['id']}",
        json={"auto_topic": True, "animal_topic": None},
    )
    response = client.post(f"/api/projects/{project['id']}/research/generate")
    assert response.status_code == 422
