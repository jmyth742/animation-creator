#!/usr/bin/env python3
"""
Chained I2V Story Pipeline

Takes a reference image and generates a multi-clip story video where each clip
is generated via Image-to-Video, using the last frame of the previous clip as
the start image for the next. This maintains visual continuity across clips.

Usage:
    python scripts/generate_story_i2v.py midnight_ramen --image reference.png
    python scripts/generate_story_i2v.py midnight_ramen --image reference.png --seed-base 500
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import requests

SERVER = "http://localhost:8188"

# ─── Workflow builders ────────────────────────────────────────────────

def build_t2v_workflow(prompt: str, seed: int, clip_prefix: str) -> dict:
    """Build a text-to-video workflow (for clip 1 fallback if no image)."""
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_name2": "byt5_small_glyphxl_fp16.safetensors", "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "EmptyHunyuanVideo15Latent", "inputs": {"width": 480, "height": 320, "length": 81, "batch_size": 1}},
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "8": {"class_type": "CFGGuider", "inputs": {"model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["7", 0], "scheduler": "simple", "steps": 15, "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["8", 0], "sampler": ["11", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": 24.0}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }


def build_i2v_workflow(prompt: str, image_name: str, seed: int, clip_prefix: str) -> dict:
    """Build an image-to-video workflow."""
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
            "width": 480, "height": 320, "length": 81, "batch_size": 1,
            "start_image": ["5", 0], "clip_vision_output": ["6", 0]
        }},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "11": {"class_type": "CFGGuider", "inputs": {"model": ["10", 0], "positive": ["7", 0], "negative": ["8", 0], "cfg": 1.0}},
        "12": {"class_type": "BasicScheduler", "inputs": {"model": ["10", 0], "scheduler": "simple", "steps": 15, "denoise": 1.0}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["13", 0], "guider": ["11", 0], "sampler": ["14", 0], "sigmas": ["12", 0], "latent_image": ["9", 0]}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["3", 0]}},
        "17": {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": 24.0}},
        "18": {"class_type": "SaveVideo", "inputs": {"video": ["17", 0], "filename_prefix": f"video/{clip_prefix}", "format": "mp4", "codec": "h264"}},
    }


# ─── ComfyUI API helpers ─────────────────────────────────────────────

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
                    print(f"\n  ERROR in execution")
                    return False

            q = requests.get(f"{SERVER}/queue").json()
            running = q.get("queue_running", [])
            pending = q.get("queue_pending", [])
            is_active = any(item[1] == prompt_id for item in running + pending)

            if is_active:
                print(f"\r  Running... ({elapsed}s elapsed)    ", end="", flush=True)
            elif elapsed > 30:
                time.sleep(5)
                r2 = requests.get(f"{SERVER}/history/{prompt_id}")
                if prompt_id in r2.json() and r2.json()[prompt_id].get("outputs"):
                    return True
                return True
        except requests.ConnectionError:
            print(f"\r  Reconnecting... ({elapsed}s)    ", end="", flush=True)

        time.sleep(poll_interval)
        elapsed += poll_interval

    print(f"\n  Timed out after {max_wait}s")
    return False


def extract_last_frame(video_path: str, output_path: str) -> bool:
    """Extract the last frame from a video using ffmpeg."""
    # Get frame count
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        # Fallback: just grab a frame near the end
        subprocess.run(
            ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", output_path],
            capture_output=True, timeout=30,
        )
        return os.path.exists(output_path)

    n_frames = int(result.stdout.strip())
    # Extract last frame
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vf", f"select=eq(n\\,{n_frames - 1})", "-frames:v", "1",
         "-q:v", "2", output_path],
        capture_output=True, timeout=30,
    )
    return os.path.exists(output_path)


def find_latest_clip(output_dir: str, prefix: str) -> str | None:
    """Find the most recently created clip matching a prefix."""
    candidates = [
        f for f in os.listdir(output_dir)
        if f.startswith(prefix) and f.endswith(".mp4")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
    return os.path.join(output_dir, candidates[0])


def copy_image_to_input(image_path: str, comfyui_input_dir: str) -> str:
    """Copy an image to ComfyUI's input dir, return the filename."""
    os.makedirs(comfyui_input_dir, exist_ok=True)
    basename = os.path.basename(image_path)
    dest = os.path.join(comfyui_input_dir, basename)
    if os.path.realpath(image_path) != os.path.realpath(dest):
        shutil.copy2(image_path, dest)
    return basename


# ─── Story definitions ───────────────────────────────────────────────

