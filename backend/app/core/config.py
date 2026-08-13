from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Wildlife Documentary Studio API"
    database_url: str = "sqlite:///./wildlife.db"
    media_root: str = "../storage/projects"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    log_level: str = "INFO"
    research_provider: str = "mock"
    research_timeout_seconds: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
