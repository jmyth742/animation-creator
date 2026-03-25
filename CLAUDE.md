# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An end-to-end automated animated series production pipeline. Given a concept, it uses Claude to write episode scripts, ComfyUI (HunyuanVideo 1.5) to generate video clips, Edge-TTS for voiceover, and FFmpeg to stitch everything into finished MP4 episodes. A full-stack web UI (FastAPI + React) manages projects, characters, locations, and episodes — and is intentionally kept polished for screen recording/demo purposes.

**Current owner: personal use only.** The UI is a demo asset — preserve its look and feel when making changes.

---

## Running the System

Three services must all be running:

```bash
# Terminal 1: ComfyUI video generation server
conda activate hunyuan-comfy
bash scripts/launch.sh                  # → http://localhost:8188

# Terminal 2: FastAPI backend
cd app/backend
# Requires app/backend/.env with SECRET_KEY set (see .env.example)
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload               # → http://localhost:8000

# Terminal 3: React frontend dev server
cd app/frontend
npm run dev                             # → http://localhost:5173

# Build frontend for production
cd app/frontend && npm run build        # output → dist/
```

### First-time setup
```bash
cp app/backend/.env.example app/backend/.env
# Edit .env and set SECRET_KEY=$(openssl rand -hex 32)
```

### CLI Production Pipeline (standalone, no web UI)

```bash
python scripts/showrunner.py create my_series
python scripts/showrunner.py write my_series          # Claude generates bible + episodes
python scripts/showrunner.py write my_series --episode 5
python scripts/showrunner.py produce my_series --episode 1 --image ref.png
python scripts/showrunner.py produce my_series --episode 1 --resume
python scripts/showrunner.py produce-all my_series
python scripts/showrunner.py status my_series

# Quick single-clip test
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p_fast.json \
  -p "A cat on a windowsill, cinematic" -s 42
```

---

## Architecture

```
React UI (Vite/Tailwind)
    ↓  Axios + WebSocket (?token= for WS auth)
FastAPI Backend (app/backend/)
    ├── routers/           CRUD + scene regeneration + portrait selection
    ├── pipeline.py        DB↔showrunner bridge; scene + episode job runners
    ├── routers/generate.py  → Claude API for script generation
    └── SQLite (SQLAlchemy ORM)
         ↓
showrunner.py (scripts/)
    ├── ComfyUI API (localhost:8188)   T2V + I2V video generation
    ├── Edge-TTS                       Per-scene voiceover
    └── FFmpeg                         Clip stitching → final MP4
```

### Episode Production Data Flow

1. `POST /episodes/{id}/produce` → `pipeline.produce_episode_job()` in a `threading.Thread`
2. `export_project_to_files()` writes `series/{slug}/bible.json` + `episodes/ep*.json` from DB
3. `showrunner.cmd_produce()` runs: T2V first scene → I2V chaining for subsequent scenes
4. Edge-TTS + FFmpeg stitch audio and clips
5. `_backfill_scene_clips()` updates every `scene.output_clip_path` + `scene.status` in the DB after completion so previews appear in the UI
6. Progress streamed to UI via `GET /ws/{job_id}?token=<jwt>`
7. **Cancel**: `POST /jobs/{id}/cancel` sets `cancelled_at`, progress thread detects it, sends `/interrupt` to ComfyUI, job ends with status `"cancelled"`

### Auto-Export (DB → JSON sync)

Every create/update/delete on characters, locations, scenes, and episodes triggers `export_project_in_background()` — a fire-and-forget thread that writes `bible.json` + episode JSONs. This keeps the on-disk files in sync with the DB at all times, eliminating the previous dual source-of-truth issue where files could go stale between production runs.

### Single-Scene Regeneration Data Flow