STORIES = {
    "midnight_ramen": {
        "title": "Midnight Ramen",
        "style": "Anime style, Studio Ghibli inspired, warm color palette, soft lighting, hand-drawn aesthetic, detailed backgrounds.",
        "clips": [
            "A lonely small ramen shop glows warmly on a quiet Tokyo side street at midnight. Rain falls gently, reflecting neon signs on the wet pavement. The camera slowly pushes in toward the entrance.",
            "Inside the tiny ramen shop, an old Japanese chef with a white headband stirs a steaming pot of broth. Steam rises in the warm lantern light. Close-up of his weathered hands working.",
            "A young woman in a wet navy trenchcoat steps through the curtain, shaking rain from her umbrella. She looks exhausted but relieved. She sits down at the wooden counter.",
            "The chef's hands expertly pull fresh noodles, stretching them rhythmically. Close-up shots of sliced chashu pork, a soft-boiled egg cut in half, fresh green onions being chopped. Steam rises.",
            "A beautiful bowl of ramen is placed on the counter. Rich golden broth, perfectly coiled noodles, sliced chashu, a halved soft egg, nori, and scallions. The camera slowly orbits the bowl.",
            "The young woman takes her first bite. Her eyes widen with emotion. She slows down, savoring the taste. A single tear rolls down her cheek. The old chef watches with a gentle smile.",
            "They talk quietly across the counter. She laughs for the first time, covering her mouth. He pours her tea. Rain continues outside. Warm interior contrasts with cold blue night.",
            "The woman bows deeply at the entrance. She steps into the rain, opening her umbrella. She looks back and smiles. The chef waves from behind the warm curtain.",
            "Wide shot of the quiet street. The woman walks away under her umbrella, growing smaller. The ramen shop glows behind her. Rain eases. A cat watches from a windowsill. Camera pulls back into the night sky.",
        ],
    },
    "forest_spirit": {
        "title": "The Forest Spirit",
        "style": "Anime style, Hayao Miyazaki inspired, lush greens and earth tones, dappled sunlight through trees, magical realism, hand-painted watercolor aesthetic.",
        "clips": [
            "Dense ancient forest at dawn. Shafts of golden sunlight pierce through massive moss-covered trees. Tiny glowing particles float in the air. A narrow dirt path winds deeper into the woods. The camera drifts forward slowly.",
            "A small girl with messy brown hair and a red backpack walks cautiously along the forest path. She touches the bark of enormous trees as she passes. Fireflies begin to appear around her despite it being morning.",
            "The girl discovers a clearing with a crystal-clear stream. She kneels at the water's edge. In the reflection, she sees not herself but a luminous deer-like spirit with branching antlers made of living wood and leaves.",
            "She looks up. The forest spirit stands across the stream, towering and gentle. Its body is translucent, made of woven branches and soft green light. Flowers bloom where its hooves touch the ground.",
            "The spirit lowers its great antlered head toward the girl. She reaches out her small hand. Where their fingers almost touch, golden light blooms and tiny butterflies made of light spiral outward.",
            "The spirit turns and walks deeper into the forest. The girl follows. As they walk together, the forest transforms around them. Dead trees spring back to life, flowers burst from the ground, mushrooms glow softly.",
            "They reach the heart of the forest. An ancient tree, the largest of all, stands hollow and dark. The spirit touches it with its nose. Golden light floods through the trunk, healing cracks, sprouting new branches and leaves.",
            "The great tree is alive again, its canopy spreading wide with fresh green leaves. Light rains down. The spirit turns to the girl, nods once, then dissolves into thousands of glowing particles that drift up through the canopy.",
            "The girl stands alone in the renewed forest, smiling with tears in her eyes. She places her hand on the great tree's bark. The camera rises slowly through the canopy into bright blue sky. Birds take flight.",
        ],
    },
}


