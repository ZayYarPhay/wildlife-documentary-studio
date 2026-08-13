from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audio import AudioAsset, AudioAssetKind, AudioSettings
from app.models.project import Project
from app.models.scene import Scene
from app.models.timeline import Timeline, TimelineItem, TimelineTrack
from app.models.voice import TranscriptSegment
from app.services.voice import ALLOWED_AUDIO, _signature_matches, probe_audio


def get_or_create_settings(project_id: int, db: Session) -> AudioSettings:
    settings = db.scalar(select(AudioSettings).where(AudioSettings.project_id == project_id))
    if settings is None:
        settings = AudioSettings(project_id=project_id)
        db.add(settings)
        db.flush()
    return settings


async def save_audio_asset(
    project: Project,
    upload: UploadFile,
    kind: AudioAssetKind,
    source_name: str,
    license_name: str,
    source_url: str | None = None,
    attribution: str | None = None,
    scene_id: int | None = None,
) -> AudioAsset:
    if not source_name.strip() or not license_name.strip():
        raise ValueError("Audio source and license are required")
    if kind == AudioAssetKind.MUSIC and scene_id is not None:
        raise ValueError("Music is project-wide and cannot be assigned to a scene")
    suffix = Path(upload.filename or "").suffix.lower()
    mime = (upload.content_type or "").lower()
    if suffix not in ALLOWED_AUDIO or mime not in ALLOWED_AUDIO[suffix]:
        raise ValueError("Only valid WAV, MP3 and M4A audio files are accepted")
    settings = get_settings()
    output_dir = Path(settings.media_root) / str(project.id) / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{kind.value.lower()}-{uuid4().hex}{suffix}"
    output_path = output_dir / filename
    size = 0
    header = b""
    try:
        with output_path.open("xb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.audio_upload_max_bytes:
                    raise ValueError("Audio file exceeds the configured size limit")
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                target.write(chunk)
        if size == 0 or not _signature_matches(suffix, header):
            raise ValueError("Audio file signature does not match its extension")
        probe = probe_audio(output_path)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    relative_url = f"{project.id}/audio/{filename}"
    return AudioAsset(
        project_id=project.id,
        scene_id=scene_id,
        kind=kind,
        path=str(output_path.resolve()),
        public_url=f"{settings.public_media_base_url.rstrip('/')}/{relative_url}",
        original_filename=Path(upload.filename or filename).name[:300],
        mime_type=mime,
        size_bytes=size,
        duration=probe["duration"],
        source_name=source_name.strip()[:300],
        source_url=source_url.strip() if source_url else None,
        license=license_name.strip()[:500],
        attribution=attribution.strip()[:1000] if attribution else None,
        metadata_json={"probe": probe},
    )


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def generate_srt(timeline: Timeline, db: Session) -> tuple[str, Path]:
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.voice_track_id == timeline.voice_track_id)
            .order_by(TranscriptSegment.start_time, TranscriptSegment.id)
        )
    )
    if not segments:
        raise ValueError("Transcript timestamps are required to generate subtitles")
    blocks = []
    for index, segment in enumerate(segments, 1):
        if (
            segment.start_time < 0
            or segment.start_time >= timeline.duration
            or segment.end_time <= segment.start_time
            or segment.end_time > timeline.duration + 0.25
        ):
            raise ValueError("Transcript contains an invalid subtitle timestamp")
        text = segment.text.replace("\r", " ").replace("\n", " ").strip()
        blocks.append(
            f"{index}\n{srt_timestamp(segment.start_time)} --> "
            f"{srt_timestamp(min(segment.end_time, timeline.duration))}\n{text}"
        )
    content = "\n\n".join(blocks) + "\n"
    directory = Path(get_settings().media_root) / str(timeline.project_id) / "subtitles"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"timeline-{timeline.id}.srt"
    path.write_text(content, encoding="utf-8")
    return content, path.resolve()


def apply_audio_to_timeline(timeline: Timeline, db: Session) -> Timeline:
    settings = get_or_create_settings(timeline.project_id, db)
    db.execute(
        delete(TimelineItem).where(
            TimelineItem.timeline_id == timeline.id,
            TimelineItem.track.in_(
                [TimelineTrack.MUSIC, TimelineTrack.AMBIENT, TimelineTrack.SUBTITLE]
            ),
        )
    )
    order = db.scalar(
        select(TimelineItem.order)
        .where(TimelineItem.timeline_id == timeline.id)
        .order_by(TimelineItem.order.desc())
        .limit(1)
    ) or 0
    srt_path = None
    if settings.subtitles_enabled:
        _, srt_path = generate_srt(timeline, db)
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.voice_track_id == timeline.voice_track_id)
                .order_by(TranscriptSegment.start_time, TranscriptSegment.id)
            )
        )
        for segment in segments:
            order += 1
            db.add(
                TimelineItem(
                    timeline_id=timeline.id,
                    track=TimelineTrack.SUBTITLE,
                    order=order,
                    start_time=segment.start_time,
                    end_time=min(segment.end_time, timeline.duration),
                    transition="NONE",
                    effect="EXPORT_OVERLAY",
                    metadata_json={
                        "text": segment.text,
                        "srt_path": str(srt_path),
                        "style": subtitle_style(settings),
                    },
                )
            )
    if settings.music_enabled:
        music = db.get(AudioAsset, settings.music_asset_id)
        if music is None or music.project_id != timeline.project_id or music.kind != AudioAssetKind.MUSIC:
            raise ValueError("Selected music asset is unavailable")
        order += 1
        db.add(_audio_item(timeline, order, music, TimelineTrack.MUSIC, settings.music_volume))
    if settings.ambient_enabled:
        assets = list(
            db.scalars(
                select(AudioAsset).where(
                    AudioAsset.project_id == timeline.project_id,
                    AudioAsset.kind == AudioAssetKind.AMBIENT,
                )
            )
        )
        for asset in assets:
            if asset.scene_id is None:
                continue
            scene = db.get(Scene, asset.scene_id)
            if scene is None:
                continue
            order += 1
            db.add(
                _audio_item(
                    timeline,
                    order,
                    asset,
                    TimelineTrack.AMBIENT,
                    settings.ambient_volume,
                    scene.start_time,
                    scene.end_time,
                )
            )
    db.flush()
    from app.services.timeline import build_render_plan

    items = list(
        db.scalars(
            select(TimelineItem)
            .where(TimelineItem.timeline_id == timeline.id)
            .order_by(TimelineItem.order)
        )
    )
    timeline.render_plan_json = enrich_render_plan(
        timeline, db, build_render_plan(timeline, items), settings, srt_path
    )
    db.flush()
    return timeline


