import asyncio
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.jobs import RenderJob
from app.models.project import Project
from app.models.script import Script
from app.models.thumbnail import ThumbnailAsset, ThumbnailConcept, ThumbnailStatus
from app.providers.base import ThumbnailProvider
from app.providers.mock_thumbnail import MockThumbnailProvider
from app.schemas.thumbnail import ThumbnailBundle, ThumbnailGenerateRequest

THUMBNAIL_NEGATIVE_PROMPT = (
    "text, letters, logo, watermark, border, collage, duplicate animals, extra limbs, "
    "deformed anatomy, incorrect species markings, human clothing, collar, fantasy creature, "
    "graphic violence, misleading habitat"
)


def get_thumbnail_provider() -> ThumbnailProvider:
    name = get_settings().thumbnail_provider.lower()
    if name == "mock":
        return MockThumbnailProvider()
    raise ValueError(f"Unsupported thumbnail provider: {name}")


def final_render_ready(project_id: int, db: Session) -> bool:
    render = db.scalar(
        select(RenderJob)
        .where(RenderJob.project_id == project_id, RenderJob.status == "COMPLETED")
        .order_by(RenderJob.finished_at.desc(), RenderJob.id.desc())
    )
    if (
        render is None
        or not render.output_path
        or render.validation_json.get("output", {}).get("valid") is not True
    ):
        return False
    path = Path(render.output_path).resolve()
    root = (Path(get_settings().media_root).resolve() / str(project_id) / "renders").resolve()
    return path.is_relative_to(root) and path.is_file()


async def create_thumbnail_concepts(
    project: Project, db: Session, provider: ThumbnailProvider | None = None
) -> list[ThumbnailConcept]:
    if not final_render_ready(project.id, db):
        raise ValueError("Complete and validate a final MP4 export before creating thumbnails")
    if not project.animal_topic:
        raise ValueError("Project topic is required for thumbnail concepts")
    script = db.scalar(
        select(Script)
        .where(Script.project_id == project.id)
        .order_by(Script.approved.desc(), Script.version.desc(), Script.id.desc())
    )
    excerpt = script.full_text[:3000] if script else ""
    active = provider or get_thumbnail_provider()
    raw = await asyncio.wait_for(
        active.suggest_concepts(
            project.animal_topic,
            excerpt,
            project_title=project.title,
            count=3,
        ),
        timeout=get_settings().thumbnail_timeout_seconds,
    )
    if not isinstance(raw, list) or len(raw) != 3:
        raise RuntimeError("Thumbnail provider must return exactly three concepts")
    version = (
        db.scalar(
            select(func.max(ThumbnailConcept.version)).where(
                ThumbnailConcept.project_id == project.id
            )
        )
        or 0
    ) + 1
    concepts = []
    for order, item in enumerate(raw, 1):
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not name or len(description) < 10 or len(prompt) < 20:
            raise RuntimeError("Thumbnail provider returned an incomplete concept")
        concept = ThumbnailConcept(
            project_id=project.id,
            version=version,
            concept_order=order,
            name=name[:200],
            description=description,
            prompt=_identity_safe_prompt(project.animal_topic, prompt),
            negative_prompt=THUMBNAIL_NEGATIVE_PROMPT,
        )
        db.add(concept)
        concepts.append(concept)
    db.commit()
    for concept in concepts:
        db.refresh(concept)
    return concepts


def submit_thumbnail_assets(
    project: Project,
    request: ThumbnailGenerateRequest,
    db: Session,
    *,
    retry_count: int = 0,
) -> list[ThumbnailAsset]:
    if not final_render_ready(project.id, db):
        raise ValueError("Complete and validate a final MP4 export before generating thumbnails")
    concepts = _selected_concepts(project.id, request.concept_ids, db)
    if not concepts:
        raise ValueError("Generate thumbnail concepts before generating images")
    settings = get_settings()
    provider = get_thumbnail_provider()
    assets = []
    for index, concept in enumerate(concepts):
        asset = ThumbnailAsset(
            project_id=project.id,
            concept_id=concept.id,
            provider=getattr(provider, "name", provider.__class__.__name__),
            status=ThumbnailStatus.PENDING,
            width=settings.thumbnail_width,
            height=settings.thumbnail_height,
            seed=request.seed + index if request.seed is not None else None,
            title_overlay=request.title_overlay,
            overlay_text=(request.overlay_text.strip() if request.overlay_text else None),
            retry_count=retry_count,
            metadata_json={"concept_version": concept.version},
        )
        db.add(asset)
        assets.append(asset)
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return assets


