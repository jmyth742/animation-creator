#!/usr/bin/env python3
"""
Showrunner — Automated Series Production Pipeline

The full pipeline from concept to finished episodes:
  1. You provide: concept.json + optional reference images
  2. Claude generates: full series bible + all episode scripts
  3. Pipeline generates: video clips with I2V chaining
  4. Edge-TTS generates: voiceover audio per scene
  5. FFmpeg stitches: final episodes with audio

Usage:
    # Create a new series from a concept
    showrunner.py create my_series

    # Generate the bible + all episode scripts via Claude
    showrunner.py write my_series

    # Write a single episode
    showrunner.py write my_series --episode 3

    # Produce an episode (generate video + audio + stitch)
    showrunner.py produce my_series --episode 1

    # Produce with a reference image for visual consistency
    showrunner.py produce my_series --episode 1 --image ref.png

    # Export just the voiceover script
    showrunner.py script my_series --episode 1

    # Produce all episodes in sequence
    showrunner.py produce-all my_series

    # List series status
    showrunner.py status my_series
"""

import argparse
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
SERIES_DIR = ROOT / "series"
OUTPUT_DIR = ROOT / "output"
AMBIENCE_DIR = ROOT / "ambience"
COMFYUI_DIR = ROOT / "ComfyUI"
COMFYUI_INPUT = COMFYUI_DIR / "input"
COMFYUI_OUTPUT = COMFYUI_DIR / "output" / "video"
SERVER = "http://localhost:8188"

# ─── Series-scoped clip output ────────────────────────────────────────
# ComfyUI was told to name every clip after the scene id alone ("ep01_s01")
# and write it into one flat directory. Scene ids are only unique *within*
# a series — every series has an ep01_s01 — so clips from different series
# collided, and find_latest_clip() simply returned whichever was rendered
# most recently. A --resume run of series B could therefore skip a scene
# because series A had already produced a same-named clip, and stitch the
# wrong series' footage into the episode. Clips now live in a per-series
# subdirectory; CURRENT_SERIES is set once from argv in main().
# Thread-local, not a plain global: the FastAPI backend runs each production
# in its own thread, so two concurrent jobs for different projects would
# otherwise overwrite each other's series and file clips under the wrong one.
_series_tls = threading.local()


def set_current_series(series: str | None):
    _series_tls.value = series


def current_series() -> str | None:
    return getattr(_series_tls, "value", None)


def clip_dir(series: str | None = None) -> Path:
    """Directory holding a series' rendered clips."""
    s = series if series is not None else current_series()
    return (COMFYUI_OUTPUT / s) if s else COMFYUI_OUTPUT


def save_prefix(clip_prefix: str) -> str:
    """filename_prefix for ComfyUI's SaveVideo node, scoped to the series."""
    s = current_series()
    return f"video/{s}/{clip_prefix}" if s else f"video/{clip_prefix}"

# ─── Step-distilled (Lightning) sampling ──────────────────────────────
# LightX2V's distilled LoRAs collapse WAN 2.2's two-stage sampling to a
# handful of steps. Measured on this box at 49 frames / 480x832:
#   18 steps, cfg 5.0, no LoRA -> 490s   (and the shot came out smeared)
#    4 steps, cfg 1.0, LoRA    ->  80s
#    8 steps, cfg 1.0, LoRA    -> 120s   (quality clearly better than base)
# CFG MUST drop to ~1.0: left at 5.0 the distilled model burns out and it
# looks like the LoRA is broken rather than the guidance being wrong.
# ─── Strict mode ──────────────────────────────────────────────────────
# Every path in this file used to warn and continue, so a wrong configuration
# and a right one produced the same exit code and the same "JOB COMPLETE".
# ~20 real defects reached finished episodes that way and not one crashed:
# a LoRA that did nothing, a seed that fell through to the previous shot, a
# narration that would not fit. Each cost a 2.5-hour render to discover.
#
# Under strict mode those specific conditions abort at the offending shot.
# jobctl checkpoints completed shots, so a resume after the fix skips the work
# already done -- aborting early is cheaper than finishing wrong.
#
# Advisory warnings (recoverable state, missing optional binaries) are NOT
# promoted; only conditions where the OUTPUT WILL BE WRONG.
STRICT = True


class PipelineError(RuntimeError):
    """A condition that makes the render wrong rather than merely imperfect."""


def fatal(msg: str, hint: str = ""):
    """Abort under strict mode; warn and carry on when it is off."""
    if STRICT:
        raise PipelineError(msg + (f"\n         {hint}" if hint else ""))
    print(f"    WARNING: {msg}")


LIGHTNING = {
    "steps": 8,
    "cfg": 1.0,
    "sampler": "euler",
    "scheduler": "simple",
    # Base names: _resolve_wan_dual_loras() expands these to the -high/-low
    # files and hands each expert its matching variant.
    "t2v": [("lightning-t2v.safetensors", 1.0)],
    "i2v": [("lightning-i2v.safetensors", 1.0)],
}


def apply_lightning(wf: dict, steps: int | None = None):
    """Patch a built workflow for distilled sampling (low cfg, few steps)."""
    st = steps or LIGHTNING["steps"]
    for v in wf.values():
        if v.get("class_type") in ("KSampler", "KSamplerAdvanced"):
            i = v["inputs"]
            i["cfg"] = LIGHTNING["cfg"]
            i["sampler_name"] = LIGHTNING["sampler"]
            i["scheduler"] = LIGHTNING["scheduler"]
            if "steps" in i:
                i["steps"] = st
            # The dual-model I2V handoff is steps//2: the high-noise expert
            # runs 0 -> mid and the low-noise expert mid -> 10000. Move the
            # handoff to the new midpoint; leave the open-ended 10000 alone.
            if "end_at_step" in i and i["end_at_step"] != 10000:
                i["end_at_step"] = max(1, st // 2)
            if i.get("start_at_step", 0) > 0:
                i["start_at_step"] = max(1, st // 2)
    return wf


# ─── Claude (script writing) ──────────────────────────────────────────
# The writing model is the single biggest lever on story quality — it writes
# the series bible and every episode script. Override per-run if needed:
#   SHOWRUNNER_CLAUDE_MODEL=claude-sonnet-5 python scripts/showrunner.py write ...
CLAUDE_MODEL = os.environ.get("SHOWRUNNER_CLAUDE_MODEL", "claude-opus-5")
# Effort controls how hard the model thinks. "high" is the default; "max" buys
# noticeably better long-form structure on season arcs at higher cost.
CLAUDE_EFFORT = os.environ.get("SHOWRUNNER_CLAUDE_EFFORT", "high")


# ─── Model configurations ────────────────────────────────────────────
# WAN 2.2 is the sole video generation model.

MODEL_CONFIGS = {
    "wan": {
        "label": "WAN 2.2 (A14B dual-model I2V + single-model T2V)",
        "fps": 16,
        "cfg": 5.0,
        "i2v_cfg": 3.5,          # Official WAN 2.2 I2V guidance (lower than T2V)
        "sampler": "uni_pc_bh2",
        "i2v_sampler": "euler",   # Official WAN 2.2 I2V sampler
        "scheduler": "simple",
        "dual_model": False,      # T2V: single high-noise model (dual caused mosaic artifacts)
        "i2v_dual_model": True,   # I2V: dual-model KSamplerAdvanced (official workflow)
        "clip_lengths": {
            "short":  {"frames": 33, "seconds": 2.1},
            "medium": {"frames": 49, "seconds": 3.1},
            "long":   {"frames": 81, "seconds": 5.1},
        },
        "quality_steps": {"draft": 15, "good": 25, "final": 40},
        "resolutions": {
            "480p": {
                "width": 832, "height": 480,
                "shift": 12.0,        # T2V shift
                "i2v_shift": 8.0,     # I2V shift (official WAN 2.2 value)
                "t2v_unet": "wan2.2_t2v_high_noise_14B_Q8_0.gguf",
                "t2v_unet_low": "wan2.2_t2v_low_noise_14B_Q8_0.gguf",
                "i2v_unet": "wan2.2_i2v_high_noise_14B_Q4_K_S.gguf",
                "i2v_unet_low": "wan2.2_i2v_low_noise_14B_Q4_K_S.gguf",
                # Speech-to-video is a SEPARATE checkpoint. The S2V workflow
                # used to load the T2V UNet, which cannot interpret the audio
                # conditioning at all -- it would have generated video that
                # simply ignored the voice track, with no lip sync and no error.
                "s2v_unet": "Wan2.2-S2V-14B-Q5_K_M.gguf",
                "min_vram_gb": 12, "label": "480p (832×480)",
            },
            "720p": {
                "width": 1280, "height": 720,
                "shift": 12.0,
                "i2v_shift": 8.0,
                "t2v_unet": "wan2.2_t2v_high_noise_14B_Q8_0.gguf",
                "t2v_unet_low": "wan2.2_t2v_low_noise_14B_Q8_0.gguf",
                "i2v_unet": "wan2.2_i2v_high_noise_14B_Q4_K_S.gguf",
                "i2v_unet_low": "wan2.2_i2v_low_noise_14B_Q4_K_S.gguf",
                # The S2V checkpoint is not resolution-specific; the 480p entry had it
                # and this one did not, so any 720p dialogue shot aborted.
                "s2v_unet": "Wan2.2-S2V-14B-Q5_K_M.gguf",
                "min_vram_gb": 24, "label": "720p (1280×720)",
            },
        },
        "text_encoders": {
            "clip1": "umt5-xxl-encoder-Q8_0.gguf",
            "clip_type": "wan",
        },
        "vae": "Wan2.1_VAE.pth",
        "clip_vision": "sigclip_vision_patch14_384.safetensors",
        "lora_loader": "LoraLoaderModelOnly",
    },
    "wan-5b": {
        "label": "WAN 2.2 TI2V-5B (local preview)",
        "fps": 16,
        "cfg": 5.0,
        "sampler": "uni_pc_bh2",
        "scheduler": "simple",
        "dual_model": False,  # 5B is a single model
        "clip_lengths": {
            "short":  {"frames": 33, "seconds": 2.1},
            "medium": {"frames": 49, "seconds": 3.1},
            "long":   {"frames": 81, "seconds": 5.1},
        },
        "quality_steps": {"draft": 10, "good": 20, "final": 30},
        "resolutions": {
            "480p": {
                "width": 832, "height": 480, "shift": 5.0,
                "t2v_unet": "wan2.2_ti2v_5B_Q4_K_S.gguf",
                "i2v_unet": "wan2.2_ti2v_5B_Q4_K_S.gguf",
                "min_vram_gb": 8, "label": "480p (832×480)",
            },
        },
        "text_encoders": {
            "clip1": "umt5-xxl-encoder-Q8_0.gguf",
            "clip_type": "wan",
        },
        "vae": "Wan2.1_VAE.pth",
        "clip_vision": "sigclip_vision_patch14_384.safetensors",
        "lora_loader": "LoraLoaderModelOnly",
    },
}
DEFAULT_VIDEO_MODEL = "wan"

# ─── Optimization presets ────────────────────────────────────────────
# EasyCache (TeaCache) skips redundant diffusion steps by reusing cached
# intermediate results when the change rate is below a threshold.
# Lower threshold = more aggressive caching = faster but lower quality.

OPTIMIZATION_PRESETS = {
    "none": {
        "label": "No optimization",
        "easycache": None,
    },
    "balanced": {
        "label": "Balanced (EasyCache 0.15)",
        "easycache": {"reuse_threshold": 0.15, "start_percent": 0.0, "end_percent": 0.85},
    },
    "fast": {
        "label": "Fast (EasyCache 0.25)",
        "easycache": {"reuse_threshold": 0.25, "start_percent": 0.0, "end_percent": 0.90},
    },
    "turbo": {
        "label": "Turbo (EasyCache 0.40)",
        "easycache": {"reuse_threshold": 0.40, "start_percent": 0.0, "end_percent": 0.95},
    },
}

# Inference quality presets
QUALITY_STEPS = MODEL_CONFIGS["wan"]["quality_steps"]

# Clip length presets
CLIP_LENGTHS = MODEL_CONFIGS["wan"]["clip_lengths"]

# I2V denoise presets — lower = closer to reference image
DENOISE_PRESETS = {
    "faithful": 0.70,
    "balanced": 0.82,
    "creative": 1.0,
}
DEFAULT_DENOISE = 0.82


def detect_vram_gb() -> float:
    """Query ComfyUI system info for available GPU VRAM in GB."""
    try:
        r = requests.get(f"{SERVER}/system_stats", timeout=5)
        if r.status_code == 200:
            data = r.json()
            devices = data.get("devices", [])
            if devices:
                vram = devices[0].get("vram_total", 0)
                return vram / (1024 ** 3)
    except Exception:
        pass
    return 0.0


def get_model_config(video_model: str = DEFAULT_VIDEO_MODEL) -> dict:
    """Get the full configuration dict for a video model."""
    return MODEL_CONFIGS.get(video_model, MODEL_CONFIGS[DEFAULT_VIDEO_MODEL])


def get_resolution_config(resolution: str | None = None, video_model: str = DEFAULT_VIDEO_MODEL) -> dict:
    """Get resolution configuration, auto-detecting VRAM if resolution is 'auto'."""
    mc = get_model_config(video_model)
    resolutions = mc["resolutions"]

    if resolution == "auto" or resolution is None:
        vram = detect_vram_gb()
        resolution = "720p" if vram >= 24 else "480p"

    return resolutions.get(resolution, list(resolutions.values())[0])


# Frame count constraints (must be 4n+1 for WAN 2.2)
MIN_FRAMES = 33   # ~1.4s at 24fps / ~2.1s at 16fps
MAX_FRAMES = 97   # ~4.0s at 24fps / ~6.1s at 16fps


def frames_for_duration(seconds: float, fps: int = 24) -> int:
    """Compute the nearest valid frame count (4n+1) for a given duration.

    WAN 2.2 requires frame counts of the form 4n+1.
    Returns the closest valid count within MIN_FRAMES..MAX_FRAMES, with a small
    buffer (+0.3s) to ensure audio fits comfortably within the clip.
    """
    target = int(round((seconds + 0.3) * fps))
    n = round((target - 1) / 4)
    frames = 4 * n + 1
    return max(MIN_FRAMES, min(MAX_FRAMES, frames))


# A single S2V sample cannot exceed MAX_FRAMES, so every shot was capped at
# ~5.1s and the episode cut every 3 seconds on average. Real animation holds a
# shot for 8-15s. WanSoundImageToVideoExtend continues a take from the previous
# chunk's sampled latent with the audio window advanced, so chunks chain into
# one continuous shot. Measured over a 15s line: identity did not decay across
# the joins (drift +0.010 over two chunks vs +0.021 within one).
S2V_CHUNK_FRAMES = 81          # 5.06s at 16fps; the length the pair was tuned at
MAX_S2V_CHUNKS = 3             # 15.19s. All three depths rendered and scored
                               # against the character anchor:
                               #   1 chunk   5.06s  drift +0.021
                               #   2 chunks 10.12s  drift +0.010
                               #   3 chunks 15.19s  drift +0.015
                               # Identity does not decay across the joins. Raise
                               # this further only after rendering and scoring
                               # that depth -- selftest asserts the cap never
                               # exceeds what exists on disk.


def pad_audio_to(path: str, seconds: float, out_path: str) -> str:
    """Extend `path` with real silence so it lasts exactly `seconds`.

    S2V drives the mouth from wav2vec2 features over the audio it is given. A
    shot held longer than its line handed the model 22-36% of a take with NO
    audio covering it, and the mouth kept moving through the silence -- the
    character mouthing words after the line had ended. The air that makes a
    piece breathe is precisely where this shows, so holding shots made it
    worse, not better.

    Padding with actual silence gives the encoder something truthful to read
    for the tail, and the mouth closes. Padding is appended, never prepended,
    so nothing shifts against the picture.
    """
    dur = _get_video_duration(path)
    if dur <= 0 or seconds <= dur + 0.02:
        return path
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", path,
         "-af", f"apad=whole_dur={seconds:.3f}",
         "-t", f"{seconds:.3f}", out_path], check=True)
    return out_path


def s2v_chunks_for_duration(seconds: float, fps: int = 16,
                            floor_seconds: float | None = None
                            ) -> tuple[int, int, int | None]:
    """How to build a take: (frames_per_chunk, extra_chunks, last_chunk_frames).

    `seconds` is the intended PICTURE duration and is treated as exact -- it is
    an authored beat. `floor_seconds` is speech that must fit, and gets a small
    safety buffer, because running out of picture mid-word is unrecoverable
    while a fraction of a second of extra hold is invisible.

    Rounding the last chunk UP unconditionally was wrong in both directions: a
    10.0s hold needs 160 frames, two chunks give 162, but ceiling division
    demanded a third chunk for the missing 2 frames and MIN_FRAMES then padded
    that chunk to 33 -- a 10-second beat came out at 12.19s and cost an entire
    extra sampling pass. Enumerate what is actually reachable and take the
    nearest instead.

    extra_chunks == 0 is an ordinary single-sample shot, so a series that never
    needs a long take builds exactly the graph it built before.
    """
    # A caller that passes only one number means "cover this" -- defaulting the
    # floor to it keeps a bare call safe, so the two-argument form can never
    # quietly build less picture than it was asked for.
    if floor_seconds is None:
        floor_seconds = seconds
    need = int(math.ceil((floor_seconds + 0.25) * fps))
    target = max(int(round(seconds * fps)), need)

    def _valid(lo, hi):
        return [f for f in range(lo, hi + 1) if f % 4 == 1]

    best = None
    for n in range(1, MAX_S2V_CHUNKS + 1):
        if n == 1:
            options = [(f, 0, None) for f in _valid(MIN_FRAMES, MAX_FRAMES)]
        else:
            base = S2V_CHUNK_FRAMES * (n - 1)
            options = [(S2V_CHUNK_FRAMES, n - 1, t)
                       for t in _valid(MIN_FRAMES, S2V_CHUNK_FRAMES)]
        for frames, extra, tail in options:
            total = (extra * frames + (tail if tail is not None else frames))
            if total < need:
                continue
            # Nearest to the authored length; on a tie prefer the longer take,
            # so an authored beat is never quietly shortened.
            key = (abs(total - target), -total, extra)
            if best is None or key < best[0]:
                best = (key, (frames, extra, tail))
    if best is None:                     # longer than the cap can reach
        return S2V_CHUNK_FRAMES, MAX_S2V_CHUNKS - 1, S2V_CHUNK_FRAMES
    return best[1]

# ─── Ambient audio system ─────────────────────────────────────────────
#
# Each location type maps to an FFmpeg filter chain that synthesises a
# 60-second ambient loop saved to ambience/<type>.mp3.
# Replace any file with a real recording and it will be used automatically.

AMBIENT_PRESETS: dict[str, dict] = {
    # ── Outdoor/natural beds. The original library was written for the
    # Belfast series (pub, prison, factory), so any non-urban story fell
    # through to city rain.
    "sea_waves": {
        "desc": "Atlantic surf on rock, slow swell, open air",
        "filter": ("anoisesrc=r=44100:c=white:a=0.5,lowpass=f=1200,highpass=f=80,"
                   "tremolo=f=0.12:d=0.65,aecho=0.6:0.5:120:0.3,volume=0.32"),
    },
    "sea_storm": {
        "desc": "Storm sea: heavy breaking waves and wind",
        "filter": ("anoisesrc=r=44100:c=white:a=0.65,lowpass=f=2200,highpass=f=70,"
                   "tremolo=f=0.18:d=0.6,aecho=0.6:0.5:90:0.3,volume=0.38"),
    },
    "wind_moor": {
        "desc": "Open moorland wind over grass, desolate, no traffic",
        "filter": ("anoisesrc=r=44100:c=pink:a=0.35,lowpass=f=900,highpass=f=60,"
                   "tremolo=f=0.1:d=0.5,volume=0.24"),
    },
    "waterfall": {
        "desc": "Falling water into a pool, steady broadband",
        "filter": ("anoisesrc=r=44100:c=white:a=0.5,lowpass=f=4000,highpass=f=250,"
                   "aecho=0.4:0.4:70:0.2,volume=0.28"),
    },
    "meadow": {
        "desc": "Still sunlit meadow, faint breeze",
        "filter": ("anoisesrc=r=44100:c=pink:a=0.2,lowpass=f=1200,highpass=f=120,"
                   "tremolo=f=0.1:d=0.4,volume=0.16"),
    },
    "street_rain": {
        "desc": "Rain on Belfast cobblestones, distant traffic, wet streets",
        # Heavy rain texture (white noise shaped) + low rumble (pink) + faint echo
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.55,lowpass=f=1800,highpass=f=150,"
            "aecho=0.5:0.5:60:0.25,"        # slight reverb for open-air feel
            "volume=0.38"
        ),
    },
    "interior_quiet": {
        "desc": "Quiet Belfast terraced house, faint street sounds from outside",
        "filter": (
            "anoisesrc=r=44100:c=pink:a=0.18,lowpass=f=500,highpass=f=60,"
            "aecho=0.3:0.4:80:0.15,"
            "volume=0.18"
        ),
    },
    "military": {
        "desc": "Army Land Rover engine idle, radio static, boots on tarmac",
        # Mid-frequency band (engine/radio range) + crackle texture
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.4,"
            "bandpass=f=1800:width_type=h:w=2500,"
            "aecho=0.2:0.3:30:0.12,"
            "volume=0.28"
        ),
    },
    "factory": {
        "desc": "Derelict factory: wind through broken windows, pigeons, creaking metal",
        # Deep low-frequency rumble + thin high whistle (wind)
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.45,lowpass=f=400,highpass=f=40,"
            "aecho=0.6:0.5:120:0.35,"       # large reverberant space
            "volume=0.30"
        ),
    },
    "crowd_protest": {
        "desc": "Derry street crowd, chanting, distant voices, tension in the air",
        # Mid-band noise shaped like crowd murmur
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.50,"
            "bandpass=f=700:width_type=h:w=1400,"
            "aecho=0.4:0.4:50:0.20,"
            "volume=0.35"
        ),
    },
    "prison": {
        "desc": "Long Kesh internment camp: metal doors, wind across the compound",
        # Very dark, low, oppressive — low-pass shaped rumble with long echo
        "filter": (
            "anoisesrc=r=44100:c=pink:a=0.30,lowpass=f=350,highpass=f=30,"
            "aecho=0.7:0.6:200:0.45,"       # deep institutional reverb
            "volume=0.22"
        ),
    },
    "pub": {
        "desc": "Belfast local pub: low murmur of conversation, clinking glasses, occasional laugh",
        # Warm mid-band noise shaped like indistinct pub chatter + glass clinks
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.35,"
            "bandpass=f=900:width_type=h:w=1600,"
            "aecho=0.3:0.3:35:0.12,"        # small room reverb
            "volume=0.28"
        ),
    },
    "garden": {
        "desc": "Suburban back garden: birdsong, light breeze, distant lawnmower, cheerful",
        # High-frequency texture (wind/birds) + very gentle low rumble
        "filter": (
            "anoisesrc=r=44100:c=white:a=0.20,highpass=f=2000,lowpass=f=8000,"
            "aecho=0.2:0.3:25:0.08,"        # open-air feel
            "volume=0.22"
        ),
    },
}

# Keyword rules for automatic location → ambient type classification
_AMBIENT_RULES: list[tuple[list[str], str]] = [
    # Natural/outdoor first — these are checked before the Belfast-era rules.
    (["storm", "stormy", "gale", "tempest"], "sea_storm"),
    (["waterfall", "waterfalls", "cascade", "falls"], "waterfall"),
    (["sea", "ocean", "wave", "waves", "surf", "shore", "coast", "cliff",
      "cliffs", "atlantic", "tide", "headland"], "sea_waves"),
    (["meadow", "meadows", "blossom", "orchard", "wildflowers", "valley",
      "paradise", "pasture"], "meadow"),
    (["moor", "heath", "hillside", "ruin", "ruins", "ruined", "fort",
      "mist", "bog", "heather"], "wind_moor"),
    (["kesh", "prison", "internment", "camp", "cell", "wire"], "prison"),
    (["checkpoint", "army", "military", "patrol", "land rover", "saracen", "barricade"], "military"),
    (["factory", "warehouse", "industrial", "derelict", "abandoned", "machinery"], "factory"),
    (["derry", "march", "protest", "crowd", "demonstration", "bogside"], "crowd_protest"),
    (["pub", "bar", "tavern", "neutral_pub", "local_pub"], "pub"),
    (["garden", "back_garden", "fence", "yard", "outside"], "garden"),
    (["home", "house", "kitchen", "sitting room", "interior", "bedroom", "inside",
      "paddy_house", "billy_house", "paddys_house", "billys_house"], "interior_quiet"),
]


def classify_ambient(location_id: str, location_desc: str = "") -> str | None:
    """Map a location to its ambient sound type based on keywords."""
    text = f"{location_id} {location_desc}".lower()
    for keywords, ambient_type in _AMBIENT_RULES:
        # Word-boundary match. A bare substring test put pub ambience under a
        # desolate ruin because "bar" occurs inside "bare thorn trees", and
        # matched "camp" in "campaign", "wire" in "wireless", "yard" in
        # "graveyard". Underscores count as separators so "back_garden" works.
        for kw in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
                return ambient_type
    # No confident match → no ambience. The old default was "street_rain"
    # ("it's Belfast, it's always raining"), which laid city rain under every
    # unrecognised location. Silence is better than the wrong room.
    return None


def get_ambient_file(location_id: str, bible: dict) -> Path | None:
    """Return the ambient audio file for a location, or None if ambience dir is empty."""
    if not AMBIENCE_DIR.exists():
        return None
    loc_desc = bible.get("world", {}).get("locations", {}).get(location_id, "")
    ambient_type = classify_ambient(location_id, loc_desc)
    if not ambient_type:
        return None
    path = AMBIENCE_DIR / f"{ambient_type}.mp3"
    return path if path.exists() else None


def generate_ambient_files(duration: int = 60):
    """
    Synthesise all ambient audio presets using FFmpeg and save to ambience/.
    Safe to re-run — skips files that already exist (delete to regenerate).
    """
    AMBIENCE_DIR.mkdir(exist_ok=True)
    for name, preset in AMBIENT_PRESETS.items():
        out = AMBIENCE_DIR / f"{name}.mp3"
        if out.exists():
            print(f"  {name}.mp3 — exists, skipping")
            continue
        print(f"  Generating {name}.mp3  ({preset['desc']})")
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"{preset['filter']},atrim=duration={duration}",
            "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            str(out),
        ], capture_output=True, timeout=30)
        if result.returncode != 0:
            print(f"    WARNING: failed — {result.stderr.decode()[-200:]}")
        else:
            print(f"    Saved: {out}")

    # Also generate two music beds:
    #   music.mp3         — melancholy A-minor drone (drama/Belfast Stories)
    #   music_comedy.mp3  — bright C-major bouncy tune (comedy/Wee Differences)
    music_beds = {
        "music.mp3": {
            "desc": "melancholy A-minor atmospheric drone",
            # A minor: A2 + E3 + A3 + C4, slow tremolo LFO
            "expr": (
                "0.12*sin(2*PI*110*t)*sin(PI*0.25*t+0.5)"
                "+0.09*sin(2*PI*165*t)*sin(PI*0.2*t+1.0)"
                "+0.07*sin(2*PI*220*t)*sin(PI*0.18*t+0.3)"
                "+0.05*sin(2*PI*261*t)*sin(PI*0.15*t+0.8)"
            ),
            "post": f"aecho=0.6:0.5:300:0.5,lowpass=f=1200,volume=0.7",
        },
        "music_comedy.mp3": {
            "desc": "bright C-major bouncy comedy tune",
            # C major: C4 (261Hz) + E4 (329Hz) + G4 (392Hz) + C5 (523Hz)
            # Fast staccato envelope via 4Hz LFO gives a bouncy feel
            "expr": (
                "0.13*sin(2*PI*261*t)*max(0,sin(PI*4.0*t))"
                "+0.10*sin(2*PI*329*t)*max(0,sin(PI*4.0*t+0.4))"
                "+0.09*sin(2*PI*392*t)*max(0,sin(PI*4.0*t+0.8))"
                "+0.07*sin(2*PI*523*t)*max(0,sin(PI*3.0*t+1.2))"
            ),
            "post": f"aecho=0.3:0.3:80:0.2,highpass=f=200,volume=0.65",
        },
    }

    for fname, bed in music_beds.items():
        music = AMBIENCE_DIR / fname
        if not music.exists():
            print(f"  Generating {fname}  ({bed['desc']})")
            result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"aevalsrc='{bed['expr']}':s=44100:c=stereo,atrim=duration={duration},{bed['post']}",
                "-c:a", "libmp3lame", "-b:a", "128k",
                str(music),
            ], capture_output=True, timeout=30)
            if result.returncode == 0:
                print(f"    Saved: {music}")
            else:
                print(f"    WARNING: {fname} generation failed")

    print(f"\n  Tip: replace any .mp3 in {AMBIENCE_DIR}/ with a real recording to upgrade that layer.")


