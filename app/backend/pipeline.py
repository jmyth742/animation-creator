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
# NOTE: showrunner.py lives outside app/backend/ so uvicorn's --reload does not
# watch it.  Any change to showrunner.py must be accompanied by a trivial touch
# of this file to force a reload, or the backend will use stale bytecode.

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
            "lora_path": char.lora_path,
            "lora_strength": char.lora_strength if char.lora_strength is not None else 0.7,
            "trigger_word": char.trigger_word,
        }

    # ── Build locations dict ──────────────────────────────────────────────────
    locations_dict: dict[str, str] = {}
    locations_meta: dict[str, dict] = {}
    for loc in project.locations:
        locations_dict[f"loc_{loc.id}"] = loc.description
        locations_meta[f"loc_{loc.id}"] = {
            "name": loc.name,
            "description": loc.description,
            "lora_path": loc.lora_path,
            "lora_strength": loc.lora_strength if loc.lora_strength is not None else 0.5,
            "trigger_word": loc.trigger_word,
        }

    # ── Write bible.json ──────────────────────────────────────────────────────
    bible: dict = {
        "series": {
            "title": project.title,
            "style": project.visual_style,
            "tone": project.tone,
            "format": {"resolution": [480, 320], "fps": 24},
        },
        "characters": characters_dict,
        "locations_meta": locations_meta,
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


# ── Background export (auto-sync on save) ────────────────────────────────────

def export_project_in_background(project_id: int) -> None:
    """Fire-and-forget export so DB → JSON files stay in sync after every save."""
    def _run():
        db = SessionLocal()
        try:
            export_project_to_files(project_id, db)
        except Exception:
            pass  # Best-effort; next production run will export anyway
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()


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
    force: bool = False,
    denoise: float = showrunner.DEFAULT_DENOISE,
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
            resume=not force,
            no_audio=False,
            no_crossfade=False,
            no_grade=False,
            no_subs=False,
            no_ambience=False,
            no_music=False,
            flagged_only=False,
            enhance=True,
            denoise=denoise,
        )

        log_buf = io.StringIO()
        error_msg: str | None = None

        # Run showrunner in the same thread, capturing its stdout output.
        # We update progress_pct by counting clips that appear in COMFYUI_OUTPUT.
        ep_prefix = f"ep{episode.number:02d}"

        # Event to signal cancellation from progress thread to main thread
        cancel_event = threading.Event()

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
                        # Check if job was cancelled
                        if j.status == "cancelled" or j.cancelled_at is not None:
                            cancel_event.set()
                            # Interrupt ComfyUI
                            try:
                                import requests as _requests
                                _requests.post("http://localhost:8188/interrupt", timeout=3)
                            except Exception:
                                pass
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

        # If cancelled, leave the cancelled status and don't overwrite
        if cancel_event.is_set() or job.status == "cancelled":
            job.log_text = log_buf.getvalue() + "\n\n[CANCELLED] Job cancelled by user."
            if not job.completed_at:
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            job.status = "cancelled"
            db.commit()
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

def _archive_existing_clip(
    scene, project, prompt: str, quality: str, seed_image: str | None, db,
    *, negative_prompt: str = "", model_name: str = "", mode: str = "",
    steps: int = 0, denoise: float = 0.0, loras: list[tuple[str, float]] | None = None,
) -> None:
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
        negative_prompt=negative_prompt or None,
        seed_image=seed_image,
        model_name=model_name or None,
        mode=mode or None,
        steps=steps or None,
        denoise=denoise or None,
        loras=json.dumps(loras) if loras else None,
    )
    db.add(version)
    db.commit()


# ── Single-scene regeneration ─────────────────────────────────────────────────