def run_thumbnail_asset(asset_id: int) -> None:
    db = SessionLocal()
    output: Path | None = None
    try:
        asset = db.get(ThumbnailAsset, asset_id)
        if asset is None or asset.status != ThumbnailStatus.PENDING:
            return
        concept = db.get(ThumbnailConcept, asset.concept_id)
        project = db.get(Project, asset.project_id)
        if concept is None or project is None:
            raise RuntimeError("Thumbnail job references missing project data")
        settings = get_settings()
        directory = (Path(settings.media_root).resolve() / str(project.id) / "thumbnails").resolve()
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"thumbnail-{asset.id}-{uuid4().hex}.png"
        provider = get_thumbnail_provider()
        result = asyncio.run(
            asyncio.wait_for(
                provider.generate(
                    concept.prompt,
                    negative_prompt=concept.negative_prompt,
                    width=asset.width,
                    height=asset.height,
                    seed=asset.seed,
                    output_path=str(output),
                    final_render_reference=False,
                ),
                timeout=settings.thumbnail_timeout_seconds,
            )
        )
        path = Path(result["local_path"]).resolve()
        if not path.is_relative_to(directory) or path != output.resolve() or not path.is_file():
            raise RuntimeError("Thumbnail provider returned an unmanaged output path")
        _validate_image(path, asset.width, asset.height)
        if asset.title_overlay:
            _apply_title_overlay(path, asset.overlay_text or project.title)
            _validate_image(path, asset.width, asset.height)
        metadata = dict(result.get("metadata_json", {}))
        metadata.update(
            {
                "concept_name": concept.name,
                "prompt": concept.prompt,
                "negative_prompt": concept.negative_prompt,
                "default_no_text": not asset.title_overlay,
            }
        )
        asset.local_path = str(path)
        asset.public_url = (
            f"{settings.public_media_base_url.rstrip('/')}/{project.id}/thumbnails/{path.name}"
        )
        asset.seed = result.get("seed", asset.seed)
        asset.metadata_json = metadata
        asset.status = ThumbnailStatus.COMPLETED
        asset.completed_at = datetime.now(UTC)
        asset.error_message = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 - persist provider-boundary diagnostics
        db.rollback()
        if output:
            output.unlink(missing_ok=True)
        asset = db.get(ThumbnailAsset, asset_id)
        if asset:
            asset.status = ThumbnailStatus.FAILED
            asset.error_message = str(exc)[-4000:]
            db.commit()
    finally:
        db.close()


def approve_thumbnail(asset: ThumbnailAsset, db: Session) -> ThumbnailAsset:
    if asset.status not in {ThumbnailStatus.COMPLETED, ThumbnailStatus.APPROVED}:
        raise ValueError("Only a completed thumbnail can be approved")
    if not asset.local_path or not Path(asset.local_path).is_file():
        raise ValueError("Thumbnail file is missing")
    for other in db.scalars(
        select(ThumbnailAsset).where(
            ThumbnailAsset.project_id == asset.project_id,
            ThumbnailAsset.status == ThumbnailStatus.APPROVED,
            ThumbnailAsset.id != asset.id,
        )
    ):
        other.status = ThumbnailStatus.COMPLETED
    asset.status = ThumbnailStatus.APPROVED
    db.commit()
    db.refresh(asset)
    return asset