# ─── Series file management ──────────────────────────────────────────

def series_path(name: str) -> Path:
    return SERIES_DIR / name


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def episode_path(series_name: str, ep_num: int) -> Path:
    return series_path(series_name) / "episodes" / f"ep{ep_num:02d}.json"


# ─── Claude API ──────────────────────────────────────────────────────

def _text_of(message) -> str:
    """
    Pull the text block out of a response.

    With thinking enabled content[0] is a ThinkingBlock, so the old
    `message.content[0].text` would raise or return reasoning instead of the
    answer. Always select by block type.
    """
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise RuntimeError("Claude returned no text block")


def _check_stop(message, what: str):
    """Turn silent truncation/refusal into a clear error instead of bad JSON."""
    reason = getattr(message, "stop_reason", None)
    if reason == "max_tokens":
        raise RuntimeError(
            f"{what}: response hit the max_tokens ceiling and was cut off. "
            f"Raise max_tokens or ask for fewer scenes."
        )
    if reason == "refusal":
        details = getattr(message, "stop_details", None)
        cat = getattr(details, "category", None) if details else None
        raise RuntimeError(f"{what}: the model declined this request"
                           f"{f' ({cat})' if cat else ''}.")


def _is_schema_error(err) -> bool:
    """True when a 400 is about the output schema, not billing/auth/params."""
    msg = str(err).lower()
    if "credit balance" in msg or "rate limit" in msg:
        return False
    return any(k in msg for k in ("schema", "output_config", "output format",
                                  "json_schema", "additionalproperties"))


def _anthropic_call(system_prompt: str, content, max_tokens: int,
                    schema: dict | None, effort: str, what: str):
    """
    One place for every Claude call: adaptive thinking, configurable effort,
    optional structured output, and streaming (required for large max_tokens,
    and it keeps long script generations from hitting request timeouts).
    """
    import anthropic
    client = anthropic.Anthropic()

    output_config: dict = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}

    def _send(cfg):
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            thinking={"type": "adaptive"},
            output_config=cfg,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            return stream.get_final_message()

    try:
        try:
            message = _send(output_config)
        except anthropic.BadRequestError as e:
            # If this deployment rejects the schema itself, fall back to a
            # plain call rather than failing the run — call_claude_json can
            # still recover the object from the raw text.
            if "format" not in output_config or not _is_schema_error(e):
                raise
            print(f"  NOTE: structured output rejected ({str(e)[:120]}); "
                  f"retrying without a schema")
            message = _send({"effort": output_config["effort"]})
    except anthropic.AuthenticationError:
        raise RuntimeError("Invalid Anthropic API key. Set ANTHROPIC_API_KEY to a valid key.")
    except anthropic.RateLimitError:
        raise RuntimeError("Anthropic rate limit exceeded. Wait a moment and try again.")
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}")

    _check_stop(message, what)
    return _text_of(message)


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 16000, *,
                schema: dict | None = None, effort: str | None = None,
                what: str = "call_claude") -> str:
    """Call Claude and return the text response."""
    return _anthropic_call(system_prompt, user_prompt, max_tokens, schema,
                           effort or CLAUDE_EFFORT, what)


def call_claude_json(system_prompt: str, user_prompt: str,
                     schema: dict | None = None,
                     max_tokens: int = 16000, *, effort: str | None = None,
                     what: str = "call_claude_json") -> dict:
    """
    Call Claude with a JSON schema and return the parsed object.

    Structured outputs make the response conform to the schema, which removes
    the markdown-fence stripping and the "Claude returned invalid JSON" class
    of failures that used to abort a whole write run.
    """
    raw = _anthropic_call(system_prompt, user_prompt, max_tokens, schema,
                          effort or CLAUDE_EFFORT, what)
    return _parse_json_response(raw, what)


def _parse_json_response(raw: str, what: str) -> dict:
    """
    Parse a JSON object out of a model response.

    With structured outputs this is a plain json.loads. It also recovers the
    object when a schema was unavailable and the model wrapped it in markdown
    fences or added a sentence around it.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            print(f"[{what}] Unparseable response: {raw[:500]}")
            raise ValueError(f"{what}: could not parse JSON: {e}") from e
    print(f"[{what}] Unparseable response: {raw[:500]}")
    raise ValueError(f"{what}: response contained no JSON object")


def call_claude_vision(system_prompt: str, content_blocks: list, max_tokens: int = 2000, *,
                       schema: dict | None = None, effort: str | None = None,
                       what: str = "call_claude_vision") -> str:
    """Call Claude with a multimodal message (text + images)."""
    return _anthropic_call(system_prompt, content_blocks, max_tokens, schema,
                           effort or CLAUDE_EFFORT, what)


def generate_bible(concept: dict) -> dict:
    """Use Claude to expand a concept into a full series bible."""
    system = """You are a creative writer and showrunner for an animated short-form video series.
You will receive a series concept and must expand it into a detailed series bible.

Return ONLY valid JSON (no markdown fences) with this exact structure:
{
  "series": {
    "title": "...",
    "style": "A detailed visual style prompt that will be appended to every video generation prompt. Be specific about art style, color palette, lighting, animation style. 2-3 sentences.",
    "format": {
      "resolution": [480, 320],
      "fps": 16
    }
  },
  "characters": {
    "character_id": {
      "name": "Display Name",
      "visual": "Detailed visual description for video generation. Include hair, clothing, distinguishing features. Be consistent and specific.",
      "voice": "TTS voice name (pick from: en-US-GuyNeural, en-US-JennyNeural, en-US-AriaNeural, en-GB-SoniaNeural, en-GB-RyanNeural, en-AU-NatashaNeural, ja-JP-NanamiNeural)",
      "voice_notes": "Character's speaking style for narration writing.",
      "role": "Their role in the story."
    }
  },
  "world": {
    "setting": "Detailed setting description.",
    "locations": {
      "location_id": "Detailed visual description of this location for video generation."
    },
    "rules": ["Story/world rules that maintain consistency"]
  },
  "season_arc": {
    "summary": "The overarching arc across all episodes.",
    "themes": ["theme1", "theme2"],
    "progression": "How the story evolves from first to last episode."
  },
  "narrator": {
    "voice": "TTS voice name for the narrator",
    "style": "Narration style description"
  }
}"""

    user = f"""Here is the series concept. Expand it into a full series bible.

CONCEPT:
{json.dumps(concept, indent=2)}

Remember: return ONLY valid JSON, no markdown."""

    # No JSON schema here: the bible keys characters and locations by id
    # (dynamic object keys), which structured outputs may not accept. The
    # prompt pins the shape and _parse_json_response recovers the object.
    return call_claude_json(system, user, schema=None, max_tokens=16000,
                            what="generate_bible")


def _episode_schema() -> dict:
    """JSON schema for an episode script — keeps clip_length in sync with CLIP_LENGTHS."""
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "location": {"type": "string"},
                        "characters": {"type": "array", "items": {"type": "string"}},
                        "clip_length": {"type": "string", "enum": list(CLIP_LENGTHS.keys())},
                        "visual": {"type": "string"},
                        "narration": {"type": ["string", "null"]},
                        "dialogue": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "character": {"type": "string"},
                                    "line": {"type": "string"},
                                },
                                "required": ["character", "line"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["id", "location", "characters", "clip_length",
                                 "visual", "narration", "dialogue"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["id", "title", "summary", "scenes"],
        "additionalProperties": False,
    }


def generate_episode(bible: dict, concept: dict, ep_num: int, total_eps: int, previous_summaries: list[str]) -> dict:
    """Use Claude to generate a single episode script."""

    target_duration = concept.get("episode_duration_seconds", 30)

    # Derive clip physics from CLIP_LENGTHS rather than hardcoding them. The
    # prompt used to claim 2.0/2.7/3.4s while the pipeline actually renders
    # 2.1/3.1/5.1s, so every "long" scene ran 1.7s longer than the writer
    # budgeted for: episodes overshot their target and long scenes were left
    # with dead air because their narration was written for a 3.4s slot.
    _order = ["short", "medium", "long"]
    # Budget against the slot a scene actually KEEPS. Every boundary gives
    # CROSSFADE_DURATION back to the transition, so writing to the full clip
    # length makes the last words of a line overrun into the next shot.
    _fps = float(get_model_config(DEFAULT_VIDEO_MODEL)["fps"])
    _secs = {k: round(CLIP_LENGTHS[k]["frames"] / _fps - CROSSFADE_DURATION, 1)
             for k in _order if k in CLIP_LENGTHS}
    _avg = sum(_secs.values()) / len(_secs)
    _min_scenes = max(4, int(target_duration / max(_secs.values())))
    _est_scenes = max(_min_scenes, round(target_duration / _avg))

    # Narration budget follows the narrator's measured speaking rate — voices
    # differ by ~35% (en-GB-Sonia 2.2 w/s vs en-US-Jenny 3.0 w/s), so a fixed
    # words-per-second either overruns the clip or leaves silence.
    _nv = (bible.get("narrator") or {}).get("voice", "")
    _wps = VOICE_WPS.get(_nv, DEFAULT_WPS)
    _words = {k: max(3, int(v * _wps)) for k, v in _secs.items()}

    _use = {"short": "action, transitions, quick cuts, reaction shots",
            "medium": "dialogue exchanges, character moments, two-shots",
            "long": "atmospheric establishing shots, emotional beats, wide shots"}
    _len_menu = "\n".join(
        f"  - {_secs[k]}s ({k}): {_use[k]}" for k in _order if k in _secs)
    _word_menu = "\n".join(
        f"  - {_secs[k]}s {k} clip: max {_words[k]} words of narration"
        for k in _order if k in _secs)
    _len_list = ", ".join(f"{_secs[k]}s" for k in _order if k in _secs)

    system = f"""You are a showrunner writing episode scripts for an animated short-form series.
Each episode is ~{target_duration} seconds long, made of multiple clips stitched together.

IMPORTANT CONSTRAINTS:
- Each clip/scene is exactly {_len_list} long — no other durations exist
- Total episode duration should be ~{target_duration} seconds (aim for {target_duration - 3} to {target_duration + 3}s)
- For a {target_duration}s episode you will need roughly {_est_scenes} scenes — DO NOT write fewer than {_min_scenes} scenes
- Choose clip duration based on content:
{_len_menu}
- Each scene needs a visual description that works as a text-to-video prompt
- NARRATION WORD LIMIT (this narrator speaks ~{_wps} words/second):
{_word_menu}
  - COUNT the words before finalising — narration that overruns will be cut off
- Dialogue lines should also be brief (5-8 words max per line); one line per dialogue scene
- COUNT your scene durations as you write to ensure they sum to ~{target_duration}s before finishing

VISUAL DESCRIPTIONS BY SCENE TYPE:
- ESTABLISHING shots: wide or aerial view, camera drifts or slowly pans, no dialogue
- DIALOGUE scenes: ALWAYS start the visual with the shot framing — e.g. "Medium two-shot of [A] and [B] facing each other" or "Close-up on [character]'s face". Camera must be STATIC or very slow push-in. Characters should face camera or face each other. Minimal background motion.
- ACTION scenes: describe the specific movement, camera follows action, can be handheld
- REACTION shots: extreme close-up on face, static camera, 2.0s short clip
- NARRATION-over-visuals: atmospheric movement (slow pan, drift), no characters needed

Return ONLY valid JSON (no markdown fences) with this structure:
{{
  "id": "ep{ep_num:02d}",
  "title": "Episode Title",
  "summary": "1-2 sentence episode summary",
  "scenes": [
    {{
      "id": "ep{ep_num:02d}_s01",
      "location": "location_id from bible",
      "characters": ["character_id"],
      "clip_length": "short|medium|long",
      "visual": "Detailed visual description for video generation. START with shot framing (Wide shot / Medium shot / Close-up / Two-shot). Describe camera movement, character pose, lighting, composition. Do NOT include dialogue or narration text in this field.",
      "narration": "Voiceover text (word count must fit clip — see limits above), or null",
      "dialogue": [
        {{"character": "character_id", "line": "Brief line (5-8 words max)"}}
      ],
      "setup": "master|reverse|wider|closer|side — which camera setup of the location",
      "staging": "left|right|close — where the character sits in frame (close-ups only), or omit"
    }}
  ]
}}

RULES:
- The visual field should be a standalone video generation prompt — describe motion, camera angles, lighting
- Never put dialogue text in the visual field
- Keep visual descriptions under 150 words
- A scene can have narration OR dialogue OR both (if both are very brief), or neither
- Dialogue scenes need static/slow camera so the spoken line is coherent with what's on screen
- Start with an establishing shot, end with a closing shot
- The episode should tell a complete mini-story while advancing the season arc

CAMERA COVERAGE — "setup" and "staging":
Each location has a small library of fixed camera setups, and a shot is rendered
from the plate for the setup you name. Naming them is how a scene keeps the same
geography from cut to cut instead of re-inventing the place every shot.

- "master"  the established view of the location
- "reverse" the opposite angle, looking back
- "wider"   pulled back, more landscape
- "closer"  pushed in
- "side"    a different vantage on the same ground

Obey the 180-degree rule in any two-hander. Pick ONE character to shoot from
"master" and always shoot the OTHER from "reverse", for the whole conversation.
Do not swap mid-scene: their eyelines stop matching and the two of them appear
not to be looking at each other. Use "wider" when someone turns away or leaves,
"closer" to tighten as a scene intensifies.

"staging" applies to close-ups only and says where the character sits in frame.

Prefer FEWER, LONGER shots. Clips cap at ~5s, so a 16-shot minute averages under
4s a shot and reads as restless. Aim for 10-12 shots a minute and let "long"
clips carry the weight."""

    prev_context = ""
    if previous_summaries:
        prev_context = "\n\nPREVIOUS EPISODES:\n" + "\n".join(
            f"  Episode {i+1}: {s}" for i, s in enumerate(previous_summaries)
        )

    # Per-episode brief from concept.json — guides the topic for this specific episode
    ep_plan = concept.get("episode_plan", [])
    ep_brief = ep_plan[ep_num - 1] if ep_num <= len(ep_plan) else ""
    ep_brief_block = f"\nTHIS EPISODE'S BRIEF:\n{ep_brief}\nStick closely to this brief — do not invent a different topic.\n" if ep_brief else ""

    user = f"""SERIES BIBLE:
{json.dumps(bible, indent=2)}

SEASON ARC:
{json.dumps(bible.get('season_arc', {}), indent=2)}
{ep_brief_block}{prev_context}

Write Episode {ep_num} of {total_eps}.
This is {'the first episode — introduce the world and characters' if ep_num == 1 else f'episode {ep_num} — continue the season arc'}.
{'This is the season finale — bring the arc to a satisfying conclusion.' if ep_num == total_eps else ''}

Target duration: ~{target_duration} seconds.
Return ONLY valid JSON, no markdown."""

    # 4000 tokens was tight: a 17-scene episode already lands near 2.4k, so a
    # longer episode truncated mid-JSON and aborted the run.
    return call_claude_json(system, user, schema=_episode_schema(),
                            max_tokens=16000, what=f"generate_episode ep{ep_num:02d}")


# ─── TTS ─────────────────────────────────────────────────────────────

# Per-voice speaking rates (measured from Edge-TTS output)
VOICE_WPS: dict[str, float] = {
    # Measured on this box with ffprobe, not estimated.
    "en-IE-ConnorNeural": 2.78,
    "en-IE-EmilyNeural": 2.75,
    "en-US-JennyNeural": 3.0,
    "en-US-AmberNeural": 2.8,
    "en-US-AriaNeural": 2.9,
    "en-US-GuyNeural": 2.9,
    "en-US-ChristopherNeural": 2.7,
    "en-US-RogerNeural": 2.8,
    "en-GB-RyanNeural": 2.3,
    "en-GB-SoniaNeural": 2.2,
    "en-GB-ThomasNeural": 2.4,
    "en-GB-AmberNeural": 2.6,
    "en-GB-GeorgeNeural": 2.3,
}
DEFAULT_WPS = 2.5
# Cap on how much a narration line may be sped up to fit its shot.
MAX_NARRATION_SPEEDUP = 22


# Edge-TTS pads every clip: measured 0.226s before the first word and 0.90s
# after the last. On a 2.6s dialogue shot that is 1.1s -- 42% -- of dead air.
# It matters more than it sounds, because S2V sizes the clip to its audio and
# drives the mouth from it, so the character stands mute for nearly half of
# their own dialogue shot. Trim to a natural breath instead.
TTS_LEAD_PAD = 0.06        # keep a little, or the line starts abruptly
TTS_TAIL_PAD = 0.18        # and a little after, or it feels clipped


def _trim_tts_silence(path: str) -> bool:
    """Trim Edge-TTS lead-in/tail silence in place, leaving a natural breath."""
    try:
        import numpy as np
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
             "-f", "f32le", "-"], capture_output=True, timeout=120).stdout
        x = np.frombuffer(raw, dtype=np.float32)
        if x.size < 1600:
            return False
        env = np.abs(x)
        peak = float(env.max())
        if peak <= 0:
            return False
        idx = np.where(env > peak * 0.06)[0]
        if idx.size == 0:
            return False
        start = max(0.0, idx[0] / 16000 - TTS_LEAD_PAD)
        end = min(len(x) / 16000, idx[-1] / 16000 + TTS_TAIL_PAD)
        if end - start < 0.25 or (end - start) >= (len(x) / 16000) - 0.05:
            return False                       # nothing worth trimming
        tmp = path + ".trim.mp3"
        ok = run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", path,
                         "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                         "-c:a", "libmp3lame", "-q:a", "2", tmp],
                        "trim tts silence")
        if ok and Path(tmp).exists() and Path(tmp).stat().st_size > 1000:
            shutil.move(tmp, path)
            return True
        Path(tmp).unlink(missing_ok=True)
    except Exception:                                          # noqa: BLE001
        pass
    return False


async def generate_tts_scene(text: str, voice: str, output_path: str,
                             rate: str = "+0%", pitch: str = "+0Hz"):
    """Generate TTS audio for a single scene with optional prosody control."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    _trim_tts_silence(output_path)


def _concat_audio_files(parts: list[str], output_path: str):
    """Concatenate multiple audio files into one using ffmpeg."""
    if len(parts) == 1:
        shutil.copy2(parts[0], output_path)
        return
    # Build concat filter
    inputs = []
    filter_parts = []
    for i, p in enumerate(parts):
        inputs += ["-i", p]
        filter_parts.append(f"[{i}:a]")
    filter_str = f"{''.join(filter_parts)}concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_str,
        "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "128k", output_path,
    ], capture_output=True, timeout=60)


def _get_character_prosody(char: dict) -> tuple[str, str]:
    """Return (rate, pitch) for Edge-TTS based on character voice_notes."""
    # An explicit rate/pitch on the character or narrator always wins — the
    # keyword heuristic below can only ever slow a voice down, so there was no
    # way to fit more narration into a clip without rewriting the line.
    if char.get("rate") or char.get("pitch"):
        return char.get("rate", "+0%"), char.get("pitch", "+0Hz")

    notes = (char.get("voice_notes", "") + " " + char.get("style", "")).lower()
    rate = "+0%"
    pitch = "+0Hz"
    # Adjust speech style based on character description
    if any(w in notes for w in ["nasal", "wheedling", "scheming", "nervous"]):
        rate = "+5%"
        pitch = "+15Hz"  # slightly higher, more strained
    elif any(w in notes for w in ["fierce", "determined", "confident", "bold"]):
        rate = "-5%"
        pitch = "-10Hz"  # slightly lower, more grounded
    elif any(w in notes for w in ["wry", "sardonic", "detached", "dry"]):
        rate = "-8%"
        pitch = "-5Hz"  # slow, measured delivery
    elif any(w in notes for w in ["warm", "gentle", "kind", "soft"]):
        rate = "-3%"
        pitch = "-5Hz"
    return rate, pitch


def scene_audio_budget(scene: dict) -> float:
    """Seconds of audio this shot can hold.

    A chained take is several chunks long, but this used to read only the
    nominal single-clip length, so a 10.12s shot was costed at 5.06s and its
    dialogue was cut to fit a shot half its real size. An authored
    hold_seconds is the shot's true length.
    """
    cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
    return max(float(cl["seconds"]), float(scene.get("hold_seconds") or 0.0))


def should_use_carry_over(index: int, scene: dict, carry_over_image: str | None,
                          planned_seed: str | None) -> bool:
    """Whether scene `index` should open on the previous episode's end frame.

    The carry-over stops a new episode jumping back to a static reference after
    the last one ended mid-scene. It is a FALLBACK. When the set library has a
    staged plate for this exact setup and framing, or a character portrait
    applies, that is an authored decision and outranks a frame inherited from
    another episode -- which otherwise put ep04's closing image under ep05's
    opening wide.
    """
    if index != 0 or not carry_over_image or (scene.get("seed") or ""):
        return False
    authored = bool(planned_seed) and (
        "__" in planned_seed or "char_" in planned_seed or "loc_" in planned_seed)
    return not authored


def generate_episode_audio(episode: dict, bible: dict, output_dir: Path) -> list[Path]:
    """Generate TTS audio for each scene with per-character voices."""
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    narrator_voice = bible.get("narrator", {}).get("voice", "en-US-GuyNeural")
    narrator_prosody = _get_character_prosody(bible.get("narrator", {}))
    audio_files = []

    for scene in episode["scenes"]:
        audio_path = audio_dir / f"{scene['id']}.mp3"
        cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
        clip_dur = scene_audio_budget(scene)

        has_narration = bool(scene.get("narration"))
        has_dialogue = bool(scene.get("dialogue"))

        if not has_narration and not has_dialogue:
            audio_files.append(None)  # Silent scene
            continue

        # Skip if audio already exists (resume mode)
        if audio_path.exists():
            audio_files.append(audio_path)
            continue

        try:
            audio_parts: list[str] = []
            temp_dir = audio_dir / f"{scene['id']}_parts"
            temp_dir.mkdir(exist_ok=True)

            part_idx = 0

            # Generate narration segment
            if has_narration:
                narr_text = scene["narration"]
                dialogue_budget = len(scene.get("dialogue", [])) * 1.5  # ~1.5s per line estimate
                narr_budget = clip_dur - dialogue_budget if has_dialogue else clip_dur

                # This used to cut the SCRIPT to fit: max_words = budget * wps * 0.9,
                # with wps falling back to a guess for any voice missing from
                # VOICE_WPS. It silently dropped the last word of five lines in a
                # sixteen-shot episode -- "the Land of Eternal" with no "Youth".
                # Speak the whole line and fit it by delivery speed instead; only
                # complain if even that cannot make it fit.
                part_file = str(temp_dir / f"{part_idx:02d}_narration.mp3")
                asyncio.run(generate_tts_scene(narr_text, narrator_voice, part_file,
                                               rate=narrator_prosody[0], pitch=narrator_prosody[1]))
                spoken = _get_video_duration(part_file)
                if narr_budget > 0 and spoken > narr_budget:
                    over = spoken / narr_budget
                    pct = min(MAX_NARRATION_SPEEDUP, int((over - 1) * 100) + 3)
                    asyncio.run(generate_tts_scene(narr_text, narrator_voice, part_file,
                                                   rate=f"+{pct}%", pitch=narrator_prosody[1]))
                    now = _get_video_duration(part_file)
                    print(f"    {scene['id']}: narration {spoken:.2f}s > {narr_budget:.2f}s slot "
                          f"— respoken at +{pct}% ({now:.2f}s)")
                    if now > narr_budget + 0.05:
                        fatal(f"{scene['id']} narration is {now - narr_budget:.2f}s too long "
                              f"even at +{pct}%",
                              "Shorten the line in the episode JSON. Nothing is being cut, so "
                              "the audio would overrun the shot and drift the rest of the film.")
                audio_parts.append(part_file)
                part_idx += 1

            # Generate per-character dialogue segments
            if has_dialogue:
                for d in scene["dialogue"]:
                    char_id = d["character"]
                    char = bible.get("characters", {}).get(char_id, {})
                    char_voice = char.get("voice", narrator_voice)
                    char_rate, char_pitch = _get_character_prosody(char)

                    line_text = d["line"]
                    # Per-voice truncation check
                    wps = VOICE_WPS.get(char_voice, DEFAULT_WPS)
                    line_dur_est = len(line_text.split()) / wps
                    remaining_budget = clip_dur * 0.9 - sum(
                        _get_video_duration(p) for p in audio_parts if os.path.exists(p)
                    )
                    # Narration that overruns is fatal a few lines above --
                    # "nothing is being cut, so the audio would overrun". Yet
                    # dialogue, the thing the audience actually listens to, was
                    # silently truncated mid-sentence and the render carried on.
                    # Two policies for one problem, and the quieter one applied
                    # to the more important text. Same rule for both now.
                    if line_dur_est > remaining_budget > 0 and remaining_budget < line_dur_est * 0.7:
                        fatal(f"{scene['id']}: {char.get('name', char_id)}'s line "
                              f"needs ~{line_dur_est:.1f}s but only "
                              f"{remaining_budget:.1f}s of the shot is left",
                              "Shorten the line, or give the shot a longer "
                              '"hold_seconds". Truncating it would cut the '
                              "performance mid-sentence.")

                    part_file = str(temp_dir / f"{part_idx:02d}_{char_id}.mp3")
                    asyncio.run(generate_tts_scene(line_text, char_voice, part_file,
                                                   rate=char_rate, pitch=char_pitch))
                    audio_parts.append(part_file)
                    part_idx += 1

            # Concatenate all parts into final scene audio
            if audio_parts:
                _concat_audio_files(audio_parts, str(audio_path))

            # Clean up temp parts
            for p in audio_parts:
                Path(p).unlink(missing_ok=True)
            temp_dir.rmdir()

            audio_files.append(audio_path)

        except Exception as e:
            print(f"    TTS failed for {scene['id']}: {e}")
            audio_files.append(None)
            continue

    return audio_files


def generate_single_scene_audio(scene: dict, bible: dict, output_dir: Path) -> Path | None:
    """Generate TTS audio for a single scene with per-character voices."""
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{scene['id']}.mp3"

    narrator_voice = bible.get("narrator", {}).get("voice", "en-US-GuyNeural")
    narrator_prosody = _get_character_prosody(bible.get("narrator", {}))

    has_narration = bool(scene.get("narration"))
    has_dialogue = bool(scene.get("dialogue"))

    if not has_narration and not has_dialogue:
        return None

    try:
        audio_parts: list[str] = []
        temp_dir = audio_dir / f"{scene['id']}_parts"
        temp_dir.mkdir(exist_ok=True)

        if has_narration:
            part_file = str(temp_dir / "00_narration.mp3")
            asyncio.run(generate_tts_scene(scene["narration"], narrator_voice, part_file,
                                           rate=narrator_prosody[0], pitch=narrator_prosody[1]))
            audio_parts.append(part_file)

        if has_dialogue:
            for j, d in enumerate(scene["dialogue"]):
                char = bible.get("characters", {}).get(d["character"], {})
                char_voice = char.get("voice", narrator_voice)
                char_rate, char_pitch = _get_character_prosody(char)
                part_file = str(temp_dir / f"{j+1:02d}_{d['character']}.mp3")
                asyncio.run(generate_tts_scene(d["line"], char_voice, part_file,
                                               rate=char_rate, pitch=char_pitch))
                audio_parts.append(part_file)

        if audio_parts:
            _concat_audio_files(audio_parts, str(audio_path))

        for p in audio_parts:
            Path(p).unlink(missing_ok=True)
        temp_dir.rmdir()

    except Exception as e:
        print(f"    TTS failed for {scene['id']}: {e}")
        return None

    return audio_path


# ─── Video generation ────────────────────────────────────────────────

def build_lora_node(model_output: list, lora_filename: str, strength: float = 0.7) -> dict:
    """Return a LoraLoaderModelOnly node dict for insertion into ComfyUI workflows."""
    return {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": model_output,
            "lora_name": lora_filename,
            "strength_model": strength,
        },
    }


