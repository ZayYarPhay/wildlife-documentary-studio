# Wildlife Documentary Studio

Phase 1 research application for a production-minded studio that will create 2–15 minute, source-backed wildlife documentaries. It provides persistent project management plus a reviewable research workflow while keeping providers replaceable.

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

## Known limitations

Authentication, real web retrieval credentials, scripts, media generation, voice-over, timelines and rendering belong to later roadmap phases and are not implemented yet.
