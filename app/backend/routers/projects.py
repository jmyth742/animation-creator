"""Project CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Character, Episode, Location, Project, User
from pipeline import slugify
from schemas import (
    CharacterRead,
    EpisodeRead,
    LocationRead,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _project_read(project: Project) -> ProjectRead:
    data = ProjectRead.model_validate(project)
    data.character_count = len(project.characters)
    data.episode_count = len(project.episodes)
    return data


def _assert_owner(project: Project, user: User) -> None:
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")


def _get_project_or_404(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _build_portrait_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/static/series/{path}"


def _build_character_read(char: Character) -> CharacterRead:
    r = CharacterRead.model_validate(char)
    r.portrait_url = _build_portrait_url(char.reference_image_path)
    return r


def _build_location_read(loc: Location) -> LocationRead:
    r = LocationRead.model_validate(loc)
    r.reference_url = _build_portrait_url(loc.reference_image_path)
    return r


def _build_episode_read(ep: Episode) -> EpisodeRead:
    r = EpisodeRead.model_validate(ep)
    r.scenes = []
    return r


# ── GET /projects ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectRead]:
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [_project_read(p) for p in projects]


# ── POST /projects ────────────────────────────────────────────────────────────

@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    base_slug = slugify(payload.title)
    slug = base_slug
    counter = 1
    while db.query(Project).filter(Project.series_slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    project = Project(
        user_id=current_user.id,
        title=payload.title,
        premise=payload.premise,
        tone=payload.tone,
        visual_style=payload.visual_style,
        setting=payload.setting,
        series_slug=slug,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Create the series directory on disk
    (settings.SERIES_DIR / slug / "episodes").mkdir(parents=True, exist_ok=True)

    return _project_read(project)


# ── GET /projects/{id} ────────────────────────────────────────────────────────

@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectDetail:
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    detail = ProjectDetail.model_validate(project)
    detail.character_count = len(project.characters)
    detail.episode_count = len(project.episodes)
    detail.characters = [_build_character_read(c) for c in project.characters]
    detail.locations = [_build_location_read(loc) for loc in project.locations]
    detail.episodes = [_build_episode_read(ep) for ep in project.episodes]
    return detail


# ── PUT /projects/{id} ────────────────────────────────────────────────────────

@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return _project_read(project)


# ── DELETE /projects/{id} ─────────────────────────────────────────────────────

@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    db.delete(project)
    db.commit()
    return {"ok": True}
