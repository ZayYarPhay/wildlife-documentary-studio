from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.research import ResearchFact
from app.models.scene import Scene, ScenePrompt, VisualStrategy
from app.models.script import Script
from app.models.timeline import Timeline
from app.models.voice import VoiceTrack, VoiceTrackStatus
from app.models.workflow import (
    WorkflowMode,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepStatus,
)
from app.schemas.workflow import WorkflowPolicy
from app.services.audio import apply_audio_to_timeline
from app.services.image_generation import run_image_job, submit_image_job
from app.services.llm import ScriptOrchestrator
from app.services.research import ResearchOrchestrator
from app.services.scene_planner import ScenePlanner
from app.services.stock_media import StockMediaService
from app.services.timeline import build_timeline
from app.services.video_generation import run_video_job, submit_video_job
from app.services.voice import apply_voice_timing

STEP_DEFINITIONS = [
    ("RESEARCH", 10.0, "Collect source-backed research"),
    ("SCRIPT", 20.0, "Prepare documentary narration"),
    ("SCENES", 30.0, "Build the scene plan"),
    ("MEDIA", 45.0, "Search and select stock candidates"),
    ("IMAGES", 60.0, "Generate required image assets"),
    ("VIDEOS", 70.0, "Generate selected AI video clips"),
    ("VOICE", 75.0, "Wait for and align voice-over"),
    ("TIMELINE", 85.0, "Assemble the deterministic timeline"),
    ("AUDIO", 95.0, "Prepare subtitles and audio mix"),
    ("RENDER_READY", 100.0, "Validate render-ready state"),
]


@dataclass
class StepOutcome:
    state: str = "COMPLETED"
    operation: str | None = None
    metadata: dict | None = None


def create_workflow_run(
    project: Project, mode: WorkflowMode, policy: WorkflowPolicy, db: Session
) -> WorkflowRun:
    active = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project.id, WorkflowRun.active_key == "ACTIVE")
        .options(selectinload(WorkflowRun.steps))
    )
    if active is not None:
        return active
    run = WorkflowRun(
        project_id=project.id,
        mode=mode,
        status=WorkflowRunStatus.PENDING,
        active_key="ACTIVE",
        current_operation="Queued",
        progress=0,
        policy_json=policy.model_dump(),
    )
    db.add(run)
    db.flush()
    for order, (name, _, operation) in enumerate(STEP_DEFINITIONS, 1):
        db.add(
            WorkflowStep(
                workflow_run_id=run.id,
                name=name,
                order=order,
                status=WorkflowStepStatus.PENDING,
                progress=0,
                operation=operation,
            )
        )
    project.status = ProjectStatus.WORKFLOW_RUNNING
    project.current_phase = ProjectPhase.WORKFLOW
    db.commit()
    return load_workflow_run(run.id, db)


def load_workflow_run(run_id: int, db: Session) -> WorkflowRun:
    run = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.steps))
    )
    if run is None:
        raise ValueError("Workflow run not found")
    return run


def workflow_runs(project_id: int, db: Session) -> list[WorkflowRun]:
    return list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project_id)
            .options(selectinload(WorkflowRun.steps))
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        )
    )


def recover_interrupted_workflows(db: Session) -> int:
    runs = list(
        db.scalars(
            select(WorkflowRun).where(
                WorkflowRun.active_key == "ACTIVE",
                WorkflowRun.status.in_([WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING]),
            )
        )
    )
    for run in runs:
        run.status = WorkflowRunStatus.PAUSED
        run.pause_requested = False
        run.current_job_id = None
        run.current_operation = "Previous process stopped; resume from the saved step"
        for step in run.steps:
            if step.status == WorkflowStepStatus.RUNNING:
                step.status = WorkflowStepStatus.PENDING
                step.operation = "Interrupted before completion; safe to resume"
        project = db.get(Project, run.project_id)
        if project:
            project.status = ProjectStatus.PIPELINE_PAUSED
            project.current_phase = ProjectPhase.WORKFLOW
    db.commit()
    return len(runs)


