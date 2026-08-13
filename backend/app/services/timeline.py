import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.media import MediaAsset, MediaAssetType
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.scene import Scene
from app.models.timeline import Timeline, TimelineItem, TimelineTrack
from app.models.voice import VoiceTrack, VoiceTrackStatus

logger = logging.getLogger(__name__)
DYNAMIC_WARNING_CODES = {
    "VISUAL_GAP",
    "VISUAL_OVERLAP",
    "DURATION_MISMATCH",
    "VOICE_ITEM_INVALID",
    "INVALID_ITEM_RANGE",
}
IMAGE_TYPES = {MediaAssetType.AI_IMAGE, MediaAssetType.STOCK_IMAGE}
VIDEO_TYPES = {MediaAssetType.AI_VIDEO, MediaAssetType.STOCK_VIDEO}


def build_timeline(project: Project, db: Session) -> Timeline:
    voice = db.scalar(
        select(VoiceTrack)
        .where(VoiceTrack.project_id == project.id, VoiceTrack.status == VoiceTrackStatus.APPLIED)
        .order_by(VoiceTrack.created_at.desc(), VoiceTrack.id.desc())
    )
    if voice is None:
        raise ValueError("Apply an aligned voice-over before building the timeline")
    scenes = list(
        db.scalars(select(Scene).where(Scene.project_id == project.id).order_by(Scene.order))
    )
    if not scenes:
        raise ValueError("Generate scenes before building the timeline")
    version = (
        db.scalar(select(func.max(Timeline.version)).where(Timeline.project_id == project.id)) or 0
    ) + 1
    timeline = Timeline(
        project_id=project.id,
        voice_track_id=voice.id,
        version=version,
        duration=voice.duration,
        output_resolution=project.output_resolution,
        fps=get_settings().timeline_fps,
        valid=False,
        warnings_json=[],
        render_plan_json={},
    )
    project.status = ProjectStatus.TIMELINE_BUILDING
    project.current_phase = ProjectPhase.TIMELINE
    db.add(timeline)
    db.flush()
    warnings: list[dict[str, Any]] = []
    order = 1
    cursor = 0.0
    previous_asset: MediaAsset | None = None
    tolerance = get_settings().timeline_gap_tolerance_seconds
    for scene in scenes:
        if scene.start_time > cursor + tolerance:
            if previous_asset is not None:
                db.add(
                    _filler_item(
                        timeline.id, order, cursor, scene.start_time, previous_asset, "SCENE_GAP"
                    )
                )
                order += 1
                warnings.append(
                    _warning(
                        "AUTO_GAP_FILL",
                        "Scene gap filled using the previous visual.",
                        scene.id,
                        "WARNING",
                    )
                )
            else:
                warnings.append(
                    _warning(
                        "VISUAL_GAP",
                        "Timeline starts with an unfilled visual gap.",
                        scene.id,
                        "ERROR",
                    )
                )
        elif scene.start_time < cursor - tolerance:
            warnings.append(
                _warning(
                    "VISUAL_OVERLAP",
                    "Scene timing overlaps the previous visual.",
                    scene.id,
                    "ERROR",
                )
            )

        asset = (
            db.get(MediaAsset, scene.preferred_media_asset_id)
            if scene.preferred_media_asset_id
            else None
        )
        if asset is None or asset.scene_id != scene.id:
            if previous_asset is not None:
                db.add(
                    _filler_item(
                        timeline.id,
                        order,
                        scene.start_time,
                        scene.end_time,
                        previous_asset,
                        "MISSING_VISUAL",
                    )
                )
                order += 1
                warnings.append(
                    _warning(
                        "MISSING_VISUAL_AUTOFILLED",
                        "Missing scene visual filled using the previous selected asset.",
                        scene.id,
                        "WARNING",
                    )
                )
            else:
                warnings.append(
                    _warning(
                        "MISSING_VISUAL", "Scene has no selected visual asset.", scene.id, "ERROR"
                    )
                )
        else:
            source_probe = None
            if not asset.local_path or not Path(asset.local_path).is_file():
                warnings.append(
                    _warning(
                        "SOURCE_NOT_LOCAL",
                        "Selected visual is not available in managed local storage.",
                        scene.id,
                        "ERROR",
                    )
                )
            elif asset.type in VIDEO_TYPES:
                try:
                    source_probe = probe_video_source(Path(asset.local_path))
                except RuntimeError as exc:
                    warnings.append(_warning("INVALID_VIDEO_SOURCE", str(exc), scene.id, "ERROR"))
            if asset.type not in IMAGE_TYPES | VIDEO_TYPES:
                warnings.append(
                    _warning(
                        "UNSUPPORTED_VISUAL",
                        "Selected asset type cannot be rendered on the visual track.",
                        scene.id,
                        "ERROR",
                    )
                )
            item = _visual_item(timeline, order, scene, asset, source_probe)
            db.add(item)
            order += 1
            previous_asset = asset
        cursor = max(cursor, scene.end_time)

    if cursor < voice.duration - tolerance:
        if previous_asset is not None:
            db.add(
                _filler_item(
                    timeline.id, order, cursor, voice.duration, previous_asset, "VOICE_TAIL"
                )
            )
            order += 1
            warnings.append(
                _warning(
                    "AUTO_GAP_FILL",
                    "Voice-over tail filled using the final visual.",
                    None,
                    "WARNING",
                )
            )
        else:
            warnings.append(
                _warning("VISUAL_GAP", "Voice-over tail has no visual coverage.", None, "ERROR")
            )
    elif cursor > voice.duration + tolerance:
        warnings.append(
            _warning(
                "DURATION_MISMATCH", "Visual scenes extend beyond the voice-over.", None, "ERROR"
            )
        )
    db.add(
        TimelineItem(
            timeline_id=timeline.id,
            track=TimelineTrack.VOICE,
            order=order,
            voice_track_id=voice.id,
            start_time=0,
            end_time=voice.duration,
            source_in=0,
            source_out=voice.duration,
            transition="NONE",
            effect=None,
            metadata_json={"source_path": voice.path, "preview_url": voice.public_url},
        )
    )
    db.flush()
    validate_timeline(timeline, db, warnings)
    project.status = ProjectStatus.TIMELINE_REVIEW
    project.current_phase = ProjectPhase.TIMELINE_REVIEW
    db.commit()
    return load_timeline(timeline.id, db)


