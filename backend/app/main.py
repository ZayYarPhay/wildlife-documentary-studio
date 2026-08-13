from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.audio import router as audio_router
from app.api.images import router as images_router
from app.api.media import router as media_router
from app.api.projects import router as projects_router
from app.api.research import router as research_router
from app.api.scenes import router as scenes_router
from app.api.scripts import router as scripts_router
from app.api.timelines import router as timelines_router
from app.api.videos import router as videos_router
from app.api.voice import router as voice_router
from app.api.worker import router as worker_router
from app.api.workflow import router as workflow_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Base, SessionLocal, engine
from app.services.media_tools import media_tool_status
from app.services.workflow import recover_interrupted_workflows

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        recover_interrupted_workflows(db)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router)
app.include_router(research_router)
app.include_router(scripts_router)
app.include_router(scenes_router)
app.include_router(media_router)
app.include_router(images_router)
app.include_router(videos_router)
app.include_router(voice_router)
app.include_router(timelines_router)
app.include_router(audio_router)
app.include_router(workflow_router)
app.include_router(worker_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": jsonable_encoder(exc.errors(), custom_encoder={ValueError: str}),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": str(exc.detail),
                "details": None,
            }
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "media_tools": media_tool_status()}
