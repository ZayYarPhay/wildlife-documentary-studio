import asyncio
import json
import re
import shutil
import subprocess
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import GenerationJob
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.scene import Scene, VisualStrategy
from app.models.voice import SceneVoiceAlignment, TranscriptSegment, VoiceTrack, VoiceTrackStatus
from app.providers.base import TranscriptionProvider
from app.providers.mock_transcription import MockTranscriptionProvider

ALLOWED_AUDIO = {
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a"},
}


def get_transcription_provider() -> TranscriptionProvider:
    name = get_settings().transcription_provider.lower()
    if name == "mock":
        return MockTranscriptionProvider()
    raise ValueError(f"Unsupported transcription provider: {name}")


async def save_voice_upload(project: Project, upload: UploadFile) -> VoiceTrack:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise ValueError("Only WAV, MP3 and M4A narration files are accepted")
    mime = (upload.content_type or "").lower()
    if mime not in ALLOWED_AUDIO[suffix]:
        raise ValueError("Uploaded MIME type does not match an accepted audio format")
    settings = get_settings()
    output_dir = Path(settings.media_root) / str(project.id) / "voice"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"voice-{uuid4().hex}{suffix}"
    output_path = output_dir / filename
    size = 0
    header = b""
    try:
        with output_path.open("xb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.voice_upload_max_bytes:
                    raise ValueError("Voice-over file exceeds the configured size limit")
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                target.write(chunk)
        if size == 0 or not _signature_matches(suffix, header):
            raise ValueError("Audio file signature does not match its extension")
        probe = probe_audio(output_path)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    relative_url = f"{project.id}/voice/{filename}"
    return VoiceTrack(
        project_id=project.id,
        path=str(output_path.resolve()),
        public_url=f"{settings.public_media_base_url.rstrip('/')}/{relative_url}",
        original_filename=Path(upload.filename or filename).name[:300],
        mime_type=mime,
        size_bytes=size,
        duration=probe["duration"],
        language=project.language,
        status=VoiceTrackStatus.UPLOADED,
        metadata_json={"probe": probe},
    )


def probe_audio(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which(get_settings().ffprobe_path)
    if ffprobe is None:
        raise RuntimeError("FFprobe is required to validate narration audio")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type,codec_name:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Uploaded file failed FFprobe audio validation")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    duration = float(payload.get("format", {}).get("duration", 0))
    if not streams or streams[0].get("codec_type") != "audio" or duration <= 0:
        raise ValueError("Uploaded file has no valid audio stream or duration")
    return {"duration": round(duration, 3), "codec": streams[0].get("codec_name")}


def submit_transcription(track: VoiceTrack, project: Project, db: Session) -> GenerationJob:
    provider = get_transcription_provider()
    job = GenerationJob(
        project_id=project.id,
        job_type="TRANSCRIPTION",
        provider=getattr(provider, "name", provider.__class__.__name__),
        status="PENDING",
        progress=0,
        request_json={"voice_track_id": track.id},
    )
    track.status = VoiceTrackStatus.TRANSCRIBING
    project.status = ProjectStatus.VOICE_TRANSCRIBING
    project.current_phase = ProjectPhase.VOICE
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def run_transcription(job_id: int, provider: TranscriptionProvider | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        track = db.get(VoiceTrack, job.request_json.get("voice_track_id")) if job else None
        if job is None or track is None:
            return
        project = db.get(Project, track.project_id)
        scenes = list(
            db.scalars(
                select(Scene).where(Scene.project_id == track.project_id).order_by(Scene.order)
            )
        )
        if project is None or not scenes:
            raise RuntimeError("Generate scenes before transcribing narration")
        job.status = "RUNNING"
        job.progress = 0.1
        db.commit()
        active_provider = provider or get_transcription_provider()
        result = await asyncio.wait_for(
            active_provider.transcribe(
                track.path,
                language=track.language,
                duration=track.duration,
                scene_texts=[scene.narration_text for scene in scenes],
            ),
            timeout=get_settings().transcription_timeout_seconds,
        )
        segments = _validate_segments(result.get("segments", []), track.duration)
        db.execute(
            delete(SceneVoiceAlignment).where(SceneVoiceAlignment.voice_track_id == track.id)
        )
        db.execute(delete(TranscriptSegment).where(TranscriptSegment.voice_track_id == track.id))
        for item in segments:
            db.add(TranscriptSegment(voice_track_id=track.id, **item))
        db.flush()
        create_alignments(track, scenes, db)
        track.language = str(result.get("language") or track.language)
        metadata = dict(track.metadata_json)
        metadata["transcription"] = result.get("metadata_json", {})
        track.metadata_json = metadata
        track.status = VoiceTrackStatus.READY
        project.status = ProjectStatus.VOICE_REVIEW
        project.current_phase = ProjectPhase.VOICE_REVIEW
        job.status = "COMPLETED"
        job.progress = 1
        db.commit()
        from app.services.workflow import resume_waiting_workflow

        await resume_waiting_workflow(track.project_id)
    except Exception as exc:  # noqa: BLE001 - provider diagnostics are persisted
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = "FAILED"
            job.error_message = str(exc)
            track = db.get(VoiceTrack, job.request_json.get("voice_track_id"))
            if track is not None:
                track.status = VoiceTrackStatus.FAILED
                project = db.get(Project, track.project_id)
                if project is not None:
                    project.status = ProjectStatus.VOICE_REVIEW
                    project.current_phase = ProjectPhase.VOICE_REVIEW
            db.commit()
    finally:
        db.close()


def create_alignments(track: VoiceTrack, scenes: list[Scene], db: Session) -> None:
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.voice_track_id == track.id)
            .order_by(TranscriptSegment.start_time)
        )
    )
    transcript_text = " ".join(segment.text for segment in segments)
    script_text = " ".join(scene.narration_text for scene in scenes)
    overall = _similarity(script_text, transcript_text)
    track.alignment_confidence = overall
    track.mismatch_warning = (
        "Narration differs substantially from the approved script; review highlighted scenes."
        if overall < 0.7
        else None
    )
    total_expected = sum(max(1, len(_tokens(scene.narration_text))) for scene in scenes)
    cursor_weight = 0
    for index, scene in enumerate(scenes):
        weight = max(1, len(_tokens(scene.narration_text)))
        start = track.duration * cursor_weight / total_expected
        cursor_weight += weight
        end = (
            track.duration
            if index == len(scenes) - 1
            else track.duration * cursor_weight / total_expected
        )
        assigned = " ".join(
            segment.text
            for segment in segments
            if segment.end_time > start + 0.01 and segment.start_time < end - 0.01
        )
        confidence = _similarity(scene.narration_text, assigned)
        old_duration = scene.target_duration
        new_duration = end - start
        if new_duration > old_duration + 0.5:
            adjustment = (
                "EXTEND_IMAGE_MOTION"
                if scene.visual_strategy == VisualStrategy.AI_IMAGE_MOTION
                else "LOOP_OR_ADDITIONAL_CLIP"
                if scene.visual_strategy == VisualStrategy.STOCK_VIDEO
                else "EXTEND_OR_SPLIT_CLIP"
            )
        elif new_duration < old_duration - 0.5:
            adjustment = "TRIM_VISUAL_SAFELY"
        else:
            adjustment = "KEEP_VISUAL_DURATION"
        db.add(
            SceneVoiceAlignment(
                voice_track_id=track.id,
                scene_id=scene.id,
                recommended_start=round(start, 3),
                recommended_end=round(end, 3),
                confidence=confidence,
                mismatch=confidence < 0.55,
                visual_adjustment=adjustment,
            )
        )


