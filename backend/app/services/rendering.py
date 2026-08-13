import json
import logging
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.audio import AudioSettings
from app.models.jobs import RenderJob
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.timeline import Timeline, TimelineTrack
from app.models.voice import TranscriptSegment, VoiceTrack, VoiceTrackStatus
from app.schemas.export import ExportSettings, PreflightCheck, PreflightReport
from app.services.timeline import ffmpeg_item_command

logger = logging.getLogger(__name__)
ACTIVE_RENDER_STATUSES = {"PENDING", "RUNNING"}
TERMINAL_RENDER_STATUSES = {"COMPLETED", "FAILED", "CANCELED"}


class RenderCanceled(RuntimeError):
    pass


def latest_timeline(project_id: int, db: Session) -> Timeline | None:
    return db.scalar(
        select(Timeline)
        .where(Timeline.project_id == project_id)
        .options(selectinload(Timeline.items))
        .order_by(Timeline.version.desc(), Timeline.id.desc())
    )


def preflight_project(
    project: Project, db: Session, export: ExportSettings | None = None
) -> PreflightReport:
    export = export or ExportSettings(fps=get_settings().timeline_fps)
    checks: list[PreflightCheck] = []
    timeline = latest_timeline(project.id, db)
    voice = None
    if timeline is None:
        checks.append(_check("TIMELINE", "Timeline", "ERROR", "Build a timeline before export."))
    else:
        checks.append(
            _check(
                "TIMELINE",
                "Timeline coverage",
                "PASS" if timeline.valid else "ERROR",
                "Timeline is valid and covers the narration."
                if timeline.valid
                else "Timeline has unresolved validation errors.",
            )
        )
        voice = db.get(VoiceTrack, timeline.voice_track_id)
    voice_ok = bool(
        voice and voice.status == VoiceTrackStatus.APPLIED and _managed_file(voice.path, project.id)
    )
    checks.append(
        _check(
            "VOICE",
            "Voice-over",
            "PASS" if voice_ok else "ERROR",
            "Applied voice-over exists in managed storage."
            if voice_ok
            else "An applied, readable voice-over is required.",
        )
    )
    visual_items = (
        [item for item in timeline.items if item.track == TimelineTrack.VISUAL] if timeline else []
    )
    missing_visuals = [
        item.id
        for item in visual_items
        if not _managed_file(str(item.metadata_json.get("source_path") or ""), project.id)
    ]
    checks.append(
        _check(
            "VISUAL_FILES",
            "Visual files",
            "PASS" if visual_items and not missing_visuals else "ERROR",
            f"{len(visual_items)} visual segments are available."
            if visual_items and not missing_visuals
            else f"Missing or unmanaged visual files for {len(missing_visuals)} timeline items.",
        )
    )
    width, height = _resolution(project.output_resolution)
    aspect_ok = abs(width / height - 16 / 9) < 0.02
    checks.append(
        _check(
            "OUTPUT_FORMAT",
            "Output format",
            "PASS" if aspect_ok else "WARNING",
            f"Sources will be normalized to {width}x{height} at {export.fps} fps."
            + ("" if aspect_ok else " Selected output is not 16:9."),
        )
    )
    subtitle_ok = True
    if timeline and export.subtitles_enabled:
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.voice_track_id == timeline.voice_track_id)
                .order_by(TranscriptSegment.start_time)
            )
        )
        subtitle_ok = bool(segments) and all(
            0 <= segment.start_time < segment.end_time <= timeline.duration + 0.25
            for segment in segments
        )
        checks.append(
            _check(
                "SUBTITLES",
                "Subtitle timestamps",
                "PASS" if subtitle_ok else "ERROR",
                f"{len(segments)} subtitle segments are valid."
                if subtitle_ok
                else "Subtitle burn-in is enabled but timestamps are missing or invalid.",
            )
        )
    audio_missing: list[int] = []
    if timeline and export.audio_mix_enabled:
        for item in timeline.items:
            if item.track in {TimelineTrack.MUSIC, TimelineTrack.AMBIENT} and not _managed_file(
                str(item.metadata_json.get("source_path") or ""), project.id
            ):
                audio_missing.append(item.id)
    checks.append(
        _check(
            "AUDIO_FILES",
            "Audio mix files",
            "PASS" if not audio_missing else "ERROR",
            "Optional audio tracks are readable."
            if not audio_missing
            else "Audio mix has missing files.",
        )
    )
    project_dir = _project_dir(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(project_dir).free
    duration = timeline.duration if timeline else project.requested_duration_seconds
    estimated = max(50_000_000, round(duration * 4_000_000))
    disk_ok = free_bytes >= max(estimated, get_settings().render_min_free_bytes)
    checks.append(
        _check(
            "DISK_SPACE",
            "Disk space",
            "PASS" if disk_ok else "ERROR",
            f"{free_bytes:,} bytes free; estimated {estimated:,} bytes required.",
        )
    )
    tools_ok = bool(shutil.which(get_settings().ffmpeg_path)) and bool(
        shutil.which(get_settings().ffprobe_path)
    )
    checks.append(
        _check(
            "MEDIA_TOOLS",
            "FFmpeg / FFprobe",
            "PASS" if tools_ok else "ERROR",
            "FFmpeg and FFprobe are available."
            if tools_ok
            else "FFmpeg and FFprobe must be installed and configured.",
        )
    )
    return PreflightReport(
        project_id=project.id,
        timeline_id=timeline.id if timeline else None,
        ready=not any(item.status == "ERROR" for item in checks),
        checks=checks,
        estimated_required_bytes=estimated,
        free_bytes=free_bytes,
    )


def submit_render_job(
    project: Project,
    export: ExportSettings,
    db: Session,
    *,
    retry_count: int = 0,
) -> RenderJob:
    active = db.scalar(
        select(RenderJob).where(
            RenderJob.project_id == project.id, RenderJob.status.in_(ACTIVE_RENDER_STATUSES)
        )
    )
    if active:
        raise ValueError("A render is already pending or running for this project")
    report = preflight_project(project, db, export)
    if not report.ready or report.timeline_id is None:
        errors = "; ".join(item.detail for item in report.checks if item.status == "ERROR")
        raise ValueError(f"Export preflight failed: {errors}")
    job = RenderJob(
        project_id=project.id,
        timeline_id=report.timeline_id,
        status="PENDING",
        progress=0,
        retry_count=retry_count,
        settings_json=export.model_dump(mode="json"),
        validation_json={"preflight": report.model_dump(mode="json")},
    )
    project.status = ProjectStatus.RENDERING
    project.current_phase = ProjectPhase.EXPORT
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def recover_stale_render_jobs(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().job_stale_seconds)
    jobs = list(
        db.scalars(
            select(RenderJob).where(RenderJob.status == "RUNNING", RenderJob.updated_at < cutoff)
        )
    )
    for job in jobs:
        job.status = "FAILED"
        job.error_message = "Render process was interrupted; retry is safe."
        job.finished_at = datetime.now(UTC)
        project = db.get(Project, job.project_id)
        if project:
            project.status = ProjectStatus.RENDER_READY
    if jobs:
        db.commit()
    return len(jobs)


def run_render_job(job_id: int) -> None:
    db = SessionLocal()
    temp_dir: Path | None = None
    try:
        job = db.get(RenderJob, job_id)
        if job is None or job.status == "CANCELED":
            return
        timeline = db.scalar(
            select(Timeline)
            .where(Timeline.id == job.timeline_id)
            .options(selectinload(Timeline.items))
        )
        project = db.get(Project, job.project_id)
        if timeline is None or project is None:
            raise RuntimeError("Render job references a missing project or timeline")
        export = ExportSettings.model_validate(job.settings_json)
        report = preflight_project(project, db, export)
        if not report.ready:
            raise RuntimeError("Render preflight became invalid after submission")
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.progress = 0.02
        job.error_message = None
        db.commit()
        render_dir = _project_dir(project.id) / "renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = render_dir / f".job-{job.id}-temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        visuals = sorted(
            (item for item in timeline.items if item.track == TimelineTrack.VISUAL),
            key=lambda item: (item.start_time, item.order),
        )
        segment_paths: list[Path] = []
        for index, item in enumerate(visuals):
            _raise_if_canceled(job.id)
            segment = temp_dir / f"segment-{index:05}.mp4"
            command = ffmpeg_item_command(item, segment, project.output_resolution, export.fps)
            _run_command(job.id, command, temp_dir, 0.03 + 0.45 * index / len(visuals))
            segment_paths.append(segment)
            _set_progress(job.id, 0.03 + 0.45 * (index + 1) / len(visuals))
        concat_list = temp_dir / "segments.txt"
        concat_list.write_text(
            "\n".join(f"file '{path.name}'" for path in segment_paths) + "\n", encoding="utf-8"
        )
        visuals_path = temp_dir / "visuals.mp4"
        ffmpeg = _required_tool(get_settings().ffmpeg_path)
        _run_command(
            job.id,
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "1",
                "-i",
                concat_list.name,
                "-an",
                "-c:v",
                "copy",
                visuals_path.name,
            ],
            temp_dir,
            0.5,
        )
        final_temp = temp_dir / "final.mp4"
        final_command = _final_command(timeline, export, visuals_path, final_temp, temp_dir, db)
        _run_command(job.id, final_command, temp_dir, 0.58, 0.32)
        output = render_dir / f"documentary-render-{job.id}.mp4"
        validation = validate_final_output(final_temp, timeline, project.output_resolution)
        os.replace(final_temp, output)
        job = db.get(RenderJob, job.id)
        job.status = "COMPLETED"
        job.progress = 1
        job.output_path = str(output.resolve())
        job.duration = validation["duration"]
        job.width = validation["width"]
        job.height = validation["height"]
        job.fps = validation["fps"]
        job.file_size_bytes = output.stat().st_size
        job.validation_json = {**job.validation_json, "output": validation}
        job.finished_at = datetime.now(UTC)
        project.status = ProjectStatus.COMPLETED
        project.current_phase = ProjectPhase.EXPORT
        db.commit()
    except RenderCanceled:
        db.rollback()
        job = db.get(RenderJob, job_id)
        if job:
            job.status = "CANCELED"
            job.progress = min(job.progress, 0.99)
            job.error_message = "Render canceled by user"
            job.finished_at = datetime.now(UTC)
            project = db.get(Project, job.project_id)
            if project:
                project.status = ProjectStatus.RENDER_READY
            db.commit()
    except Exception as exc:
        logger.exception("Render job failed", extra={"render_job_id": job_id})
        db.rollback()
        job = db.get(RenderJob, job_id)
        if job:
            job.status = "FAILED"
            job.error_message = str(exc)[-4000:]
            job.logs = ((job.logs or "") + "\n" + str(exc))[-20_000:]
            job.finished_at = datetime.now(UTC)
            project = db.get(Project, job.project_id)
            if project:
                project.status = ProjectStatus.RENDER_READY
            db.commit()
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        db.close()


