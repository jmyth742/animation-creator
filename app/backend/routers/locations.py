"""Location CRUD routes."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Location, Project, User
from pipeline import generate_location_reference, slugify
from schemas import (
    LocationCreate,
    LocationRead,
    LocationUpdate,
    ReferenceGenerateResponse,
    SelectReferenceRequest,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_reference_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/static/series/{path}"


def _location_read(loc: Location) -> LocationRead:
    r = LocationRead.model_validate(loc)
    r.reference_url = _build_reference_url(loc.reference_image_path)
    return r


def _get_project_or_404(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _get_location_or_404(location_id: int, user: User, db: Session) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found.")
    if loc.project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return loc


# ── GET /projects/{project_id}/locations ──────────────────────────────────────

@router.get("/projects/{project_id}/locations", response_model=list[LocationRead])
def list_locations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LocationRead]:
    _get_project_or_404(project_id, current_user, db)
    locs = db.query(Location).filter(Location.project_id == project_id).all()
    return [_location_read(loc) for loc in locs]


# ── POST /projects/{project_id}/locations ─────────────────────────────────────

@router.post(
    "/projects/{project_id}/locations",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    project_id: int,
    payload: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    _get_project_or_404(project_id, current_user, db)

    loc = Location(
        project_id=project_id,
        name=payload.name,
        slug=slugify(payload.name),
        description=payload.description,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _location_read(loc)


# ── PUT /locations/{id} ───────────────────────────────────────────────────────

@router.put("/locations/{location_id}", response_model=LocationRead)
def update_location(
    location_id: int,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    loc = _get_location_or_404(location_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        loc.slug = slugify(updates["name"])
    for field, value in updates.items():
        setattr(loc, field, value)

    db.commit()
    db.refresh(loc)
    return _location_read(loc)


# ── DELETE /locations/{id} ────────────────────────────────────────────────────

@router.delete("/locations/{location_id}")
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    loc = _get_location_or_404(location_id, current_user, db)
    db.delete(loc)
    db.commit()
    return {"ok": True}


# ── POST /locations/{id}/generate-reference ───────────────────────────────────

@router.post("/locations/{location_id}/generate-reference", response_model=ReferenceGenerateResponse)
def generate_reference(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReferenceGenerateResponse:
    loc = _get_location_or_404(location_id, current_user, db)
    if not loc.description:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Location needs a visual description before generating reference images.",
        )
    try:
        rel_paths = generate_location_reference(location_id, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    urls = [f"/static/series/{p}" for p in rel_paths]
    return ReferenceGenerateResponse(
        reference_urls=urls,
        message=f"Generated {len(urls)} reference image(s).",
    )


# ── POST /locations/{id}/select-reference ─────────────────────────────────────

@router.post("/locations/{location_id}/select-reference", response_model=LocationRead)
def select_reference(
    location_id: int,
    payload: SelectReferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    loc = _get_location_or_404(location_id, current_user, db)

    src = settings.SERIES_DIR / payload.reference_path
    if not src.exists():
        raise HTTPException(status_code=404, detail="Reference image file not found.")

    # Copy to the canonical path showrunner.get_scene_seed_image() expects
    series_slug = loc.project.series_slug
    ref_dir = settings.SERIES_DIR / series_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)
    canonical = ref_dir / f"loc_{loc.id}.png"
    shutil.copy2(src, canonical)

    loc.reference_image_path = payload.reference_path
    db.commit()
    db.refresh(loc)
    return _location_read(loc)