def recompute_alignments(track: VoiceTrack, db: Session) -> None:
    scenes = list(
        db.scalars(select(Scene).where(Scene.project_id == track.project_id).order_by(Scene.order))
    )
    db.execute(delete(SceneVoiceAlignment).where(SceneVoiceAlignment.voice_track_id == track.id))
    db.flush()
    create_alignments(track, scenes, db)
    db.commit()


def apply_voice_timing(track: VoiceTrack, db: Session) -> None:
    scenes = list(
        db.scalars(select(Scene).where(Scene.project_id == track.project_id).order_by(Scene.order))
    )
    alignments = {
        item.scene_id: item
        for item in db.scalars(
            select(SceneVoiceAlignment).where(SceneVoiceAlignment.voice_track_id == track.id)
        )
    }
    if len(alignments) != len(scenes):
        raise ValueError("Every scene needs an alignment before timing can be applied")
    ordered = [alignments[scene.id] for scene in scenes]
    if (
        abs(ordered[0].recommended_start) > 0.05
        or abs(ordered[-1].recommended_end - track.duration) > 0.05
    ):
        raise ValueError("Alignment must cover the full voice-over duration")
    for previous, current in pairwise(ordered):
        if abs(previous.recommended_end - current.recommended_start) > 0.1:
            raise ValueError("Scene alignments must be contiguous")
    for scene, alignment in zip(scenes, ordered, strict=True):
        scene.start_time = alignment.recommended_start
        scene.end_time = alignment.recommended_end
        scene.target_duration = round(alignment.recommended_end - alignment.recommended_start, 3)
    track.status = VoiceTrackStatus.APPLIED
    project = db.get(Project, track.project_id)
    if project is not None:
        project.status = ProjectStatus.VOICE_APPLIED
        project.current_phase = ProjectPhase.VOICE_REVIEW
    db.commit()


def _validate_segments(items: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    result = []
    previous_end = 0.0
    for item in items:
        start = float(item["start_time"])
        end = float(item["end_time"])
        text = str(item["text"]).strip()
        if start < previous_end - 0.01 or end <= start or end > duration + 0.25 or not text:
            raise RuntimeError("Transcription provider returned invalid timestamp segments")
        result.append(
            {
                "start_time": start,
                "end_time": end,
                "text": text,
                "confidence": item.get("confidence"),
            }
        )
        previous_end = end
    if not result:
        raise RuntimeError("Transcription provider returned no timestamp segments")
    return result


def _signature_matches(suffix: str, header: bytes) -> bool:
    if suffix == ".wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if suffix == ".mp3":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
        )
    return suffix == ".m4a" and len(header) >= 12 and header[4:8] == b"ftyp"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _similarity(expected: str, actual: str) -> float:
    return round(
        SequenceMatcher(None, " ".join(_tokens(expected)), " ".join(_tokens(actual))).ratio(), 4
    )
