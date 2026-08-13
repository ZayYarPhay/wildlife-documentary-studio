import re
from typing import Any

from app.providers.base import StockMediaProvider


class MockStockMediaProvider(StockMediaProvider):
    name = "mock"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def search(self, query: str, **options: Any) -> list[dict[str, Any]]:
        if "fail" in query.lower().split():
            raise RuntimeError("Intentional mock stock provider failure")
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        common = {
            "provider_asset_id": "shared-landscape-001",
            "type": "STOCK_VIDEO",
            "preview_url": "https://placehold.co/640x360/1f3d2a/ffffff?text=Mock+Wildlife+Preview",
            "download_url": None,
            "source_page_url": "https://example.com/",
            "creator": "Mock provider",
            "license": None,
            "attribution_requirements": "License unknown; confirm provider terms before production use.",
            "width": 1920,
            "height": 1080,
            "duration": 12.0,
            "metadata_json": {"mock": True, "title": f"Wildlife landscape for {query}"},
        }
        specific = {
            **common,
            "provider_asset_id": f"{slug}-specific",
            "width": 3840,
            "height": 2160,
            "duration": 8.0,
            "metadata_json": {"mock": True, "title": query, "query": query},
        }
        portrait = {
            **common,
            "provider_asset_id": f"{slug}-portrait",
            "width": 1080,
            "height": 1920,
            "duration": 4.0,
            "metadata_json": {"mock": True, "title": f"Portrait clip {query}", "query": query},
        }
        return [common, specific, portrait]
