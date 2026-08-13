import asyncio
import hashlib
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.providers.base import ThumbnailProvider


class MockThumbnailProvider(ThumbnailProvider):
    """Deterministic no-text thumbnails for lifecycle tests; not wildlife artwork."""

    name = "mock-thumbnail"
    is_mock = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def suggest_concepts(
        self, topic: str, script_excerpt: str, **options: Any
    ) -> list[dict[str, Any]]:
        await asyncio.sleep(0)
        return [
            {
                "name": "Intimate portrait",
                "description": f"A close, eye-level portrait that builds an immediate connection with {topic}.",
                "prompt": f"One {topic}, intimate eye-level wildlife portrait, face and eyes tack sharp, natural habitat softly receding, dramatic side light, clean negative space, cinematic 16:9 composition.",
            },
            {
                "name": "Animal in habitat",
                "description": f"A wide environmental frame showing how {topic} belongs to its landscape.",
                "prompt": f"One identifiable {topic} in its scientifically appropriate natural habitat, wide environmental wildlife photograph, strong scale and depth, subject on a rule-of-thirds point, cinematic natural light, 16:9.",
            },
            {
                "name": "Defining behavior",
                "description": "A dynamic but natural behavior-led frame inspired by the documentary narration.",
                "prompt": f"One {topic} performing a natural species-appropriate behavior, frozen decisive moment, readable silhouette, authentic habitat, restrained documentary drama, sharp anatomy, cinematic 16:9 framing.",
            },
        ]

    async def generate(self, prompt: str, **options: Any) -> dict[str, Any]:
        await asyncio.sleep(0)
        if "[fail]" in prompt.lower():
            raise RuntimeError("Mock thumbnail failure requested")
        seed = options.get("seed")
        if seed is None:
            seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        width = int(options["width"])
        height = int(options["height"])
        output = Path(options["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        rng = random.Random(seed)
        sky = tuple(rng.randint(35, 100) for _ in range(3))
        land = tuple(max(12, channel - rng.randint(10, 35)) for channel in sky)
        image = Image.new("RGB", (width, height), sky)
        draw = ImageDraw.Draw(image)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            color = tuple(int(sky[index] * (1 - ratio) + land[index] * ratio) for index in range(3))
            draw.line((0, y, width, y), fill=color)
        draw.ellipse(
            (width * 0.29, height * 0.18, width * 0.73, height * 0.84),
            fill=(22, 27, 24),
        )
        draw.ellipse(
            (width * 0.37, height * 0.27, width * 0.65, height * 0.65),
            fill=(48, 57, 50),
        )
        draw.ellipse(
            (width * 0.43, height * 0.38, width * 0.47, height * 0.44), fill=(220, 190, 95)
        )
        draw.ellipse(
            (width * 0.56, height * 0.38, width * 0.60, height * 0.44), fill=(220, 190, 95)
        )
        image.save(output, "PNG", optimize=True)
        return {
            "local_path": str(output.resolve()),
            "width": width,
            "height": height,
            "seed": seed,
            "metadata_json": {"mock": True, "contains_text": False},
        }
