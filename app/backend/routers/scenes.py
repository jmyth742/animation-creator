"""Scene CRUD routes and bulk reorder."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Character, Episode, Location, Scene, SceneCharacter, User
from schemas import CharacterRead, SceneRead, SceneReorderItem, SceneUpdate

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_portrait_url(path: str | None) -> str | None:
    return f"/static/series/{path}" if path else None


def _character_read(char: Character) -> CharacterRead:
    r = CharacterRead.model_validate(char)
    r.portrait_url = _build_portrait_url(char.reference_image_path)
    return r


def _scene_read(scene: Scene, db: Session) -> SceneRead:
    r = SceneRead.model_validate(scene)
    r.characters = [_character_read(sc.character) for sc in scene.scene_characters]
    r.preview_url = (
        f"/static/clips/{scene.output_clip_path}" if scene.output_clip_path else None
    )
    if scene.location_id:
        loc: Location | None = db.get(Location, scene.location_id)
        r.location_name = loc.name if loc else None
    return r


def _get_scene_or_404(scene_id: int, user: User, db: Session) -> Scene:
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found.")
    if scene.episode.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return scene


# ── GET /scenes/{id} ──────────────────────────────────────────────────────────

@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SceneRead:
    scene = _get_scene_or_404(scene_id, current_user, db)
    return _scene_read(scene, db)


# ── PUT /scenes/{id} ──────────────────────────────────────────────────────────

@router.put("/scenes/{scene_id}", response_model=SceneRead)
def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SceneRead:
    scene = _get_scene_or_404(scene_id, current_user, db)

    project_id = scene.episode.project_id
    updates = payload.model_dump(exclude_unset=True)
    character_ids: list[int] | None = updates.pop("character_ids", None)
    dialogue = updates.pop("dialogue", None)

    # Validate location belongs to this project before applying
    if "location_id" in updates and updates["location_id"] is not None:
        loc = db.get(Location, updates["location_id"])
        if loc is None or loc.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not found in this project.",
            )

    for field, value in updates.items():
        setattr(scene, field, value)

    if dialogue is not None:
        scene.dialogue = json.dumps(
            [d if isinstance(d, dict) else d.model_dump() for d in dialogue],
            ensure_ascii=False,
        )

    if character_ids is not None:
        # Validate all character IDs belong to this project
        for char_id in character_ids:
            char = db.get(Character, char_id)
            if char is None or char.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Character {char_id} not found in this project.",
                )
        # Rebuild join table rows
        db.query(SceneCharacter).filter(SceneCharacter.scene_id == scene.id).delete()
        for char_id in character_ids:
            db.add(SceneCharacter(scene_id=scene.id, character_id=char_id))

    db.commit()
    db.refresh(scene)
    return _scene_read(scene, db)


# ── DELETE /scenes/{id} ───────────────────────────────────────────────────────

@router.delete("/scenes/{scene_id}")
def delete_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    scene = _get_scene_or_404(scene_id, current_user, db)
    db.delete(scene)
    db.commit()
    return {"ok": True}


# ── POST /episodes/{episode_id}/scenes/reorder ────────────────────────────────

@router.post("/episodes/{episode_id}/scenes/reorder")
def reorder_scenes(
    episode_id: int,
    items: list[SceneReorderItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ep: Episode | None = db.get(Episode, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found.")
    if ep.project.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    id_to_order = {item.id: item.order_idx for item in items}

    scenes = db.query(Scene).filter(Scene.episode_id == episode_id).all()
    for scene in scenes:
        if scene.id in id_to_order:
            scene.order_idx = id_to_order[scene.id]

    db.commit()
    return {"ok": True, "updated": len(id_to_order)}
