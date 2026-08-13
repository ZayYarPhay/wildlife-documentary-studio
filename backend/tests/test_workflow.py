from sqlalchemy import delete, func, select
from test_api import payload
from test_timeline import timeline_project
from test_voice import wav_bytes

from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.project import Project
from app.models.scene import Scene
from app.models.voice import VoiceTrack
from app.models.workflow import WorkflowMode, WorkflowRunStatus, WorkflowStepStatus
from app.schemas.workflow import WorkflowPolicy
from app.services.llm import ScriptOrchestrator
from app.services.workflow import create_workflow_run, recover_interrupted_workflows, request_pause


def test_manual_pipeline_pauses_for_each_major_review_and_is_idempotent(client):
    project = client.post("/api/projects", json=payload()).json()
    started = client.post(
        f"/api/projects/{project['id']}/workflow/start", json={"mode": "MANUAL"}
    )
    assert started.status_code == 202
    current = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert current["status"] == "PAUSED"
    assert current["current_step"] == "RESEARCH"
    assert current["steps"][0]["status"] == "WAITING"

    duplicate = client.post(
        f"/api/projects/{project['id']}/workflow/start", json={"mode": "AUTO"}
    )
    assert duplicate.json()["id"] == current["id"]
    history = client.get(f"/api/projects/{project['id']}/workflow").json()["runs"]
    assert len(history) == 1

    fact = client.get(f"/api/projects/{project['id']}/research").json()["facts"][0]
    client.post(f"/api/research/facts/{fact['id']}/approve")
    client.post(f"/api/workflows/{current['id']}/resume")
    current = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert current["status"] == "PAUSED"
    assert current["current_step"] == "SCRIPT"
    assert current["steps"][0]["status"] == "COMPLETED"
    assert current["steps"][1]["status"] == "WAITING"

    script = client.get(f"/api/projects/{project['id']}/script").json()["current"]
    client.post(f"/api/scripts/{script['id']}/approve")
    client.post(f"/api/workflows/{current['id']}/resume")
    current = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert current["current_step"] == "SCENES"
    assert current["status"] == "PAUSED"
    assert current["progress"] == 20


def test_auto_pipeline_waits_for_voice_then_upload_resumes_to_render_ready(client):
    project, _, old_track = timeline_project(client)
    db = SessionLocal()
    try:
        db.execute(delete(VoiceTrack).where(VoiceTrack.id == old_track["id"]))
        db.commit()
    finally:
        db.close()

    client.post(
        f"/api/projects/{project['id']}/workflow/start",
        json={"mode": "AUTO", "policy": {"generate_ai_video": False}},
    )
    waiting = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert waiting["status"] == "VOICE_WAITING"
    assert waiting["current_step"] == "VOICE"
    assert waiting["progress"] == 70

    uploaded = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("resume.wav", wav_bytes(), "audio/wav")},
    )
    assert uploaded.status_code == 202
    completed = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert completed["status"] == "RENDER_READY"
    assert completed["progress"] == 100
    assert all(step["status"] == "COMPLETED" for step in completed["steps"])
    timeline = client.get(f"/api/projects/{project['id']}/timeline").json()["current"]
    assert timeline["valid"] is True
    assert "subtitles" in timeline["render_plan_json"]
    assert "audio_mix" in timeline["render_plan_json"]


def test_one_click_auto_builds_fresh_project_to_voice_waiting_without_duplicates(client):
    project = client.post("/api/projects", json=payload()).json()
    response = client.post(
        f"/api/projects/{project['id']}/workflow/start",
        json={"mode": "AUTO", "policy": {"generate_ai_video": False}},
    )
    assert response.status_code == 202
    waiting = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert waiting["status"] == "VOICE_WAITING"
    assert waiting["progress"] == 70
    assert [step["status"] for step in waiting["steps"][:6]] == ["COMPLETED"] * 6
    db = SessionLocal()
    try:
        scenes = list(db.scalars(select(Scene).where(Scene.project_id == project["id"])))
        assert scenes
        assert all(scene.preferred_media_asset_id is not None for scene in scenes)
        job_count = db.scalar(
            select(func.count(GenerationJob.id)).where(GenerationJob.project_id == project["id"])
        )
    finally:
        db.close()
    duplicate = client.post(
        f"/api/projects/{project['id']}/workflow/start", json={"mode": "AUTO"}
    )
    assert duplicate.json()["id"] == waiting["id"]
    db = SessionLocal()
    try:
        assert db.scalar(
            select(func.count(GenerationJob.id)).where(GenerationJob.project_id == project["id"])
        ) == job_count
    finally:
        db.close()


def test_failed_step_retries_without_repeating_completed_research(client, monkeypatch):
    project = client.post("/api/projects", json=payload()).json()
    original = ScriptOrchestrator.generate

    async def fail_script(*_args, **_kwargs):
        raise RuntimeError("synthetic script provider failure")

    monkeypatch.setattr(ScriptOrchestrator, "generate", fail_script)
    client.post(
        f"/api/projects/{project['id']}/workflow/start",
        json={
            "mode": "AUTO",
            "policy": {"auto_approve_script": False, "generate_ai_video": False},
        },
    )
    failed = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert failed["status"] == "FAILED"
    assert failed["current_step"] == "SCRIPT"
    assert "synthetic" in failed["error_message"]
    assert failed["steps"][0]["attempts"] == 1

    monkeypatch.setattr(ScriptOrchestrator, "generate", original)
    client.post(f"/api/workflows/{failed['id']}/retry")
    retried = client.get(f"/api/projects/{project['id']}/workflow").json()["current"]
    assert retried["status"] == "PAUSED"
    assert retried["current_step"] == "SCRIPT"
    assert retried["steps"][0]["attempts"] == 1
    assert retried["steps"][1]["attempts"] == 2
    db = SessionLocal()
    try:
        research_jobs = db.scalar(
            select(func.count(GenerationJob.id))
            .where(
                GenerationJob.project_id == project["id"],
                GenerationJob.job_type == "RESEARCH",
            )
        )
        assert research_jobs == 1
    finally:
        db.close()


def test_pending_workflow_can_pause_before_execution(client):
    project_data = client.post("/api/projects", json=payload()).json()
    db = SessionLocal()
    try:
        project = db.get(Project, project_data["id"])
        run = create_workflow_run(project, WorkflowMode.AUTO, WorkflowPolicy(), db)
        paused = request_pause(run, db)
        assert paused.status == WorkflowRunStatus.PAUSED
        assert paused.current_operation == "Paused before execution"
    finally:
        db.close()


def test_interrupted_running_workflow_recovers_as_resumable(client):
    project_data = client.post("/api/projects", json=payload()).json()
    db = SessionLocal()
    try:
        project = db.get(Project, project_data["id"])
        run = create_workflow_run(project, WorkflowMode.AUTO, WorkflowPolicy(), db)
        run.status = WorkflowRunStatus.RUNNING
        run.current_step = "RESEARCH"
        run.steps[0].status = WorkflowStepStatus.RUNNING
        db.commit()
        assert recover_interrupted_workflows(db) == 1
        db.refresh(run)
        assert run.status == WorkflowRunStatus.PAUSED
        assert run.steps[0].status == WorkflowStepStatus.PENDING
        assert "resume" in run.current_operation.lower()
    finally:
        db.close()