def generate_single_scene_job(scene_id: int, quality: str = "draft", denoise: float = showrunner.DEFAULT_DENOISE) -> None:
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

        base_prompt = showrunner.build_scene_prompt(scene_dict, bible)

        # Enhance the prompt with Claude (same as full episode produce)
        try:
            prompt = showrunner.enhance_scene_prompt(scene_dict, bible, base_prompt)
        except Exception:
            prompt = base_prompt

        neg = showrunner.build_negative_prompt(scene_dict)

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

        cl = showrunner.CLIP_LENGTHS.get(scene.clip_length, showrunner.CLIP_LENGTHS["medium"])
        frames = cl["frames"]
        steps = showrunner.QUALITY_STEPS.get(quality, 20)
        clip_prefix = scene_dict["id"]
        import random
        seed = random.randint(1, 999999)

        # Collect all LoRAs for this scene (up to 2 chars + 1 location)
        scene_loras = showrunner.get_scene_loras(scene_dict, bible)

        gen_mode = "i2v" if seed_image else "t2v"
        model_name = (showrunner.build_i2v_workflow.__defaults__ if seed_image
                       else showrunner.build_t2v_workflow.__defaults__)
        # Get actual model name from workflow
        if seed_image:
            model_name = "hunyuanvideo1.5_480p_i2v_cfg_distilled-Q5_K_S.gguf"
        else:
            model_name = "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf"

        # Archive the current clip (if any) before overwriting it
        _archive_existing_clip(
            scene, project, prompt, quality, seed_image, db,
            negative_prompt=neg, model_name=model_name, mode=gen_mode,
            steps=steps, denoise=denoise if seed_image else 1.0,
            loras=scene_loras,
        )

        if seed_image:
            wf = showrunner.build_i2v_workflow(
                prompt, seed_image, seed, clip_prefix, frames, steps=steps, denoise=denoise,
                negative_prompt=neg, loras=scene_loras,
            )
        else:
            wf = showrunner.build_t2v_workflow(prompt, seed, clip_prefix, frames, steps=steps,
                negative_prompt=neg, loras=scene_loras,
            )

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

        # Keep on-disk JSON in sync with DB after clip path update
        try:
            export_project_in_background(episode.project_id)
        except Exception:
            pass

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

def generate_character_portrait(character_id: int, db, engine: str = "flux") -> list[str]:
    """
    Generate 3 portrait candidates for a character (different seeds).

    engine:
      "flux"    — FLUX.1-schnell T2I (fast, high quality stills)
      "hunyuan" — HunyuanVideo 1.5 single-frame T2V (matches video model style)

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

        # Generate portrait using selected engine
        if engine == "hunyuan":
            wf = showrunner.build_ref_workflow(prompt, seed=seed, prefix=candidate_label, width=480, height=640, steps=30)
        else:
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

def generate_location_reference(location_id: int, db, engine: str = "flux") -> list[str]:
    """
    Generate 3 reference image candidates for a location (different seeds).

    engine:
      "flux"    — FLUX.1-schnell T2I (fast, high quality stills)
      "hunyuan" — HunyuanVideo 1.5 single-frame T2V (matches video model style)

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

        # Generate location reference using selected engine
        if engine == "hunyuan":
            wf = showrunner.build_ref_workflow(prompt, seed=seed, prefix=candidate_label, width=480, height=320, steps=30)
        else:
            wf = showrunner.build_t2i_workflow(prompt, seed=seed, prefix=candidate_label, width=480, height=320)

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

        # 480×320 landscape — matches video output resolution exactly
        wf = showrunner.build_t2i_workflow(prompt, seed=seed, prefix=candidate_label, width=480, height=320)

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

# ── Background training job ──────────────────────────────────────────────────