def thumbnail_bundle(project: Project, db: Session) -> ThumbnailBundle:
    latest_version = db.scalar(
        select(func.max(ThumbnailConcept.version)).where(ThumbnailConcept.project_id == project.id)
    )
    concepts = (
        list(
            db.scalars(
                select(ThumbnailConcept)
                .where(
                    ThumbnailConcept.project_id == project.id,
                    ThumbnailConcept.version == latest_version,
                )
                .order_by(ThumbnailConcept.concept_order)
            )
        )
        if latest_version
        else []
    )
    assets = list(
        db.scalars(
            select(ThumbnailAsset)
            .where(ThumbnailAsset.project_id == project.id)
            .order_by(ThumbnailAsset.created_at.desc(), ThumbnailAsset.id.desc())
        )
    )
    provider = get_thumbnail_provider()
    approved = next((item.id for item in assets if item.status == ThumbnailStatus.APPROVED), None)
    return ThumbnailBundle(
        project_id=project.id,
        final_render_ready=final_render_ready(project.id, db),
        provider=getattr(provider, "name", provider.__class__.__name__),
        is_mock=bool(getattr(provider, "is_mock", False)),
        concepts=concepts,
        assets=assets,
        approved_thumbnail_id=approved,
        warning=(
            "Mock thumbnails validate the workflow and are not production wildlife artwork."
            if getattr(provider, "is_mock", False) and (concepts or assets)
            else None
        ),
    )


def _selected_concepts(
    project_id: int, concept_ids: list[int], db: Session
) -> list[ThumbnailConcept]:
    if concept_ids:
        concepts = list(
            db.scalars(
                select(ThumbnailConcept).where(
                    ThumbnailConcept.project_id == project_id,
                    ThumbnailConcept.id.in_(concept_ids),
                )
            )
        )
        if len(concepts) != len(set(concept_ids)):
            raise ValueError("Thumbnail concepts must belong to this project")
        return sorted(concepts, key=lambda item: concept_ids.index(item.id))
    latest = db.scalar(
        select(func.max(ThumbnailConcept.version)).where(ThumbnailConcept.project_id == project_id)
    )
    if latest is None:
        return []
    return list(
        db.scalars(
            select(ThumbnailConcept)
            .where(
                ThumbnailConcept.project_id == project_id,
                ThumbnailConcept.version == latest,
            )
            .order_by(ThumbnailConcept.concept_order)
        )
    )


def _identity_safe_prompt(topic: str, prompt: str) -> str:
    return (
        f"Subject identity: exactly one {topic}; scientifically accurate anatomy, proportions, "
        "coat/skin/feather pattern and species-specific features. Preserve a single coherent animal "
        "identity. No text or typography in the generated image.\n"
        f"Composition: {prompt}\n"
        "Style: photorealistic ethical wildlife-documentary thumbnail, authentic natural behavior, "
        "clear focal subject, high visual readability at small size, 16:9 landscape."
    )


def _validate_image(path: Path, width: int, height: int) -> None:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.size != (width, height) or image.format != "PNG":
            raise RuntimeError("Thumbnail must be an exact-size PNG image")
        if abs(width / height - 16 / 9) > 0.02:
            raise RuntimeError("Thumbnail output must use a 16:9 aspect ratio")


def _apply_title_overlay(path: Path, text: str) -> None:
    clean = " ".join(text.split())[:120]
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font_size = max(32, image.width // 18)
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    lines = textwrap.wrap(clean, width=26)[:2]
    content = "\n".join(lines)
    box = draw.multiline_textbbox((0, 0), content, font=font, spacing=8, stroke_width=2)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    x = max(40, image.width - text_width - 70)
    y = image.height - text_height - 70
    draw.rounded_rectangle(
        (x - 25, y - 20, image.width - 35, image.height - 35),
        radius=18,
        fill=(0, 0, 0, 165),
    )
    draw.multiline_text(
        (x, y),
        content,
        fill=(255, 255, 255, 255),
        font=font,
        spacing=8,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )
    image.save(path, "PNG", optimize=True)
