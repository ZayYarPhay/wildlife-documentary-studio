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
    llm_provider: str = "mock"
    llm_timeout_seconds: int = 60
    narration_words_per_minute: int = 140
    script_length_tolerance: float = 0.15
    stock_media_provider: str = "mock"
    stock_search_timeout_seconds: int = 30
    stock_download_on_select: bool = False
    stock_max_download_bytes: int = 1_073_741_824
    image_generation_provider: str = "mock"
    image_generation_timeout_seconds: int = 120
    public_media_base_url: str = "http://localhost:8000/media"
    video_generation_provider: str = "mock"
    video_generation_timeout_seconds: int = 180
    video_generation_max_retries: int = 1
    video_generation_fps: int = 24
    video_generation_max_duration_seconds: float = 10
    transcription_provider: str = "mock"
    transcription_timeout_seconds: int = 180
    voice_upload_max_bytes: int = 536_870_912
    audio_upload_max_bytes: int = 536_870_912
    timeline_fps: int = 24
    timeline_gap_tolerance_seconds: float = 0.05
    generation_execution_mode: str = "local"
    worker_auth_token: str = "change-me-in-production"
    worker_lease_seconds: int = 300
    worker_result_max_bytes: int = 1_073_741_824
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
