# Wan 2.2 — Animated Series Production Research

## Executive Summary

Wan 2.2 (released July 28, 2025 by Alibaba/Tongyi Wanxiang) is a major upgrade over HunyuanVideo for your use case. It offers better motion quality, cinematic aesthetics, native LoRA support, and — critically — **Wan-Animate** and **Wan-S2V** models specifically designed for character animation and audio-driven dialogue. For a 2-character animated series with 5–6 second clips, this is the current state-of-the-art open-source option.

---

## 1. Model Overview

### What's New in 2.2 vs 2.1 vs HunyuanVideo

| Feature | HunyuanVideo 1.5 (current) | Wan 2.1 | Wan 2.2 |
|---------|---------------------------|---------|---------|
| Architecture | DiT | DiT | **MoE DiT** (27B total, 14B active) |
| Resolution | 480×320 (8GB) | 480p–720p | **720p @ 24fps** |
| VAE compression | Standard | Standard | **16×16×4 (64× total)** — much more efficient |
| Character consistency | Manual I2V chaining | VACE model (good) | **Animate-14B + LoRA** (excellent) |
| Audio/dialogue | None (Edge-TTS bolted on) | None | **S2V-14B** (native speech-to-video) |
| LoRA support | Via musubi-tuner | Yes | **Native, MoE-aware** |
| Motion quality | Decent at low res | Good | **Significantly better** (+83% more training video) |
| License | Open | Apache 2.0 | Apache 2.0 |

### Available Models

| Model | Params | Purpose | Min VRAM |
|-------|--------|---------|----------|
| **Wan2.2-TI2V-5B** | 5B | Hybrid text+image to video | **8GB** (runs on your 4070!) |
| **Wan2.2-T2V-A14B** | 14B MoE | Text to video (highest quality) | 16–24GB |
| **Wan2.2-I2V-A14B** | 14B MoE | Image to video | 16–24GB |
| **Wan2.2-Animate-14B** | 14B | Character animation/replacement | 24GB+ |
| **Wan2.2-S2V-14B** | 14B | Speech/audio-driven video | 24GB+ |

---

## 2. Architecture for Your Animated Series

### The Pipeline (Replacing HunyuanVideo)

```
concept.json + character reference images (YOU CREATE)
        │
        ▼
   Claude API → bible + episode scripts (KEEP AS-IS)
        │
        ▼
   ┌──────────────────────────────────────────────────────┐
   │  Character Setup (ONE-TIME):                         │
   │                                                      │
   │  1. Generate character sheets (multiple angles/poses) │
   │     using FLUX/SDXL or Wan VACE                      │
   │  2. Train LoRA per character (Char A + Char B)       │
   │  3. Optionally train style LoRA for series look      │
   └──────────────────────────────────────────────────────┘
        │
        ▼
   ┌──────────────────────────────────────────────────────┐
   │  Per Episode Scene Generation:                       │
   │                                                      │
   │  For DIALOGUE scenes:                                │
   │    Reference image + TTS audio                       │
   │         → Wan2.2-S2V-14B                             │
   │         → Character speaks with lip sync!            │
   │                                                      │
   │  For ACTION scenes:                                  │
   │    Reference image + text prompt                     │
   │         → Wan2.2-I2V-A14B (with character LoRA)      │
   │         → I2V chain (last frame → next clip)         │
   │                                                      │
   │  For CHARACTER ANIMATION:                            │
   │    Character image + motion reference video          │
   │         → Wan2.2-Animate-14B                         │
   │         → Character moves like reference performer   │
   │                                                      │
   │  FFmpeg → stitch clips + final audio                 │
   │         → ep01_final.mp4                             │
   └──────────────────────────────────────────────────────┘
```

### Key Advantage: Three Generation Modes

Your current pipeline only has one mode (I2V chaining). Wan 2.2 gives you three:

1. **I2V + LoRA** — Standard scenes. Character reference image → animated clip. LoRA keeps characters consistent.
2. **S2V (Speech-to-Video)** — Dialogue scenes. Feed audio + character image → character speaks with natural lip sync, expressions, body language. No more bolting TTS audio onto silent video.
3. **Animate** — Complex motion scenes. Record yourself (or any reference video) performing the action → your animated character replicates the motion with their appearance preserved.

