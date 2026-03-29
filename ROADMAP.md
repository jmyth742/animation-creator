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
| **LoRA training targets HunyuanVideo, not Wan** | 🔴 Critical | Trained LoRAs won't load in Wan 2.2 — different architecture (`WanAttentionBlock` vs `MMDoubleStreamBlock`) |
| **No S2V (Speech-to-Video)** | 🟠 High | Dialogue scenes have no lip sync — audio bolted onto silent video |
| **No scene-type routing** | 🟠 High | All scenes go through same T2V→I2V chain regardless of content |
| **No TI2V-5B config** | 🟡 Medium | Can't preview on local 8GB GPU — must use RunPod for everything |
| **Wan 2.1 VAE instead of 2.2** | 🟡 Medium | Missing 16×16×4 compression — less efficient VRAM usage |
| **No Wan-Animate integration** | 🟡 Medium | Complex motion scenes lack motion transfer capability |
| **Captioning doesn't follow LoRA best practices** | 🟡 Medium | Florence-2 describes everything including character features — should omit what the LoRA is meant to learn |

---

## Improvement Plan

### Phase 1: Fix LoRA Training Target (Critical)

**Problem:** `training/configs/character_lora.toml`, `style_lora.toml`, and `motion_lora.toml` all reference:
```
pretrained_model_name_or_path = "/workspace/models/hunyuan_video_I2V_720_fp16.safetensors"
```
This produces HunyuanVideo LoRAs that are architecturally incompatible with Wan 2.2.

**Fix:**
1. Update all training configs to point at Wan 2.2 base model weights
2. Update `training_orchestrator.py` HuggingFace references to download Wan 2.2 models:
   - DiT: `Wan-AI/Wan2.2-I2V-A14B` or `Wan-AI/Wan2.2-T2V-A14B`
   - VAE: `Wan-AI/Wan2.2-TI2V-5B` (includes new VAE)
   - Text encoder: `umt5-xxl` (same across Wan versions)
3. Update `runpod/train_wan_lora.sh` to use Wan 2.2 model paths
4. Verify musubi-tuner supports Wan 2.2 MoE architecture for LoRA extraction
5. If musubi-tuner doesn't support Wan 2.2 yet, fall back to training on Wan 2.1 14B (LoRAs may transfer to 2.2 with reduced effectiveness — test this)

**Files to modify:**
- `training/configs/character_lora.toml`
- `training/configs/style_lora.toml`
- `training/configs/motion_lora.toml`
- `runpod/training_orchestrator.py` (HF model references)
- `runpod/train_wan_lora.sh`
- `training/setup.sh` (model download step)

---

### Phase 2: Add TI2V-5B Config for Local Preview

**Problem:** Only 14B MoE configs exist — can't run anything on the RTX 4070 Laptop (8GB VRAM).

**Fix:** Add `wan_5b` model config to `showrunner.py`:

```python
"wan_5b": {
    "label": "WAN 2.2 TI2V-5B (local preview)",
    "fps": 24,
    "cfg": 5.0,
    "sampler": "uni_pc_bh2",
    "scheduler": "simple",
    "dual_model": False,  # 5B is a single dense model, NOT MoE
    "clip_lengths": {
        "short":  {"frames": 33, "seconds": 1.4},
        "medium": {"frames": 49, "seconds": 2.0},
        "long":   {"frames": 81, "seconds": 3.4},
    },
    "quality_steps": {"draft": 10, "good": 20, "final": 30},
    "resolutions": {
        "480p": {
            "width": 832, "height": 480, "shift": 12.0,
            "t2v_unet": "wan2.2_ti2v_5B.safetensors",  # Single model handles both T2V and I2V
            "i2v_unet": "wan2.2_ti2v_5B.safetensors",
            "min_vram_gb": 8, "label": "480p (832×480)",
        },
    },
    "text_encoders": {
        "clip1": "umt5-xxl-encoder-Q8_0.gguf",
        "clip_type": "wan",
    },
    "vae": "wan2.2_vae.safetensors",  # New high-compression VAE
    "clip_vision": "sigclip_vision_patch14_384.safetensors",
    "lora_loader": "LoraLoaderModelOnly",
}
```

**Also:** Add non-MoE workflow builder (single sampler pass, no `SplitSigmas`).

**Files to modify:**
- `scripts/showrunner.py` — add `wan_5b` config + single-model workflow builder
- `app/backend/pipeline.py` — pass model choice through to showrunner
- CLI: `--video-model wan_5b` option

---

### Phase 3: Wan 2.2 VAE Upgrade

**Problem:** Config references `Wan2.1_VAE.pth`. Wan 2.2 ships a new VAE with 16×16×4 compression ratio (64× total) — more efficient, faster, lower VRAM.

**Fix:**
1. Download `wan2.2_vae.safetensors` from `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` or `Wan-AI/Wan2.2-TI2V-5B`
2. Update `wan` config in `showrunner.py`: `"vae": "wan2.2_vae.safetensors"`
3. Note: The 5B TI2V model was specifically designed for this new VAE — the 14B MoE models also benefit from it

**Files to modify:**
- `scripts/showrunner.py` — update VAE reference in `wan` config
- Model download scripts — add Wan 2.2 VAE download

---

### Phase 4: Scene-Type Routing

**Problem:** All scenes use the same generation path (T2V for first, I2V chain for rest). Dialogue, action, and establishing shots have very different requirements.

**Fix:**

