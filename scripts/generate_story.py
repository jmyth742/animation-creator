#!/usr/bin/env python3
"""Generate a multi-clip story video from a sequence of scene prompts."""

import argparse
import copy
import os
import subprocess
import sys
import tempfile
import time
import uuid

import requests

SERVER = "http://localhost:8188"
WS_SERVER = "ws://localhost:8188/ws"

# Base workflow template — v1.5 distilled, 480×320, 81 frames
BASE_WORKFLOW = {
    "1": {
        "class_type": "UnetLoaderGGUF",
        "inputs": {
            "unet_name": "hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf"
        }
    },
    "2": {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "clip_name2": "byt5_small_glyphxl_fp16.safetensors",
            "type": "hunyuan_video_15"
        }
    },
    "3": {
        "class_type": "VAELoader",
        "inputs": {
            "vae_name": "hunyuanvideo15_vae_fp16.safetensors"
        }
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["2", 0],
            "text": ""
        }
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["2", 0],
            "text": ""
        }
    },
    "6": {
        "class_type": "EmptyHunyuanVideo15Latent",
        "inputs": {
            "width": 480,
            "height": 320,
            "length": 81,
            "batch_size": 1
        }
    },
    "7": {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": ["1", 0],
            "shift": 5.0
        }
    },
    "8": {
        "class_type": "CFGGuider",
        "inputs": {
            "model": ["7", 0],
            "positive": ["4", 0],
            "negative": ["5", 0],
            "cfg": 1.0
        }
    },
    "9": {
        "class_type": "BasicScheduler",
        "inputs": {
            "model": ["7", 0],
            "scheduler": "simple",
            "steps": 15,
            "denoise": 1.0
        }
    },
    "10": {
        "class_type": "RandomNoise",
        "inputs": {
            "noise_seed": 42
        }
    },
    "11": {
        "class_type": "KSamplerSelect",
        "inputs": {
            "sampler_name": "euler"
        }
    },
    "12": {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["10", 0],
            "guider": ["8", 0],
            "sampler": ["11", 0],
            "sigmas": ["9", 0],
            "latent_image": ["6", 0]
        }
    },
    "13": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["12", 0],
            "vae": ["3", 0]
        }
    },
    "14": {
        "class_type": "CreateVideo",
        "inputs": {
            "images": ["13", 0],
            "fps": 24.0
        }
    },
    "15": {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["14", 0],
            "filename_prefix": "video/story_clip",
            "format": "mp4",
            "codec": "h264"
        }
    }
}


# ─── Story definitions ───────────────────────────────────────────────

STORIES = {
    "midnight_ramen": {
        "title": "Midnight Ramen",
        "style": "Anime style, Studio Ghibli inspired, warm color palette, soft lighting, hand-drawn aesthetic, detailed backgrounds.",
        "clips": [
            # 1 — Establishing shot
            "A lonely small ramen shop glows warmly on a quiet Tokyo side street at midnight. Rain falls gently, reflecting neon signs on the wet pavement. A wooden sign reads 'RAMEN'. The camera slowly pushes in toward the shop entrance. No people visible yet.",

            # 2 — The chef
            "Inside the tiny ramen shop, an old Japanese chef with a white headband stands behind the counter. He carefully stirs a steaming pot of broth with a long ladle, steam rising. The shop is cozy with wooden walls and warm lantern light. Close-up of his weathered hands working.",

            # 3 — The customer arrives
            "A young woman in a wet navy trenchcoat steps through the ramen shop curtain, shaking rain from her umbrella. She looks exhausted but relieved. The old chef nods to her warmly without speaking. She sits down at the counter on a wooden stool.",

            # 4 — Cooking montage
            "The chef's hands expertly pull fresh noodles, stretching them in rhythmic motions. Close-up shots of ingredients being prepared: sliced chashu pork, a soft-boiled egg cut in half with golden yolk, fresh green onions being chopped. Steam rises dramatically.",

            # 5 — The bowl
            "A beautiful bowl of ramen is placed on the wooden counter. Rich golden broth, perfectly coiled noodles, sliced chashu, a halved soft egg, nori seaweed, and chopped scallions. Steam curls upward. The camera slowly orbits around the bowl. Warm lighting.",

            # 6 — Eating
            "The young woman picks up chopsticks and takes her first bite of noodles. Her eyes widen with emotion, and she slows down, savoring the taste. A single tear rolls down her cheek. The old chef watches from behind the counter with a gentle knowing smile.",

            # 7 — Connection
            "The young woman and the old chef talk quietly across the counter. She laughs for the first time, covering her mouth. He pours her a small cup of tea. The rain continues outside the window. The warm interior contrasts with the cold blue night outside.",

            # 8 — Departure
            "The young woman bows deeply to the old chef at the shop entrance. She steps out into the rain, opening her umbrella. She looks back once and smiles. The chef waves from behind the warm glow of the shop curtain.",

            # 9 — Closing shot
            "Wide shot of the quiet Tokyo street at night. The young woman walks away under her umbrella, growing smaller. The ramen shop glows warmly behind her. The rain begins to ease. A cat watches from a windowsill. The camera slowly pulls back and up into the night sky.",
        ],
    },
}


