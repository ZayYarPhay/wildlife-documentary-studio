import json
from typing import Any

from app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Deterministic provider used to exercise script workflows without an API key."""

    name = "mock"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def generate(self, prompt: str, **options: Any) -> str:
        if options.get("fail"):
            raise RuntimeError("Intentional mock LLM failure")

        task = options.get("task", "script")
        facts = options.get("facts", [])
        if task == "section":
            section = options["section"]
            mode = options.get("mode", "regenerate")
            words = section["text"].split()
            if mode == "shorten":
                text = " ".join(words[: max(8, int(len(words) * 0.65))])
            elif mode == "expand":
                text = section["text"] + " " + section["text"]
            else:
                linked = [
                    fact["claim"] for fact in facts if fact["id"] in section["source_fact_ids"]
                ]
                text = " ".join(linked) or section["text"]
            return json.dumps({"title": section["title"], "text": text})

        target_words = int(options["target_words"])
        section_count = min(max(len(facts), 1), 6)
        words_per_section = max(1, target_words // section_count)
        sections = []
        titles = [
            "Opening",
            "The Living World",
            "Adaptation",
            "Daily Life",
            "Challenges",
            "Closing",
        ]
        for index in range(section_count):
            fact = facts[index % len(facts)]
            claim_words = fact["claim"].split()
            narrative_words: list[str] = []
            while len(narrative_words) < words_per_section:
                narrative_words.extend(claim_words)
            sections.append(
                {
                    "title": titles[index],
                    "text": " ".join(narrative_words[:words_per_section]),
                    "source_fact_ids": [fact["id"]],
                }
            )
        return json.dumps({"sections": sections})
