import io
import wave

from test_stock_media import ready_scene

from app.core.config import get_settings


def wav_bytes(duration: float = 120, sample_rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * int(duration * sample_rate))
    return buffer.getvalue()


def voice_project(client):
    project, _ = ready_scene(client)
    script_before = client.get(f"/api/projects/{project['id']}/script").json()["current"][
        "full_text"
    ]
    response = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("my narration.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 202
    bundle = client.get(f"/api/projects/{project['id']}/voice").json()
    return project, bundle, script_before


def test_secure_file_validation(client):
    project, _ = ready_scene(client)
    bad_extension = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("voice.exe", b"not audio", "application/octet-stream")},
    )
    assert bad_extension.status_code == 422
    bad_mime = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("voice.wav", wav_bytes(1), "text/plain")},
    )
    assert bad_mime.status_code == 422
    bad_signature = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("voice.mp3", b"this is not mp3", "audio/mpeg")},
    )
    assert bad_signature.status_code == 422


def test_upload_size_limit(client, monkeypatch):
    project, _ = ready_scene(client)
    monkeypatch.setattr(get_settings(), "voice_upload_max_bytes", 100)
    response = client.post(
        f"/api/projects/{project['id']}/voice/upload",
        files={"file": ("voice.wav", wav_bytes(1), "audio/wav")},
    )
    assert response.status_code == 422
    assert "size limit" in response.json()["error"]["message"]


def test_upload_transcription_timestamps_and_safe_filename(client):
    _, bundle, _ = voice_project(client)
    track = bundle["active"]
    assert track["status"] == "READY"
    assert track["duration"] == 120
    assert track["mime_type"] == "audio/wav"
    assert track["original_filename"] == "my narration.wav"
    assert "my%20narration" not in track["public_url"]
    assert len(track["segments"]) == len(track["alignments"])
    assert track["segments"][0]["start_time"] == 0
    assert track["segments"][-1]["end_time"] == 120
    assert all(item["end_time"] > item["start_time"] for item in track["segments"])
    audio = client.get(track["public_url"].replace("http://localhost:8000", ""))
    assert audio.status_code == 200
    assert audio.headers["content-type"] in {"audio/x-wav", "audio/wav", "audio/wave"}


def test_alignment_apply_uses_voice_duration_and_preserves_script(client):
    project, bundle, script_before = voice_project(client)
    track = bundle["active"]
    scenes_before = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    narration_before = [scene["narration_text"] for scene in scenes_before]
    stock = client.post(f"/api/scenes/{scenes_before[0]['id']}/stock/search").json()
    selected_asset = stock["assets"][0]
    client.post(f"/api/media-assets/{selected_asset['id']}/select")
    response = client.post(f"/api/voice-tracks/{track['id']}/apply")
    assert response.status_code == 200
    assert response.json()["active"]["status"] == "APPLIED"
    scenes_after = client.get(f"/api/projects/{project['id']}/scenes").json()["scenes"]
    assert scenes_after[0]["start_time"] == 0
    assert scenes_after[-1]["end_time"] == 120
    assert sum(scene["target_duration"] for scene in scenes_after) == 120
    assert [scene["narration_text"] for scene in scenes_after] == narration_before
    assert scenes_after[0]["preferred_media_asset_id"] == selected_asset["id"]
    assert client.get(f"/api/scenes/{scenes_after[0]['id']}/stock").json()["assets"]
    script_after = client.get(f"/api/projects/{project['id']}/script").json()["current"][
        "full_text"
    ]
    assert script_after == script_before


def test_transcript_manual_correction_recomputes_mismatch(client):
    project, bundle, _ = voice_project(client)
    track = bundle["active"]
    first = track["segments"][0]
    edited = client.patch(
        f"/api/transcript-segments/{first['id']}",
        json={"text": "completely unrelated manual narration words"},
    )
    assert edited.status_code == 200
    refreshed = client.get(f"/api/projects/{project['id']}/voice").json()["active"]
    first_alignment = min(refreshed["alignments"], key=lambda item: item["recommended_start"])
    assert first_alignment["mismatch"] is True
    assert first_alignment["confidence"] < 0.55


def test_retranscribe_preserves_track_and_replaces_segments(client):
    project, bundle, _ = voice_project(client)
    track = bundle["active"]
    first = track["segments"][0]
    original_text = first["text"]
    client.patch(
        f"/api/transcript-segments/{first['id']}",
        json={"text": "manual temporary correction"},
    )
    response = client.post(f"/api/voice-tracks/{track['id']}/transcribe")
    assert response.status_code == 202
    refreshed = client.get(f"/api/projects/{project['id']}/voice").json()["active"]
    assert refreshed["id"] == track["id"]
    assert refreshed["status"] == "READY"
    assert refreshed["segments"][0]["text"] == original_text
    assert len(refreshed["segments"]) == len(track["segments"])


def test_manual_alignment_range_validation(client):
    _, bundle, _ = voice_project(client)
    alignment = bundle["active"]["alignments"][0]
    invalid = client.patch(
        f"/api/voice-alignments/{alignment['id']}",
        json={"recommended_start": 10, "recommended_end": 5},
    )
    assert invalid.status_code == 422
