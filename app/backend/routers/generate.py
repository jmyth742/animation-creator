"""Script generation via Claude API."""

from __future__ import annotations

import json
import os
import types
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Episode, Project, Scene, SceneCharacter, User
from pipeline import slugify

router = APIRouter()


# ── Enhance endpoint ──────────────────────────────────────────────────────────

_ENHANCE_SYSTEM = """\
You are an expert prompt engineer for AI video generation pipelines.
The user is building an animated series using FLUX (text-to-image) for reference images
and HunyuanVideo (image-to-video) for clip generation.

When asked to enhance a field, return exactly 3 numbered suggestions separated by "---".
Each suggestion should be concise but specific, optimized for AI generation.

Rules per field type:
- visual_style: comma-separated style keywords (e.g. "2D cel animation, bold black outlines, flat color fills, warm earthy palette"). NO full sentences.
- tone: short descriptor phrase (e.g. "bittersweet nostalgia, dry wit, grounded drama"). Keep under 10 words.
- setting: vivid time+place description useful for world-building and scene prompts.
- premise: 2-3 sentences, punchy logline style.
- character_visual: comma-separated physical descriptors used directly in image prompts (clothes, build, face, colours). Specific, visual-only.
- backstory: 2-4 sentences, emotionally grounded, informs how Claude writes the character.
- location: comma-separated visual descriptors for the location (architecture, lighting, mood, era). Used in image generation.
- scene_visual: what is visually happening in the frame — action, composition, character positions, lighting. Cinematic language.
- narration: voiceover text spoken over the scene. Matches series tone.

Format your response as exactly 3 options, like:
1. [suggestion text]
---
2. [suggestion text]
---
3. [suggestion text]
"""

_ENHANCE_FIELD_HINTS = {
    "visual_style": "The user's series visual style field — used in every FLUX and HunyuanVideo prompt.",
    "tone": "The series tone/mood field — shapes how Claude writes dialogue and scene descriptions.",
    "setting": "The series setting field — time period and world context.",
    "premise": "The series premise — 2-3 sentence core concept.",
    "character_visual": "Character visual description — used in portrait generation and every scene prompt.",
    "backstory": "Character backstory — informs how Claude writes the character.",
    "location": "Location visual description — used in FLUX reference image generation.",
    "scene_visual": "Scene visual description — what is happening visually, used in video generation.",
    "narration": "Scene narration/voiceover — spoken text over the scene clip.",
}


class EnhanceRequest(BaseModel):
    field_type: str
    current_text: str
    context: dict = {}


class EnhanceResponse(BaseModel):
    suggestions: list[str]


@router.post("/enhance", response_model=EnhanceResponse)
def enhance_text(
    payload: EnhanceRequest,
    current_user: User = Depends(get_current_user),
) -> EnhanceResponse:
    """Use Claude to generate 2-3 improved suggestions for a description field."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set.")

    hint = _ENHANCE_FIELD_HINTS.get(payload.field_type, "A text field in an animated series project.")
    ctx = payload.context

    context_lines = []
    if ctx.get("series_title"):
        context_lines.append(f"Series title: {ctx['series_title']}")
    if ctx.get("visual_style"):
        context_lines.append(f"Visual style: {ctx['visual_style']}")
    if ctx.get("tone"):
        context_lines.append(f"Tone: {ctx['tone']}")
    if ctx.get("setting"):
        context_lines.append(f"Setting: {ctx['setting']}")
    if ctx.get("premise"):
        context_lines.append(f"Premise: {ctx['premise']}")
    if ctx.get("character_name"):
        context_lines.append(f"Character name: {ctx['character_name']}")
    if ctx.get("character_role"):
        context_lines.append(f"Character role: {ctx['character_role']}")

    context_block = "\n".join(context_lines)
    current = payload.current_text.strip() or "(empty — write something from scratch)"
    context_section = ("Project context:\n" + context_block + "\n") if context_block else ""

    user_message = (
        f"Field type: {payload.field_type}\n"
        f"Field purpose: {hint}\n\n"
        f"{context_section}\n"
        f"Current text:\n{current}\n\n"
        f"Generate 3 enhanced versions of this field."
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=_ENHANCE_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()

    # Parse the 3 suggestions split by ---
    parts = [p.strip() for p in raw.split("---") if p.strip()]
    suggestions = []
    for part in parts[:3]:
        # Strip leading "1. " / "2. " / "3. "
        lines = part.strip().splitlines()
        first = lines[0].strip()
        if first and first[0].isdigit() and len(first) > 2 and first[1] in ".):":
            first = first[2:].strip()
            lines[0] = first
        suggestions.append("\n".join(lines).strip())

    if not suggestions:
        raise HTTPException(status_code=500, detail="Claude returned no suggestions.")

    return EnhanceResponse(suggestions=suggestions)


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
