from typing import Any

from app.providers.base import ResearchProvider


class MockResearchProvider(ResearchProvider):
    """Deterministic development data; never presented as completed real research."""

    name = "mock"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def research(self, topic: str, **options: Any) -> list[dict[str, Any]]:
        if topic == "__fail__":
            raise RuntimeError("Intentional mock provider failure")

        return [
            {
                "source": {
                    "title": "IUCN Red List of Threatened Species",
                    "url": "https://www.iucnredlist.org/",
                    "source_name": "IUCN",
                    "metadata_json": {"mock": True, "role": "source-discovery starting point"},
                },
                "category": "conservation",
                "claim": f"Verify the current conservation assessment for {topic} in the IUCN Red List before script approval.",
                "confidence": 0.25,
                "notes": "Development placeholder—not an approved wildlife fact.",
            },
            {
                "source": {
                    "title": "Animal Diversity Web",
                    "url": "https://animaldiversity.org/",
                    "source_name": "University of Michigan Museum of Zoology",
                    "metadata_json": {"mock": True, "role": "source-discovery starting point"},
                },
                "category": "taxonomy",
                "claim": f"Locate and review a species account for {topic} before using taxonomy or behavior claims.",
                "confidence": 0.25,
                "notes": "Development placeholder—not an approved wildlife fact.",
            },
            {
                "source": {
                    "title": "Animal Diversity Web",
                    "url": "https://animaldiversity.org/",
                    "source_name": "University of Michigan Museum of Zoology",
                    "metadata_json": {"mock": True, "role": "source-discovery starting point"},
                },
                "category": "taxonomy",
                "claim": f"Locate and review a species account for {topic} before using taxonomy or behavior claims.",
                "confidence": 0.25,
                "notes": "Duplicate emitted deliberately to exercise deduplication.",
            },
        ]
