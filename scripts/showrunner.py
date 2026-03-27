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
import os
import shutil
import subprocess
import sys
import tempfile
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

# ─── Model configurations ────────────────────────────────────────────
# Each video model has its own resolution presets, clip lengths, quality steps,
# and workflow structure. Toggle between models via --video-model flag.

MODEL_CONFIGS = {
    "hunyuan": {
        "label": "HunyuanVideo 1.5",
        "fps": 24,
        "cfg": 1.0,          # Distilled model — must be 1.0
        "sampler": "euler",
        "scheduler": "simple",
        "clip_lengths": {
            "short":  {"frames": 49, "seconds": 2.0},
            "medium": {"frames": 65, "seconds": 2.7},
            "long":   {"frames": 81, "seconds": 3.4},
        },
        "quality_steps": {"draft": 20, "good": 30, "final": 50},
        "resolutions": {
            "480p": {
                "width": 848, "height": 480, "shift": 5.0,
                "t2v_unet": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf",
                "i2v_unet": "hunyuanvideo1.5_480p_i2v_cfg_distilled-Q5_K_S.gguf",
                "min_vram_gb": 8, "label": "480p (848×480)",
            },
            "720p": {
                "width": 1280, "height": 720, "shift": 9.0,
                "t2v_unet": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf",
                "i2v_unet": "hunyuanvideo1.5_480p_i2v_cfg_distilled-Q5_K_S.gguf",
                "min_vram_gb": 24, "label": "720p (1280×720)",
            },
        },
        "text_encoders": {
            "clip1": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "clip2": "byt5_small_glyphxl_fp16.safetensors",
            "clip_type": "hunyuan_video_15",
        },
        "vae": "hunyuanvideo15_vae_fp16.safetensors",
        "clip_vision": "sigclip_vision_patch14_384.safetensors",
        "lora_loader": "LoraLoaderModelOnly",
    },
    "wan": {
        "label": "WAN 2.2 (A14B dual-model)",
        "fps": 16,
        "cfg": 5.0,
        "sampler": "uni_pc_bh2",
        "scheduler": "simple",
        "dual_model": True,  # WAN 2.2 uses high-noise + low-noise model switching
        "timestep_boundary": 0.875,  # Switch from high→low noise model at this % of steps
        "clip_lengths": {
            "short":  {"frames": 33, "seconds": 2.1},
            "medium": {"frames": 49, "seconds": 3.1},
            "long":   {"frames": 81, "seconds": 5.1},
        },
        "quality_steps": {"draft": 15, "good": 25, "final": 40},
        "resolutions": {
            "480p": {
                "width": 832, "height": 480, "shift": 12.0,
                "t2v_unet": "wan2.2_t2v_high_noise_14B_Q4_K_S.gguf",
                "t2v_unet_low": "wan2.2_t2v_low_noise_14B_Q4_K_S.gguf",
                "i2v_unet": "wan2.2_i2v_high_noise_14B_Q4_K_S.gguf",
                "i2v_unet_low": "wan2.2_i2v_low_noise_14B_Q4_K_S.gguf",
                "min_vram_gb": 12, "label": "480p (832×480)",
            },
            "720p": {
                "width": 1280, "height": 720, "shift": 12.0,
                "t2v_unet": "wan2.2_t2v_high_noise_14B_Q4_K_S.gguf",
                "t2v_unet_low": "wan2.2_t2v_low_noise_14B_Q4_K_S.gguf",
                "i2v_unet": "wan2.2_i2v_high_noise_14B_Q4_K_S.gguf",
                "i2v_unet_low": "wan2.2_i2v_low_noise_14B_Q4_K_S.gguf",
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
}
DEFAULT_VIDEO_MODEL = "hunyuan"

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

# Inference quality presets — these are overridden by model config but kept for backward compat
QUALITY_STEPS = MODEL_CONFIGS["hunyuan"]["quality_steps"]

# Clip length presets — backward compat alias
CLIP_LENGTHS = MODEL_CONFIGS["hunyuan"]["clip_lengths"]

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


# Frame count constraints (must be 4n+1 for both HunyuanVideo and WAN)
MIN_FRAMES = 33   # ~1.4s at 24fps / ~2.1s at 16fps
MAX_FRAMES = 97   # ~4.0s at 24fps / ~6.1s at 16fps


def frames_for_duration(seconds: float, fps: int = 24) -> int:
    """Compute the nearest valid frame count (4n+1) for a given duration.

    Both HunyuanVideo and WAN require frame counts of the form 4n+1.
    Returns the closest valid count within MIN_FRAMES..MAX_FRAMES, with a small
    buffer (+0.3s) to ensure audio fits comfortably within the clip.
    """
    target = int(round((seconds + 0.3) * fps))
    n = round((target - 1) / 4)
    frames = 4 * n + 1
    return max(MIN_FRAMES, min(MAX_FRAMES, frames))

# ─── Ambient audio system ─────────────────────────────────────────────
#
# Each location type maps to an FFmpeg filter chain that synthesises a
# 60-second ambient loop saved to ambience/<type>.mp3.
# Replace any file with a real recording and it will be used automatically.

AMBIENT_PRESETS: dict[str, dict] = {
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
    (["kesh", "prison", "internment", "camp", "cell", "wire"], "prison"),
    (["checkpoint", "army", "military", "patrol", "land rover", "saracen", "barricade"], "military"),
    (["factory", "warehouse", "industrial", "derelict", "abandoned", "machinery"], "factory"),
    (["derry", "march", "protest", "crowd", "demonstration", "bogside"], "crowd_protest"),
    (["pub", "bar", "tavern", "neutral_pub", "local_pub"], "pub"),
    (["garden", "back_garden", "fence", "yard", "outside"], "garden"),
    (["home", "house", "kitchen", "sitting room", "interior", "bedroom", "inside",
      "paddy_house", "billy_house", "paddys_house", "billys_house"], "interior_quiet"),
]


def classify_ambient(location_id: str, location_desc: str = "") -> str:
    """Map a location to its ambient sound type based on keywords."""
    text = f"{location_id} {location_desc}".lower()
    for keywords, ambient_type in _AMBIENT_RULES:
        if any(kw in text for kw in keywords):
            return ambient_type
    return "street_rain"   # default — it's Belfast, it's always raining


def get_ambient_file(location_id: str, bible: dict) -> Path | None:
    """Return the ambient audio file for a location, or None if ambience dir is empty."""
    if not AMBIENCE_DIR.exists():
        return None
    loc_desc = bible.get("world", {}).get("locations", {}).get(location_id, "")
    ambient_type = classify_ambient(location_id, loc_desc)
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

def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 8000) -> str:
    """Call Claude API and return the text response."""
    import anthropic
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def call_claude_vision(system_prompt: str, content_blocks: list, max_tokens: int = 1000) -> str:
    """Call Claude API with a multimodal message (text + images)."""
    import anthropic
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": content_blocks}],
    )
    return message.content[0].text


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
      "fps": 24
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

    response = call_claude(system, user)
    # Strip markdown fences if present
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1]
    if response.endswith("```"):
        response = response.rsplit("```", 1)[0]
    response = response.strip()
    return json.loads(response)