# ─── Main pipeline ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a story video using chained Image-to-Video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate with a reference image (I2V for all clips)
  python scripts/generate_story_i2v.py midnight_ramen --image ref.png

  # Generate without reference (T2V for clip 1, I2V chain for rest)
  python scripts/generate_story_i2v.py forest_spirit

  # List available stories
  python scripts/generate_story_i2v.py --list
        """,
    )
    parser.add_argument("story", nargs="?", choices=list(STORIES.keys()), help="Story to generate")
    parser.add_argument("--image", "-i", help="Reference image for the first clip")
    parser.add_argument("--seed-base", type=int, default=1000, help="Base seed")
    parser.add_argument("--output", "-o", help="Final output path")
    parser.add_argument("--list", action="store_true", help="List available stories")
    parser.add_argument("--resume", action="store_true", help="Skip clips that already exist")
    args = parser.parse_args()

    if args.list or not args.story:
        print("Available stories:")
        for key, s in STORIES.items():
            print(f"  {key:20s} — {s['title']} ({len(s['clips'])} clips, ~{len(s['clips']) * 3.4:.0f}s)")
        return

    story = STORIES[args.story]
    clips = story["clips"]
    style = story["style"]
    title = story["title"]
    n = len(clips)

    root = os.path.join(os.path.dirname(__file__), "..")
    output_dir = os.path.join(root, "ComfyUI", "output", "video")
    comfyui_input = os.path.join(root, "ComfyUI", "input")
    os.makedirs(output_dir, exist_ok=True)

    print(f"{'=' * 60}")
    print(f"  {title}")
    print(f"  {n} clips × ~3.4s = ~{n * 3.4:.0f}s")
    if args.image:
        print(f"  Reference image: {args.image}")
        print(f"  Mode: I2V chain (all clips use image-to-video)")
    else:
        print(f"  Mode: T2V first clip → I2V chain for remaining clips")
    print(f"{'=' * 60}")
    print()

    current_image = None
    if args.image:
        current_image = copy_image_to_input(args.image, comfyui_input)
        print(f"  Reference image copied: {current_image}")

    for i, prompt in enumerate(clips, 1):
        clip_prefix = f"{args.story}_i2v_clip{i:02d}"
        seed = args.seed_base + i
        full_prompt = f"{prompt} {style}"

        # Resume: skip existing clips but still extract last frame for chaining
        if args.resume:
            existing = find_latest_clip(output_dir, clip_prefix)
            if existing:
                print(f"[{i}/{n}] {clip_prefix} — SKIPPED (exists)")
                # Extract last frame for the next clip
                frame_path = os.path.join(comfyui_input, f"chain_frame_{i:02d}.png")
                if extract_last_frame(existing, frame_path):
                    current_image = f"chain_frame_{i:02d}.png"
                continue

        print(f"[{i}/{n}] {clip_prefix}")
        print(f"  {prompt[:70]}...")

        if current_image:
            # I2V mode
            print(f"  Mode: I2V (from {current_image})")
            wf = build_i2v_workflow(full_prompt, current_image, seed, clip_prefix)
        else:
            # T2V mode (first clip, no reference image)
            print(f"  Mode: T2V (no reference image)")
            wf = build_t2v_workflow(full_prompt, seed, clip_prefix)

        try:
            prompt_id = queue_prompt(wf)
        except requests.ConnectionError:
            print(f"  ERROR: Cannot connect to ComfyUI at {SERVER}")
            sys.exit(1)

        print(f"  Queued: {prompt_id}")
        success = poll_until_done(prompt_id)

        if success:
            print(f"\n  Clip {i} complete!")
            # Find the output and extract last frame for chaining
            clip_path = find_latest_clip(output_dir, clip_prefix)
            if clip_path:
                frame_path = os.path.join(comfyui_input, f"chain_frame_{i:02d}.png")
                if extract_last_frame(clip_path, frame_path):
                    current_image = f"chain_frame_{i:02d}.png"
                    print(f"  Extracted last frame → {current_image}")
                else:
                    print(f"  WARNING: Could not extract last frame, next clip will reuse previous image")
        else:
            print(f"\n  WARNING: Clip {i} may have failed. Continuing with previous frame...")

        print()

    # ─── Stitch all clips ─────────────────────────────────────────────
    print(f"{'=' * 60}")
    print(f"  Stitching {n} clips")
    print(f"{'=' * 60}")

    concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    clip_count = 0
    try:
        for i in range(1, n + 1):
            clip_prefix = f"{args.story}_i2v_clip{i:02d}"
            clip_path = find_latest_clip(output_dir, clip_prefix)
            if clip_path:
                concat_file.write(f"file '{os.path.realpath(clip_path)}'\n")
                print(f"  Clip {i}: {os.path.basename(clip_path)}")
                clip_count += 1
            else:
                print(f"  Clip {i}: MISSING — skipped")
        concat_file.close()

        if clip_count == 0:
            print("  No clips found. Nothing to stitch.")
            return

        final = args.output or os.path.join(output_dir, f"{args.story}_i2v_final.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file.name, "-c", "copy", final],
            capture_output=True, timeout=60,
        )

        duration = clip_count * 3.4
        print(f"\n  Final video: {final}")
        print(f"  {clip_count} clips, ~{duration:.0f} seconds")
        print()
    finally:
        os.unlink(concat_file.name)


if __name__ == "__main__":
    main()
