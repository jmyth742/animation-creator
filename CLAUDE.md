# HunyuanVideo 1.5 × ComfyUI Workspace

## Host Machine

| Component | Spec |
|-----------|------|
| GPU | NVIDIA GeForce RTX 4070 Laptop |
| VRAM | **8GB** |
| RAM | 31GB |
| Disk free | ~170GB |
| CUDA driver | 12.2 |
| PyTorch | 2.5.1+cu121 (pip install, not conda) |
| OS | Ubuntu 24.04 |

---

## Model Choice: HunyuanVideo 1.5 GGUF

**HunyuanVideo 1.5** (8.3B params) replaces v1.0 (13B params) — smaller, better quality,
and much more practical on 8GB VRAM. Uses GGUF quantization via
[jayn7/HunyuanVideo-1.5_T2V_480p-GGUF](https://huggingface.co/jayn7/HunyuanVideo-1.5_T2V_480p-GGUF).

| Quant | File size | Est. VRAM | Quality | Verdict |
|-------|-----------|-----------|---------|---------|
| Q8_0 | ~9.0GB | ~9GB | Best | ❌ OOM |
| Q6_K | ~7.0GB | ~7GB | Very good | ⚠️ Borderline |
| Q5_K_S | ~5.9GB | ~6GB | Good | ✅ Alt option |
| Q4_K_S | ~4.9GB | ~5GB | OK | ✅ Recommended |

**Use `Q4_K_S` CFG-distilled as default.** More VRAM headroom than v1.0.

Text encoders:
- Qwen2.5-VL-7B FP8: ~9.4GB on disk, offloads to CPU RAM
- Glyph-ByT5: ~440MB on disk, offloads to CPU RAM
- 31GB RAM handles both comfortably

---

## Resolution & Frame Limits for 8GB

**Default configuration (480p distilled):**
- Resolution: **848×480** (16:9) or **480×848** (9:16)
- Frame count: **25–33 frames** (≈1–1.4 seconds at 24fps)
- Inference steps: **20** for drafts, **30–50** for finals

**Frame count rule:** must be a multiple of 4 + 1. Valid values: 1, 5, 9, 13, 17, 21, 25, 29, 33.

**Aspect ratios at 480p:**
- 16:9 → 848×480
- 9:16 → 480×848
- 4:3 → 640×480
- 1:1 → 480×480

---

## Repository Layout

```
.
├── ComfyUI/
│   ├── custom_nodes/
│   │   ├── ComfyUI-HunyuanVideoWrapper/   # Kijai's wrapper (legacy v1.0 support)
│   │   ├── ComfyUI-GGUF/                  # REQUIRED for GGUF weight loading
│   │   └── ComfyUI-Manager/               # Node manager UI
│   ├── models/
│   │   ├── unet/                          # DiT GGUF weights
│   │   │   └── hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf
│   │   ├── vae/
│   │   │   └── hunyuanvideo15_vae_fp16.safetensors
│   │   └── text_encoders/
│   │       ├── qwen_2.5_vl_7b_fp8_scaled.safetensors
│   │       └── byt5_small_glyphxl_fp16.safetensors
│   └── workflows/
│       └── hunyuan/
│
├── scripts/
│   ├── setup_env.sh
│   ├── install_comfyui.sh
│   ├── download_models.sh              # v1.0 models (legacy)
│   ├── download_models_v15.sh          # v1.5 models (active)
│   ├── comfyui_api_gen.py
│   └── launch.sh
│
└── workflows/
    ├── t2v_v15_480p.json               # Main workflow: v1.5, 30 steps, 33 frames
    ├── t2v_v15_480p_fast.json          # Draft workflow: v1.5, 20 steps, 25 frames
    ├── t2v_gguf_540p.json              # Legacy v1.0 workflow
    └── t2v_gguf_540p_fast.json         # Legacy v1.0 draft workflow
```

---

## Installation

### 1. Conda environment

```bash
conda create -n hunyuan-comfy python=3.10.9 -y
conda activate hunyuan-comfy

# PyTorch via pip (not conda — avoids MKL/iJIT conflicts)
python -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu121

# Verify
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

### 2. ComfyUI + Custom Nodes

```bash
bash scripts/install_comfyui.sh
```

### 3. Model Downloads (v1.5)

```bash
bash scripts/download_models_v15.sh
```

Downloads:
- DiT GGUF Q4_K_S (~5GB) from jayn7
- VAE (~size) from Comfy-Org repackaged
- Qwen2.5-VL FP8 (~9.4GB) from Comfy-Org repackaged
- Glyph-ByT5 (~440MB) from Comfy-Org repackaged

---

## ComfyUI Node Configuration (v1.5)

HunyuanVideo 1.5 uses **native ComfyUI nodes** (not Kijai's wrapper).

**`UnetLoaderGGUF` (from ComfyUI-GGUF):**
- `unet_name`: `hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf`

**`DualCLIPLoaderGGUF`:**
- `clip_name1`: `qwen_2.5_vl_7b_fp8_scaled.safetensors`
- `clip_name2`: `byt5_small_glyphxl_fp16.safetensors`
- `type`: `hunyuan_video_15`

**`VAELoader`:**
- `vae_name`: `hunyuanvideo15_vae_fp16.safetensors`

**`ModelSamplingSD3`:**
- `shift`: 5.0 (for 480p), 9.0 (for 720p)

**`CFGGuider`:**
- `cfg`: 1.0 (distilled model — must be 1.0)
- `cfg`: 6.0 (full/non-distilled model)

**`BasicScheduler`:**
- `scheduler`: `simple`
- `steps`: 20–50
- `denoise`: 1.0

**`KSamplerSelect`:**
- `sampler_name`: `euler`

**`EmptyHunyuanVideo15Latent`:**
- `width`: 848, `height`: 480
- `length`: 25 (draft) or 33 (quality)
- `batch_size`: 1

---

## Inference Parameters Reference

| Parameter | This machine | Notes |
|-----------|-------------|-------|
| Resolution | 848×480 | Default for 480p model |
| `length` | 25–33 | 25 = fast, 33 = quality |
| `steps` | 20–30 | 50 for finals |
| `cfg` | 1.0 | **Must be 1.0 for distilled model** |
| `shift` | 5.0 | 480p default |
| `sampler` | euler | Default |
| `scheduler` | simple | Default |

---

## VRAM Monitoring

```bash
watch -n 1 nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv
```

---

## Launching ComfyUI

```bash
conda activate hunyuan-comfy
bash scripts/launch.sh
```

Open: http://localhost:8188

---

## ComfyUI API Automation

```bash
# Quick generation with prompt override
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p_fast.json \
  -p "A drone shot over Berlin at golden hour, cinematic, 35mm" \
  -s 42

# Full quality run
python scripts/comfyui_api_gen.py workflows/t2v_v15_480p.json \
  -p "A cat sitting on a windowsill watching rain" \
  --steps 50 --frames 33
```

---

## Performance Optimizations

### Draft → Final workflow
1. Generate at 20 steps, 25 frames to validate prompt and composition
2. Re-run at 30–50 steps, 33 frames once happy with the result
3. Fix the seed between runs for consistent composition

### Flash Attention
```bash
python -m pip install flash-attn --no-build-isolation
```
Optional, reduces VRAM ~10–15%.

---

## Prompt Engineering

HunyuanVideo 1.5 uses Qwen2.5-VL which understands natural language well.

**Tips:**
- Describe subject, environment, motion, and camera separately
- Be explicit about camera movement: "slow push-in", "static shot", "handheld"
- Specify lighting: "golden hour", "overcast diffused light", "neon-lit night"
- End with style: "cinematic, 35mm film grain" or "photorealistic, 8K"

**Example:**
```
A woman in a red coat walks slowly through an empty Berlin train station at dawn.
The camera tracks alongside her at eye level. Warm morning light streams through
tall windows. Cinematic, 35mm film grain, shallow depth of field.
```

---

## References

- HunyuanVideo 1.5: https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5
- GGUF weights (jayn7): https://huggingface.co/jayn7/HunyuanVideo-1.5_T2V_480p-GGUF
- Comfy-Org repackaged: https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged
- ComfyUI-GGUF: https://github.com/city96/ComfyUI-GGUF
- ComfyUI native HunyuanVideo 1.5: https://blog.comfy.org/p/hunyuanvideo-15-native-support
- ComfyUI examples: https://comfyanonymous.github.io/ComfyUI_examples/hunyuan_video/
