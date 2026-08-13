import shutil
import subprocess
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from test_stock_media import ready_scene
from test_voice import wav_bytes

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.scene import Scene
from app.models.timeline import TimelineItem, TimelineTrack
from app.services.timeline import ffmpeg_item_command, run_ffmpeg_logged


def timeline_project(client):
    project, _ = ready_scene(client)
    scenes = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    for scene in scenes[2:]:
        client.delete(f"/api/scenes/{scene['id']}")
    response = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("timeline.wav", wav_bytes(), "audio/wav")},
    )
    track = client.get(f"/api/projects/{project['id']}/voice").json()["active"]
    assert response.status_code == 202 and track["status"] == "READY"
    client.post(f"/api/voice-tracks/{track['id']}/apply")
    scenes = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    add_local_assets(project["id"], [scene["id"] for scene in scenes])
    return project, scenes, track


def add_local_assets(project_id: int, scene_ids: list[int]) -> None:
    root = Path(get_settings().media_root).resolve() / str(project_id) / "timeline-test"
    root.mkdir(parents=True, exist_ok=True)
    image_path = root / "still.png"
    Image.new("RGB", (320, 180), (45, 90, 60)).save(image_path)
    video_path = root / "clip.mp4"
    ffmpeg = shutil.which(get_settings().ffmpeg_path)
    assert ffmpeg
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            "2",
            "-vf",
            "format=yuv420p",
            "-r",
            "12",
            "-an",
            "-c:v",
            "libx264",
            str(video_path),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    db = SessionLocal()
    try:
        scenes = list(
            db.scalars(select(Scene).where(Scene.id.in_(scene_ids)).order_by(Scene.order))
        )
        image = MediaAsset(
            project_id=project_id,
            scene_id=scenes[0].id,
            provider="timeline-test",
            provider_asset_id="still",
            type=MediaAssetType.AI_IMAGE,
            preview_url="http://localhost:8000/media/still.png",
            download_url=None,
            source_page_url=None,
            width=320,
            height=180,
            duration=None,
            local_path=str(image_path),
            metadata_json={},
            relevance_score=1,
            status=MediaAssetStatus.SELECTED,
        )
        video = MediaAsset(
            project_id=project_id,
            scene_id=scenes[1].id,
            provider="timeline-test",
            provider_asset_id="video",
            type=MediaAssetType.AI_VIDEO,
            preview_url="http://localhost:8000/media/clip.mp4",
            download_url=None,
            source_page_url=None,
            width=320,
            height=180,
            duration=2,
            local_path=str(video_path),
            metadata_json={},
            relevance_score=1,
            status=MediaAssetStatus.SELECTED,
        )
        db.add_all([image, video])
        db.flush()
        scenes[0].preferred_media_asset_id = image.id
        scenes[1].preferred_media_asset_id = video.id
        db.commit()
    finally:
        db.close()


def test_complete_timeline_duration_image_effect_and_video_trim(client):
    project, _, track = timeline_project(client)
    response = client.post(f"/api/projects/{project['id']}/timeline/build")
    assert response.status_code == 200
    timeline = response.json()["current"]
    assert timeline["valid"] is True
    assert timeline["duration"] == track["duration"] == 120
    visuals = [item for item in timeline["items"] if item["track"] == "VISUAL"]
    voices = [item for item in timeline["items"] if item["track"] == "VOICE"]
    assert visuals[0]["effect"] == "KEN_BURNS_SUBTLE"
    assert visuals[0]["metadata_json"]["operations"][0]["black_borders"] is False
    assert visuals[1]["effect"] == "VIDEO_TRIM"
    assert visuals[1]["source_out"] == 2
    assert visuals[1]["metadata_json"]["source_probe"]["duration"] == 2
    assert visuals[1]["metadata_json"]["loop_count"] > 1
    assert len(voices) == 1 and voices[0]["end_time"] == 120
    assert timeline["render_plan_json"]["tracks"]["MUSIC"] == []
    assert timeline["render_plan_json"]["tracks"]["AMBIENT"] == []
    assert timeline["render_plan_json"]["tracks"]["SUBTITLE"] == []


def test_missing_first_visual_is_detected(client):
    project, scenes, _ = timeline_project(client)
    db = SessionLocal()
    try:
        first = db.get(Scene, scenes[0]["id"])
        first.preferred_media_asset_id = None
        db.commit()
    finally:
        db.close()
    timeline = client.post(f"/api/projects/{project['id']}/timeline/build").json()["current"]
    codes = {warning["code"] for warning in timeline["warnings_json"]}
    assert timeline["valid"] is False
    assert "MISSING_VISUAL" in codes
    assert "VISUAL_GAP" in codes


def test_gap_is_auto_filled_when_previous_visual_exists(client):
    project, scenes, _ = timeline_project(client)
    db = SessionLocal()
    try:
        second = db.get(Scene, scenes[1]["id"])
        second.start_time += 2
        db.commit()
    finally:
        db.close()
    timeline = client.post(f"/api/projects/{project['id']}/timeline/build").json()["current"]
    fillers = [
        item
        for item in timeline["items"]
        if item["metadata_json"].get("auto_fill_reason") == "SCENE_GAP"
    ]
    assert len(fillers) == 1
    assert "AUTO_GAP_FILL" in {warning["code"] for warning in timeline["warnings_json"]}
    assert timeline["valid"] is True


def test_overlap_and_manual_edit_revalidation(client):
    project, _, _ = timeline_project(client)
    timeline = client.post(f"/api/projects/{project['id']}/timeline/build").json()["current"]
    visuals = [item for item in timeline["items"] if item["track"] == "VISUAL"]
    response = client.patch(
        f"/api/timeline-items/{visuals[1]['id']}",
        json={"start_time": visuals[0]["end_time"] - 1},
    )
    assert response.status_code == 200
    validated = client.post(f"/api/timelines/{timeline['id']}/validate").json()
    assert validated["valid"] is False
    assert "VISUAL_OVERLAP" in {warning["code"] for warning in validated["warnings_json"]}


def test_rebuild_preserves_timeline_versions(client):
    project, _, _ = timeline_project(client)
    first = client.post(f"/api/projects/{project['id']}/timeline/build").json()["current"]
    second_bundle = client.post(f"/api/projects/{project['id']}/timeline/build").json()
    assert second_bundle["current"]["version"] == first["version"] + 1
    assert len(second_bundle["versions"]) == 2


def test_small_ffmpeg_item_smoke():
    root = Path("test-timeline-smoke").resolve()
    root.mkdir(exist_ok=True)
    source = root / "source.png"
    output = root / "smoke.mp4"
    try:
        Image.new("RGB", (160, 90), (20, 70, 40)).save(source)
        item = TimelineItem(
            timeline_id=1,
            track=TimelineTrack.VISUAL,
            order=1,
            start_time=0,
            end_time=0.5,
            source_in=0,
            transition="NONE",
            effect="KEN_BURNS_SUBTLE",
            metadata_json={"source_path": str(source)},
        )
        command = ffmpeg_item_command(item, output, "320x180", 12)
        assert "zoompan" in command[command.index("-vf") + 1]
        completed = run_ffmpeg_logged(command, timeout=30)
        assert completed.returncode == 0
        assert output.stat().st_size > 1024
    finally:
        output.unlink(missing_ok=True)
        source.unlink(missing_ok=True)
        root.rmdir()