def generate_episode(bible: dict, concept: dict, ep_num: int, total_eps: int, previous_summaries: list[str]) -> dict:
    """Use Claude to generate a single episode script."""

    target_duration = concept.get("episode_duration_seconds", 30)

    system = f"""You are a showrunner writing episode scripts for an animated short-form series.
Each episode is ~{target_duration} seconds long, made of multiple clips stitched together.

IMPORTANT CONSTRAINTS:
- Each clip/scene can be 2.0s, 2.7s, or 3.4s long
- Total episode duration should be ~{target_duration} seconds (aim for {target_duration - 3} to {target_duration + 3}s)
- For a {target_duration}s episode you will need roughly {max(9, target_duration // 3)} scenes — DO NOT write fewer than {max(8, target_duration // 4)} scenes
- Choose clip duration based on content:
  - 2.0s (short): action, transitions, quick cuts, reaction shots
  - 2.7s (medium): dialogue exchanges, character moments, two-shots
  - 3.4s (long): atmospheric establishing shots, emotional beats, wide shots
- Each scene needs a visual description that works as a text-to-video prompt
- NARRATION WORD LIMIT (TTS speaks ~2.5 words/second):
  - 2.0s short clip: max 5 words of narration
  - 2.7s medium clip: max 7 words of narration
  - 3.4s long clip: max 8 words of narration
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
      ]
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
- The episode should tell a complete mini-story while advancing the season arc"""

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

    response = call_claude(system, user, max_tokens=4000)
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1]
    if response.endswith("```"):
        response = response.rsplit("```", 1)[0]
    response = response.strip()
    return json.loads(response)


# ─── TTS ─────────────────────────────────────────────────────────────