def _insert_easycache(wf: dict, preset: dict, model_node: str) -> None:
    """Insert an EasyCache node for step-skipping optimization.

    EasyCache (the ComfyUI native TeaCache implementation) monitors the change
    rate between diffusion steps and skips computation when the intermediate
    result is similar enough to the cached version. This can speed up generation
    by 30-60% with minimal quality loss.

    Args:
        wf: Workflow dict to modify in-place.
        preset: Dict with reuse_threshold, start_percent, end_percent.
        model_node: Node ID whose model output should be wrapped with caching.
    """
    if preset is None:
        return

    # Get the current model output from the target node
    current_model = wf[model_node]["inputs"]["model"]

    # Insert EasyCache between the model source and the target node
    wf["70"] = {
        "class_type": "EasyCache",
        "inputs": {
            "model": current_model,
            "reuse_threshold": preset["reuse_threshold"],
            "start_percent": preset["start_percent"],
            "end_percent": preset["end_percent"],
            "verbose": False,
        },
    }

    # Point the target node to the EasyCache output
    wf[model_node]["inputs"]["model"] = ["70", 0]


def _insert_optimizations(wf: dict, optimization: str, model_node: str) -> None:
    """Insert all optimization nodes based on the selected preset.

    Args:
        wf: Workflow dict to modify in-place.
        optimization: Preset name from OPTIMIZATION_PRESETS.
        model_node: The ModelSamplingSD3 node ID.
    """
    preset = OPTIMIZATION_PRESETS.get(optimization, OPTIMIZATION_PRESETS["none"])

    if preset.get("easycache"):
        _insert_easycache(wf, preset["easycache"], model_node)


def _insert_lora_chain(wf: dict, loras: list[tuple[str, float]], unet_node: str,
                       sampler_model_node: str, node_id_offset: int = 50) -> None:
    """Insert a chain of LoRA nodes between the UNet loader and the sampler model node.

    Each LoRA feeds into the next, forming a chain:
      UnetLoaderGGUF → LoRA_1 → LoRA_2 → LoRA_3 → ModelSamplingSD3

    Args:
        wf: The workflow dict to modify in-place.
        loras: List of (lora_filename, strength) tuples. Max 3 recommended.
        unet_node: Node ID of UnetLoaderGGUF (e.g. "1").
        sampler_model_node: Node ID that consumes the model (e.g. "7" for T2V, "10" for I2V).
        node_id_offset: Starting node ID for LoRA nodes (default 50; use 60 for second chain).
    """
    if not loras:
        return

    prev_output = [unet_node, 0]  # Start from UNet output

    for idx, (lora_name, lora_strength) in enumerate(loras):
        node_id = str(node_id_offset + idx)  # "50", "51", "52" or "60", "61", "62"
        wf[node_id] = build_lora_node(prev_output, lora_name, lora_strength)
        prev_output = [node_id, 0]

    # Point the sampler model node to the last LoRA output
    wf[sampler_model_node]["inputs"]["model"] = prev_output


# ─── WAN 2.2 workflow builders ──────────────────────────────────────

def build_wan_t2v_workflow(prompt: str, seed: int, clip_prefix: str, frames: int,
                            negative_prompt: str = "", steps: int = 25,
                            loras: list[tuple[str, float]] | None = None,
                            high_loras: list[tuple[str, float]] | None = None,
                            low_loras: list[tuple[str, float]] | None = None,
                            res_config: dict | None = None,
                            model_config: dict | None = None) -> dict:
    """Build a WAN T2V workflow.

    Supports both dual-model (WAN 2.2 14B) and single-model (TI2V-5B) configs.
    In dual-model mode, uses SplitSigmas to switch between high-noise and
    low-noise expert models at the timestep_boundary.
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]
    is_dual = mc.get("dual_model", False)

    # Single-model T2V with KSampler (dual-model SplitSigmas causes mosaic artifacts)
    wf = {
        "1":  {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["t2v_unet"]}},
        "2":  {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "3":  {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},
        "4":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},
        "6":  {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
            "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
        }},
        "7":  {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "8":  {"class_type": "KSampler", "inputs": {
            "model": ["7", 0], "positive": ["6", 0], "negative": ["6", 1],
            "latent_image": ["6", 2], "seed": seed, "steps": steps, "cfg": mc["cfg"],
            "sampler_name": mc["sampler"], "scheduler": mc["scheduler"], "denoise": 1.0,
        }},
    }

    sampled_output = "8"

    # Decode and save
    wf["13"] = {"class_type": "VAEDecode", "inputs": {"samples": [sampled_output, 0], "vae": ["3", 0]}}
    wf["14"] = {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(mc["fps"])}}
    wf["15"] = {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": save_prefix(clip_prefix), "format": "mp4", "codec": "h264"}}

    # LoRA injection (single model — high-noise only)
    if loras:
        _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="7", node_id_offset=50)

    return wf


def build_wan_i2v_workflow(prompt: str, image_name: str, seed: int, clip_prefix: str, frames: int,
                            negative_prompt: str = "", steps: int = 25,
                            denoise: float = DEFAULT_DENOISE,
                            loras: list[tuple[str, float]] | None = None,
                            high_loras: list[tuple[str, float]] | None = None,
                            low_loras: list[tuple[str, float]] | None = None,
                            res_config: dict | None = None,
                            model_config: dict | None = None) -> dict:
    """Build a WAN 2.2 I2V workflow with dual-model KSamplerAdvanced.

    Uses the official WAN 2.2 14B I2V architecture:
    - High-noise model handles early denoising (steps 0 → mid)
    - Low-noise model handles detail refinement (steps mid → end)
    - KSamplerAdvanced enables the step-range handoff between models
    - Image conditioning via WanImageToVideo (VAE-encodes start image)

    For the 5B single-model config, falls back to a single KSampler pass.

    Key I2V parameters (differ from T2V):
    - shift: 8.0 (official WAN 2.2 I2V value, vs 12.0 for T2V)
    - cfg: 3.5 (lower guidance for I2V, vs 5.0 for T2V)
    - sampler: euler (official I2V sampler)
    - denoise: 1.0 (image conditioning is via WanImageToVideo concat, not denoise)
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]
    is_i2v_dual = mc.get("i2v_dual_model", False)

    i2v_shift = rc.get("i2v_shift", 8.0)
    i2v_cfg = mc.get("i2v_cfg", 3.5)
    i2v_sampler = mc.get("i2v_sampler", "euler")

    # Common nodes: text encoder, VAE, image loading, conditioning
    wf = {
        "3": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": negative_prompt}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "8": {"class_type": "ImageScale", "inputs": {
            "image": ["7", 0], "upscale_method": "lanczos",
            "width": rc["width"], "height": rc["height"], "crop": "center",
        }},
        "9": {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "vae": ["4", 0],
            "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
            "start_image": ["8", 0],
        }},
    }

    if is_i2v_dual and rc.get("i2v_unet_low"):
        # Dual-model: high-noise + low-noise with KSamplerAdvanced handoff
        mid_step = steps // 2

        wf["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["i2v_unet"]}}
        wf["2"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["i2v_unet_low"]}}
        wf["10"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": i2v_shift}}
        wf["11"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": i2v_shift}}

        # KSamplerAdvanced #1: high-noise pass
        wf["12"] = {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["10", 0], "positive": ["9", 0], "negative": ["9", 1],
            "latent_image": ["9", 2], "noise_seed": seed, "steps": steps, "cfg": i2v_cfg,
            "sampler_name": i2v_sampler, "scheduler": mc["scheduler"],
            "start_at_step": 0, "end_at_step": mid_step,
            "add_noise": "enable", "return_with_leftover_noise": "enable",
        }}

        # KSamplerAdvanced #2: low-noise refinement pass
        wf["13"] = {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["11", 0], "positive": ["9", 0], "negative": ["9", 1],
            "latent_image": ["12", 0], "noise_seed": seed, "steps": steps, "cfg": i2v_cfg,
            "sampler_name": i2v_sampler, "scheduler": mc["scheduler"],
            "start_at_step": mid_step, "end_at_step": 10000,
            "add_noise": "disable", "return_with_leftover_noise": "disable",
        }}

        sampled_output = "13"

        # LoRA injection: each model gets its matching -high/-low variant
        i2v_high_loras = high_loras or loras
        i2v_low_loras = low_loras or loras
        if i2v_high_loras:
            _insert_lora_chain(wf, i2v_high_loras, unet_node="1", sampler_model_node="10", node_id_offset=50)
        if i2v_low_loras:
            _insert_lora_chain(wf, i2v_low_loras, unet_node="2", sampler_model_node="11", node_id_offset=60)

    else:
        # Single-model fallback (5B or if low-noise model unavailable)
        wf["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["i2v_unet"]}}
        wf["10"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": i2v_shift}}
        wf["11"] = {"class_type": "KSampler", "inputs": {
            "model": ["10", 0], "positive": ["9", 0], "negative": ["9", 1],
            "latent_image": ["9", 2], "seed": seed, "steps": steps, "cfg": i2v_cfg,
            "sampler_name": i2v_sampler, "scheduler": mc["scheduler"], "denoise": 1.0,
        }}

        sampled_output = "11"

        if loras:
            _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="10", node_id_offset=50)

    # Decode and save
    wf["16"] = {"class_type": "VAEDecode", "inputs": {"samples": [sampled_output, 0], "vae": ["4", 0]}}
    wf["17"] = {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": float(mc["fps"])}}
    wf["18"] = {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": save_prefix(clip_prefix), "format": "mp4", "codec": "h264"}}

    return wf


def _resolve_wan_dual_loras(loras: list[tuple[str, float]] | None) -> tuple[list[tuple[str, float]] | None, list[tuple[str, float]] | None]:
    """Resolve WAN LoRA base names to actual files on disk.

    For T2V (single high-noise model): resolves to -high variant and mutates
    the input list in-place.

    For I2V (dual-model): returns separate (high_loras, low_loras) lists so
    each model gets its matching LoRA variant.

    Examples:
        "reemi-wan22.safetensors" → high: "reemi-wan22-high.safetensors"
                                  → low:  "reemi-wan22-low.safetensors"
    """
    if not loras:
        return None, None

    loras_dir = COMFYUI_DIR / "models" / "loras"
    high_loras = []
    low_loras = []

    for i, (lora_name, strength) in enumerate(loras):
        base = lora_name.removesuffix(".safetensors")
        high_file = f"{base}-high.safetensors"
        low_file = f"{base}-low.safetensors"

        # If the exact file exists, use it for both (unsplit LoRA)
        if (loras_dir / lora_name).exists():
            high_loras.append((lora_name, strength))
            low_loras.append((lora_name, strength))
            continue

        # Check for split -high/-low variants
        has_high = (loras_dir / high_file).exists()
        has_low = (loras_dir / low_file).exists()

        if has_high:
            loras[i] = (high_file, strength)  # Mutate for T2V single-model path
            high_loras.append((high_file, strength))
            print(f"[WAN] Resolved LoRA (high): {lora_name} → {high_file}")
        else:
            fatal(f"LoRA not found: {lora_name} (checked {high_file})",
                  "The shot would render without it and look plausible while "
                  "proving nothing about the LoRA.")

        if has_low:
            low_loras.append((low_file, strength))
            print(f"[WAN] Resolved LoRA (low): {lora_name} → {low_file}")
        elif has_high:
            # No -low variant — use -high for both (better than nothing)
            low_loras.append((high_file, strength))
            print(f"[WAN] No -low variant for {lora_name}, using -high for both models")

    return high_loras or None, low_loras or None


def _s2v_unet(rc: dict) -> str:
    """
    The speech-to-video checkpoint. Falling back to the T2V UNet would produce
    a clip that ignores the audio entirely -- no lip sync, no error, no clue.
    """
    name = rc.get("s2v_unet")
    if not name:
        raise RuntimeError("No s2v_unet configured for this resolution")
    if not (COMFYUI_DIR / "models" / "unet" / name).exists():
        raise RuntimeError(
            f"S2V model missing: models/unet/{name}. Download it from "
            f"QuantStack/Wan2.2-S2V-14B-GGUF before using dialogue scenes.")
    return name


def build_wan_s2v_workflow(prompt: str, audio_path: str, seed: int, clip_prefix: str, frames: int,
                           extra_chunks: int = 0, last_chunk_frames: int | None = None,
                            negative_prompt: str = "", steps: int = 25,
                            ref_image: str | None = None,
                            loras: list[tuple[str, float]] | None = None,
                            high_loras: list[tuple[str, float]] | None = None,
                            low_loras: list[tuple[str, float]] | None = None,
                            res_config: dict | None = None,
                            model_config: dict | None = None) -> dict:
    """Build a WAN 2.2 S2V (Speech-to-Video) workflow for dialogue scenes.

    Uses WanSoundImageToVideo to generate video driven by audio input,
    producing natural lip sync and expressions. Requires:
    - Audio encoder model in ComfyUI/models/audio_encoders/
    - S2V-compatible UNet (wan2.2_t2v_* works, dedicated S2V model preferred)

    Args:
        audio_path: Path to audio file (TTS-generated dialogue).
        ref_image: Character reference image for visual conditioning.
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]
    is_dual = mc.get("dual_model", False)

    wf = {
        # Text encoder + VAE
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},

        # Audio encoding
        "40": {"class_type": "AudioEncoderLoader", "inputs": {"audio_encoder_name": "wav2vec2_large_english_fp16.safetensors"}},
        "41": {"class_type": "LoadAudio", "inputs": {"audio": audio_path}},
        "42": {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["40", 0], "audio": ["41", 0]}},
    }

    # S2V conditioning — ref_image is optional but strongly recommended
    s2v_inputs = {
        "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
        "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
        "audio_encoder_output": ["42", 0],
    }
    if ref_image:
        wf["43"] = {"class_type": "LoadImage", "inputs": {"image": ref_image}}
        wf["44"] = {"class_type": "ImageScale", "inputs": {
            "image": ["43", 0], "upscale_method": "lanczos",
            "width": rc["width"], "height": rc["height"], "crop": "center"
        }}
        s2v_inputs["ref_image"] = ["44", 0]

    wf["9"] = {"class_type": "WanSoundImageToVideo", "inputs": s2v_inputs}

    # UNet + sampling (single model + KSampler — dual-model SplitSigmas causes mosaic)
    wf["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": _s2v_unet(rc)}}
    wf["10"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}}
    # Sample from node 9's CONDITIONING outputs, not the raw text encodings.
    # wan_sound_to_video() writes both the audio embedding and the ref_image's
    # VAE latent into the conditioning it returns:
    #     positive = conditioning_set_values(positive, {"audio_embed": ...})
    #     positive = conditioning_set_values(positive, {"reference_latents": [ref_latent]})
    # Taking only its latent (["9", 2]) and passing ["4", 0] / ["5", 0] to the
    # sampler threw the character reference away on every S2V shot. Measured
    # consequence: S2V identity averaged 0.777 against I2V's 0.876, and seven
    # of the eight worst shots in ep04 were dialogue shots.
    wf["11"] = {"class_type": "KSampler", "inputs": {
        "model": ["10", 0], "positive": ["9", 0], "negative": ["9", 1],
        "latent_image": ["9", 2], "seed": seed, "steps": steps, "cfg": mc["cfg"],
        "sampler_name": mc["sampler"], "scheduler": mc["scheduler"], "denoise": 1.0,
    }}

    sampled_output = "11"
    wf["16"] = {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}}
    images_output = "16"

    # ── Chained chunks: shots longer than the per-clip ceiling ────────
    # WanSoundImageToVideoExtend takes the PREVIOUS chunk's sampled latent,
    # advances the audio window by that chunk's frame count, and carries motion
    # continuity through ref_motion_latent. Chunks therefore join into ONE
    # continuous take rather than a cut.
    #
    # This is the single biggest structural limit on how the result reads. A
    # 5.06s ceiling forces roughly 17 cuts a minute; real animation holds shots
    # for 8-15s. Measured on a 10.5s line:
    #     1 chunk   5.06s   identity 0.907 -> 0.928   drift +0.021
    #     2 chunks 10.12s   identity 0.915 -> 0.925   drift +0.010
    # Twice the length, LESS drift, no visible seam.
    #
    # Extend is handed the RAW text conditioning, exactly as chunk 1 is:
    # wan_sound_to_video() re-applies the audio window and appends the
    # reference latent itself, so passing already-conditioned input would stack
    # reference_latents and overwrite the audio embed.
    if extra_chunks > 0:
        last_latent, last_images = "11", "16"
        for n in range(2, extra_chunks + 2):
            ext, ks, dec, cat = f"x{n}", f"xk{n}", f"xd{n}", f"xc{n}"
            # The final chunk is sized to what is left of the line rather than
            # padded to a full one. Rounding every take up to a whole chunk
            # bought 5 seconds of silent picture -- and a second full sampling
            # pass to render it -- for a line 0.2s over the ceiling.
            n_frames = (last_chunk_frames if (n == extra_chunks + 1
                                              and last_chunk_frames) else frames)
            wf[ext] = {"class_type": "WanSoundImageToVideoExtend", "inputs": {
                "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
                "length": n_frames, "video_latent": [last_latent, 0],
                "audio_encoder_output": ["42", 0]}}
            if ref_image:
                wf[ext]["inputs"]["ref_image"] = ["44", 0]
            wf[ks] = {"class_type": "KSampler", "inputs": {
                "model": ["10", 0], "positive": [ext, 0], "negative": [ext, 1],
                "latent_image": [ext, 2], "seed": seed + n, "steps": steps,
                "cfg": mc["cfg"], "sampler_name": mc["sampler"],
                "scheduler": mc["scheduler"], "denoise": 1.0}}
            wf[dec] = {"class_type": "VAEDecode",
                       "inputs": {"samples": [ks, 0], "vae": ["3", 0]}}
            wf[cat] = {"class_type": "ImageBatch",
                       "inputs": {"image1": [last_images, 0], "image2": [dec, 0]}}
            last_latent, last_images = ks, cat
        images_output = last_images

    wf["17"] = {"class_type": "CreateVideo", "inputs": {"images": [images_output, 0], "fps": float(mc["fps"])}}
    wf["18"] = {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": save_prefix(clip_prefix), "format": "mp4", "codec": "h264"}}

    # LoRA injection (single model)
    if loras:
        _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="10", node_id_offset=50)

    return wf


def build_wan_animate_workflow(prompt: str, ref_image: str, motion_video: str,
                                seed: int, clip_prefix: str, frames: int,
                                negative_prompt: str = "", steps: int = 25,
                                loras: list[tuple[str, float]] | None = None,
                                high_loras: list[tuple[str, float]] | None = None,
                                low_loras: list[tuple[str, float]] | None = None,
                                res_config: dict | None = None,
                                model_config: dict | None = None) -> dict:
    """Build a WAN 2.2 Animate workflow for motion transfer scenes.

    Takes a character reference image + a motion reference video and generates
    the character performing the same motion with expression replication.

    Requires:
    - Wan2.2-Animate model in ComfyUI/models/unet/
    - ComfyUI-WanVideoWrapper custom node (Kijai) with WanAnimate support

    Args:
        ref_image: Character reference image filename (in ComfyUI input/).
        motion_video: Motion reference video filename (in ComfyUI input/).
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]

    # Animate uses its own UNet — fall back to T2V if animate-specific model not configured
    animate_unet = rc.get("animate_unet", rc["t2v_unet"])

    wf = {
        # Text encoder + VAE
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},

        # Character reference image
        "43": {"class_type": "LoadImage", "inputs": {"image": ref_image}},
        "44": {"class_type": "ImageScale", "inputs": {
            "image": ["43", 0], "upscale_method": "lanczos",
            "width": rc["width"], "height": rc["height"], "crop": "center"
        }},

        # Motion reference video
        "45": {"class_type": "LoadVideo", "inputs": {"video": motion_video, "force_size": "Disabled"}},

        # WanAnimate conditioning — skeleton extraction is implicit
        "9": {"class_type": "WanAnimate", "inputs": {
            "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
            "ref_image": ["44", 0],
            "motion_video": ["45", 0],
            "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
        }},

        # UNet + sampling (single model)
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": animate_unet}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "11": {"class_type": "KSampler", "inputs": {
            "model": ["10", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["9", 2], "seed": seed, "steps": steps, "cfg": mc["cfg"],
            "sampler_name": mc["sampler"], "scheduler": mc["scheduler"], "denoise": 1.0,
        }},

        # Decode + save
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": float(mc["fps"])}},
        "18": {"class_type": "SaveVideo", "inputs": {
            "video": ["17", 0], "filename_prefix": save_prefix(clip_prefix),
            "format": "mp4", "codec": "h264"
        }},
    }

    # LoRA injection (single model for animate)
    if loras:
        _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="10", node_id_offset=50)

    return wf


def classify_scene_type(scene: dict) -> str:
    """Classify a scene into a generation mode based on its content.

    Returns:
        "s2v"           — dialogue scene with speech (uses S2V for lip sync)
        "i2v"           — action/continuation scene (uses I2V with reference image)
        "t2v"           — establishing/wide shot (uses T2V, no reference needed)
    """
    has_dialogue = bool(scene.get("dialogue"))
    has_narration = bool((scene.get("narration") or "").strip())
    has_characters = bool(scene.get("characters"))

    # Dialogue with characters → S2V (lip sync)
    if has_dialogue and has_characters:
        return "s2v"

    # Characters present but no dialogue → I2V (reference seeding)
    if has_characters:
        return "i2v"

    # No characters (establishing shot, location) → T2V
    return "t2v"


# ─── Workflow dispatch ────────────────────────────────────────────────

def build_video_workflow(video_model: str, mode: str, prompt: str, seed: int,
                          clip_prefix: str, frames: int, res_config: dict,
                          negative_prompt: str = "", steps: int = 25,
                          denoise: float = DEFAULT_DENOISE,
                          loras: list[tuple[str, float]] | None = None,
                          image_name: str | None = None,
                          audio_path: str | None = None,
                          motion_video: str | None = None,
                          optimization: str = "none",
                          extra_chunks: int = 0,
                          last_chunk_frames: int | None = None) -> dict:
    """Build a WAN video generation workflow.

    Args:
        video_model: "wan" (14B dual-model) or "wan-5b" (5B local preview).
        mode: "t2v", "i2v", "s2v" (speech-to-video), or "animate" (motion transfer).
        audio_path: Path to audio file (required for s2v mode).
        motion_video: Motion reference video filename (required for animate mode).
        optimization: "none", "balanced", "fast", or "turbo" (EasyCache presets)
        Other args passed through to the WAN workflow builders.
    """
    mc = get_model_config(video_model)

    # Resolve split high/low noise LoRA variants if they exist on disk
    high_loras, low_loras = _resolve_wan_dual_loras(loras)

    if mode == "animate" and image_name and motion_video:
        # Animate: motion transfer from reference video to character
        wf = build_wan_animate_workflow(prompt, image_name, motion_video, seed, clip_prefix, frames,
                                         negative_prompt=negative_prompt, steps=steps,
                                         loras=loras, high_loras=high_loras, low_loras=low_loras,
                                         res_config=res_config, model_config=mc)
        _insert_optimizations(wf, optimization, model_node="10")
    elif mode == "s2v" and audio_path:
        # S2V: audio-driven video with lip sync
        wf = build_wan_s2v_workflow(prompt, audio_path, seed, clip_prefix, frames,
                                     extra_chunks=extra_chunks,
                                     last_chunk_frames=last_chunk_frames,
                                     negative_prompt=negative_prompt, steps=steps,
                                     ref_image=image_name, loras=loras,
                                     high_loras=high_loras, low_loras=low_loras,
                                     res_config=res_config, model_config=mc)
        _insert_optimizations(wf, optimization, model_node="10")
    elif mode == "i2v" and image_name:
        wf = build_wan_i2v_workflow(prompt, image_name, seed, clip_prefix, frames,
                                     negative_prompt=negative_prompt, steps=steps,
                                     denoise=denoise, loras=loras,
                                     high_loras=high_loras, low_loras=low_loras,
                                     res_config=res_config, model_config=mc)
        _insert_optimizations(wf, optimization, model_node="10")
    else:
        wf = build_wan_t2v_workflow(prompt, seed, clip_prefix, frames,
                                     negative_prompt=negative_prompt, steps=steps,
                                     loras=loras,
                                     high_loras=high_loras, low_loras=low_loras,
                                     res_config=res_config, model_config=mc)
        _insert_optimizations(wf, optimization, model_node="7")

    return wf


# ─── IP-Adapter for character consistency ────────────────────────────
#
# IP-Adapter conditions the model on a reference image at inference time,
# providing much stronger appearance/face consistency than LoRAs alone.
# Requires: ComfyUI-IPAdapter-plus custom node + IP-Adapter model files.

# Default IP-Adapter model for video
IP_ADAPTER_MODEL = "ip-adapter-plus_sd15.safetensors"
IP_ADAPTER_CLIP_VISION = "sigclip_vision_patch14_384.safetensors"  # Reuse existing CLIP vision
IP_ADAPTER_DEFAULT_STRENGTH = 0.5


def _insert_ip_adapter(wf: dict, ref_image: str, strength: float = IP_ADAPTER_DEFAULT_STRENGTH,
                        model_input_node: str = "10") -> None:
    """Insert IP-Adapter nodes into a workflow for character appearance conditioning.

    Adds nodes:
      60: IPAdapterModelLoader — loads the IP-Adapter model
      61: LoadImage — loads the character reference portrait
      62: IPAdapterApply — applies reference conditioning to the model

    The IP-Adapter output replaces the model input to the sampler model node,
    inserting after any LoRA chain.

    Args:
        wf: Workflow dict to modify in-place.
        ref_image: Filename of the reference image (must be in ComfyUI/input/).
        strength: IP-Adapter conditioning strength (0.0–1.0). Default 0.5.
        model_input_node: Node ID that consumes the model (e.g. "10" for I2V ModelSamplingSD3).
    """
    # Get the current model input to the sampling node
    current_model_input = wf[model_input_node]["inputs"]["model"]

    # Add IP-Adapter nodes with IDs 60-62 (avoids collision with LoRA nodes 50-52)
    wf["60"] = {
        "class_type": "IPAdapterModelLoader",
        "inputs": {"ipadapter_file": IP_ADAPTER_MODEL},
    }
    wf["61"] = {
        "class_type": "LoadImage",
        "inputs": {"image": ref_image},
    }
    wf["62"] = {
        "class_type": "IPAdapterApply",
        "inputs": {
            "ipadapter": ["60", 0],
            "clip_vision": ["4", 0],  # Reuse the existing CLIPVisionLoader node
            "image": ["61", 0],
            "model": current_model_input,  # Chain from LoRA output or UNet
            "weight": strength,
            "noise": 0.0,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 1.0,
        },
    }

    # Point the ModelSamplingSD3 node to the IP-Adapter output
    wf[model_input_node]["inputs"]["model"] = ["62", 0]


def get_ip_adapter_ref(scene: dict, series_name: str) -> str | None:
    """Get the IP-Adapter reference image for a scene's primary character.

    Returns the filename (relative to ComfyUI/input/) or None if no reference exists.
    Only returns a reference for dialogue/close-up scenes where face consistency matters.
    """
    visual_lower = scene.get("visual", "").lower()
    is_dialogue = bool(scene.get("dialogue"))
    is_close = any(w in visual_lower for w in ["close-up", "extreme close", "ecu", "reaction"])

    # Only use IP-Adapter for scenes where character face is prominent
    if not (is_dialogue or is_close):
        return None

    characters = scene.get("characters", [])
    if not characters:
        return None

    # Use the first character's canonical portrait
    char_key = characters[0]
    char_id = char_key.removeprefix("char_")
    ref_dir = series_path(series_name) / "reference_images"
    char_ref = _find_ref(ref_dir, char_id, "char") or ref_dir / f"char_{char_id}.png"

    if char_ref.exists():
        return copy_to_input(str(char_ref))
    return None


def _char_brief(char: dict) -> str:
    """Return first sentence of character visual description as a short identifier."""
    visual = char.get("visual", "")
    first = visual.split(".")[0].strip()
    return first if first else visual[:80]


def _infer_shot_type(visual: str) -> str:
    """Infer the shot type from the scene visual description."""
    v = visual.lower()
    if any(w in v for w in ["wide shot", "establishing", "aerial", "panoramic", "long shot"]):
        return "establishing"
    if any(w in v for w in ["close-up", "extreme close", "ecu", "reaction"]):
        return "closeup"
    if any(w in v for w in ["two-shot", "medium two", "medium shot"]):
        return "medium"
    return "general"


# Camera motion tokens mapped to shot types for systematic cinematography
CAMERA_MOTION = {
    "establishing": "slow camera pan, smooth drift",
    "closeup": "static camera, locked-off tripod",
    "medium": "static camera, steady shot",
    "dialogue": "static camera, locked-off tripod",
    "action": "handheld camera, tracking shot",
    "general": "",
}