1. **Update Claude prompt** in `showrunner.py` episode generation to output scene types:
```json
{
    "scene_number": 3,
    "type": "dialogue",  // dialogue | action | establishing | transition
    "speaker": "char_1",
    "clip_length": "medium",
    "visual": "Close-up of Jack speaking...",
    "dialogue": "The city never sleeps, and neither do I.",
    "emotion": "weary, determined"
}
```

2. **Route by scene type** in the production loop:
```python
if scene["type"] == "dialogue" and s2v_available:
    # Generate TTS first, then S2V with audio input
    generate_dialogue_scene_s2v(scene, character_ref, audio)
elif scene["type"] == "establishing":
    # T2V only — no character reference needed
    generate_establishing_scene(scene)
else:
    # Standard I2V with character LoRA
    generate_action_scene(scene, seed_image, loras)
```

3. **Update `build_scene_prompt()`** to adjust prompt style per scene type

**Files to modify:**
- `scripts/showrunner.py` — Claude episode prompt, production loop, prompt builder
- `app/backend/models.py` — add `scene_type` field to Scene model
- `app/backend/schemas.py` — add scene type to schema
- `app/frontend/src/components/EpisodesTab.jsx` — display scene type badges

---

### Phase 5: S2V (Speech-to-Video) Integration

**Problem:** Dialogue scenes have no lip sync. Audio is generated separately and muxed onto silent video.

**Wan2.2-S2V-14B capabilities:**
- Takes: character image + audio file + text prompt
- Outputs: video with natural lip sync, facial expressions, body language
- Supports: dialogue, singing, performance
- Full-body and half-body framing
- Camera movement via text prompt

**Implementation:**

1. **Add S2V model config** — S2V uses its own model weights (`Wan-AI/Wan2.2-S2V-14B`)

2. **Add S2V workflow builder** — `build_wan_s2v_workflow()`:
   - Input: character reference image + audio file + text prompt
   - Audio encoding via CosyVoice or direct WAV input
   - Output: video with synced lip movement

3. **Update production loop:**
   - For dialogue scenes: generate TTS audio first → feed to S2V with character portrait
   - For non-dialogue: use existing I2V pipeline
   - Skip separate audio mux step for S2V scenes (audio is baked in)

4. **ComfyUI requirements:**
   - Kijai's `ComfyUI-WanVideoWrapper` recommended (has S2V support ahead of native nodes)
   - S2V model weights: ~14B parameters, needs 24GB+ VRAM (RunPod only)

**Files to modify:**
- `scripts/showrunner.py` — add S2V workflow builder + production routing
- `app/backend/pipeline.py` — S2V scene handling
- Model download scripts — add S2V model download

**Hardware:** S2V is RunPod-only (A6000 48GB recommended). Local preview would still use standard I2V + separate audio.

---

### Phase 6: Wan-Animate Integration (Optional / Advanced)

**What it does:** Given a character image + reference performance video → generates your character performing the same motion with expression replication.

**Use cases:**
- Complex choreographed action (fight scenes, dance)
- Two-character interaction (film each separately with reference motion)
- Consistent body language across episodes

**Two modes:**
- **Character Animation:** Animate character with performer's motion
- **Character Replacement:** Replace person in existing video, matching lighting/tone

**Requirements:**
- Model: `Wan-AI/Wan2.2-Animate-14B`
- Skeleton extraction for motion control
- Implicit facial features for expression
- Optional Relighting LoRA for environment matching
- 24GB+ VRAM

**Implementation is more complex** — requires skeleton signal processing and facial feature extraction. Recommend doing this after S2V is stable.

---

### Phase 7: Captioning Best Practices

**Problem:** Florence-2 auto-captioner describes everything in the image, including character features. Research from Civitai shows this hurts LoRA training because the model can't learn the diff.

**Fix:** Update `auto_caption.py` to:
1. Accept a `--character-features` flag listing what NOT to describe (e.g., "red hair, blue eyes, leather jacket")
2. Post-process Florence-2 captions to strip character-feature sentences
3. Or switch to a two-pass approach:
   - Pass 1: Florence-2 generates full caption
   - Pass 2: LLM (Claude or local) rewrites caption following LoRA rules — describes background/environment in detail, uses trigger word for character, omits character visual features

**Captioning template:**
```
[trigger_word] [pose/action]. [Background: detailed description of environment,
lighting, colors, objects]. [Camera: angle, movement]. [Style: aesthetic notes].
```

**Example:**
```
ohwx_jack standing with hands in pockets, looking left. Rainy street at night,
neon signs reflecting off wet cobblestones, steam rising from a grate, parked
cars with fogged windows. Medium shot, slight low angle. Film noir, high
contrast, moody blue-orange color grade.
```

**Files to modify:**
- `scripts/auto_caption.py` — add character-aware mode
- `training/scripts/prepare_dataset.sh` — pass character features to captioner

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

1. **Phase 1** — Fix LoRA training target (critical bug, blocks all LoRA work)
2. **Phase 2** — TI2V-5B local preview (quick win, unblocks local iteration)
3. **Phase 3** — Wan 2.2 VAE (quick config change, better performance)
4. **Phase 4** — Scene-type routing (structural improvement, enables Phase 5)
5. **Phase 5** — S2V integration (biggest quality leap for dialogue)
6. **Phase 7** — Captioning best practices (improves LoRA quality)
7. **Phase 6** — Wan-Animate (advanced, do last)
