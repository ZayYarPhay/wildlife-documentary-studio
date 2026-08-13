# Production operations

## Components

- Build the frontend with `npm ci && npm run build`, then run it behind HTTPS.
- Run Alembic before serving FastAPI with a production ASGI process manager.
- SQLite is for local development; use PostgreSQL for multi-process production.
- Deploy `worker/Dockerfile` on a GPU host only for image/video generation.
- Phase 12 renders through the FastAPI background process. At scale, send the durable `RenderJob` ID to a dedicated CPU worker.
- Keep `MEDIA_ROOT/{project_id}` on persistent storage outside executable application directories.

## Configuration

Install Python 3.12+, Node.js, FFmpeg and FFprobe. Copy `.env.example` to `backend/.env`, configure the database, storage/public URLs and providers, then run `alembic upgrade head`. Never commit `.env` or credentials.

Production-critical variables include `DATABASE_URL`, `MEDIA_ROOT`, `PUBLIC_MEDIA_BASE_URL`, `NEXT_PUBLIC_API_URL`, `FFMPEG_PATH`, `FFPROBE_PATH`, all `RENDER_*` and provider timeout/retry values, `JOB_STALE_SECONDS`, `GENERATION_EXECUTION_MODE`, `WORKER_AUTH_TOKEN` and `WORKER_LEASE_SECONDS`.

## Queue and worker

Use a long random worker token, HTTPS and network allowlists. Monitor backend `/health`, authenticated `/api/worker/queue/health`, and worker `/health`. PostgreSQL plus a dedicated broker is recommended when multiple workers claim concurrently. Keep database and web responsibilities off GPU hosts.

## Storage and cleanup

The maintenance API detects missing database-backed files, creates selected-asset proxies and can delete only unselected AI generations inside the managed project root. Project deletion verifies the resolved path before recursive cleanup. Monitor free space above `RENDER_MIN_FREE_BYTES`; final render temp files can briefly require several times the final output size.

## Backups and recovery

Back up the database and media root as one consistency set. For SQLite, stop writes or use its online backup facility. For PostgreSQL, use `pg_dump` or managed snapshots and versioned object storage. Test restores. Approved research, scripts, prompts, voice files and license metadata are higher priority than reproducible render outputs.

Startup recovery makes interrupted workflows resumable and marks stale local generation/render jobs failed with retry diagnostics. Expired GPU claims are requeued. Retry creates a new history record without erasing upstream work.

## Logs and monitoring

Ship backend structured logs to centralized storage. Render records retain a bounded FFmpeg diagnostic tail; retain full platform logs separately. Alert on repeated failures, stale jobs, queue depth, low disk, default worker-token warnings and health-check failure. Never log API keys, bearer tokens or private signed URLs.

## Release checklist

1. Back up database and media.
2. Install locked dependencies and run backend tests plus frontend lint/type/build.
3. Run `alembic upgrade head` once.
4. Confirm FFmpeg/FFprobe health and writable storage.
5. Smoke-test a mock project through preflight and a short export.
6. Verify HTTPS, CORS, worker-token rotation, backups and download authorization at the reverse proxy.
