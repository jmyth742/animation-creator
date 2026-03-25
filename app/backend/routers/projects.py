"""Project CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Character, Episode, Location, Project, User
import requests as _requests

import pipeline
from pipeline import slugify

COMFYUI_BASE = "http://localhost:8188"
from schemas import (
    CharacterRead,
    EpisodeRead,
    LocationRead,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
    TemplateListItem,
)
from templates import TEMPLATES

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


# ── GET /projects/templates ──────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateListItem])
def list_templates() -> list[TemplateListItem]:
    """Return available project templates."""
    return [
        TemplateListItem(
            id=t["id"],
            title=t["title"],
            description=t["description"],
            genre=t["genre"],
            character_count=len(t["characters"]),
            location_count=len(t["locations"]),
        )
        for t in TEMPLATES
    ]


# ── POST /projects/from-template ────────────────────────────────────────────

@router.post("/from-template", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_from_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    """Create a new project pre-seeded from a template."""
    tpl = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    base_slug = slugify(tpl["title"])
    slug = base_slug
    counter = 1
    while db.query(Project).filter(Project.series_slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    project = Project(
        user_id=current_user.id,
        title=tpl["title"],
        premise=tpl["premise"],
        tone=tpl["tone"],
        visual_style=tpl["visual_style"],
        setting=tpl["setting"],
        series_slug=slug,
    )
    db.add(project)
    db.flush()

    for char_data in tpl["characters"]:
        db.add(Character(
            project_id=project.id,
            name=char_data["name"],
            role=char_data.get("role", ""),
            backstory=char_data.get("backstory", ""),
            visual_description=char_data.get("visual_description", ""),
            voice=char_data.get("voice", "en-GB-SoniaNeural"),
            voice_notes=char_data.get("voice_notes", ""),
        ))

    for loc_data in tpl["locations"]:
        db.add(Location(
            project_id=project.id,
            name=loc_data["name"],
            slug=slugify(loc_data["name"]),
            description=loc_data.get("description", ""),
        ))

    db.commit()
    db.refresh(project)
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


# ── POST /projects/{id}/regenerate-references ────────────────────────────────

@router.post("/{project_id}/regenerate-references")
def start_regen_references(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a background job that regenerates all char portraits + location refs."""
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    try:
        resp = _requests.get(COMFYUI_BASE, timeout=3)
        resp.raise_for_status()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ComfyUI is not reachable at http://localhost:8188. Start ComfyUI and retry.",
        )

    job_id = pipeline.start_regenerate_all_references(project_id)
    total = len(project.characters) + len(project.locations)
    return {"job_id": job_id, "total": total}


@router.get("/{project_id}/regenerate-references/{job_id}")
def get_regen_references_status(
    project_id: int,
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Poll the status of a running bulk reference regeneration job."""
    job = pipeline.get_ref_regen_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ── POST /projects/{id}/regenerate-clips ──────────────────────────────────────

@router.post("/{project_id}/regenerate-clips")
def start_regen_clips(
    project_id: int,
    quality: str = "draft",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a background job that regenerates every scene clip across all episodes."""
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    try:
        resp = _requests.get(COMFYUI_BASE, timeout=3)
        resp.raise_for_status()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ComfyUI is not reachable at http://localhost:8188. Start ComfyUI and retry.",
        )

    total = sum(len(ep.scenes) for ep in project.episodes)
    job_id = pipeline.start_regenerate_all_clips(project_id, quality)
    return {"job_id": job_id, "total": total}


@router.get("/{project_id}/regenerate-clips/{job_id}")
def get_regen_clips_status(
    project_id: int,
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Poll the status of a running bulk clip regeneration job."""
    job = pipeline.get_clip_regen_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ── GET /projects/{id}/theater ────────────────────────────────────────────────

@router.get("/{project_id}/theater")
def get_theater(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return finished episodes with their final video paths for the Theater view."""
    project = _get_project_or_404(project_id, db)
    _assert_owner(project, current_user)

    series_slug = project.series_slug
    results = []
    for ep in sorted(project.episodes, key=lambda e: e.number):
        ep_dir = settings.OUTPUT_DIR / series_slug / f"ep{ep.number:02d}"
        video_path = None
        for candidate_name in [
            f"ep{ep.number:02d}_final_graded.mp4",
            f"ep{ep.number:02d}_final.mp4",
        ]:
            candidate = ep_dir / candidate_name
            if candidate.exists():
                rel = candidate.relative_to(settings.OUTPUT_DIR)
                video_path = f"/static/output/{rel}"
                break

        results.append({
            "id": ep.id,
            "number": ep.number,
            "title": ep.title,
            "summary": ep.summary,
            "video_path": video_path,
            "scene_count": len(ep.scenes),
        })
    return results


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