async def generate_tts_scene(text: str, voice: str, output_path: str):
    """Generate TTS audio for a single scene."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_episode_audio(episode: dict, bible: dict, output_dir: Path) -> list[Path]:
    """Generate TTS audio for each scene, return list of audio file paths."""
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    narrator_voice = bible.get("narrator", {}).get("voice", "en-US-GuyNeural")
    audio_files = []

    TTS_WPS = 2.5  # words per second (Edge-TTS typical rate)

    for scene in episode["scenes"]:
        audio_path = audio_dir / f"{scene['id']}.mp3"
        cl = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])
        clip_dur = cl["seconds"]

        # Build the spoken text for this scene
        spoken_parts = []

        if scene.get("narration"):
            spoken_parts.append(scene["narration"])

        if scene.get("dialogue"):
            has_narration = bool(scene.get("narration"))
            for d in scene["dialogue"]:
                if has_narration:
                    # Mixed scene narrated by narrator — prefix with name so it's clear who speaks
                    char = bible.get("characters", {}).get(d["character"], {})
                    name = char.get("name", d["character"])
                    spoken_parts.append(f"{name}: {d['line']}")
                else:
                    # Pure dialogue scene — character voice is used, no prefix needed
                    spoken_parts.append(d["line"])

        if spoken_parts:
            full_text = " ".join(spoken_parts)

            # Warn if spoken text is likely longer than the video clip
            word_count = len(full_text.split())
            est_dur = word_count / TTS_WPS
            if est_dur > clip_dur + 0.3:
                print(f"    WARNING: {scene['id']} audio ~{est_dur:.1f}s but clip is {clip_dur}s — text will be cut off")

            # Use narrator voice for narration, character voice for dialogue-only
            voice = narrator_voice
            if not scene.get("narration") and scene.get("dialogue"):
                # Pure dialogue scene — use first character's voice
                first_char = scene["dialogue"][0]["character"]
                voice = bible.get("characters", {}).get(first_char, {}).get("voice", narrator_voice)

            if not audio_path.exists():
                try:
                    asyncio.run(generate_tts_scene(full_text, voice, str(audio_path)))
                except Exception as e:
                    print(f"    TTS failed for {scene['id']}: {e}")
                    audio_files.append(None)
                    continue

            audio_files.append(audio_path)
        else:
            audio_files.append(None)  # Silent scene

    return audio_files


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


def _insert_lora_chain(wf: dict, loras: list[tuple[str, float]], unet_node: str, sampler_model_node: str) -> None:
    """Insert a chain of LoRA nodes between the UNet loader and the sampler model node.

    Each LoRA feeds into the next, forming a chain:
      UnetLoaderGGUF → LoRA_1 → LoRA_2 → LoRA_3 → ModelSamplingSD3

    Args:
        wf: The workflow dict to modify in-place.
        loras: List of (lora_filename, strength) tuples. Max 3 recommended.
        unet_node: Node ID of UnetLoaderGGUF (e.g. "1").
        sampler_model_node: Node ID that consumes the model (e.g. "7" for T2V, "10" for I2V).
    """
    if not loras:
        return

    prev_output = [unet_node, 0]  # Start from UNet output

    for idx, (lora_name, lora_strength) in enumerate(loras):
        node_id = str(50 + idx)  # "50", "51", "52"
        wf[node_id] = build_lora_node(prev_output, lora_name, lora_strength)
        prev_output = [node_id, 0]

    # Point the sampler model node to the last LoRA output
    wf[sampler_model_node]["inputs"]["model"] = prev_output


def build_t2v_workflow(prompt: str, seed: int, clip_prefix: str, frames: int,
                       negative_prompt: str = "", steps: int = 15,
                       lora_name: str | None = None, lora_strength: float = 0.7,
                       loras: list[tuple[str, float]] | None = None,
                       res_config: dict | None = None) -> dict:
    rc = res_config or RESOLUTION_PRESETS[DEFAULT_RESOLUTION]
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["t2v_unet"]}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},
        "6": {"class_type": "EmptyHunyuanVideo15Latent", "inputs": {"width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1}},
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "8": {"class_type": "CFGGuider", "inputs": {"model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["8", 0], "sampler": ["11", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": 24.0}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }
    # Build LoRA list: prefer new `loras` param, fall back to legacy single lora
    lora_list = loras or ([(lora_name, lora_strength)] if lora_name else [])
    _insert_lora_chain(wf, lora_list, unet_node="1", sampler_model_node="7")
    return wf


def build_i2v_workflow(prompt: str, image_name: str, seed: int, clip_prefix: str, frames: int,
                       negative_prompt: str = "", steps: int = 15,
                       denoise: float = DEFAULT_DENOISE,
                       lora_name: str | None = None, lora_strength: float = 0.7,
                       loras: list[tuple[str, float]] | None = None,
                       res_config: dict | None = None) -> dict:
    rc = res_config or RESOLUTION_PRESETS[DEFAULT_RESOLUTION]
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["i2v_unet"]}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "sigclip_vision_patch14_384.safetensors"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "20": {"class_type": "ImageScale", "inputs": {
            "image": ["5", 0], "upscale_method": "lanczos",
            "width": rc["width"], "height": rc["height"], "crop": "center"
        }},
        "6": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["4", 0], "image": ["20", 0], "crop": "center"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},
        "9": {"class_type": "HunyuanVideo15ImageToVideo", "inputs": {
            "positive": ["7", 0], "negative": ["8", 0], "vae": ["3", 0],
            "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
            "start_image": ["20", 0], "clip_vision_output": ["6", 0]
        }},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "11": {"class_type": "CFGGuider", "inputs": {"model": ["10", 0], "positive": ["9", 0], "negative": ["9", 1], "cfg": 1.0}},
        "12": {"class_type": "BasicScheduler", "inputs": {"model": ["10", 0], "scheduler": "simple", "steps": steps, "denoise": denoise}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["13", 0], "guider": ["11", 0], "sampler": ["14", 0], "sigmas": ["12", 0], "latent_image": ["9", 2]}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["3", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": 24.0}},
        "18": {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }
    lora_list = loras or ([(lora_name, lora_strength)] if lora_name else [])
    _insert_lora_chain(wf, lora_list, unet_node="1", sampler_model_node="10")
    return wf


# ─── WAN 2.1 workflow builders ──────────────────────────────────────

def build_wan_t2v_workflow(prompt: str, seed: int, clip_prefix: str, frames: int,
                            negative_prompt: str = "", steps: int = 25,
                            loras: list[tuple[str, float]] | None = None,
                            res_config: dict | None = None,
                            model_config: dict | None = None) -> dict:
    """Build a WAN 2.2 T2V workflow with dual-model (high/low noise) architecture.

    WAN 2.2 uses two DiT models:
      - High-noise model: handles early denoising steps (coarse structure)
      - Low-noise model: handles later steps (fine detail refinement)
    The switch happens at timestep_boundary (default 87.5% of steps).

    This produces significantly better quality than single-model WAN 2.1
    because each model is specialized for its noise level range.
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]
    boundary = mc.get("timestep_boundary", 0.875)
    boundary_step = int(steps * boundary)

    wf = {
        # Shared: text encoder, VAE, prompts
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},

        # High-noise model (early steps: structure, composition)
        "1":  {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["t2v_unet"]}},
        "7":  {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "8":  {"class_type": "CFGGuider", "inputs": {"model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": mc["cfg"]}},
        "9":  {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": mc["scheduler"], "steps": steps, "denoise": 1.0}},
        "30": {"class_type": "SplitSigmas", "inputs": {"sigmas": ["9", 0], "step": boundary_step}},

        # Low-noise model (later steps: detail, refinement)
        "31": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc.get("t2v_unet_low", rc["t2v_unet"])}},
        "32": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["31", 0], "shift": rc["shift"]}},
        "33": {"class_type": "CFGGuider", "inputs": {"model": ["32", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": mc["cfg"]}},

        # Latent, noise, sampler
        "6":  {"class_type": "EmptySD3LatentImage", "inputs": {"width": rc["width"], "height": rc["height"], "batch_size": 1}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": mc["sampler"]}},

        # Two-stage sampling: high-noise → low-noise
        "34": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["10", 0], "guider": ["8", 0], "sampler": ["11", 0],
            "sigmas": ["30", 0], "latent_image": ["6", 0]
        }},
        "35": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["10", 0], "guider": ["33", 0], "sampler": ["11", 0],
            "sigmas": ["30", 1], "latent_image": ["34", 0]
        }},

        # Decode and save
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["35", 0], "vae": ["3", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(mc["fps"])}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }
    if loras:
        _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="7")
        # Also apply LoRAs to the low-noise model
        _insert_lora_chain(wf, loras, unet_node="31", sampler_model_node="32")
    return wf


