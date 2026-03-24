"""
Showrunner integration layer.

All heavy lifting (video generation, audio synthesis, stitching) is delegated
to the existing showrunner.py pipeline script.  This module:

  1. Exports DB data to the on-disk JSON format expected by showrunner.
  2. Runs showrunner.cmd_produce() in a background thread for episode production.
  3. Calls showrunner's ComfyUI helpers to generate character portraits.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import threading
import types
import uuid
from contextlib import redirect_stdout
from pathlib import Path
import datetime
import time


# ── In-memory reference regeneration job registry ─────────────────────────────
# { job_id: { status, progress, total, items: [{label, status, error?}], error } }
_ref_regen_jobs: dict[str, dict] = {}

# ── Bootstrap showrunner import ───────────────────────────────────────────────

sys.path.insert(0, str(Path("/workspace/text-to-video/scripts")))
import showrunner  # noqa: E402  (side-effects intentional)

from config import settings
from database import SessionLocal

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Lowercase, replace spaces/special chars with hyphens, collapse runs."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


# ── Bible / episode file export ───────────────────────────────────────────────

def export_project_to_files(project_id: int, db) -> tuple[str, Path]:
    """
    Read the project (characters, locations, episodes, scenes) from the database
    and write the bible.json + per-episode JSON files expected by showrunner.

    Returns (series_slug, series_path).
    """
    from models import Project, Character, Location, Episode, Scene, SceneCharacter

    project = db.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    series_slug = project.series_slug
    series_path = settings.SERIES_DIR / series_slug
    series_path.mkdir(parents=True, exist_ok=True)
    (series_path / "episodes").mkdir(exist_ok=True)

    # ── Build characters dict ─────────────────────────────────────────────────
    characters_dict: dict[str, dict] = {}
    for char in project.characters:
        characters_dict[f"char_{char.id}"] = {
            "name": char.name,
            "visual": char.visual_description,
            "voice": char.voice,
            "voice_notes": char.voice_notes,
            "role": char.role,
        }

    # ── Build locations dict ──────────────────────────────────────────────────
    locations_dict: dict[str, str] = {}
    for loc in project.locations:
        locations_dict[f"loc_{loc.id}"] = loc.description

    # ── Write bible.json ──────────────────────────────────────────────────────
    bible: dict = {
        "series": {
            "title": project.title,
            "style": project.visual_style,
            "tone": project.tone,
            "format": {"resolution": [480, 320], "fps": 24},
        },
        "characters": characters_dict,
        "world": {
            "setting": project.setting,
            "locations": locations_dict,
            "rules": [],
        },
        "season_arc": {
            "summary": project.premise,
            "themes": [],
            "progression": "",
        },
        "narrator": {
            "voice": "en-GB-SoniaNeural",
            "style": "Detached documentary narrator.",
        },
    }

    bible_path = series_path / "bible.json"
    bible_path.write_text(json.dumps(bible, indent=2, ensure_ascii=False))

    # ── Write per-episode JSON ────────────────────────────────────────────────
    for episode in project.episodes:
        ep_id = f"ep{episode.number:02d}"
        scenes_list: list[dict] = []

        for scene in episode.scenes:
            # Resolve character IDs for this scene
            char_ids = [
                f"char_{sc.character_id}" for sc in scene.scene_characters
            ]

            # Parse stored dialogue JSON; translate bare names → char_* keys
            try:
                raw_dialogue: list[dict] = json.loads(scene.dialogue or "[]")
            except (json.JSONDecodeError, TypeError):
                raw_dialogue = []

            # Resolve scene-level reference image to an absolute path so
            # showrunner.get_scene_seed_image() can find it without knowing SERIES_DIR.
            scene_ref: str | None = None
            if scene.reference_image_path:
                candidate = settings.SERIES_DIR / scene.reference_image_path
                if candidate.exists():
                    scene_ref = str(candidate)

            scene_dict: dict = {
                "id": f"{ep_id}_s{scene.order_idx + 1:02d}",
                "location": (
                    f"loc_{scene.location_id}" if scene.location_id else "loc_unknown"
                ),
                "characters": char_ids,
                "clip_length": scene.clip_length,
                "visual": scene.visual,
                "narration": scene.narration,
                "dialogue": raw_dialogue,
                "reference_image": scene_ref,  # None when not set
            }
            scenes_list.append(scene_dict)

        ep_json: dict = {
            "id": ep_id,
            "title": episode.title,
            "summary": episode.summary,
            "scenes": scenes_list,
        }

        ep_file = series_path / "episodes" / f"{ep_id}.json"
        ep_file.write_text(json.dumps(ep_json, indent=2, ensure_ascii=False))

    return series_slug, series_path


# ── Scene clip back-fill ──────────────────────────────────────────────────────

def _backfill_scene_clips(episode_id: int, db) -> None:
    """
    After a full episode production run, match generated clip files to scene
    rows and update output_clip_path + status so the UI can show previews.
    """
    from models import Episode, Scene

    if not settings.COMFYUI_OUTPUT.exists():
        return

    episode = db.get(Episode, episode_id)
    if episode is None:
        return

    ep_id = f"ep{episode.number:02d}"
    for scene in episode.scenes:
        clip_prefix = f"{ep_id}_s{scene.order_idx + 1:02d}"
        clip_path = showrunner.find_latest_clip(clip_prefix)
        if clip_path:
            try:
                rel = str(Path(clip_path).relative_to(settings.COMFYUI_OUTPUT))
                scene.output_clip_path = rel
                scene.status = "done"
            except ValueError:
                pass

    try:
        db.commit()
    except Exception:
        db.rollback()


# ── Background episode production ─────────────────────────────────────────────

def produce_episode_job(
    job_id: int,
    episode_id: int,
    quality: str = "draft",
) -> None:
    """
    Intended to run in a background threading.Thread.

    Lifecycle
    ---------
    1. Acquires its own DB session from the scoped_session factory.
    2. Sets job.status = "running".
    3. Exports project files to disk.
    4. Builds a synthetic argparse.Namespace and delegates to
       showrunner.cmd_produce(args), capturing stdout.
    5. Periodically flushes captured stdout to job.log_text.
    6. On completion sets job.status = "complete" / "error" and records
       job.completed_at + job.progress_pct = 100.
    """
    from models import Episode, GenerationJob

    db = SessionLocal()

    def _flush_log(buf: io.StringIO, job: GenerationJob) -> None:
        content = buf.getvalue()
        if content:
            job.log_text = content
            db.commit()

    def _count_expected_clips(ep_id: int) -> int:
        ep = db.get(Episode, ep_id)
        return len(ep.scenes) if ep else 0

    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        episode = db.get(Episode, episode_id)
        if episode is None:
            job.status = "error"
            job.log_text += "\nEpisode not found."
            db.commit()
            return

        series_slug, _ = export_project_to_files(episode.project_id, db)

        expected_clips = _count_expected_clips(episode_id)

        # Build a namespace that mirrors what argparse would produce for
        # `showrunner.py produce <series> --episode N --quality Q`
        args = types.SimpleNamespace(
            series=series_slug,
            episode=episode.number,
            quality=quality,
            steps=showrunner.QUALITY_STEPS.get(quality, 15),
            image=None,
            seed_base=1000,
            resume=True,
            no_audio=False,
            no_crossfade=False,
            no_grade=False,
            no_subs=False,
            no_ambience=False,
            no_music=False,
            flagged_only=False,
            enhance=False,
        )

        log_buf = io.StringIO()
        error_msg: str | None = None

        # Run showrunner in the same thread, capturing its stdout output.
        # We update progress_pct by counting clips that appear in COMFYUI_OUTPUT.
        ep_prefix = f"ep{episode.number:02d}"

        def _progress_thread() -> None:
            """Lightweight poller — uses its own DB session to avoid contention."""
            pdb = SessionLocal()
            try:
                while True:
                    time.sleep(5)
                    try:
                        j = pdb.get(GenerationJob, job_id)
                        pdb.refresh(j)
                        if j is None or j.status in ("complete", "error"):
                            break
                        if expected_clips > 0 and settings.COMFYUI_OUTPUT.exists():
                            found = len(
                                list(settings.COMFYUI_OUTPUT.glob(f"{ep_prefix}_s*.mp4"))
                            )
                            pct = min(int(found / expected_clips * 95), 95)
                            j.progress_pct = pct
                        content = log_buf.getvalue()
                        if content:
                            j.log_text = content
                        pdb.commit()
                    except Exception:
                        try:
                            pdb.rollback()
                        except Exception:
                            pass
            finally:
                pdb.close()

        progress_t = threading.Thread(target=_progress_thread, daemon=True)
        progress_t.start()

        try:
            with redirect_stdout(log_buf):
                showrunner.cmd_produce(args)
        except Exception as exc:
            error_msg = str(exc)

        # Final flush
        job = db.get(GenerationJob, job_id)
        if job is None:
            return

        job.log_text = log_buf.getvalue()
        job.completed_at = datetime.datetime.now(datetime.timezone.utc)

        if error_msg:
            job.status = "error"
            job.log_text += f"\n\n[ERROR] {error_msg}"
        else:
            job.status = "complete"
            job.progress_pct = 100

        db.commit()

        # Back-fill scene clip paths so preview_url works in the UI
        if not error_msg:
            _backfill_scene_clips(episode_id, db)



    except Exception as exc:
        try:
            job = db.get(GenerationJob, job_id)
            if job:
                job.status = "error"
                job.log_text += f"\n\n[FATAL] {exc}"
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Clip version archiving ────────────────────────────────────────────────────

def _archive_existing_clip(scene, project, prompt: str, quality: str, seed_image: str | None, db) -> None:
    """
    If the scene already has a generated clip, copy it to an archive filename
    and record a SceneClipVersion row before it gets overwritten.
    """
    from models import SceneClipVersion

    if not scene.output_clip_path:
        return

    src = settings.COMFYUI_OUTPUT / scene.output_clip_path
    if not src.exists():
        return

    # Archive filename: same stem + timestamp suffix
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{src.stem}_v{ts}{src.suffix}"
    archive_dir = settings.COMFYUI_OUTPUT / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / archive_name

    shutil.copy2(src, archive_path)
    rel = f"archive/{archive_name}"

    version = SceneClipVersion(
        scene_id=scene.id,
        clip_path=rel,
        quality=quality,
        visual_style=project.visual_style,
        tone=project.tone,
        prompt=prompt,
        seed_image=seed_image,
    )
    db.add(version)
    db.commit()


# ── Single-scene regeneration ─────────────────────────────────────────────────

def generate_single_scene_job(scene_id: int, quality: str = "draft") -> None:
    """
    Intended to run in a background threading.Thread.

    Generates (or re-generates) a single scene clip without touching the rest
    of the episode.  Updates scene.status and scene.output_clip_path on completion.
    """
    from models import Scene

    db = SessionLocal()
    try:
        scene = db.get(Scene, scene_id)
        if scene is None:
            return

        scene.status = "generating"
        db.commit()

        episode = scene.episode
        project = episode.project

        # Export current project state to JSON (bible + episode files)
        series_slug, series_path_dir = export_project_to_files(project.id, db)

        # Load bible dict that showrunner functions expect
        bible = json.loads((series_path_dir / "bible.json").read_text())

        # Build a scene dict matching the showrunner JSON format
        ep_id = f"ep{episode.number:02d}"
        char_ids = [f"char_{sc.character_id}" for sc in scene.scene_characters]
        try:
            raw_dialogue = json.loads(scene.dialogue or "[]")
        except (json.JSONDecodeError, TypeError):
            raw_dialogue = []

        scene_dict: dict = {
            "id": f"{ep_id}_s{scene.order_idx + 1:02d}",
            "location": f"loc_{scene.location_id}" if scene.location_id else "loc_unknown",
            "characters": char_ids,
            "clip_length": scene.clip_length,
            "visual": scene.visual,
            "narration": scene.narration,
            "dialogue": raw_dialogue,
        }

        prompt = showrunner.build_scene_prompt(scene_dict, bible)

        # Scene-specific reference takes highest priority.
        # Must call copy_to_input() so build_i2v_workflow's LoadImage node
        # can find the file by name in ComfyUI's input directory.
        seed_image: str | None = None
        if scene.reference_image_path:
            candidate = settings.SERIES_DIR / scene.reference_image_path
            if candidate.exists():
                seed_image = showrunner.copy_to_input(str(candidate))
        if seed_image is None:
            seed_image = showrunner.get_scene_seed_image(scene_dict, series_slug, None)

        # Archive the current clip (if any) before overwriting it
        _archive_existing_clip(scene, project, prompt, quality, seed_image, db)

        cl = showrunner.CLIP_LENGTHS.get(scene.clip_length, showrunner.CLIP_LENGTHS["medium"])
        frames = cl["frames"]
        steps = showrunner.QUALITY_STEPS.get(quality, 15)
        clip_prefix = scene_dict["id"]
        seed = 1000 + scene.order_idx + 1

        if seed_image:
            wf = showrunner.build_i2v_workflow(
                prompt, seed_image, seed, clip_prefix, frames, steps
            )
        else:
            wf = showrunner.build_t2v_workflow(prompt, seed, clip_prefix, frames, steps)

        prompt_id = showrunner.queue_prompt(wf)
        success = showrunner.poll_until_done(prompt_id)

        # Re-fetch scene in case DB session is stale
        scene = db.get(Scene, scene_id)
        if scene is None:
            return

        if success:
            clip_path = showrunner.find_latest_clip(clip_prefix)
            if clip_path:
                rel = Path(clip_path).relative_to(settings.COMFYUI_OUTPUT)
                scene.output_clip_path = str(rel)
                scene.status = "done"
            else:
                scene.status = "error"
        else:
            scene.status = "error"

        db.commit()

    except Exception as exc:
        try:
            db.rollback()
            scene = db.get(Scene, scene_id)
            if scene:
                scene.status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Character portrait generation ─────────────────────────────────────────────

def generate_character_portrait(character_id: int, db) -> list[str]:
    """
    Generate 3 portrait candidates for a character (different seeds).

    Uses showrunner.build_ref_workflow + queue_prompt + poll_until_done.
    The first successful candidate is stored in Character.reference_image_path.

    Returns a list of paths relative to the series reference_images directory
    (as URL-friendly strings).
    """
    import requests as _requests
    from models import Character

    char = db.get(Character, character_id)
    if char is None:
        raise ValueError(f"Character {character_id} not found")

    project = char.project
    series_slug = project.series_slug
    style = project.visual_style

    ref_dir = settings.SERIES_DIR / series_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)

    # ComfyUI saves images to ComfyUI/output/refs/<prefix>_*.png
    comfy_refs_out = settings.COMFYUI_DIR / "output" / "refs"

    # Style goes FIRST — earliest tokens carry most weight in diffusion models.
    # "Video frame" anchors FLUX toward something HunyuanVideo will naturally extend.
    prompt_parts: list[str] = []
    if style:
        prompt_parts.append(style)
    if project.setting:
        prompt_parts.append(project.setting)
    if project.tone:
        prompt_parts.append(project.tone)
    prompt_parts.append("cinematic video frame")
    prompt_parts.append(f"portrait of {char.visual_description}")
    prompt_parts.append("facing camera, neutral expression, upper body visible")
    prompt = ", ".join(filter(None, prompt_parts))
    prefix = f"char_{char.id}"

    seeds = [999, 1234, 5678]
    saved_paths: list[str] = []

    for i, seed in enumerate(seeds):
        candidate_label = f"{prefix}_v{i+1}"
        out_png = ref_dir / f"{candidate_label}.png"

        # Use FLUX T2I (portrait orientation — 480×640)
        wf = showrunner.build_t2i_workflow(prompt, seed=seed, prefix=candidate_label, width=480, height=640)

        try:
            prompt_id = showrunner.queue_prompt(wf)
        except _requests.ConnectionError:
            raise RuntimeError("ComfyUI not reachable at http://localhost:8188")

        success = showrunner.poll_until_done(prompt_id)
        if not success:
            continue

        # Find the generated file in ComfyUI output
        candidates = (
            sorted(
                comfy_refs_out.glob(f"{candidate_label}*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if comfy_refs_out.exists()
            else []
        )
        if candidates:
            shutil.copy2(candidates[0], out_png)
            rel_path = f"{series_slug}/reference_images/{candidate_label}.png"
            saved_paths.append(rel_path)

    # Persist the first generated portrait path on the character
    if saved_paths:
        char.reference_image_path = saved_paths[0]
        db.commit()

    return saved_paths


# ── Location reference image generation ───────────────────────────────────────

def generate_location_reference(location_id: int, db) -> list[str]:
    """
    Generate 3 reference image candidates for a location (different seeds).

    The prompt is grounded in the project's visual_style, setting, and tone so
    every location looks consistent with the overall series aesthetic.

    The canonical file (loc_{id}.png) is what showrunner.get_scene_seed_image()
    uses as the I2V seed for establishing/wide shots in that location.

    Returns a list of paths relative to settings.SERIES_DIR.
    """
    import requests as _requests
    from models import Location

    loc = db.get(Location, location_id)
    if loc is None:
        raise ValueError(f"Location {location_id} not found")

    project = loc.project
    series_slug = project.series_slug

    ref_dir = settings.SERIES_DIR / series_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)

    comfy_refs_out = settings.COMFYUI_DIR / "output" / "refs"

    # Style goes FIRST — earliest tokens carry most weight in diffusion models.
    prompt_parts: list[str] = []
    if project.visual_style:
        prompt_parts.append(project.visual_style)
    if project.setting:
        prompt_parts.append(project.setting)
    if project.tone:
        prompt_parts.append(project.tone)
    prompt_parts.append("cinematic video frame")
    prompt_parts.append(loc.description or loc.name)
    prompt_parts.append("establishing shot, wide angle, no people, empty scene")
    prompt = ", ".join(filter(None, prompt_parts))

    prefix = f"loc_{loc.id}"
    seeds = [111, 2222, 33333]
    saved_paths: list[str] = []

    for i, seed in enumerate(seeds):
        candidate_label = f"{prefix}_v{i + 1}"
        out_png = ref_dir / f"{candidate_label}.png"

        # Use FLUX T2I (landscape orientation — 640×360 matches video aspect ratio)
        wf = showrunner.build_t2i_workflow(prompt, seed=seed, prefix=candidate_label, width=640, height=360)

        try:
            prompt_id = showrunner.queue_prompt(wf)
        except _requests.ConnectionError:
            raise RuntimeError("ComfyUI not reachable at http://localhost:8188")

        success = showrunner.poll_until_done(prompt_id)
        if not success:
            continue

        candidates = (
            sorted(
                comfy_refs_out.glob(f"{candidate_label}*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if comfy_refs_out.exists()
            else []
        )
        if candidates:
            shutil.copy2(candidates[0], out_png)
            rel_path = f"{series_slug}/reference_images/{candidate_label}.png"
            saved_paths.append(rel_path)

    if saved_paths:
        loc.reference_image_path = saved_paths[0]
        db.commit()

    return saved_paths


# ── Scene reference image generation ──────────────────────────────────────────

def generate_scene_reference(scene_id: int, db) -> list[str]:
    """
    Generate 3 reference still candidates for a specific scene using FLUX T2I.

    The prompt is assembled from the scene's visual description, characters,
    location, and the project's overall visual aesthetic — giving the T2I model
    full context to produce an accurate composition still.

    When selected as canonical, the still is stored at:
        series/{slug}/reference_images/scene_{id}.png
    and used as the I2V seed for that scene's clip in generate_single_scene_job,
    taking priority over the generic char/location ref lookup.

    Returns a list of paths relative to settings.SERIES_DIR.
    """
    import requests as _requests
    from models import Scene

    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"Scene {scene_id} not found")

    episode = scene.episode
    project = episode.project
    series_slug = project.series_slug

    ref_dir = settings.SERIES_DIR / series_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)

    comfy_refs_out = settings.COMFYUI_DIR / "output" / "refs"

    # Build a rich prompt: style FIRST for maximum influence, then scene content.
    prompt_parts: list[str] = []

    # Project aesthetic anchors the whole image
    if project.visual_style:
        prompt_parts.append(project.visual_style)
    if project.setting:
        prompt_parts.append(project.setting)
    if project.tone:
        prompt_parts.append(project.tone)
    prompt_parts.append("cinematic video frame")

    # Scene content
    if scene.visual:
        prompt_parts.append(scene.visual)

    # Location description
    if scene.location:
        loc_desc = scene.location.description or scene.location.name
        if loc_desc:
            prompt_parts.append(loc_desc)

    # Characters visible in this scene
    for sc in scene.scene_characters:
        char = sc.character
        if char.visual_description:
            prompt_parts.append(char.visual_description)

    prompt_parts.append("high detail, sharp focus")
    prompt = ". ".join(filter(None, prompt_parts))

    prefix = f"scene_{scene_id}"
    seeds = [42, 777, 9999]
    saved_paths: list[str] = []

    for i, seed in enumerate(seeds):
        candidate_label = f"{prefix}_v{i + 1}"
        out_png = ref_dir / f"{candidate_label}.png"

        # 640×360 landscape — matches video clip aspect ratio
        wf = showrunner.build_t2i_workflow(prompt, seed=seed, prefix=candidate_label, width=640, height=360)

        try:
            prompt_id = showrunner.queue_prompt(wf)
        except _requests.ConnectionError:
            raise RuntimeError("ComfyUI not reachable at http://localhost:8188")

        success = showrunner.poll_until_done(prompt_id)
        if not success:
            continue

        candidates = (
            sorted(
                comfy_refs_out.glob(f"{candidate_label}*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if comfy_refs_out.exists()
            else []
        )
        if candidates:
            shutil.copy2(candidates[0], out_png)
            rel_path = f"{series_slug}/reference_images/{candidate_label}.png"
            saved_paths.append(rel_path)

    if saved_paths:
        scene.reference_image_path = saved_paths[0]
        db.commit()

    return saved_paths


# ── Bulk clip regeneration ────────────────────────────────────────────────────

_clip_regen_jobs: dict[str, dict] = {}


def get_clip_regen_job(job_id: str) -> dict | None:
    return _clip_regen_jobs.get(job_id)


def start_regenerate_all_clips(project_id: int, quality: str = "draft") -> str:
    """
    Start a background thread that regenerates every scene clip across all episodes
    in the project, sequentially, using the current reference images as I2V seeds.
    """
    job_id = str(uuid.uuid4())
    _clip_regen_jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "items": [],
        "error": None,
    }
    thread = threading.Thread(
        target=_regenerate_all_clips_bg,
        args=(project_id, job_id, quality),
        daemon=True,
    )
    thread.start()
    return job_id


def _regenerate_all_clips_bg(project_id: int, job_id: str, quality: str) -> None:
    """
    Background worker: regenerates every scene clip in the project, in episode/scene order.

    Calls generate_single_scene_job() for each scene so that all the same logic
    applies — reference image priority, prompt building, I2V seeding, etc.
    """
    from models import Project, Scene

    db = SessionLocal()
    job = _clip_regen_jobs[job_id]

    try:
        project = db.get(Project, project_id)
        if project is None:
            job["status"] = "error"
            job["error"] = "Project not found"
            return

        # Collect all scenes across all episodes, ordered
        # Collect scene IDs + labels while DB is open
        all_scenes: list[tuple[str, int]] = []
        for episode in sorted(project.episodes, key=lambda e: e.number):
            for scene in sorted(episode.scenes, key=lambda s: s.order_idx):
                ep_label = f"EP{episode.number:02d} · SC{scene.order_idx + 1:02d}"
                visual_preview = (scene.visual or "")[:50] + ("…" if len(scene.visual or "") > 50 else "")
                all_scenes.append((f"{ep_label} — {visual_preview}", scene.id))

        job["total"] = len(all_scenes)
        db.close()  # release before long-running loop

        done = 0
        for label, scene_id in all_scenes:
            item: dict = {"label": label, "status": "running"}
            job["items"].append(item)
            try:
                # generate_single_scene_job opens and closes its own session
                generate_single_scene_job(scene_id, quality)
                item["status"] = "done"
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
            done += 1
            job["progress"] = done

        job["status"] = "complete"

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        try:
            db.close()
        except Exception:
            pass


# ── Bulk reference regeneration ───────────────────────────────────────────────

def get_ref_regen_job(job_id: str) -> dict | None:
    return _ref_regen_jobs.get(job_id)


def start_regenerate_all_references(project_id: int) -> str:
    """
    Start a background thread that regenerates all character portraits and
    location reference images for the project.

    Returns a job_id that callers can poll via get_ref_regen_job().
    """
    job_id = str(uuid.uuid4())
    _ref_regen_jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "items": [],
        "error": None,
    }
    thread = threading.Thread(
        target=_regenerate_all_references_bg,
        args=(project_id, job_id),
        daemon=True,
    )
    thread.start()
    return job_id


def _regenerate_all_references_bg(project_id: int, job_id: str) -> None:
    """
    Background worker for bulk reference regeneration.

    For each character and location:
      1. Generates 3 FLUX candidates (using updated style-first prompts).
      2. Auto-canonicalises the first candidate to char_{id}.png / loc_{id}.png
         so get_scene_seed_image() picks it up immediately on the next production run.

    Users can still visit Portrait Studio / Location Studio afterwards to pick a
    different candidate as their preferred canonical.
    """
    from models import Project

    db = SessionLocal()
    job = _ref_regen_jobs[job_id]

    try:
        project = db.get(Project, project_id)
        if project is None:
            job["status"] = "error"
            job["error"] = "Project not found"
            return

        series_slug = project.series_slug
        ref_dir = settings.SERIES_DIR / series_slug / "reference_images"
        ref_dir.mkdir(parents=True, exist_ok=True)

        chars = list(project.characters)
        locs = list(project.locations)
        job["total"] = len(chars) + len(locs)
        done = 0

        # ── Characters ────────────────────────────────────────────────────────
        for char in chars:
            item: dict = {"label": f"Portrait — {char.name}", "status": "running"}
            job["items"].append(item)
            try:
                saved_paths = generate_character_portrait(char.id, db)
                if saved_paths:
                    # Auto-canonicalise: copy first candidate to char_{id}.png
                    src = settings.SERIES_DIR / saved_paths[0]
                    canonical = ref_dir / f"char_{char.id}.png"
                    if src.exists():
                        shutil.copy2(src, canonical)
                    item["status"] = "done"
                else:
                    item["status"] = "error"
                    item["error"] = "No candidates generated"
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
            done += 1
            job["progress"] = done

        # ── Locations ─────────────────────────────────────────────────────────
        for loc in locs:
            item = {"label": f"Location — {loc.name}", "status": "running"}
            job["items"].append(item)
            try:
                saved_paths = generate_location_reference(loc.id, db)
                if saved_paths:
                    # Auto-canonicalise: copy first candidate to loc_{id}.png
                    src = settings.SERIES_DIR / saved_paths[0]
                    canonical = ref_dir / f"loc_{loc.id}.png"
                    if src.exists():
                        shutil.copy2(src, canonical)
                    item["status"] = "done"
                else:
                    item["status"] = "error"
                    item["error"] = "No candidates generated"
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
            done += 1
            job["progress"] = done

        job["status"] = "complete"

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        db.close()
