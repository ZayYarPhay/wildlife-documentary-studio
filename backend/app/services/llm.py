import asyncio
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.jobs import GenerationJob
from app.models.project import Project, ProjectPhase, ProjectStatus
from app.models.research import ResearchFact
from app.models.script import Script, ScriptSection
from app.providers.base import LLMProvider
from app.providers.mock_llm import MockLLMProvider


def word_count(text: str) -> int:
    return len(text.split())


def estimate_duration_seconds(text: str, words_per_minute: int) -> float:
    if words_per_minute <= 0:
        raise ValueError("words_per_minute must be greater than zero")
    return round(word_count(text) / words_per_minute * 60, 2)


def target_word_range(
    duration_seconds: int, words_per_minute: int, tolerance: float
) -> tuple[int, int]:
    target = duration_seconds / 60 * words_per_minute
    return round(target * (1 - tolerance)), round(target * (1 + tolerance))


def length_status(words: int, minimum: int, maximum: int) -> str:
    if words < minimum:
        return "TOO_SHORT"
    if words > maximum:
        return "TOO_LONG"
    return "ON_TARGET"


def get_llm_provider() -> LLMProvider:
    name = get_settings().llm_provider.lower()
    if name == "mock":
        return MockLLMProvider()
    raise ValueError(f"Unsupported LLM provider: {name}")


@dataclass
class ScriptGenerationResult:
    script: Script
    provider: str
    is_mock: bool