def validate_final_output(path: Path, timeline: Timeline, resolution: str) -> dict[str, Any]:
    ffprobe = _required_tool(get_settings().ffprobe_path)
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Final FFprobe validation failed: {completed.stderr[-2000:]}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    duration = float(payload.get("format", {}).get("duration", 0))
    width, height = _resolution(resolution)
    if video is None or audio is None or duration <= 0:
        raise RuntimeError("Final output must contain non-empty video and audio streams")
    if int(video.get("width", 0)) != width or int(video.get("height", 0)) != height:
        raise RuntimeError("Final output resolution does not match export settings")
    if abs(duration - timeline.duration) > max(0.5, timeline.duration * 0.02):
        raise RuntimeError("Final output duration does not approximately match the timeline")
    frame_rate = _fraction(video.get("avg_frame_rate", "0/1"))
    return {
        "valid": True,
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(frame_rate, 3),
        "has_video": True,
        "has_audio": True,
        "aspect_ratio": "16:9" if abs(width / height - 16 / 9) < 0.02 else f"{width}:{height}",
    }


def _final_command(
    timeline: Timeline,
    export: ExportSettings,
    visuals_path: Path,
    output: Path,
    temp_dir: Path,
    db: Session,
) -> list[str]:
    voice = db.get(VoiceTrack, timeline.voice_track_id)
    if voice is None:
        raise RuntimeError("Timeline voice-over no longer exists")
    ffmpeg = _required_tool(get_settings().ffmpeg_path)
    command = [ffmpeg, "-y", "-i", visuals_path.name, "-i", voice.path]
    audio_items = (
        [
            item
            for item in timeline.items
            if item.track in {TimelineTrack.MUSIC, TimelineTrack.AMBIENT}
        ]
        if export.audio_mix_enabled
        else []
    )
    for item in audio_items:
        if item.metadata_json.get("loop"):
            command.extend(["-stream_loop", "-1"])
        command.extend(["-i", str(item.metadata_json["source_path"])])
    filters = ["[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice]"]
    labels = ["[voice]"]
    for index, item in enumerate(audio_items, start=2):
        duration = item.end_time - item.start_time
        delay = round(item.start_time * 1000)
        volume = float(item.metadata_json.get("volume", 0.15))
        label = f"extra{index}"
        filters.append(
            f"[{index}:a]atrim=0:{duration},adelay={delay}|{delay},volume={volume}[{label}]"
        )
        labels.append(f"[{label}]")
    audio_label = "voice"
    if len(labels) > 1:
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
            "alimiter=limit=0.95[mix]"
        )
        audio_label = "mix"
    if filters:
        command.extend(["-filter_complex", ";".join(filters)])
    subtitle_filter = None
    settings = db.scalar(
        select(AudioSettings).where(AudioSettings.project_id == timeline.project_id)
    )
    if export.subtitles_enabled and settings and settings.subtitles_enabled:
        subtitle_item = next(
            (item for item in timeline.items if item.track == TimelineTrack.SUBTITLE), None
        )
        source = Path(str(subtitle_item.metadata_json.get("srt_path"))) if subtitle_item else None
        if source and source.is_file():
            local_subtitle = temp_dir / "subtitles.srt"
            shutil.copyfile(source, local_subtitle)
            alignment = {"TOP": 8, "MIDDLE": 5, "BOTTOM": 2}.get(settings.subtitle_position, 2)
            style = (
                f"FontSize={settings.subtitle_font_size},Alignment={alignment},"
                f"MarginV={settings.subtitle_safe_margin},Outline="
                f"{2 if settings.subtitle_outline else 0}"
            )
            subtitle_filter = f"subtitles=subtitles.srt:force_style='{style}'"
    command.extend(["-map", "0:v:0", "-map", f"[{audio_label}]"])
    if subtitle_filter:
        command.extend(["-vf", subtitle_filter])
    command.extend(
        [
            "-t",
            str(timeline.duration),
            "-c:v",
            "libx264",
            "-preset",
            export.preset,
            "-crf",
            str(export.crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            output.name,
        ]
    )
    return command


def _run_command(
    job_id: int,
    command: list[str],
    cwd: Path,
    base_progress: float,
    progress_span: float = 0.02,
) -> None:
    command = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]
    log_path = cwd / f"ffmpeg-{int(time.time() * 1000)}.log"
    started = time.monotonic()
    with log_path.open("w+", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            shell=False,
        )
        assert process.stdout is not None
        while True:
            line = process.stdout.readline()
            if line.startswith("out_time_ms="):
                _set_progress(job_id, min(0.98, base_progress + progress_span * 0.5))
            if _cancel_requested(job_id):
                process.kill()
                process.wait()
                raise RenderCanceled("Render canceled by user")
            if process.poll() is not None:
                break
            if time.monotonic() - started > get_settings().render_timeout_seconds:
                process.kill()
                process.wait()
                raise RuntimeError("FFmpeg render timed out")
        process.stdout.close()
        log_file.seek(0)
        diagnostic = log_file.read()[-20_000:]
    _append_logs(job_id, diagnostic)
    if process.returncode:
        raise RuntimeError(f"FFmpeg failed with code {process.returncode}: {diagnostic[-4000:]}")
    _set_progress(job_id, min(0.98, base_progress + progress_span))


