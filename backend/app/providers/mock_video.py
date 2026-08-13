import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.providers.base import VideoGenerationProvider


class MockVideoGenerationProvider(VideoGenerationProvider):
    """Local image-to-video adapter for development; no model or API key required."""

    name = "mock-video"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def generate(self, source: str, prompt: str, **options: Any) -> dict[str, Any]:
        if "[fail]" in prompt.lower():
            raise RuntimeError("Mock video generation failure requested by prompt")
        ffmpeg = shutil.which(get_settings().ffmpeg_path)
        if ffmpeg is None:
            raise RuntimeError("FFmpeg is required by the mock video provider")
        source_path = Path(source).resolve(strict=True)
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        job_id = options.get("job_id", "video")
        output_path = output_dir / f"mock-{job_id}.mp4"
        duration = float(options["duration"])
        fps = int(options["fps"])
        width = int(options["width"])
        height = int(options["height"])
        command = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source_path),
            "-t",
            str(duration),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            timeout=get_settings().video_generation_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            diagnostic = (
                completed.stderr.strip().splitlines()[-1] if completed.stderr else "unknown"
            )
            raise RuntimeError(f"Mock FFmpeg generation failed: {diagnostic}")
        return {
            "provider_asset_id": f"mock-video-{job_id}",
            "filename": output_path.name,
            "local_path": str(output_path.resolve()),
            "width": width,
            "height": height,
            "duration": duration,
            "fps": fps,
            "mime_type": "video/mp4",
            "metadata_json": {"mock": True, "source_path": str(source_path)},
        }
