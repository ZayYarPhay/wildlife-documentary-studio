import argparse
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from PIL import Image, ImageDraw

ALLOWED_JOB_TYPES = {"AI_IMAGE", "AI_VIDEO"}
MAX_INPUT_BYTES = 1_073_741_824
STATE = {"status": "starting", "worker_id": "", "current_job_id": None, "last_error": None}


class WorkerClient:
    def __init__(self) -> None:
        self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
        self.token = os.getenv("WORKER_AUTH_TOKEN", "")
        self.worker_id = os.getenv("WORKER_ID", f"worker-{os.getpid()}")
        self.poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
        if not self.token:
            raise RuntimeError("WORKER_AUTH_TOKEN is required")
        STATE.update(status="idle", worker_id=self.worker_id)
        self.client = httpx.Client(
            base_url=self.backend_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=httpx.Timeout(120, connect=15),
        )

    def claim(self) -> dict | None:
        response = self.client.post(
            "/api/worker/jobs/claim",
            json={
                "worker_id": self.worker_id,
                "accepted_job_types": sorted(ALLOWED_JOB_TYPES),
            },
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    def process(self, claim: dict) -> None:
        job = claim["job"]
        payload = claim["payload"]
        job_id = int(job["id"])
        if payload.get("job_type") not in ALLOWED_JOB_TYPES:
            raise RuntimeError("Backend returned a non-whitelisted job type")
        callbacks = self._callbacks(payload, job_id)
        STATE.update(status="running", current_job_id=job_id, last_error=None)
        self._progress(callbacks["progress_path"], 0.1)
        started = time.monotonic()
        temp_root_value = os.getenv("WORKER_TEMP_ROOT")
        temp_root = Path(temp_root_value).resolve() if temp_root_value else None
        if temp_root is not None:
            temp_root.mkdir(parents=True, exist_ok=True)
        root = (temp_root or Path.cwd()) / f"wildlife-worker-{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=False)
        try:
            inputs = [self._download(reference, root) for reference in claim["input_assets"]]
            if payload["job_type"] == "AI_IMAGE":
                output = self._mock_image(payload, root)
                mime_type = "image/png"
            else:
                if len(inputs) != 1:
                    raise RuntimeError("AI_VIDEO requires exactly one input asset")
                output = self._mock_video(payload, inputs[0], root)
                mime_type = "video/mp4"
            self._progress(callbacks["progress_path"], 0.85)
            result = {
                "model": "standalone-mock-worker",
                "runtime_seconds": round(time.monotonic() - started, 3),
                "seed": payload.get("parameters", {}).get("seed"),
            }
            with output.open("rb") as artifact:
                response = self.client.post(
                    callbacks["complete_path"],
                    data={"worker_id": self.worker_id, "result_json": json.dumps(result)},
                    files={"file": (output.name, artifact, mime_type)},
                )
            response.raise_for_status()
        finally:
            shutil.rmtree(root, ignore_errors=True)
        STATE.update(status="idle", current_job_id=None)

    def fail(self, job_id: int, fail_path: str, exc: Exception) -> None:
        message = str(exc)[:4000] or exc.__class__.__name__
        STATE.update(status="error", current_job_id=None, last_error=message)
        response = self.client.post(
            fail_path,
            json={
                "worker_id": self.worker_id,
                "error_message": message,
                "diagnostics": {"exception_type": exc.__class__.__name__},
            },
        )
        response.raise_for_status()

    def run(self, once: bool = False) -> None:
        while True:
            claim = self.claim()
            if claim is None:
                STATE["status"] = "idle"
                if once:
                    return
                time.sleep(self.poll_seconds)
                continue
            job_id = int(claim["job"]["id"])
            fail_path = self._callbacks(claim["payload"], job_id)["fail_path"]
            try:
                self.process(claim)
            except Exception as exc:  # worker boundary reports durable diagnostics
                try:
                    self.fail(job_id, fail_path, exc)
                except Exception as report_error:  # noqa: BLE001 - preserve both remote errors
                    STATE.update(status="error", last_error=f"{exc}; report failed: {report_error}")
                if once:
                    raise

    def _progress(self, progress_path: str, progress: float) -> None:
        response = self.client.post(
            progress_path,
            json={"worker_id": self.worker_id, "progress": progress},
        )
        response.raise_for_status()

    @staticmethod
    def _callbacks(payload: dict, job_id: int) -> dict[str, str]:
        callbacks = payload.get("callback_metadata")
        expected = {
            "progress_path": f"/api/worker/jobs/{job_id}/progress",
            "complete_path": f"/api/worker/jobs/{job_id}/complete",
            "fail_path": f"/api/worker/jobs/{job_id}/fail",
        }
        if callbacks != expected:
            raise RuntimeError("Backend returned invalid worker callback metadata")
        return expected

    def _download(self, reference: dict, root: Path) -> Path:
        relative = str(reference["download_url"])
        url = urljoin(f"{self.backend_url}/", relative.lstrip("/"))
        backend = urlparse(self.backend_url)
        target = urlparse(url)
        if target.scheme not in {"http", "https"} or target.netloc != backend.netloc:
            raise RuntimeError("Worker input URL is outside the configured backend origin")
        path = root / f"input-{int(reference['asset_id'])}.bin"
        size = 0
        with self.client.stream("GET", url) as response:
            response.raise_for_status()
            with path.open("xb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_INPUT_BYTES:
                        raise RuntimeError("Worker input exceeds size limit")
                    output.write(chunk)
        if size == 0:
            raise RuntimeError("Worker input is empty")
        return path

    @staticmethod
    def _mock_image(payload: dict, root: Path) -> Path:
        parameters = payload["parameters"]
        width, height = int(parameters["width"]), int(parameters["height"])
        seed = parameters.get("seed")
        if seed is None:
            seed = int(hashlib.sha256(payload["prompt"].encode()).hexdigest()[:8], 16)
        color = ((seed >> 16) & 127, (seed >> 8) & 127, seed & 127)
        image = Image.new("RGB", (width, height), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, height * 3 // 4, width, height), fill=(12, 24, 18))
        draw.text((40, height * 3 // 4 + 40), "STANDALONE MOCK GPU WORKER", fill="white")
        output = root / "result.png"
        image.save(output, "PNG", optimize=True)
        return output

    @staticmethod
    def _mock_video(payload: dict, source: Path, root: Path) -> Path:
        ffmpeg = shutil.which(os.getenv("FFMPEG_PATH", "ffmpeg"))
        if ffmpeg is None:
            raise RuntimeError("FFmpeg is required for mock video worker jobs")
        parameters = payload["parameters"]
        width, height = int(parameters["width"]), int(parameters["height"])
        output = root / "result.mp4"
        command = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-t",
            str(float(parameters["duration"])),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
            "-r",
            str(int(parameters["fps"])),
            "-an",
            "-c:v",
            "libx264",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"FFmpeg worker render failed: {completed.stderr[-2000:]}")
        return output


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(STATE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def start_health_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Wildlife Documentary Studio generation worker")
    parser.add_argument("--once", action="store_true", help="Claim at most one job and exit")
    parser.add_argument("--health-port", type=int, default=int(os.getenv("WORKER_HEALTH_PORT", "8081")))
    args = parser.parse_args()
    server = start_health_server(args.health_port)
    try:
        WorkerClient().run(once=args.once)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