def build_scene_prompt(scene: dict, bible: dict) -> str:
    """Build a structured video generation prompt optimised for WAN 2.2.

    Prompt order matters — earlier tokens carry more weight in diffusion models.
    Structure: shot_type → trigger_words → action/composition → camera_motion → location → lighting → style

    This ordering ensures:
    - Shot framing is established first (composition anchor)
    - Character LoRAs activate early (visual identity)
    - Action/composition is the core of the prompt
    - Camera motion reinforces scene type
    - Style comes last as a subtle modifier
    """
    characters = scene.get("characters", [])
    visual = scene["visual"]
    visual_lower = visual.lower()
    is_dialogue = bool(scene.get("dialogue"))
    shot_type = _infer_shot_type(visual)

    parts: list[str] = []

    # 1. Shot type prefix — anchors the composition early
    #    Only add if the visual description doesn't already specify one
    has_shot_type = any(w in visual_lower for w in [
        "wide shot", "close-up", "medium shot", "two-shot", "establishing",
        "aerial", "long shot", "extreme close", "over-the-shoulder",
    ])
    if not has_shot_type:
        shot_labels = {
            "establishing": "Wide establishing shot",
            "closeup": "Close-up shot",
            "medium": "Medium shot",
        }
        if shot_type in shot_labels:
            parts.append(shot_labels[shot_type])

    # 2. Character trigger words — LoRAs carry the visual knowledge;
    #    for characters without LoRAs, inject a brief visual description instead
    for char_id in characters:
        char = bible.get("characters", {}).get(char_id)
        if not char:
            continue
        if char.get("lora_path"):
            # Emit the trigger word AND a brief description. The trigger is what
            # actually activates the LoRA -- without it in the prompt the LoRA
            # loads, wires correctly, and does absolutely nothing, with no error.
            # Keeping the brief too means a weak LoRA degrades to a described
            # character rather than to a stranger.
            trigger = char.get("trigger_word", "")
            if trigger:
                parts.append(trigger)
            if char.get("visual"):
                parts.append(_char_brief(char))
        elif char.get("visual"):
            parts.append(_char_brief(char))

    # 3. Scene visual — the action / composition (what the user wrote)
    parts.append(visual)

    # 4. Camera motion — systematic per shot type
    if is_dialogue:
        cam = CAMERA_MOTION["dialogue"]
    elif shot_type == "establishing":
        cam = CAMERA_MOTION["establishing"]
    elif shot_type == "closeup":
        cam = CAMERA_MOTION["closeup"]
    elif any(w in visual_lower for w in ["runs", "chase", "fight", "action", "explosion"]):
        cam = CAMERA_MOTION["action"]
    else:
        cam = CAMERA_MOTION.get(shot_type, "")
    # Only add camera motion if not already described in the visual
    if cam and not any(w in visual_lower for w in ["static", "handheld", "tracking", "pan", "push", "drift"]):
        parts.append(cam)

    # 5. Location. Close-up dialogue used to be skipped entirely, on the theory
    # that the background competes with the face. The effect was the opposite of
    # intended: with NO setting in the prompt the model invents one, so dialogue
    # close-ups came back in modern interiors and studio rooms while the scene
    # was supposed to be on a windswept cliff. Close-ups now get a short setting
    # cue -- enough to anchor the background, not enough to fight the face.
    loc_id = scene.get("location")
    if loc_id and is_dialogue and shot_type == "closeup":
        loc_desc = bible.get("world", {}).get("locations", {}).get(loc_id, "")
        if loc_desc:
            # first clause only: "A high green headland above a calm sea"
            brief = loc_desc.split(",")[0].split(".")[0].strip()
            if brief:
                parts.append(f"{brief} in the background, softly out of focus")
    elif loc_id:
        locations_meta = bible.get("locations_meta", {})
        loc_meta = locations_meta.get(loc_id) or locations_meta.get(f"loc_{loc_id}") if isinstance(locations_meta, dict) else None
        if loc_meta and isinstance(loc_meta, dict):
            loc_trigger = loc_meta.get("trigger_word", "") if loc_meta.get("lora_path") else ""
            if loc_trigger:
                parts.append(loc_trigger)
            else:
                loc_desc = bible.get("world", {}).get("locations", {}).get(loc_id, "")
                if loc_desc:
                    parts.append(loc_desc)

    # 6. Style — the first SENTENCE, not the first clause.
    # split(",")[0] kept only the text before the first comma, so a style
    # reading "Cinematic epic fantasy, photorealistic live-action film still"
    # was truncated to the genre label and the photoreal qualifier was thrown
    # away. Every prompt then ENDED on a term associated with concept art, and
    # shots collapsed into cel-shaded cartoon while "cartoon, anime" sat
    # uselessly in the negative prompt.
    series_style = bible["series"].get("style", "")
    if series_style:
        short_style = series_style.split(".")[0].strip()
        if len(short_style) > 150:
            # cut at a clause boundary, never mid-word
            cut = short_style[:150].rfind(",")
            short_style = short_style[:cut if cut > 60 else 150].strip()
        parts.append(short_style)

    # Clean up: strip trailing periods from parts before joining
    cleaned = [p.rstrip(".").strip() for p in parts if p]

    # ── Style first for S2V ──────────────────────────────────────────
    # Diffusion weights early tokens far more heavily, and the style sits LAST
    # here, where it counts least. That is fine for I2V and T2V: their seed is
    # a reference image already rendered in the series style, so the look comes
    # in through the picture rather than the words.
    #
    # S2V has no such luck. It is seeded from a character portrait, but the S2V
    # checkpoint's own prior overrides it -- a cel-shaded portrait came back as
    # a smooth 3D-CGI face with the wrong hair, in an episode where every other
    # shot was flat cel. Moving the style to the FRONT of the prompt fixed it:
    # same scene, same seed, clean linework and flat colour.
    #
    # Scoped deliberately to S2V. I2V and T2V already render correctly and
    # there is no measurement saying the reorder helps them, so they are left
    # alone rather than changed on a hunch.
    if cleaned and classify_scene_type(scene) == "s2v" and series_style:
        style_part = cleaned[-1]
        if style_part.startswith(short_style.rstrip(".")[:30]):
            # Lead with the RENDERING technique only. A palette clause at the
            # very front lands on whatever follows it, and what follows it is
            # the character: "...restrained palette of greens. Oisin." rendered
            # him with green skin, as an ogre. Colour is art direction for the
            # frame, not a description of the subject, so it stays at the back
            # where it tints the picture instead of the person.
            clauses = [c.strip() for c in style_part.split(",") if c.strip()]
            technique, colour = [], []
            for c in clauses:
                low = c.lower()
                is_colour = ("palette" in low
                             or any(w in low for w in ("greens", "blues", "gold",
                                                       "slate", "colour of", "hues")))
                (colour if is_colour else technique).append(c)
            if technique:
                cleaned = [", ".join(technique)] + cleaned[:-1]
                if colour:
                    cleaned.append(", ".join(colour))
            else:
                cleaned = [style_part] + cleaned[:-1]

    return ". ".join(filter(None, cleaned)) + "."


def build_negative_prompt(scene: dict) -> str:
    """Return a negative prompt tailored to the scene type.

    Different scene types have different failure modes:
    - Dialogue: camera shake and face blur ruin lip-sync coherence
    - Establishing: characters appearing where there should be none
    - Action: static/frozen frames defeat the purpose
    - Close-up: multiple faces or merged identities
    """
    # "painting/illustration" belongs in the negatives, not as a "not a
    # painting" phrase in the positive prompt -- diffusion models do not
    # handle negation there and will happily render what you told them not to.
    # The series is deliberately cel-shaded, so suppressing "cartoon/anime/
    # illustration" here was spending guidance to fight the look we want -- and
    # losing, unevenly, which is what produced two visual styles in one episode.
    # Keep only genuine defects.
    base = ("low quality, blurry, distorted, deformed, ugly, watermark, text overlay, "
            "oversaturated, smeared, melting, warped anatomy, extra fingers, "
            "photorealistic, live action, photograph")
    visual_lower = scene.get("visual", "").lower()
    is_dialogue = bool(scene.get("dialogue"))
    shot_type = _infer_shot_type(scene.get("visual", ""))

    extras = []
    if classify_scene_type(scene) == "s2v":
        # The S2V checkpoint's prior pulls hard toward smooth 3D-CGI faces and
        # overrides its own seed image -- a cel-shaded portrait came back as a
        # game-cutscene head in an episode where every other shot was flat cel.
        # Moving the style to the front of the prompt fixes most of it; naming
        # the failure mode here measurably improved the rest (warmer painted
        # background, the character's gold detailing preserved).
        extras.extend([
            "3d render", "cgi", "computer generated", "smooth plastic skin",
            "video game cutscene", "unreal engine", "realistic rendering",
            # The series palette is green-heavy and, front-loaded in the
            # prompt, it once tinted the character's skin rather than the
            # scene -- a close-up came back as a green ogre.
            "green skin", "tinted skin", "monster", "ogre", "orc",
        ])
    if is_dialogue:
        extras.extend([
            "fast movement", "shaky camera", "motion blur", "erratic motion",
            "camera shake", "blurry faces", "extreme camera movement",
            "multiple people merging", "face distortion",
        ])
    if shot_type == "establishing":
        extras.extend([
            "people", "characters", "close-up", "indoor",
            "portrait", "face",
        ])
    if shot_type == "closeup":
        extras.extend([
            "multiple faces", "duplicate person", "merged faces",
            "wide shot", "full body", "crowd",
        ])
    if any(w in visual_lower for w in ["runs", "chase", "fight", "action"]):
        extras.extend([
            "static", "frozen", "lifeless", "stiff movement",
            "still image", "no motion",
        ])

    if extras:
        return f"{base}, {', '.join(extras)}"
    return base


def get_scene_lora(scene: dict, bible: dict) -> tuple[str | None, float]:
    """Legacy single-LoRA interface. Returns the first character LoRA found."""
    loras = get_scene_loras(scene, bible)
    if loras:
        return loras[0]
    return None, 0.7


def lora_is_stale(lora_name: str, ref_dir: Path) -> bool:
    """Was this LoRA trained before the current reference images were made?

    A LoRA carries the STYLE of the images it was trained on, not just the
    identity. When the series style changes, every existing character LoRA is
    suddenly training data from a different show -- and it does not announce
    that, it just quietly pulls shots back toward the old look.

    Compared by mtime against the reference images, so retraining a character
    on the current anchors clears the staleness automatically rather than
    needing a flag flipped somewhere.
    """
    if not ref_dir.exists():
        return False
    refs = list(ref_dir.glob("*.png"))
    if not refs:
        return False
    newest_ref = max(r.stat().st_mtime for r in refs)
    lora_dir = COMFYUI_DIR / "models" / "loras"
    base = lora_name.removesuffix(".safetensors")
    for cand in (lora_dir / lora_name,
                 lora_dir / f"{base}-high.safetensors",
                 lora_dir / f"{base}-low.safetensors"):
        if cand.exists():
            return cand.stat().st_mtime < newest_ref
    return False


def get_scene_loras(scene: dict, bible: dict) -> list[tuple[str, float]]:
    """Return all LoRAs for a scene: up to 2 character LoRAs + 1 location/style LoRA.

    The LoRAs are chained in order:
      1. Character LoRAs (up to 2, in scene character order)
      2. Location style LoRA (if the location has one)

    Each entry is (lora_filename, strength).
    """
    loras: list[tuple[str, float]] = []

    # Character LoRAs (max 2)
    for char_id in scene.get("characters", []):
        if len(loras) >= 2:
            break
        char = bible.get("characters", {}).get(char_id)
        if char and char.get("lora_path"):
            loras.append((char["lora_path"], char.get("lora_strength", 0.7)))

    # Location style LoRA
    loc_id = scene.get("location")
    if loc_id:
        locations = bible.get("locations_meta", {})
        loc = locations.get(loc_id) or locations.get(f"loc_{loc_id}") if isinstance(locations, dict) else None
        if loc and isinstance(loc, dict) and loc.get("lora_path"):
            loras.append((loc["lora_path"], loc.get("lora_strength", 0.5)))

    return loras


# ─── Prompt enhancement via Claude ───────────────────────────────────

# ─── Crash-safe JSON state ────────────────────────────────────────────
# Production runs are expected to be interrupted (SSH drop, OOM, pod
# restart). A plain write_text() that is cut off mid-flush leaves a
# truncated file, and the next run then dies in json.loads() before it
# can resume. Read tolerantly, write atomically.

def read_json_state(path: Path, default):
    """Load JSON state, surviving a missing or half-written file."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        salvage = path.with_suffix(path.suffix + ".corrupt")
        try:
            path.replace(salvage)
            print(f"  WARNING: {path.name} was unreadable ({e}); "
                  f"moved to {salvage.name} and starting fresh")
        except OSError:
            print(f"  WARNING: {path.name} was unreadable ({e}); ignoring it")
        return default


def write_json_state(path: Path, data):
    """Write JSON so an interrupted run can never leave a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic within the same filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


PROMPT_CACHE_FILE = "prompt_cache.json"


def load_prompt_cache(ep_out: Path) -> dict:
    cache = read_json_state(ep_out / PROMPT_CACHE_FILE, {})
    return cache if isinstance(cache, dict) else {}


def save_prompt_cache(ep_out: Path, cache: dict):
    write_json_state(ep_out / PROMPT_CACHE_FILE, cache)


def enhance_scene_prompt(scene: dict, bible: dict, base_prompt: str) -> str:
    """
    Ask Claude to rewrite a raw scene visual description as a precise
    cinematographer-style video generation prompt.
    Falls back to base_prompt if Claude call fails.
    Trigger words are re-injected post-hoc to guarantee LoRA activation.
    """
    is_dialogue = bool(scene.get("dialogue"))
    visual_lower = scene.get("visual", "").lower()

    if is_dialogue:
        scene_type = "dialogue — static camera essential, faces must be clearly visible"
    elif any(w in visual_lower for w in ["wide", "aerial", "establishing", "long shot"]):
        scene_type = "establishing/wide — atmospheric, camera drift/pan acceptable"
    elif any(w in visual_lower for w in ["close-up", "reaction", "extreme close"]):
        scene_type = "reaction/close-up — extreme facial detail, locked-off camera"
    else:
        scene_type = "action/movement — camera can follow subject"

    # Collect trigger words from characters and location
    trigger_words = []
    char_descs = []
    for cid in scene.get("characters", []):
        char = bible.get("characters", {}).get(cid, {})
        if char:
            char_descs.append(f"{char.get('name', cid)}: {char.get('visual', '')}")
            tw = char.get("trigger_word", "")
            if tw and char.get("lora_path"):
                trigger_words.append(tw)

    loc_id = scene.get("location", "")
    loc_desc = bible.get("world", {}).get("locations", {}).get(loc_id, loc_id)
    loc_meta = bible.get("locations_meta", {}).get(loc_id, {})
    if isinstance(loc_meta, dict) and loc_meta.get("trigger_word") and loc_meta.get("lora_path"):
        trigger_words.append(loc_meta["trigger_word"])

    clip_sec = CLIP_LENGTHS.get(scene.get("clip_length", "medium"), CLIP_LENGTHS["medium"])["seconds"]

    trigger_line = ", ".join(trigger_words) if trigger_words else ""

    system = (
        "You are a senior cinematographer's assistant specialising in animated short-form drama. "
        "Rewrite rough scene descriptions into precise, evocative video generation prompts. "
        "IMPORTANT: Preserve all character and location names exactly as given — "
        "these are trigger words for visual model conditioning. "
        "Return ONLY the enhanced prompt text — no explanation, no preamble, no markdown."
    )

    user = f"""SCENE TYPE: {scene_type}
CLIP LENGTH: {scene.get('clip_length', 'medium')} ({clip_sec}s)
RAW DESCRIPTION: {scene['visual']}
CHARACTERS (integrate their appearance into the prompt):
{chr(10).join(char_descs) if char_descs else 'none'}
LOCATION: {loc_desc}
SERIES STYLE: {bible['series']['style']}
{f"TRIGGER WORDS (must appear verbatim in your output): {trigger_line}" if trigger_line else ""}

Rewrite as a single paragraph (90–120 words) that:
- Leads with exact shot type (Medium two-shot / Extreme close-up / Wide establishing shot / etc.)
- Names the precise lighting setup (hard sidelight, harsh white searchlight, warm amber streetlight, etc.)
- References each character's visual appearance (clothing, hair, features) at least once
- Describes character pose and expression if present
- Specifies camera movement exactly (static locked-off / slow 2mm push-in / handheld drift / etc.)
- Includes depth-of-field note (shallow / deep / rack focus)
- Ends with 3–5 texture and mood keywords matching the series style

For dialogue scenes: static camera and clear face visibility are non-negotiable.
For establishing shots: prioritise atmosphere and environment."""

    try:
        enhanced = call_claude(system, user, max_tokens=300).strip()
    except Exception as e:
        print(f"      Prompt enhancement failed ({e}) — using base prompt")
        return base_prompt

    # Post-hoc: re-inject any trigger words Claude may have dropped
    if trigger_words:
        enhanced_lower = enhanced.lower()
        missing = [tw for tw in trigger_words if tw.lower() not in enhanced_lower]
        if missing:
            enhanced = ", ".join(missing) + ". " + enhanced

    return enhanced


# ─── Clip validation ──────────────────────────────────────────────────

def validate_clip(clip_path: str) -> tuple[bool, str]:
    """
    Detect common clip failure modes. Returns (is_ok, reason).
    Checks: file size, duration, black frames, frozen/duplicate frames.
    """
    import re

    if not os.path.exists(clip_path):
        return False, "file not found"

    size = os.path.getsize(clip_path)
    if size < 20_000:
        return False, f"suspiciously small ({size // 1024}KB)"

    dur = _get_video_duration(clip_path)
    if dur < 0.5:
        return False, f"too short ({dur:.2f}s)"

    # Black frame detection — blackdetect reports intervals; sum them up
    bd = subprocess.run([
        "ffmpeg", "-i", clip_path,
        "-vf", "blackdetect=d=0.05:pix_th=0.08",
        "-an", "-f", "null", "-",
    ], capture_output=True, text=True, timeout=30)
    black_durs = [float(m) for m in re.findall(r"black_duration:([\d.]+)", bd.stderr)]
    if dur > 0 and sum(black_durs) / dur > 0.85:
        return False, f"mostly black ({sum(black_durs):.1f}s/{dur:.1f}s)"

    # Frozen frame detection — mpdecimate drops duplicate frames
    mp = subprocess.run([
        "ffmpeg", "-i", clip_path,
        "-vf", "mpdecimate", "-f", "null", "-",
    ], capture_output=True, text=True, timeout=30)
    drops = len(re.findall(r"drop\s+pts", mp.stderr))
    keeps = len(re.findall(r"keep\s+pts", mp.stderr))
    total = drops + keeps
    if total > 5 and drops / total > 0.90:
        return False, f"likely frozen ({drops}/{total} frames duplicated)"

    return True, "ok"


def validate_episode_clips(scenes: list) -> dict[str, tuple[bool, str]]:
    """Validate all clips for an episode. Returns {scene_id: (ok, reason)}."""
    results = {}
    for scene in scenes:
        clip = find_latest_clip(scene["id"])
        results[scene["id"]] = validate_clip(clip) if clip else (False, "clip not found")
    return results


def _graph_check(workflow: dict, mode: str = "?"):
    """Validate the graph before it costs GPU time.

    Ten silent defects reached finished renders in this project. Configuration
    checks, data checks and output checks all passed on every one, because the
    fault was in the GRAPH -- most expensively, an S2V sampler wired to raw
    text conditioning so the character reference was discarded on every
    dialogue shot for the life of the project.
    """
    try:
        import validate_workflow as vw
        problems = vw.check(workflow, mode)
    except Exception:                                          # noqa: BLE001
        return                                                 # never block on the checker itself
    if problems:
        print("      GRAPH PROBLEM:")
        for p_ in problems:
            print(f"        {p_}")
        if STRICT:
            raise PipelineError(
                "workflow graph is wrong before any GPU time was spent:\n         "
                + "\n         ".join(problems))


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    r = requests.post(f"{SERVER}/prompt", json={"prompt": workflow, "client_id": client_id})
    if not r.ok:
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} — {r.text[:500]}",
            response=r,
        )
    return r.json()["prompt_id"]


def poll_until_done(prompt_id: str, poll_interval: int = 10,
                    max_wait: int = 1800) -> bool:
    """Wait for a queued prompt. False means it did NOT produce output.

    This used to return a bare False for three unrelated conditions -- ComfyUI
    reported an error, the prompt vanished from the queue, or the wait ran out
    -- and every caller treated all three as "no clip, carry on". A chained S2V
    take that needed 35 minutes therefore looked exactly like a broken graph:
    thirty minutes of GPU, one line of output, no clip, no reason. Say which.
    """
    # max_wait budgets EXECUTION, not the wall clock. Time spent queued behind
    # another job used to count against it, so a prompt could be abandoned
    # having never started: tonight a 3-chunk take and three banner concepts
    # all reported "no output" while sitting in the queue, and the 3-chunk one
    # was still rendering an hour later. Only tick the budget while the prompt
    # is actually the running job.
    elapsed = 0          # execution time, the thing max_wait bounds
    waited = 0           # total wall clock, for reporting only
    queued_note = False
    inactive_checks = 0  # how many consecutive polls the job was absent from queue
    while elapsed < max_wait:
        try:
            r = requests.get(f"{SERVER}/history/{prompt_id}")
            history = r.json()
            if prompt_id in history:
                entry = history[prompt_id]
                status_str = entry.get("status", {}).get("status_str", "")
                if status_str == "error":
                    msg = entry.get("status", {}).get("messages", [])
                    print(f"\n      ComfyUI error: {msg[:200] if msg else 'unknown'}")
                    return False
                # outputs can be {} briefly before populated — check status_str
                # or non-empty outputs dict
                if entry.get("outputs") or status_str == "success":
                    return True
            q = requests.get(f"{SERVER}/queue").json()
            is_active = any(
                item[1] == prompt_id
                for item in q.get("queue_running", []) + q.get("queue_pending", [])
            )
            is_running = any(item[1] == prompt_id
                             for item in q.get("queue_running", []))
            if is_active:
                inactive_checks = 0
                if is_running:
                    elapsed += poll_interval
                    print(f"\r    Running... ({elapsed}s)    ", end="", flush=True)
                else:
                    ahead = len(q.get("queue_running", [])) + sum(
                        1 for i, item in enumerate(q.get("queue_pending", []))
                        if item[1] != prompt_id)
                    if not queued_note:
                        print(f"\n    Queued behind {ahead} job(s); the "
                              f"{max_wait}s budget starts when it does.")
                        queued_note = True
                    print(f"\r    Queued... ({waited}s waited)    ",
                          end="", flush=True)
            else:
                inactive_checks += 1
                elapsed += poll_interval
                print(f"\r    Finalizing... ({elapsed}s)    ", end="", flush=True)
                # Give ComfyUI time to write outputs after job leaves queue.
                # Only give up after 6 consecutive inactive polls (~60s of no activity).
                if inactive_checks >= 6:
                    print(f"\n      ComfyUI dropped prompt {prompt_id} from the "
                          f"queue after {elapsed}s without recording an output")
                    return False
        except requests.ConnectionError:
            print(f"\r    Reconnecting... ({elapsed}s)", end="", flush=True)
        time.sleep(poll_interval)
        waited += poll_interval
    print(f"\n      TIMEOUT after {max_wait}s of execution ({waited}s wall clock) — the job may still be running. "
          f"A chained take samples once per chunk, so raise max_wait rather "
          f"than assuming the graph is broken.")
    return False


def extract_last_frame(video_path: str, output_path: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
         "-frames:v", "1", "-q:v", "2", output_path],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"[extract_last_frame] ffmpeg failed (rc={result.returncode}): {result.stderr.decode(errors='replace')[:500]}")
        return False
    return os.path.exists(output_path)


# ComfyUI appends a counter to the prefix: "ep01_s01" -> "ep01_s01_00007_.mp4"
_CLIP_SUFFIX_RE = re.compile(r"^(_\d+_?)?\.mp4$", re.IGNORECASE)


def find_latest_clip(prefix: str, series: str | None = None) -> str | None:
    """
    Newest rendered clip for a scene id, searched within one series only.

    Suffix matching is boundary-aware rather than a bare startswith(): scene
    ids are zero-padded today, but if a generated episode ever emitted
    "ep01_s1" alongside "ep01_s10", startswith() would silently return the
    wrong scene's clip.
    """
    d = clip_dir(series)
    if not d.is_dir():
        return None
    candidates = [f for f in os.listdir(d)
                  if f.startswith(prefix) and _CLIP_SUFFIX_RE.match(f[len(prefix):])]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(d / f), reverse=True)
    return str(d / candidates[0])


def copy_to_input(src: str) -> str:
    COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    basename = os.path.basename(src)
    dest = COMFYUI_INPUT / basename
    if Path(src).resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return basename


# ─── Stitching ────────────────────────────────────────────────────────

CROSSFADE_DURATION = 0.3  # seconds of transition between clips

# Transition types — maps to FFmpeg xfade filter transition names
TRANSITIONS = {
    "dissolve":   "dissolve",      # Default — smooth blend
    "fade_black": "fade",          # Fade through black — scene changes, time jumps
    "wipe_left":  "wipeleft",      # Wipe left — action transitions
    "wipe_right": "wiperight",     # Wipe right — return transitions
    "hard_cut":   None,            # No transition — instant cut (concat)
}


def _pick_transition(scene_a: dict, scene_b: dict) -> str:
    """Auto-select a transition type based on the scene context.

    Rules:
    - Same location, dialogue→dialogue: hard_cut (natural conversation flow)
    - Different location: fade_black (signals scene change)
    - Establishing shot incoming: dissolve (atmospheric entry)
    - Action scene outgoing: wipe_left (energy carry)
    - Default: dissolve
    """
    loc_a = scene_a.get("location", "")
    loc_b = scene_b.get("location", "")
    same_location = loc_a == loc_b and loc_a

    is_dialogue_a = bool(scene_a.get("dialogue"))
    is_dialogue_b = bool(scene_b.get("dialogue"))

    visual_b = scene_b.get("visual", "").lower()
    is_establishing_b = any(w in visual_b for w in ["wide", "establishing", "aerial", "long shot"])

    visual_a = scene_a.get("visual", "").lower()
    is_action_a = any(w in visual_a for w in ["runs", "chase", "fight", "action", "explosion"])

    # Same location dialogue: hard cut for naturalism
    if same_location and is_dialogue_a and is_dialogue_b:
        return "hard_cut"

    # Location change: fade through black
    if not same_location:
        return "fade_black"

    # Entering an establishing shot: dissolve
    if is_establishing_b:
        return "dissolve"

    # Coming out of action: wipe
    if is_action_a:
        return "wipe_left"

    return "dissolve"


