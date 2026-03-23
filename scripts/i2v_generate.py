#!/usr/bin/env python3
"""Generate video from a reference image using HunyuanVideo 1.5 I2V."""

import argparse
import json
import os
import shutil
import sys
import time
import uuid

import requests

SERVER = "http://localhost:8188"

BASE_WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "..", "workflows", "i2v_v15_480p.json")


def load_workflow(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


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
                outputs = history[prompt_id].get("outputs", {})
                if outputs:
                    return True

            q = requests.get(f"{SERVER}/queue").json()
            running = q.get("queue_running", [])
            pending = q.get("queue_pending", [])
            is_active = any(item[1] == prompt_id for item in running + pending)

            if is_active:
                print(f"\r  Running... ({elapsed}s elapsed)", end="", flush=True)
            elif elapsed > 30:
                time.sleep(5)
                r2 = requests.get(f"{SERVER}/history/{prompt_id}")
                h2 = r2.json()
                if prompt_id in h2 and h2[prompt_id].get("outputs"):
                    return True
                return True
        except requests.ConnectionError:
            print(f"\r  Reconnecting... ({elapsed}s)", end="", flush=True)

        time.sleep(poll_interval)
        elapsed += poll_interval

    print(f"\n  Timed out after {max_wait}s")
    return False


def main():
    parser = argparse.ArgumentParser(description="Generate video from a reference image")
    parser.add_argument("image", help="Path to input image")
    parser.add_argument("--prompt", "-p", default="The scene comes to life with gentle motion. Cinematic, smooth animation.",
                        help="Text prompt describing desired motion/style")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Random seed")
    parser.add_argument("--frames", type=int, default=81, help="Frame count (default 81 = ~3.4s)")
    parser.add_argument("--steps", type=int, default=15, help="Inference steps")
    parser.add_argument("--width", type=int, default=480, help="Output width")
    parser.add_argument("--height", type=int, default=320, help="Output height")
    parser.add_argument("--prefix", default="hunyuan15_i2v", help="Output filename prefix")
    args = parser.parse_args()

    # Copy image to ComfyUI input directory
    comfyui_input = os.path.join(os.path.dirname(__file__), "..", "ComfyUI", "input")
    os.makedirs(comfyui_input, exist_ok=True)

    img_basename = os.path.basename(args.image)
    dest = os.path.join(comfyui_input, img_basename)
    if os.path.realpath(args.image) != os.path.realpath(dest):
        shutil.copy2(args.image, dest)
        print(f"Copied {args.image} -> {dest}")

    # Load and configure workflow
    wf = load_workflow(BASE_WORKFLOW_PATH)
    wf["5"]["inputs"]["image"] = img_basename
    wf["7"]["inputs"]["text"] = args.prompt
    wf["9"]["inputs"]["width"] = args.width
    wf["9"]["inputs"]["height"] = args.height
    wf["9"]["inputs"]["length"] = args.frames
    wf["13"]["inputs"]["noise_seed"] = args.seed
    wf["12"]["inputs"]["steps"] = args.steps
    wf["18"]["inputs"]["filename_prefix"] = f"video/{args.prefix}"

    print(f"Image-to-Video generation:")
    print(f"  Input: {img_basename}")
    print(f"  Prompt: {args.prompt[:80]}...")
    print(f"  Resolution: {args.width}x{args.height}, {args.frames} frames")
    print(f"  Steps: {args.steps}, Seed: {args.seed}")

    try:
        prompt_id = queue_prompt(wf)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to ComfyUI at {SERVER}")
        sys.exit(1)

    print(f"  Queued: {prompt_id}")
    print("  Waiting for completion...")

    success = poll_until_done(prompt_id)
    if success:
        print(f"\n  Done! Check ComfyUI/output/video/{args.prefix}*.mp4")
    else:
        print(f"\n  Generation may have failed. Check ComfyUI logs.")


if __name__ == "__main__":
    main()