def run_training_job(job_id: int) -> None:
    """
    Intended to run in a background threading.Thread.

    Lifecycle
    ---------
    1. Acquires its own DB session.
    2. Updates status through stages: provisioning -> bootstrapping -> uploading
       -> training -> downloading -> complete.
    3. Uses TrainingOrchestrator from runpod.training_orchestrator.
    4. On completion, copies LoRA to ComfyUI/models/loras/ and updates job + character.
    5. On error, sets job.status = "error" and logs the error.
    6. Checks for cancellation (job.cancelled_at) between stages.
    """
    from models import Character, Location, TrainingJob

    db = SessionLocal()

    def _log(job: TrainingJob, msg: str) -> None:
        job.log_text = (job.log_text or "") + msg + "\n"
        db.commit()

    def _check_cancelled(job: TrainingJob) -> bool:
        db.refresh(job)
        return job.cancelled_at is not None or job.status == "cancelled"

    def _set_stage(job: TrainingJob, stage: str, pct: int) -> None:
        job.status = stage
        job.progress_pct = pct
        _log(job, f"[{stage.upper()}] Stage started (progress: {pct}%)")

    try:
        job = db.get(TrainingJob, job_id)
        if job is None:
            return

        # ── Stage 1: Provisioning ────────────────────────────────────────────
        _set_stage(job, "provisioning", 5)

        try:
            sys.path.insert(0, str(Path("/workspace/text-to-video/runpod")))
            from training_orchestrator import TrainingOrchestrator
        except ImportError:
            _log(job, "[ERROR] training_orchestrator module not found. "
                 "Ensure runpod/training_orchestrator.py exists.")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        orchestrator = TrainingOrchestrator()

        if _check_cancelled(job):
            return

        # Provision the pod
        _log(job, f"Requesting {job.gpu_type} pod...")
        try:
            pod_id, ssh_host, ssh_port = orchestrator.create_training_pod(
                gpu_type=job.gpu_type,
            )
            job.pod_id = pod_id
            job.pod_ssh_host = ssh_host
            job.pod_ssh_port = ssh_port
            # Update GPU type in case orchestrator fell back to a different one
            job.gpu_type = orchestrator._pods.get(pod_id, type('', (), {'gpu_type': job.gpu_type})()).gpu_type or job.gpu_type
            db.commit()
            _log(job, f"Pod created: {pod_id} (GPU: {job.gpu_type}, SSH: {ssh_host}:{ssh_port})")
        except Exception as exc:
            _log(job, f"[ERROR] Failed to provision pod: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        # Wait for pod to be ready
        try:
            orchestrator.wait_for_pod_ready(job.pod_id)
            _log(job, "Pod is running and SSH accessible.")
        except Exception as exc:
            _log(job, f"[ERROR] Pod failed to start: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        if _check_cancelled(job):
            orchestrator.stop_pod(job.pod_id)
            return

        # ── Stage 2: Bootstrapping ───────────────────────────────────────────
        _set_stage(job, "bootstrapping", 15)

        try:
            orchestrator.bootstrap_training_env(job.pod_ssh_host, job.pod_ssh_port)
            _log(job, "Pod bootstrapped successfully.")
        except Exception as exc:
            _log(job, f"[ERROR] Failed to bootstrap pod: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        if _check_cancelled(job):
            orchestrator.stop_pod(job.pod_id)
            return

        # ── Stage 3: Uploading ───────────────────────────────────────────────
        _set_stage(job, "uploading", 25)

        if not job.dataset_path:
            _log(job, "[ERROR] No dataset path set. Upload a dataset first.")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        try:
            remote_dataset_path = orchestrator.upload_dataset(
                job.pod_ssh_host, job.pod_ssh_port, job.dataset_path,
            )
            _log(job, f"Dataset uploaded from {job.dataset_path}")
        except Exception as exc:
            _log(job, f"[ERROR] Failed to upload dataset: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        if _check_cancelled(job):
            orchestrator.stop_pod(job.pod_id)
            return

        # ── Stage 4: Training ────────────────────────────────────────────────
        _set_stage(job, "training", 35)

        char_slug = (job.character_name or "unknown").lower().replace(" ", "_")

        try:
            training_config = {
                "dataset_path": remote_dataset_path,
                "character_name": char_slug,
                "rank": job.rank,
                "alpha": job.rank,
                "lr": job.learning_rate,
                "epochs": job.epochs,
                "blocks_to_swap": orchestrator.TRAINING_COMPATIBLE_GPUS.get(job.gpu_type, 32),
            }
            session_name = orchestrator.start_training(
                job.pod_ssh_host, job.pod_ssh_port, training_config,
            )
            _log(job, f"Training started in screen session: {session_name}")
        except Exception as exc:
            _log(job, f"[ERROR] Failed to start training: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        # Poll training progress
        import time as _time
        while True:
            if _check_cancelled(job):
                orchestrator.stop_pod(job.pod_id)
                return

            try:
                status = orchestrator.check_training_status(
                    job.pod_ssh_host, job.pod_ssh_port, session_name,
                )
                if status.epoch > 0 and job.epochs > 0:
                    pct = 35 + int((status.epoch / job.epochs) * 50)
                    job.progress_pct = min(pct, 85)
                if status.loss is not None:
                    job.training_loss = status.loss
                if status.log_tail:
                    # Append last few lines of log
                    last_lines = "\n".join(status.log_tail.splitlines()[-5:])
                    _log(job, last_lines)
                if not status.running:
                    _log(job, "Training process finished.")
                    break
            except Exception:
                pass

            _time.sleep(30)

        if _check_cancelled(job):
            orchestrator.stop_pod(job.pod_id)
            return

        # ── Stage 5: Downloading ─────────────────────────────────────────────
        _set_stage(job, "downloading", 85)

        loras_dir = settings.COMFYUI_DIR / "models" / "loras"
        loras_dir.mkdir(parents=True, exist_ok=True)

        lora_filename = f"{char_slug}-comfyui.safetensors"
        remote_lora_path = f"/workspace/lora_outputs/{char_slug}/{lora_filename}"

        try:
            orchestrator.download_lora(
                job.pod_ssh_host, job.pod_ssh_port,
                remote_lora_path, str(loras_dir),
            )
            _log(job, f"LoRA downloaded to {loras_dir / lora_filename}")
        except Exception as exc:
            _log(job, f"[ERROR] Failed to download LoRA: {exc}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            orchestrator.stop_pod(job.pod_id)
            return

        # ── Stage 6: Complete ────────────────────────────────────────────────
        job.status = "complete"
        job.progress_pct = 100
        job.lora_path = lora_filename
        job.completed_at = datetime.datetime.now(datetime.timezone.utc)
        _log(job, f"[COMPLETE] LoRA saved as {lora_filename}")

        # Update the linked character or location with the trained LoRA
        if job.character_id:
            char = db.get(Character, job.character_id)
            if char:
                char.lora_path = lora_filename
                char.lora_strength = job.lora_strength
                char.trigger_word = job.trigger_word
                _log(job, f"Updated character '{char.name}' with LoRA {lora_filename} (trigger: {job.trigger_word})")
        elif job.location_id:
            loc = db.get(Location, job.location_id)
            if loc:
                loc.lora_path = lora_filename
                loc.lora_strength = job.lora_strength
                loc.trigger_word = job.trigger_word
                _log(job, f"Updated location '{loc.name}' with LoRA {lora_filename} (trigger: {job.trigger_word})")

        db.commit()

        # Stop the pod now that we're done
        try:
            orchestrator.stop_pod(job.pod_id)
            _log(job, "RunPod pod stopped.")
        except Exception:
            pass  # Best-effort cleanup

    except Exception as exc:
        try:
            job = db.get(TrainingJob, job_id)
            if job:
                job.status = "error"
                job.log_text = (job.log_text or "") + f"\n\n[FATAL] {exc}"
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Local training job (runs on this pod) ────────────────────────────────────

MUSUBI_DIR = Path("/workspace/musubi-tuner")
TRAINING_MODELS_DIR = Path("/workspace/training_models")
DIT_MODEL_PATH = TRAINING_MODELS_DIR / "split_files" / "diffusion_models" / "hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors"


def _stop_comfyui() -> int | None:
    """Stop ComfyUI to free VRAM. Returns the PID if it was running."""
    import subprocess
    result = subprocess.run(
        ["pgrep", "-f", "main.py.*8188"], capture_output=True, text=True,
    )
    comfy_pid = None
    if result.stdout.strip():
        comfy_pid = int(result.stdout.strip().splitlines()[0])
        subprocess.run(["kill", str(comfy_pid)], capture_output=True)

    # Also kill any stale training processes hogging VRAM
    for pattern in ["hv_1_5_train_network", "accelerate.*train", "compile_worker"]:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True)

    import time as _t
    _t.sleep(3)
    return comfy_pid


def _start_comfyui() -> None:
    """Restart ComfyUI in background."""
    import subprocess
    subprocess.Popen(
        ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"],
        cwd="/workspace/text-to-video/ComfyUI",
        stdout=open("/tmp/comfyui.log", "a"),
        stderr=subprocess.STDOUT,
    )


def run_local_training_job(job_id: int) -> None:
    """
    Run LoRA training directly on this pod using musubi-tuner.
    No remote provisioning needed — everything runs locally.
    Auto-stops ComfyUI to free VRAM, restarts it when done.
    """
    import subprocess
    from models import Character, Location, TrainingJob

    db = SessionLocal()

    def _log(job, msg):
        job.log_text = (job.log_text or "") + msg + "\n"
        db.commit()

    def _check_cancelled(job):
        db.refresh(job)
        return job.cancelled_at is not None or job.status == "cancelled"

    def _set_stage(job, stage, pct):
        job.status = stage
        job.progress_pct = pct
        _log(job, f"[{stage.upper()}] {pct}%")

    try:
        job = db.get(TrainingJob, job_id)
        if job is None:
            return

        # ── Stop ComfyUI to free VRAM ────────────────────────────────────
        comfyui_was_running = _stop_comfyui()
        if comfyui_was_running:
            _log(job, "Stopped ComfyUI to free VRAM.")

        # ── Stage 1: Setup (install deps + download model) ───────────────
        _set_stage(job, "bootstrapping", 5)
        _log(job, "Setting up local training environment...")

        # Install musubi-tuner if needed
        if not MUSUBI_DIR.exists():
            _log(job, "Cloning musubi-tuner...")
            subprocess.run(
                ["git", "clone", "https://github.com/kohya-ss/musubi-tuner", str(MUSUBI_DIR)],
                check=True, capture_output=True, text=True,
            )

        # Install Python deps
        _log(job, "Installing training dependencies...")
        subprocess.run(
            ["pip", "install", "-q", "-e", str(MUSUBI_DIR)],
            check=True, capture_output=True, text=True, timeout=300,
        )
        subprocess.run(
            ["pip", "install", "-q", "accelerate", "bitsandbytes", "prodigyopt"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        _log(job, "Dependencies installed.")

        if _check_cancelled(job):
            return

        # Download full-precision DiT model if needed (~16.7GB)
        _set_stage(job, "bootstrapping", 15)
        if not DIT_MODEL_PATH.exists():
            _log(job, "Downloading full-precision DiT model (~16.7GB)...")
            TRAINING_MODELS_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["python3", "-c", (
                    "from huggingface_hub import hf_hub_download; "
                    "hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged', "
                    "filename='split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors', "
                    f"local_dir='{TRAINING_MODELS_DIR}/')"
                )],
                check=True, capture_output=True, text=True, timeout=1800,
            )
            _log(job, "DiT model downloaded.")
        else:
            _log(job, "DiT model already present.")

        if _check_cancelled(job):
            return

        # ── Stage 2: Validate dataset ────────────────────────────────────
        _set_stage(job, "uploading", 25)

        if not job.dataset_path or not Path(job.dataset_path).exists():
            _log(job, "[ERROR] No dataset found. Generate or upload a dataset first.")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        dataset_dir = Path(job.dataset_path)
        img_count = len(list(dataset_dir.glob("*.png"))) + len(list(dataset_dir.glob("*.jpg")))
        _log(job, f"Dataset: {dataset_dir} ({img_count} images)")

        if img_count == 0:
            _log(job, "[ERROR] Dataset has no images.")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        # ── Stage 3: Cache latents + text encoder outputs ────────────────
        _set_stage(job, "training", 30)

        char_slug = (job.character_name or "unknown").lower().replace(" ", "_")
        cache_dir = Path(f"/workspace/lora_cache/{char_slug}")
        output_dir = Path(f"/workspace/lora_outputs/{char_slug}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        vae_path = settings.COMFYUI_DIR / "models" / "vae" / "hunyuanvideo15_vae_fp16.safetensors"
        # Training needs the full-precision Qwen model, not the fp8 version
        te_dir = settings.COMFYUI_DIR / "models" / "text_encoders"
        te_path_fp16 = te_dir / "qwen_2.5_vl_7b.safetensors"
        if not te_path_fp16.exists():
            _log(job, "Downloading full-precision Qwen2.5-VL text encoder (~15GB)...")
            subprocess.run(
                ["python3", "-c", (
                    "from huggingface_hub import hf_hub_download; import shutil; "
                    f"p = hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged', "
                    f"filename='split_files/text_encoders/qwen_2.5_vl_7b.safetensors'); "
                    f"shutil.copy2(p, '{te_path_fp16}')"
                )],
                check=True, capture_output=True, text=True, timeout=1800,
            )
            _log(job, "Qwen2.5-VL text encoder downloaded.")
        te_path = te_path_fp16
        byt5_path = settings.COMFYUI_DIR / "models" / "text_encoders" / "byt5_small_glyphxl_fp16.safetensors"

        # Write dataset config TOML
        config_path = cache_dir / "config.toml"
        config_path.write_text(
            f'[general]\nresolution = [480, 320]\ncaption_extension = ".txt"\n'
            f'batch_size = 1\nenable_bucket = true\n\n'
            f'[[datasets]]\nimage_directory = "{dataset_dir}"\n'
            f'cache_directory = "{cache_dir / "latents"}"\nnum_repeats = 1\n'
        )

        _log(job, "Caching latents...")
        result = subprocess.run(
            ["python3", "hv_1_5_cache_latents.py",
             "--dataset_config", str(config_path),
             "--vae", str(vae_path)],
            cwd=str(MUSUBI_DIR), capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            _log(job, f"[ERROR] Latent caching failed:\n{result.stderr[-500:]}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        if _check_cancelled(job):
            return

        _set_stage(job, "training", 40)
        _log(job, "Caching text encoder outputs...")
        te_cache_cmd = [
            "python3", "hv_1_5_cache_text_encoder_outputs.py",
            "--dataset_config", str(config_path),
            "--text_encoder", str(te_path),
            "--byt5", str(byt5_path),
            "--batch_size", "16",
        ]
        # Only use --fp8_vl flag with the fp8 quantized model
        if "fp8" in te_path.name:
            te_cache_cmd.append("--fp8_vl")
        result = subprocess.run(
            te_cache_cmd,
            cwd=str(MUSUBI_DIR), capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            _log(job, f"[ERROR] Text encoder caching failed:\n{result.stderr[-500:]}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        if _check_cancelled(job):
            return

        # ── Stage 4: Train ───────────────────────────────────────────────
        _set_stage(job, "training", 50)
        _log(job, f"Starting LoRA training (rank={job.rank}, epochs={job.epochs}, lr={job.learning_rate})...")

        train_cmd = [
            "accelerate", "launch",
            "--num_cpu_threads_per_process", "1",
            "--mixed_precision", "bf16",
            "hv_1_5_train_network.py",
            "--dit", str(DIT_MODEL_PATH),
            "--dataset_config", str(config_path),
            "--network_module", "networks.lora_hv_1_5",
            "--network_dim", str(job.rank),
            "--network_alpha", str(job.rank),
            "--learning_rate", job.learning_rate,
            "--optimizer_type", "adamw8bit",
            "--mixed_precision", "bf16",
            "--max_train_epochs", str(job.epochs),
            "--save_every_n_epochs", "25",
            "--gradient_checkpointing",
            "--blocks_to_swap", "32",
            "--img_in_txt_in_offloading",
            "--timestep_sampling", "shift",
            "--discrete_flow_shift", "2.0",
            "--weighting_scheme", "none",
            "--sdpa", "--split_attn",
            "--output_dir", str(output_dir),
            "--output_name", char_slug,
        ]

        # Run training — stream output to log
        process = subprocess.Popen(
            train_cmd, cwd=str(MUSUBI_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        import re as _re
        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue
            # Parse epoch progress
            epoch_match = _re.search(r'epoch\s+(\d+)/(\d+)', line, _re.IGNORECASE)
            step_match = _re.search(r'(\d+)%\|', line)
            loss_match = _re.search(r'loss[=:]\s*([\d.]+)', line)

            if epoch_match:
                current_epoch = int(epoch_match.group(1))
                pct = 50 + int((current_epoch / max(job.epochs, 1)) * 40)
                job.progress_pct = min(pct, 90)
            if loss_match:
                job.training_loss = float(loss_match.group(1))

            # Log every meaningful line (not progress bars)
            if epoch_match or loss_match or 'saving' in line.lower() or 'error' in line.lower():
                _log(job, line)
            elif not step_match:
                # Log non-progress-bar lines
                _log(job, line)

            # Check cancellation periodically
            if _check_cancelled(job):
                process.kill()
                return

        process.wait()
        if process.returncode != 0:
            _log(job, f"[ERROR] Training exited with code {process.returncode}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        if _check_cancelled(job):
            return

        # ── Stage 5: Convert for ComfyUI ─────────────────────────────────
        _set_stage(job, "downloading", 92)
        _log(job, "Converting LoRA for ComfyUI...")

        # Find latest checkpoint
        checkpoints = sorted(output_dir.glob(f"{char_slug}*.safetensors"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not checkpoints:
            _log(job, "[ERROR] No checkpoint found after training.")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        latest_ckpt = checkpoints[0]
        converted_name = f"{char_slug}-comfyui.safetensors"
        converted_path = output_dir / converted_name

        result = subprocess.run(
            ["python3", "convert_lora.py",
             "--input", str(latest_ckpt),
             "--output", str(converted_path),
             "--target", "other"],
            cwd=str(MUSUBI_DIR), capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            _log(job, f"[ERROR] LoRA conversion failed:\n{result.stderr[-500:]}")
            job.status = "error"
            job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return

        # Copy to ComfyUI loras dir
        loras_dir = settings.COMFYUI_DIR / "models" / "loras"
        loras_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(converted_path, loras_dir / converted_name)

        # ── Stage 6: Complete ────────────────────────────────────────────
        lora_filename = converted_name
        job.status = "complete"
        job.progress_pct = 100
        job.lora_path = lora_filename
        job.completed_at = datetime.datetime.now(datetime.timezone.utc)
        _log(job, f"[COMPLETE] LoRA saved as {lora_filename}")

        if job.character_id:
            char = db.get(Character, job.character_id)
            if char:
                char.lora_path = lora_filename
                char.lora_strength = job.lora_strength
                char.trigger_word = job.trigger_word
                _log(job, f"Updated character '{char.name}' with LoRA {lora_filename} (trigger: {job.trigger_word})")
        elif job.location_id:
            loc = db.get(Location, job.location_id)
            if loc:
                loc.lora_path = lora_filename
                loc.lora_strength = job.lora_strength
                loc.trigger_word = job.trigger_word
                _log(job, f"Updated location '{loc.name}' with LoRA {lora_filename} (trigger: {job.trigger_word})")

        db.commit()

    except Exception as exc:
        try:
            job = db.get(TrainingJob, job_id)
            if job:
                job.status = "error"
                job.log_text = (job.log_text or "") + f"\n\n[FATAL] {exc}"
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        # Always restart ComfyUI
        _start_comfyui()
        db.close()


def _update_training_progress(db, job_id: int, pct: int, msg: str) -> None:
    """Callback for the training orchestrator to report progress."""
    from models import TrainingJob

    try:
        job = db.get(TrainingJob, job_id)
        if job and job.status == "training":
            # Map training progress (0-100) to our range (35-85)
            job.progress_pct = 35 + int(pct * 0.5)
            job.log_text = (job.log_text or "") + msg + "\n"
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def get_ref_regen_job(job_id: str) -> dict | None:
    return _ref_regen_jobs.get(job_id)


def start_regenerate_all_references(project_id: int, engine: str = "flux") -> str:
    """
    Start a background thread that regenerates all character portraits and
    location reference images for the project.

    engine: "flux" (default) or "hunyuan" (matches video model style).

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
        args=(project_id, job_id, engine),
        daemon=True,
    )
    thread.start()
    return job_id


def _regenerate_all_references_bg(project_id: int, job_id: str, engine: str = "flux") -> None:
    """
    Background worker for bulk reference regeneration.

    For each character and location:
      1. Generates 3 candidates (FLUX T2I or HunyuanVideo single-frame).
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
                saved_paths = generate_character_portrait(char.id, db, engine=engine)
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
                saved_paths = generate_location_reference(loc.id, db, engine=engine)
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


# ── Training dataset generation (FLUX T2I) ──────────────────────────────────

# Variation templates for character dataset generation.
# Each entry is (prompt_suffix, width, height, seed_offset).
CHARACTER_DATASET_VARIATIONS: list[dict] = [
    # Portraits — different expressions
    {"desc": "facing camera, neutral expression, upper body visible", "w": 480, "h": 640},
    {"desc": "facing camera, smiling warmly, upper body visible", "w": 480, "h": 640},
    {"desc": "facing camera, serious expression, intense gaze, upper body visible", "w": 480, "h": 640},
    {"desc": "facing camera, surprised expression, eyes wide, upper body visible", "w": 480, "h": 640},
    {"desc": "facing camera, speaking, mouth slightly open, upper body visible", "w": 480, "h": 640},
    {"desc": "looking to the side, profile view, contemplative expression", "w": 480, "h": 640},
    # Angles
    {"desc": "three-quarter view, looking slightly away from camera, upper body", "w": 480, "h": 640},
    {"desc": "side profile, dramatic lighting, sharp shadows", "w": 480, "h": 640},
    {"desc": "looking over shoulder, back partially visible, turning to camera", "w": 480, "h": 640},
    {"desc": "low angle shot, looking down at camera, imposing pose", "w": 480, "h": 640},
    # Full body
    {"desc": "full body standing pose, arms at sides, facing camera", "w": 480, "h": 640},
    {"desc": "full body walking pose, mid-stride, slight motion", "w": 480, "h": 640},
    {"desc": "sitting in a chair, relaxed pose, upper body and legs visible", "w": 640, "h": 480},
    # Different settings / lighting
    {"desc": "facing camera, warm indoor lighting, cozy atmosphere, upper body", "w": 480, "h": 640},
    {"desc": "facing camera, outdoor natural sunlight, bright clear day, upper body", "w": 480, "h": 640},
    {"desc": "facing camera, moody dramatic lighting, dark background, upper body", "w": 480, "h": 640},
    {"desc": "facing camera, soft golden hour light, gentle backlight, upper body", "w": 480, "h": 640},
    {"desc": "facing camera, cool blue-tinted night lighting, upper body", "w": 480, "h": 640},
    # Action / gesture
    {"desc": "gesturing with hands while speaking, animated expression, medium shot", "w": 480, "h": 640},
    {"desc": "arms crossed, confident stance, looking at camera, medium shot", "w": 480, "h": 640},
    {"desc": "leaning forward, engaged expression, close-up portrait", "w": 480, "h": 640},
    {"desc": "looking upward, hopeful expression, soft lighting, portrait", "w": 480, "h": 640},
    # Close-ups
    {"desc": "extreme close-up face, eyes in sharp focus, detailed skin texture", "w": 640, "h": 480},
    {"desc": "close-up face and shoulders, soft bokeh background, portrait", "w": 480, "h": 640},
    {"desc": "medium close-up, hand near face, thoughtful pose", "w": 480, "h": 640},
]

LOCATION_DATASET_VARIATIONS: list[dict] = [
    {"desc": "wide establishing shot, full environment visible", "w": 640, "h": 360},
    {"desc": "medium shot, showing key details and atmosphere", "w": 640, "h": 360},
    {"desc": "close-up detail shot, textures and materials visible", "w": 640, "h": 360},
    {"desc": "low angle perspective, dramatic composition", "w": 640, "h": 360},
    {"desc": "high angle overview, bird's eye view", "w": 640, "h": 360},
    {"desc": "warm daytime lighting, bright and inviting", "w": 640, "h": 360},
    {"desc": "cool night lighting, moody shadows, atmospheric", "w": 640, "h": 360},
    {"desc": "golden hour, long shadows, warm amber tones", "w": 640, "h": 360},
    {"desc": "overcast diffused lighting, soft even tones", "w": 640, "h": 360},
    {"desc": "rainy atmosphere, wet surfaces, reflections", "w": 640, "h": 360},
    {"desc": "panoramic wide view, environment stretching to horizon", "w": 640, "h": 360},
    {"desc": "intimate corner detail, shallow depth of field", "w": 640, "h": 360},
]

# In-memory dataset generation job registry
_dataset_gen_jobs: dict[str, dict] = {}


def get_dataset_gen_job(job_id: str) -> dict | None:
    return _dataset_gen_jobs.get(job_id)


def start_generate_dataset(
    project_id: int,
    training_job_id: int,
    character_id: int | None = None,
    location_id: int | None = None,
    trigger_word: str = "ohwx person",
    num_images: int = 25,
) -> str:
    """
    Start a background thread that generates a LoRA training dataset using FLUX T2I.

    For characters: generates varied portraits/poses of the character.
    For locations: generates varied angles/lighting of the location.
    Auto-captions each image with the trigger word + description.

    Returns a job_id that can be polled via get_dataset_gen_job().
    """
    job_id = str(uuid.uuid4())
    _dataset_gen_jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "total": num_images,
        "generated": 0,
        "dataset_path": None,
        "error": None,
    }
    thread = threading.Thread(
        target=_generate_dataset_bg,
        args=(project_id, training_job_id, character_id, location_id,
              trigger_word, num_images, job_id),
        daemon=True,
    )
    thread.start()
    return job_id


def _generate_dataset_bg(
    project_id: int,
    training_job_id: int,
    character_id: int | None,
    location_id: int | None,
    trigger_word: str,
    num_images: int,
    job_id: str,
) -> None:
    """Background worker that generates training dataset images via FLUX T2I."""
    import requests as _requests
    from models import Character, Location, Project, TrainingJob

    db = SessionLocal()
    job = _dataset_gen_jobs[job_id]

    try:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")

        # Build base prompt from project style
        style_parts: list[str] = []
        if project.visual_style:
            style_parts.append(project.visual_style)
        if project.setting:
            style_parts.append(project.setting)
        if project.tone:
            style_parts.append(project.tone)
        style_parts.append("cinematic video frame")
        style_prefix = ", ".join(filter(None, style_parts))

        # Determine subject and variations
        if character_id:
            char = db.get(Character, character_id)
            if char is None:
                raise ValueError(f"Character {character_id} not found")
            subject_desc = char.visual_description or char.name
            subject_name = (char.name or "character").lower().replace(" ", "_")
            variations = CHARACTER_DATASET_VARIATIONS
        elif location_id:
            loc = db.get(Location, location_id)
            if loc is None:
                raise ValueError(f"Location {location_id} not found")
            subject_desc = loc.description or loc.name
            subject_name = (loc.name or "location").lower().replace(" ", "_")
            trigger_word = "sksstyle"  # Use style trigger for locations
            variations = LOCATION_DATASET_VARIATIONS
        else:
            raise ValueError("Must provide either character_id or location_id")

        # Create dataset directory
        dataset_dir = Path("/workspace/datasets") / subject_name
        dataset_dir.mkdir(parents=True, exist_ok=True)

        # Cap to available variations, cycling if needed
        comfy_refs_out = settings.COMFYUI_DIR / "output" / "refs"
        generated = 0
        base_seed = 42

        for i in range(num_images):
            variation = variations[i % len(variations)]
            seed = base_seed + i * 7  # Spread seeds for variety

            # Build prompt: style + subject + variation
            if character_id:
                prompt = f"{style_prefix}, {subject_desc}, {variation['desc']}"
            else:
                prompt = f"{style_prefix}, {subject_desc}, {variation['desc']}"

            prefix = f"dataset_{subject_name}_{i:03d}"
            width = variation["w"]
            height = variation["h"]

            try:
                wf = showrunner.build_t2i_workflow(
                    prompt, seed=seed, prefix=prefix,
                    width=width, height=height,
                )
                prompt_id = showrunner.queue_prompt(wf)
                success = showrunner.poll_until_done(prompt_id)

                if success:
                    # Find the generated image
                    candidates = (
                        sorted(
                            comfy_refs_out.glob(f"{prefix}*.png"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        if comfy_refs_out.exists()
                        else []
                    )
                    if candidates:
                        # Copy to dataset dir with sequential name
                        dest_name = f"{subject_name}_{i+1:03d}"
                        dest_img = dataset_dir / f"{dest_name}.png"
                        shutil.copy2(candidates[0], dest_img)

                        # Write auto-caption
                        caption = f"{trigger_word}, {subject_desc}, {variation['desc']}"
                        caption_file = dataset_dir / f"{dest_name}.txt"
                        caption_file.write_text(caption)

                        generated += 1
            except _requests.ConnectionError:
                job["error"] = "ComfyUI not reachable"
                break
            except Exception as exc:
                # Log but continue with other images
                print(f"  Dataset gen failed for {prefix}: {exc}")

            job["generated"] = generated
            job["progress"] = generated

        # Update dataset path on the training job
        training_job = db.get(TrainingJob, training_job_id)
        if training_job:
            training_job.dataset_path = str(dataset_dir)
            db.commit()

        job["status"] = "complete"
        job["dataset_path"] = str(dataset_dir)

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        db.close()