def _mux_clip_audio(clip_path: str, audio: Path | None, out: str,
                    ambient: Path | None = None, music: Path | None = None):
    """
    Mux a video clip with layered audio:
      [0] video
      [1] voiceover/dialogue (or lavfi silence)
      [2] ambient loop, if provided — sidechain-ducked by the VO
      [3] music bed, if provided — fixed low level

    Ducking: sidechaincompress reduces ambient -10dB whenever VO is present.
    Falls back to simple mux if the filter chain fails.
    """
    duration = _get_video_duration(clip_path) or 4.0
    # atrim only TRUNCATES. A 4.0s narration in a 5.06s clip stayed 4.0s, so the
    # muxed clip carried less audio than video; acrossfade then packed the clips
    # end-to-end on audio time while xfade used video time, and every scene
    # after the first drifted earlier. Pad to the exact clip length.
    trim = (f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={duration:.3f}")

    # ── Build input list, tracking stream indices explicitly ──────────
    cmd_inputs: list[str] = ["-i", clip_path]
    idx = 1  # [0] is video

    if audio and audio.exists():
        cmd_inputs += ["-i", str(audio)]
        vo_idx = idx; idx += 1
        has_vo = True
    else:
        cmd_inputs += ["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration:.3f}"]
        vo_idx = idx; idx += 1
        has_vo = False

    if ambient and ambient.exists():
        cmd_inputs += ["-stream_loop", "-1", "-t", str(duration + 1), "-i", str(ambient)]
        amb_idx = idx; idx += 1
        has_amb = True
    else:
        has_amb = False

    if music and music.exists():
        cmd_inputs += ["-stream_loop", "-1", "-t", str(duration + 1), "-i", str(music)]
        mus_idx = idx; idx += 1
        has_mus = True
    else:
        has_mus = False

    # ── Build filter_complex ──────────────────────────────────────────
    fp: list[str] = []

    # VO: trim + channel normalise
    fp.append(f"[{vo_idx}:a]{trim},aformat=channel_layouts=stereo[vo]")
    vo_out = "[vo]"

    if has_amb:
        fp.append(
            f"[{amb_idx}:a]{trim},aformat=channel_layouts=stereo,volume=0.35[amb_raw]"
        )
        if has_vo:
            # Sidechain: VO signal triggers gentle compression on ambient
            fp.append(
                "[amb_raw][vo]sidechaincompress="
                "threshold=0.05:ratio=3:attack=80:release=500:makeup=1[amb_out]"
            )
        else:
            fp.append("[amb_raw]volume=1.2[amb_out]")
        amb_out = "[amb_out]"
    else:
        amb_out = None

    if has_mus:
        fp.append(
            f"[{mus_idx}:a]{trim},aformat=channel_layouts=stereo,volume=0.12[mus_out]"
        )
        mus_out = "[mus_out]"
    else:
        mus_out = None

    # Final amix
    layers = [vo_out] + ([amb_out] if amb_out else []) + ([mus_out] if mus_out else [])
    # duration=shortest cut the whole mix down to the narration even when a
    # full-length ambience bed was present. Take the longest, then trim to the
    # clip so every muxed clip is exactly as long as its picture.
    pad_trim = (f"apad=whole_dur={duration:.3f},atrim=duration={duration:.3f},"
                f"asetpts=PTS-STARTPTS")
    if len(layers) == 1:
        fp.append(f"{layers[0]}{pad_trim}[audio_out]")
    else:
        fp.append(f"{''.join(layers)}amix=inputs={len(layers)}:duration=longest:"
                  f"normalize=0,{pad_trim}[audio_out]")

    result = subprocess.run([
        "ffmpeg", "-y", *cmd_inputs,
        "-filter_complex", ";".join(fp),
        "-map", "0:v:0", "-map", "[audio_out]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration),
        out,
    ], capture_output=True, timeout=120)

    # Fallback: plain mux without ambience/music
    if result.returncode != 0 or not os.path.exists(out):
        pad = ["-af", f"apad=whole_dur={duration:.3f}", "-t", f"{duration:.3f}"]
        vo_inputs = (["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", *pad]
                     if (audio and audio.exists()) else
                     ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                      "-map", "0:v:0", "-map", "1:a:0", *pad])
        subprocess.run([
            "ffmpeg", "-y", "-i", clip_path, *vo_inputs,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k", out,
        ], capture_output=True, timeout=120)


def run_ffmpeg(cmd: list, what: str, output: str | Path | None = None,
               timeout: int = 300) -> bool:
    """
    Run ffmpeg and actually check whether it worked.

    Most ffmpeg calls in this file discarded the result, so a failed stitch,
    grade or mux left the previous file in place and the pipeline carried on
    using it -- the next stage would happily grade or subtitle a stale master
    and report success. Returns True only if ffmpeg exited 0 AND the expected
    output exists and is non-trivial.
    """
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"      ERROR: {what} timed out after {timeout}s")
        return False
    if r.returncode != 0:
        tail = r.stderr.decode(errors="replace").strip().splitlines()[-4:]
        print(f"      ERROR: {what} failed (exit {r.returncode})")
        for line in tail:
            print(f"        {line[:160]}")
        return False
    if output is not None:
        f = Path(output)
        if not f.exists() or f.stat().st_size < 1024:
            print(f"      ERROR: {what} produced no usable output at {f}")
            return False
    return True


def _get_video_duration(path: str) -> float:
    """
    Duration in seconds via ffprobe, for video OR audio files.

    This used to look only for a stream with codec_type == "video", so it
    returned 0.0 for every .mp3 -- which silently disabled the "use the real
    narration length" path in generate_srt() and made callers fall back to
    nominal clip lengths without ever saying so.
    """
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path
    ], capture_output=True, text=True, timeout=15)
    try:
        data = json.loads(result.stdout)
    except Exception:
        return 0.0
    for want in ("video", "audio"):
        for stream in data.get("streams", []):
            if stream.get("codec_type") == want:
                try:
                    return float(stream.get("duration", 0))
                except (TypeError, ValueError):
                    pass
    try:
        return float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        return 0.0


def _rms(path) -> float:
    """Mean RMS of an audio file, 0.0 if unreadable."""
    try:
        import numpy as np
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000",
             "-f", "f32le", "-"], capture_output=True, timeout=120).stdout
        x = np.frombuffer(out, dtype=np.float32)
        return float(np.sqrt((x ** 2).mean())) if x.size else 0.0
    except Exception:                                          # noqa: BLE001
        return 0.0


def _gain_to(path, target_rms: float, fallback: float) -> float:
    """Multiplier that brings a file to target_rms.

    A fixed `volume=0.22` assumes the source is at a sensible level. The
    synthesised ambience beds are not: sea_waves.mp3 measures RMS 0.0050
    against a voiceover's 0.0721, so scaling it by 0.22 produced 0.0011 --
    inaudible. Measured on the finished ep04, 72% of the film was near-silent
    and only 25% carried any audible content. Scale to a TARGET instead, so a
    quiet bed is lifted and a loud one is not blasted.
    """
    r = _rms(path)
    if r <= 0:
        return fallback
    g = target_rms / r
    return max(0.05, min(g, 12.0))          # never silent, never deafening


# Voiceover sits around RMS 0.07. A bed at 0.018 is clearly present underneath
# without competing, and music below that again.
AMBIENCE_TARGET_RMS = 0.018
MUSIC_TARGET_RMS = 0.008


def build_timeline_audio(scenes: list, audio_files: list, offsets: list,
                         total: float, out_wav: Path,
                         bible: dict | None = None, use_ambience: bool = True,
                         music: Path | None = None, music_gain: float = 0.10) -> bool:
    """
    Build the whole audio track on one absolute timeline.

    The per-clip approach muxes each narration into its own clip and then joins
    clips with acrossfade -- which fades the stream boundary, so EVERY line
    fades in over the crossfade and the previous line bleeds across it. Here
    each line is simply delayed to its true start time and mixed, so nothing
    fades and nothing bleeds. Offsets come from scene_start_offsets(), which
    already accounts for the video crossfades.
    """
    inputs, filters, labels = [], [], []
    idx = 0
    for i, scene in enumerate(scenes):
        a = audio_files[i] if i < len(audio_files) else None
        if not (a and Path(a).exists()):
            continue
        inputs += ["-i", str(a)]
        ms = int(round(offsets[i] * 1000))
        filters.append(f"[{idx}:a]aformat=channel_layouts=stereo,"
                       f"adelay={ms}|{ms}[vo{idx}]")
        labels.append(f"[vo{idx}]")
        idx += 1

    if use_ambience and bible:
        for i, scene in enumerate(scenes):
            amb = get_ambient_file(scene.get("location", ""), bible)
            if not amb:
                continue
            cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
            dur = cl["frames"] / float(get_model_config(DEFAULT_VIDEO_MODEL)["fps"])
            ms = int(round(offsets[i] * 1000))
            inputs += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(amb)]
            # short fades so a bed starting mid-timeline does not click
            _g = _gain_to(amb, AMBIENCE_TARGET_RMS, 0.22)
            filters.append(f"[{idx}:a]aformat=channel_layouts=stereo,volume={_g:.3f},"
                           f"afade=t=in:st=0:d=0.25,afade=t=out:st={max(0.0, dur-0.25):.3f}:d=0.25,"
                           f"adelay={ms}|{ms}[amb{idx}]")
            labels.append(f"[amb{idx}]")
            idx += 1

    if music and Path(music).exists():
        # One continuous bed under the whole episode rather than a copy per
        # clip: a score should not restart at every cut.
        inputs += ["-stream_loop", "-1", "-t", f"{total:.3f}", "-i", str(music)]
        _mg = _gain_to(music, MUSIC_TARGET_RMS, music_gain)
        filters.append(f"[{idx}:a]aformat=channel_layouts=stereo,volume={_mg:.3f},"
                       f"afade=t=in:st=0:d=2.0,"
                       f"afade=t=out:st={max(0.0, total - 3.0):.3f}:d=3.0[mus]")
        labels.append("[mus]")
        idx += 1

    if not labels:
        return False
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:"
                   f"normalize=0,apad=whole_dur={total:.3f},atrim=duration={total:.3f}[out]")
    return run_ffmpeg(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
                       "-map", "[out]", "-c:a", "pcm_s16le", str(out_wav)],
                      "timeline audio", out_wav, timeout=300)


