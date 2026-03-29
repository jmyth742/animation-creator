# Animation Creator

An end-to-end pipeline that turns a story concept into fully-produced animated episodes — complete with AI-generated scripts, video, voiceover, and ambient audio. Designed to run on consumer GPUs (8 GB VRAM and up).

**Stack:** Claude (scripting) + HunyuanVideo 1.5 / WAN 2.2 (video) + ComfyUI (orchestration) + Edge-TTS (voice) + FFmpeg (stitching) + FastAPI & React (web UI)

---

## How It Works

```
concept.json  +  reference images
        |
        v
  Claude API  -->  series bible  +  episode scripts
        |
        v
  ComfyUI (HunyuanVideo / WAN)  -->  T2V & I2V chained video clips
        |
        v
  Edge-TTS  -->  per-scene voiceover
        |
        v
  FFmpeg  -->  stitched final episodes (MP4)
```

Each episode is produced as a chain of short video clips (2-3 seconds each). The last frame of each clip seeds the next via image-to-video, maintaining visual continuity. Character canonical portraits are injected as I2V seeds for dialogue scenes.

---

## Quick Start (CLI)

```bash
# 1. Create a new series
python scripts/showrunner.py create my_series

# 2. Edit the concept (the only thing you write - everything else is generated)
nano series/my_series/concept.json

# 3. Drop reference images for visual style
cp my_ref.png series/my_series/reference_images/

# 4. Generate bible + episode scripts via Claude
python scripts/showrunner.py write my_series

# 5. Produce episode 1
python scripts/showrunner.py produce my_series --episode 1 \
  --image series/my_series/reference_images/my_ref.png

# 6. Check progress
python scripts/showrunner.py status my_series
```

### Other CLI Commands

```bash
# Produce all episodes
python scripts/showrunner.py produce-all my_series --resume

# Export voiceover script for review
python scripts/showrunner.py script my_series --episode 1

# Regenerate scripts from scratch
python scripts/showrunner.py write my_series --force

# Quick single-clip test (no Claude needed)
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p_fast.json \
  -p "A cat on a windowsill, cinematic" -s 42

# Single image-to-video
python scripts/i2v_generate.py photo.jpg -p "The scene comes alive" --frames 81
```

---

## Web UI

A full-stack application for managing projects, characters, locations, and episodes visually.

```bash
# Terminal 1: ComfyUI
bash scripts/launch.sh

# Terminal 2: FastAPI backend
cd app/backend
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload

# Terminal 3: React frontend
cd app/frontend
npm run dev
```

**Features:**
- Project management with pre-seeded templates (noir detective, space frontier, folklore horror)
- Character editor with AI portrait generation and canonical portrait selection
- Location management with visual descriptions
- Episode/scene timeline with per-scene regeneration
- Theater view for watching finished episodes
- LoRA training job management
- Real-time progress via WebSocket

### First-Time Setup

```bash
cp app/backend/.env.example app/backend/.env
# Edit .env and set SECRET_KEY=$(openssl rand -hex 32)

cd app/frontend && npm install
```

---

## The Concept File

This is the only thing you write. Everything else is AI-generated.

```json
{
  "title": "The Keeper's Garden",
  "premise": "An elderly woman tends a magical rooftop garden in Tokyo...",
  "tone": "whimsical, heartfelt, contemplative",
  "visual_style": "anime, Studio Ghibli inspired, watercolor",
  "target_audience": "general",
  "setting": "Quiet residential Tokyo neighborhood, present day.",
  "main_characters": [
    "Hana - elderly Japanese woman, silver hair, the garden keeper",
    "Sora - 10-year-old boy, round glasses, yellow raincoat, curious"
  ],
  "season_arc": "Sora learns each plant responds to emotion. By the finale, he must save the garden from demolition.",
  "reference_images": [],
  "episodes_per_season": 20,
  "episode_duration_seconds": 30
}
```

---

## What Keeps Episodes Coherent

| Mechanism | What It Does |
|-----------|-------------|
| **Series bible** | Character visuals, locations, style - injected into every prompt |
| **I2V chaining** | Last frame of each clip feeds as start image for the next |
| **Character portraits** | Canonical portrait used as I2V seed for dialogue scenes |
| **Episode context** | Claude sees previous episode summaries when writing new ones |
| **LoRA fine-tuning** | Optional per-character LoRA for stronger visual consistency |

---

## Video Generation

### Supported Models

| Model | Resolution | FPS | VRAM | Notes |
|-------|-----------|-----|------|-------|
| HunyuanVideo 1.5 (GGUF) | 848x480 | 24 | 8 GB+ | Default, distilled, fast |
| WAN 2.2 (dual-model) | 832x480 | 16 | 12 GB+ | Higher quality, dual high/low noise |

### Clip Lengths

| Type | Frames | Duration | Use Case |
|------|--------|----------|----------|
| short | 49 | 2.0s | Action, transitions |
| medium | 65 | 2.7s | Dialogue, character moments |
| long | 81 | 3.4s | Establishing shots, emotional beats |

