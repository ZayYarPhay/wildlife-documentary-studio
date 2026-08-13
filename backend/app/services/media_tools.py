import shutil
import subprocess

from app.core.config import get_settings


def media_tool_status() -> dict[str, dict[str, str | bool | None]]:
    settings = get_settings()
    result: dict[str, dict[str, str | bool | None]] = {}
    for name, configured_path in {
        "ffmpeg": settings.ffmpeg_path,
        "ffprobe": settings.ffprobe_path,
    }.items():
        path = shutil.which(configured_path)
        version = None
        if path:
            completed = subprocess.run(
                [path, "-version"], capture_output=True, text=True, timeout=3, check=False
            )
            version = completed.stdout.splitlines()[0] if completed.stdout else None
        result[name] = {"available": bool(path), "path": path, "version": version}
    return result