def validate_timeline(
    timeline: Timeline, db: Session, base_warnings: list[dict[str, Any]] | None = None
) -> Timeline:
    items = list(
        db.scalars(
            select(TimelineItem)
            .where(TimelineItem.timeline_id == timeline.id)
            .order_by(TimelineItem.order)
        )
    )
    warnings = (
        base_warnings
        if base_warnings is not None
        else [
            item for item in timeline.warnings_json if item.get("code") not in DYNAMIC_WARNING_CODES
        ]
    )
    tolerance = get_settings().timeline_gap_tolerance_seconds
    visuals = sorted(
        (item for item in items if item.track == TimelineTrack.VISUAL),
        key=lambda item: (item.start_time, item.order),
    )
    cursor = 0.0
    for item in visuals:
        if item.end_time <= item.start_time:
            warnings.append(
                _warning(
                    "INVALID_ITEM_RANGE",
                    "Visual item has an invalid time range.",
                    item.scene_id,
                    "ERROR",
                )
            )
            continue
        if item.start_time > cursor + tolerance:
            warnings.append(
                _warning(
                    "VISUAL_GAP",
                    f"Visual gap from {cursor:.3f}s to {item.start_time:.3f}s.",
                    item.scene_id,
                    "ERROR",
                )
            )
        if item.start_time < cursor - tolerance:
            warnings.append(
                _warning(
                    "VISUAL_OVERLAP",
                    f"Visual overlap begins at {item.start_time:.3f}s.",
                    item.scene_id,
                    "ERROR",
                )
            )
        cursor = max(cursor, item.end_time)
    if cursor < timeline.duration - tolerance:
        warnings.append(
            _warning(
                "VISUAL_GAP",
                f"Visual coverage ends at {cursor:.3f}s before voice-over ends.",
                None,
                "ERROR",
            )
        )
    if cursor > timeline.duration + tolerance:
        warnings.append(
            _warning(
                "DURATION_MISMATCH", "Visual coverage exceeds voice-over duration.", None, "ERROR"
            )
        )
    voices = [item for item in items if item.track == TimelineTrack.VOICE]
    if (
        len(voices) != 1
        or abs(voices[0].start_time) > tolerance
        or abs(voices[0].end_time - timeline.duration) > tolerance
    ):
        warnings.append(
            _warning(
                "VOICE_ITEM_INVALID",
                "Voice track must cover the exact timeline duration.",
                None,
                "ERROR",
            )
        )
    timeline.warnings_json = _deduplicate_warnings(warnings)
    timeline.valid = not any(item.get("severity") == "ERROR" for item in timeline.warnings_json)
    timeline.render_plan_json = build_render_plan(timeline, items)
    db.flush()
    return timeline


