# ROADMAP — Wan 2.2 Pipeline Assessment & Improvement Plan

*Generated March 29, 2026 — based on research into Wan 2.2 ecosystem and analysis of latest commits.*

---

## Current State Assessment

### ✅ What's Working

| Feature | Implementation |
|---------|---------------|
| **Wan 2.2 Dual-Model T2V** | Full MoE workflow — high-noise + low-noise expert switching at 87.5% via `SplitSigmas` + `SamplerCustomAdvanced` chaining |
| **Wan 2.2 Dual-Model I2V** | Same dual-model architecture with `WanImageToVideo` conditioning + `ImageScale` |
| **LoRA support in workflows** | LoRA chains injected into both high and low noise experts |
| **LoRA training pipeline** | RunPod orchestrator handles full lifecycle: pod creation → SSH → dataset upload → training → download → cleanup |
| **Auto-captioning** | Florence-2 based (`auto_caption.py`) with trigger word injection |
| **Training configs** | Separate TOML configs for character, style, and motion LoRAs via musubi-tuner |
| **Web UI — Training** | Full job management with GPU availability checker, real-time status, progress bars |
| **Web UI — Theater** | Episode viewer for watching finished episodes |
| **Web UI — Templates** | Pre-seeded projects (noir detective, space frontier, folklore horror) |
| **Character consistency** | Canonical portrait generation → selection → I2V seed for dialogue scenes |
| **Ambient audio** | FFmpeg filter chains synthesizing environmental audio per location type |
| **Clip durations** | 5.1s max at 16fps (81 frames) — fits the 5-6s target |
| **720p support** | Resolution config present for 1280×720 on 24GB+ GPUs |
| **EasyCache optimization** | TeaCache presets (balanced/fast/turbo) for faster inference |
| **Quality presets** | Draft (15 steps) / Good (25) / Final (40) for Wan |

### ❌ What's Missing or Broken

| Issue | Priority | Impact |
|-------|----------|--------|
| ~~**LoRA training targets HunyuanVideo, not Wan**~~ | ✅ Done | Training orchestrator updated to Wan 2.2 (`Comfy-Org/Wan_2.2_ComfyUI_Repackaged`) |
| ~~**No S2V (Speech-to-Video)**~~ | ✅ Done | S2V workflow wired into production loop — dialogue scenes auto-route to S2V with TTS audio |
| ~~**No scene-type routing**~~ | ✅ Done | `classify_scene_type()` routes dialogue→S2V, characters→I2V, establishing→T2V |
| ~~**No TI2V-5B config**~~ | ✅ Done | `wan-5b` model config added — single-model 5B at 480p on 8GB VRAM |
| ~~**Wan 2.1 VAE instead of 2.2**~~ | ✅ Done | Updated to `wan2.2_vae.safetensors` across all configs and workflows |
| ~~**No Wan-Animate integration**~~ | ✅ Done | `build_wan_animate_workflow()` + `--motion-video` CLI flag + dispatch wiring |
| ~~**Captioning doesn't follow LoRA best practices**~~ | ✅ Done | `--character-features` strips learned traits, `--rewrite` uses Claude for best-practice captions |

---

## Improvement Plan

### Phase 1: Fix LoRA Training Target ✅ DONE

Training orchestrator and all configs updated to use Wan 2.2 models from `Comfy-Org/Wan_2.2_ComfyUI_Repackaged`:
- DiT: `wan2.2_t2v_low_noise_14B_fp16.safetensors`
- VAE: `wan2.2_vae.safetensors`
- Text encoder: `qwen_2.5_vl_7b_fp8_scaled.safetensors` + `byt5_small_glyphxl_fp16.safetensors`
- Training uses musubi-tuner with `hv_1_5_train_network.py` (Wan-compatible)
- Both remote (RunPod) and local training paths use Wan 2.2 weights

---

### Phase 2: Add TI2V-5B Config for Local Preview ✅ DONE

Added `wan-5b` model config to showrunner.py:
- Single-model `wan2.2_ti2v_5B_Q4_K_S.gguf` for both T2V and I2V (no dual-model handoff)
- 480p at 8GB VRAM minimum, shift=5.0
- Lower quality steps: draft=10, good=20, final=30
- CLI: `--video-model wan-5b` on `produce` and `produce-all` commands
- I2V workflow auto-detects single-model via missing `i2v_dual_model` key → uses single KSampler

---

### Phase 3: Wan 2.2 VAE Upgrade ✅ DONE

Updated `Wan2.1_VAE.pth` → `wan2.2_vae.safetensors` in all configs, workflow JSONs, test files, and training orchestrator.

---

### Phase 4: Scene-Type Routing ✅ DONE

