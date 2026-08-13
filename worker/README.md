# Separate generation worker

The Phase 11 worker is a process/container that claims normalized `AI_IMAGE` and `AI_VIDEO` jobs from the FastAPI backend. It has no database, research, UI or arbitrary-command access.

## Local process

Configure the backend:

```env
GENERATION_EXECUTION_MODE=worker
WORKER_AUTH_TOKEN=replace-with-a-long-random-secret
```

Start the backend, then run the worker from the repository root:

```powershell
$env:BACKEND_URL='http://localhost:8000'
$env:WORKER_AUTH_TOKEN='replace-with-a-long-random-secret'
$env:WORKER_ID='local-gpu-worker'
$env:WORKER_TEMP_ROOT='.worker-temp'
python -m worker.worker
```

`python -m worker.worker --once` claims at most one job. Worker health is exposed on `http://localhost:8081/health` while the process is running.

## Docker / rented GPU VM

```powershell
$env:WORKER_AUTH_TOKEN='replace-with-a-long-random-secret'
docker compose -f docker-compose.worker.yml up --build
```

For a rented GPU host, deploy only the worker image and point `BACKEND_URL` at the HTTPS backend. A real image/video provider can replace the deterministic mock methods inside the worker while retaining the same claim/progress/result protocol. Add the provider's model weights and GPU runtime to a derived image; do not put database or web-app responsibilities on that host.

## Security and operations

- Use a unique, long bearer token and TLS. Never keep `change-me-in-production` outside local development.
- The backend accepts only `AI_IMAGE` and `AI_VIDEO` payloads with bounded typed parameters.
- Payloads contain asset IDs and authenticated download URLs, never backend filesystem paths.
- Prompt text is data and is never interpolated into a shell command.
- FFmpeg is invoked with a fixed argument list and `shell=False` semantics.
- The backend controls output filenames and validates type, size, dimensions/duration and managed storage paths.
- Claims have leases. Expired claims are requeued and duplicate result delivery is idempotent.
- Preserve worker/backend logs and monitor both `/health` and `/api/worker/queue/health`.
- Current Phase 11 transfers artifacts through authenticated HTTP. Production-scale deployments should replace this transport with short-lived S3-compatible object-storage URLs while keeping the same asset-ID trust boundary.