1. `POST /scenes/{id}/regenerate?quality=draft` → `pipeline.generate_single_scene_job()` in a thread
2. Scene marked `status="generating"` immediately
3. Project exported, `build_scene_prompt()` + `get_scene_seed_image()` called from showrunner
4. T2V or I2V workflow submitted to ComfyUI; `scene.output_clip_path` + `scene.status` updated on completion
5. UI polls `GET /episodes/{id}` every 3s while any scene in the episode has `status="generating"`

### Character Consistency System

Characters have a **canonical portrait** that feeds directly into video generation:

1. **Generate**: `POST /characters/{id}/generate-portrait` → ComfyUI T2I → 3 candidates saved to `series/{slug}/reference_images/char_{id}_v{1,2,3}.png`
2. **Select**: `POST /characters/{id}/select-portrait` with `portrait_path` → copies chosen file to `series/{slug}/reference_images/char_{id}.png` (the path `showrunner.get_scene_seed_image()` looks for) + updates `character.reference_image_path` in DB
3. **Used**: `get_scene_seed_image()` in showrunner uses the canonical `char_{id}.png` as the I2V seed image for dialogue scenes and close-ups featuring that character — ensuring visual consistency across episodes

Character `visual_description` is injected into every scene prompt via `build_scene_prompt()` (brief form for dialogue, full form for wide/establishing shots).

---

## Key Source Files

| File | Role |
|------|------|
| `scripts/showrunner.py` | ~95KB orchestrator: Claude calls, ComfyUI workflows, FFmpeg, prompt building |
| `app/backend/pipeline.py` | `produce_episode_job`, `generate_single_scene_job`, `_backfill_scene_clips`, `export_project_to_files`, `generate_character_portrait` |
| `app/backend/models.py` | SQLAlchemy ORM: User, Project, Character, Location, Episode, Scene, GenerationJob |
| `app/backend/schemas.py` | Pydantic v2 schemas with field validation, password complexity, `SelectPortraitRequest` |
| `app/backend/routers/scenes.py` | Scene CRUD + `POST /scenes/{id}/regenerate` |
| `app/backend/routers/characters.py` | Character CRUD + portrait generation + `POST /characters/{id}/select-portrait` |
| `app/backend/routers/episodes.py` | Episode CRUD + `POST /episodes/{id}/produce` |
| `app/backend/routers/jobs.py` | Job status REST + WebSocket (`/ws/{job_id}?token=`) |
| `app/frontend/src/components/EpisodesTab.jsx` | Episode/scene list, per-scene regenerate button, inline preview player, 3s polling |
| `app/frontend/src/components/CharacterModal.jsx` | Character form + portrait generation + canonical portrait selection |
| `app/frontend/src/components/TheaterTab.jsx` | Episode viewer — lists finished episodes with inline video player |
| `app/frontend/src/components/CharacterCard.jsx` | Character card with canonical portrait star badge |
| `app/backend/templates.py` | Pre-seeded project templates (noir-detective, space-frontier, folklore-horror) |
| `workflows/t2v_v15_480p_fast.json` | Default ComfyUI T2V workflow |
| `workflows/i2v_v15_480p.json` | I2V workflow (used for chaining + character ref seeding) |

### Key showrunner.py Functions (for pipeline.py integration)

| Function | Line | Purpose |
|----------|------|---------|
| `build_scene_prompt(scene, bible)` | ~596 | Builds video prompt with character descriptions injected |
| `get_scene_seed_image(scene, series, chain)` | ~1223 | Picks I2V seed: char ref → location ref → previous frame chain |
| `build_t2v_workflow(prompt, seed, prefix, frames, steps)` | ~542 | T2V ComfyUI workflow dict |
| `build_i2v_workflow(prompt, img, seed, prefix, frames, steps)` | ~562 | I2V ComfyUI workflow dict |
| `queue_prompt(workflow)` | ~766 | POST to ComfyUI, returns prompt_id |
| `poll_until_done(prompt_id)` | ~773 | Polls until complete (30min timeout) |
| `find_latest_clip(prefix)` | ~814 | Finds most recent MP4 matching prefix in COMFYUI_OUTPUT |
| `CLIP_LENGTHS` | ~80 | `{"short": {"frames": 49}, "medium": {"frames": 65}, "long": {"frames": 81}}` |
| `QUALITY_STEPS` | ~70 | `{"draft": 15, "good": 30, "final": 50}` |