def stitch_clips_with_audio(scenes: list, audio_files: list, output_path: Path,
                             crossfade: bool = True, bible: dict | None = None,
                             use_ambience: bool = True, music_path: Path | None = None):
    """Stitch video clips with per-scene audio, optional ambient, and optional music bed.

    When crossfade=True, auto-selects transition types per scene boundary:
    dissolve, fade_black, wipe_left, or hard_cut based on scene context.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Step 1: mux each clip with its audio + ambient layers
        muxed = []        # (file_path, scene_dict) pairs for transition selection
        for i, scene in enumerate(scenes):
            clip_path = find_latest_clip(scene["id"])
            if not clip_path:
                print(f"    MISSING: {scene['id']}")
                continue
            out = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            audio = audio_files[i] if i < len(audio_files) else None
            ambient = (
                get_ambient_file(scene.get("location", ""), bible)
                if use_ambience and bible else None
            )
            _mux_clip_audio(clip_path, audio, out, ambient=ambient, music=music_path)
            if os.path.exists(out):
                muxed.append((out, scene))

        if not muxed:
            print("    No clips to stitch.")
            return

        muxed_files = [m[0] for m in muxed]

        if len(muxed) == 1 or not crossfade:
            # Simple concat — no transitions needed
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for c in muxed_files:
                    f.write(f"file '{c}'\n")
            run_ffmpeg([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file, "-c", "copy", str(output_path),
            ], "concat stitch", output_path, timeout=120)
            return

        # Step 2: get actual durations for xfade offset calculation
        durations = [_get_video_duration(c) for c in muxed_files]

        # Step 3: determine transition type per boundary
        transitions = []
        for i in range(len(muxed) - 1):
            t = _pick_transition(muxed[i][1], muxed[i + 1][1])
            transitions.append(t)

        # Step 4: build xfade + acrossfade filter_complex chain
        #         Hard cuts are handled by concat (no xfade filter needed)
        n = len(muxed)
        xf = CROSSFADE_DURATION

        # Check if ALL transitions are hard cuts — use simple concat
        if all(t == "hard_cut" for t in transitions):
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for c in muxed_files:
                    f.write(f"file '{c}'\n")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file, "-c", "copy", str(output_path),
            ], capture_output=True, timeout=120)
            return

        # Input args
        inputs = []
        for c in muxed_files:
            inputs += ["-i", c]

        # Build filter chains with per-boundary transition types
        v_filters = []
        a_filters = []
        offset = durations[0] - xf
        prev_v, prev_a = "[0:v]", "[0:a]"

        for i in range(1, n):
            out_v = "[vout]" if i == n - 1 else f"[xfv{i}]"
            out_a = "[aout]" if i == n - 1 else f"[xfa{i}]"

            trans_name = transitions[i - 1]
            ffmpeg_trans = TRANSITIONS.get(trans_name, "dissolve")

            if ffmpeg_trans is None:
                # hard_cut within a mixed chain — use 0-duration dissolve (effectively a cut)
                ffmpeg_trans = "dissolve"
                dur = 0.01
            else:
                dur = xf

            v_filters.append(
                f"{prev_v}[{i}:v]xfade=transition={ffmpeg_trans}:duration={dur}:offset={offset:.3f}{out_v}"
            )
            a_filters.append(
                f"{prev_a}[{i}:a]acrossfade=d={dur}:c1=tri:c2=tri{out_a}"
            )
            if i < n - 1:
                offset += durations[i] - dur
            prev_v, prev_a = out_v, out_a

        filter_complex = ";".join(v_filters + a_filters)

        run_ffmpeg([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ], "crossfade stitch", output_path, timeout=300)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def stitch_clips_silent(scenes: list, output_path: Path):
    """Stitch video clips without audio (no crossfades — used as fallback)."""
    concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        count = 0
        for scene in scenes:
            clip_path = find_latest_clip(scene["id"])
            if clip_path:
                concat_file.write(f"file '{os.path.realpath(clip_path)}'\n")
                count += 1
            else:
                print(f"    MISSING: {scene['id']}")
        concat_file.close()
        if count:
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file.name, "-c", "copy", str(output_path),
            ], capture_output=True, timeout=120)
    finally:
        os.unlink(concat_file.name)


# ─── Post-processing ──────────────────────────────────────────────────

def apply_colour_grade(input_path: Path, output_path: Path):
    """
    Apply a gritty Belfast animation colour grade:
      - Slight desaturation (70% saturation)
      - Mild S-curve for contrast and lifted blacks
      - Film grain
      - Subtle vignette
    """
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", (
            "hue=s=0.70,"                          # desaturate to 70%
            "curves=all='0/0.04 0.5/0.48 1/0.92'," # S-curve: lift blacks, pull highs
            "noise=alls=7:allf=t+u,"               # film grain (temporal+uniform)
            "vignette=PI/4"                        # edge darkening
        ),
        "-c:a", "copy",
        str(output_path),
    ], "colour grade", output_path, timeout=180)


# How long a subtitle stays up after its audio ends, so the final words of a
# line remain readable instead of disappearing mid-sentence.
SUBTITLE_TAIL = 0.45
# Cues may run this far past the next scene's start rather than clip a word.
SUBTITLE_OVERLAP = 0.30


def scene_start_offsets(scenes: list) -> list[float]:
    """
    Start time of each scene in the FINISHED film.

    stitch_clips_with_audio() overlaps neighbouring clips with xfade/acrossfade,
    so the finished film is shorter than the sum of its clips -- 16 scenes
    totalling 75.6s render as a 70.6s film. Subtitles were timed against the
    uncompressed sum, so they drifted progressively later and by the closing
    shots a cue appeared seconds after its audio had already played.

    Mirrors the stitcher: every boundary removes the transition's duration
    (CROSSFADE_DURATION, or ~0 for a hard cut).
    """
    # Prefer the MEASURED duration of the rendered clip over the nominal slot.
    # S2V sizes each clip to its audio and clamps at MAX_FRAMES, so a dialogue
    # shot is routinely 1-2.5s away from its clip_length. Timing audio and
    # subtitles against the nominal slot put them seconds out by the end of an
    # episode. Nominal is only a fallback for clips that do not exist yet.
    fps = float(get_model_config(DEFAULT_VIDEO_MODEL)["fps"])
    offsets, t = [], 0.0
    for i, scene in enumerate(scenes):
        offsets.append(t)
        cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
        dur = cl["frames"] / fps
        clip = find_latest_clip(scene["id"])
        if clip:
            measured = _get_video_duration(clip)
            if measured > 0:
                dur = measured
        t += dur
        if i < len(scenes) - 1:
            trans = TRANSITIONS.get(_pick_transition(scene, scenes[i + 1]), "dissolve")
            t -= 0.01 if trans is None else CROSSFADE_DURATION
    return offsets


def generate_srt(episode: dict, bible: dict, output_path: Path,
                 audio_files: list[Path | None] | None = None):
    """Generate an SRT subtitle file with per-character dialogue attribution.

    If audio_files are provided, uses actual audio duration for timing.
    Otherwise falls back to CLIP_LENGTHS estimates.
    """
    def srt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    entries = []
    offsets = scene_start_offsets(episode["scenes"])
    for i, scene in enumerate(episode["scenes"]):
        t = offsets[i]
        # The scene's SLOT on the timeline is the clip length. The audio only
        # decides how long the cue stays up -- using the audio length to
        # advance the timeline (as this did) desynced everything after it.
        slot = CLIP_LENGTHS.get(scene.get("clip_length", "long"),
                                CLIP_LENGTHS["long"])["seconds"]
        speech = 0.0
        if audio_files and i < len(audio_files) and audio_files[i] and audio_files[i].exists():
            speech = _get_video_duration(str(audio_files[i])) or 0.0
        dur = min(speech, slot) if speech > 0 else slot

        # A cue must outlast its speech, not undercut it. This used to show a
        # narration cue for 85% of the audio, so the last words of every line
        # vanished before they were spoken. Show the full line plus a short
        # tail, clamped so it cannot run into the next scene's cue.
        next_start = offsets[i + 1] if i + 1 < len(offsets) else t + slot + SUBTITLE_TAIL
        # A line whose speech outruns its post-crossfade slot would otherwise
        # have its last word cut. A fraction of overlap with the next cue is
        # imperceptible; a missing final word is not. Prefer the overlap.
        room = max(0.4, next_start - t + SUBTITLE_OVERLAP)

        # Build subtitle entries — separate narration from dialogue
        if scene.get("narration"):
            narr_text = scene["narration"]
            narr_dur = (dur * 0.4 if scene.get("dialogue")
                        else min(dur + SUBTITLE_TAIL, room))
            entries.append((t, t + narr_dur, narr_text))

            # Dialogue follows narration
            if scene.get("dialogue"):
                dial_start = t + narr_dur + 0.1
                dial_dur = max(0.4, min(dur, room) - narr_dur - 0.1)
                n_lines = len(scene["dialogue"])
                per_line = dial_dur / max(n_lines, 1)
                for j, d in enumerate(scene["dialogue"]):
                    char = bible.get("characters", {}).get(d["character"], {})
                    name = char.get("name", d["character"]).upper()
                    line_start = dial_start + j * per_line
                    line_end = line_start + per_line * 0.98
                    entries.append((line_start, line_end, f"{name}: \"{d['line']}\""))

        elif scene.get("dialogue"):
            # Pure dialogue — distribute time across speakers
            n_lines = len(scene["dialogue"])
            per_line = min(dur + SUBTITLE_TAIL, room) / max(n_lines, 1)
            for j, d in enumerate(scene["dialogue"]):
                char = bible.get("characters", {}).get(d["character"], {})
                name = char.get("name", d["character"]).upper()
                line_start = t + j * per_line
                line_end = line_start + per_line * 0.85
                entries.append((line_start, line_end, f"{name}: \"{d['line']}\""))


    srt_lines = []
    for i, (start, end, text) in enumerate(entries, 1):
        srt_lines.append(str(i))
        srt_lines.append(f"{srt_ts(start)} --> {srt_ts(end)}")
        srt_lines.append(text)
        srt_lines.append("")

    output_path.write_text("\n".join(srt_lines), encoding="utf-8")


def upscale_video(input_path: Path, output_path: Path, scale: int = 4) -> bool:
    """
    Upscale video using Real-ESRGAN (realesrgan-ncnn-vulkan).

    Falls back to FFmpeg lanczos if the binary is not installed.
    Returns True if upscaling succeeded.
    """
    realesrgan_bin = shutil.which("realesrgan-ncnn-vulkan")
    if not realesrgan_bin:
        # Fallback: FFmpeg lanczos upscale (lower quality but always available)
        print(f"      realesrgan-ncnn-vulkan not found — using FFmpeg lanczos {scale}x")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(input_path),
                "-vf", f"scale=iw*{scale}:ih*{scale}:flags=lanczos",
                "-c:a", "copy",
                "-preset", "fast", "-crf", "18",
                str(output_path),
            ], capture_output=True, timeout=600)
            return output_path.exists()
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"      FFmpeg upscale failed: {e}")
            return False

    # Real-ESRGAN frame-by-frame upscaling
    tmp_dir = Path(tempfile.mkdtemp())
    frames_in = tmp_dir / "frames_in"
    frames_out = tmp_dir / "frames_out"
    frames_in.mkdir()
    frames_out.mkdir()

    try:
        # 1. Extract frames
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path),
            "-qscale:v", "2",
            str(frames_in / "frame_%06d.png"),
        ], capture_output=True, timeout=300)

        frame_count = len(list(frames_in.glob("*.png")))
        if frame_count == 0:
            print("      No frames extracted")
            return False

        # 2. Get source FPS
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "csv=p=0", str(input_path),
        ], capture_output=True, text=True, timeout=30)
        fps = probe.stdout.strip() or "24"

        print(f"      Upscaling {frame_count} frames {scale}x with Real-ESRGAN...")

        # 3. Upscale frames
        subprocess.run([
            realesrgan_bin,
            "-i", str(frames_in),
            "-o", str(frames_out),
            "-s", str(scale),
            "-n", "realesrgan-x4plus-anime",  # anime-optimised model
        ], capture_output=True, timeout=600)

        # 4. Re-encode with audio from original
        subprocess.run([
            "ffmpeg", "-y",
            "-framerate", fps,
            "-i", str(frames_out / "frame_%06d.png"),
            "-i", str(input_path),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ], capture_output=True, timeout=300)

        return output_path.exists()

    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"      Upscaling failed: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def interpolate_video(input_path: Path, output_path: Path, multiplier: int = 2) -> bool:
    """
    Interpolate video frames using RIFE (rife-ncnn-vulkan) for smoother motion.

    multiplier: 2 = 24fps→48fps, 4 = 24fps→96fps (default: 2)
    Falls back gracefully if the binary is not installed.
    """
    rife_bin = shutil.which("rife-ncnn-vulkan")
    if not rife_bin:
        # rife-ncnn-vulkan is not installed here, and silently skipping meant
        # --interpolate did nothing at all. FFmpeg's motion interpolation is a
        # decent stand-in: 16fps -> 48fps on a 5s clip takes ~14s on CPU, so it
        # does not compete with the GPU, and synthesized frames come out clean.
        src_fps = 16.0
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(input_path),
        ], capture_output=True, text=True, timeout=30)
        raw = (probe.stdout or "").strip()
        if "/" in raw:
            try:
                num, den = raw.split("/"); src_fps = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass
        elif raw:
            try:
                src_fps = float(raw)
            except ValueError:
                pass
        target = int(round(src_fps * multiplier))
        print(f"      rife-ncnn-vulkan not found — FFmpeg minterpolate "
              f"{src_fps:.0f}→{target}fps")
        r = subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path),
            "-filter:v", f"minterpolate=fps={target}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "copy", str(output_path),
        ], capture_output=True, timeout=3600)
        if r.returncode == 0 and Path(output_path).exists():
            return True
        print(f"      minterpolate failed: {r.stderr.decode()[-200:]}")
        return False

    tmp_dir = Path(tempfile.mkdtemp())
    frames_in = tmp_dir / "frames_in"
    frames_out = tmp_dir / "frames_out"
    frames_in.mkdir()
    frames_out.mkdir()

    try:
        # 1. Extract frames
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path),
            "-qscale:v", "2",
            str(frames_in / "frame_%06d.png"),
        ], capture_output=True, timeout=300)

        frame_count = len(list(frames_in.glob("*.png")))
        if frame_count == 0:
            return False

        # 2. Get source FPS
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "csv=p=0", str(input_path),
        ], capture_output=True, text=True, timeout=30)
        fps_str = probe.stdout.strip() or "24"
        # Parse fractional FPS (e.g. "24000/1001")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            src_fps = float(num) / float(den)
        else:
            src_fps = float(fps_str)
        target_fps = src_fps * multiplier

        print(f"      Interpolating {frame_count} frames {multiplier}x ({src_fps:.1f}→{target_fps:.1f} fps)...")

        # 3. Run RIFE interpolation
        subprocess.run([
            rife_bin,
            "-i", str(frames_in),
            "-o", str(frames_out),
            "-m", "rife-v4.6",
            "-n", str(frame_count * multiplier),
        ], capture_output=True, timeout=600)

        out_count = len(list(frames_out.glob("*.png")))
        if out_count == 0:
            return False

        # 4. Re-encode at target FPS with audio from original
        subprocess.run([
            "ffmpeg", "-y",
            "-framerate", str(target_fps),
            "-i", str(frames_out / "%08d.png"),
            "-i", str(input_path),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ], capture_output=True, timeout=300)

        return output_path.exists()

    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"      Interpolation failed: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def burn_subtitles(input_path: Path, srt_path: Path, output_path: Path):
    """Burn SRT subtitles onto the video with styled white text."""
    style = (
        "FontName=Arial,"
        "FontSize=14,"
        "PrimaryColour=&H00FFFFFF,"   # white
        "OutlineColour=&H00000000,"   # black outline
        "BackColour=&H80000000,"      # semi-transparent shadow
        "Outline=1,"
        "Shadow=1,"
        "Bold=0,"
        "Alignment=2,"                # bottom-centre
        "MarginV=12"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-c:a", "copy",
        str(output_path),
    ], capture_output=True, timeout=180)


# ─── Reference image generation ──────────────────────────────────────

# FLUX.1-schnell GGUF — high-quality T2I model for reference image generation.
# Run scripts/download_flux.py to download all required files.
T2I_UNET  = "flux1-schnell-Q4_K_S.gguf"           # → ComfyUI/models/unet/
T2I_CLIP1 = "t5xxl_fp8_e4m3fn.safetensors"         # → ComfyUI/models/text_encoders/
T2I_CLIP2 = "clip_l.safetensors"                   # → ComfyUI/models/text_encoders/
T2I_VAE   = "ae.safetensors"                       # → ComfyUI/models/vae/


def build_t2i_workflow(
    prompt: str,
    seed: int,
    prefix: str,
    width: int = 640,
    height: int = 360,
) -> dict:
    """
    FLUX.1-schnell GGUF T2I workflow.

    Generates a high-quality still image for use as an I2V seed in WAN 2.2.
    4 inference steps (distilled model) — fast and sharp.

    width/height defaults:
      640×360  landscape (scenes, locations)
      480×640  portrait  (character headshots — pass explicitly)
    """
    return {
        "1":  {"class_type": "UnetLoaderGGUF",     "inputs": {"unet_name": T2I_UNET}},
        "2":  {"class_type": "DualCLIPLoader",      "inputs": {"clip_name1": T2I_CLIP1, "clip_name2": T2I_CLIP2, "type": "flux"}},
        "3":  {"class_type": "VAELoader",           "inputs": {"vae_name": T2I_VAE}},
        "4":  {"class_type": "CLIPTextEncode",      "inputs": {"clip": ["2", 0], "text": prompt}},
        "5":  {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6":  {"class_type": "ModelSamplingFlux",   "inputs": {"model": ["1", 0], "max_shift": 1.15, "base_shift": 0.5, "width": width, "height": height}},
        "7":  {"class_type": "RandomNoise",         "inputs": {"noise_seed": seed}},
        "8":  {"class_type": "BasicGuider",         "inputs": {"model": ["6", 0], "conditioning": ["4", 0]}},
        "9":  {"class_type": "KSamplerSelect",      "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "BasicScheduler",      "inputs": {"model": ["6", 0], "scheduler": "simple", "steps": 4, "denoise": 1.0}},
        "11": {"class_type": "SamplerCustomAdvanced","inputs": {"noise": ["7", 0], "guider": ["8", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["5", 0]}},
        "12": {"class_type": "VAEDecode",           "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage",           "inputs": {"images": ["12", 0], "filename_prefix": f"refs/{prefix}"}},
    }


def generate_reference_images(series_name: str, bible: dict, force: bool = False,
                              engine: str = "flux"):
    """
    Generate canonical reference images for all characters and locations in the bible.

    engine:
      "flux"      — FLUX.1-schnell T2I (fast, high quality stills)

    Output filenames come from _ref_name(), the same helper get_scene_seed_image()
    reads with, so semantically-keyed bibles ("niamh") and "char_N" bibles both
    resolve. Previously these two disagreed and portraits were silently unused.
    """
    ref_dir = series_path(series_name) / "reference_images"
    ref_dir.mkdir(exist_ok=True)

    style   = bible["series"].get("style", "")
    tone    = bible["series"].get("tone", "")
    setting = bible.get("world", {}).get("setting", "")

    # (prefix, label, prompt, width, height)
    items: list[tuple[str, str, str, int, int]] = []

    # Characters — portrait orientation (480×640)
    # Style goes FIRST — earliest tokens carry most weight in diffusion models.
    for char_id, char in bible.get("characters", {}).items():
        prompt_parts: list[str] = []
        if style:   prompt_parts.append(style)
        if setting: prompt_parts.append(setting)
        if tone:    prompt_parts.append(tone)
        prompt_parts.append("cinematic video frame")
        prompt_parts.append(f"portrait of {char['visual']}")
        prompt_parts.append("facing camera, neutral expression, upper body visible")
        items.append((_ref_name(char_id, "char")[:-4], f"Character: {char.get('name', char_id)}",
                       ", ".join(filter(None, prompt_parts)), 480, 640))

    # Locations — landscape orientation (640×360)
    for loc_id, loc_desc in bible.get("world", {}).get("locations", {}).items():
        prompt_parts = []
        if style:   prompt_parts.append(style)
        if setting: prompt_parts.append(setting)
        if tone:    prompt_parts.append(tone)
        prompt_parts.append("cinematic video frame")
        prompt_parts.append(loc_desc)
        prompt_parts.append("establishing shot, wide angle, no people, empty scene")
        items.append((_ref_name(loc_id, "loc")[:-4], f"Location: {loc_id}",
                       ", ".join(filter(None, prompt_parts)), 640, 360))

    refs_out = COMFYUI_DIR / "output" / "refs"
    engine_label = "FLUX T2I"
    print(f"  Generating {len(items)} reference images with {engine_label}...")

    for prefix, label, prompt, width, height in items:
        out_png = ref_dir / f"{prefix}.png"
        if out_png.exists() and not force:
            print(f"    {label} — exists, skipping")
            continue

        print(f"    {label} ({width}×{height}) [{engine_label}]...")
        wf = build_t2i_workflow(prompt, seed=999, prefix=prefix, width=width, height=height)
        _graph_check(wf, mode)
        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"      ERROR: ComfyUI not running at {SERVER}")
            return

        success = poll_until_done(prompt_id)
        if not success:
            print(f"      WARNING: generation may have failed")
            continue

        candidates = (sorted(refs_out.glob(f"{prefix}*.png"),
                             key=lambda p: p.stat().st_mtime, reverse=True)
                      if refs_out.exists() else [])
        if candidates:
            shutil.copy2(candidates[0], out_png)
            print(f"      Saved: {out_png}")
        else:
            print(f"      WARNING: output not found in {refs_out}")

    print(f"\n  Reference images saved to: {ref_dir}")


def _ref_name(key: str, prefix: str) -> str:
    """
    Canonical reference-image filename for a bible key.

    Bibles key characters either as "char_1" or semantically ("niamh"), and the
    two sides of this disagreed: generate_reference_images() wrote "{key}.png"
    while get_scene_seed_image() looked for "char_{key}.png". They only matched
    for "char_N" keys, so a semantically-keyed series generated portraits that
    were then silently never used. Both sides now call this.
    """
    return f"{prefix}_{key.removeprefix(prefix + '_')}.png"


def _find_ref(ref_dir: Path, key: str, prefix: str) -> Path | None:
    """Canonical name first, then the legacy bare "{key}.png"."""
    for name in (_ref_name(key, prefix), f"{key}.png"):
        f = ref_dir / name
        if f.exists():
            return f
    return None


def _find_set_plate(series_name: str, location: str, setup: str | None = None,
                    character: str | None = None, staging: str | None = None,
                    framing_pref: list[str] | None = None) -> Path | None:
    """Look up a plate in the persistent set library, if one has been built.

    Layout (scripts/build_sets.py):
        sets/<location>/master.png
        sets/<location>/<setup>.png
        sets/<location>/<setup>__<character>_<staging>.png

    Returns None when no set library exists, so a series that has not built one
    behaves exactly as before.
    """
    d = series_path(series_name) / "sets" / location
    if not d.is_dir():
        return None
    base = setup or "master"
    if character:
        # Prefer the requested staging, then a staging whose FRAMING matches the
        # shot, then any staging of this character.
        #
        # Framing matters as much as identity here. A plate carries its own
        # framing into the render: seeding an authored WIDE two-shot from a
        # close plate fixed the identity (0.669 -> 0.808) and turned the shot
        # into a medium, losing the geography the wide existed to establish.
        # Alphabetical fallback picked "close" for every shot.
        if staging:
            f = d / f"{base}__{character}_{staging}.png"
            if f.exists():
                return f
        for pref in (framing_pref or []):
            f = d / f"{base}__{character}_{pref}.png"
            if f.exists():
                return f
            hits = sorted(d.glob(f"*__{character}_{pref}.png"))
            if hits:
                return hits[0]
        for f in sorted(d.glob(f"{base}__{character}_*.png")):
            return f
        for f in sorted(d.glob(f"*__{character}_*.png")):
            return f
        return None
    f = d / f"{base}.png"
    if f.exists():
        return f
    f = d / "master.png"
    return f if f.exists() else None


def get_scene_seed_image(scene: dict, series_name: str, current_chain: str | None) -> str | None:
    """
    Choose the best I2V seed image for a scene, in priority order:
    1. Scene-specific FLUX reference (highest quality, set via Scene Studio)
    2. Character portrait ref (for dialogue/close-up scenes)
    3. Location reference (for establishing/wide shots)
    4. Chain from previous clip
    """
    ref_dir = series_path(series_name) / "reference_images"
    visual_lower = scene.get("visual", "").lower()

    # 0. Explicit per-scene override. Without this every scene inherits the
    #    previous frame, so a shot that has to INTRODUCE something new (a
    #    character riding in, a hard cut to a new place) is seeded with the
    #    old image and the model simply continues the old shot.
    #      "t2v"      — no seed at all; generate from the prompt alone
    #      "portrait" — force the character portrait
    #      "location" — force the location plate
    #      "chain"    — force continuity from the previous clip
    seed_mode = (scene.get("seed") or "").lower()
    if seed_mode == "t2v":
        return None

    # 1. Scene-specific reference — set explicitly via Scene Studio UI
    scene_ref_path = scene.get("reference_image")
    if scene_ref_path and Path(scene_ref_path).exists():
        return copy_to_input(scene_ref_path)

    # ── Persistent set library ───────────────────────────────────────
    # A shot seeded from the same plate as its neighbours keeps the same
    # geography: ep04 s01 and s02 share a cliff, a wind-bent tree and a
    # horizon line because both started from the same plate. The library
    # extends that from one camera position to several, and -- crucially --
    # gives CLOSE-UPS something that carries both the face and the room.
    # Without it a close-up seeds from a bare portrait and the model invents
    # a background, which is how dialogue ended up in modern interiors.
    setup = (scene.get("setup") or "").strip() or None
    staging = (scene.get("staging") or "").strip() or None
    loc_id = scene.get("location")

    # seed:"location" means the PLAIN plate, deliberately without a character
    # in it -- used when a shot is wide enough that identity does not register
    # and a staged plate would insist on a figure the shot does not want. The
    # set-library block used to run first and hand back a staged plate anyway,
    # silently ignoring the override.
    if loc_id and seed_mode not in ("t2v", "chain", "location"):
        # A TIGHT close-up keeps the bare portrait. Measured: the portrait
        # scores 1.000 against the anchor because it IS the anchor, while a
        # staged plate scores 0.908 -- so seeding a close-up from a plate
        # trades away identity signal to gain a background the frame barely
        # shows. On ep04 that cost the dialogue shots 0.02-0.04 each while the
        # wides gained 0.16-0.20. Setting for close-ups is already handled by
        # the location cue build_scene_prompt adds to the prompt, which is what
        # actually fixed the modern-interior problem.
        _is_tight = any(w in visual_lower for w in
                        ("tight close-up", "extreme close", "ecu")) or (
            "close-up" in visual_lower and "medium" not in visual_lower)
        # Only a WIDE shot benefits from a staged plate. Measured across the
        # whole of ep04 v2, which used plates everywhere:
        #
        #   wide  s09 +0.195   s02 +0.165      <- the portrait cannot fill a
        #                                         landscape, and a bare location
        #                                         plate has no face in it at all
        #   medium two-shot s13 -0.073         <- plate caps identity at 0.908
        #   close-ups       -0.020 to -0.048      while the portrait is 1.000
        #
        # Every non-wide shot lost. So the plate is for the case the portrait
        # genuinely cannot serve, and nothing else.
        # A staged plate is used wherever the portrait CANNOT deliver the
        # requested framing. The portrait is a head-and-shoulders image and
        # I2V inherits its framing: a shot written "medium shot, from the
        # waist up" rendered as an extreme close-up with the head cropped.
        #
        # An earlier rule reserved plates for wides only, on the evidence that
        # a plate cost 0.073 of IDENTITY on a medium two-shot. That measured
        # the wrong thing -- identity is worth little if the shot is not the
        # shot that was written, and a 12-close-up episode is why this pass
        # exists. Plates now cover every framing wider than a close-up.
        _needs_wider_than_portrait = (
            bool(re.search(r"\bwide\b", visual_lower))
            or "establishing" in visual_lower
            or "long shot" in visual_lower
            or "medium shot" in visual_lower
            or "medium two-shot" in visual_lower
            or "three-quarter shot" in visual_lower
            or "over-the-shoulder" in visual_lower
            or "full body" in visual_lower
            or "two-shot" in visual_lower)
        _is_close_or_dialogue = _needs_wider_than_portrait and not _is_tight
        chars = scene.get("characters") or []
        if _is_close_or_dialogue and chars:
            # Whose shot is it? For dialogue, the first speaker.
            if scene.get("dialogue"):
                spk = scene["dialogue"][0].get("character", chars[0])
                who = spk if spk in chars else chars[0]
            else:
                who = chars[0]
            # Derive the wanted framing from how the shot is written, in
            # order of preference. An authored wide must not be handed a
            # close-up plate just because it sorts first.
            if any(w in visual_lower for w in ("extreme close", "ecu")):
                pref = ["ecu", "close", "three_quarter", "medium"]
            elif "close-up" in visual_lower:
                pref = ["close", "ecu", "three_quarter", "medium"]
            elif re.search(r"\bwide\b", visual_lower) or "establishing" in visual_lower:
                pref = ["full_body", "wide_figure", "walking_away", "medium"]
            elif "over-the-shoulder" in visual_lower:
                pref = ["over_shoulder", "medium", "three_quarter"]
            elif "three-quarter shot" in visual_lower:
                pref = ["three_quarter", "medium", "full_body"]
            elif "two-shot" in visual_lower or "medium shot" in visual_lower:
                pref = ["medium", "three_quarter", "full_body", "close"]
            else:
                pref = ["medium", "three_quarter", "close"]
            staged = _find_set_plate(series_name, loc_id, setup, who, staging,
                                     framing_pref=pref)
            if staged:
                return copy_to_input(str(staged))
        # A plain setup plate has no face in it, so it is only ever right for a
        # shot with no characters. Handing one to a close-up is how shots came
        # back as empty cliffs -- and it is strictly worse than the portrait,
        # which at least carries the identity.
        if not chars:
            plate = _find_set_plate(series_name, loc_id, setup)
            if plate:
                return copy_to_input(str(plate))

    is_close = any(w in visual_lower for w in ["close-up", "extreme close", "ecu"])
    # Substring matching on "wide shot" missed "Wide static shot", "wide aerial
    # shot" and similar, so shots that read as establishing were classified as
    # close-ups. Allow words between "wide" and "shot".
    is_establishing = (
        bool(re.search(r"\bwide\b[^.]{0,20}?\bshot\b", visual_lower))
        or any(w in visual_lower for w in ("establishing", "aerial", "long shot"))
    )
    is_dialogue = bool(scene.get("dialogue"))

    has_characters = bool(scene.get("characters"))

    if seed_mode == "chain":
        return current_chain

    if seed_mode == "location" and scene.get("location"):
        # Force the plate. Previously this only stopped the establishing check
        # from being disabled, so a scene whose wording missed that check fell
        # all the way through to the chain and rendered the previous shot again.
        loc_ref = _find_ref(ref_dir, scene["location"], "loc")
        if loc_ref:
            return copy_to_input(str(loc_ref))
        fatal(f"seed:location requested but no plate for {scene['location']}",
              "Falling back re-renders the previous shot instead of the new place. "
              "Run: showrunner.py gen-refs <series>")

    # A wide shot whose SUBJECT is a character used to fall through to the
    # chain, so a scene introducing a character rendered as whatever the
    # previous shot showed — an empty landscape. Seeding it with the portrait
    # is equally wrong: I2V starts from that image, so a head-and-shoulders
    # portrait forces portrait framing onto a wide action shot.
    #
    # Falling all the way through to T2V (no seed at all) was the next attempt,
    # and it cost the series its look: with nothing to anchor rendering, a wide
    # shot free-associates from the prompt. "Cel-shaded 2D animation" came back
    # as generic 1980s anime — plate armour and a red gown instead of the
    # leather jerkin and emerald dress in the bible — while the seeded shots
    # around it looked like a different show entirely.
    #
    # The LOCATION PLATE solves both: it is already a wide composition, so
    # there is no portrait-framing to inherit, and it is rendered in the
    # series' own style, so the shot inherits the look AND the place. The
    # characters are composed into it from the prompt. Only when there is no
    # plate do we fall back to T2V.
    if is_establishing and has_characters and seed_mode not in ("portrait", "location"):
        if scene.get("location"):
            loc_ref = _find_ref(ref_dir, scene["location"], "loc")
            if loc_ref:
                return copy_to_input(str(loc_ref))
        return None

    # 2. Character portrait seed — the primary consistency mechanism for
    # WAN 2.2 I2V (IP-Adapter is not compatible).
    if has_characters and (not is_establishing or seed_mode == "portrait"):
        # For dialogue, prefer the first speaking character's portrait
        if is_dialogue and scene.get("dialogue"):
            first_speaker = scene["dialogue"][0].get("character", scene["characters"][0])
            char_key = first_speaker if first_speaker in scene["characters"] else scene["characters"][0]
        else:
            char_key = scene["characters"][0]                      # e.g. "char_1"
        char_ref = _find_ref(ref_dir, char_key, "char")
        if char_ref:
            return copy_to_input(str(char_ref))

    # 3. Establishing/wide → location reference
    # Locations are keyed as "loc_1" in scene dicts; strip prefix similarly.
    if is_establishing and scene.get("location"):
        loc_ref = _find_ref(ref_dir, scene["location"], "loc")
        if loc_ref:
            return copy_to_input(str(loc_ref))

    return current_chain


# ─── Review / flagging ────────────────────────────────────────────────

FLAGS_FILE = "flags.json"


def load_flags(ep_out: Path) -> set[str]:
    flags = read_json_state(ep_out / FLAGS_FILE, [])
    return set(flags) if isinstance(flags, list) else set()


def save_flags(ep_out: Path, flags: set[str]):
    write_json_state(ep_out / FLAGS_FILE, sorted(flags))


def update_flags(ep_out: Path, bad: set[str], checked: set[str]):
    """
    Record the latest verdict for the clips we actually examined.

    Clips in `checked` that are not in `bad` are cleared: without this the
    flag set only ever grew, so a clip regenerated successfully by a
    --flagged-only pass stayed flagged forever and every later pass
    regenerated it again. Clips outside `checked` keep their prior flag.
    """
    flags = load_flags(ep_out)
    cleared = (flags & checked) - bad
    flags = (flags - checked) | bad
    save_flags(ep_out, flags)
    return flags, cleared


# ─── Season compilation ───────────────────────────────────────────────

def make_title_card(title: str, subtitle: str, output_path: Path,
                    duration: float = 3.0, music_path: Path | None = None,
                    width: int = 480, height: int = 320):
    """Generate a title card MP4 with black background and centred white text."""
    # Find a font that exists
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    font = next((f for f in font_candidates if os.path.exists(f)), None)
    font_arg = f":fontfile={font}" if font else ""

    vf = (
        f"drawtext=text='{title}'{font_arg}:fontsize=13:fontcolor=white@0.6"
        f":x=(w-text_w)/2:y=h*0.32,"
        f"drawtext=text='{subtitle}'{font_arg}:fontsize=18:fontcolor=white"
        f":x=(w-text_w)/2:y=h*0.50,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={duration-0.4:.1f}:d=0.4"
    )

    audio_inputs: list[str] = []
    audio_filter = ""
    if music_path and music_path.exists():
        audio_inputs = ["-stream_loop", "-1", "-t", str(duration + 1), "-i", str(music_path)]
        audio_filter = f"[1:a]atrim=duration={duration},volume=0.15,afade=t=in:d=0.3,afade=t=out:st={duration-0.3:.1f}:d=0.3[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=black:s={width}x{height}:r=24:d={duration}",
        *audio_inputs,
        "-vf", vf,
    ]
    if audio_filter:
        cmd += ["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += [
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-map", "0:v", "-map", "1:a",
        ]
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration),
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


# ─── Export script ───────────────────────────────────────────────────

def export_script(episode: dict, bible: dict, output_path: Path):
    lines = []
    title = bible["series"]["title"]
    lines.append(f"{'=' * 60}")
    lines.append(f"  {title} — {episode['title']}")
    lines.append(f"  Episode {episode['id']}")
    lines.append(f"{'=' * 60}")
    lines.append(f"\nSUMMARY: {episode['summary']}\n")

    chars_in_ep = set()
    for s in episode["scenes"]:
        chars_in_ep.update(s.get("characters", []))
    if chars_in_ep:
        lines.append("VOICE NOTES:")
        for cid in sorted(chars_in_ep):
            c = bible.get("characters", {}).get(cid, {})
            lines.append(f"  {c.get('name', cid)}: {c.get('voice_notes', '-')}")
        lines.append("")

    t = 0.0
    for i, s in enumerate(episode["scenes"], 1):
        cl = CLIP_LENGTHS.get(s.get("clip_length", "long"), CLIP_LENGTHS["long"])
        dur = cl["seconds"]
        mins, secs = divmod(int(t), 60)
        lines.append(f"SCENE {i} [{mins}:{secs:02d}] ({dur}s) — {s.get('location', '?')}")
        if s.get("narration"):
            lines.append(f"  NARRATION: {s['narration']}")
        if s.get("dialogue"):
            for d in s["dialogue"]:
                c = bible.get("characters", {}).get(d["character"], {})
                lines.append(f"  {c.get('name', d['character']).upper()}: \"{d['line']}\"")
        lines.append("")
        t += dur

    lines.append(f"Total: ~{t:.0f}s\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


# ─── Commands ─────────────────────────────────────────────────────────

def cmd_gen_refs(args):
    """Generate canonical reference images for all characters and locations."""
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    print(f"\nGenerating reference images for: {bible['series']['title']}")
    engine = getattr(args, "engine", "flux")
    generate_reference_images(args.series, bible, force=args.force, engine=engine)


def cmd_review(args):
    """Interactively review generated clips and flag weak ones for regeneration."""
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    ep_num = args.episode
    ep = load_json(episode_path(args.series, ep_num))
    ep_out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}"
    flags = load_flags(ep_out)

    print(f"\n  Reviewing: {ep['title']} ({len(ep['scenes'])} scenes)")
    print(f"  Flagged for regen: {sorted(flags) or 'none'}")
    print(f"  [y] flag for regen  [u] unflag  [Enter] keep  [q] quit\n")

    for scene in ep["scenes"]:
        sid = scene["id"]
        clip = find_latest_clip(sid)
        cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
        label = "dialogue" if scene.get("dialogue") else ("narration" if scene.get("narration") else "visual")
        flagged = "⚑ FLAGGED" if sid in flags else ""
        print(f"  {sid}  [{label}]  {cl['seconds']}s  {'OK' if clip else 'MISSING'}  {flagged}")
        if scene.get("narration"):
            print(f"    narration: {scene['narration']}")
        if scene.get("dialogue"):
            for d in scene["dialogue"]:
                print(f"    {d['character']}: {d['line']}")
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "q":
            break
        elif choice == "y":
            flags.add(sid)
            print(f"    Flagged.")
        elif choice == "u":
            flags.discard(sid)
            print(f"    Unflagged.")

    save_flags(ep_out, flags)
    print(f"\n  Saved {len(flags)} flags to {ep_out / FLAGS_FILE}")
    if flags:
        print(f"  Run: python scripts/showrunner.py produce {args.series} --episode {ep_num} --flagged-only")


def cmd_compile(args):
    """Compile all produced episodes into a single season reel with title cards."""
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    series_title = bible["series"]["title"]
    music_path = AMBIENCE_DIR / "music.mp3" if (AMBIENCE_DIR / "music.mp3").exists() else None

    episodes = sorted([
        int(f.stem[2:]) for f in (sp / "episodes").glob("ep*.json")
    ])
    produced = []
    for ep_num in episodes:
        final = OUTPUT_DIR / args.series / f"ep{ep_num:02d}" / f"ep{ep_num:02d}_final.mp4"
        if final.exists():
            ep = load_json(episode_path(args.series, ep_num))
            produced.append((ep_num, ep["title"], final))

    if not produced:
        print("No produced episodes found.")
        return

    print(f"\nCompiling {len(produced)} episodes into season reel...")
    temp_dir = tempfile.mkdtemp()
    segments: list[str] = []

    try:
        for ep_num, ep_title, ep_path in produced:
            # Title card
            card_path = os.path.join(temp_dir, f"card_{ep_num:02d}.mp4")
            subtitle = ep_title.replace("'", "\\'")
            header = series_title.replace("'", "\\'")
            ep_label = f"Episode {ep_num}\\: {subtitle}"
            print(f"  Title card: Episode {ep_num} — {ep_title}")
            make_title_card(
                title=header,
                subtitle=ep_label,
                output_path=Path(card_path),
                duration=args.card_duration,
                music_path=music_path,
            )
            if os.path.exists(card_path):
                segments.append(card_path)

            # Re-encode episode to ensure consistent stream params
            norm_path = os.path.join(temp_dir, f"ep_{ep_num:02d}.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-i", str(ep_path),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-r", "24", "-ar", "44100", "-ac", "2",
                norm_path,
            ], capture_output=True, timeout=120)
            if os.path.exists(norm_path):
                segments.append(norm_path)

        if not segments:
            print("  No segments generated.")
            return

        # Concat all segments
        concat_file = os.path.join(temp_dir, "season.txt")
        with open(concat_file, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        season_out = OUTPUT_DIR / args.series / f"{args.series}_season.mp4"
        print(f"\n  Stitching season reel...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", str(season_out),
        ], capture_output=True, timeout=600)

        if season_out.exists():
            size_mb = season_out.stat().st_size / 1024 / 1024
            print(f"\n  Season reel: {season_out}  ({size_mb:.1f} MB)")
        else:
            print("  ERROR: season reel not created")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─── Clip analysis via Claude vision ─────────────────────────────────

ANALYSIS_FILE = "clip_analysis.json"
ANALYSIS_MIN_SCORE = 3  # clips scoring below this are auto-flagged


def extract_keyframes(clip_path: str, n: int = 3) -> list[str]:
    """
    Extract n evenly-spaced keyframes from a clip.
    Returns a list of base64-encoded PNG strings (empty list on failure).
    """
    import base64
    dur = _get_video_duration(clip_path)
    if dur <= 0:
        return []

    frames_b64 = []
    for i in range(n):
        t = min(dur * (i / max(n - 1, 1)), dur - 0.1)  # 0%, 50%, ~100% of clip
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        result = subprocess.run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", clip_path,
            "-frames:v", "1", "-q:v", "3", "-vf", "scale=480:320",
            tmp_path,
        ], capture_output=True, timeout=15)
        if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
            with open(tmp_path, "rb") as f:
                data = f.read()
            if data:
                frames_b64.append(base64.standard_b64encode(data).decode())
            os.unlink(tmp_path)

    return frames_b64


def analyse_clip(scene: dict, bible: dict, clip_path: str) -> dict:
    """
    Send keyframes + scene context to Claude for quality analysis.
    Returns a dict with: score, matches_intent, issues, composition_notes,
    character_accuracy, improved_prompt, should_regenerate.
    """
    frames = extract_keyframes(clip_path, n=3)
    if not frames:
        return {"score": 0, "error": "could not extract frames", "should_regenerate": True}

    char_descs = []
    for cid in scene.get("characters", []):
        char = bible.get("characters", {}).get(cid, {})
        if char:
            char_descs.append(f"{char.get('name', cid)}: {char.get('visual', '')}")

    loc_id = scene.get("location", "")
    loc_desc = bible.get("world", {}).get("locations", {}).get(loc_id, loc_id)
    clip_sec = CLIP_LENGTHS.get(scene.get("clip_length", "medium"), CLIP_LENGTHS["medium"])["seconds"]

    system = (
        "You are a video quality assessor for an animated drama series. "
        "You receive keyframes (start, middle, end) from a generated clip alongside the intended scene description. "
        "Return ONLY valid JSON — no markdown fences, no explanation."
    )

    # Build content: frames first, then the text prompt
    content: list[dict] = []
    labels = ["START FRAME", "MIDDLE FRAME", "END FRAME"]
    for i, b64 in enumerate(frames):
        content.append({"type": "text", "text": f"[{labels[i]}]"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })

    dialogue_lines = " / ".join(f"{d['character']}: {d['line']}" for d in scene.get("dialogue", []))
    content.append({"type": "text", "text": f"""
INTENDED SCENE:
  Visual: {scene['visual']}
  Narration: {scene.get('narration') or '(none)'}
  Dialogue: {dialogue_lines or '(none)'}
  Clip length: {clip_sec}s ({scene.get('clip_length', 'medium')})
  Characters: {chr(10).join(char_descs) if char_descs else '(none)'}
  Location: {loc_desc}
  Series style: {bible['series']['style']}

Analyse these three keyframes and return JSON with exactly these fields:
{{
  "score": <integer 1–5>,
  "matches_intent": <true|false>,
  "issues": ["specific problem 1", "..."],
  "composition_notes": "<framing, shot type, depth of field>",
  "character_accuracy": "<do the visible characters match their descriptions?>",
  "atmosphere": "<does lighting and mood match the series style?>",
  "improved_prompt": "<rewritten video generation prompt that would better achieve the intent, 80–120 words>",
  "should_regenerate": <true if score <= 2 or matches_intent is false>
}}

