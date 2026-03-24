# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An end-to-end automated animated series production pipeline. Given a `concept.json`, it uses Claude to write episode scripts, ComfyUI (HunyuanVideo 1.5) to generate video clips, Edge-TTS for voiceover, and FFmpeg to stitch everything into finished MP4 episodes. A full-stack web UI (FastAPI + React) lets users manage projects without touching the CLI.

---

## Running the System

Three services must be running for full functionality:

```bash
# Terminal 1: ComfyUI video generation server
conda activate hunyuan-comfy
bash scripts/launch.sh                  # → http://localhost:8188

# Terminal 2: FastAPI backend
cd app/backend
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload               # → http://localhost:8000

# Terminal 3: React frontend dev server
cd app/frontend
npm run dev                             # → http://localhost:5173

# Build frontend for production
cd app/frontend && npm run build        # output → dist/
```

### CLI Production Pipeline (standalone, no web UI needed)

```bash
# Create a new series directory scaffold
python scripts/showrunner.py create my_series

# Generate series bible + episode scripts via Claude
python scripts/showrunner.py write my_series
python scripts/showrunner.py write my_series --episode 5   # single episode
python scripts/showrunner.py write my_series --force       # overwrite existing

# Produce a video episode (requires ComfyUI running)
python scripts/showrunner.py produce my_series --episode 1 --image ref.png
python scripts/showrunner.py produce my_series --episode 1 --no-audio
python scripts/showrunner.py produce my_series --episode 1 --resume  # continue interrupted

# Batch produce all episodes
python scripts/showrunner.py produce-all my_series

# Check series status
python scripts/showrunner.py status my_series

# Quick single-clip generation test (bypasses showrunner)
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p_fast.json \
  -p "A cat on a windowsill, cinematic" -s 42
```

---

## Architecture

```
React UI (Vite/Tailwind)
    ↓  Axios + WebSocket
FastAPI Backend (app/backend/)
    ├── routers/           CRUD for projects, characters, locations, episodes, scenes
    ├── pipeline.py        Bridges DB ↔ showrunner: exports JSON, spawns production jobs
    ├── routers/generate.py  Calls showrunner.cmd_write() → Claude API for script gen
    └── SQLite (SQLAlchemy ORM)
         ↓
showrunner.py (scripts/)   Main orchestrator — write mode calls Claude; produce mode calls:
    ├── ComfyUI API (localhost:8188)   T2V + I2V video clip generation
    ├── Edge-TTS                       Per-scene voiceover synthesis
    └── FFmpeg                         Audio mux + clip stitching → final MP4
```

### Data Flow for Episode Production

1. Web UI triggers `POST /episodes/{id}/produce` → `pipeline.py::produce_episode_job()`
2. `pipeline.py` exports the project DB to JSON files (`series/{slug}/bible.json`, `episodes/ep*.json`)
3. A background `threading.Thread` runs `showrunner.cmd_produce()`
4. `showrunner` calls ComfyUI for each scene: first scene = T2V, subsequent scenes = I2V using last frame of previous clip (visual chaining)
5. Edge-TTS generates per-scene audio; FFmpeg stitches clips + audio
6. Progress is written to `GenerationJob.log_text` and streamed to the UI via WebSocket (`/ws/{job_id}`)

### Key Source Files

| File | Role |
|------|------|
| `scripts/showrunner.py` | ~95KB main orchestrator; all Claude calls, ComfyUI calls, FFmpeg logic |
| `app/backend/pipeline.py` | DB→JSON export, background job runner, progress tracking |
| `app/backend/models.py` | SQLAlchemy ORM: User, Project, Character, Location, Episode, Scene, GenerationJob |
| `app/backend/routers/generate.py` | `POST /projects/{id}/generate-scripts` → Claude |
| `app/backend/routers/episodes.py` | `POST /episodes/{id}/produce` → background job |
| `workflows/t2v_v15_480p_fast.json` | Default ComfyUI workflow (draft quality) |
| `workflows/i2v_v15_480p.json` | Image-to-video workflow for chained scenes |

### Series File Format

```
series/{slug}/
├── concept.json      # User-authored: title, premise, tone, visual_style, characters, setting
├── bible.json        # Claude-generated: character visuals/voices, locations, world rules
└── episodes/
    ├── ep01.json     # Claude-generated: scenes with visual prompts, narration, dialogue
    └── ep02.json
```

Each scene in an episode JSON has: `location`, `characters[]`, `clip_length` (short/medium/long), `visual` (T2V prompt), `narration`, `dialogue[]`.

---

## Hardware Constraints (RTX 4070 Laptop, 8GB VRAM)

These constraints are baked into the codebase — don't change them without testing:

| Parameter | Value | Reason |
|-----------|-------|--------|
| Resolution | 848×480 or 480×848 | Max for 8GB with Q4_K_S |
| `cfg` | **1.0** | Distilled model — any other value breaks output |
| `shift` | 5.0 | 480p default (use 9.0 for 720p) |
| Frame count | 49/65/81 (short/medium/long) | Must be `4n + 1`; max ~81 for 8GB |
| Clip duration | 2.0s / 2.7s / 3.4s | Corresponds to above frame counts |

**Model**: `hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf` (Q4_K_S = recommended for 8GB)

---

## Environment

- **Python env**: `conda activate hunyuan-comfy` (Python 3.10.9, PyTorch 2.5.1+cu121)
- **ANTHROPIC_API_KEY**: required for `showrunner.py write` and `/generate-scripts` endpoint
- **ComfyUI**: must be running on `localhost:8188` for any video production
- **Database**: SQLite at `app/backend/storybuilder.db` (auto-created on first run via `init_db()`)
- **Claude model in use**: `claude-sonnet-4-20250514` (set in `showrunner.py`)

---

## ComfyUI Node Notes

HunyuanVideo 1.5 uses **native ComfyUI nodes** (not the legacy Kijai wrapper). The `ComfyUI-GGUF` custom node is required for `UnetLoaderGGUF`. The `DualCLIPLoader` type must be `hunyuan_video_15`. See `workflows/t2v_v15_480p.json` for the canonical node graph.