---

## Series File Format

```
series/{slug}/
├── concept.json           # User-authored: title, premise, tone, visual_style, setting
├── bible.json             # Claude-generated: characters, locations, world rules
├── reference_images/
│   ├── char_1.png         # Canonical portrait (copied here by select-portrait)
│   ├── char_1_v1.png      # Generated candidates
│   ├── char_1_v2.png
│   └── char_1_v3.png
└── episodes/
    ├── ep01.json          # Claude-generated scenes
    └── ep02.json
```

Scene JSON fields: `id`, `location`, `characters[]` (keys like `char_1`), `clip_length`, `visual`, `narration`, `dialogue[]`.

---

## API Reference (additions to standard CRUD)

| Endpoint | Purpose |
|----------|---------|
| `POST /scenes/{id}/regenerate?quality=draft\|quality` | Regenerate single clip; polls via scene.status |
| `POST /characters/{id}/generate-portrait` | Generate 3 portrait candidates via ComfyUI |
| `POST /characters/{id}/select-portrait` | Set canonical portrait; copies to `char_{id}.png` |
| `POST /episodes/{id}/produce?quality=draft\|quality` | Full episode production job |
| `POST /jobs/{id}/cancel` | Cancel a running production job; interrupts ComfyUI |
| `GET /ws/{job_id}?token=<jwt>` | WebSocket: streams job progress |
| `POST /projects/{id}/generate-scripts` | Claude writes all episode scripts |
| `GET /projects/templates` | List available project templates |
| `POST /projects/from-template?template_id=X` | Create project pre-seeded from template |
| `GET /projects/{id}/theater` | List episodes with final video paths for viewing |

---

## Security Notes

- `SECRET_KEY` is **required** in `.env` — app refuses to start without it. Generate: `openssl rand -hex 32`
- WebSocket auth via `?token=<jwt>` query param — ownership verified before `accept()`
- All `location_id` and `character_ids` in scene create/update are validated to belong to the same project
- Rate limiting: `/auth/login` 20/hour, `/auth/register` 10/hour (via `slowapi`)
- CORS restricted to `localhost:5173` and `localhost:4173` — update `ALLOWED_ORIGINS` in `.env` for production

---

## Hardware Constraints (RTX 4070 Laptop, 8GB VRAM)

Do not change these without testing:

| Parameter | Value | Reason |
|-----------|-------|--------|
| Resolution | 848×480 or 480×848 | Max for 8GB with Q4_K_S |
| `cfg` | **1.0** | Distilled model — any other value breaks output |
| `shift` | 5.0 | 480p default (9.0 for 720p) |
| Frame count | 49 / 65 / 81 | short/medium/long; must be `4n+1` |
| Clip duration | 2.0s / 2.7s / 3.4s | Corresponds to frame counts above |

**Model**: `hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf`

---

## Environment

- **Python env**: `conda activate hunyuan-comfy` (Python 3.10.9, PyTorch 2.5.1+cu121)
- **`ANTHROPIC_API_KEY`**: required for script generation
- **`SECRET_KEY`**: required for JWT auth — set in `app/backend/.env`
- **ComfyUI**: must be running on `localhost:8188` for any video/portrait generation
- **Database**: SQLite at `app/backend/storybuilder.db` (auto-created on first `uvicorn` run)
- **Claude model**: `claude-sonnet-4-20250514` (hardcoded in `showrunner.py`)
- **Static file mounts**: `/static/clips/` → `ComfyUI/output/video/`, `/static/series/` → `series/`, `/static/output/` → `output/`