---

## 3. Character Consistency Strategy

This is the hardest problem in AI animation. Here's the multi-layered approach:

### Layer 1: Character LoRA Training

**The most important step.** Train a dedicated LoRA for each of your 2 characters.

**Dataset preparation:**
- Generate 20–50 images of each character in varied poses, angles, expressions
- Use Wan 2.1 VACE to generate character rotation videos, then extract good frames
- Alternatively, use FLUX/SDXL to generate consistent character sheets
- Caption carefully — describe background/environment in detail, but DON'T over-describe the character features the LoRA should learn (counterintuitive but proven)

**Training best practices (from community testing):**
- Start at **low resolution** (128×128 or 256×256) to validate learning
- Use **10–20 videos/images** per training batch
- Train one thing at a time (one angle, one outfit, etc.)
- Build the LoRA piece by piece — you can enhance a working LoRA with new data
- Standardize framerate across training data
- Start with higher learning rate (5e-5 or 1e-4), reduce as you finetune
- Use musubi-tuner or community Wan LoRA training scripts
- LoRA rank 32 for simple characters, 64 for complex ones
- Don't train above 256×256 — the model hallucinates fine details at inference time

**Captioning rules (critical):**
```
WRONG: "A girl with cat ears, blue eyes, pink hair, wearing a red dress"
        (too much character detail = LoRA can't learn the diff)

RIGHT: "ohwx girl. She is standing in a hospital break room with grey floors 
        and white walls. She is smiling and waving. Realistic lighting."
        (trigger word + describe everything EXCEPT what LoRA should learn)
```

### Layer 2: I2V Chaining (Scene Continuity)

Same principle as your current HunyuanVideo pipeline:
- Last frame of clip N → reference image for clip N+1
- Maintains visual continuity within a scene
- LoRA ensures character appearance stays consistent even when chaining

### Layer 3: Series Bible in Prompts

Keep injecting the series bible (character descriptions, style string, location details) into every generation prompt. This is additive to the LoRA — belt and suspenders.

### Layer 4: Wan-Animate for Complex Scenes

When you need both characters interacting:
- Record reference motion (even with stick figures or yourself)
- Use Animate-14B to transfer that motion onto your character
- Particularly useful for: fight scenes, dance sequences, physical comedy

---

## 4. Hardware Strategy

### Option A: Local (Your RTX 4070 Laptop, 8GB VRAM)

**What works:**
- Wan2.2-TI2V-5B — the hybrid 5B model fits in 8GB with ComfyUI native offloading
- 480p resolution, ~5 seconds per clip
- Good for prototyping, previewing, testing prompts

**What doesn't:**
- 14B models (T2V, I2V, Animate, S2V) won't fit
- No LoRA training locally

### Option B: RunPod (Recommended for Production)

| Task | GPU | Cost/hr | Notes |
|------|-----|---------|-------|
| Episode production (14B) | RTX 4090 24GB | ~$0.40 | Can run I2V-A14B with block swap |
| S2V dialogue scenes | A6000 48GB | ~$0.65 | S2V-14B needs more headroom |
| Animate scenes | A6000 48GB | ~$0.65 | Animate-14B + reference video |
| LoRA training | A6000 48GB | ~$0.65 | 2-6 hours per character |
| Fast everything | A100 80GB | ~$1.50 | No VRAM constraints |

**Recommended workflow:**
1. Write scripts + plan scenes locally (Claude API, free)
2. Generate preview clips locally with TI2V-5B (free, 8GB)
3. Spin up RunPod for final production with 14B models
4. Cost per episode: roughly $2-5 depending on scene count

### Option C: Hybrid (Best Value)

- Use TI2V-5B locally for iteration and previews
- Use RunPod for final 720p renders with 14B + LoRA
- Use fp8 quantized models (from Kijai) to squeeze 14B into 24GB

---

## 5. ComfyUI Integration

### Two ComfyUI Options

1. **Native ComfyUI nodes** — Official Wan 2.2 support built into ComfyUI core
   - Stable, well-tested
   - Good for standard T2V and I2V workflows