def build_wan_i2v_workflow(prompt: str, image_name: str, seed: int, clip_prefix: str, frames: int,
                            negative_prompt: str = "", steps: int = 25,
                            denoise: float = DEFAULT_DENOISE,
                            loras: list[tuple[str, float]] | None = None,
                            res_config: dict | None = None,
                            model_config: dict | None = None) -> dict:
    """Build a WAN 2.2 I2V workflow with dual-model architecture.

    Same dual high/low noise approach as T2V, but uses Wan22ImageToVideoLatent
    for start image conditioning and the I2V-specific model checkpoints.
    """
    mc = model_config or MODEL_CONFIGS["wan"]
    rc = res_config or list(mc["resolutions"].values())[0]
    te = mc["text_encoders"]
    boundary = mc.get("timestep_boundary", 0.875)
    boundary_step = int(steps * boundary)

    wf = {
        # Shared
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": te["clip1"], "type": te["clip_type"]}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": mc["vae"]}},

        # Image conditioning
        "5":  {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "20": {"class_type": "ImageScale", "inputs": {
            "image": ["5", 0], "upscale_method": "lanczos",
            "width": rc["width"], "height": rc["height"], "crop": "center"
        }},

        # Text conditioning
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative_prompt}},

        # WAN 2.2 I2V latent — uses Wan22ImageToVideoLatent for proper inpainting-style conditioning
        "9": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["3", 0],
            "width": rc["width"], "height": rc["height"], "length": frames, "batch_size": 1,
            "start_image": ["20", 0],
        }},

        # High-noise model
        "1":  {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc["i2v_unet"]}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": rc["shift"]}},
        "11": {"class_type": "CFGGuider", "inputs": {"model": ["10", 0], "positive": ["7", 0], "negative": ["8", 0], "cfg": mc["cfg"]}},
        "12": {"class_type": "BasicScheduler", "inputs": {"model": ["10", 0], "scheduler": mc["scheduler"], "steps": steps, "denoise": denoise}},
        "30": {"class_type": "SplitSigmas", "inputs": {"sigmas": ["12", 0], "step": boundary_step}},

        # Low-noise model
        "31": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": rc.get("i2v_unet_low", rc["i2v_unet"])}},
        "32": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["31", 0], "shift": rc["shift"]}},
        "33": {"class_type": "CFGGuider", "inputs": {"model": ["32", 0], "positive": ["7", 0], "negative": ["8", 0], "cfg": mc["cfg"]}},

        # Noise + sampler
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": mc["sampler"]}},

        # Two-stage sampling
        "34": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["13", 0], "guider": ["11", 0], "sampler": ["14", 0],
            "sigmas": ["30", 0], "latent_image": ["9", 0]
        }},
        "35": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["13", 0], "guider": ["33", 0], "sampler": ["14", 0],
            "sigmas": ["30", 1], "latent_image": ["34", 0]
        }},

        # Decode and save
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["35", 0], "vae": ["3", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": float(mc["fps"])}},
        "18": {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }
    if loras:
        _insert_lora_chain(wf, loras, unet_node="1", sampler_model_node="10")
        _insert_lora_chain(wf, loras, unet_node="31", sampler_model_node="32")
    return wf


# ─── Model-agnostic workflow dispatch ────────────────────────────────

def build_video_workflow(video_model: str, mode: str, prompt: str, seed: int,
                          clip_prefix: str, frames: int, res_config: dict,
                          negative_prompt: str = "", steps: int = 25,
                          denoise: float = DEFAULT_DENOISE,
                          loras: list[tuple[str, float]] | None = None,
                          image_name: str | None = None,
                          optimization: str = "none") -> dict:
    """Dispatch to the correct workflow builder based on video model and mode.

    Args:
        video_model: "hunyuan" or "wan"
        mode: "t2v" or "i2v"
        optimization: "none", "balanced", "fast", or "turbo" (EasyCache presets)
        Other args passed through to the model-specific builder.
    """
    mc = get_model_config(video_model)

    if video_model == "wan":
        if mode == "i2v" and image_name:
            wf = build_wan_i2v_workflow(prompt, image_name, seed, clip_prefix, frames,
                                         negative_prompt=negative_prompt, steps=steps,
                                         denoise=denoise, loras=loras,
                                         res_config=res_config, model_config=mc)
            _insert_optimizations(wf, optimization, model_node="10")
        else:
            wf = build_wan_t2v_workflow(prompt, seed, clip_prefix, frames,
                                         negative_prompt=negative_prompt, steps=steps,
                                         loras=loras, res_config=res_config, model_config=mc)
            _insert_optimizations(wf, optimization, model_node="7")
    else:  # hunyuan (default)
        if mode == "i2v" and image_name:
            wf = build_i2v_workflow(prompt, image_name, seed, clip_prefix, frames,
                                     negative_prompt=negative_prompt, steps=steps,
                                     denoise=denoise, loras=loras, res_config=res_config)
            _insert_optimizations(wf, optimization, model_node="10")
        else:
            wf = build_t2v_workflow(prompt, seed, clip_prefix, frames,
                                     negative_prompt=negative_prompt, steps=steps,
                                     loras=loras, res_config=res_config)
            _insert_optimizations(wf, optimization, model_node="7")

    return wf


# ─── IP-Adapter for character consistency ────────────────────────────
#
# IP-Adapter conditions the model on a reference image at inference time,
# providing much stronger appearance/face consistency than LoRAs alone.
# Requires: ComfyUI-IPAdapter-plus custom node + IP-Adapter model files.

# Default IP-Adapter model for video (works with HunyuanVideo via SD1.5 adapter)
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
    char_ref = ref_dir / f"char_{char_id}.png"

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
    """Build a structured video generation prompt optimised for HunyuanVideo.

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

    # 2. Character trigger words — LoRAs carry the visual knowledge
    for char_id in characters:
        char = bible.get("characters", {}).get(char_id)
        if not char:
            continue
        trigger = char.get("trigger_word", "") if char.get("lora_path") else ""
        if trigger:
            parts.append(trigger)

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

    # 5. Location trigger (LoRA handles the look; skip for close-up dialogue)
    loc_id = scene.get("location")
    if loc_id and not (is_dialogue and shot_type == "closeup"):
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

    # 6. Style — one short phrase, not the full user description
    series_style = bible["series"].get("style", "")
    if series_style:
        short_style = series_style.split(",")[0].strip()[:60]
        parts.append(short_style)

    return ", ".join(filter(None, parts))


def build_negative_prompt(scene: dict) -> str:
    """Return a negative prompt tailored to the scene type.

    Different scene types have different failure modes:
    - Dialogue: camera shake and face blur ruin lip-sync coherence
    - Establishing: characters appearing where there should be none
    - Action: static/frozen frames defeat the purpose
    - Close-up: multiple faces or merged identities
    """
    base = "low quality, blurry, distorted, deformed, ugly, watermark, text overlay, oversaturated"
    visual_lower = scene.get("visual", "").lower()
    is_dialogue = bool(scene.get("dialogue"))
    shot_type = _infer_shot_type(scene.get("visual", ""))

    extras = []
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

PROMPT_CACHE_FILE = "prompt_cache.json"


def load_prompt_cache(ep_out: Path) -> dict:
    f = ep_out / PROMPT_CACHE_FILE
    return json.loads(f.read_text()) if f.exists() else {}


def save_prompt_cache(ep_out: Path, cache: dict):
    (ep_out / PROMPT_CACHE_FILE).write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def enhance_scene_prompt(scene: dict, bible: dict, base_prompt: str) -> str:
    """
    Ask Claude to rewrite a raw scene visual description as a precise
    cinematographer-style video generation prompt.
    Falls back to base_prompt if Claude call fails.
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

    char_descs = []
    for cid in scene.get("characters", []):
        char = bible.get("characters", {}).get(cid, {})
        if char:
            char_descs.append(f"{char.get('name', cid)}: {char.get('visual', '')}")

    loc_id = scene.get("location", "")
    loc_desc = bible.get("world", {}).get("locations", {}).get(loc_id, loc_id)
    clip_sec = CLIP_LENGTHS.get(scene.get("clip_length", "medium"), CLIP_LENGTHS["medium"])["seconds"]

    system = (
        "You are a senior cinematographer's assistant specialising in animated short-form drama. "
        "Rewrite rough scene descriptions into precise, evocative video generation prompts. "
        "Return ONLY the enhanced prompt text — no explanation, no preamble, no markdown."
    )

    user = f"""SCENE TYPE: {scene_type}
CLIP LENGTH: {scene.get('clip_length', 'medium')} ({clip_sec}s)
RAW DESCRIPTION: {scene['visual']}
CHARACTERS: {chr(10).join(char_descs) if char_descs else 'none'}
LOCATION: {loc_desc}
SERIES STYLE: {bible['series']['style']}

Rewrite as a single paragraph (90–120 words) that:
- Leads with exact shot type (Medium two-shot / Extreme close-up / Wide establishing shot / etc.)
- Names the precise lighting setup (hard sidelight, harsh white searchlight, warm amber streetlight, etc.)
- Describes character pose and expression if present
- Specifies camera movement exactly (static locked-off / slow 2mm push-in / handheld drift / etc.)
- Includes depth-of-field note (shallow / deep / rack focus)
- Ends with 3–5 texture and mood keywords matching the series style

For dialogue scenes: static camera and clear face visibility are non-negotiable.
For establishing shots: prioritise atmosphere and environment."""

    try:
        return call_claude(system, user, max_tokens=300).strip()
    except Exception as e:
        print(f"      Prompt enhancement failed ({e}) — using base prompt")
        return base_prompt


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


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    r = requests.post(f"{SERVER}/prompt", json={"prompt": workflow, "client_id": client_id})
    if not r.ok:
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} — {r.text[:500]}",
            response=r,
        )
    return r.json()["prompt_id"]


