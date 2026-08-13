from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.project import Project
from app.models.scene import Scene, ScenePrompt
from app.models.script import Script
from app.schemas.scene import SceneBundle, SceneCreate, SceneRead, SceneReorder, SceneUpdate
from app.services.scene_planner import ScenePlanner, prompt_values, retime_scenes

router = APIRouter(tags=["scenes"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def scene_or_404(scene_id: int, db: Session) -> Scene:
    scene = db.scalar(
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.prompts), selectinload(Scene.project))
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


def project_scenes(project_id: int, db: Session) -> list[Scene]:
    return list(
        db.scalars(
            select(Scene)
            .where(Scene.project_id == project_id)
            .options(selectinload(Scene.prompts))
            .order_by(Scene.order)
        )
    )


def bundle(project: Project, db: Session) -> SceneBundle:
    scenes = project_scenes(project.id, db)
    total = round(sum(scene.target_duration for scene in scenes), 3)
    return SceneBundle(
        project_id=project.id,
        status="review" if scenes else "idle",
        total_duration=total,
        target_duration=float(project.requested_duration_seconds),
        duration_difference=round(total - project.requested_duration_seconds, 3),
        scenes=scenes,
    )


def approved_script(project_id: int, db: Session) -> Script:
    script = db.scalar(
        select(Script)
        .where(Script.project_id == project_id, Script.approved.is_(True))
        .order_by(Script.version.desc())
    )
    if script is None:
        raise HTTPException(status_code=422, detail="Approve a script version first")
    return script


@router.post("/api/projects/{project_id}/scenes/generate", response_model=SceneBundle)
def generate_scenes(project_id: int, db: DatabaseSession) -> SceneBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        ScenePlanner().generate(project, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scene planning failed: {exc}") from exc
    return bundle(project, db)


@router.get("/api/projects/{project_id}/scenes", response_model=SceneBundle)
def get_scenes(project_id: int, db: DatabaseSession) -> SceneBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return bundle(project, db)


@router.post(
    "/api/projects/{project_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scene(project_id: int, payload: SceneCreate, db: DatabaseSession) -> Scene:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    script = approved_script(project_id, db)
    scenes = project_scenes(project_id, db)
    order = min(payload.order or len(scenes) + 1, len(scenes) + 1)
    for scene in scenes:
        if scene.order >= order:
            scene.order += 1
    data = payload.model_dump(exclude={"order"})
    scene = Scene(
        project_id=project_id,
        script_id=script.id,
        order=order,
        start_time=0,
        end_time=payload.target_duration,
        status="READY",
        **data,
    )
    db.add(scene)
    db.flush()
    image, negative, video = prompt_values(scene)
    db.add(
        ScenePrompt(
            scene_id=scene.id,
            image_prompt=image,
            negative_prompt=negative,
            video_prompt=video,
            version=1,
        )
    )
    scenes.append(scene)
    retime_scenes(scenes)
    db.commit()
    return scene_or_404(scene.id, db)


@router.patch("/api/scenes/{scene_id}", response_model=SceneRead)
def update_scene(scene_id: int, payload: SceneUpdate, db: DatabaseSession) -> Scene:
    scene = scene_or_404(scene_id, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(scene, key, value.strip() if isinstance(value, str) else value)
    retime_scenes(project_scenes(scene.project_id, db))
    db.commit()
    return scene_or_404(scene.id, db)


@router.delete("/api/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: int, db: DatabaseSession) -> Response:
    scene = scene_or_404(scene_id, db)
    project_id = scene.project_id
    db.delete(scene)
    db.flush()
    retime_scenes(project_scenes(project_id, db))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/scenes/{scene_id}/regenerate", response_model=SceneRead)
def regenerate_scene(scene_id: int, db: DatabaseSession) -> Scene:
    scene = scene_or_404(scene_id, db)
    return ScenePlanner.regenerate_scene(scene, db)


@router.post("/api/projects/{project_id}/scenes/reorder", response_model=SceneBundle)
def reorder_scenes(project_id: int, payload: SceneReorder, db: DatabaseSession) -> SceneBundle:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = project_scenes(project_id, db)
    by_id = {scene.id: scene for scene in scenes}
    if set(payload.scene_ids) != set(by_id):
        raise HTTPException(
            status_code=422, detail="scene_ids must contain every project scene exactly once"
        )
    ordered = [by_id[scene_id] for scene_id in payload.scene_ids]
    for index, scene in enumerate(ordered, start=1):
        scene.order = index
    retime_scenes(ordered)
    db.commit()
    return bundle(project, db)