### Quality Presets

| Preset | Steps | Use Case |
|--------|-------|----------|
| draft | 15 | Quick preview |
| good | 30 | Production quality |
| final | 50 | Maximum quality |

---

## LoRA Training (Character Consistency)

Train a LoRA on your characters so they look consistent across every episode.

### Preparing Data

Collect 15-30 images of your character in varied poses, expressions, and lighting. Caption each with a trigger word + description:

```
ohwx woman, standing with arms crossed, confident expression, wearing
red coat, in a park at sunset, warm golden light
```

### Training (RunPod)

```bash
# Prepare dataset
bash runpod/prepare_dataset.sh /path/to/images my_character "ohwx person"

# Train (A6000 recommended)
bash training/train.sh

# LoRA auto-copies to ComfyUI/models/loras/ when done
```

| Parameter | Default |
|-----------|---------|
| Rank | 32 |
| Learning rate | 1e-4 (adamw8bit) |
| Epochs | 150 |
| Optimizer | adamw8bit |

Training configs are in `training/configs/` with templates for character, style, and motion LoRAs.

---

## RunPod Cloud Deployment

For higher quality (720p, longer clips) and LoRA training on cloud GPUs.

```bash
# One-time setup on a RunPod pod with network volume
bash runpod/setup.sh

# Start ComfyUI on each session
bash runpod/start.sh

# Then use showrunner normally
python scripts/showrunner.py produce my_series --episode 1
```

| Capability | Local (8 GB) | RTX 3090 (24 GB) | A6000 (48 GB) |
|-----------|-------------|-------------------|----------------|
| Resolution | 480x320 | 848x480 to 1280x720 | 1280x720+ |
| Max clip | 3.4s | 5-10s | 10s+ |
| LoRA training | No | Rank 32 | Rank 64-128 |
| Speed | ~10 min/clip | ~3-5 min/clip | ~2-3 min/clip |

---

## Installation

### Prerequisites

- NVIDIA GPU with 8 GB+ VRAM
- Conda (Miniconda or Anaconda)
- ~40 GB disk space (models + ComfyUI)
- Anthropic API key (for script generation)

### Setup

```bash
# 1. Python environment
conda create -n hunyuan-comfy python=3.10.9 -y
conda activate hunyuan-comfy

# 2. PyTorch
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu121

# 3. ComfyUI + custom nodes
bash scripts/install_comfyui.sh

# 4. Download models
bash scripts/download_models_v15.sh    # T2V (~15 GB)
bash scripts/download_i2v_models.sh    # I2V (~6 GB)

# 5. Production dependencies
pip install edge-tts anthropic huggingface_hub websocket-client

# 6. Set API key
export ANTHROPIC_API_KEY="your-key-here"
```

---

## Project Structure

```
.
├── scripts/
│   ├── showrunner.py              # Main production orchestrator
│   ├── comfyui_api_gen.py         # ComfyUI API client
│   ├── i2v_generate.py            # Single image-to-video
│   ├── generate_story.py          # Simple T2V story generator
│   ├── generate_story_i2v.py      # I2V chained story generator
│   ├── install_comfyui.sh         # ComfyUI installer
│   ├── download_models_v15.sh     # T2V model downloader
│   ├── download_i2v_models.sh     # I2V model downloader
│   └── launch.sh                  # ComfyUI launcher
│
├── app/
│   ├── backend/                   # FastAPI + SQLAlchemy + SQLite
│   │   ├── main.py                # App entry, CORS, WebSocket
│   │   ├── pipeline.py            # DB <-> showrunner bridge
│   │   ├── models.py              # ORM models
│   │   ├── templates.py           # Pre-seeded project templates
│   │   └── routers/               # REST endpoints
│   │
│   └── frontend/                  # React + Vite + Tailwind
│       └── src/components/
│           ├── EpisodesTab.jsx    # Scene timeline + regeneration
│           ├── CharacterModal.jsx # Portrait generation + selection
│           ├── TheaterTab.jsx     # Episode viewer
│           └── TrainingTab.jsx    # LoRA training management
│
├── workflows/                     # ComfyUI workflow JSONs
│   ├── t2v_v15_480p.json         # Text-to-video (quality)
│   ├── t2v_v15_480p_fast.json    # Text-to-video (draft)
│   └── i2v_v15_480p.json         # Image-to-video
│
├── series/                        # Series projects
│   └── .template/concept.json     # Template for new series
│
├── training/                      # LoRA training configs
│   ├── configs/                   # Dataset + LoRA config templates
│   ├── train.sh                   # Training entry point
│   └── setup.sh                   # Training env setup
│
├── runpod/                        # Cloud GPU deployment
│   ├── setup.sh                   # One-time RunPod setup
│   ├── start.sh                   # Per-session launcher
│   └── train_wan_lora.sh          # WAN 2.2 LoRA training
│
└── output/                        # Generated episodes (gitignored)
```

---

## License

This project is for personal/educational use.
