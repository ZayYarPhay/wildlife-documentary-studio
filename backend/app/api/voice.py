from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.project import Project
from app.models.scene import Scene
from app.models.voice import SceneVoiceAlignment, TranscriptSegment, VoiceTrack
from app.schemas.voice import (
    SceneVoiceAlignmentRead,
    SceneVoiceAlignmentUpdate,
    TranscriptSegmentRead,
    TranscriptSegmentUpdate,
    VoiceBundle,
)
from app.services.voice import (
    apply_voice_timing,
    recompute_alignments,
    run_transcription,
    save_voice_upload,
    submit_transcription,
)

router = APIRouter(tags=["voice-over"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def track_or_404(track_id: int, db: Session) -> VoiceTrack:
    track = db.scalar(
        select(VoiceTrack)
        .where(VoiceTrack.id == track_id)
        .options(selectinload(VoiceTrack.segments), selectinload(VoiceTrack.alignments))
    )
    if track is None:
        raise HTTPException(status_code=404, detail="Voice track not found")
    return track


def voice_bundle(project_id: int, db: Session) -> VoiceBundle:
    tracks = list(
        db.scalars(
            select(VoiceTrack)
            .where(VoiceTrack.project_id == project_id)
            .options(selectinload(VoiceTrack.segments), selectinload(VoiceTrack.alignments))
            .order_by(VoiceTrack.created_at.desc(), VoiceTrack.id.desc())
        )
    )
    provider = get_settings().transcription_provider
    return VoiceBundle(
        project_id=project_id,
        provider=provider,
        is_mock=provider.lower() == "mock",
        active=tracks[0] if tracks else None,
        tracks=tracks,
        warning=(
            "Mock transcription mirrors scene narration for workflow testing; it does not listen to audio."
            if provider.lower() == "mock" and tracks
            else None
        ),
    )


@router.get("/api/projects/{project_id}/voice", response_model=VoiceBundle)
def get_voice(project_id: int, db: DatabaseSession) -> VoiceBundle:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return voice_bundle(project_id, db)


@router.post(
    "/api/projects/{project_id}/voice/upload",
    response_model=VoiceBundle,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_voice(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
) -> VoiceBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if db.scalar(select(Scene.id).where(Scene.project_id == project_id).limit(1)) is None:
        raise HTTPException(status_code=422, detail="Generate scenes before uploading narration")
    try:
        track = await save_voice_upload(project, file)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(track)
    db.flush()
    job = submit_transcription(track, project, db)
    background_tasks.add_task(run_transcription, job.id)
    return voice_bundle(project_id, db)


@router.post(
    "/api/voice-tracks/{track_id}/transcribe",
    response_model=VoiceBundle,
    status_code=status.HTTP_202_ACCEPTED,
)
def retranscribe_voice(
    track_id: int, background_tasks: BackgroundTasks, db: DatabaseSession
) -> VoiceBundle:
    track = track_or_404(track_id, db)
    project = db.get(Project, track.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job = submit_transcription(track, project, db)
    background_tasks.add_task(run_transcription, job.id)
    return voice_bundle(track.project_id, db)


@router.patch("/api/transcript-segments/{segment_id}", response_model=TranscriptSegmentRead)
def update_transcript_segment(
    segment_id: int, payload: TranscriptSegmentUpdate, db: DatabaseSession
) -> TranscriptSegment:
    segment = db.get(TranscriptSegment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Transcript segment not found")
    segment.text = payload.text.strip()
    track = track_or_404(segment.voice_track_id, db)
    db.flush()
    recompute_alignments(track, db)
    db.refresh(segment)
    return segment


@router.patch("/api/voice-alignments/{alignment_id}", response_model=SceneVoiceAlignmentRead)
def update_voice_alignment(
    alignment_id: int, payload: SceneVoiceAlignmentUpdate, db: DatabaseSession
) -> SceneVoiceAlignment:
    alignment = db.get(SceneVoiceAlignment, alignment_id)
    if alignment is None:
        raise HTTPException(status_code=404, detail="Voice alignment not found")
    alignment.recommended_start = payload.recommended_start
    alignment.recommended_end = payload.recommended_end
    alignment.manually_edited = True
    db.commit()
    db.refresh(alignment)
    return alignment


@router.post("/api/voice-tracks/{track_id}/apply", response_model=VoiceBundle)
def apply_timing(track_id: int, db: DatabaseSession) -> VoiceBundle:
    track = track_or_404(track_id, db)
    try:
        apply_voice_timing(track, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return voice_bundle(track.project_id, db)
