# Text-to-Video Production Pipeline

Automated animated series production using HunyuanVideo 1.5, ComfyUI, Claude API, and Edge-TTS. Designed for an 8GB VRAM GPU (RTX 4070 Laptop).

Takes a high-level concept and reference images → generates full episode scripts → produces video clips → adds AI voiceover → outputs finished episodes ready for YouTube Shorts.

## Quick Start

```bash
# 1. Create a new series
python scripts/showrunner.py create my_series

# 2. Edit the concept file with your idea
nano series/my_series/concept.json

# 3. Drop 1-2 reference images for visual style
cp my_reference.png series/my_series/reference_images/

# 4. Claude generates bible + all episode scripts
python scripts/showrunner.py write my_series

# 5. Produce episode 1 with reference image
python scripts/showrunner.py produce my_series --episode 1 \
  --image series/my_series/reference_images/my_reference.png

# 6. Check progress
python scripts/showrunner.py status my_series
```

---

## Architecture

```
concept.json + reference images (YOU WRITE THIS)
        │
        ▼
   Claude API generates bible + 20 episode scripts
        │
        ▼
   ┌────────────────────────────────────────────┐
   │  Per Episode:                               │
   │                                             │
   │  Reference Image ──► I2V Clip 1             │
   │                        │                    │
   │                   last frame                │
   │                        │                    │
   │                        ▼                    │
   │                     I2V Clip 2              │
   │                        │                    │
   │                   last frame                │
   │                        │                    │
   │                        ▼                    │
   │                      ...                    │
   │                        │                    │
   │  Edge-TTS ──► per-scene voiceover audio     │
   │                        │                    │
   │  FFmpeg ──► stitch clips + audio            │
   │                        │                    │
   │                        ▼                    │
   │              ep01_final.mp4                 │
   └────────────────────────────────────────────┘
```

### What keeps episodes coherent

| Mechanism | What it does |
|-----------|-------------|
| **Series bible** | Character visuals, locations, style prompt — injected into every video prompt |
| **I2V chaining** | Last frame of each clip feeds as start image for the next clip |
| **Episode context** | Claude sees previous episode summaries when writing new ones |
| **Season arc** | Defined in concept, guides Claude's story progression across all 20 episodes |
| **Consistent style string** | Same art style appended to every generation prompt |

---

## The Concept File

This is the only thing you write. Everything else is generated.

```json
{
  "title": "The Keeper's Garden",
  "premise": "An elderly woman tends a magical rooftop garden in Tokyo. A curious boy discovers it and becomes her apprentice.",
  "tone": "whimsical, heartfelt, contemplative",
  "visual_style": "anime, Studio Ghibli inspired, watercolor",
  "target_audience": "general",
  "setting": "Quiet residential Tokyo neighborhood, present day. A rooftop garden with subtle magical properties.",
  "main_characters": [
    "Hana — elderly Japanese woman, silver hair, indigo apron, the garden keeper",
    "Sora — 10-year-old boy, messy black hair, round glasses, yellow raincoat, curious"
  ],
  "season_arc": "Sora learns to tend the garden and discovers each plant responds to genuine emotion. By the finale, he must save the garden when the building is threatened with demolition.",
  "reference_images": [],
  "episodes_per_season": 20,
  "episode_duration_seconds": 30
}
```

---

## Showrunner Commands

### `create` — Start a new series

```bash
python scripts/showrunner.py create my_series
```

Creates the directory structure:

```
series/my_series/
  concept.json            ← edit this
  reference_images/       ← drop images here
  episodes/               ← auto-generated
  bible.json              ← auto-generated
```

### `write` — Generate scripts via Claude

```bash
# Generate bible + all 20 episodes
python scripts/showrunner.py write my_series

# Generate just one episode
python scripts/showrunner.py write my_series --episode 5

# Regenerate everything from scratch
python scripts/showrunner.py write my_series --force
```

Claude generates:
- **Bible**: characters (with visual descriptions + TTS voice assignments), locations, world rules, season arc
- **Episodes**: scene-by-scene breakdowns with visual prompts, narration, dialogue, and variable clip lengths

### `script` — Export voiceover scripts

```bash
python scripts/showrunner.py script my_series --episode 1
```

Outputs a readable script with timestamps, narration text, and dialogue — useful for review before producing.