def subtitle_style(settings: AudioSettings) -> dict:
    return {
        "font_size": settings.subtitle_font_size,
        "position": settings.subtitle_position,
        "outline": settings.subtitle_outline,
        "background": settings.subtitle_background,
        "safe_margin": settings.subtitle_safe_margin,
        "burn_in": "EXPORT_ONLY",
    }


def build_audio_filter(
    settings: AudioSettings,
    has_music: bool,
    ambient_items: int | list[TimelineItem],
    duration: float = 60,
) -> str:
    filters = ["[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice]"]
    labels = ["[voice]"]
    input_index = 1
    if has_music:
        filters.append("[voice]asplit=2[voiceout][sidechain]")
        labels[0] = "[voiceout]"
        fade_out_start = max(0, duration - settings.music_fade_out)
        filters.append(
            f"[{input_index}:a]volume={settings.music_volume},"
            f"afade=t=in:st=0:d={settings.music_fade_in},"
            f"afade=t=out:st={fade_out_start}:d={settings.music_fade_out}[musicbase]"
        )
        filters.append(
            f"[musicbase][sidechain]sidechaincompress=threshold=0.03:ratio={settings.ducking_ratio}:"
            "attack=20:release=500[duckedmusic]"
        )
        labels.append("[duckedmusic]")
        input_index += 1
    items = [None] * ambient_items if isinstance(ambient_items, int) else ambient_items
    for number, item in enumerate(items):
        label = f"ambient{number}"
        timing = ""
        if item is not None:
            item_duration = item.end_time - item.start_time
            delay_ms = round(item.start_time * 1000)
            timing = f"atrim=0:{item_duration},adelay={delay_ms}|{delay_ms},"
        filters.append(
            f"[{input_index}:a]{timing}volume={settings.ambient_volume}[{label}]"
        )
        labels.append(f"[{label}]")
        input_index += 1
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[mix]")
    return ";".join(filters)


def enrich_render_plan(
    timeline: Timeline,
    db: Session,
    plan: dict | None = None,
    settings: AudioSettings | None = None,
    srt_path: Path | None = None,
) -> dict:
    plan = dict(plan or timeline.render_plan_json)
    settings = settings or get_or_create_settings(timeline.project_id, db)
    if srt_path is None:
        subtitle_item = db.scalar(
            select(TimelineItem).where(
                TimelineItem.timeline_id == timeline.id,
                TimelineItem.track == TimelineTrack.SUBTITLE,
            )
        )
        raw_path = subtitle_item.metadata_json.get("srt_path") if subtitle_item else None
        srt_path = Path(raw_path) if raw_path else None
    ambient_items = list(
        db.scalars(
            select(TimelineItem).where(
                TimelineItem.timeline_id == timeline.id,
                TimelineItem.track == TimelineTrack.AMBIENT,
            )
        )
    )
    plan["subtitles"] = {
        "enabled": settings.subtitles_enabled,
        "srt_path": str(srt_path) if srt_path else None,
        "style": subtitle_style(settings),
    }
    plan["audio_mix"] = {
        "voice_first": True,
        "target_loudness_lufs": -16,
        "true_peak_db": -1.5,
        "limiter": 0.95,
        "music_ducking": settings.music_enabled,
        "ffmpeg_filter": build_audio_filter(
            settings, settings.music_enabled, ambient_items, timeline.duration
        ),
    }
    return plan


def _audio_item(
    timeline: Timeline,
    order: int,
    asset: AudioAsset,
    track: TimelineTrack,
    volume: float,
    start: float = 0,
    end: float | None = None,
) -> TimelineItem:
    item_end = timeline.duration if end is None else min(end, timeline.duration)
    return TimelineItem(
        timeline_id=timeline.id,
        track=track,
        order=order,
        start_time=start,
        end_time=item_end,
        source_in=0,
        source_out=min(asset.duration, item_end - start),
        transition="NONE",
        effect="VOICE_DUCKED" if track == TimelineTrack.MUSIC else "LOW_VOLUME_AMBIENT",
        metadata_json={
            "audio_asset_id": asset.id,
            "source_path": asset.path,
            "preview_url": asset.public_url,
            "volume": volume,
            "loop": asset.duration < item_end - start,
            "license": asset.license,
            "source_name": asset.source_name,
        },
    )
