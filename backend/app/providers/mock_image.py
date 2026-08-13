import asyncio
import hashlib
import random
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.providers.base import ImageGenerationProvider


class MockImageGenerationProvider(ImageGenerationProvider):
    """Deterministic local provider used for development and lifecycle tests."""

    name = "mock-image"
    is_mock = True
    supports_seed = True
    supports_reference_images = True

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "mock": True}

    async def generate(self, prompt: str, **options: Any) -> dict[str, Any]:
        await asyncio.sleep(0)
        if "[fail]" in prompt.lower():
            raise RuntimeError("Mock image generation failure requested by prompt")

        seed = options.get("seed")
        if seed is None:
            seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        width = int(options.get("width", 1280))
        height = int(options.get("height", 720))
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"mock-{seed}-{options.get('job_id', 'image')}.png"
        output_path = output_dir / filename

        rng = random.Random(seed)
        base = tuple(rng.randint(25, 95) for _ in range(3))
        accent = tuple(min(255, channel + rng.randint(70, 140)) for channel in base)
        image = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(image)
        for index in range(12):
            x = int(width * index / 11)
            color = tuple(
                int(base[channel] + (accent[channel] - base[channel]) * index / 11)
                for channel in range(3)
            )
            draw.rectangle((x, 0, x + width // 10 + 2, height), fill=color)
        draw.rectangle((48, height - 250, width - 48, height - 48), fill=(8, 15, 18, 220))
        font = ImageFont.load_default(size=24)
        draw.text((76, height - 220), "MOCK WILDLIFE IMAGE", fill="white", font=font)
        lines = textwrap.wrap(prompt, width=82)[:4]
        draw.multiline_text(
            (76, height - 170), "\n".join(lines), fill=(230, 238, 232), font=font, spacing=8
        )
        image.save(output_path, format="PNG", optimize=True)
        thumbnail_filename = f"mock-{seed}-{options.get('job_id', 'image')}-preview.png"
        thumbnail_path = output_dir / thumbnail_filename
        thumbnail = image.copy()
        thumbnail.thumbnail((640, 360))
        thumbnail.save(thumbnail_path, format="PNG", optimize=True)
        return {
            "provider_asset_id": f"mock-{seed}-{options.get('job_id', 'image')}",
            "local_path": str(output_path.resolve()),
            "filename": filename,
            "thumbnail_filename": thumbnail_filename,
            "width": width,
            "height": height,
            "seed": seed,
            "mime_type": "image/png",
            "metadata_json": {
                "mock": True,
                "reference_asset_ids": options.get("reference_asset_ids", []),
                "thumbnail_path": str(thumbnail_path.resolve()),
            },
        }