Score guide: 1=unusable (black/frozen/totally wrong), 2=poor, 3=acceptable, 4=good, 5=excellent."""})

    try:
        raw = call_claude_vision(system, content, max_tokens=800)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        result["scene_id"] = scene["id"]
        result["clip_path"] = clip_path
        return result
    except Exception as e:
        return {
            "scene_id": scene["id"],
            "score": 0,
            "error": str(e),
            "should_regenerate": True,
            "improved_prompt": "",
        }


def analyse_episode_clips(ep: dict, bible: dict, ep_out: Path,
                           min_score: int = ANALYSIS_MIN_SCORE) -> list[dict]:
    """
    Analyse all clips for an episode. Saves clip_analysis.json and clip_analysis.md.
    Returns list of analysis dicts.
    """
    results = []
    scenes = ep["scenes"]

    for i, scene in enumerate(scenes):
        clip = find_latest_clip(scene["id"])
        if not clip:
            results.append({"scene_id": scene["id"], "score": 0,
                            "error": "clip not found", "should_regenerate": True})
            print(f"    [{i+1}/{len(scenes)}] {scene['id']} — MISSING")
            continue

        print(f"    [{i+1}/{len(scenes)}] {scene['id']}...", end="", flush=True)
        analysis = analyse_clip(scene, bible, clip)
        results.append(analysis)
        score = analysis.get("score", 0)
        regen = analysis.get("should_regenerate", False)
        print(f" score={score}/5{'  ← FLAG' if regen else ''}")
        if analysis.get("issues"):
            for issue in analysis["issues"][:3]:
                print(f"        • {issue}")

    # Save JSON
    (ep_out / ANALYSIS_FILE).write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )

    # Save markdown report
    _write_analysis_report(ep, bible, results, ep_out)

    return results


def _write_analysis_report(ep: dict, bible: dict, results: list[dict], ep_out: Path):
    """Write a human-readable markdown analysis report."""
    lines = [
        f"# Clip Analysis — {ep['title']}",
        f"",
        f"Series: {bible['series']['title']}  |  Episode: {ep['id']}",
        f"",
    ]
    flagged = [r for r in results if r.get("should_regenerate")]
    lines += [
        f"**{len(results)} clips analysed — {len(flagged)} flagged for regeneration**",
        f"",
        f"---",
        f"",
    ]
    for r in results:
        sid = r.get("scene_id", "?")
        score = r.get("score", "?")
        regen = r.get("should_regenerate", False)
        flag_mark = " 🚩" if regen else ""
        lines += [f"## {sid}  —  score {score}/5{flag_mark}", ""]
        if r.get("error"):
            lines += [f"**Error:** {r['error']}", ""]
            continue
        lines += [
            f"**Matches intent:** {'Yes' if r.get('matches_intent') else 'No'}",
            f"",
            f"**Composition:** {r.get('composition_notes', '-')}",
            f"",
            f"**Character accuracy:** {r.get('character_accuracy', '-')}",
            f"",
            f"**Atmosphere:** {r.get('atmosphere', '-')}",
            f"",
        ]
        if r.get("issues"):
            lines.append("**Issues:**")
            for issue in r["issues"]:
                lines.append(f"- {issue}")
            lines.append("")
        if r.get("improved_prompt"):
            lines += [
                "**Improved prompt:**",
                f"> {r['improved_prompt']}",
                "",
            ]
        lines.append("---")
        lines.append("")

    (ep_out / "clip_analysis.md").write_text("\n".join(lines), encoding="utf-8")


def cmd_validate(args):
    """Validate all generated clips for an episode — detect blank, frozen, or corrupt clips."""
    sp = series_path(args.series)
    ep_num = args.episode
    ep = load_json(episode_path(args.series, ep_num))
    ep_out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}"

    print(f"\n  Validating clips: {ep['title']} ({len(ep['scenes'])} scenes)")
    val = validate_episode_clips(ep["scenes"])

    bad = {sid: r for sid, (ok, r) in val.items() if not ok}
    good = [sid for sid, (ok, _) in val.items() if ok]

    for sid in good:
        print(f"    {sid} — OK")
    for sid, reason in bad.items():
        print(f"    {sid} — PROBLEM: {reason}")

    if bad:
        if args.auto_flag:
            flags = load_flags(ep_out)
            flags.update(bad.keys())
            save_flags(ep_out, flags)
            print(f"\n  Auto-flagged {len(bad)} clips → {ep_out / FLAGS_FILE}")
            print(f"  Run: python scripts/showrunner.py produce {args.series} --episode {ep_num} --flagged-only")
        else:
            print(f"\n  {len(bad)} problem(s) found. Run with --auto-flag to flag them for regeneration.")
    else:
        print(f"\n  All {len(good)} clips look good!")


def cmd_analyse(args):
    """
    Analyse generated clips for an episode using Claude vision.
    Extracts keyframes, sends them to Claude with the intended scene description,
    and produces a quality report with scores and improved prompts.
    """
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    ep_num = args.episode
    ep = load_json(episode_path(args.series, ep_num))
    ep_out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}"
    ep_out.mkdir(parents=True, exist_ok=True)

    min_score = args.min_score

    print(f"\n  Analysing clips: {ep['title']} ({len(ep['scenes'])} scenes)")
    print(f"  Auto-flag threshold: score < {min_score}")
    print()

    results = analyse_episode_clips(ep, bible, ep_out, min_score=min_score)

    # Auto-flag low-scoring clips
    to_flag = [r["scene_id"] for r in results if r.get("should_regenerate") or r.get("score", 5) < min_score]
    if to_flag:
        flags = load_flags(ep_out)
        flags.update(to_flag)
        save_flags(ep_out, flags)
        print(f"\n  Flagged {len(to_flag)} clip(s) for regeneration: {to_flag}")

    # Write improved prompts back to the prompt cache so --enhance picks them up
    if args.update_cache:
        cache = load_prompt_cache(ep_out)
        updated = 0
        for r in results:
            if r.get("improved_prompt") and r.get("score", 5) < min_score:
                cache[r["scene_id"]] = r["improved_prompt"]
                updated += 1
        if updated:
            save_prompt_cache(ep_out, cache)
            print(f"  Updated prompt cache with {updated} improved prompt(s)")

    report_path = ep_out / "clip_analysis.md"
    print(f"\n  Report: {report_path}")
    print(f"  JSON:   {ep_out / ANALYSIS_FILE}")

    if to_flag:
        print(f"\n  Re-run flagged clips:")
        print(f"    python scripts/showrunner.py produce {args.series} --episode {ep_num} --flagged-only --enhance")


def cmd_setup_ambience(args):
    """Generate synthetic ambient audio files for all location types."""
    print(f"Generating ambient audio files in {AMBIENCE_DIR}/")
    print("(Each file is a synthesised loop. Replace with real recordings for best results.)\n")
    generate_ambient_files(duration=getattr(args, "duration", 60))
    print("\nAmbient types and their auto-matched locations:")
    for name, preset in AMBIENT_PRESETS.items():
        print(f"  {name:<20} — {preset['desc']}")
    print(f"\n  music.mp3 — melancholy A-minor drone (replace with your own track)")
    print(f"\nDrop any real .mp3 recording into {AMBIENCE_DIR}/ with the matching filename to override.")


def cmd_create(args):
    """Create a new series directory from template."""
    sp = series_path(args.series)
    if sp.exists():
        print(f"Series '{args.series}' already exists at {sp}")
        return
    sp.mkdir(parents=True)
    (sp / "episodes").mkdir()
    (sp / "reference_images").mkdir()
    shutil.copy2(SERIES_DIR / ".template" / "concept.json", sp / "concept.json")
    print(f"Created series: {sp}")
    print(f"  1. Edit {sp / 'concept.json'} with your series idea")
    print(f"  2. Drop reference images in {sp / 'reference_images/'}")
    print(f"  3. Run: python scripts/showrunner.py write {args.series}")


def cmd_write(args):
    """Generate bible + episode scripts via Claude."""
    sp = series_path(args.series)
    concept = load_json(sp / "concept.json")

    # Generate or load bible
    bible_path = sp / "bible.json"
    if bible_path.exists() and not args.force:
        print(f"Bible exists. Loading. (Use --force to regenerate)")
        bible = load_json(bible_path)
    else:
        print(f"Generating series bible via Claude...")
        bible = generate_bible(concept)
        save_json(bible_path, bible)
        print(f"  Saved: {bible_path}")

    total_eps = concept.get("episodes_per_season", 20)

    if args.episode:
        episodes_to_write = [args.episode]
    else:
        episodes_to_write = list(range(1, total_eps + 1))

    # Collect existing episode summaries for context
    summaries = []
    for i in range(1, total_eps + 1):
        ep_path = episode_path(args.series, i)
        if ep_path.exists():
            ep = load_json(ep_path)
            summaries.append(ep.get("summary", ""))
        else:
            summaries.append("")

    for ep_num in episodes_to_write:
        ep_path = episode_path(args.series, ep_num)
        if ep_path.exists() and not args.force:
            print(f"  Episode {ep_num} exists. Skipping. (Use --force to regenerate)")
            continue

        print(f"  Writing episode {ep_num}/{total_eps}...")
        prev = [s for s in summaries[:ep_num - 1] if s]
        ep = generate_episode(bible, concept, ep_num, total_eps, prev)
        save_json(ep_path, ep)
        summaries[ep_num - 1] = ep.get("summary", "")
        print(f"    Saved: {ep_path}")
        print(f"    Title: {ep['title']}")
        print(f"    Scenes: {len(ep['scenes'])}")

    print(f"\nDone. Run: python scripts/showrunner.py produce {args.series} --episode N")


def cmd_script(args):
    """Export voiceover scripts."""
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")

    if args.episode:
        episodes = [args.episode]
    else:
        episodes = sorted([
            int(f.stem[2:]) for f in (sp / "episodes").glob("ep*.json")
        ])

    for ep_num in episodes:
        ep = load_json(episode_path(args.series, ep_num))
        out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}" / f"ep{ep_num:02d}_script.txt"
        export_script(ep, bible, out)
        print(f"  Script: {out}")


def cmd_produce(args):
    """Produce an episode: generate video + audio + stitch."""
    set_current_series(getattr(args, "series", None))
    # Resolve video model and its configuration
    video_model = getattr(args, "video_model", DEFAULT_VIDEO_MODEL)
    mc = get_model_config(video_model)
    args.steps = mc["quality_steps"].get(getattr(args, "quality", "draft"), 15)

    # Resolve generation resolution (auto-detect VRAM or use explicit flag)
    resolution = getattr(args, "resolution", "auto")
    res_config = get_resolution_config(resolution, video_model=video_model)
    print(f"  Model: {mc['label']}")
    print(f"  Resolution: {res_config['label']} (shift={res_config['shift']})")

    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    ep_num = args.episode
    ep = load_json(episode_path(args.series, ep_num))
    scenes = ep["scenes"]
    n = len(scenes)
    ep_out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}"
    ep_out.mkdir(parents=True, exist_ok=True)

    # Export script
    script_path = ep_out / f"ep{ep_num:02d}_script.txt"
    export_script(ep, bible, script_path)

    total_dur = sum(CLIP_LENGTHS.get(s.get("clip_length", "long"), CLIP_LENGTHS["long"])["seconds"] for s in scenes)

    print(f"\n{'=' * 60}")
    print(f"  {bible['series']['title']} — {ep['title']}")
    print(f"  {n} scenes, ~{total_dur:.0f}s")
    print(f"{'=' * 60}")

    # ─── Generate TTS audio ───────────────────────────────────────
    tts_engine = getattr(args, "tts_engine", "edge")
    if not args.no_audio:
        if tts_engine == "xtts":
            print(f"\n  Generating voiceover audio (XTTS v2 with voice cloning)...")
            voice_dir = sp / "voice_samples"
            audio_files = generate_episode_audio_xtts(ep, bible, ep_out, voice_samples_dir=voice_dir)
        else:
            print(f"\n  Generating voiceover audio (Edge-TTS)...")
            audio_files = generate_episode_audio(ep, bible, ep_out)
        audio_count = sum(1 for a in audio_files if a)
        print(f"    Generated {audio_count}/{n} audio clips")
    else:
        audio_files = [None] * n

    # ─── Generate video clips ─────────────────────────────────────
    flagged_only = getattr(args, "flagged_only", False)
    flags = load_flags(ep_out) if flagged_only else set()
    if flagged_only:
        print(f"\n  --flagged-only: regenerating {len(flags)} flagged scene(s): {sorted(flags) or 'none'}")
        if not flags:
            print("  Nothing to regenerate.")

    # Load or initialise the prompt cache for enhanced prompts
    use_enhance = getattr(args, "enhance", False)
    prompt_cache = load_prompt_cache(ep_out) if use_enhance else {}
    if use_enhance:
        print(f"\n  Prompt enhancement enabled (Claude will rewrite each scene prompt)")

    # ── Cross-episode continuity ──────────────────────────────────
    # If the previous episode has a saved end-frame, use it as the I2V seed
    # for this episode's first scene so visual style carries over seamlessly.
    continuity_dir = sp / "continuity"
    continuity_dir.mkdir(exist_ok=True)
    prev_endframe = continuity_dir / f"ep{ep_num - 1:02d}_endframe.png"
    carry_over_image: str | None = None
    if not args.image and prev_endframe.exists():
        carry_over_image = copy_to_input(str(prev_endframe))
        # Announce that one is AVAILABLE, not that it will be used --
        # should_use_carry_over() decides per scene, and an authored plate
        # outranks it. Stating the outcome here contradicted the actual seed.
        print(f"\n  Cross-episode carry-over available (ep{ep_num - 1:02d} end-frame); "
              f"an authored plate for scene 1 takes precedence")

    ref_dir = sp / "reference_images"

    print(f"\n  Generating video clips...")
    current_image = None
    if args.image:
        current_image = copy_to_input(args.image)
        print(f"    Reference image: {current_image}")

    for i, scene in enumerate(scenes):
        clip_prefix = scene["id"]
        seed = args.seed_base + i + 1
        model_clip_lengths = mc["clip_lengths"]
        cl = model_clip_lengths.get(scene.get("clip_length", "long"), model_clip_lengths["long"])
        frames = cl["frames"]

        # Clip length: never SHORTER than what the script asked for.
        # This used to REPLACE the authored length with whatever the audio
        # needed, so a 5.06s atmospheric shot carrying a 2.2s line rendered as
        # a 2.5s shot. That silently discards the editing rhythm -- every shot
        # ends the instant its line does, which is the opposite of how drama is
        # cut. Extend for long audio; never truncate the authored beat.
        audio_file = audio_files[i] if i < len(audio_files) else None
        if audio_file and Path(str(audio_file)).exists():
            audio_dur = _get_video_duration(str(audio_file))
            if audio_dur > 0:
                needed = frames_for_duration(audio_dur, fps=mc["fps"])
                if needed > frames:
                    print(f"      extending {clip_prefix} to {needed} frames "
                          f"({audio_dur:.2f}s of speech)")
                frames = max(frames, needed)

        base_prompt = build_scene_prompt(scene, bible)

        if use_enhance:
            if clip_prefix in prompt_cache:
                prompt = prompt_cache[clip_prefix]
            else:
                print(f"      Enhancing prompt for {clip_prefix}...")
                prompt = enhance_scene_prompt(scene, bible, base_prompt)
                prompt_cache[clip_prefix] = prompt
                save_prompt_cache(ep_out, prompt_cache)
        else:
            prompt = base_prompt

        # Skip non-flagged scenes when in flagged-only mode (but still update chain)
        if flagged_only and clip_prefix not in flags:
            existing = find_latest_clip(clip_prefix)
            if existing:
                frame_path = str(COMFYUI_INPUT / f"chain_{clip_prefix}.png")
                if extract_last_frame(existing, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
            print(f"    [{i+1}/{n}] {clip_prefix} — SKIPPED (not flagged)")
            continue

        # Resume: skip clips that already exist (unless flagged-only overrides)
        if args.resume and not flagged_only:
            existing = find_latest_clip(clip_prefix)
            if existing:
                print(f"    [{i+1}/{n}] {clip_prefix} — SKIPPED (resume)")
                frame_path = str(COMFYUI_INPUT / f"chain_{clip_prefix}.png")
                if extract_last_frame(existing, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
                continue

        loc = scene.get("location", "?")
        neg = build_negative_prompt(scene)
        scene_label = "dialogue" if scene.get("dialogue") else ("narration" if scene.get("narration") else "visual")
        print(f"    [{i+1}/{n}] {clip_prefix} [{loc}] {cl['seconds']}s [{scene_label}]")

        # Choose seed image.
        # For the first scene of episode N+1: use the carry-over end-frame from
        # episode N so the visual style continues directly instead of jumping
        # back to a static reference image. For all other scenes keep the
        # normal priority (scene-ref > char/loc ref > chain).
        # An explicit per-scene seed beats the cross-episode carry-over. Without
        # this, scene 1 of every episode silently inherits the LAST FRAME of the
        # previous episode -- so a dawn cliff opens on the muddy ruin the last
        # episode ended in, and any "seed": "location" on that scene is ignored.
        # The carry-over exists so a new episode does not jump back to a static
        # reference after the last one ended mid-scene. It is a FALLBACK for a
        # shot that has nothing better. When the set library has a staged plate
        # for this exact setup and framing, that plate is an authored decision
        # and outranks a frame inherited from another episode -- which here put
        # ep04's closing image under ep05's opening wide.
        _planned = get_scene_seed_image(scene, args.series, current_image)
        if should_use_carry_over(i, scene, carry_over_image, _planned):
            # A carry-over frame older than the reference images means the
            # series style CHANGED after that episode was rendered. Continuing
            # from it opens the new episode in the old look, and every later
            # shot chains off it -- the failure is invisible until someone
            # watches the first ten seconds.
            _co = COMFYUI_INPUT / carry_over_image
            _refs = list((series_path(args.series) / "reference_images").glob("*.png"))
            if _refs and _co.exists():
                _newest_ref = max(r.stat().st_mtime for r in _refs)
                if _co.stat().st_mtime < _newest_ref:
                    fatal(f"{clip_prefix}: cross-episode carry-over frame predates the "
                          f"reference images",
                          "The series style changed after that episode was rendered, so "
                          "this episode would open in the old look. Give scene 1 an "
                          'explicit "seed" ("location" or "portrait"), or re-render the '
                          "previous episode.")
            seed_image = carry_over_image
            print(f"      Using cross-episode carry-over as seed")
        else:
            seed_image = get_scene_seed_image(scene, args.series, current_image)

        # Collect all LoRAs for this scene (up to 2 chars + 1 location)
        scene_loras = [] if getattr(args, "no_char_loras", False) else get_scene_loras(scene, bible)
        use_lightning = getattr(args, "lightning", False)
        use_lightning_here = use_lightning
        if scene_loras:
            for ln, ls in scene_loras:
                print(f"      LoRA: {ln} (strength={ls})")

        # Per-scene denoise: used for single-model I2V fallback (5B).
        # For dual-model I2V (14B), denoise is always 1.0 — image conditioning
        # happens via WanImageToVideo concat, not denoise strength.
        base_denoise = getattr(args, 'denoise', DEFAULT_DENOISE)
        shot = _infer_shot_type(scene.get("visual", ""))
        is_dialogue = bool(scene.get("dialogue"))
        if seed_image and (shot == "closeup" or (is_dialogue and len(scene.get("characters", [])) == 1)):
            scene_denoise = min(base_denoise, 0.70)  # Faithful for solo character scenes
        else:
            scene_denoise = base_denoise

        # Scene mode routing: animate (explicit), S2V for dialogue, I2V for character, T2V for establishing.
        motion_video = getattr(args, "motion_video", None)
        scene_type = classify_scene_type(scene)
        audio_for_s2v: str | None = None
        if motion_video and seed_image:
            # Explicit animate mode — motion transfer from reference video
            mode = "animate"
        elif (scene_type == "s2v" and audio_file and Path(str(audio_file)).exists()
              and (COMFYUI_DIR / "models" / "audio_encoders" / "wav2vec2_large_english_fp16.safetensors").exists()):
            mode = "s2v"
            # LoadAudio resolves names against ComfyUI's input directory and
            # declares `audio` as a combo built from os.listdir(input_dir), so a
            # path pointing outside that directory is not a safe thing to pass.
            # Stage it in, exactly as images are staged with copy_to_input().
            audio_for_s2v = copy_to_input(str(audio_file))
            # Ensure S2V has a ref_image for character consistency
            if not seed_image and scene.get("characters"):
                char_key = scene["characters"][0]
                char_ref = _find_ref(ref_dir, char_key, "char")
                if char_ref:
                    seed_image = copy_to_input(str(char_ref))
                    print(f"      S2V ref_image fallback: {char_key} portrait")
        elif scene_type == "s2v":
            # S2V scene but no audio available — fall back to I2V
            mode = "i2v" if seed_image else "t2v"
        elif scene_type == "i2v" and seed_image:
            mode = "i2v"
        elif seed_image and (scene.get("seed") or "").lower() in ("location", "portrait", "chain"):
            # classify_scene_type() calls every characterless scene "t2v", which
            # made the mode routing discard seed_image — so location plates were
            # resolved and then never used, and an explicit per-scene seed on a
            # characterless shot was silently ignored. Honour the override.
            mode = "i2v"
        else:
            mode = "t2v"

        # A character LoRA trained on the PREVIOUS series style drags an S2V
        # shot back to that style. Measured on this episode: Niamh via I2V came
        # back correctly cel-shaded (the cel seed image dominates), while Oisin
        # via S2V came back photoreal in the same episode -- S2V leans far less
        # on its seed, so the LoRA wins. Dropping the stale LoRA costs some
        # likeness on those shots and keeps the episode in one style, which is
        # the trade that matters. Retraining on the current anchors clears this
        # automatically, since the check is by mtime.
        if mode == "s2v" and scene_loras:
            # Character LoRAs are trained against the T2V checkpoints
            # (wan2.2_t2v_{low,high}_noise_14B). S2V renders with a different
            # model family entirely (Wan2.2-S2V-14B), and applying a LoRA
            # across families degrades rather than helps -- the same reason the
            # Lightning distill LoRAs are already skipped here.
            #
            # Measured: ep04_s03 with a freshly trained, correctly built rank-64
            # character LoRA went identity 0.782 -> 0.644 and, far worse, the
            # cel-style score collapsed 0.999 -> 0.001. The shot came back
            # photoreal in a cel-shaded series. The training data was verified
            # 12/12 animated, so the data was not the problem; the checkpoint
            # mismatch was.
            print(f"      Dropped {len(scene_loras)} character LoRA(s) for S2V: "
                  f"{', '.join(n for n, _ in scene_loras)}")
            print(f"      (trained on the T2V checkpoint; S2V is a different "
                  f"model family)")
            scene_loras = []

        # Chunk a dialogue shot that runs past the single-sample ceiling, so
        # the authored beat survives instead of being clipped to 5.06s. An
        # explicit "chunks": N on the scene forces a hold longer than its line
        # -- that is how a 12-second beat is written.
        extra_chunks, last_chunk_frames = 0, None
        if mode == "s2v":
            _want = max(float(scene.get("hold_seconds") or 0.0),
                        _get_video_duration(str(audio_file)) if audio_file else 0.0)
            _spoken = _get_video_duration(str(audio_file)) if audio_file else 0.0
            frames, extra_chunks, last_chunk_frames = s2v_chunks_for_duration(
                _want, fps=mc["fps"], floor_seconds=_spoken)
            if scene.get("chunks"):
                extra_chunks = max(0, min(MAX_S2V_CHUNKS, int(scene["chunks"])) - 1)
                if extra_chunks:
                    frames, last_chunk_frames = S2V_CHUNK_FRAMES, None
            _secs = (extra_chunks * frames
                     + (last_chunk_frames or frames)) / mc["fps"]
            if extra_chunks:
                print(f"      Extended take: {extra_chunks + 1} chained chunks "
                      f"= {_secs:.2f}s")
            # Give the audio encoder the WHOLE take. Anything past the end of
            # the line must be audible silence, not absent audio.
            if audio_file and _spoken > 0 and _secs > _spoken + 0.02:
                _padded = str(Path(str(audio_file)).with_name(
                    f"{clip_prefix}_padded.mp3"))
                pad_audio_to(str(audio_file), _secs, _padded)
                audio_for_s2v = copy_to_input(_padded)
                print(f"      Padded audio {_spoken:.2f}s -> {_secs:.2f}s so the "
                      f"mouth is not driven by absent audio")
            # A line past MAX_S2V_CHUNKS is silently cut off mid-sentence --
            # the same class of defect as narration over budget, which is
            # already fatal. Say so rather than shipping a truncated take.
            if _want - _secs > 0.25:
                fatal(f"{clip_prefix}: {_want:.2f}s of speech does not fit in "
                      f"{_secs:.2f}s of picture",
                      f"A take caps at {MAX_S2V_CHUNKS} chunks "
                      f"({MAX_S2V_CHUNKS * S2V_CHUNK_FRAMES / mc['fps']:.2f}s). "
                      f"Split the line across two shots, or shorten it.")

        if mode == "animate":
            print(f"      Mode: Animate (motion transfer) — ref: {motion_video}")
        elif mode == "s2v":
            print(f"      Mode: S2V (speech-to-video) — audio: {audio_for_s2v}")
        elif mode == "i2v":
            print(f"      Mode: I2V (dual-model) — seed: {seed_image}")
        else:
            print(f"      Mode: T2V")

        optimization = getattr(args, "optimization", "balanced")
        build_loras = list(scene_loras)
        build_steps = args.steps
        if use_lightning:
            # The distilled LoRA goes on the expert(s) this mode actually
            # samples with: T2V here is single (high-noise) model, I2V is dual.
            if mode in ("s2v", "animate"):
                # The distill LoRAs are trained for the T2V and I2V checkpoints.
                # Applying the T2V one to the S2V model is a different model
                # family -- it would degrade the result rather than speed it up.
                print(f"      Lightning: skipped for {mode} (no distill LoRA for this model)")
                use_lightning_here = False
            else:
                build_loras += (LIGHTNING["i2v"] if mode == "i2v" else LIGHTNING["t2v"])
                use_lightning_here = True
            if use_lightning_here:
                build_steps = getattr(args, "lightning_steps", None) or LIGHTNING["steps"]
                print(f"      Lightning: {build_steps} steps, cfg {LIGHTNING['cfg']}")
        wf = build_video_workflow(
            video_model, mode, prompt, seed, clip_prefix, frames, res_config,
            negative_prompt=neg, steps=build_steps, denoise=scene_denoise,
            loras=build_loras, image_name=seed_image,
            audio_path=audio_for_s2v, motion_video=motion_video,
            optimization=optimization, extra_chunks=extra_chunks,
            last_chunk_frames=last_chunk_frames,
        )
        if use_lightning and use_lightning_here:
            apply_lightning(wf, steps=build_steps)

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"      ERROR: ComfyUI not running at {SERVER}")
            sys.exit(1)
        except requests.HTTPError as e:
            print(f"      ERROR: ComfyUI rejected workflow — {e}")
            continue

        # A chained take samples once PER CHUNK, so a 3-chunk shot needs roughly
        # three times the wall clock of a single one. The fixed 30-minute wait
        # abandoned a 3-chunk test that was still running, reported "no clip
        # produced", and looked exactly like a broken graph.
        success = poll_until_done(
            prompt_id, max_wait=1800 * (1 + extra_chunks))
        if not success:
            # Check if clip was actually generated despite polling failure
            clip_path = find_latest_clip(clip_prefix)
            if clip_path:
                print(f"\n      Polling lost track but clip was generated — recovering")
                success = True
            else:
                # Retry once: re-queue the same workflow
                print(f"\n      WARNING: Generation may have failed — retrying once...")
                try:
                    prompt_id = queue_prompt(wf)
                    success = poll_until_done(prompt_id)
                except (requests.ConnectionError, requests.HTTPError) as e:
                    print(f"      Retry failed: {e}")
        if success:
            print(f"\n      Done!")
            clip_path = find_latest_clip(clip_prefix)
            if clip_path:
                frame_path = str(COMFYUI_INPUT / f"chain_{clip_prefix}.png")
                if extract_last_frame(clip_path, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
        else:
            print(f"\n      FAILED: Clip not generated after retry")
            # Reset chain to character portrait so next scene doesn't use stale frame
            if scene.get("characters"):
                fallback_char = scene["characters"][0]
                fallback_id = fallback_char.removeprefix("char_")
                fallback_ref = _find_ref(ref_dir, fallback_char, "char")
                if fallback_ref:
                    current_image = copy_to_input(str(fallback_ref))
                    print(f"      Chain reset to {fallback_char} portrait")
                else:
                    fatal(f"chain broken and no portrait fallback for {fallback_char}",
                          "The next shot would seed from a stale or missing frame.")
            else:
                fatal("chain broken and the scene has no characters to fall back to",
                      "The next shot would seed from a stale or missing frame.")

    # ─── Save end-frame for next episode's carry-over ────────────
    # current_image is the last chain frame filename (relative to COMFYUI_INPUT).
    # Copy it into the continuity directory so ep N+1 can use it as its scene-1 seed.
    if current_image:
        last_chain_src = COMFYUI_INPUT / current_image
        if last_chain_src.exists():
            ep_endframe = continuity_dir / f"ep{ep_num:02d}_endframe.png"
            shutil.copy2(last_chain_src, ep_endframe)
            print(f"\n  End-frame saved → continuity/ep{ep_num:02d}_endframe.png")

    # ─── Validate clips ──────────────────────────────────────────
    print(f"\n  Validating clips...")
    val_results = validate_episode_clips(scenes)
    bad_clips = {sid: reason for sid, (ok, reason) in val_results.items() if not ok}
    # Every validated clip gets its verdict recorded, so clips that a
    # --flagged-only pass has since fixed are un-flagged rather than
    # staying flagged forever.
    _, cleared = update_flags(ep_out, set(bad_clips), set(val_results))
    if bad_clips:
        print(f"  WARNING: {len(bad_clips)} bad clip(s) detected:")
        for sid, reason in bad_clips.items():
            print(f"    {sid} — {reason}")
        print(f"  Bad clips auto-flagged.")
        fatal(f"{len(bad_clips)} clip(s) failed validation",
              "Stitching them produces a finished-looking episode with broken shots "
              "in it. Re-run with --flagged-only to regenerate just these.")
    else:
        print(f"    All {len(val_results)} clips OK")
    if cleared:
        print(f"  Cleared {len(cleared)} previously-flagged clip(s) now passing: "
              f"{', '.join(sorted(cleared))}")

    # ─── Auto-analyse with Claude vision ─────────────────────────
    use_auto_analyse = getattr(args, "auto_analyse", False)
    if use_auto_analyse:
        print(f"\n  Running Claude vision analysis...")
        analysis_results = analyse_episode_clips(ep, bible, ep_out)
        flagged_by_analysis = set()
        for ar in analysis_results:
            if ar.get("should_regenerate"):
                flagged_by_analysis.add(ar["scene_id"])
            # Update prompt cache with improved prompts from analysis
            improved = ar.get("improved_prompt")
            if improved and ar["scene_id"] not in prompt_cache:
                prompt_cache[ar["scene_id"]] = improved
        analysed = {ar["scene_id"] for ar in analysis_results if ar.get("scene_id")}
        _, cleared = update_flags(ep_out, flagged_by_analysis, analysed)
        save_prompt_cache(ep_out, prompt_cache)
        if flagged_by_analysis:
            print(f"  Analysis flagged {len(flagged_by_analysis)} clip(s) for regeneration")
            print(f"  Re-run with --flagged-only --enhance to regenerate with improved prompts")
        else:
            print(f"  All clips passed analysis")
        if cleared:
            print(f"  Cleared {len(cleared)} previously-flagged clip(s) now passing analysis")

    # ─── Lip sync (dialogue scenes only) ─────────────────────────
    use_lip_sync = getattr(args, "lip_sync", False)
    if use_lip_sync:
        print(f"\n  Applying lip sync to dialogue scenes...")
        synced = 0
        for i, scene in enumerate(scenes):
            if not scene.get("dialogue"):
                continue
            clip_path = find_latest_clip(scene["id"])
            audio = audio_files[i] if i < len(audio_files) else None
            if not clip_path or not audio or not Path(str(audio)).exists():
                continue

            synced_path = Path(clip_path).with_suffix(".lipsync.mp4")
            print(f"    {scene['id']}...")
            if apply_lip_sync(Path(clip_path), Path(str(audio)), synced_path):
                # Replace the original clip with the lip-synced version
                shutil.move(str(synced_path), clip_path)
                synced += 1
        print(f"    Lip-synced {synced} dialogue scene(s)")

    # ─── Stitch ──────────────────────────────────────────────────
    print(f"\n  Stitching episode...")
    stitched = ep_out / f"ep{ep_num:02d}_stitched.mp4"

    # Pick music bed: explicit --music-bed arg, else auto-detect from concept tone
    if args.no_music:
        music_path = None
    elif getattr(args, "music_bed", None):
        music_path = AMBIENCE_DIR / args.music_bed
        music_path = music_path if music_path.exists() else None
    else:
        concept_path = series_path(args.series) / "concept.json"
        concept_tone = ""
        if concept_path.exists():
            concept_tone = load_json(concept_path).get("tone", "").lower()
        is_comedy = any(w in concept_tone for w in ["comedy", "sitcom", "funny", "comic", "humour", "humor"])
        bed_name = "music_comedy.mp3" if is_comedy else "music.mp3"
        candidate = AMBIENCE_DIR / bed_name
        music_path = candidate if candidate.exists() else (AMBIENCE_DIR / "music.mp3" if (AMBIENCE_DIR / "music.mp3").exists() else None)
    use_amb = not args.no_ambience

    if not args.no_audio and any(a for a in audio_files):
        stitch_clips_with_audio(
            scenes, audio_files, stitched,
            crossfade=not args.no_crossfade,
            bible=bible,
            use_ambience=use_amb,
            music_path=music_path,
        )
    else:
        stitch_clips_silent(scenes, stitched)

    # ─── Rebuild the audio on one absolute timeline ───────────────
    # stitch_clips_with_audio() muxes each line into its own clip and joins the
    # clips with acrossfade. acrossfade has no offset parameter -- unlike the
    # video's xfade, which is given an explicit offset per boundary -- so audio
    # timing comes from the concatenated stream lengths alone. Every clip's AAC
    # encode adds a little priming delay, and those add up: measured on ep04,
    # dialogue ran +0.017s late at shot 3 and +0.148s late by shot 15, growing
    # monotonically. That is the "lip sync doesn't quite line up" symptom, and
    # it gets worse the longer the episode.
    #
    # build_timeline_audio() delays each line to its true start time and mixes,
    # so a line's position cannot depend on anything before it. Nothing to
    # accumulate.
    if not args.no_audio and any(a for a in audio_files) and stitched.exists():
        total = _get_video_duration(str(stitched))
        tl_wav = ep_out / f"ep{ep_num:02d}_timeline.wav"
        offsets = scene_start_offsets(scenes)
        if total > 0 and build_timeline_audio(
                scenes, audio_files, offsets, total, tl_wav,
                bible=bible, use_ambience=use_amb, music=music_path):
            relaid = ep_out / f"ep{ep_num:02d}_relaid.mp4"
            ok = run_ffmpeg([
                "ffmpeg", "-v", "error", "-y",
                "-i", str(stitched), "-i", str(tl_wav),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(relaid),
            ], "relay audio on absolute timeline")
            if ok and relaid.exists():
                stitched = relaid
                print(f"    Audio relaid on absolute offsets "
                      f"(no per-cut accumulation)")
            else:
                print(f"    WARNING: timeline relay failed — keeping per-clip audio")

    current = stitched

    # ─── Upscale ──────────────────────────────────────────────────
    if getattr(args, "upscale", False) and current.exists():
        print(f"  Upscaling video...")
        upscaled = ep_out / f"ep{ep_num:02d}_upscaled.mp4"
        if upscale_video(current, upscaled, scale=getattr(args, "upscale_factor", 4)):
            current = upscaled

    # ─── Frame interpolation ─────────────────────────────────────
    if getattr(args, "interpolate", False) and current.exists():
        print(f"  Interpolating frames...")
        interpolated = ep_out / f"ep{ep_num:02d}_interpolated.mp4"
        if interpolate_video(current, interpolated, multiplier=2):
            current = interpolated

    # ─── Colour grade ────────────────────────────────────────────
    if not args.no_grade and current.exists():
        print(f"  Applying colour grade...")
        graded = ep_out / f"ep{ep_num:02d}_graded.mp4"
        apply_colour_grade(current, graded)
        if graded.exists():
            current = graded

    # ─── Subtitles ───────────────────────────────────────────────
    if not args.no_subs and current.exists():
        print(f"  Burning subtitles...")
        srt_path = ep_out / f"ep{ep_num:02d}.srt"
        generate_srt(ep, bible, srt_path, audio_files=audio_files)
        subbed = ep_out / f"ep{ep_num:02d}_final.mp4"
        burn_subtitles(current, srt_path, subbed)
        if subbed.exists():
            current = subbed

    # Rename to final if no subtitle step was run
    final = ep_out / f"ep{ep_num:02d}_final.mp4"
    if current != final and current.exists():
        shutil.copy2(current, final)

    print(f"\n{'=' * 60}")
    print(f"  Output: {final}")
    print(f"  Script: {script_path}")
    print(f"{'=' * 60}\n")


def cmd_produce_all(args):
    """Produce all episodes in sequence."""
    set_current_series(getattr(args, "series", None))
    sp = series_path(args.series)
    episodes = sorted([
        int(f.stem[2:]) for f in (sp / "episodes").glob("ep*.json")
    ])
    print(f"Producing {len(episodes)} episodes...")
    for ep_num in episodes:
        args.episode = ep_num
        cmd_produce(args)


def cmd_status(args):
    """Show series status."""
    sp = series_path(args.series)
    if not sp.exists():
        print(f"Series '{args.series}' not found.")
        return

    has_concept = (sp / "concept.json").exists()
    has_bible = (sp / "bible.json").exists()
    episodes = sorted((sp / "episodes").glob("ep*.json"))

    print(f"\n  {args.series}")
    print(f"  {'=' * 50}")
    print(f"  Concept:  {'OK' if has_concept else 'MISSING'}")
    print(f"  Bible:    {'OK' if has_bible else 'NOT GENERATED'}")
    print(f"  Episodes: {len(episodes)} written")

    if has_bible:
        bible = load_json(sp / "bible.json")
        print(f"  Title:    {bible['series']['title']}")

    for ep_file in episodes:
        ep = load_json(ep_file)
        ep_num = int(ep_file.stem[2:])
        ep_out = OUTPUT_DIR / args.series / f"ep{ep_num:02d}"
        has_video = (ep_out / f"ep{ep_num:02d}_final.mp4").exists()
        status = "PRODUCED" if has_video else "scripted"
        n_scenes = len(ep.get("scenes", []))
        print(f"    ep{ep_num:02d}: {ep['title']:30s}  {n_scenes} scenes  [{status}]")

    print()


# ─── Storyboard preview ──────────────────────────────────────────────

def cmd_storyboard(args):
    """Generate a storyboard: one still frame per scene for quick review before video production."""
    sp = series_path(args.series)
    bible = load_json(sp / "bible.json")
    ep_num = args.episode
    ep = load_json(episode_path(args.series, ep_num))
    scenes = ep["scenes"]
    n = len(scenes)

    resolution = getattr(args, "resolution", "auto")
    res_config = get_resolution_config(resolution)
    engine = getattr(args, "engine", "flux")

    sb_dir = OUTPUT_DIR / args.series / f"ep{ep_num:02d}" / "storyboard"
    sb_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Storyboard: {bible['series']['title']} — {ep['title']}")
    print(f"  {n} scenes, engine={engine}, resolution={res_config['label']}")
    print(f"{'=' * 60}\n")

    generated = 0
    for i, scene in enumerate(scenes):
        frame_path = sb_dir / f"{scene['id']}.png"

        if frame_path.exists() and not args.force:
            print(f"  [{i+1}/{n}] {scene['id']} — exists, skipping")
            continue

        prompt = build_scene_prompt(scene, bible)
        neg = build_negative_prompt(scene)
        seed = args.seed_base + i + 1
        prefix = f"storyboard/{scene['id']}"

        print(f"  [{i+1}/{n}] {scene['id']}: {prompt[:80]}...")

        # Generate a single still frame via FLUX
        wf = build_t2i_workflow(prompt, seed=seed, prefix=prefix,
                                width=res_config["width"], height=res_config["height"])

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"    ERROR: ComfyUI not running at {SERVER}")
            return

        success = poll_until_done(prompt_id)
        if success:
            # Find and copy the generated frame
            # Try both output dirs
            for out_dir in [COMFYUI_DIR / "output" / "storyboard", COMFYUI_DIR / "output" / "refs"]:
                if out_dir.exists():
                    candidates = sorted(
                        out_dir.glob(f"{scene['id']}*.png"),
                        key=lambda p: p.stat().st_mtime, reverse=True,
                    )
                    if candidates:
                        shutil.copy2(candidates[0], frame_path)
                        generated += 1
                        print(f"    Done → {frame_path.name}")
                        break
            else:
                print(f"    WARNING: frame not found in output")
        else:
            print(f"    WARNING: generation may have failed")

    # Generate HTML contact sheet
    html_path = sb_dir / "storyboard.html"
    _generate_storyboard_html(scenes, bible, sb_dir, html_path)

    print(f"\n{'=' * 60}")
    print(f"  Generated {generated}/{n} storyboard frames")
    print(f"  HTML preview: {html_path}")
    print(f"{'=' * 60}\n")


def _generate_storyboard_html(scenes: list, bible: dict, sb_dir: Path, output_path: Path):
    """Generate an HTML contact sheet from storyboard frames."""
    title = bible["series"]["title"]

    rows = []
    for i, scene in enumerate(scenes):
        frame_file = f"{scene['id']}.png"
        frame_exists = (sb_dir / frame_file).exists()
        img_tag = f'<img src="{frame_file}" />' if frame_exists else '<div class="missing">No frame</div>'

        loc = scene.get("location", "—")
        chars = ", ".join(scene.get("characters", []))
        clip_len = scene.get("clip_length", "medium")
        visual = scene.get("visual", "")
        narration = scene.get("narration", "")
        dialogue_lines = []
        for d in scene.get("dialogue", []):
            char = bible.get("characters", {}).get(d["character"], {})
            name = char.get("name", d["character"])
            dialogue_lines.append(f"<b>{name}:</b> {d['line']}")
        dialogue_html = "<br>".join(dialogue_lines)

        rows.append(f"""
        <div class="scene">
            <div class="frame">{img_tag}</div>
            <div class="info">
                <div class="scene-id">{scene['id']} [{clip_len}]</div>
                <div class="location">📍 {loc} | 👤 {chars}</div>
                <div class="visual">{visual}</div>
                {f'<div class="narration">🎙 {narration}</div>' if narration else ''}
                {f'<div class="dialogue">{dialogue_html}</div>' if dialogue_html else ''}
            </div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Storyboard — {title}</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
