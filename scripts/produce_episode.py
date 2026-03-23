#!/usr/bin/env python3
"""
Series Production Pipeline

Reads a series definition JSON and produces an episode:
1. Generates video clips (T2V for first scene, I2V chained for rest)
2. Exports narration/dialogue scripts for voiceover
3. Stitches clips into a final video
4. Optionally muxes voiceover audio onto the final video

Usage:
    # List episodes in a series
    python scripts/produce_episode.py series/example_series.json --list

    # Produce episode 1
    python scripts/produce_episode.py series/example_series.json ep01

    # Produce with a reference image
    python scripts/produce_episode.py series/example_series.json ep01 --image ref.png

    # Resume a partially completed episode
    python scripts/produce_episode.py series/example_series.json ep01 --resume

    # Export just the script (no video generation)
    python scripts/produce_episode.py series/example_series.json ep01 --script-only

    # Mux voiceover audio onto completed video
    python scripts/produce_episode.py series/example_series.json ep01 --mux-audio voiceover.mp3
"""

import argparse
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

SERVER = "http://localhost:8188"


# ─── Series loader ───────────────────────────────────────────────────

def load_series(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_episode(series_data: dict, episode_id: str) -> dict | None:
    for ep in series_data["episodes"]:
        if ep["id"] == episode_id:
            return ep
    return None


def build_scene_prompt(scene: dict, series_data: dict) -> str:
    """Build a full visual prompt for a scene, incorporating character
    descriptions, location details, and series style."""
    parts = []

    # Scene visual description
    parts.append(scene["visual"])

    # Add character visuals for consistency
    for char_id in scene.get("characters", []):
        char = series_data.get("characters", {}).get(char_id)
        if char:
            parts.append(f"Character: {char['visual']}")

    # Add location details
    loc_id = scene.get("location")
    if loc_id:
        loc_desc = series_data.get("world", {}).get("locations", {}).get(loc_id)
        if loc_desc:
            parts.append(f"Setting: {loc_desc}")

    # Add series style
    parts.append(series_data["series"]["style"])

    return " ".join(parts)


# ─── Script export ───────────────────────────────────────────────────

def export_script(episode: dict, series_data: dict, output_path: str):
    """Export the episode script with narration and dialogue for voiceover."""
    lines = []
    title = series_data["series"]["title"]
    ep_title = episode["title"]

    lines.append(f"{'=' * 60}")
    lines.append(f"  {title}")
    lines.append(f"  Episode: {episode['id']} — {ep_title}")
    lines.append(f"{'=' * 60}")
    lines.append("")
    lines.append(f"SUMMARY: {episode['summary']}")
    lines.append("")

    # Character voice notes
    chars_in_ep = set()
    for scene in episode["scenes"]:
        chars_in_ep.update(scene.get("characters", []))

    if chars_in_ep:
        lines.append("CHARACTER VOICE NOTES:")
        for char_id in sorted(chars_in_ep):
            char = series_data.get("characters", {}).get(char_id, {})
            lines.append(f"  {char.get('name', char_id)}: {char.get('voice_notes', 'No notes')}")
        lines.append("")

    lines.append("-" * 60)
    lines.append("")

    total_duration = 0
    for i, scene in enumerate(episode["scenes"], 1):
        duration = scene.get("duration_seconds", 3.4)
        total_duration += duration
        timestamp = format_timestamp(total_duration - duration)

        lines.append(f"SCENE {i} [{timestamp}] — {scene.get('location', 'unknown')}")
        lines.append(f"  Visual: {scene['visual'][:100]}...")
        lines.append("")

        # Narration
        if scene.get("narration"):
            lines.append(f"  NARRATION:")
            lines.append(f"    {scene['narration']}")
            lines.append("")

        # Dialogue
        if scene.get("dialogue"):
            lines.append(f"  DIALOGUE:")
            for d in scene["dialogue"]:
                char = series_data.get("characters", {}).get(d["character"], {})
                name = char.get("name", d["character"]).upper()
                lines.append(f"    {name}: \"{d['line']}\"")
            lines.append("")

        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Total duration: ~{total_duration:.0f} seconds ({len(episode['scenes'])} scenes)")
    lines.append("")

    # Write to file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    return output_path


def format_timestamp(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


# ─── Voiceover timing export ─────────────────────────────────────────

def export_voiceover_timing(episode: dict, series_data: dict, output_path: str):
    """Export a JSON file with per-scene timing for voiceover alignment."""
    scenes = []
    current_time = 0.0

    for i, scene in enumerate(episode["scenes"], 1):
        duration = scene.get("duration_seconds", 3.4)
        entry = {
            "scene": i,
            "id": scene["id"],
            "start_time": round(current_time, 2),
            "end_time": round(current_time + duration, 2),
            "duration": duration,
            "location": scene.get("location"),
        }

        if scene.get("narration"):
            entry["narration"] = scene["narration"]

        if scene.get("dialogue"):
            entry["dialogue"] = [
                {
                    "character": series_data.get("characters", {}).get(d["character"], {}).get("name", d["character"]),
                    "line": d["line"],
                }
                for d in scene["dialogue"]
            ]

        scenes.append(entry)
        current_time += duration

    data = {
        "series": series_data["series"]["title"],
        "episode": episode["id"],
        "episode_title": episode["title"],
        "total_duration": round(current_time, 2),
        "scenes": scenes,
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return output_path


# ─── Video generation ────────────────────────────────────────────────

def build_t2v_workflow(prompt: str, seed: int, clip_prefix: str, fmt: dict) -> dict:
    w, h = fmt["resolution"]
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "EmptyHunyuanVideo15Latent", "inputs": {"width": w, "height": h, "length": fmt["frames_per_clip"], "batch_size": 1}},
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "8": {"class_type": "CFGGuider", "inputs": {"model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": "simple", "steps": fmt["steps"], "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["8", 0], "sampler": ["11", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(fmt["fps"])}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }


def build_i2v_workflow(prompt: str, image_name: str, seed: int, clip_prefix: str, fmt: dict) -> dict:
    w, h = fmt["resolution"]
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "hunyuanvideo1.5_480p_i2v_cfg_distilled-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "sigclip_vision_patch14_384.safetensors"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "6": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["4", 0], "image": ["5", 0], "crop": "center"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "9": {"class_type": "HunyuanVideo15ImageToVideo", "inputs": {
            "positive": ["7", 0], "negative": ["8", 0], "vae": ["3", 0],
            "width": w, "height": h, "length": fmt["frames_per_clip"], "batch_size": 1,
            "start_image": ["5", 0], "clip_vision_output": ["6", 0]
        }},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "11": {"class_type": "CFGGuider", "inputs": {"model": ["10", 0], "positive": ["7", 0], "negative": ["8", 0], "cfg": 1.0}},
        "12": {"class_type": "BasicScheduler", "inputs": {"model": ["10", 0], "scheduler": "simple", "steps": fmt["steps"], "denoise": 1.0}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["13", 0], "guider": ["11", 0], "sampler": ["14", 0], "sigmas": ["12", 0], "latent_image": ["9", 0]}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["3", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": float(fmt["fps"])}},
        "18": {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    r = requests.post(f"{SERVER}/prompt", json={"prompt": workflow, "client_id": client_id})
    r.raise_for_status()
    return r.json()["prompt_id"]


def poll_until_done(prompt_id: str, poll_interval: int = 10, max_wait: int = 1800) -> bool:
    elapsed = 0
    while elapsed < max_wait:
        try:
            r = requests.get(f"{SERVER}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
            if prompt_id in history:
                if history[prompt_id].get("outputs"):
                    return True
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    print(f"\n    ERROR in execution")
                    return False

            q = requests.get(f"{SERVER}/queue").json()
            running = q.get("queue_running", [])
            pending = q.get("queue_pending", [])
            is_active = any(item[1] == prompt_id for item in running + pending)

            if is_active:
                print(f"\r    Running... ({elapsed}s elapsed)    ", end="", flush=True)
            elif elapsed > 30:
                time.sleep(5)
                r2 = requests.get(f"{SERVER}/history/{prompt_id}")
                if prompt_id in r2.json() and r2.json()[prompt_id].get("outputs"):
                    return True
                return True
        except requests.ConnectionError:
            print(f"\r    Reconnecting... ({elapsed}s)    ", end="", flush=True)

        time.sleep(poll_interval)
        elapsed += poll_interval

    print(f"\n    Timed out after {max_wait}s")
    return False


def extract_last_frame(video_path: str, output_path: str) -> bool:
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
         "-frames:v", "1", "-q:v", "2", output_path],
        capture_output=True, timeout=30,
    )
    return os.path.exists(output_path)


def find_latest_clip(output_dir: str, prefix: str) -> str | None:
    if not os.path.isdir(output_dir):
        return None
    candidates = [f for f in os.listdir(output_dir) if f.startswith(prefix) and f.endswith(".mp4")]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
    return os.path.join(output_dir, candidates[0])


def copy_to_input(src: str, comfyui_input: str) -> str:
    os.makedirs(comfyui_input, exist_ok=True)
    basename = os.path.basename(src)
    dest = os.path.join(comfyui_input, basename)
    if os.path.realpath(src) != os.path.realpath(dest):
        shutil.copy2(src, dest)
    return basename


# ─── Main pipeline ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Produce an episode from a series definition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("series_file", help="Path to series JSON file")
    parser.add_argument("episode_id", nargs="?", help="Episode ID to produce (e.g. ep01)")
    parser.add_argument("--image", "-i", help="Reference image for first scene")
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--resume", action="store_true", help="Skip completed scenes")
    parser.add_argument("--list", action="store_true", help="List episodes")
    parser.add_argument("--script-only", action="store_true", help="Export script without generating video")
    parser.add_argument("--mux-audio", help="Path to voiceover audio to mux onto final video")
    args = parser.parse_args()

    series_data = load_series(args.series_file)
    series_title = series_data["series"]["title"]

    if args.list or not args.episode_id:
        print(f"\n  {series_title}")
        print(f"  {'=' * 50}")
        for ep in series_data["episodes"]:
            n = len(ep["scenes"])
            dur = sum(s.get("duration_seconds", 3.4) for s in ep["scenes"])
            print(f"  {ep['id']:10s}  {ep['title']:30s}  {n} scenes  ~{dur:.0f}s")
        print()
        return

    episode = get_episode(series_data, args.episode_id)
    if not episode:
        print(f"Episode '{args.episode_id}' not found.")
        sys.exit(1)

    root = Path(__file__).parent.parent
    ep_output = root / "output" / args.episode_id
    ep_output.mkdir(parents=True, exist_ok=True)
    video_output_dir = root / "ComfyUI" / "output" / "video"
    video_output_dir.mkdir(parents=True, exist_ok=True)
    comfyui_input = root / "ComfyUI" / "input"
    fmt = series_data["series"]["format"]

    scenes = episode["scenes"]
    n = len(scenes)
    total_dur = sum(s.get("duration_seconds", 3.4) for s in scenes)

    # ─── Always export script and timing ──────────────────────────
    script_path = ep_output / f"{args.episode_id}_script.txt"
    timing_path = ep_output / f"{args.episode_id}_timing.json"

    export_script(episode, series_data, str(script_path))
    export_voiceover_timing(episode, series_data, str(timing_path))

    print(f"\n{'=' * 60}")
    print(f"  {series_title} — {episode['title']}")
    print(f"  {n} scenes × ~3.4s = ~{total_dur:.0f}s")
    print(f"{'=' * 60}")
    print(f"  Script:  {script_path}")
    print(f"  Timing:  {timing_path}")

    if args.script_only:
        print(f"\n  Script exported. Record voiceover using the timing file,")
        print(f"  then run again with --mux-audio to combine.")
        return

    # ─── Mux audio onto existing video ────────────────────────────
    if args.mux_audio:
        final_video = ep_output / f"{args.episode_id}_final.mp4"
        if not final_video.exists():
            print(f"  ERROR: Final video not found at {final_video}")
            print(f"  Generate video first, then mux audio.")
            sys.exit(1)
        output_with_audio = ep_output / f"{args.episode_id}_with_audio.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(final_video),
            "-i", args.mux_audio,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_with_audio),
        ], capture_output=True, timeout=120)
        print(f"\n  Output with audio: {output_with_audio}")
        return

    # ─── Generate video clips ─────────────────────────────────────
    if args.image:
        print(f"  Reference: {args.image}")
        print(f"  Mode: I2V chain (all scenes)")
    else:
        print(f"  Mode: T2V scene 1 → I2V chain")
    print()

    current_image = None
    if args.image:
        current_image = copy_to_input(args.image, str(comfyui_input))

    for i, scene in enumerate(scenes, 1):
        clip_prefix = scene["id"]
        seed = args.seed_base + i
        prompt = build_scene_prompt(scene, series_data)

        # Resume check
        if args.resume:
            existing = find_latest_clip(str(video_output_dir), clip_prefix)
            if existing:
                print(f"  [{i}/{n}] {clip_prefix} — SKIPPED (exists)")
                frame_path = str(comfyui_input / f"chain_{clip_prefix}.png")
                if extract_last_frame(existing, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
                continue

        loc = scene.get("location", "?")
        chars = ", ".join(scene.get("characters", []))
        print(f"  [{i}/{n}] {clip_prefix}  [{loc}] [{chars}]")
        print(f"    {scene['visual'][:70]}...")

        if current_image:
            print(f"    Mode: I2V (from {current_image})")
            wf = build_i2v_workflow(prompt, current_image, seed, clip_prefix, fmt)
        else:
            print(f"    Mode: T2V")
            wf = build_t2v_workflow(prompt, seed, clip_prefix, fmt)

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"    ERROR: Cannot connect to ComfyUI at {SERVER}")
            sys.exit(1)

        print(f"    Queued: {prompt_id}")
        success = poll_until_done(prompt_id)

        if success:
            print(f"\n    Scene {i} complete!")
            clip_path = find_latest_clip(str(video_output_dir), clip_prefix)
            if clip_path:
                frame_path = str(comfyui_input / f"chain_{clip_prefix}.png")
                if extract_last_frame(clip_path, frame_path):
                    current_image = f"chain_{clip_prefix}.png"
                    print(f"    Chained → {current_image}")
        else:
            print(f"\n    WARNING: Scene {i} may have failed. Continuing...")

        print()

    # ─── Stitch ──────────────────────────────────────────────────
    print(f"  Stitching {n} scenes...")
    concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    clip_count = 0
    try:
        for scene in scenes:
            clip_path = find_latest_clip(str(video_output_dir), scene["id"])
            if clip_path:
                concat_file.write(f"file '{os.path.realpath(clip_path)}'\n")
                clip_count += 1
            else:
                print(f"    MISSING: {scene['id']}")
        concat_file.close()

        if clip_count == 0:
            print("    No clips found.")
            return

        final = ep_output / f"{args.episode_id}_final.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_file.name, "-c", "copy", str(final)],
            capture_output=True, timeout=60,
        )

        print(f"\n{'=' * 60}")
        print(f"  Final video: {final}")
        print(f"  {clip_count}/{n} scenes, ~{clip_count * 3.4:.0f}s")
        print()
        print(f"  Next steps:")
        print(f"    1. Review the script:  {script_path}")
        print(f"    2. Record voiceover using timing: {timing_path}")
        print(f"    3. Mux audio:  python scripts/produce_episode.py {args.series_file} {args.episode_id} --mux-audio voiceover.mp3")
        print()
    finally:
        os.unlink(concat_file.name)


if __name__ == "__main__":
    main()