def build_render_plan(timeline: Timeline, items: list[TimelineItem]) -> dict[str, Any]:
    tracks: dict[str, list[dict[str, Any]]] = {track.value: [] for track in TimelineTrack}
    for item in items:
        tracks[item.track.value].append(
            {
                "item_id": item.id,
                "scene_id": item.scene_id,
                "asset_id": item.asset_id,
                "voice_track_id": item.voice_track_id,
                "timeline_in": item.start_time,
                "timeline_out": item.end_time,
                "source_in": item.source_in,
                "source_out": item.source_out,
                "transition": item.transition,
                "effect": item.effect,
                "operations": item.metadata_json.get("operations", []),
                "source_path": item.metadata_json.get("source_path"),
            }
        )
    return {
        "schema_version": 1,
        "duration": timeline.duration,
        "output": {"resolution": timeline.output_resolution, "fps": timeline.fps},
        "transition_policy": "minimal documentary cuts",
        "tracks": tracks,
    }


def load_timeline(timeline_id: int, db: Session) -> Timeline:
    timeline = db.scalar(
        select(Timeline).where(Timeline.id == timeline_id).options(selectinload(Timeline.items))
    )
    if timeline is None:
        raise ValueError("Timeline not found")
    return timeline


def ffmpeg_item_command(
    item: TimelineItem, output_path: Path, resolution: str, fps: int
) -> list[str]:
    ffmpeg = shutil.which(get_settings().ffmpeg_path)
    source = item.metadata_json.get("source_path")
    if ffmpeg is None or not source:
        raise RuntimeError("FFmpeg and a local source are required")
    width, height = resolution.split("x", maxsplit=1)
    duration = item.end_time - item.start_time
    common_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},format=yuv420p"
    if item.effect == "KEN_BURNS_SUBTLE":
        ken_burns = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0005,1.05)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},format=yuv420p"
        )
        return [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            source,
            "-t",
            str(duration),
            "-vf",
            ken_burns,
            "-an",
            "-c:v",
            "libx264",
            str(output_path),
        ]
    if item.effect == "HOLD_LAST_FRAME":
        return [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            source,
            "-t",
            str(duration),
            "-vf",
            common_filter,
            "-an",
            "-c:v",
            "libx264",
            str(output_path),
        ]
    command = [ffmpeg, "-y"]
    if item.metadata_json.get("loop_count", 1) > 1:
        command.extend(["-stream_loop", "-1"])
    command.extend(
        [
            "-ss",
            str(item.source_in),
            "-i",
            source,
            "-t",
            str(duration),
            "-vf",
            common_filter,
            "-an",
            "-c:v",
            "libx264",
            str(output_path),
        ]
    )
    return command


