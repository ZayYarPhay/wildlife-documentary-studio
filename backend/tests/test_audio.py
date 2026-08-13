import shutil
import subprocess
from pathlib import Path

from test_timeline import timeline_project
from test_voice import wav_bytes

from app.db.session import SessionLocal
from app.models.audio import AudioSettings
from app.services.audio import build_audio_filter, srt_timestamp


def test_srt_generation_uses_transcript_timestamps(client):
    project, _, _ = timeline_project(client)
    timeline = client.post(f"/api/projects/{project['id']}/timeline/build").json()["current"]
    response = client.get(f"/api/timelines/{timeline['id']}/subtitles.srt")
    assert response.status_code == 200
    assert "00:00:00,000 -->" in response.text
    assert "\n1\n" not in response.text[:2]
    assert srt_timestamp(3661.234) == "01:01:01,234"


def test_music_requires_license_and_is_ducked_under_voice(client):
    project, _, _ = timeline_project(client)
    client.post(f"/api/projects/{project['id']}/timeline/build")
    missing_license = client.post(
        f"/api/projects/{project['id']}/audio/assets",
        files={"file": ("music.wav", wav_bytes(1), "audio/wav")},
        data={"kind": "MUSIC", "source_name": "Composer"},
    )
    assert missing_license.status_code == 422
    uploaded = client.post(
        f"/api/projects/{project['id']}/audio/assets",
        files={"file": ("music.wav", wav_bytes(1), "audio/wav")},
        data={
            "kind": "MUSIC",
            "source_name": "Test composer",
            "license": "CC0-1.0",
        },
    )
    assert uploaded.status_code == 201
    music = uploaded.json()["assets"][0]
    configured = client.patch(
        f"/api/projects/{project['id']}/audio/settings",
        json={
            **uploaded.json()["settings"],
            "music_enabled": True,
            "music_asset_id": music["id"],
            "music_volume": 0.15,
        },
    )
    assert configured.status_code == 200
    plan = configured.json()["mix_plan"]
    assert plan["voice_first"] is True
    assert "sidechaincompress" in plan["ffmpeg_filter"]
    assert "alimiter=limit=0.95" in plan["ffmpeg_filter"]
    timeline = client.get(f"/api/projects/{project['id']}/timeline").json()["current"]
    music_items = [item for item in timeline["items"] if item["track"] == "MUSIC"]
    assert len(music_items) == 1
    assert music_items[0]["metadata_json"]["license"] == "CC0-1.0"
    project_state = client.get(f"/api/projects/{project['id']}").json()
    assert project_state["status"] == "AUDIO_REVIEW"
    assert project_state["current_phase"] == "AUDIO_REVIEW"


def test_ambient_must_be_assigned_to_project_scene(client):
    project, scenes, _ = timeline_project(client)
    client.post(f"/api/projects/{project['id']}/timeline/build")
    response = client.post(
        f"/api/projects/{project['id']}/audio/assets",
        files={"file": ("forest.wav", wav_bytes(1), "audio/wav")},
        data={
            "kind": "AMBIENT",
            "source_name": "Field recording",
            "license": "CC BY 4.0",
            "scene_id": scenes[0]["id"],
        },
    )
    assert response.status_code == 201
    settings = response.json()["settings"]
    configured = client.patch(
        f"/api/projects/{project['id']}/audio/settings",
        json={**settings, "ambient_enabled": True},
    )
    assert configured.status_code == 200
    timeline = client.get(f"/api/projects/{project['id']}/timeline").json()["current"]
    ambient_items = [item for item in timeline["items"] if item["track"] == "AMBIENT"]
    assert len(ambient_items) == 1
    assert "adelay=" in configured.json()["mix_plan"]["ffmpeg_filter"]


def test_ffmpeg_voice_first_filter_smoke():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    root = Path("test-audio-smoke").resolve()
    root.mkdir(exist_ok=True)
    voice = root / "voice.wav"
    music = root / "music.wav"
    output = root / "mix.wav"
    voice.write_bytes(wav_bytes(1, 8000))
    music.write_bytes(wav_bytes(1, 8000))
    db = SessionLocal()
    try:
        settings = AudioSettings(
            project_id=1,
            music_enabled=True,
            music_asset_id=1,
            music_volume=0.18,
            music_fade_in=0.1,
            music_fade_out=0.1,
            ducking_ratio=8,
            ambient_volume=0.12,
        )
        audio_filter = build_audio_filter(settings, True, 0, 1)
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(voice),
                "-i",
                str(music),
                "-filter_complex",
                audio_filter,
                "-map",
                "[mix]",
                "-t",
                "1",
                str(output),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.decode(errors="replace")[-2000:]
        assert output.stat().st_size > 1000
    finally:
        db.close()
        for path in (output, music, voice):
            path.unlink(missing_ok=True)
        root.rmdir()
