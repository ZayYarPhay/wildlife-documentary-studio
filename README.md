# Wildlife Documentary Studio

Phase 6 application for a production-minded studio that will create 2–15 minute, source-backed wildlife documentaries. It provides persistent projects, reviewable research, versioned narration, timed scenes, ranked stock media and provider-neutral AI image/video generation.

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

## Known limitations

Authentication, real web retrieval/LLM/stock/image/video credentials, voice-over, timelines and final rendering belong to later roadmap phases and are not implemented yet. Space-delimited word counting is an approximation for languages such as Burmese that require specialized segmentation. Stock selection remains metadata-only; Phase 5/6 mock image and video output is local development media.
