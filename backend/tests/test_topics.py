from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.project import Project


def project_payload(topic: str) -> dict:
    return {
        "title": f"Documentary: {topic}",
        "animal_topic": topic,
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": 300,
        "output_resolution": "1920x1080",
        "documentary_tone": "cinematic wildlife documentary",
    }


def test_categories_and_structured_suggestions_do_not_start_work(client):
    categories = client.get("/api/topics/categories")
    assert categories.status_code == 200
    assert {item["value"] for item in categories.json()} == {
        "MAMMALS",
        "BIRDS",
        "REPTILES",
        "OCEAN",
        "INSECTS",
        "RARE_ANIMALS",
        "PREDATORS",
    }
    response = client.post(
        "/api/topics/suggest",
        json={
            "category": "OCEAN",
            "count": 3,
            "duration_seconds": 600,
            "visual_preference": "BALANCED",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock" and body["is_mock"] is True
    assert len(body["suggestions"]) == 3
    first = body["suggestions"][0]
    assert first["category"] == "OCEAN"
    assert first["stock_availability"] in {"HIGH", "MEDIUM", "LOW"}
    assert first["production_difficulty"] in {"EASY", "MEDIUM", "HARD"}
    assert sum(first["recommended_visual_mix"].values()) == 100
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(Project.id))) == 0
        assert db.scalar(select(func.count(GenerationJob.id))) == 0
    finally:
        db.close()


def test_recent_topics_are_avoided_and_disclosed(client):
    client.post("/api/projects", json=project_payload("Snow leopard"))
    response = client.post(
        "/api/topics/suggest",
        json={"category": "PREDATORS", "count": 4, "duration_seconds": 300},
    )
    body = response.json()
    assert response.status_code == 200
    assert "Snow leopard" in body["excluded_recent_topics"]
    topics = [item["topic"] for item in body["suggestions"]]
    assert topics[-1] == "Snow leopard"
    assert body["suggestions"][-1]["recently_used"] is True
    assert all(item["recently_used"] is False for item in body["suggestions"][:-1])


def test_surprise_respects_category_and_difficulty_context(client):
    response = client.post(
        "/api/topics/surprise",
        json={
            "category": "RARE_ANIMALS",
            "duration_seconds": 900,
            "visual_preference": "ECONOMY",
        },
    )
    assert response.status_code == 200
    suggestion = response.json()["suggestions"][0]
    assert suggestion["category"] == "RARE_ANIMALS"
    assert suggestion["production_difficulty"] == "HARD"
    assert suggestion["recommended_visual_mix"]["ai_video"] == 5


def test_topic_request_validation(client):
    unknown = client.post("/api/topics/suggest", json={"category": "DINOSAURS"})
    assert unknown.status_code == 422
    too_many = client.post("/api/topics/suggest", json={"category": "BIRDS", "count": 20})
    assert too_many.status_code == 422
    expensive_without_preferences = client.post(
        "/api/topics/surprise", json={"duration_seconds": 901}
    )
    assert expensive_without_preferences.status_code == 422