### `produce` — Generate an episode

```bash
# With reference image (recommended)
python scripts/showrunner.py produce my_series --episode 1 \
  --image series/my_series/reference_images/ref.png

# Without reference image (T2V for first clip, I2V chain for rest)
python scripts/showrunner.py produce my_series --episode 1

# Resume after interruption
python scripts/showrunner.py produce my_series --episode 1 --resume

# Skip audio (video only)
python scripts/showrunner.py produce my_series --episode 1 --no-audio
```

This:
1. Generates Edge-TTS voiceover audio per scene
2. Generates video clips via ComfyUI (I2V chained)
3. Muxes audio onto each clip
4. Stitches everything into a final MP4

### `produce-all` — Batch produce every episode

```bash
python scripts/showrunner.py produce-all my_series \
  --image series/my_series/reference_images/ref.png --resume
```

### `status` — Check series progress

```bash
python scripts/showrunner.py status my_series
```

---

## Output Structure

```
output/my_series/
  ep01/
    ep01_script.txt           ← voiceover script with timestamps
    ep01_final.mp4            ← finished episode (video + audio)
    audio/
      ep01_s01.mp3            ← per-scene TTS audio
      ep01_s02.mp3
      ...
  ep02/
    ...
```

---

## Video Generation Details

### Resolution & Clip Lengths

Constrained by 8GB VRAM at 480×320 resolution:

| Clip type | Frames | Duration | Use case |
|-----------|--------|----------|----------|
| `short` | 49 | 2.0s | Action, transitions, quick cuts |
| `medium` | 65 | 2.7s | Dialogue, character moments |
| `long` | 81 | 3.4s | Establishing shots, atmospheric, emotional beats |

Claude chooses the clip length per scene based on content. A 30-second episode typically has 9–15 scenes.

### Models Used

| Component | Model | Size | Source |
|-----------|-------|------|--------|
| DiT (T2V) | HunyuanVideo 1.5 480p distilled Q4_K_S | 4.9GB | jayn7/HunyuanVideo-1.5_T2V_480p-GGUF |
| DiT (I2V) | HunyuanVideo 1.5 480p I2V distilled Q4_K_S | 4.9GB | jayn7/HunyuanVideo-1.5_I2V_480p-GGUF |
| Text encoder 1 | Qwen2.5-VL-7B FP8 | 9.4GB | Comfy-Org/HunyuanVideo_1.5_repackaged |
| Text encoder 2 | Glyph-ByT5 FP16 | 440MB | Comfy-Org/HunyuanVideo_1.5_repackaged |
| VAE | HunyuanVideo 1.5 VAE FP16 | 2.4GB | Comfy-Org/HunyuanVideo_1.5_repackaged |
| CLIP Vision | SigCLIP ViT-L/14 384px | 857MB | Comfy-Org/HunyuanVideo_1.5_repackaged |

### Sampler Settings

| Parameter | Value | Notes |
|-----------|-------|-------|
| Sampler | euler | |
| Scheduler | simple | |
| Steps | 15 | Balance of speed vs quality |
| CFG | 1.0 | Required for distilled model |
| Shift | 5.0 | 480p default |

---

## Standalone Scripts

Beyond the showrunner, individual scripts are available for manual use:

### `comfyui_api_gen.py` — Queue any workflow

```bash
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p_fast.json \
  -p "A cat on a windowsill" -s 42
```

### `i2v_generate.py` — Single image-to-video

```bash
python scripts/i2v_generate.py photo.jpg \
  -p "The scene comes alive with gentle motion" \
  --frames 81 --seed 42
```

### `generate_story.py` — Simple multi-clip story (no Claude, no TTS)

```bash
python scripts/generate_story.py midnight_ramen
```

