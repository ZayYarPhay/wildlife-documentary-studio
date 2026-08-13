# Wildlife Documentary Studio

Phase 12 application for creating 2–15 minute, source-backed wildlife documentaries. It carries projects from research through visual generation, voice alignment, timeline planning, audio mixing and a validated final MP4 export, using manual editors or a resumable one-click workflow with optional generation on a separate worker host.

## Architecture

- `frontend/` — Next.js, React and TypeScript dashboard
- `backend/` — FastAPI, Pydantic, SQLAlchemy and Alembic
- `storage/projects/` — ignored local media workspace
- SQLite locally; `DATABASE_URL` can later point to PostgreSQL
- Provider abstract classes isolate the business layer from AI vendors

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item ..\.env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API: `http://localhost:8000`; docs: `http://localhost:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

UI: `http://localhost:3000`.

## Checks

```powershell
cd backend
pytest
ruff check .

cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

## Phase 0 scope

- Health endpoint with FFmpeg/ffprobe detection
- Project create/list/read/update/delete API
- 2–15 minute validation and auto-topic rule
- Persistent SQLite database and initial migration
- Dashboard, new project, project details and settings pages
- Placeholder workflow tabs
- Generation and render job base entities

## Phase 1 scope

- `ResearchSource` and `ResearchFact` records with source relationships
- Retry-safe research orchestration and generation job tracking
- Claim normalization and duplicate suppression
- Research generate/list and fact edit/approve/delete APIs
- Category-grouped Research review UI with source links and confidence
- Explicit idle/researching/review/failed states
- Previous successful facts are preserved when a provider retry fails

The default `RESEARCH_PROVIDER=mock` is deliberately safe: it creates low-confidence source-discovery placeholders, marks them as mock data, and never pretends they are verified wildlife facts. Configure a real retrieval provider before production research. The provider contract is in `backend/app/providers/base.py` and orchestration is in `backend/app/services/research.py`.

### Research API

- `POST /api/projects/{id}/research/generate`
- `GET /api/projects/{id}/research`
- `PATCH /api/research/facts/{fact_id}`
- `DELETE /api/research/facts/{fact_id}`
- `POST /api/research/facts/{fact_id}/approve`

## Phase 2 scope

- Versioned `Script` and ordered `ScriptSection` records
- Approved research facts are the only factual inputs sent to the LLM provider
- Section-level `source_fact_ids` preserve internal traceability
- Configurable narration words-per-minute and length tolerance
- Target word range, duration estimate and too-short/on-target/too-long detection
- Full narration and section editors; full edits preserve one paragraph per traceable section
- Regenerate, shorten and expand individual sections
- Approve one script version while preserving version history
- Provider timeout/failure handling preserves earlier successful versions
- Interactive Research and Script tabs in the project workspace

The default `LLM_PROVIDER=mock` generates deterministic development narration and is clearly marked in the UI. Replace it with a real `LLMProvider` implementation for production-quality prose.

### Script API

- `POST /api/projects/{id}/script/generate`
- `GET /api/projects/{id}/script`
- `PATCH /api/scripts/{script_id}`
- `PATCH /api/script-sections/{section_id}`
- `POST /api/script-sections/{section_id}/regenerate`
- `POST /api/scripts/{script_id}/approve`

## Phase 3 scope

- Approved scripts become ordered, timed `Scene` records
- Natural narration chunking targets roughly 4–10 seconds per visual scene
- Scene start/end times are recalculated after edits, insertion, deletion or reorder
- Varied shot types and restrained camera-motion recommendations
- `STOCK_VIDEO`, `AI_IMAGE_MOTION` and `AI_VIDEO` strategy recommendations
- Versioned `ScenePrompt` image/video prompt plans without generating media
- Full-plan generation plus single-scene visual-plan regeneration
- Scene edit, add, duplicate, delete and move-up/down reorder controls
- Total scene duration, project target and mismatch warning
- SQLite foreign-key enforcement so project cleanup cascades safely
- Approved script content remains unchanged during scene operations

### Scene API

- `POST /api/projects/{id}/scenes/generate`
- `GET /api/projects/{id}/scenes`
- `POST /api/projects/{id}/scenes`
- `PATCH /api/scenes/{scene_id}`
- `DELETE /api/scenes/{scene_id}`
- `POST /api/scenes/{scene_id}/regenerate`
- `POST /api/projects/{id}/scenes/reorder`

## Phase 4 scope

- Provider-neutral stock-video search using the existing `StockMediaProvider`
- Short query variants derived from species, environment, behavior and shot type
- Candidate deduplication across multiple query variants
- Transparent relevance scoring for keywords, landscape framing, resolution and usable duration
- Preference for landscape 16:9, 1080p-or-better footage
- Persistent provider/source/creator/license/attribution metadata
- Candidate, selected and rejected asset states
- One preferred media asset per scene
- Search-again behavior preserves existing selection and avoids duplicate assets
- Provider failures preserve previously retrieved candidates
- Scene picker and ranked candidate cards in the Media tab
- No arbitrary URL download endpoint; mock mode does not download external files

The default `STOCK_MEDIA_PROVIDER=mock` supplies UI/test placeholders. It deliberately stores `license = null` and requires provider terms to be confirmed. Implement a real provider adapter and verify its license fields before production use. Future download implementations must enforce content-type checks, size limits, timeouts and safe filenames; current Phase 4 selection is metadata-only.

### Stock-media API

- `POST /api/scenes/{scene_id}/stock/search`
- `GET /api/scenes/{scene_id}/stock`
- `POST /api/media-assets/{asset_id}/select`
- `POST /api/media-assets/{asset_id}/reject`

## Phase 5 scope

- Provider-neutral image generation through `ImageGenerationProvider`
- Structured, species-conscious prompts covering behavior, habitat, framing, lighting, realism and visual continuity
- Negative constraints for anatomy, duplicates, incorrect markings, fantasy features, text/watermarks and impossible habitats
- Immutable `ScenePrompt` versions for generated and manually edited prompts
- Background `GenerationJob` lifecycle with pending/running/completed/failed/canceled states, progress and durable diagnostics
- Retry creates a new job and preserves the failed attempt
- Optional provider seed persistence and future-ready reference asset IDs
- Local 16:9 production-resolution image and preview persistence
- Regeneration history that never overwrites an approved image
- Prompt editor, generation status/history, retry, preview download and approve/select controls in the Media tab
- AI image generation is limited to `AI_IMAGE_MOTION` and `AI_VIDEO` fallback scenes; no video generation yet

The default `IMAGE_GENERATION_PROVIDER=mock` creates deterministic local PNG placeholders so the full job and review workflow works without an API key. These files are explicitly marked as mock and are not production AI artwork. Add a real provider adapter without changing the core job, prompt or asset logic.

### AI-image API

- `GET /api/scenes/{scene_id}/images`
- `POST /api/scenes/{scene_id}/image-prompts/generate`
- `POST /api/scenes/{scene_id}/image-prompts`
- `POST /api/scenes/{scene_id}/images/generate`
- `POST /api/image-jobs/{job_id}/retry`
- `POST /api/image-jobs/{job_id}/cancel`
- `POST /api/media-assets/{asset_id}/select`

## Phase 6 scope

- Provider-neutral image-to-video generation through `VideoGenerationProvider`
- Structured motion prompts covering animal pose/action, environment, camera movement, duration and realism constraints
- Natural species movement guidance and explicit anti-morphing/identity-continuity constraints
- Approved local AI image required as the video source; arbitrary URLs and unmanaged file paths are rejected
- Configurable duration, FPS and resolution with provider-specific options isolated in job metadata
- Background video job lifecycle with progress, durable errors and preserved generation history
- Real MP4 validation through FFprobe for video stream, duration, resolution and non-empty output
- Retry limit with diagnostics preserved for every failed attempt
- Exhausted retries offer explicit `AI_IMAGE_MOTION` and `STOCK_VIDEO` fallbacks without failing the project
- Video prompt editor, job history, playback preview, retry, fallback selection, download and approve/select UI
- Regeneration does not replace an already approved clip
- No final documentary timeline or rendering yet

The default `VIDEO_GENERATION_PROVIDER=mock` uses local FFmpeg to create a deterministic MP4 image hold. It validates the complete provider/job/asset workflow but does not synthesize animal motion. A real image-to-video provider can replace it without changing scene, prompt, job or asset contracts.

### AI-video API

- `GET /api/scenes/{scene_id}/videos`
- `POST /api/scenes/{scene_id}/video-prompts/generate`
- `POST /api/scenes/{scene_id}/video-prompts`
- `POST /api/scenes/{scene_id}/videos/generate`
- `POST /api/video-jobs/{job_id}/retry`
- `POST /api/scenes/{scene_id}/video-fallback`
- `POST /api/media-assets/{asset_id}/select`

## Phase 7 scope

- Secure WAV, MP3 and FFmpeg-supported M4A voice-over upload
- Extension, MIME, magic-byte, size-limit and FFprobe audio-stream validation
- Random safe storage filenames under managed project media; original filenames remain metadata only
- Provider-neutral transcription through `TranscriptionProvider`
- Persistent `VoiceTrack`, timestamped `TranscriptSegment` and per-scene alignment records
- Approximate sequential script/transcript matching with overall and scene-level confidence
- Mismatch warnings plus manual transcript and timing correction
- Voice duration as scene-timing authority without automatically changing speech speed
- Scene timing recommendations for safe trim, image-motion extension, stock looping/additional clips or AI-video extension/splitting
- Explicit timing application that preserves approved script text and all selected media
- Upload history, audio player, transcript editor, re-transcribe and apply-timing UI
- No automatic timeline/render composition yet

The default `TRANSCRIPTION_PROVIDER=mock` uses the approved scene narration to generate deterministic timestamp segments. It tests persistence, alignment and review behavior but does not listen to the uploaded audio. Configure a real provider adapter for speech recognition.

### Voice-over API

- `GET /api/projects/{project_id}/voice`
- `POST /api/projects/{project_id}/voice/upload`
- `POST /api/voice-tracks/{track_id}/transcribe`
- `PATCH /api/transcript-segments/{segment_id}`
- `PATCH /api/voice-alignments/{alignment_id}`
- `POST /api/voice-tracks/{track_id}/apply`

## Phase 8 scope

- Versioned `Timeline` and ordered `TimelineItem` persistence
- Track architecture for VISUAL, VOICE, MUSIC, AMBIENT and SUBTITLE; Phase 8 establishes visual and voice planning
- Deterministic timeline building from applied voice duration, scene timing and each scene's selected media
- Selected video trim/loop planning, exact scale/crop and FPS normalization metadata
- Selected still-image duration filling with a subtle centered Ken Burns zoom/pan, preserved aspect ratio and no black borders
- Minimal documentary transition policy using cuts by default
- Missing visual/local source, gap, overlap, invalid range and duration mismatch validation
- Safe automatic gap/missing-visual fill using the previous selected visual when possible
- Provider-independent intermediate JSON render plan rather than one monolithic FFmpeg command
- Logged FFmpeg item runner with captured stderr and clear failure diagnostics
- Ordered track visualization, source previews, warnings, timing/transition edits, validation and rebuild/version controls
- No polished final export yet

Timeline validity requires one voice item covering the voice-over exactly and contiguous visual coverage for the same duration. Rebuilding creates a new immutable timeline version; manual edits affect only the selected version and never rewrite scene media or narration.

### Timeline API

- `GET /api/projects/{project_id}/timeline`
- `POST /api/projects/{project_id}/timeline/build`
- `PATCH /api/timeline-items/{item_id}`
- `POST /api/timelines/{timeline_id}/validate`

## Phase 9 scope

- Timestamp-preserving UTF-8 SRT generation from the applied voice transcript
- Export-only subtitle overlays: source media remains untouched
- Configurable subtitle enablement, font size, top/middle/bottom position, outline, background and safe margin
- Secure WAV/MP3/M4A upload for project music and per-scene ambient sound
- Required source/creator and license metadata for every uploaded music or ambient asset
- Music enablement, volume, fade-in/fade-out and automatic voice side-chain ducking controls
- Optional per-scene ambience with an independent low-volume control
- Deterministic FFmpeg audio filter plan using voice loudness normalization, music ducking, mixing and a true-peak limiter
- Persistent `AudioAsset` and project-level `AudioSettings` records
- Timeline MUSIC, AMBIENT and SUBTITLE items plus downloadable current SRT
- Subtitle preview, licensed-audio uploader/selector, audio previews and mix-plan inspection in the Timeline tab

Subtitles are not permanently burned into source clips. The SRT path, subtitle style and audio filter are saved in the intermediate render plan for the later export phase. Voice is normalized to a `-16 LUFS` target with a `-1.5 dB` true-peak target; the mixed output also uses a `0.95` limiter. These deterministic defaults are starting points and should still be reviewed with real narration and music.

### Subtitle and audio API

- `GET /api/projects/{project_id}/audio`
- `PATCH /api/projects/{project_id}/audio/settings`
- `POST /api/projects/{project_id}/audio/assets`
- `GET /api/timelines/{timeline_id}/subtitles.srt`

## Phase 10 scope

- Persistent `WorkflowRun` and ordered `WorkflowStep` state with attempts, diagnostics, progress and timestamps
- AUTO and MANUAL modes over every currently implemented phase
- Weighted overall progress from research through render-ready validation
- Idempotent start: repeated clicks return the active run instead of duplicating jobs/assets
- Existing approved research, scripts, scenes and selected media are reused
- AUTO policy controls for approvals, media selection, AI-video generation and local-image stock fallback
- MANUAL review pauses that preserve access to every existing editor
- Clean `VOICE_WAITING` state; AUTO resumes after transcription while MANUAL waits for timing approval
- Safe pause at step boundaries, resume, cancel and failed-step-only retry
- Process-restart recovery: interrupted pending/running workflows become resumable paused runs
- Current operation and generation-job visibility
- Render-ready validation without starting the future final MP4 render
- One-click pipeline panel with progress, step history, diagnostics and direct manual-editor navigation

The default AUTO policy approves generated research and script versions, selects generated media, creates configured AI-video scenes and falls back from unavailable local stock to AI image motion. Disable AI-video generation for a cheaper image-motion workflow. AUTO never replaces an already selected local visual. MANUAL mode pauses at major review boundaries and leaves all existing tabs fully functional.

### Workflow API

- `GET /api/projects/{project_id}/workflow`
- `POST /api/projects/{project_id}/workflow/start`
- `POST /api/workflows/{run_id}/pause`
- `POST /api/workflows/{run_id}/resume`
- `POST /api/workflows/{run_id}/retry`
- `POST /api/workflows/{run_id}/cancel`

## Phase 11 scope

- Configurable `local` or separate `worker` execution for AI image/video generation
- Persistent backend `WorkerJob` queue linked one-to-one with existing generation jobs
- Strict normalized/discriminated job payloads with job/project/scene IDs, prompts, bounded parameters and input asset IDs
- Bearer-token authenticated claim, progress, input-download, completion and failure protocol
- Whitelisted `AI_IMAGE` and `AI_VIDEO` job types only
- Atomic claim attempts, worker identity ownership, renewable leases and expired-lease requeue
- Authenticated asset-ID downloads; backend filesystem paths are never sent to workers
- Backend-controlled result filenames, size limits, image verification/dimension checks and FFprobe video validation
- Durable worker/result diagnostics and idempotent duplicate result delivery
- AUTO workflow pause while remote work runs and automatic resume when valid results arrive
- Remote worker failure propagation to the current workflow step for explicit retry
- Standalone polling mock worker with an independent `/health` endpoint
- Worker Dockerfile and generic Docker Compose/rented-GPU deployment direction
- Backend remains fully usable when no GPU worker is online; queued jobs wait safely

Keep `GENERATION_EXECUTION_MODE=local` for the original in-process development behavior. Set it to `worker`, configure the same non-default `WORKER_AUTH_TOKEN` on backend and worker, and start `python -m worker.worker`. The included worker produces deterministic mock assets; it demonstrates the complete separate-process trust and lifecycle boundary, not a production diffusion/video model.

### Worker API

- `GET /api/worker/queue/health`
- `POST /api/worker/jobs/claim`
- `POST /api/worker/jobs/{job_id}/progress`
- `POST /api/worker/jobs/{job_id}/complete`
- `POST /api/worker/jobs/{job_id}/fail`
- `GET /api/worker/assets/{asset_id}`

All worker API routes require `Authorization: Bearer <WORKER_AUTH_TOKEN>`.

## Phase 12 scope

- Actionable preflight checks for voice, timeline coverage, visuals, subtitles, audio, managed files, media tools and disk space
- Background staged FFmpeg rendering, H.264/AAC encoding and atomic final-file publication
- FFprobe validation for duration, video/audio streams, selected resolution and aspect ratio
- Durable render history with progress, bounded logs, cancel, retry, stale-process recovery and temp cleanup
- Export settings and UI for FPS, CRF, preset, subtitles, audio, preview and MP4 download
- Project duplication, safe storage cleanup, storage reporting, missing-file detection and selected-asset proxies
- Mock-provider end-to-end flow and real tiny-sample FFmpeg export tests without paid AI/GPU calls

See [`docs/production.md`](docs/production.md) for deployment, queue, storage, backup and logging guidance.

### Export and production API

- `GET /api/projects/{project_id}/export`
- `POST /api/projects/{project_id}/export/preflight`
- `POST /api/projects/{project_id}/export/render`
- `POST /api/render-jobs/{job_id}/cancel`
- `POST /api/render-jobs/{job_id}/retry`
- `GET /api/render-jobs/{job_id}/download`
- `POST /api/projects/{project_id}/duplicate`
- `GET /api/projects/{project_id}/storage`
- `POST /api/projects/{project_id}/media/maintenance`

## Known limitations

End-user authentication and real web retrieval/LLM/stock/image/video/transcription adapters are deployment-specific and are not included. Multi-node production should use PostgreSQL, a dedicated broker and short-lived object-storage URLs. Render jobs currently run in the backend background process; production should move the same durable contract to a CPU render worker. Interrupted FFmpeg encodes restart from the render step, while upstream work is preserved. Users must confirm media licenses. Burmese and other non-space-delimited languages need specialized tokenization/alignment. Mock providers exercise the full flow but are not production AI models.
