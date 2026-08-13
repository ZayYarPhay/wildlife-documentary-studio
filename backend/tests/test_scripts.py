import asyncio
import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.project import Project
from app.models.research import ResearchFact, ResearchSource
from app.models.script import Script
from app.providers.base import LLMProvider
from app.services.llm import ScriptOrchestrator, estimate_duration_seconds, target_word_range


def project_payload(duration=300):
    return {
        "title": f"Documentary {duration}",
        "animal_topic": "Snow leopard",
        "auto_topic": False,
        "language": "English",
        "requested_duration_seconds": duration,
        "output_resolution": "1920x1080",
        "documentary_tone": "calm nature",
    }


def project_with_research(client, duration=300):
    project = client.post("/api/projects", json=project_payload(duration)).json()
    facts = client.post(f"/api/projects/{project['id']}/research/generate").json()["facts"]
    client.post(f"/api/research/facts/{facts[0]['id']}/approve")
    return project, facts


def test_duration_estimation_and_range():
    assert estimate_duration_seconds("one two three four", 120) == 2
    assert target_word_range(120, 140, 0.15) == (238, 322)


def test_only_approved_facts_generate_script(client):
    project, facts = project_with_research(client)
    response = client.post(f"/api/projects/{project['id']}/script/generate")
    assert response.status_code == 200
    script = response.json()["current"]
    approved_id = facts[0]["id"]
    unapproved_id = facts[1]["id"]
    assert script["sections"]
    assert all(section["source_fact_ids"] == [approved_id] for section in script["sections"])
    assert all(unapproved_id not in section["source_fact_ids"] for section in script["sections"])


def test_versioning_order_edit_and_approve(client):
    project, _ = project_with_research(client)
    first = client.post(f"/api/projects/{project['id']}/script/generate").json()["current"]
    second_bundle = client.post(f"/api/projects/{project['id']}/script/generate").json()
    second = second_bundle["current"]
    assert first["version"] == 1
    assert second["version"] == 2
    assert [item["version"] for item in second_bundle["versions"]] == [2, 1]
    assert [section["order"] for section in second["sections"]] == list(
        range(1, len(second["sections"]) + 1)
    )

    section_id = second["sections"][0]["id"]
    edited = client.patch(
        f"/api/script-sections/{section_id}",
        json={"title": "New opening", "text": "Edited narration text."},
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "New opening"

    expanded = client.post(f"/api/script-sections/{section_id}/regenerate", json={"mode": "expand"})
    assert expanded.status_code == 200
    assert len(expanded.json()["text"]) > len("Edited narration text.")

    approved = client.post(f"/api/scripts/{second['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["approved"] is True

    full_text = client.get(f"/api/projects/{project['id']}/script").json()["current"]["full_text"]
    saved = client.patch(f"/api/scripts/{second['id']}", json={"full_text": full_text + " revised"})
    assert saved.status_code == 200
    assert saved.json()["sections"][-1]["text"].endswith("revised")


def test_two_minute_script_is_shorter_than_fifteen_minute_script(client):
    short_project, _ = project_with_research(client, 120)
    long_project, _ = project_with_research(client, 900)
    short_script = client.post(f"/api/projects/{short_project['id']}/script/generate").json()[
        "current"
    ]
    long_script = client.post(f"/api/projects/{long_project['id']}/script/generate").json()[
        "current"
    ]
    assert short_script["estimated_words"] < long_script["estimated_words"]
    assert long_script["estimated_words"] >= short_script["estimated_words"] * 5


def test_script_requires_approved_research(client):
    project = client.post("/api/projects", json=project_payload()).json()
    client.post(f"/api/projects/{project['id']}/research/generate")
    response = client.post(f"/api/projects/{project['id']}/script/generate")
    assert response.status_code == 422


class FailingProvider(LLMProvider):
    name = "failing"

    async def health(self):
        return {"status": "failed"}

    async def generate(self, prompt: str, **options):
        raise RuntimeError("provider unavailable")


class CapturingProvider(LLMProvider):
    name = "capturing"

    def __init__(self):
        self.facts = []

    async def health(self):
        return {"status": "ok"}

    async def generate(self, prompt: str, **options):
        self.facts = options["facts"]
        fact = self.facts[0]
        return json.dumps(
            {
                "sections": [
                    {
                        "title": "Verified",
                        "text": fact["claim"],
                        "source_fact_ids": [fact["id"]],
                    }
                ]
            }
        )


def test_orchestrator_passes_only_approved_and_failure_preserves_script(client):
    project_data, _ = project_with_research(client)
    db = SessionLocal()
    try:
        project = db.get(Project, project_data["id"])
        source = db.scalar(select(ResearchSource).where(ResearchSource.project_id == project.id))
        db.add(
            ResearchFact(
                project_id=project.id,
                source_id=source.id,
                category="hidden",
                claim="This unapproved claim must never reach the provider.",
                normalized_claim="this unapproved claim must never reach the provider.",
                confidence=0.9,
                approved=False,
            )
        )
        db.commit()

        capturing = CapturingProvider()
        asyncio.run(ScriptOrchestrator(provider=capturing).generate(project, db))
        assert len(capturing.facts) == 1
        existing_id = db.scalar(select(Script.id).where(Script.project_id == project.id))

        try:
            asyncio.run(ScriptOrchestrator(provider=FailingProvider()).generate(project, db))
        except RuntimeError:
            pass
        assert db.get(Script, existing_id) is not None
        assert db.scalar(select(Script).where(Script.project_id == project.id)).id == existing_id
    finally:
        db.close()
