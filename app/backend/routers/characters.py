"""Character CRUD routes and portrait generation."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Character, Project, User
from pipeline import generate_character_portrait, export_project_in_background, slugify
from schemas import (
    CharacterCreate,
    CharacterRead,
    CharacterUpdate,
    PortraitGenerateResponse,
    SelectPortraitRequest,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_portrait_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/static/series/{path}"


def _character_read(char: Character) -> CharacterRead:
    r = CharacterRead.model_validate(char)
    r.portrait_url = _build_portrait_url(char.reference_image_path)
    return r


def _get_project_or_404(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_character_or_404(character_id: int, user: User, db: Session) -> Character:
    char = db.get(Character, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    if char.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return char


# ── GET /projects/{project_id}/characters ─────────────────────────────────────

@router.get("/projects/{project_id}/characters", response_model=list[CharacterRead])
def list_characters(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CharacterRead]:
    _get_project_or_404(project_id, current_user, db)
    chars = db.query(Character).filter(Character.project_id == project_id).all()
    return [_character_read(c) for c in chars]


# ── POST /projects/{project_id}/characters ────────────────────────────────────

@router.post(
    "/projects/{project_id}/characters",
    response_model=CharacterRead,
    status_code=status.HTTP_201_CREATED,
)
def create_character(
    project_id: int,
    payload: CharacterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterRead:
    _get_project_or_404(project_id, current_user, db)

    char = Character(
        project_id=project_id,
        name=payload.name,
        role=payload.role,
        backstory=payload.backstory,
        visual_description=payload.visual_description,
        voice=payload.voice,
        voice_notes=payload.voice_notes,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    export_project_in_background(project_id)
    return _character_read(char)


# ── GET /characters/{id} ──────────────────────────────────────────────────────

@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterRead:
    char = _get_character_or_404(character_id, current_user, db)
    return _character_read(char)


# ── PUT /characters/{id} ──────────────────────────────────────────────────────

@router.put("/characters/{character_id}", response_model=CharacterRead)
def update_character(
    character_id: int,
    payload: CharacterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterRead:
    char = _get_character_or_404(character_id, current_user, db)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(char, field, value)

    db.commit()
    db.refresh(char)
    export_project_in_background(char.project_id)
    return _character_read(char)


# ── DELETE /characters/{id} ───────────────────────────────────────────────────

@router.delete("/characters/{character_id}")
def delete_character(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    char = _get_character_or_404(character_id, current_user, db)
    project_id = char.project_id
    db.delete(char)
    db.commit()
    export_project_in_background(project_id)
    return {"ok": True}


# ── POST /characters/{id}/generate-portrait ───────────────────────────────────

@router.post("/characters/{character_id}/generate-portrait", response_model=PortraitGenerateResponse)
def generate_portrait(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortraitGenerateResponse:
    """
    Synchronously generate up to 3 portrait candidates via ComfyUI
    (takes ~30 s per candidate).  Returns the URL list when complete.
    """
    _get_character_or_404(character_id, current_user, db)

    try:
        paths = generate_character_portrait(character_id, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Portrait generation failed: {exc}",
        )

    portrait_urls = [f"/static/series/{p}" for p in paths]
    return PortraitGenerateResponse(
        portrait_urls=portrait_urls,
        message=f"Generated {len(portrait_urls)} portrait(s).",
    )


# ── POST /characters/{id}/select-portrait ─────────────────────────────────────

@router.post("/characters/{character_id}/select-portrait", response_model=CharacterRead)
def select_portrait(
    character_id: int,
    payload: SelectPortraitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterRead:
    """
    Set the canonical portrait for a character.

    Copies the chosen portrait to the path showrunner expects:
        series/{slug}/reference_images/char_{id}.png

    This is the file get_scene_seed_image() looks for when deciding
    whether to use I2V seeding for scenes featuring this character.
    """
    char = _get_character_or_404(character_id, current_user, db)

    src = settings.SERIES_DIR / payload.portrait_path
    if not src.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portrait file not found.",
        )

    # Copy to canonical path showrunner looks for
    series_slug = char.project.series_slug
    canonical = (
        settings.SERIES_DIR / series_slug / "reference_images" / f"char_{char.id}.png"
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, canonical)

    char.reference_image_path = payload.portrait_path
    db.commit()
    db.refresh(char)
    return _character_read(char)