def poll_until_done(prompt_id: str, poll_interval: int = 10, max_wait: int = 1800) -> bool:
    elapsed = 0
    while elapsed < max_wait:
        try:
            r = requests.get(f"{SERVER}/history/{prompt_id}")
            history = r.json()
            if prompt_id in history:
                if history[prompt_id].get("outputs"):
                    return True
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    return False
            q = requests.get(f"{SERVER}/queue").json()
            is_active = any(
                item[1] == prompt_id
                for item in q.get("queue_running", []) + q.get("queue_pending", [])
            )
            if is_active:
                print(f"\r    Running... ({elapsed}s)    ", end="", flush=True)
            elif elapsed > 30:
                time.sleep(5)
                r2 = requests.get(f"{SERVER}/history/{prompt_id}")
                if prompt_id in r2.json() and r2.json()[prompt_id].get("outputs"):
                    return True
                return True
        except requests.ConnectionError:
            print(f"\r    Reconnecting... ({elapsed}s)", end="", flush=True)
        time.sleep(poll_interval)
        elapsed += poll_interval
    return False


def extract_last_frame(video_path: str, output_path: str) -> bool:
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
         "-frames:v", "1", "-q:v", "2", output_path],
        capture_output=True, timeout=30,
    )
    return os.path.exists(output_path)


