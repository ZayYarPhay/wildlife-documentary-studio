import asyncio
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.jobs import GenerationJob
from app.models.media import MediaAsset, MediaAssetStatus, MediaAssetType
from app.models.project import ProjectPhase, ProjectStatus
from app.models.scene import Scene
from app.providers.base import StockMediaProvider
from app.providers.mock_stock import MockStockMediaProvider

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "before",
    "using",
    "approved",
    "research",
    "verify",
    "verified",
    "described",
    "narration",
}


def keywords(text: str, limit: int = 4) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    result: list[str] = []
    for token in tokens:
        if token not in STOP_WORDS and len(token) > 2 and token not in result:
            result.append(token)
        if len(result) == limit:
            break
    return result


def build_stock_queries(scene: Scene) -> list[str]:
    species = " ".join(keywords(scene.species, 3)) or scene.species.strip()
    environment = " ".join(keywords(scene.environment, 3))
    behavior = " ".join(keywords(scene.animal_behavior, 3))
    shot = " ".join(keywords(scene.shot_type, 2))
    candidates = [species, f"{species} {environment}", f"{species} {behavior}", f"{species} {shot}"]
    queries: list[str] = []
    for query in candidates:
        normalized = " ".join(query.split())
        if normalized and normalized not in queries:
            queries.append(normalized)
    return queries


def score_candidate(scene: Scene, candidate: dict[str, Any]) -> tuple[float, dict[str, float]]:
    target_terms = set(keywords(f"{scene.species} {scene.environment} {scene.animal_behavior}", 12))
    searchable = str(candidate.get("metadata_json", {}).get("title", ""))
    candidate_terms = set(keywords(searchable, 16))
    overlap = len(target_terms & candidate_terms) / max(len(target_terms), 1)
    keyword_score = min(0.5, overlap * 0.5)
    width = candidate.get("width") or 0
    height = candidate.get("height") or 0
    landscape_score = 0.15 if width > height and width / max(height, 1) >= 1.5 else 0
    resolution_score = 0.2 if width >= 1920 and height >= 1080 else 0.1 if width >= 1280 else 0
    duration = candidate.get("duration") or 0
    duration_score = (
        0.15 if duration >= min(scene.target_duration, 4) else 0.05 if duration > 0 else 0
    )
    breakdown = {
        "keyword": round(keyword_score, 4),
        "landscape": landscape_score,
        "resolution": resolution_score,
        "duration": duration_score,
    }
    return round(sum(breakdown.values()), 4), breakdown


def get_stock_provider() -> StockMediaProvider:
    name = get_settings().stock_media_provider.lower()
    if name == "mock":
        return MockStockMediaProvider()
    raise ValueError(f"Unsupported stock media provider: {name}")


@dataclass
class StockSearchResult:
    assets: list[MediaAsset]
    queries: list[str]
    provider: str
    is_mock: bool


class StockMediaService:
    def __init__(
        self, provider: StockMediaProvider | None = None, timeout_seconds: int | None = None
    ):
        self.provider = provider or get_stock_provider()
        self.timeout_seconds = timeout_seconds or get_settings().stock_search_timeout_seconds

    async def search(self, scene: Scene, db: Session) -> StockSearchResult:
        queries = build_stock_queries(scene)
        provider_name = getattr(self.provider, "name", self.provider.__class__.__name__)
        job = GenerationJob(
            project_id=scene.project_id,
            scene_id=scene.id,
            job_type="STOCK_SEARCH",
            provider=provider_name,
            status="RUNNING",
            progress=0.1,
        )
        scene.project.status = ProjectStatus.MEDIA_SEARCH
        scene.project.current_phase = ProjectPhase.MEDIA
        db.add(job)
        db.commit()
        try:
            batches = []
            for query in queries:
                batch = await asyncio.wait_for(
                    self.provider.search(query, media_type="video"), timeout=self.timeout_seconds
                )
                batches.extend(batch)
            deduplicated: dict[str, dict[str, Any]] = {}
            for candidate in batches:
                asset_id = str(candidate["provider_asset_id"])
                score, breakdown = score_candidate(scene, candidate)
                current = deduplicated.get(asset_id)
                if current is None or score > current["_score"]:
                    deduplicated[asset_id] = {
                        **candidate,
                        "_score": score,
                        "_breakdown": breakdown,
                    }

            existing = {
                asset.provider_asset_id: asset
                for asset in db.scalars(
                    select(MediaAsset).where(
                        MediaAsset.scene_id == scene.id, MediaAsset.provider == provider_name
                    )
                )
            }
            for provider_asset_id, candidate in deduplicated.items():
                asset = existing.get(provider_asset_id)
                metadata = dict(candidate.get("metadata_json") or {})
                metadata["score_breakdown"] = candidate["_breakdown"]
                metadata["search_queries"] = queries
                values = {
                    "type": MediaAssetType(candidate.get("type", "STOCK_VIDEO")),
                    "preview_url": candidate["preview_url"],
                    "download_url": candidate.get("download_url"),
                    "source_page_url": candidate["source_page_url"],
                    "creator": candidate.get("creator"),
                    "license": candidate.get("license"),
                    "attribution_requirements": candidate.get("attribution_requirements"),
                    "width": candidate.get("width"),
                    "height": candidate.get("height"),
                    "duration": candidate.get("duration"),
                    "metadata_json": metadata,
                    "relevance_score": candidate["_score"],
                }
                if asset is None:
                    asset = MediaAsset(
                        project_id=scene.project_id,
                        scene_id=scene.id,
                        provider=provider_name,
                        provider_asset_id=provider_asset_id,
                        **values,
                    )
                    db.add(asset)
                    existing[provider_asset_id] = asset
                else:
                    for key, value in values.items():
                        setattr(asset, key, value)
            job.status = "COMPLETED"
            job.progress = 1
            scene.project.status = ProjectStatus.MEDIA_REVIEW
            scene.project.current_phase = ProjectPhase.MEDIA_REVIEW
            db.commit()
        except Exception as exc:
            db.rollback()
            persisted_job = db.get(GenerationJob, job.id)
            persisted_scene = db.get(Scene, scene.id)
            if persisted_job:
                persisted_job.status = "FAILED"
                persisted_job.error_message = str(exc)
            if persisted_scene:
                persisted_scene.project.status = ProjectStatus.FAILED
                persisted_scene.project.current_phase = ProjectPhase.MEDIA
            db.commit()
            raise
        assets = list(
            db.scalars(
                select(MediaAsset)
                .where(MediaAsset.scene_id == scene.id)
                .order_by(MediaAsset.relevance_score.desc(), MediaAsset.id)
            )
        )
        return StockSearchResult(
            assets=assets,
            queries=queries,
            provider=provider_name,
            is_mock=bool(getattr(self.provider, "is_mock", False)),
        )

    @staticmethod
    def select_asset(asset: MediaAsset, scene: Scene, db: Session) -> MediaAsset:
        for other in db.scalars(select(MediaAsset).where(MediaAsset.scene_id == scene.id)):
            if other.status == MediaAssetStatus.SELECTED:
                other.status = MediaAssetStatus.CANDIDATE
        asset.status = MediaAssetStatus.SELECTED
        scene.preferred_media_asset_id = asset.id
        db.commit()
        db.refresh(asset)
        return asset

    @staticmethod
    def reject_asset(asset: MediaAsset, scene: Scene, db: Session) -> MediaAsset:
        asset.status = MediaAssetStatus.REJECTED
        if scene.preferred_media_asset_id == asset.id:
            scene.preferred_media_asset_id = None
        db.commit()
        db.refresh(asset)
        return asset
