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
    # "closer" is an Oisin-only setup at this location; Niamh's coverage
    # angle is "reverse". The old name silently skipped the shot -- and the
    # close-up is the one that most needs to read at phone size.
    ("close_vertical", "farewell_cliff", "reverse", "niamh", "close",
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
            raw = out / f"{name}_480x832.mp4"
            subprocess.run(["cp", clip, str(raw)])
            # Shorts are 1080x1920. WAN's portrait native is 480x832, whose
            # aspect (0.5769) is very slightly wider than 9:16 (0.5625), so
            # scaling to 1080 wide gives 1080x1872 and leaves 48px. Pad rather
            # than crop -- 48px of ground costs nothing, and cropping a
            # cel-shaded frame throws away composition for the sake of an
            # aspect ratio nobody will measure.
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(raw),
                 "-vf", ("scale=1080:-2:flags=lanczos,"
                         "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0d0e11,"
                         "format=yuv420p"),
                 "-c:v", "libx264", "-crf", "17",
                 str(out / f"{name}.mp4")], check=True)
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0",
                 str(out / f"{name}.mp4")],
                capture_output=True, text=True).stdout.strip()
            print(f"    rendered 480x832 -> {r}")
    print(f"\n  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
