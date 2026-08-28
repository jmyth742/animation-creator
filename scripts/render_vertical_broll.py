#!/usr/bin/env python3
"""
Vertical b-roll for short-form, rendered rather than cropped.

Cel-shaded wides ARE their composition: Oisin small against a headland becomes
a torso if you crop it to 9:16. 480x832 is a native WAN generation size, so the
honest fix is to render portrait in the first place.

Four shots, chosen because they carry the short-form stories: a character who
moves (the negative-prompt short needs a before and an after), a close-up that
reads at phone size, and the ruin.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

SHOTS = [
    ("walk_vertical", "farewell_cliff", "master", "oisin", "walking_away",
     "He walks steadily away across the headland, one foot after the other, "
     "cloak swinging with each stride. Continuous walking."),
    ("stand_vertical", "tir_na_nog", "master", "oisin", "full_body",
     "He stands up slowly from the grass and turns to look down the valley."),
    ("close_vertical", "farewell_cliff", "closer", "niamh", "close",
     "She looks steadily into the middle distance, wind moving her hair."),
    ("ruin_vertical", "ruined_ireland", "master", "oisin", "three_quarter",
     "He walks forward between the fallen stones, looking up at the ruin."),
]


def main():
    series = sys.argv[1] if len(sys.argv) > 1 else "tir-na-nog-legend"
    sr.set_current_series(series)
    bible = sr.load_json(sr.series_path(series) / "bible.json")
    res = dict(sr.get_resolution_config("480p", "wan"))
    # Portrait. Both are native sizes; swapping them is all that is required.
    res["width"], res["height"] = 480, 832
    out = Path("/workspace/review/vertical")
    out.mkdir(parents=True, exist_ok=True)
    print(f"  rendering at {res['width']}x{res['height']} (portrait, native)\n")

    for name, loc, setup, who, framing, action in SHOTS:
        plate = sr.series_path(series) / "sets" / loc / f"{setup}__{who}_{framing}.png"
        if not plate.exists():
            print(f"  {name}: no plate {plate.name}"); continue
        ch = bible["characters"][who]
        # Per the audit: with a conditioning image, drop static scene
        # description and keep the DYNAMIC content. No background, no palette.
        prompt = (f"Cel-shaded 2D animation, clean linework, flat colour. "
                  f"{ch.get('trigger_word','')}. {ch['visual'].split('.')[0]}. "
                  f"{action}")
        scene = {"id": name, "visual": action, "characters": [who]}
        neg = sr.build_negative_prompt(scene)
        clip = sr.find_latest_clip(name)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "i2v", prompt, 7700, name, 81, res,
                negative_prompt=neg, steps=8,
                image_name=sr.copy_to_input(str(plate)),
                loras=[(ch["lora_path"], ch.get("lora_strength", 0.9))]
                      + list(sr.LIGHTNING["i2v"]) if ch.get("lora_path")
                      else list(sr.LIGHTNING["i2v"]))
            sr.apply_lightning(wf, steps=8)
            print(f"  {name} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(name)
        if clip:
            subprocess.run(["cp", clip, str(out / f"{name}.mp4")])
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", clip],
                capture_output=True, text=True).stdout.strip()
            print(f"    {r}  -> {out / (name + '.mp4')}")
    print(f"\n  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