2. **Kijai's ComfyUI-WanVideoWrapper** — Community wrapper (recommended)
   - Gets cutting-edge features first (Animate, S2V, VACE)
   - Better VRAM optimization (block swapping, fp8 scaled)
   - LoRA support with async prefetching
   - Supports GGUF quantized models
   - More active development

### Key ComfyUI Workflows You'd Need

1. **I2V + LoRA** — Base scene generation
2. **S2V** — Dialogue scenes with lip sync
3. **Animate** — Motion transfer scenes
4. **VACE** — Inpainting/editing existing clips (fix consistency issues)

### Model Files

From Kijai's fp8 scaled repo (recommended for 24GB GPUs):
- `wan2.2_t2v_a14b_fp8_scaled.safetensors` — T2V
- `wan2.2_i2v_a14b_fp8_scaled.safetensors` — I2V
- Text encoder: `umt5_xxl_fp16.safetensors`
- VAE: `wan_2.2_vae.safetensors` (new high-compression VAE)
- CLIP Vision: as needed for I2V

---

## 6. Speech-to-Video (S2V) — Game Changer for Dialogue

This is the biggest upgrade over your current pipeline. Currently you:
1. Generate silent video clips
2. Generate TTS audio separately
3. Mux them together (no lip sync, no expression matching)

With Wan2.2-S2V-14B:
1. Generate TTS audio (Edge-TTS or CosyVoice)
2. Feed audio + character image + text prompt → S2V generates video WITH lip sync
3. Character naturally speaks, emotes, and moves in response to the audio

**Capabilities:**
- Natural lip sync to input audio
- Facial expressions matching emotional tone
- Body language (gestures, posture shifts)
- Supports full-body and half-body framing
- Can handle dialogue, singing, and performance
- Camera movement control via text prompt
- CosyVoice integration for TTS → S2V pipeline

**For your 2-character series:** Generate each character's dialogue clips separately with S2V, then composite/edit them together. Or use shot-reverse-shot editing (standard animation technique).

---

## 7. Wan-Animate — Motion Transfer

**Use case:** You want a character to perform a specific action (running, fighting, dancing).

**How it works:**
1. Provide a character reference image
2. Provide a "performer" video (can be you, an actor, or any reference)
3. Animate-14B transfers the performer's motion onto your character
4. Preserves character appearance while replicating movement + expressions

**Two modes:**
- **Character Animation:** Animate your character with performer's motion
- **Character Replacement:** Replace the person in an existing video with your character, matching lighting/color tone

**For your series:** This is perfect for complex action scenes. Film a quick reference clip on your phone → your animated characters perform the same actions.

---

## 8. Recommended Pipeline Architecture

### Modified showrunner.py Flow

```python
# Per scene, choose generation mode based on scene type:

if scene.type == "dialogue":
    # 1. Generate TTS audio (Edge-TTS or CosyVoice)
    # 2. Feed to Wan2.2-S2V-14B with character LoRA
    # → Lip-synced character video
    
elif scene.type == "action":
    # 1. Use reference image (or last frame of previous clip)
    # 2. Feed to Wan2.2-I2V-A14B with character LoRA  
    # 3. Chain clips for longer sequences
    # → Action video with consistent character
    
elif scene.type == "complex_motion":
    # 1. Use pre-recorded motion reference
    # 2. Feed to Wan2.2-Animate-14B
    # → Character performing specific choreographed motion

elif scene.type == "establishing":
    # 1. Text prompt only (no character needed)
    # 2. Feed to Wan2.2-T2V-A14B
    # → Environment/setting shot
```

### Scene Type Tags in Episode Scripts

Update Claude's episode generation to tag each scene:

```json
{
  "scene_number": 3,
  "type": "dialogue",           // NEW: dialogue|action|complex_motion|establishing
  "speaker": "character_a",     // NEW: which character speaks
  "duration": "medium",
  "visual_prompt": "Close-up of Hana speaking gently...",
  "dialogue": "The garden remembers everyone who cares for it.",
  "emotion": "warm, contemplative"
}
```

---