def queue_prompt(workflow: dict) -> str:
    """Queue a workflow, return prompt_id."""
    client_id = str(uuid.uuid4())
    r = requests.post(
        f"{SERVER}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    r.raise_for_status()
    return r.json()["prompt_id"]


def poll_until_done(prompt_id: str, poll_interval: int = 10, max_wait: int = 1800) -> bool:
    """Poll /history until the prompt completes. No websocket needed.
    max_wait: give up after this many seconds (default 30 min).
    """
    import time
    elapsed = 0
    while elapsed < max_wait:
        try:
            r = requests.get(f"{SERVER}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
            if prompt_id in history:
                entry = history[prompt_id]
                # Check for completion
                outputs = entry.get("outputs", {})
                status = entry.get("status", {})
                if status.get("completed", False) or outputs:
                    return True
                # Check for error
                if status.get("status_str") == "error":
                    print(f"\n  ERROR in execution")
                    return False
            # Also check queue to see position
            q = requests.get(f"{SERVER}/queue").json()
            running = q.get("queue_running", [])
            pending = q.get("queue_pending", [])
            is_running = any(item[1] == prompt_id for item in running)
            is_pending = any(item[1] == prompt_id for item in pending)
            if is_running:
                print(f"\r  Running... ({elapsed}s elapsed)", end="", flush=True)
            elif is_pending:
                print(f"\r  Queued... ({elapsed}s elapsed)", end="", flush=True)
            elif not is_running and not is_pending and elapsed > 30:
                # Not in queue and not in history with outputs — check one more time
                time.sleep(5)
                r2 = requests.get(f"{SERVER}/history/{prompt_id}")
                h2 = r2.json()
                if prompt_id in h2 and h2[prompt_id].get("outputs"):
                    return True
                # Truly gone — likely completed between checks
                return True
        except requests.ConnectionError:
            print(f"\r  ComfyUI not responding, retrying... ({elapsed}s)", end="", flush=True)
        time.sleep(poll_interval)
        elapsed += poll_interval

    print(f"\n  Timed out after {max_wait}s")
    return False


def queue_and_wait(workflow: dict) -> bool:
    """Queue workflow and poll until done."""
    prompt_id = queue_prompt(workflow)
    print(f"  Queued: {prompt_id}")
    return poll_until_done(prompt_id)


def build_workflow(prompt: str, style: str, clip_prefix: str, seed: int) -> dict:
    wf = copy.deepcopy(BASE_WORKFLOW)
    wf["4"]["inputs"]["text"] = f"{prompt} {style}"
    wf["10"]["inputs"]["noise_seed"] = seed
    wf["15"]["inputs"]["filename_prefix"] = f"video/{clip_prefix}"
    return wf


def main():
    parser = argparse.ArgumentParser(description="Generate a multi-clip story video")
    parser.add_argument("story", choices=list(STORIES.keys()), help="Story to generate")
    parser.add_argument("--seed-base", type=int, default=1000, help="Base seed (each clip adds its index)")
    parser.add_argument("--output", "-o", default=None, help="Final output path")
    args = parser.parse_args()

    story = STORIES[args.story]
    clips = story["clips"]
    style = story["style"]
    title = story["title"]
    n = len(clips)

    print(f"=== {title} — {n} clips × ~3.4s = ~{n * 3.4:.0f}s ===")
    print()

    output_dir = os.path.join(os.path.dirname(__file__), "..", "ComfyUI", "output", "video")

    for i, prompt in enumerate(clips, 1):
        clip_prefix = f"{args.story}_clip{i:02d}"
        seed = args.seed_base + i

        # Resume: skip if clip already exists
        existing = [f for f in os.listdir(output_dir) if f.startswith(clip_prefix) and f.endswith(".mp4")] if os.path.isdir(output_dir) else []
        if existing:
            print(f"--- [{i}/{n}] {clip_prefix} --- SKIPPED (already exists: {existing[0]})")
            continue

        print(f"--- [{i}/{n}] {clip_prefix} ---")
        print(f"  {prompt[:80]}...")

        wf = build_workflow(prompt, style, clip_prefix, seed)

        try:
            success = queue_and_wait(wf)
        except requests.ConnectionError:
            print(f"  ERROR: Cannot connect to ComfyUI at {SERVER}")
            sys.exit(1)

        if not success:
            print(f"  WARNING: Clip {i} may have failed. Continuing...")
        print()

    # Stitch with ffmpeg
    print(f"=== Stitching {n} clips with ffmpeg ===")
    concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        for i in range(1, n + 1):
            clip_prefix = f"{args.story}_clip{i:02d}"
            # Find latest matching file
            candidates = sorted(
                [f for f in os.listdir(output_dir) if f.startswith(clip_prefix) and f.endswith(".mp4")],
                key=lambda f: os.path.getmtime(os.path.join(output_dir, f)),
                reverse=True,
            )
            if not candidates:
                print(f"  WARNING: No output found for clip {i}, skipping")
                continue
            path = os.path.realpath(os.path.join(output_dir, candidates[0]))
            concat_file.write(f"file '{path}'\n")
            print(f"  Clip {i}: {candidates[0]}")
        concat_file.close()

        final = args.output or os.path.join(output_dir, f"{args.story}_final.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file.name, "-c", "copy", final],
            capture_output=True,
        )
        print(f"\n=== Final video: {final} ===")
        print(f"    {n} clips, ~{n * 3.4:.0f} seconds")
    finally:
        os.unlink(concat_file.name)


if __name__ == "__main__":
    main()