def find_latest_clip(prefix: str) -> str | None:
    if not COMFYUI_OUTPUT.is_dir():
        return None
    candidates = [f for f in os.listdir(COMFYUI_OUTPUT) if f.startswith(prefix) and f.endswith(".mp4")]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(COMFYUI_OUTPUT / f), reverse=True)
    return str(COMFYUI_OUTPUT / candidates[0])


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
    trim = f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS"

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
            f"[{amb_idx}:a]{trim},aformat=channel_layouts=stereo,volume=0.18[amb_raw]"
        )
        if has_vo:
            # Sidechain: VO signal triggers compression on ambient
            fp.append(
                "[amb_raw][vo]sidechaincompress="
                "threshold=0.015:ratio=5:attack=80:release=400:makeup=1[amb_out]"
            )
        else:
            fp.append("[amb_raw]volume=1.5[amb_out]")
        amb_out = "[amb_out]"
    else:
        amb_out = None

    if has_mus:
        fp.append(
            f"[{mus_idx}:a]{trim},aformat=channel_layouts=stereo,volume=0.07[mus_out]"
        )
        mus_out = "[mus_out]"
    else:
        mus_out = None

    # Final amix
    layers = [vo_out] + ([amb_out] if amb_out else []) + ([mus_out] if mus_out else [])
    if len(layers) == 1:
        fp.append(f"{layers[0]}acopy[audio_out]")
    else:
        fp.append(f"{''.join(layers)}amix=inputs={len(layers)}:duration=shortest:normalize=0[audio_out]")

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
        vo_inputs = (["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
                     if (audio and audio.exists()) else
                     ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                      "-map", "0:v:0", "-map", "1:a:0", "-shortest"])
        subprocess.run([
            "ffmpeg", "-y", "-i", clip_path, *vo_inputs,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k", out,
        ], capture_output=True, timeout=120)


def _get_video_duration(path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path
    ], capture_output=True, text=True, timeout=15)
    try:
        for stream in json.loads(result.stdout).get("streams", []):
            if stream.get("codec_type") == "video":
                return float(stream.get("duration", 0))
    except Exception:
        pass
    return 0.0


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
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file, "-c", "copy", str(output_path),
            ], capture_output=True, timeout=120)
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

        subprocess.run([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ], capture_output=True, timeout=300)

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
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", (
            "hue=s=0.70,"                          # desaturate to 70%
            "curves=all='0/0.04 0.5/0.48 1/0.92'," # S-curve: lift blacks, pull highs
            "noise=alls=7:allf=t+u,"               # film grain (temporal+uniform)
            "vignette=PI/4"                        # edge darkening
        ),
        "-c:a", "copy",
        str(output_path),
    ], capture_output=True, timeout=180)


def generate_srt(episode: dict, bible: dict, output_path: Path):
    """Generate an SRT subtitle file from episode scene narration and dialogue."""
    def srt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    entries = []
    t = 0.0
    for scene in episode["scenes"]:
        dur = CLIP_LENGTHS.get(scene.get("clip_length", "long"), CLIP_LENGTHS["long"])["seconds"]
        lines = []
        if scene.get("narration"):
            lines.append(scene["narration"])
        if scene.get("dialogue"):
            for d in scene["dialogue"]:
                char = bible.get("characters", {}).get(d["character"], {})
                name = char.get("name", d["character"]).upper()
                lines.append(f"{name}: \"{d['line']}\"")
        if lines:
            # Show subtitle for 85% of the clip duration (leave breathing room)
            sub_end = t + dur * 0.85
            entries.append((t, sub_end, "\n".join(lines)))
        t += dur

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
        print(f"      rife-ncnn-vulkan not found — skipping interpolation")
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

    Generates a high-quality still image for use as an I2V seed in HunyuanVideo.
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


def build_ref_workflow(prompt: str, seed: int, prefix: str,
                       width: int = 480, height: int = 320, steps: int = 30) -> dict:
    """HunyuanVideo 1.5 T2V workflow that generates a single frame.

    Used for character/location reference images when engine='hunyuan'.
    Produces images that match the video model's visual style exactly,
    which improves I2V seeding consistency.
    """
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "blurry, motion blur, multiple people, duplicate"}},
        "6": {"class_type": "EmptyHunyuanVideo15Latent", "inputs": {"width": width, "height": height, "length": 1, "batch_size": 1}},
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "8": {"class_type": "CFGGuider", "inputs": {"model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["8", 0], "sampler": ["11", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": f"refs/{prefix}"}},
    }


