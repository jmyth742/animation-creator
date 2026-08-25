#!/usr/bin/env python3
"""Compare I2V dual-model vs existing T2V clips for Reemi scenes.

Produces ep02 scenes 4-5 (Reemi character) using the new dual-model I2V
workflow and saves with prefix "i2v_compare_" so you can compare against
the existing T2V-produced clips side by side.

Usage:
    python scripts/test_i2v_comparison.py [--steps 20] [--quality good]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.showrunner as s

SERIES = "palestine-stories"


def main():
    parser = argparse.ArgumentParser(description="Compare I2V vs T2V on Reemi scenes")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--scenes", default="3,4", help="Comma-separated scene indices (0-based)")
    args = parser.parse_args()

    ep = json.load(open(f"series/{SERIES}/episodes/ep02.json"))
    bible = json.load(open(f"series/{SERIES}/bible.json"))
    rc = s.get_resolution_config()
    scene_indices = [int(x) for x in args.scenes.split(",")]

    print(f"=== I2V Dual-Model Comparison Test ===")
    print(f"Series: {SERIES}, Episode: ep02")
    print(f"Steps: {args.steps}")
    print()

    current_image = None

    for idx in scene_indices:
        scene = ep["scenes"][idx]
        sid = scene["id"]
        scene_type = s.classify_scene_type(scene)
        seed_img = s.get_scene_seed_image(scene, SERIES, current_image)
        scene_loras = s.get_scene_loras(scene, bible)
        prompt = s.build_scene_prompt(scene, bible)
        neg = s.build_negative_prompt(scene)
        cl = s.MODEL_CONFIGS["wan"]["clip_lengths"].get(
            scene.get("clip_length", "medium"), s.MODEL_CONFIGS["wan"]["clip_lengths"]["medium"]
        )

        # Resolve LoRAs for dual-model
        if scene_loras:
            s._resolve_wan_dual_loras(scene_loras)

        compare_prefix = f"i2v_compare_{sid}"

        print(f"Scene {sid}:")
        print(f"  Type: {scene_type} → {'I2V' if seed_img else 'T2V'}")
        print(f"  Seed image: {seed_img}")
        print(f"  LoRAs: {scene_loras}")
        print(f"  Frames: {cl['frames']} ({cl['seconds']}s)")
        print(f"  Prompt: {prompt[:100]}...")

        mode = "i2v" if seed_img else "t2v"

        wf = s.build_video_workflow(
            "wan", mode, prompt, 42, compare_prefix, cl["frames"], rc,
            negative_prompt=neg, steps=args.steps,
            loras=scene_loras, image_name=seed_img,
        )

        print(f"  Submitting ({mode} dual-model)...")
        try:
            prompt_id = s.queue_prompt(wf)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        print(f"  prompt_id: {prompt_id}")
        success = s.poll_until_done(prompt_id)

        if success:
            clip = s.find_latest_clip(compare_prefix)
            print(f"  SUCCESS → {clip}")
            if clip:
                frame_path = str(s.COMFYUI_INPUT / f"chain_{compare_prefix}.png")
                if s.extract_last_frame(clip, frame_path):
                    current_image = f"chain_{compare_prefix}.png"
        else:
            print(f"  FAILED")

        print()

    print("=== Done! Compare clips: ===")
    print(f"  New I2V: http://localhost:8000/static/clips/i2v_compare_ep02_s04_*.mp4")
    print(f"  New I2V: http://localhost:8000/static/clips/i2v_compare_ep02_s05_*.mp4")
    print(f"  Existing T2V: in output/palestine-stories/ep02/")


if __name__ == "__main__":
    main()
