from typing import Any

from app.providers.base import TranscriptionProvider


class MockTranscriptionProvider(TranscriptionProvider):
    name = "mock-transcription"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def transcribe(self, audio_path: str, **options: Any) -> dict[str, Any]:
        scene_texts = [
            str(text).strip() for text in options.get("scene_texts", []) if str(text).strip()
        ]
        duration = float(options["duration"])
        if not scene_texts:
            return {"language": options.get("language", "unknown"), "segments": []}
        weights = [max(1, len(text.split())) for text in scene_texts]
        total = sum(weights)
        cursor = 0.0
        segments = []
        for index, (text, weight) in enumerate(zip(scene_texts, weights, strict=True)):
            end = duration if index == len(scene_texts) - 1 else cursor + duration * weight / total
            segments.append(
                {
                    "start_time": round(cursor, 3),
                    "end_time": round(end, 3),
                    "text": text,
                    "confidence": 0.99,
                }
            )
            cursor = end
        return {
            "language": options.get("language", "unknown"),
            "segments": segments,
            "metadata_json": {"mock": True, "audio_path_received": bool(audio_path)},
        }