def run_ffmpeg_logged(command: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    logger.info("FFmpeg command started", extra={"command": command})
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr[-4000:] if completed.stderr else "No FFmpeg diagnostic output"
        logger.error(
            "FFmpeg command failed",
            extra={"returncode": completed.returncode, "stderr": diagnostic},
        )
        raise RuntimeError(f"FFmpeg failed: {diagnostic}")
    logger.info("FFmpeg command completed", extra={"returncode": completed.returncode})
    return completed


def probe_video_source(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which(get_settings().ffprobe_path)
    if ffprobe is None:
        raise RuntimeError("FFprobe is required to validate timeline video sources")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Selected video failed FFprobe validation")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    duration = float(payload.get("format", {}).get("duration", 0))
    if not streams or streams[0].get("codec_type") != "video" or duration <= 0:
        raise RuntimeError("Selected video has no valid video stream or duration")
    return {
        "width": int(streams[0]["width"]),
        "height": int(streams[0]["height"]),
        "duration": round(duration, 3),
        "frame_rate": streams[0].get("avg_frame_rate"),
    }


def _visual_item(
    timeline: Timeline,
    order: int,
    scene: Scene,
    asset: MediaAsset,
    source_probe: dict[str, Any] | None = None,
) -> TimelineItem:
    duration = scene.end_time - scene.start_time
    base = {
        "source_path": asset.local_path,
        "preview_url": asset.preview_url,
        "asset_type": asset.type.value,
        "source_probe": source_probe,
    }
    if asset.type in IMAGE_TYPES:
        effect = "KEN_BURNS_SUBTLE"
        source_out = None
        base["operations"] = [
            {
                "op": "scale_crop",
                "resolution": timeline.output_resolution,
                "preserve_aspect": True,
                "black_borders": False,
            },
            {
                "op": "ken_burns",
                "zoom_start": 1.0,
                "zoom_end": 1.05,
                "pan": "center",
                "duration": duration,
            },
            {"op": "normalize_fps", "fps": timeline.fps},
        ]
    elif asset.type in VIDEO_TYPES:
        effect = "VIDEO_TRIM"
        available = (
            float(source_probe.get("duration")) if source_probe else asset.duration or duration
        )
        source_out = min(available, duration)
        loop_count = max(1, math.ceil(duration / max(available, 0.001)))
        base["loop_count"] = loop_count
        base["operations"] = [
            {"op": "trim", "source_in": 0, "source_out": source_out},
            {"op": "loop", "count": loop_count, "enabled": loop_count > 1},
            {
                "op": "scale_crop",
                "resolution": timeline.output_resolution,
                "preserve_aspect": True,
                "black_borders": False,
            },
            {"op": "normalize_fps", "fps": timeline.fps},
        ]
    else:
        effect = "UNSUPPORTED"
        source_out = None
        base["operations"] = []
    return TimelineItem(
        timeline_id=timeline.id,
        track=TimelineTrack.VISUAL,
        order=order,
        scene_id=scene.id,
        asset_id=asset.id,
        start_time=scene.start_time,
        end_time=scene.end_time,
        source_in=0,
        source_out=source_out,
        transition="NONE" if order == 1 else "CUT",
        effect=effect,
        metadata_json=base,
    )


def _filler_item(
    timeline_id: int, order: int, start: float, end: float, asset: MediaAsset, reason: str
) -> TimelineItem:
    is_image = asset.type in IMAGE_TYPES
    return TimelineItem(
        timeline_id=timeline_id,
        track=TimelineTrack.VISUAL,
        order=order,
        scene_id=None,
        asset_id=asset.id,
        start_time=start,
        end_time=end,
        source_in=0,
        source_out=None if is_image else min(asset.duration or end - start, end - start),
        transition="CUT",
        effect="HOLD_LAST_FRAME" if is_image else "LOOP_FILL",
        metadata_json={
            "source_path": asset.local_path,
            "preview_url": asset.preview_url,
            "asset_type": asset.type.value,
            "auto_fill_reason": reason,
            "loop_count": 1
            if is_image
            else max(1, math.ceil((end - start) / max(asset.duration or end - start, 0.001))),
            "operations": [{"op": "auto_fill", "reason": reason, "duration": end - start}],
        },
    )


def _warning(code: str, message: str, scene_id: int | None, severity: str) -> dict[str, Any]:
    return {"code": code, "message": message, "scene_id": scene_id, "severity": severity}


def _deduplicate_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for warning in warnings:
        unique[(warning.get("code"), warning.get("message"), warning.get("scene_id"))] = warning
    return list(unique.values())
