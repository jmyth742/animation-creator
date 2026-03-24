"""Episode CRUD routes, scene listing, and episode production."""

from __future__ import annotations

import json
import threading
from typing import Any

import requests as _requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import (
    Character,
    Episode,
    GenerationJob,
    Location,
    Project,
    Scene,
    SceneCharacter,
    User,
)
from pipeline import produce_episode_job
from schemas import (
    CharacterRead,
    EpisodeCreate,
    EpisodeRead,
    EpisodeUpdate,
    GenerationJobRead,
    ProduceResponse,
    SceneCreate,
    SceneRead,
)

router = APIRouter()

COMFYUI_BASE = "http://localhost:8188"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_or_404(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_episode_or_404(episode_id: int, user: User, db: Session) -> Episode:
    ep = db.get(Episode, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found.")
    if ep.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return ep


def _build_portrait_url(path: str | None) -> str | None:
    return f"/static/series/{path}" if path else None


def _character_read(char: Character) -> CharacterRead:
    r = CharacterRead.model_validate(char)
    r.portrait_url = _build_portrait_url(char.reference_image_path)
    return r


def _scene_read(scene: Scene, db: Session) -> SceneRead:
    r = SceneRead.model_validate(scene)
    r.characters = [
        _character_read(sc.character) for sc in scene.scene_characters
    ]
    r.preview_url = (
        f"/static/clips/{scene.output_clip_path}" if scene.output_clip_path else None
    )
    if scene.location_id:
        loc: Location | None = db.get(Location, scene.location_id)
        r.location_name = loc.name if loc else None
    return r


def _episode_read_no_scenes(ep: Episode) -> EpisodeRead:
    r = EpisodeRead.model_validate(ep)
    r.scenes = []
    return r


def _episode_read_with_scenes(ep: Episode, db: Session) -> EpisodeRead:
    r = EpisodeRead.model_validate(ep)
    r.scenes = [_scene_read(s, db) for s in ep.scenes]
    return r


# ── GET /projects/{project_id}/episodes ───────────────────────────────────────

@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeRead])
def list_episodes(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EpisodeRead]:
    _get_project_or_404(project_id, current_user, db)
    eps = (
        db.query(Episode)
        .filter(Episode.project_id == project_id)
        .order_by(Episode.number)
        .all()
    )
    return [_episode_read_no_scenes(ep) for ep in eps]


# ── POST /projects/{project_id}/episodes ──────────────────────────────────────

@router.post(
    "/projects/{project_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_episode(
    project_id: int,
    payload: EpisodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EpisodeRead:
    _get_project_or_404(project_id, current_user, db)

    ep = Episode(
        project_id=project_id,
        number=payload.number,
        title=payload.title,
        summary=payload.summary,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return _episode_read_no_scenes(ep)


# ── GET /episodes/{id} ────────────────────────────────────────────────────────

@router.get("/episodes/{episode_id}", response_model=EpisodeRead)
def get_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EpisodeRead:
    ep = _get_episode_or_404(episode_id, current_user, db)
    return _episode_read_with_scenes(ep, db)


# ── PUT /episodes/{id} ────────────────────────────────────────────────────────

@router.put("/episodes/{episode_id}", response_model=EpisodeRead)
def update_episode(
    episode_id: int,
    payload: EpisodeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EpisodeRead:
    ep = _get_episode_or_404(episode_id, current_user, db)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ep, field, value)

    db.commit()
    db.refresh(ep)
    return _episode_read_no_scenes(ep)


# ── DELETE /episodes/{id} ─────────────────────────────────────────────────────

@router.delete("/episodes/{episode_id}")
def delete_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ep = _get_episode_or_404(episode_id, current_user, db)
    db.delete(ep)
    db.commit()
    return {"ok": True}


# ── GET /episodes/{id}/scenes ─────────────────────────────────────────────────

@router.get("/episodes/{episode_id}/scenes", response_model=list[SceneRead])
def list_scenes(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SceneRead]:
    ep = _get_episode_or_404(episode_id, current_user, db)
    return [_scene_read(s, db) for s in ep.scenes]


# ── POST /episodes/{id}/scenes ────────────────────────────────────────────────

@router.post(
    "/episodes/{episode_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scene(
    episode_id: int,
    payload: SceneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SceneRead:
    ep = _get_episode_or_404(episode_id, current_user, db)
    project_id = ep.project_id

    # Validate location belongs to this project
    if payload.location_id is not None:
        loc = db.get(Location, payload.location_id)
        if loc is None or loc.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location not found in this project.",
            )

    # Validate all character IDs belong to this project
    for char_id in payload.character_ids:
        char = db.get(Character, char_id)
        if char is None or char.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Character {char_id} not found in this project.",
            )

    scene = Scene(
        episode_id=episode_id,
        order_idx=payload.order_idx,
        location_id=payload.location_id,
        clip_length=payload.clip_length,
        visual=payload.visual,
        narration=payload.narration,
        dialogue=json.dumps(
            [d.model_dump() for d in payload.dialogue], ensure_ascii=False
        ),
    )
    db.add(scene)
    db.flush()  # get scene.id

    for char_id in payload.character_ids:
        db.add(SceneCharacter(scene_id=scene.id, character_id=char_id))

    db.commit()
    db.refresh(scene)
    return _scene_read(scene, db)


# ── POST /episodes/{id}/produce ───────────────────────────────────────────────

@router.post("/episodes/{episode_id}/produce", response_model=ProduceResponse)
def produce_episode(
    episode_id: int,
    quality: str = "draft",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProduceResponse:
    ep = _get_episode_or_404(episode_id, current_user, db)

    # Check ComfyUI is reachable
    try:
        resp = _requests.get(COMFYUI_BASE, timeout=3)
        resp.raise_for_status()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ComfyUI is not reachable at http://localhost:8188. Start ComfyUI and retry.",
        )

    job = GenerationJob(episode_id=episode_id)
    db.add(job)
    db.commit()
    db.refresh(job)

    thread = threading.Thread(
        target=produce_episode_job,
        args=(job.id, episode_id, quality),
        daemon=True,
    )
    thread.start()

    return ProduceResponse(
        job_id=job.id,
        message=f"Production job {job.id} started for episode {ep.number} at quality='{quality}'.",
    )
