"""Script generation via Claude API."""

from __future__ import annotations

import json
import types
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Episode, Project, Scene, SceneCharacter, User
from pipeline import slugify

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_or_404(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _write_concept_json(project: Project) -> Path:
    """Write a concept.json for the project to the series directory."""
    series_path = settings.SERIES_DIR / project.series_slug
    series_path.mkdir(parents=True, exist_ok=True)
    (series_path / "episodes").mkdir(exist_ok=True)

    main_characters = [
        f"{c.name} — {c.role or c.backstory or 'unnamed role'}"
        for c in project.characters
    ]

    concept = {
        "title": project.title,
        "premise": project.premise,
        "tone": project.tone,
        "visual_style": project.visual_style,
        "target_audience": "general",
        "setting": project.setting,
        "main_characters": main_characters,
        "season_arc": project.premise,
        "reference_images": [],
        "episodes_per_season": 10,
        "episode_duration_seconds": 30,
    }

    concept_path = series_path / "concept.json"
    concept_path.write_text(json.dumps(concept, indent=2, ensure_ascii=False))
    return concept_path


def _import_episode_json(ep_json: dict, project_id: int, db: Session) -> tuple[int, int]:
    """
    Parse a showrunner episode JSON file and upsert Episode + Scenes into DB.
    Returns (episode_id, scenes_count).
    """
    ep_id_str: str = ep_json.get("id", "ep00")
    ep_num = int(ep_id_str[2:]) if ep_id_str[2:].isdigit() else 0

    # Upsert episode
    existing_ep = (
        db.query(Episode)
        .filter(Episode.project_id == project_id, Episode.number == ep_num)
        .first()
    )
    if existing_ep:
        existing_ep.title = ep_json.get("title", existing_ep.title)
        existing_ep.summary = ep_json.get("summary", existing_ep.summary)
        ep_obj = existing_ep
    else:
        ep_obj = Episode(
            project_id=project_id,
            number=ep_num,
            title=ep_json.get("title", f"Episode {ep_num}"),
            summary=ep_json.get("summary", ""),
        )
        db.add(ep_obj)
        db.flush()

    # Remove existing scenes and rebuild
    db.query(Scene).filter(Scene.episode_id == ep_obj.id).delete()
    db.flush()

    scenes_data: list[dict] = ep_json.get("scenes", [])
    for idx, s in enumerate(scenes_data):
        dialogue_raw = s.get("dialogue", [])
        scene = Scene(
            episode_id=ep_obj.id,
            order_idx=idx,
            clip_length=s.get("clip_length", "medium"),
            visual=s.get("visual", ""),
            narration=s.get("narration"),
            dialogue=json.dumps(dialogue_raw, ensure_ascii=False),
        )
        db.add(scene)

    db.commit()
    db.refresh(ep_obj)
    return ep_obj.id, len(scenes_data)


# ── Schema ────────────────────────────────────────────────────────────────────

class GenerateScriptsRequest(BaseModel):
    episodes: int = 5
    force: bool = False


class GenerateScriptsResponse(BaseModel):
    episodes_created: int
    scenes_created: int
    message: str


# ── POST /projects/{id}/generate-scripts ──────────────────────────────────────

@router.post(
    "/projects/{project_id}/generate-scripts",
    response_model=GenerateScriptsResponse,
)
def generate_scripts(
    project_id: int,
    payload: GenerateScriptsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateScriptsResponse:
    """
    Generate episode scripts for a project via Claude API.

    1. Writes concept.json from project data.
    2. Calls showrunner.cmd_write() to generate bible + episode JSON files.
    3. Imports the generated episodes/scenes into the DB.
    """
    import sys
    sys.path.insert(0, str(Path("/workspace/text-to-video/scripts")))
    import showrunner  # noqa: E402

    project = _get_project_or_404(project_id, current_user, db)

    # Limit episodes to a reasonable range
    num_episodes = max(1, min(payload.episodes, 20))

    # Write concept.json
    _write_concept_json(project)

    # Update episodes_per_season in concept.json
    series_path = settings.SERIES_DIR / project.series_slug
    concept_path = series_path / "concept.json"
    concept_data = json.loads(concept_path.read_text())
    concept_data["episodes_per_season"] = num_episodes
    concept_path.write_text(json.dumps(concept_data, indent=2, ensure_ascii=False))

    # Build a fake args namespace for showrunner
    args = types.SimpleNamespace(
        series=project.series_slug,
        episode=None,
        force=payload.force,
    )

    try:
        showrunner.cmd_write(args)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Script generation failed: {exc}",
        )

    # Import generated episode JSON files into DB
    episodes_dir = series_path / "episodes"
    total_episodes = 0
    total_scenes = 0

    for ep_file in sorted(episodes_dir.glob("ep*.json")):
        ep_json = json.loads(ep_file.read_text())
        _, scene_count = _import_episode_json(ep_json, project_id, db)
        total_episodes += 1
        total_scenes += scene_count

    return GenerateScriptsResponse(
        episodes_created=total_episodes,
        scenes_created=total_scenes,
        message=(
            f"Generated {total_episodes} episodes with {total_scenes} scenes. "
            "Review them in the Episodes tab."
        ),
    )