def _append_logs(job_id: int, text: str) -> None:
    if not text:
        return
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        if job:
            job.logs = ((job.logs or "") + "\n" + text)[-20_000:]
            db.commit()


def _set_progress(job_id: int, progress: float) -> None:
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        if job:
            job.progress = max(job.progress, progress)
            db.commit()


def _cancel_requested(job_id: int) -> bool:
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        return bool(job is None or job.cancel_requested or job.status == "CANCELED")


def _raise_if_canceled(job_id: int) -> None:
    if _cancel_requested(job_id):
        raise RenderCanceled("Render canceled by user")


def _managed_file(raw_path: str, project_id: int) -> bool:
    if not raw_path:
        return False
    path = Path(raw_path).resolve()
    root = _project_dir(project_id)
    return path.is_relative_to(root) and path.is_file()


def _project_dir(project_id: int) -> Path:
    return (Path(get_settings().media_root).resolve() / str(project_id)).resolve()


def _resolution(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", maxsplit=1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Output resolution must use WIDTHxHEIGHT") from exc
    if width < 64 or height < 64 or width > 8192 or height > 8192:
        raise ValueError("Output resolution is outside supported bounds")
    return width, height


def _required_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise RuntimeError(f"Required media tool is unavailable: {name}")
    return tool


def _fraction(value: str) -> float:
    numerator, denominator = value.split("/", maxsplit=1)
    return float(numerator) / max(float(denominator), 1)


def _check(code: str, label: str, status: str, detail: str) -> PreflightCheck:
    return PreflightCheck(code=code, label=label, status=status, detail=detail)