class ScriptOrchestrator:
    def __init__(self, provider: LLMProvider | None = None, timeout_seconds: int | None = None):
        self.provider = provider or get_llm_provider()
        self.timeout_seconds = timeout_seconds or get_settings().llm_timeout_seconds

    async def generate(self, project: Project, db: Session) -> ScriptGenerationResult:
        facts = list(
            db.scalars(
                select(ResearchFact)
                .where(ResearchFact.project_id == project.id, ResearchFact.approved.is_(True))
                .order_by(ResearchFact.id)
            )
        )
        if not facts:
            raise ValueError("Approve at least one research fact before generating a script")

        settings = get_settings()
        minimum, maximum = target_word_range(
            project.requested_duration_seconds,
            settings.narration_words_per_minute,
            settings.script_length_tolerance,
        )
        target = round(
            project.requested_duration_seconds / 60 * settings.narration_words_per_minute
        )
        provider_name = getattr(self.provider, "name", self.provider.__class__.__name__)
        job = GenerationJob(
            project_id=project.id,
            job_type="SCRIPT",
            provider=provider_name,
            status="RUNNING",
            progress=0.1,
        )
        project.status = ProjectStatus.SCRIPTING
        project.current_phase = ProjectPhase.SCRIPT
        db.add(job)
        db.commit()

        fact_payload = [
            {"id": fact.id, "category": fact.category, "claim": fact.claim} for fact in facts
        ]
        prompt = self._build_prompt(project, fact_payload, minimum, maximum)
        try:
            raw = await asyncio.wait_for(
                self.provider.generate(
                    prompt,
                    task="script",
                    facts=fact_payload,
                    target_words=target,
                    language=project.language,
                    tone=project.documentary_tone,
                ),
                timeout=self.timeout_seconds,
            )
            parsed = json.loads(raw)
            script = self._store(project, facts, parsed, db, minimum, maximum)
            job.status = "COMPLETED"
            job.progress = 1
            project.status = ProjectStatus.SCRIPT_REVIEW
            project.current_phase = ProjectPhase.SCRIPT_REVIEW
            db.commit()
            db.refresh(script)
        except Exception as exc:
            db.rollback()
            persisted_job = db.get(GenerationJob, job.id)
            persisted_project = db.get(Project, project.id)
            if persisted_job:
                persisted_job.status = "FAILED"
                persisted_job.error_message = str(exc)
            if persisted_project:
                persisted_project.status = ProjectStatus.FAILED
                persisted_project.current_phase = ProjectPhase.SCRIPT
            db.commit()
            raise

        return ScriptGenerationResult(
            script=script,
            provider=provider_name,
            is_mock=bool(getattr(self.provider, "is_mock", False)),
        )

    async def regenerate_section(
        self, section: ScriptSection, mode: str, db: Session
    ) -> ScriptSection:
        script = db.get(Script, section.script_id)
        facts = list(
            db.scalars(
                select(ResearchFact).where(
                    ResearchFact.project_id == script.project_id,
                    ResearchFact.approved.is_(True),
                )
            )
        )
        fact_payload = [
            {"id": fact.id, "category": fact.category, "claim": fact.claim} for fact in facts
        ]
        raw = await asyncio.wait_for(
            self.provider.generate(
                "Revise a documentary section using only its linked approved facts.",
                task="section",
                mode=mode,
                section={
                    "title": section.title,
                    "text": section.text,
                    "source_fact_ids": section.source_fact_ids,
                },
                facts=fact_payload,
            ),
            timeout=self.timeout_seconds,
        )
        parsed = json.loads(raw)
        section.title = parsed["title"].strip()
        section.text = parsed["text"].strip()
        self.recalculate_script(script)
        db.commit()
        db.refresh(section)
        return section

    @staticmethod
    def _build_prompt(
        project: Project, facts: list[dict[str, Any]], minimum: int, maximum: int
    ) -> str:
        fact_lines = "\n".join(f"FACT {fact['id']}: {fact['claim']}" for fact in facts)
        return (
            f"Write a {project.documentary_tone} narration in {project.language}. "
            f"Target {minimum}-{maximum} words. Use only the approved facts below. "
            "Dramatic language must not add factual claims. Return structured sections with fact IDs.\n"
            f"{fact_lines}"
        )

    @staticmethod
    def _store(
        project: Project,
        facts: list[ResearchFact],
        parsed: dict[str, Any],
        db: Session,
        minimum: int,
        maximum: int,
    ) -> Script:
        sections_data = parsed.get("sections")
        if not isinstance(sections_data, list) or not sections_data:
            raise ValueError("LLM response must contain at least one script section")
        allowed_ids = {fact.id for fact in facts}
        for item in sections_data:
            ids = item.get("source_fact_ids", [])
            if not ids or not set(ids).issubset(allowed_ids):
                raise ValueError("Script section referenced unapproved or missing research facts")
            if not str(item.get("text", "")).strip():
                raise ValueError("Script sections cannot be empty")

        version = (
            db.scalar(select(func.max(Script.version)).where(Script.project_id == project.id)) or 0
        ) + 1
        full_text = "\n\n".join(str(item["text"]).strip() for item in sections_data)
        words = word_count(full_text)
        settings = get_settings()
        script = Script(
            project_id=project.id,
            version=version,
            tone=project.documentary_tone,
            full_text=full_text,
            estimated_words=words,
            estimated_duration_seconds=estimate_duration_seconds(
                full_text, settings.narration_words_per_minute
            ),
            length_status=length_status(words, minimum, maximum),
        )
        db.add(script)
        db.flush()
        for index, item in enumerate(sections_data, start=1):
            text = str(item["text"]).strip()
            db.add(
                ScriptSection(
                    script_id=script.id,
                    order=index,
                    title=str(item.get("title") or f"Section {index}").strip(),
                    text=text,
                    estimated_duration_seconds=estimate_duration_seconds(
                        text, settings.narration_words_per_minute
                    ),
                    source_fact_ids=item["source_fact_ids"],
                )
            )
        db.flush()
        return script

    @staticmethod
    def recalculate_script(script: Script) -> None:
        settings = get_settings()
        script.full_text = "\n\n".join(section.text.strip() for section in script.sections)
        script.estimated_words = word_count(script.full_text)
        script.estimated_duration_seconds = estimate_duration_seconds(
            script.full_text, settings.narration_words_per_minute
        )
        minimum, maximum = target_word_range(
            script.project.requested_duration_seconds,
            settings.narration_words_per_minute,
            settings.script_length_tolerance,
        )
        script.length_status = length_status(script.estimated_words, minimum, maximum)
