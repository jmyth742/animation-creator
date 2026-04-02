#!/usr/bin/env python3
"""Test WAN 2.2 I2V with dual-model KSamplerAdvanced workflow.

Submits a single I2V clip to ComfyUI using the official WAN 2.2 14B I2V
architecture (high-noise + low-noise models with KSamplerAdvanced handoff).

This is a standalone test — does not modify any production code.

Usage:
    python scripts/test_i2v_dual.py [--steps 20] [--image i2v_test_char.png]
"""

import argparse
import json
import time
import requests

SERVER = "http://localhost:8188"

# ─── Official WAN 2.2 14B I2V parameters ─────────────────────────────
I2V_CFG = 3.5
I2V_SHIFT = 8.0
I2V_SAMPLER = "euler"
I2V_SCHEDULER = "simple"
I2V_HIGH_UNET = "wan2.2_i2v_high_noise_14B_Q4_K_S.gguf"
I2V_LOW_UNET = "wan2.2_i2v_low_noise_14B_Q4_K_S.gguf"
TEXT_ENCODER = "umt5-xxl-encoder-Q8_0.gguf"
VAE = "wan2.2_vae.safetensors"
WIDTH, HEIGHT = 832, 480
FPS = 16


def build_i2v_dual_workflow(
    prompt: str,
    image_name: str,
    seed: int,
    frames: int = 49,
    steps: int = 20,
    negative_prompt: str = "",
    clip_prefix: str = "video/i2v_test",
) -> dict:
    """Build the official WAN 2.2 14B I2V workflow with dual-model KSamplerAdvanced.

    Architecture:
        LoadImage → ImageScale → WanImageToVideo (conditioning)
        UnetLoaderGGUF (high-noise) → ModelSamplingSD3 (shift=8) → KSamplerAdvanced #1 (steps 0→mid)
        UnetLoaderGGUF (low-noise) → ModelSamplingSD3 (shift=8) → KSamplerAdvanced #2 (mid→end)
        KSamplerAdvanced #1 latent → KSamplerAdvanced #2 latent → VAEDecode → SaveVideo
    """
    mid_step = steps // 2  # Official split: 50% high-noise, 50% low-noise

    wf = {
        # ── Models ──
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": I2V_HIGH_UNET}},
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": I2V_LOW_UNET}},
        "3": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": TEXT_ENCODER, "type": "wan"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},

        # ── Text encoding ──
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": negative_prompt}},

        # ── Image loading + scaling ──
        "7": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "8": {"class_type": "ImageScale", "inputs": {
            "image": ["7", 0], "upscale_method": "lanczos",
            "width": WIDTH, "height": HEIGHT, "crop": "center",
        }},

        # ── I2V conditioning (VAE-encodes start image into latent concat) ──
        "9": {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "vae": ["4", 0],
            "width": WIDTH, "height": HEIGHT, "length": frames, "batch_size": 1,
            "start_image": ["8", 0],
        }},

        # ── Model shift (both models use the same shift for I2V) ──
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": I2V_SHIFT}},
        "11": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": I2V_SHIFT}},

        # ── KSamplerAdvanced #1: high-noise pass (steps 0 → mid) ──
        "12": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["10", 0],
            "positive": ["9", 0], "negative": ["9", 1], "latent_image": ["9", 2],
            "noise_seed": seed, "steps": steps, "cfg": I2V_CFG,
            "sampler_name": I2V_SAMPLER, "scheduler": I2V_SCHEDULER,
            "start_at_step": 0, "end_at_step": mid_step,
            "add_noise": "enable", "return_with_leftover_noise": "enable",
        }},

        # ── KSamplerAdvanced #2: low-noise pass (mid → end) ──
        "13": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["11", 0],
            "positive": ["9", 0], "negative": ["9", 1], "latent_image": ["12", 0],
            "noise_seed": seed, "steps": steps, "cfg": I2V_CFG,
            "sampler_name": I2V_SAMPLER, "scheduler": I2V_SCHEDULER,
            "start_at_step": mid_step, "end_at_step": 10000,
            "add_noise": "disable", "return_with_leftover_noise": "disable",
        }},

        # ── Decode + save ──
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}},
        "15": {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "fps": float(FPS)}},
        "16": {"class_type": "SaveVideo", "inputs": {
            "video": ["15", 0], "filename_prefix": clip_prefix,
            "format": "mp4", "codec": "h264",
        }},
    }
    return wf


def queue_prompt(workflow: dict) -> str:
    """Submit workflow to ComfyUI and return the prompt_id."""
    payload = {"prompt": workflow}
    r = requests.post(f"{SERVER}/prompt", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()["prompt_id"]


def poll_until_done(prompt_id: str, timeout: int = 1800) -> bool:
    """Poll ComfyUI until the prompt completes or times out."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{SERVER}/history/{prompt_id}", timeout=5)
            if r.ok:
                data = r.json()
                if prompt_id in data:
                    status = data[prompt_id].get("status", {})
                    if status.get("completed", False) or status.get("status_str") == "success":
                        return True
                    if status.get("status_str") == "error":
                        print(f"  ERROR: {json.dumps(status, indent=2)}")
                        return False
        except requests.RequestException:
            pass
        time.sleep(3)
    print("  TIMEOUT")
    return False


def main():
    parser = argparse.ArgumentParser(description="Test WAN 2.2 dual-model I2V")
    parser.add_argument("--image", default="i2v_test_char.png", help="Image filename in ComfyUI/input/")
    parser.add_argument("--prompt", default=(
        "Close-up shot, a young person standing in a sunlit olive grove, "
        "gentle breeze rustling leaves, warm golden hour lighting, "
        "cinematic film grain, shallow depth of field"
    ))
    parser.add_argument("--negative", default=(
        "blurry, static, frozen, distorted face, extra limbs, watermark, "
        "text, logo, low quality, jpeg artifacts"
    ))
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--frames", type=int, default=49)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"=== WAN 2.2 I2V Dual-Model Test ===")
    print(f"  Image: {args.image}")
    print(f"  Steps: {args.steps} (high-noise: 0→{args.steps//2}, low-noise: {args.steps//2}→{args.steps})")
    print(f"  Frames: {args.frames}")
    print(f"  CFG: {I2V_CFG}, Shift: {I2V_SHIFT}, Sampler: {I2V_SAMPLER}")
    print(f"  Models: {I2V_HIGH_UNET} + {I2V_LOW_UNET}")
    print()

    wf = build_i2v_dual_workflow(
        prompt=args.prompt,
        image_name=args.image,
        seed=args.seed,
        frames=args.frames,
        steps=args.steps,
        negative_prompt=args.negative,
        clip_prefix="video/i2v_dual_test",
    )

    print("Submitting to ComfyUI...")
    try:
        prompt_id = queue_prompt(wf)
    except requests.ConnectionError:
        print(f"ERROR: ComfyUI not running at {SERVER}")
        return
    except requests.HTTPError as e:
        print(f"ERROR: ComfyUI rejected workflow: {e}")
        print(f"Response: {e.response.text[:500]}")
        return

    print(f"  prompt_id: {prompt_id}")
    print(f"  Polling for completion...")

    success = poll_until_done(prompt_id)
    if success:
        print(f"\n  SUCCESS! Check ComfyUI/output/video/ for i2v_dual_test_*.mp4")
    else:
        print(f"\n  FAILED — check ComfyUI logs for errors")


if __name__ == "__main__":
    main()