## 9. Clip Duration — 5-6 Seconds

Your target of 5–6 seconds per scene aligns well with Wan 2.2:

| Model | Resolution | 5 sec clip | Frames | Gen time (4090) |
|-------|-----------|------------|--------|-----------------|
| TI2V-5B | 480p | ✅ | ~120 @ 24fps | ~4 min |
| TI2V-5B | 720p | ✅ | ~120 @ 24fps | ~9 min |
| I2V-A14B | 720p | ✅ | ~120 @ 24fps | ~8-12 min |
| T2V-A14B | 720p | ✅ | ~120 @ 24fps | ~9 min |

Compared to your current HunyuanVideo setup (max 3.4s at 480×320), this is a massive upgrade in both duration and resolution.

---

## 10. Step-by-Step Implementation Plan

### Phase 1: Character Setup (Day 1-2)
1. Design your 2 characters (can use FLUX/SDXL for reference sheets)
2. Generate 30+ reference images per character (varied angles, expressions, poses)
3. Use Wan 2.1 VACE to generate rotation videos for additional training frames
4. Train Character A LoRA (RunPod A6000, ~3-4 hours)
5. Train Character B LoRA (RunPod A6000, ~3-4 hours)
6. Test both LoRAs with simple prompts, iterate if needed

### Phase 2: Pipeline Update (Day 3-5)
1. Update ComfyUI + install Kijai's WanVideoWrapper
2. Download Wan 2.2 models (TI2V-5B for local, A14B for RunPod)
3. Create ComfyUI workflows: I2V+LoRA, S2V, T2V
4. Update `showrunner.py` to support scene types and Wan 2.2 API
5. Update episode script generation (Claude) to output scene type tags
6. Test full pipeline with 1 episode

### Phase 3: Production (Ongoing)
1. Write series concept + bible
2. Generate all episode scripts via Claude
3. Produce episodes: preview locally (5B), final render on RunPod (14B)
4. Iterate on LoRAs as you find consistency issues

### Phase 4: Advanced (When Ready)
1. Add Wan-Animate support for complex scenes
2. Add S2V for dialogue scenes
3. Train style LoRA for consistent visual aesthetic
4. Experiment with CosyVoice for more natural TTS

---

## 11. Key Resources

- **Wan 2.2 repo:** https://github.com/Wan-Video/Wan2.2
- **ComfyUI official workflows:** https://docs.comfy.org/tutorials/video/wan/wan2_2
- **Kijai's WanVideoWrapper (recommended):** https://github.com/kijai/ComfyUI-WanVideoWrapper
- **fp8 quantized models:** https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled
- **Wan-Animate:** https://humanaigc.github.io/wan-animate
- **Wan-S2V:** https://humanaigc.github.io/wan-s2v-webpage
- **LoRA training guide:** https://civitai.com/articles/11942/training-a-wan-or-hunyuan-lora-the-right-way
- **HuggingFace models:** https://huggingface.co/Wan-AI/
- **Diffusers integration:** Available for T2V-A14B, I2V-A14B, TI2V-5B

---

## 12. Comparison: Current Pipeline vs Wan 2.2 Pipeline

| Aspect | Current (HunyuanVideo 1.5) | Proposed (Wan 2.2) |
|--------|---------------------------|-------------------|
| Max resolution | 480×320 | **720p (1280×720)** |
| Max clip length | 3.4s | **5-6s+** |
| Character consistency | I2V chaining only | **LoRA + I2V chaining + Animate** |
| Dialogue/lip sync | None (audio bolted on) | **Native S2V with lip sync** |
| Expressions | Random/prompt-dependent | **Audio-driven + controllable** |
| 2-character interaction | Very difficult | **Animate mode + compositing** |
| Local preview | Yes (8GB) | **Yes (TI2V-5B fits 8GB)** |
| Motion quality | Decent | **Significantly better** |
| Style control | Prompt-only | **LoRA + cinematic aesthetic labels** |
| Cost per episode | ~$2-5 (RunPod) | **Similar, higher quality output** |

---

*Research compiled March 29, 2026. Wan 2.2 ecosystem is actively evolving — check repos for latest updates.*