def generate_reference_images(series_name: str, bible: dict, force: bool = False,
                              engine: str = "flux"):
    """
    Generate canonical reference images for all characters and locations in the bible.

    engine:
      "flux"      — FLUX.1-schnell T2I (fast, high quality stills, different style from video model)
      "hunyuan"   — HunyuanVideo 1.5 single-frame T2V (matches video model style exactly)

    Character keys in the bible are already prefixed ("char_1", "char_2", …) as are
    location keys ("loc_1", …).  The prefix is used directly as the output filename
    so get_scene_seed_image() can find them without double-prefixing.
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
        items.append((char_id, f"Character: {char.get('name', char_id)}",
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
        items.append((loc_id, f"Location: {loc_id}",
                       ", ".join(filter(None, prompt_parts)), 640, 360))

    refs_out = COMFYUI_DIR / "output" / "refs"
    engine_label = "HunyuanVideo T2V" if engine == "hunyuan" else "FLUX T2I"
    print(f"  Generating {len(items)} reference images with {engine_label}...")

    for prefix, label, prompt, width, height in items:
        out_png = ref_dir / f"{prefix}.png"
        if out_png.exists() and not force:
            print(f"    {label} — exists, skipping")
            continue

        print(f"    {label} ({width}×{height}) [{engine_label}]...")
        if engine == "hunyuan":
            wf = build_ref_workflow(prompt, seed=999, prefix=prefix)
        else:
            wf = build_t2i_workflow(prompt, seed=999, prefix=prefix, width=width, height=height)
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

    # 1. Scene-specific reference — set explicitly via Scene Studio UI
    scene_ref_path = scene.get("reference_image")
    if scene_ref_path and Path(scene_ref_path).exists():
        return copy_to_input(scene_ref_path)

    is_close = any(w in visual_lower for w in ["close-up", "extreme close", "ecu"])
    is_establishing = any(w in visual_lower for w in ["wide shot", "establishing", "aerial", "wide establishing", "long shot"])
    is_dialogue = bool(scene.get("dialogue"))

    # 2. Character portrait seed — for any scene with characters that isn't
    # a wide/establishing shot. This gives HunyuanVideo's CLIP vision encoder
    # a strong reference for character appearance, which is the primary
    # consistency mechanism for this model (IP-Adapter is not compatible).
    has_characters = bool(scene.get("characters"))
    if has_characters and not is_establishing:
        char_key = scene["characters"][0]                          # e.g. "char_1"
        char_id  = char_key.removeprefix("char_")                  # e.g. "1"
        char_ref = ref_dir / f"char_{char_id}.png"
        if char_ref.exists():
            return copy_to_input(str(char_ref))

    # 3. Establishing/wide → location reference
    # Locations are keyed as "loc_1" in scene dicts; strip prefix similarly.
    if is_establishing and scene.get("location"):
        loc_key = scene["location"]                                # e.g. "loc_1"
        loc_id  = loc_key.removeprefix("loc_")                    # e.g. "1"
        loc_ref = ref_dir / f"loc_{loc_id}.png"
        if loc_ref.exists():
            return copy_to_input(str(loc_ref))

    return current_chain


# ─── Review / flagging ────────────────────────────────────────────────

FLAGS_FILE = "flags.json"


def load_flags(ep_out: Path) -> set[str]:
    f = ep_out / FLAGS_FILE
    if f.exists():
        return set(json.load(f.open()))
    return set()


def save_flags(ep_out: Path, flags: set[str]):
    with open(ep_out / FLAGS_FILE, "w") as f:
        json.dump(sorted(flags), f, indent=2)


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
        t = dur * (i / max(n - 1, 1))  # 0%, 50%, 100% of clip
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        result = subprocess.run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", clip_path,
            "-frames:v", "1", "-q:v", "3", "-vf", "scale=480:320",
            tmp_path,
        ], capture_output=True, timeout=15)
        if result.returncode == 0 and os.path.exists(tmp_path):
            with open(tmp_path, "rb") as f:
                frames_b64.append(base64.standard_b64encode(f.read()).decode())
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
        print(f"\n  Cross-episode carry-over: using ep{ep_num - 1:02d} end-frame as scene-1 seed")

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

        # Dynamic clip length: if TTS audio exists, match frame count to audio duration
        audio_file = audio_files[i] if i < len(audio_files) else None
        if audio_file and Path(str(audio_file)).exists():
            audio_dur = _get_video_duration(str(audio_file))
            if audio_dur > 0:
                frames = frames_for_duration(audio_dur, fps=mc["fps"])

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
        if i == 0 and carry_over_image:
            seed_image = carry_over_image
            print(f"      Using cross-episode carry-over as seed")
        else:
            seed_image = get_scene_seed_image(scene, args.series, current_image)

        # Collect all LoRAs for this scene (up to 2 chars + 1 location)
        scene_loras = get_scene_loras(scene, bible)
        if scene_loras:
            for ln, ls in scene_loras:
                print(f"      LoRA: {ln} (strength={ls})")

        # Per-scene denoise: use lower denoise for character close-ups/dialogue
        # so the portrait reference has stronger influence on appearance.
        base_denoise = getattr(args, 'denoise', DEFAULT_DENOISE)
        shot = _infer_shot_type(scene.get("visual", ""))
        is_dialogue = bool(scene.get("dialogue"))
        if seed_image and (shot == "closeup" or (is_dialogue and len(scene.get("characters", [])) == 1)):
            scene_denoise = min(base_denoise, 0.70)  # Faithful for solo character scenes
        else:
            scene_denoise = base_denoise

        mode = "i2v" if seed_image else "t2v"
        optimization = getattr(args, "optimization", "none")
        wf = build_video_workflow(
            video_model, mode, prompt, seed, clip_prefix, frames, res_config,
            negative_prompt=neg, steps=args.steps, denoise=scene_denoise,
            loras=scene_loras, image_name=seed_image, optimization=optimization,
        )

        # IP-Adapter: not compatible with HunyuanVideo DiT architecture.
        # Character consistency is handled through I2V seed images instead —
        # get_scene_seed_image() already feeds character portraits into dialogue/
        # close-up scenes via the HunyuanVideo15ImageToVideo CLIP vision encoder.
        # The --ip-adapter flag is kept for future model support.

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"      ERROR: ComfyUI not running at {SERVER}")
            sys.exit(1)

        success = poll_until_done(prompt_id)
        if success:
            print(f"\n      Done!")
            clip_path = find_latest_clip(clip_prefix)
            if clip_path:
                frame_path = str(COMFYUI_INPUT / f"chain_{clip_prefix}.png")
                if extract_last_frame(clip_path, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
        else:
            print(f"\n      WARNING: May have failed")

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
    if bad_clips:
        print(f"  WARNING: {len(bad_clips)} bad clip(s) detected:")
        for sid, reason in bad_clips.items():
            print(f"    {sid} — {reason}")
        # Auto-flag bad clips so they can be re-run with --flagged-only
        flags = load_flags(ep_out)
        flags.update(bad_clips.keys())
        save_flags(ep_out, flags)
        print(f"  Bad clips auto-flagged. Re-run with --flagged-only to regenerate.")
    else:
        print(f"    All {len(val_results)} clips OK")

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
        generate_srt(ep, bible, srt_path)
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

        # Generate a single still frame
        if engine == "hunyuan":
            wf = build_ref_workflow(prompt, seed=seed, prefix=prefix,
                                    width=res_config["width"], height=res_config["height"], steps=30)
        else:
            wf = build_t2i_workflow(prompt, seed=seed, prefix=prefix,
                                    width=res_config["width"], height=res_config["height"])

        # Inject LoRAs if available
        scene_loras = get_scene_loras(scene, bible)
        if engine == "hunyuan" and scene_loras:
            _insert_lora_chain(wf, scene_loras, unet_node="1", sampler_model_node="7")

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"    ERROR: ComfyUI not running at {SERVER}")
            return

        success = poll_until_done(prompt_id)
        if success:
            # Find and copy the generated frame
            if engine == "hunyuan":
                refs_out = COMFYUI_DIR / "output" / "storyboard"
            else:
                refs_out = COMFYUI_DIR / "output" / "refs"
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
    p_produce.add_argument("--video-model", choices=["hunyuan", "wan"], default="hunyuan",
                           help="Video generation model: hunyuan (HunyuanVideo 1.5) or wan (WAN 2.1 14B) (default: hunyuan)")
    p_produce.add_argument("--optimization", choices=["none", "balanced", "fast", "turbo"], default="none",
                           help="Speed optimization: none, balanced (30%% faster), fast (50%% faster), turbo (60%% faster, lower quality)")
    p_produce.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                           help="Generation resolution: 480p (8GB), 720p (24GB+), auto (detect VRAM) (default: auto)")
    p_produce.add_argument("--ip-adapter", action="store_true",
                           help="Use IP-Adapter for character consistency in dialogue/close-up scenes (requires ComfyUI-IPAdapter-plus)")
    p_produce.add_argument("--ip-adapter-strength", type=float, default=IP_ADAPTER_DEFAULT_STRENGTH,
                           help=f"IP-Adapter conditioning strength 0.0–1.0 (default: {IP_ADAPTER_DEFAULT_STRENGTH})")
    p_produce.add_argument("--lip-sync", action="store_true",
                           help="Apply Wav2Lip lip sync to dialogue scenes (requires Wav2Lip)")
    p_produce.add_argument("--tts-engine", choices=["edge", "xtts"], default="edge",
                           help="TTS engine: edge (Edge-TTS, fast) or xtts (XTTS v2, voice cloning) (default: edge)")

    p_all = sub.add_parser("produce-all", help="Produce all episodes")
    p_all.add_argument("series")
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
    p_all.add_argument("--video-model", choices=["hunyuan", "wan"], default="hunyuan",
                       help="Video generation model (default: hunyuan)")
    p_all.add_argument("--optimization", choices=["none", "balanced", "fast", "turbo"], default="none",
                       help="Speed optimization preset")
    p_all.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                       help="Generation resolution (default: auto)")
    p_all.add_argument("--ip-adapter", action="store_true",
                       help="Use IP-Adapter for character consistency")
    p_all.add_argument("--ip-adapter-strength", type=float, default=IP_ADAPTER_DEFAULT_STRENGTH)
    p_all.add_argument("--lip-sync", action="store_true",
                       help="Apply Wav2Lip lip sync to dialogue scenes")
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
    p_refs.add_argument("--engine", choices=["flux", "hunyuan"], default="flux",
                        help="Portrait engine: flux (FLUX T2I, fast, sharp stills) or hunyuan (HunyuanVideo single-frame, matches video style) (default: flux)")

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
    p_storyboard.add_argument("--engine", choices=["flux", "hunyuan"], default="flux",
                              help="Image engine: flux (fast T2I) or hunyuan (matches video model) (default: flux)")
    p_storyboard.add_argument("--resolution", choices=["480p", "720p", "auto"], default="auto",
                              help="Resolution for HunyuanVideo engine (default: auto)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

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
