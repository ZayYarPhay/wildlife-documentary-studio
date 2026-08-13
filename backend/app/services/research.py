import asyncio
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.jobs import GenerationJob
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.research import ResearchFact, ResearchSource
from app.providers.base import ResearchProvider
from app.providers.mock_research import MockResearchProvider


def normalize_claim(claim: str) -> str:
    return re.sub(r"\s+", " ", claim.strip().lower())


def get_research_provider() -> ResearchProvider:
    provider = get_settings().research_provider.lower()
    if provider == "mock":
        return MockResearchProvider()
    raise ValueError(f"Unsupported research provider: {provider}")


@dataclass
class ResearchResult:
    provider: str
    is_mock: bool
    facts: list[ResearchFact]


class ResearchOrchestrator:
    def __init__(
        self, provider: ResearchProvider | None = None, timeout_seconds: int | None = None
    ):
        self.provider = provider or get_research_provider()
        self.timeout_seconds = timeout_seconds or get_settings().research_timeout_seconds

    async def generate(self, project: Project, db: Session) -> ResearchResult:
        topic = (project.animal_topic or "").strip()
        if not topic:
            raise ValueError("Choose a project topic before generating research")

        provider_name = getattr(self.provider, "name", self.provider.__class__.__name__)
        job = GenerationJob(
            project_id=project.id,
            job_type="RESEARCH",
            provider=provider_name,
            status="RUNNING",
            progress=0.05,
        )
        project.status = ProjectStatus.RESEARCHING
        project.current_phase = ProjectPhase.RESEARCH
        db.add(job)
        db.commit()

        try:
            raw_facts = await asyncio.wait_for(
                self.provider.research(topic), timeout=self.timeout_seconds
            )
            self._store(raw_facts, project, db)
            job.status = "COMPLETED"
            job.progress = 1
            project.status = ProjectStatus.RESEARCH_REVIEW
            project.current_phase = ProjectPhase.RESEARCH_REVIEW
            db.commit()
        except Exception as exc:
            db.rollback()
            persisted_job = db.get(GenerationJob, job.id)
            persisted_project = db.get(Project, project.id)
            if persisted_job:
                persisted_job.status = "FAILED"
                persisted_job.error_message = str(exc)
            if persisted_project:
                persisted_project.status = ProjectStatus.FAILED
                persisted_project.current_phase = ProjectPhase.RESEARCH
            db.commit()
            raise

        facts = list(
            db.scalars(
                select(ResearchFact)
                .where(ResearchFact.project_id == project.id)
                .options(selectinload(ResearchFact.source))
                .order_by(ResearchFact.category, ResearchFact.id)
            )
        )
        return ResearchResult(
            provider=provider_name,
            is_mock=bool(getattr(self.provider, "is_mock", False)),
            facts=facts,
        )

    @staticmethod
    def _store(raw_facts: list[dict[str, Any]], project: Project, db: Session) -> None:
        existing_sources = {
            source.url: source
            for source in db.scalars(
                select(ResearchSource).where(ResearchSource.project_id == project.id)
            )
        }
        existing_claims = set(
            db.scalars(
                select(ResearchFact.normalized_claim).where(ResearchFact.project_id == project.id)
            )
        )

        for raw in raw_facts:
            source_data = raw["source"]
            source = existing_sources.get(source_data["url"])
            if source is None:
                source = ResearchSource(project_id=project.id, **source_data)
                db.add(source)
                db.flush()
                existing_sources[source.url] = source

            normalized = normalize_claim(raw["claim"])
            if normalized in existing_claims:
                continue
            db.add(
                ResearchFact(
                    project_id=project.id,
                    source_id=source.id,
                    category=raw["category"],
                    claim=raw["claim"].strip(),
                    normalized_claim=normalized,
                    confidence=raw.get("confidence", 0.5),
                    notes=raw.get("notes"),
                )
            )
            existing_claims.add(normalized)
