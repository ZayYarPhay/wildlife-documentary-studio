from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    @abstractmethod
    async def health(self) -> dict[str, Any]: ...


class LLMProvider(Provider):
    @abstractmethod
    async def generate(self, prompt: str, **options: Any) -> str: ...


class ResearchProvider(Provider):
    @abstractmethod
    async def research(self, topic: str, **options: Any) -> list[dict[str, Any]]: ...


class StockMediaProvider(Provider):
    @abstractmethod
    async def search(self, query: str, **options: Any) -> list[dict[str, Any]]: ...


class ImageGenerationProvider(Provider):
    @abstractmethod
    async def generate(self, prompt: str, **options: Any) -> dict[str, Any]: ...


class VideoGenerationProvider(Provider):
    @abstractmethod
    async def generate(self, source: str, prompt: str, **options: Any) -> dict[str, Any]: ...


class TranscriptionProvider(Provider):
    @abstractmethod
    async def transcribe(self, audio_path: str, **options: Any) -> dict[str, Any]: ...


class RenderProvider(Provider):
    @abstractmethod
    async def render(self, plan: dict[str, Any], **options: Any) -> dict[str, Any]: ...