Built-in stories: `midnight_ramen`, (add more in the script's `STORIES` dict).

### `generate_story_i2v.py` — I2V chained story

```bash
python scripts/generate_story_i2v.py forest_spirit --image ref.png
```

Built-in stories: `midnight_ramen`, `forest_spirit`.

---

## Installation

### Prerequisites

- NVIDIA GPU with 8GB+ VRAM
- Conda (Miniconda/Anaconda)
- ~40GB disk space (models + ComfyUI)

### Setup

```bash
# 1. Create conda environment
conda create -n hunyuan-comfy python=3.10.9 -y
conda activate hunyuan-comfy

# 2. Install PyTorch (pip, not conda — avoids MKL conflicts)
python -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu121

# 3. Install ComfyUI + custom nodes
bash scripts/install_comfyui.sh

# 4. Download T2V models (~15GB)
bash scripts/download_models_v15.sh

# 5. Download I2V models (~5.8GB)
bash scripts/download_i2v_models.sh

# 6. Install production dependencies
python -m pip install edge-tts anthropic huggingface_hub websocket-client
```

### Environment Variables

```bash
export ANTHROPIC_API_KEY="your-key-here"  # Required for showrunner write command
```

### Launching ComfyUI

```bash
conda activate hunyuan-comfy
bash scripts/launch.sh
```

ComfyUI must be running at `http://localhost:8188` before producing episodes.

---

## Directory Structure

```
text-to-video/
├── scripts/
│   ├── showrunner.py              # Main production pipeline
│   ├── produce_episode.py         # Standalone episode producer
│   ├── generate_story.py          # Simple T2V story generator
│   ├── generate_story_i2v.py      # I2V chained story generator
│   ├── i2v_generate.py            # Single image-to-video
│   ├── comfyui_api_gen.py         # Raw ComfyUI API client
│   ├── setup_env.sh               # Conda env setup
│   ├── install_comfyui.sh         # ComfyUI + custom nodes installer
│   ├── download_models_v15.sh     # T2V model downloader
│   ├── download_i2v_models.sh     # I2V model downloader
│   ├── download_models.sh         # Legacy v1.0 downloader
│   └── launch.sh                  # ComfyUI launcher
│
├── series/
│   ├── .template/
│   │   └── concept.json           # Template for new series
│   └── example_series.json        # Example series definition
│
├── workflows/
│   ├── t2v_v15_480p.json          # T2V quality workflow
│   ├── t2v_v15_480p_fast.json     # T2V draft workflow
│   ├── i2v_v15_480p.json          # I2V workflow
│   ├── t2v_v15_test.json          # Minimal test workflow
│   ├── t2v_gguf_540p.json         # Legacy v1.0 workflow
│   └── fight_scene_clip*.json     # Example multi-clip workflows
│
├── output/                        # Generated episodes go here
│
├── ComfyUI/                       # ComfyUI installation
│   ├── models/
│   │   ├── unet/                  # GGUF model weights
│   │   ├── vae/                   # VAE weights
│   │   ├── text_encoders/         # Qwen + ByT5
│   │   └── clip_vision/           # SigCLIP
│   ├── custom_nodes/
│   │   ├── ComfyUI-GGUF/         # GGUF weight loader
│   │   ├── ComfyUI-HunyuanVideoWrapper/
│   │   └── ComfyUI-Manager/
│   ├── input/                     # Reference images go here
│   └── output/video/              # Raw clip output
│
├── CLAUDE.md                      # Machine specs + technical reference
└── README.md                      # This file
```

---

## Tips

- **Start with `--no-audio`** to test video generation before adding TTS
- **Use `--resume`** liberally — it skips completed clips so you can restart safely
- **Monitor VRAM** while producing: `watch -n 1 nvidia-smi`
- **Reference images matter** — a strong reference image sets the visual tone for the entire episode
- **Review scripts before producing** — use `showrunner.py script` to check dialogue and narration before spending time on video generation
- **Iterate on concepts** — run `write --force` to regenerate episodes if you tweak the concept
- **Each episode takes ~30-60 minutes** to produce on an RTX 4070 Laptop depending on scene count

---

## RunPod Cloud Deployment

For higher quality output (720p, longer clips) and LoRA training, deploy to RunPod.

### RunPod Setup

**1. Create a Network Volume (50GB)**

In the RunPod dashboard → Storage → Create Network Volume. Pick the same region as your GPU pods.

**2. Sync your project to the volume**

Start a cheap CPU pod attached to your volume, then:

```bash
# From your local machine
rsync -avz --exclude 'ComfyUI/models' --exclude 'ComfyUI/.git' \
  ~/text-to-video/ root@POD_IP:/workspace/text-to-video/
```

**3. Run the setup script (one-time)**

SSH into the pod and run:

```bash
bash /workspace/text-to-video/runpod/setup.sh
```

This installs ComfyUI, custom nodes, downloads all models (~25GB), and sets up musubi-tuner for LoRA training.

**4. Store your API key**

```bash
echo 'ANTHROPIC_API_KEY=your-key-here' > /workspace/.env
```

**5. Start a GPU pod for production**

Start a pod (RTX 3090 / A5000 for inference, A6000 / A100 for training), attach your network volume, then:

```bash
bash /workspace/text-to-video/runpod/start.sh
```

ComfyUI starts on port 8188 (accessible via RunPod's proxy URL). Then use the showrunner normally:

```bash
cd /workspace/text-to-video
python scripts/showrunner.py produce my_series --episode 1
```

### What RunPod unlocks vs local 8GB

| Capability | Local (8GB) | RunPod 3090 (24GB) | RunPod A6000 (48GB) |
|-----------|-------------|--------------------|--------------------|
| Resolution | 480×320 | **848×480 to 1280×720** | **1280×720+** |
| Max clip length | 3.4s (81f) | **5-10s (121-241f)** | **10s+** |
| Quality | Q4_K_S | **Q5_K_S or Q6_K** | **Q8_0 or FP8** |
| LoRA training | No | Rank 32 possible | **Rank 64-128** |
| Generation speed | ~10min/clip | **~3-5min/clip** | **~2-3min/clip** |

### RunPod GPU Recommendations

| Task | GPU | Cost | Notes |
|------|-----|------|-------|
| Episode production | RTX 3090 24GB | ~$0.35/hr | Best value for inference |
| Higher quality production | A5000 24GB | ~$0.45/hr | More stable than 3090 |
| LoRA training | A6000 48GB | ~$0.65/hr | Comfortable for rank 32-64 |
| Fast training + production | A100 40GB | ~$1.10/hr | Train + produce in one session |

---

## LoRA Training for Character Consistency

Train a LoRA on your characters so they look consistent across every episode.

### Preparing Training Data

```bash
# 1. Collect 15-30 images of your character in various poses/angles
# 2. Prepare the dataset
bash runpod/prepare_dataset.sh /path/to/raw/images my_character "ohwx person"

# 3. Edit the generated captions in /workspace/datasets/my_character/
#    Each .txt file should start with the trigger word, then describe
#    the pose, expression, clothing, and background.
```

**Good training data:**
- 15-30 images (or 10-20 short video clips)
- Varied poses: front, side, 3/4 view, sitting, standing
- Varied expressions: smiling, serious, talking
- Consistent character but varied settings/lighting
- Each captioned with trigger word + description

**Caption example:**
```
ohwx woman, standing with arms crossed, confident expression, wearing
red coat and black boots, in a park at sunset, warm golden light
```

### Training

```bash
# SSH into a RunPod A6000 pod with your volume attached
bash /workspace/text-to-video/runpod/train_lora.sh \
  /workspace/datasets/my_character \
  my_character

# Training takes 2-6 hours depending on dataset size
# Checkpoints saved every 25 epochs
# Final LoRA auto-converted and copied to ComfyUI/models/loras/
```

**Training parameters (defaults in train_lora.sh):**

| Parameter | Default | Notes |
|-----------|---------|-------|
| Rank | 32 | 16 for simple characters, 64 for complex |
| Learning rate | 1e-4 | With adamw8bit optimizer |
| Epochs | 150 | Monitor loss, stop at plateau |
| blocks_to_swap | 32 | Set to 20 on 48GB GPU for speed |

### Using Your LoRA

The trained LoRA is automatically copied to `ComfyUI/models/loras/`. To use it in workflows, add a `LoraLoaderModelOnly` node between the UNet loader and sampler:

```
UnetLoaderGGUF → LoraLoaderModelOnly (strength: 0.7) → ModelSamplingSD3 → ...
```

Start with strength 0.7, adjust between 0.5–1.0. Higher = stronger character likeness but less flexibility.

### LoRA training files

```
runpod/
├── setup.sh              # One-time RunPod setup (ComfyUI + models + musubi-tuner)
├── start.sh              # Start ComfyUI on each new pod session
├── train_lora.sh         # Full LoRA training pipeline
└── prepare_dataset.sh    # Prepare images/videos for training
```