Implemented `classify_scene_type()` → routes dialogue→S2V, character scenes→I2V, establishing→T2V.
- Added `scene_type` column to Scene model + API schema
- Scene type badges (S2V/I2V/T2V) shown in Episodes UI
- Production loop and single-scene regeneration both use scene-type routing

---

### Phase 5: S2V (Speech-to-Video) Integration ✅ DONE

- `build_wan_s2v_workflow()` generates audio-conditioned video with lip sync
- Production loop auto-routes dialogue scenes to S2V when audio is available
- `generate_single_scene_audio()` helper for single-scene regeneration
- Audio encoder download added to RunPod setup
- Falls back to I2V when S2V audio unavailable

---

### Phase 6: Wan-Animate Integration ✅ DONE

- `build_wan_animate_workflow()` — motion transfer from reference video to character
- `--motion-video` CLI flag on `produce` and `produce-all` commands
- Dispatch wired in `build_video_workflow()` — animate mode takes priority when motion video provided
- Model download ref added to setup.sh (commented out, ~28GB) and training_orchestrator.py
- LoRA injection supported for animate mode

---

### Phase 7: Captioning Best Practices ✅ DONE

- `--character-features` flag strips learned traits from captions via regex
- `--rewrite` two-pass mode: Florence-2 → Claude Haiku rewrites following LoRA best practices
- `strip_character_features()` handles comma/conjunction cleanup
- `prepare_dataset.sh` passes character features through to auto_caption.py

---

## Deployment Checklist

### For RunPod Production (24GB+ GPU)

```bash
# 1. Download Wan 2.2 models (after fixes applied)
#    - T2V high-noise: wan2.2_t2v_high_noise_14B (GGUF Q4_K_S or fp8)
#    - T2V low-noise:  wan2.2_t2v_low_noise_14B
#    - I2V high-noise: wan2.2_i2v_high_noise_14B
#    - I2V low-noise:  wan2.2_i2v_low_noise_14B
#    - VAE:            wan2.2_vae.safetensors (NEW - not 2.1)
#    - Text encoder:   umt5-xxl (GGUF Q8_0)
#    - CLIP vision:    sigclip_vision_patch14_384

# 2. Install ComfyUI + Kijai's WanVideoWrapper
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper \
    ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper
pip install -r ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper/requirements.txt

# 3. For S2V (Phase 5):
#    - Download Wan2.2-S2V-14B weights
#    - Needs A6000 (48GB) for comfortable inference

# 4. For LoRA training:
#    - Ensure training configs point at Wan 2.2 base models (Phase 1)
#    - Use A6000 for rank 64 character LoRA
```

### For Local Preview (RTX 4070, 8GB)

```bash
# 1. Download TI2V-5B model (after Phase 2)
#    - wan2.2_ti2v_5B.safetensors
#    - wan2.2_vae.safetensors
#    - umt5-xxl (GGUF Q8_0)

# 2. Use --video-model wan_5b for local preview runs
python scripts/showrunner.py produce my_series --episode 1 --video-model wan_5b
```

---

## Model Download Reference

| Model | Source | Size | Purpose |
|-------|--------|------|---------|
| Wan2.2-T2V-A14B (GGUF) | Kijai/WanVideo_comfy | ~5GB each | T2V high+low noise experts |
| Wan2.2-I2V-A14B (GGUF) | Kijai/WanVideo_comfy | ~5GB each | I2V high+low noise experts |
| Wan2.2-TI2V-5B | Wan-AI/Wan2.2-TI2V-5B | ~10GB | Local preview (8GB VRAM) |
| Wan2.2-S2V-14B | Wan-AI/Wan2.2-S2V-14B | ~28GB | Speech-to-video (RunPod) |
| Wan2.2-Animate-14B | Wan-AI/Wan2.2-Animate-14B | ~28GB | Motion transfer (RunPod) |
| Wan 2.2 VAE | Comfy-Org/Wan_2.2_ComfyUI_Repackaged | ~2.5GB | New high-compression VAE |
| umt5-xxl (GGUF Q8_0) | Kijai/WanVideo_comfy | ~5GB | Text encoder |
| SigCLIP ViT-L/14 | Comfy-Org | ~857MB | CLIP vision (I2V) |
| fp8 scaled models | Kijai/WanVideo_comfy_fp8_scaled | varies | Quality/VRAM tradeoff |

---

## Priority Order

1. ~~**Phase 1** — Fix LoRA training target~~ ✅
2. ~~**Phase 2** — TI2V-5B local preview~~ ✅
3. ~~**Phase 3** — Wan 2.2 VAE~~ ✅
4. ~~**Phase 4** — Scene-type routing~~ ✅
5. ~~**Phase 5** — S2V integration~~ ✅
6. ~~**Phase 7** — Captioning best practices~~ ✅
7. ~~**Phase 6** — Wan-Animate~~ ✅
