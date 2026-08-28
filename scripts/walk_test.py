#!/usr/bin/env python3
"""
Get a character to walk across a scene.

Identity is solid and movement is not. But every movement test so far ran
through S2V, which is the wrong tool for this: it is anchored to a talking head
and driven by audio, so it spends its capacity on a mouth. A walk across frame
has no dialogue in it, which means I2V -- a different model family that follows
its seed image differently AND can use the character LoRAs that S2V cannot.

Four things vary, one at a time where possible:

    seed plate    walking_away (already framed for it) vs full_body
    prompt        how explicitly the walk is described
    lightning     8 distilled steps vs 20 full ones -- distillation buys speed
                  by taking fewer, larger denoising jumps, and it is worth
                  knowing whether that costs motion
    length        up to 97 frames, 6.06s. I2V cannot chain: WanSoundImageTo-
                  VideoExtend is an S2V node, so this is a hard ceiling.

Scored on whole-frame motion (did anything happen), on how much the frame
CHANGES end to end (did he actually cross, or just sway), and on identity.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

STYLE_HEAD = ("Cel-shaded 2D animation, clean confident linework, flat blocks "
              "of colour with simple shading, painted background art.")

VARIANTS = [
    # name, plate framing, prompt tail, lightning, steps
    ("away_light",  "walking_away",
     "He walks steadily away from camera across the headland, one foot after "
     "the other, his cloak swinging with each stride. Continuous walking. "
     "Static camera.", True, 8),
    ("away_full",   "walking_away",
     "He walks steadily away from camera across the headland, one foot after "
     "the other, his cloak swinging with each stride. Continuous walking. "
     "Static camera.", False, 20),
    ("cross_light", "full_body",
     "He walks from the left of the frame to the right, crossing the headland "
     "with long strides, cloak trailing. He does not stop. Static camera.",
     True, 8),
    ("cross_full",  "full_body",
     "He walks from the left of the frame to the right, crossing the headland "
     "with long strides, cloak trailing. He does not stop. Static camera.",
     False, 20),
]


def frames(clip: str, fps: int = 6):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                        f"fps={fps}", f"{td}/f_%03d.png"], check=True)
        return [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
                for f in sorted(Path(td).glob("f_*.png"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="tir-na-nog-legend")
    ap.add_argument("--location", default="farewell_cliff")
    ap.add_argument("--setup", default="master")
    ap.add_argument("--who", default="oisin")
    ap.add_argument("--frames", type=int, default=97)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ch = bible["characters"][a.who]
    desc = ch["visual"].split(".")[0]
    trig = ch.get("trigger_word") or ""
    lora = ch.get("lora_path")
    res = sr.get_resolution_config("480p", "wan")
    sets = sr.series_path(a.series) / "sets" / a.location
    anchor = vr._embed_images([Image.open(sr._find_ref(
        sr.series_path(a.series) / "reference_images", a.who, "char")).convert("RGB")])

    out = Path("/workspace/review/walk"); out.mkdir(parents=True, exist_ok=True)
    print(f"  {a.frames} frames = {a.frames/16:.2f}s   location {a.location}\n")
    rows = []
    for name, framing, tail, light, steps in VARIANTS:
        plate = sets / f"{a.setup}__{a.who}_{framing}.png"
        if not plate.exists():
            print(f"  {name}: no plate {plate.name}"); continue
        seed = sr.copy_to_input(str(plate))
        # I2V can use the character LoRA -- S2V cannot, and that is most of why
        # dialogue shots run untrained.
        loras = list(sr.LIGHTNING["i2v"]) if light else []
        if lora:
            loras = [(lora, ch.get("lora_strength", 0.9))] + loras
        prompt = f"{STYLE_HEAD} {trig + '. ' if trig else ''}{desc}. {tail}"
        neg = ("low quality, blurry, distorted, deformed, warped anatomy, "
               "photorealistic, live action, static, frozen, still image, "
               "no motion, stiff, motionless")
        prefix = f"walk_{name}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "i2v", prompt, 7200, prefix, a.frames, res,
                negative_prompt=neg, steps=steps, image_name=seed,
                loras=loras or None)
            if light:
                sr.apply_lightning(wf, steps=steps)
            print(f"  {name} ({framing}, {'lightning ' if light else ''}"
                  f"{steps} steps) ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=2400):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        fr = frames(clip)
        mo = float(np.mean([np.abs(fr[i+1]-fr[i]).mean()
                            for i in range(len(fr)-1)])) if len(fr) > 1 else 0
        travel = float(np.abs(fr[-1] - fr[0]).mean()) if len(fr) > 1 else 0
        with tempfile.TemporaryDirectory() as td:
            p = f"{td}/m.png"
            d = sr._get_video_duration(clip)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d*0.5:.2f}",
                            "-i", clip, "-frames:v", "1", p], check=True)
            with Image.open(p) as im:
                idn = float((vr._embed_images([im.convert("RGB").copy()])
                             @ anchor.T)[0][0])
        subprocess.run(["cp", clip, str(out / f"{name}.mp4")])
        rows.append({"name": name, "framing": framing, "lightning": light,
                     "steps": steps, "motion": mo, "travel": travel,
                     "identity": idn})
        print(f"    motion {mo:6.3f}   travel {travel:6.2f}   identity {idn:.3f}",
              flush=True)

    if not rows:
        print("\n  nothing rendered"); return 1
    print(f"\n  {'variant':13} {'plate':14} {'steps':>6} {'motion':>7} "
          f"{'travel':>7} {'identity':>9}")
    for r in rows:
        print(f"  {r['name']:13} {r['framing']:14} "
              f"{('L' + str(r['steps'])) if r['lightning'] else str(r['steps']):>6} "
              f"{r['motion']:7.3f} {r['travel']:7.2f} {r['identity']:9.3f}")
    best = max(rows, key=lambda r: r["travel"])
    print(f"\n  most actual travel: {best['name']}  "
          f"(travel {best['travel']:.2f}, identity {best['identity']:.3f})")
    print(f"  travel is first-frame vs last-frame difference -- a character who")
    print(f"  sways in place scores low on it however busy the motion looks.")
    (out / "results.json").write_text(json.dumps(rows, indent=2))
    print(f"  clips in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