h1 {{ color: #e94560; }}
.scene {{ display: flex; gap: 16px; margin: 12px 0; padding: 12px; background: #16213e; border-radius: 8px; }}
.frame {{ flex: 0 0 320px; }}
.frame img {{ width: 320px; border-radius: 4px; }}
.missing {{ width: 320px; height: 180px; background: #333; display: flex; align-items: center; justify-content: center; border-radius: 4px; color: #666; }}
.info {{ flex: 1; }}
.scene-id {{ font-weight: bold; color: #e94560; font-size: 14px; }}
.location {{ color: #0f3460; font-size: 12px; margin: 4px 0; color: #a8a8a8; }}
.visual {{ margin: 6px 0; font-size: 13px; }}
.narration {{ color: #53d8fb; font-size: 12px; margin: 4px 0; font-style: italic; }}
.dialogue {{ color: #f0d43a; font-size: 12px; margin: 4px 0; }}
</style></head>
<body>
<h1>Storyboard — {title}</h1>
<p>{len(scenes)} scenes</p>
{''.join(rows)}
</body></html>"""

    output_path.write_text(html, encoding="utf-8")


# ─── Lip sync (Wav2Lip) ─────────────────────────────────────────────

def apply_lip_sync(video_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Apply lip sync to a video clip using Wav2Lip.

    Requires: wav2lip inference script or wav2lip binary in PATH.
    Falls back gracefully if not installed.

    Args:
        video_path: Input video clip (dialogue scene).
        audio_path: TTS audio for this scene.
        output_path: Output video with synced lips.

    Returns True if lip sync succeeded.
    """
    wav2lip_bin = shutil.which("wav2lip")
    wav2lip_script = Path("/workspace/Wav2Lip/inference.py")

    if wav2lip_bin:
        # Use standalone binary
        try:
            subprocess.run([
                wav2lip_bin,
                "--face", str(video_path),
                "--audio", str(audio_path),
                "--outfile", str(output_path),
            ], capture_output=True, timeout=300)
            return output_path.exists()
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"      Wav2Lip failed: {e}")
            return False

    elif wav2lip_script.exists():
        # Use Python inference script
        checkpoint = Path("/workspace/Wav2Lip/checkpoints/wav2lip_gan.pth")
        if not checkpoint.exists():
            print(f"      Wav2Lip checkpoint not found at {checkpoint}")
            return False
        try:
            subprocess.run([
                sys.executable, str(wav2lip_script),
                "--checkpoint_path", str(checkpoint),
                "--face", str(video_path),
                "--audio", str(audio_path),
                "--outfile", str(output_path),
                "--resize_factor", "1",
                "--nosmooth",
            ], capture_output=True, timeout=300)
            return output_path.exists()
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"      Wav2Lip inference failed: {e}")
            return False

    else:
        print(f"      Wav2Lip not found — skipping lip sync")
        return False


# ─── XTTS v2 TTS ────────────────────────────────────────────────────

async def generate_tts_xtts(text: str, voice_sample: str, output_path: str,
                             language: str = "en"):
    """
    Generate TTS audio using XTTS v2 (Coqui) with voice cloning.

    Args:
        text: Text to speak.
        voice_sample: Path to a 6+ second WAV sample of the target voice.
        output_path: Where to save the generated audio.
        language: Language code (default: "en").
    """
    try:
        from TTS.api import TTS
    except ImportError:
        raise RuntimeError("XTTS not installed. Install: pip install TTS")

    tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
    tts.tts_to_file(
        text=text,
        speaker_wav=voice_sample,
        language=language,
        file_path=output_path,
    )


def generate_episode_audio_xtts(episode: dict, bible: dict, output_dir: Path,
                                 voice_samples_dir: Path | None = None) -> list[Path]:
    """Generate TTS audio using XTTS v2 with voice cloning for character dialogue.

    Falls back to Edge-TTS for narration or if voice samples don't exist.
    Voice samples should be WAV files named: {char_key}.wav (e.g. char_1.wav)
    in the voice_samples_dir (defaults to series/{slug}/voice_samples/).

    Args:
        episode: Episode JSON dict.
        bible: Series bible dict.
        output_dir: Output directory for audio files.
        voice_samples_dir: Directory containing voice sample WAVs.

    Returns list of audio file paths (one per scene, None for silent scenes).
    """
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    narrator_voice = bible.get("narrator", {}).get("voice", "en-US-GuyNeural")
    audio_files = []

    # Check if XTTS is available
    xtts_available = False
    try:
        import TTS  # noqa: F401
        xtts_available = True
    except ImportError:
        pass

    for scene in episode["scenes"]:
        audio_path = audio_dir / f"{scene['id']}.mp3"

        if audio_path.exists():
            audio_files.append(audio_path)
            continue

        spoken_parts = []
        if scene.get("narration"):
            spoken_parts.append(scene["narration"])
        if scene.get("dialogue"):
            has_narration = bool(scene.get("narration"))
            for d in scene["dialogue"]:
                if has_narration:
                    char = bible.get("characters", {}).get(d["character"], {})
                    name = char.get("name", d["character"])
                    spoken_parts.append(f"{name}: {d['line']}")
                else:
                    spoken_parts.append(d["line"])

        if not spoken_parts:
            audio_files.append(None)
            continue

        full_text = " ".join(spoken_parts)

        # Decide which TTS engine to use
        use_xtts = False
        voice_sample_path = None

        if xtts_available and not scene.get("narration") and scene.get("dialogue"):
            # Pure dialogue: try XTTS with character voice clone
            first_char = scene["dialogue"][0]["character"]
            if voice_samples_dir:
                sample = voice_samples_dir / f"{first_char}.wav"
                if sample.exists():
                    voice_sample_path = str(sample)
                    use_xtts = True

        try:
            if use_xtts and voice_sample_path:
                # Use XTTS v2 with voice cloning
                wav_path = audio_dir / f"{scene['id']}.wav"
                asyncio.run(generate_tts_xtts(full_text, voice_sample_path, str(wav_path)))
                # Convert WAV to MP3 for consistency
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-b:a", "128k", str(audio_path),
                ], capture_output=True, timeout=30)
                wav_path.unlink(missing_ok=True)
            else:
                # Fallback to Edge-TTS
                voice = narrator_voice
                if not scene.get("narration") and scene.get("dialogue"):
                    first_char = scene["dialogue"][0]["character"]
                    voice = bible.get("characters", {}).get(first_char, {}).get("voice", narrator_voice)
                asyncio.run(generate_tts_scene(full_text, voice, str(audio_path)))

            audio_files.append(audio_path)
        except Exception as e:
            print(f"    TTS failed for {scene['id']}: {e}")
            audio_files.append(None)

    return audio_files


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Showrunner — Automated Series Production")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new series from template")
    p_create.add_argument("series", help="Series name (used as directory name)")

    p_write = sub.add_parser("write", help="Generate bible + episode scripts via Claude")
    p_write.add_argument("series")
    p_write.add_argument("--episode", type=int, help="Write only this episode number")
    p_write.add_argument("--force", action="store_true", help="Regenerate existing files")

    p_script = sub.add_parser("script", help="Export voiceover scripts")
    p_script.add_argument("series")
    p_script.add_argument("--episode", type=int)

    p_produce = sub.add_parser("produce", help="Produce an episode (video + audio + stitch)")
    p_produce.add_argument("series")
    p_produce.add_argument("--episode", type=int, required=True)
    p_produce.add_argument("--image", "-i", help="Reference image for visual consistency")
    p_produce.add_argument("--seed-base", type=int, default=1000)
    p_produce.add_argument("--resume", action="store_true")
    p_produce.add_argument("--no-audio", action="store_true", help="Skip TTS generation")
    p_produce.add_argument("--quality", choices=["draft", "good", "final"], default="draft",
                           help="Inference quality: draft=15 steps, good=30, final=50 (default: draft)")
    p_produce.add_argument("--no-crossfade", action="store_true", help="Use hard cuts instead of dissolve transitions")
    p_produce.add_argument("--no-grade", action="store_true", help="Skip colour grade post-processing")
    p_produce.add_argument("--no-subs", action="store_true", help="Skip subtitle burn-in")
    p_produce.add_argument("--no-ambience", action="store_true", help="Skip ambient audio mixing")
    p_produce.add_argument("--no-music", action="store_true", help="Skip music bed")
    p_produce.add_argument("--music-bed", help="Override music bed filename (e.g. music_comedy.mp3)")
    p_produce.add_argument("--flagged-only", action="store_true",
                           help="Only regenerate scenes flagged via 'review' command")
    p_produce.add_argument("--enhance", action="store_true",
                           help="Enhance scene prompts via Claude before generation (cached per scene)")
    p_produce.add_argument("--upscale", action="store_true",
                           help="Upscale stitched video with Real-ESRGAN (4x, requires realesrgan-ncnn-vulkan; falls back to FFmpeg lanczos)")
    p_produce.add_argument("--upscale-factor", type=int, default=4, choices=[2, 4],
                           help="Upscale factor (default: 4)")
    p_produce.add_argument("--interpolate", action="store_true",
                           help="Interpolate frames with RIFE for smoother motion (2x, requires rife-ncnn-vulkan)")
    p_produce.add_argument("--video-model", choices=["wan", "wan-5b"], default="wan",
                           help="Video model: wan (14B dual-model) or wan-5b (5B local preview) (default: wan)")
    p_produce.add_argument("--optimization", choices=["none", "balanced", "fast", "turbo"], default="balanced",
                           help="Speed optimization: none, balanced (30%% faster, default), fast (50%% faster), turbo (60%% faster, lower quality)")
    p_produce.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                           help="Generation resolution: 480p (8GB), 720p (24GB+), auto (detect VRAM) (default: auto)")
    p_produce.add_argument("--ip-adapter", action="store_true",
                           help="Use IP-Adapter for character consistency in dialogue/close-up scenes (requires ComfyUI-IPAdapter-plus)")
    p_produce.add_argument("--ip-adapter-strength", type=float, default=IP_ADAPTER_DEFAULT_STRENGTH,
                           help=f"IP-Adapter conditioning strength 0.0–1.0 (default: {IP_ADAPTER_DEFAULT_STRENGTH})")
    p_produce.add_argument("--lip-sync", action="store_true",
                           help="Apply Wav2Lip lip sync to dialogue scenes (requires Wav2Lip)")
    p_produce.add_argument("--motion-video",
                           help="Motion reference video for animate mode — character performs the motion from this video")
    p_produce.add_argument("--tts-engine", choices=["edge", "xtts"], default="edge",
                           help="TTS engine: edge (Edge-TTS, fast) or xtts (XTTS v2, voice cloning) (default: edge)")
    p_produce.add_argument("--no-char-loras", action="store_true",
                           help="Ignore character LoRAs. They are trained on t2v-A14B; applying "
                                "them across the I2V and S2V checkpoints in one episode is a "
                                "cross-family mix and can make shots look inconsistent.")
    p_produce.add_argument("--lightning", action="store_true",
                           help="Step-distilled sampling via the LightX2V LoRAs: ~6x faster "
                                "and better on hard shots. Forces cfg=1.0 and euler/simple.")
    p_produce.add_argument("--lightning-steps", type=int, default=None,
                           help="Steps when --lightning is on (default 8; 4 also works)")
    p_produce.add_argument("--no-strict", action="store_true",
                           help="Continue past conditions that make the output wrong "
                                "(missing LoRA, broken seed chain, over-long narration, "
                                "failed clip validation). Strict is ON by default.")
    p_produce.add_argument("--auto-analyse", action="store_true",
                           help="After production, run Claude vision analysis on all clips and flag low-scoring ones")

    p_all = sub.add_parser("produce-all", help="Produce all episodes")
    p_all.add_argument("series")
    p_all.add_argument("--no-strict", action="store_true",
                       help="Continue past conditions that make the output wrong. "
                            "Strict is ON by default.")
    p_all.add_argument("--image", "-i")
    p_all.add_argument("--seed-base", type=int, default=1000)
    p_all.add_argument("--resume", action="store_true")
    p_all.add_argument("--no-audio", action="store_true")
    p_all.add_argument("--quality", choices=["draft", "good", "final"], default="draft",
                       help="Inference quality preset (default: draft)")
    p_all.add_argument("--no-crossfade", action="store_true")
    p_all.add_argument("--no-grade", action="store_true")
    p_all.add_argument("--no-subs", action="store_true")
    p_all.add_argument("--no-ambience", action="store_true")
    p_all.add_argument("--no-music", action="store_true")
    p_all.add_argument("--enhance", action="store_true",
                       help="Enhance scene prompts via Claude before generation")
    p_all.add_argument("--upscale", action="store_true",
                       help="Upscale stitched video with Real-ESRGAN (4x)")
    p_all.add_argument("--upscale-factor", type=int, default=4, choices=[2, 4])
    p_all.add_argument("--interpolate", action="store_true",
                       help="Interpolate frames with RIFE (2x smoother motion)")
    p_all.add_argument("--video-model", choices=["wan", "wan-5b"], default="wan",
                       help="Video model: wan (14B dual-model) or wan-5b (5B local preview) (default: wan)")
    p_all.add_argument("--optimization", choices=["none", "balanced", "fast", "turbo"], default="balanced",
                       help="Speed optimization preset (default: balanced)")
    p_all.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                       help="Generation resolution (default: auto)")
    p_all.add_argument("--ip-adapter", action="store_true",
                       help="Use IP-Adapter for character consistency")
    p_all.add_argument("--ip-adapter-strength", type=float, default=IP_ADAPTER_DEFAULT_STRENGTH)
    p_all.add_argument("--lip-sync", action="store_true",
                       help="Apply Wav2Lip lip sync to dialogue scenes")
    p_all.add_argument("--motion-video",
                       help="Motion reference video for animate mode")
    p_all.add_argument("--tts-engine", choices=["edge", "xtts"], default="edge",
                       help="TTS engine: edge or xtts (default: edge)")

    p_amb = sub.add_parser("setup-ambience", help="Generate synthetic ambient audio files")
    p_amb.add_argument("--duration", type=int, default=60, help="Loop duration in seconds (default: 60)")

    p_validate = sub.add_parser("validate", help="Validate generated clips — detect blank, frozen, or corrupt clips")
    p_validate.add_argument("series")
    p_validate.add_argument("--episode", type=int, required=True)
    p_validate.add_argument("--auto-flag", action="store_true",
                            help="Automatically flag bad clips for regeneration")

    p_analyse = sub.add_parser("analyse", help="Analyse clips via Claude vision — quality scores, issue reports, improved prompts")
    p_analyse.add_argument("series")
    p_analyse.add_argument("--episode", type=int, required=True)
    p_analyse.add_argument("--min-score", type=int, default=3,
                           help="Clips scoring below this are flagged for regeneration (default: 3)")
    p_analyse.add_argument("--update-cache", action="store_true",
                           help="Write Claude's improved prompts into the prompt cache for --enhance")

    p_refs = sub.add_parser("gen-refs", help="Generate canonical reference images for all characters and locations")
    p_refs.add_argument("series")
    p_refs.add_argument("--force", action="store_true", help="Regenerate even if images already exist")
    p_refs.add_argument("--engine", choices=["flux"], default="flux",
                        help="Portrait engine: flux (FLUX T2I, fast, sharp stills) (default: flux)")

    p_review = sub.add_parser("review", help="Interactively review clips and flag weak ones for regeneration")
    p_review.add_argument("series")
    p_review.add_argument("--episode", type=int, required=True)

    p_compile = sub.add_parser("compile", help="Compile all produced episodes into a season reel with title cards")
    p_compile.add_argument("series")
    p_compile.add_argument("--card-duration", type=float, default=3.0,
                           help="Duration of each title card in seconds (default: 3.0)")

    p_status = sub.add_parser("status", help="Show series status")
    p_status.add_argument("series")

    p_storyboard = sub.add_parser("storyboard", help="Generate a storyboard (one frame per scene) for quick review before production")
    p_storyboard.add_argument("series")
    p_storyboard.add_argument("--episode", type=int, required=True)
    p_storyboard.add_argument("--seed-base", type=int, default=1000)
    p_storyboard.add_argument("--force", action="store_true", help="Regenerate existing storyboard frames")
    p_storyboard.add_argument("--engine", choices=["flux"], default="flux",
                              help="Image engine: flux (FLUX T2I) (default: flux)")
    p_storyboard.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                              help="Resolution (default: auto)")

    args = parser.parse_args()

    # Strict is the default for renders; --no-strict opts out per run.

    global STRICT

    STRICT = not getattr(args, 'no_strict', False)

    if not args.command:
        parser.print_help()
        return

    # Scope clip output/lookup to this series for the whole run.
    set_current_series(getattr(args, "series", None))

    cmds = {
        "create": cmd_create,
        "write": cmd_write,
        "script": cmd_script,
        "produce": cmd_produce,
        "produce-all": cmd_produce_all,
        "status": cmd_status,
        "setup-ambience": cmd_setup_ambience,
        "gen-refs": cmd_gen_refs,
        "review": cmd_review,
        "compile": cmd_compile,
        "validate": cmd_validate,
        "analyse": cmd_analyse,
        "storyboard": cmd_storyboard,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
