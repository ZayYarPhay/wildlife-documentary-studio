from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audio import AudioAsset, AudioAssetKind
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.scene import Scene
from app.models.timeline import Timeline
from app.schemas.audio import AudioBundle, AudioSettingsUpdate
from app.services.audio import apply_audio_to_timeline, get_or_create_settings, save_audio_asset

router = APIRouter(tags=["subtitle-audio"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def current_timeline(project_id: int, db: Session) -> Timeline | None:
    return db.scalar(
        select(Timeline)
        .where(Timeline.project_id == project_id)
        .order_by(Timeline.version.desc())
    )


def bundle(project_id: int, db: Session) -> AudioBundle:
    settings = get_or_create_settings(project_id, db)
    assets = list(
        db.scalars(
            select(AudioAsset)
            .where(AudioAsset.project_id == project_id)
            .order_by(AudioAsset.created_at.desc(), AudioAsset.id.desc())
        )
    )
    timeline = current_timeline(project_id, db)
    subtitles = timeline.render_plan_json.get("subtitles", {}) if timeline else {}
    return AudioBundle(
        project_id=project_id,
        settings=settings,
        assets=assets,
        srt_url=(
            f"/api/timelines/{timeline.id}/subtitles.srt"
            if timeline and subtitles.get("srt_path")
            else None
        ),
        mix_plan=timeline.render_plan_json.get("audio_mix", {}) if timeline else {},
    )


@router.get("/api/projects/{project_id}/audio", response_model=AudioBundle)
def get_audio(project_id: int, db: DatabaseSession) -> AudioBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = bundle(project_id, db)
    db.commit()
    return result


@router.patch("/api/projects/{project_id}/audio/settings", response_model=AudioBundle)
def update_audio_settings(
    project_id: int, payload: AudioSettingsUpdate, db: DatabaseSession
) -> AudioBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_or_create_settings(project_id, db)
    values = payload.model_dump()
    music = db.get(AudioAsset, payload.music_asset_id) if payload.music_asset_id else None
    if payload.music_enabled and (
        music is None or music.project_id != project_id or music.kind != AudioAssetKind.MUSIC
    ):
        raise HTTPException(status_code=422, detail="Select project music with known license metadata")
    for key, value in values.items():
        setattr(settings, key, value)
    timeline = current_timeline(project_id, db)
    if timeline:
        try:
            apply_audio_to_timeline(timeline, db)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    project = db.get(Project, project_id)
    if project:
        project.status = ProjectStatus.AUDIO_REVIEW
        project.current_phase = ProjectPhase.AUDIO_REVIEW
    db.commit()
    return bundle(project_id, db)


@router.post(
    "/api/projects/{project_id}/audio/assets",
    response_model=AudioBundle,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio_asset(
    project_id: int,
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
    kind: Annotated[AudioAssetKind, Form()],
    source_name: Annotated[str, Form(min_length=1, max_length=300)],
    license_name: Annotated[str, Form(alias="license", min_length=1, max_length=500)],
    source_url: Annotated[str | None, Form(max_length=2000)] = None,
    attribution: Annotated[str | None, Form(max_length=1000)] = None,
    scene_id: Annotated[int | None, Form()] = None,
) -> AudioBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if scene_id is not None:
        scene = db.get(Scene, scene_id)
        if scene is None or scene.project_id != project_id:
            raise HTTPException(status_code=422, detail="Ambient scene does not belong to project")
    if kind == AudioAssetKind.AMBIENT and scene_id is None:
        raise HTTPException(status_code=422, detail="Ambient audio requires a scene")
    try:
        asset = await save_audio_asset(
            project,
            file,
            kind,
            source_name,
            license_name,
            source_url,
            attribution,
            scene_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(asset)
    db.commit()
    return bundle(project_id, db)


@router.get("/api/timelines/{timeline_id}/subtitles.srt")
def download_subtitles(timeline_id: int, db: DatabaseSession):
    from fastapi.responses import FileResponse

    timeline = db.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    path = timeline.render_plan_json.get("subtitles", {}).get("srt_path")
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Subtitles are disabled or unavailable")
    return FileResponse(path, media_type="application/x-subrip", filename=f"timeline-{timeline_id}.srt")