async def run_workflow(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = load_workflow_run(run_id, db)
        if run.status != WorkflowRunStatus.PENDING:
            return
        run.status = WorkflowRunStatus.RUNNING
        run.pause_requested = False
        run.error_message = None
        project = db.get(Project, run.project_id)
        if project is None:
            raise RuntimeError("Workflow project no longer exists")
        project.status = ProjectStatus.WORKFLOW_RUNNING
        project.current_phase = ProjectPhase.WORKFLOW
        db.commit()
        engine = ProjectWorkflow(run, project, db)
        for name, target_progress, default_operation in STEP_DEFINITIONS:
            db.expire_all()
            run = load_workflow_run(run_id, db)
            project = db.get(Project, run.project_id)
            step = next(item for item in run.steps if item.name == name)
            if step.status in {WorkflowStepStatus.COMPLETED, WorkflowStepStatus.SKIPPED}:
                continue
            if run.status == WorkflowRunStatus.CANCELED:
                return
            if run.pause_requested:
                _pause(run, project, "Paused at a safe step boundary", db)
                return
            step.status = WorkflowStepStatus.RUNNING
            step.attempts += 1
            step.started_at = step.started_at or datetime.now(UTC)
            step.error_message = None
            step.operation = default_operation
            run.current_step = name
            run.current_operation = default_operation
            run.status = WorkflowRunStatus.RUNNING
            project.status = ProjectStatus.WORKFLOW_RUNNING
            project.current_phase = ProjectPhase.WORKFLOW
            db.commit()
            try:
                outcome = await engine.execute(name)
            except Exception as exc:  # noqa: BLE001 - step diagnostics must persist for retry
                db.rollback()
                run = load_workflow_run(run_id, db)
                project = db.get(Project, run.project_id)
                step = next(item for item in run.steps if item.name == name)
                step.status = WorkflowStepStatus.FAILED
                step.error_message = str(exc)
                step.operation = f"Failed: {exc}"
                step.finished_at = datetime.now(UTC)
                run.status = WorkflowRunStatus.FAILED
                run.error_message = str(exc)
                run.current_operation = f"{name} failed"
                project.status = ProjectStatus.FAILED
                project.current_phase = ProjectPhase.WORKFLOW
                db.commit()
                return
            db.expire_all()
            run = load_workflow_run(run_id, db)
            project = db.get(Project, run.project_id)
            step = next(item for item in run.steps if item.name == name)
            step.operation = outcome.operation or default_operation
            step.metadata_json = outcome.metadata or {}
            if outcome.state in {"WAITING", "VOICE_WAITING"}:
                run.current_job_id = None
                step.status = WorkflowStepStatus.WAITING
                step.progress = 0.5
                run.status = (
                    WorkflowRunStatus.VOICE_WAITING
                    if outcome.state == "VOICE_WAITING"
                    else WorkflowRunStatus.PAUSED
                )
                run.current_operation = step.operation
                project.status = (
                    ProjectStatus.VOICE_WAITING
                    if outcome.state == "VOICE_WAITING"
                    else ProjectStatus.PIPELINE_PAUSED
                )
                project.current_phase = ProjectPhase.WORKFLOW
                db.commit()
                return
            step.status = WorkflowStepStatus.COMPLETED
            run.current_job_id = None
            step.progress = 1
            step.finished_at = datetime.now(UTC)
            run.progress = target_progress
            run.current_operation = step.operation
            project.status = ProjectStatus.WORKFLOW_RUNNING
            project.current_phase = ProjectPhase.WORKFLOW
            db.commit()
            db.refresh(run)
            if run.status == WorkflowRunStatus.CANCELED:
                return
            if run.pause_requested:
                _pause(run, project, "Paused at a safe step boundary", db)
                return
        run = load_workflow_run(run_id, db)
        project = db.get(Project, run.project_id)
        run.status = WorkflowRunStatus.RENDER_READY
        run.progress = 100
        run.current_step = "RENDER_READY"
        run.current_operation = "Project is ready for the future final-render phase"
        run.current_job_id = None
        run.active_key = None
        run.finished_at = datetime.now(UTC)
        project.status = ProjectStatus.RENDER_READY
        project.current_phase = ProjectPhase.RENDER_READY
        db.commit()
    finally:
        db.close()


async def resume_waiting_workflow(project_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.scalar(
            select(WorkflowRun).where(
                WorkflowRun.project_id == project_id,
                WorkflowRun.active_key == "ACTIVE",
                WorkflowRun.mode == WorkflowMode.AUTO,
                WorkflowRun.status == WorkflowRunStatus.VOICE_WAITING,
            )
        )
        if run:
            run.status = WorkflowRunStatus.PENDING
            run.pause_requested = False
            run.current_operation = "Voice transcription completed; resuming AUTO pipeline"
            db.commit()
        run_id = run.id if run else None
    finally:
        db.close()
    if run_id is not None:
        await run_workflow(run_id)


def request_pause(run: WorkflowRun, db: Session) -> WorkflowRun:
    if run.status not in {WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING}:
        raise ValueError("Only pending or running workflows can be paused")
    if run.status == WorkflowRunStatus.PENDING:
        run.status = WorkflowRunStatus.PAUSED
        run.current_operation = "Paused before execution"
    else:
        run.pause_requested = True
        run.current_operation = "Pause requested; waiting for a safe step boundary"
    db.commit()
    return load_workflow_run(run.id, db)


def prepare_resume(run: WorkflowRun, db: Session) -> WorkflowRun:
    if run.status not in {WorkflowRunStatus.PAUSED, WorkflowRunStatus.VOICE_WAITING}:
        raise ValueError("Only paused or voice-waiting workflows can resume")
    run.status = WorkflowRunStatus.PENDING
    run.pause_requested = False
    run.error_message = None
    db.commit()
    return load_workflow_run(run.id, db)


def prepare_retry(run: WorkflowRun, db: Session) -> WorkflowRun:
    if run.status != WorkflowRunStatus.FAILED:
        raise ValueError("Only failed workflows can retry")
    failed = next((step for step in run.steps if step.status == WorkflowStepStatus.FAILED), None)
    if failed is None:
        raise ValueError("Workflow has no failed step to retry")
    failed.status = WorkflowStepStatus.PENDING
    failed.progress = 0
    failed.error_message = None
    run.status = WorkflowRunStatus.PENDING
    run.error_message = None
    run.current_operation = f"Retrying {failed.name}"
    db.commit()
    return load_workflow_run(run.id, db)


def cancel_workflow(run: WorkflowRun, db: Session) -> WorkflowRun:
    if run.status in {WorkflowRunStatus.RENDER_READY, WorkflowRunStatus.CANCELED}:
        raise ValueError("Workflow is already finished")
    run.status = WorkflowRunStatus.CANCELED
    run.active_key = None
    run.pause_requested = True
    run.current_operation = "Canceled by user"
    run.finished_at = datetime.now(UTC)
    project = db.get(Project, run.project_id)
    if project:
        project.status = ProjectStatus.PIPELINE_PAUSED
        project.current_phase = ProjectPhase.WORKFLOW
    db.commit()
    return load_workflow_run(run.id, db)


def _pause(run: WorkflowRun, project: Project, operation: str, db: Session) -> None:
    run.status = WorkflowRunStatus.PAUSED
    run.current_operation = operation
    project.status = ProjectStatus.PIPELINE_PAUSED
    project.current_phase = ProjectPhase.WORKFLOW
    db.commit()


class ProjectWorkflow:
    def __init__(self, run: WorkflowRun, project: Project, db: Session):
        self.run = run
        self.project = project
        self.db = db
        self.policy = WorkflowPolicy.model_validate(run.policy_json)

    async def execute(self, name: str) -> StepOutcome:
        return await getattr(self, f"_{name.lower()}")()

    async def _research(self) -> StepOutcome:
        facts = list(
            self.db.scalars(select(ResearchFact).where(ResearchFact.project_id == self.project.id))
        )
        generated = False
        if not facts:
            await ResearchOrchestrator().generate(self.project, self.db)
            facts = list(
                self.db.scalars(
                    select(ResearchFact).where(ResearchFact.project_id == self.project.id)
                )
            )
            generated = True
        approved = [fact for fact in facts if fact.approved]
        auto_approve = self.run.mode == WorkflowMode.AUTO and self.policy.auto_approve_research
        if not approved and auto_approve:
            for fact in facts:
                fact.approved = True
            self.db.commit()
            approved = facts
        if not approved:
            return StepOutcome("WAITING", "Review and approve at least one sourced research fact")
        if self.run.mode == WorkflowMode.MANUAL and generated:
            return StepOutcome("WAITING", "Research generated; review approved facts, then resume")
        return StepOutcome(operation=f"Using {len(approved)} approved research facts")

    async def _script(self) -> StepOutcome:
        latest = self.db.scalar(
            select(Script)
            .where(Script.project_id == self.project.id)
            .order_by(Script.version.desc())
        )
        generated = False
        if latest is None:
            latest = (await ScriptOrchestrator().generate(self.project, self.db)).script
            generated = True
        if not latest.approved and self.run.mode == WorkflowMode.AUTO and self.policy.auto_approve_script:
            self.db.execute(
                update(Script).where(Script.project_id == self.project.id).values(approved=False)
            )
            latest.approved = True
            self.db.commit()
        if not latest.approved:
            return StepOutcome("WAITING", "Review and approve the current script, then resume")
        if self.run.mode == WorkflowMode.MANUAL and generated:
            return StepOutcome("WAITING", "Script generated; review and approve it, then resume")
        return StepOutcome(operation=f"Using approved script version {latest.version}")

    async def _scenes(self) -> StepOutcome:
        scenes = self._scenes_list()
        if scenes:
            return StepOutcome(operation=f"Preserving {len(scenes)} existing scenes")
        result = ScenePlanner().generate(self.project, self.db)
        if self.run.mode == WorkflowMode.MANUAL:
            return StepOutcome("WAITING", "Scene plan generated; review it, then resume")
        return StepOutcome(operation=f"Generated {len(result.scenes)} scenes")

    async def _media(self) -> StepOutcome:
        searched = 0
        missing_manual = []
        for scene in self._scenes_list():
            preferred = self._preferred(scene)
            if preferred is not None:
                continue
            candidates = list(
                self.db.scalars(
                    select(MediaAsset).where(
                        MediaAsset.scene_id == scene.id,
                        MediaAsset.type.in_([MediaAssetType.STOCK_VIDEO, MediaAssetType.STOCK_IMAGE]),
                    )
                )
            )
            if not candidates:
                result = await StockMediaService().search(scene, self.db)
                candidates = result.assets
                searched += 1
            if scene.visual_strategy != VisualStrategy.STOCK_VIDEO:
                continue
            if self.run.mode == WorkflowMode.AUTO and self.policy.auto_select_media:
                local = next(
                    (asset for asset in candidates if asset.local_path and Path(asset.local_path).is_file()),
                    None,
                )
                if local:
                    StockMediaService.select_asset(local, scene, self.db)
                elif self.policy.fallback_missing_stock_to_image:
                    scene.visual_strategy = VisualStrategy.AI_IMAGE_MOTION
                    self.db.commit()
                else:
                    raise RuntimeError(f"Scene {scene.order} has no local stock asset")
            else:
                missing_manual.append(scene.order)
        if missing_manual:
            return StepOutcome(
                "WAITING",
                f"Select stock media for scenes {', '.join(map(str, missing_manual))}, then resume",
            )
        return StepOutcome(operation=f"Stock search complete; {searched} scenes searched")

    async def _images(self) -> StepOutcome:
        generated = 0
        job_ids = []
        waiting = []
        for scene in self._scenes_list():
            preferred = self._preferred(scene)
            if preferred and preferred.local_path and Path(preferred.local_path).is_file():
                if scene.visual_strategy != VisualStrategy.AI_VIDEO or preferred.type != MediaAssetType.AI_IMAGE:
                    continue
                continue
            candidate = self.db.scalar(
                select(MediaAsset)
                .where(
                    MediaAsset.scene_id == scene.id,
                    MediaAsset.type == MediaAssetType.AI_IMAGE,
                    MediaAsset.status != MediaAssetStatus.REJECTED,
                )
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
            )
            if candidate and candidate.local_path and Path(candidate.local_path).is_file():
                if self.run.mode == WorkflowMode.AUTO:
                    StockMediaService.select_asset(candidate, scene, self.db)
                else:
                    waiting.append(scene.order)
                continue
            if scene.visual_strategy not in {VisualStrategy.AI_IMAGE_MOTION, VisualStrategy.AI_VIDEO}:
                waiting.append(scene.order)
                continue
            prompt = self.db.scalar(
                select(ScenePrompt)
                .where(ScenePrompt.scene_id == scene.id)
                .order_by(ScenePrompt.version.desc())
            )
            if prompt is None:
                raise RuntimeError(f"Scene {scene.order} has no image prompt")
            latest_job = self._latest_job(scene.id, "AI_IMAGE")
            retry_count = latest_job.retry_count + 1 if latest_job and latest_job.status == "FAILED" else 0
            job = submit_image_job(scene, prompt, self.db, retry_count=retry_count)
            job_ids.append(job.id)
            self.run.current_job_id = job.id
            self.run.current_operation = f"Generating image for scene {scene.order}"
            self.db.commit()
            await run_image_job(job.id)
            self.db.expire_all()
            job = self.db.get(GenerationJob, job.id)
            scene = self.db.get(Scene, scene.id)
            if job is None or job.status != "COMPLETED" or job.output_asset_id is None:
                raise RuntimeError(job.error_message if job else "Image generation failed")
            generated += 1
            asset = self.db.get(MediaAsset, job.output_asset_id)
            if self.run.mode == WorkflowMode.AUTO:
                StockMediaService.select_asset(asset, scene, self.db)
            else:
                waiting.append(scene.order)
        if waiting:
            return StepOutcome(
                "WAITING", f"Review/select image media for scenes {', '.join(map(str, waiting))}, then resume"
            )
        return StepOutcome(
            operation=f"Image assets ready; {generated} generated", metadata={"job_ids": job_ids}
        )

    async def _videos(self) -> StepOutcome:
        generated = 0
        job_ids = []
        waiting = []
        for scene in self._scenes_list():
            preferred = self._preferred(scene)
            if scene.visual_strategy != VisualStrategy.AI_VIDEO:
                continue
            if preferred and preferred.type != MediaAssetType.AI_IMAGE:
                continue
            if not self.policy.generate_ai_video:
                scene.visual_strategy = VisualStrategy.AI_IMAGE_MOTION
                self.db.commit()
                continue
            if preferred is None or preferred.type != MediaAssetType.AI_IMAGE:
                raise RuntimeError(f"Scene {scene.order} needs a selected source image")
            candidate = self.db.scalar(
                select(MediaAsset)
                .where(
                    MediaAsset.scene_id == scene.id,
                    MediaAsset.type == MediaAssetType.AI_VIDEO,
                    MediaAsset.status != MediaAssetStatus.REJECTED,
                )
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
            )
            if candidate and candidate.local_path and Path(candidate.local_path).is_file():
                if self.run.mode == WorkflowMode.AUTO:
                    StockMediaService.select_asset(candidate, scene, self.db)
                else:
                    waiting.append(scene.order)
                continue
            prompt = self.db.scalar(
                select(ScenePrompt)
                .where(ScenePrompt.scene_id == scene.id)
                .order_by(ScenePrompt.version.desc())
            )
            if prompt is None:
                raise RuntimeError(f"Scene {scene.order} has no video prompt")
            latest_job = self._latest_job(scene.id, "AI_VIDEO")
            retry_count = latest_job.retry_count + 1 if latest_job and latest_job.status == "FAILED" else 0
            job = submit_video_job(scene, prompt, preferred, self.db, retry_count=retry_count)
            job_ids.append(job.id)
            self.run.current_job_id = job.id
            self.run.current_operation = f"Generating video for scene {scene.order}"
            self.db.commit()
            await run_video_job(job.id)
            self.db.expire_all()
            job = self.db.get(GenerationJob, job.id)
            scene = self.db.get(Scene, scene.id)
            if job is None or job.status != "COMPLETED" or job.output_asset_id is None:
                raise RuntimeError(job.error_message if job else "Video generation failed")
            generated += 1
            asset = self.db.get(MediaAsset, job.output_asset_id)
            if self.run.mode == WorkflowMode.AUTO:
                StockMediaService.select_asset(asset, scene, self.db)
            else:
                waiting.append(scene.order)
        if waiting:
            return StepOutcome(
                "WAITING", f"Review/select video media for scenes {', '.join(map(str, waiting))}, then resume"
            )
        return StepOutcome(
            operation=f"Video assets ready; {generated} generated", metadata={"job_ids": job_ids}
        )

    async def _voice(self) -> StepOutcome:
        track = self.db.scalar(
            select(VoiceTrack)
            .where(VoiceTrack.project_id == self.project.id)
            .order_by(VoiceTrack.created_at.desc(), VoiceTrack.id.desc())
        )
        if track is None or track.status in {
            VoiceTrackStatus.UPLOADED,
            VoiceTrackStatus.TRANSCRIBING,
            VoiceTrackStatus.FAILED,
        }:
            return StepOutcome("VOICE_WAITING", "Upload a voice-over; AUTO mode resumes after transcription")
        if track.status == VoiceTrackStatus.READY:
            if self.run.mode == WorkflowMode.AUTO:
                apply_voice_timing(track, self.db)
            else:
                return StepOutcome("VOICE_WAITING", "Review transcript timing, apply it, then resume")
        return StepOutcome(operation=f"Using applied voice track {track.id}")

    async def _timeline(self) -> StepOutcome:
        applied = self.db.scalar(
            select(VoiceTrack)
            .where(
                VoiceTrack.project_id == self.project.id,
                VoiceTrack.status == VoiceTrackStatus.APPLIED,
            )
            .order_by(VoiceTrack.created_at.desc(), VoiceTrack.id.desc())
        )
        if applied is None:
            raise RuntimeError("Apply voice timing before timeline assembly")
        timeline = self.db.scalar(
            select(Timeline)
            .where(Timeline.project_id == self.project.id)
            .order_by(Timeline.version.desc())
        )
        if timeline is None or timeline.voice_track_id != applied.id or not timeline.valid:
            timeline = build_timeline(self.project, self.db)
        if not timeline.valid:
            errors = [item["message"] for item in timeline.warnings_json if item["severity"] == "ERROR"]
            raise RuntimeError("Timeline preflight failed: " + "; ".join(errors))
        return StepOutcome(operation=f"Timeline version {timeline.version} is valid")

    async def _audio(self) -> StepOutcome:
        timeline = self.db.scalar(
            select(Timeline)
            .where(Timeline.project_id == self.project.id)
            .order_by(Timeline.version.desc())
        )
        if timeline is None:
            raise RuntimeError("Timeline is required before audio planning")
        apply_audio_to_timeline(timeline, self.db)
        self.db.commit()
        return StepOutcome(operation="Subtitle and voice-first audio plan prepared")

    async def _render_ready(self) -> StepOutcome:
        timeline = self.db.scalar(
            select(Timeline)
            .where(Timeline.project_id == self.project.id)
            .order_by(Timeline.version.desc())
        )
        if timeline is None or not timeline.valid:
            raise RuntimeError("A valid timeline is required for render-ready state")
        plan = timeline.render_plan_json
        if "subtitles" not in plan or "audio_mix" not in plan:
            raise RuntimeError("Subtitle and audio plans are incomplete")
        return StepOutcome(operation="All implemented phases are render-ready")

    def _scenes_list(self) -> list[Scene]:
        return list(
            self.db.scalars(
                select(Scene).where(Scene.project_id == self.project.id).order_by(Scene.order)
            )
        )

    def _preferred(self, scene: Scene) -> MediaAsset | None:
        return self.db.get(MediaAsset, scene.preferred_media_asset_id) if scene.preferred_media_asset_id else None

    def _latest_job(self, scene_id: int, job_type: str) -> GenerationJob | None:
        return self.db.scalar(
            select(GenerationJob)
            .where(GenerationJob.scene_id == scene_id, GenerationJob.job_type == job_type)
            .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        )
