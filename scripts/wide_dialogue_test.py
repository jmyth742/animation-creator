#!/usr/bin/env python3
"""
Can a dialogue shot authored as a WIDE actually be delivered as a wide?

Six of eight wide-authored dialogue shots rendered as head-and-shoulders
close-ups. Every one was seeded from a staged full-body plate and every prompt
said "wide"; the speech-to-video checkpoint is a talking-head model and pulls
to the face regardless. So the shot variety in every dialogue scene is fiction,
and an episode that reads as "talking heads with scenery" reads that way for a
reason that no amount of prompting will fix.

The obvious alternative is what an animator would do anyway: render the wide
SILENT with image-to-video, and lay the voice over it. Nobody needs lip sync on
a mouth six pixels across.

The catch is length. I2V caps at 97 frames (6.06s) where S2V chains to three
chunks, and six of the eleven lines run longer than that -- ep10_s02 and
ep10_s05 are 7.99s. So the silent wide has to be extended, and hold_tail()
already does that: freeze the last frame, push slowly, dissolve in. On a
landscape that is an ordinary device. On a close-up it would look broken.

Renders one shot both ways and compares what actually arrives:

    A  current    S2V, lip synced          (what ships today)
    B  proposed   I2V silent + hold_tail   (wide, voice laid over)

Judged on: does B deliver a WIDE. Scored by CLIP against three framing
descriptions -- the whole point is framing, and identity cannot see framing.

    wide_dialogue_test.py <series> --scene ep07_s01
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

OUT = Path("/workspace/review/wide_dialogue")
SEED = 5150


# Framing options for CLIP. The first version of this measured "skin-toned
# pixels" by an RGB rule and reported ep12_s03 -- a small figure on a ledge --
# as 0.989, a close-up, because golden grass and a sunset sea are skin-toned by
# any loose rule. It was measuring warm terrain. This is the same mechanism
# verify_render uses for style, including the x100 scaling without which the
# softmax cannot discriminate.
_FRAMING_OPTIONS = [
    "an extreme close-up of a person's face filling the frame",
    "a medium shot of a person from the waist up",
    "a wide landscape shot with a small distant figure in it",
]


def framing(clip: str) -> tuple[float, str]:
    """
    Probability the shot is a WIDE, plus the winning label.

    Judged by CLIP against three framing descriptions rather than by pixel
    statistics, because the thing being asked is semantic: is the person small
    in a landscape, or are they the frame.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                        "fps=1,scale=384:-1", f"{td}/f_%03d.png"], check=True)
        fr = sorted(Path(td).glob("f_*.png"))[:6]
        if not fr:
            return 0.0, "?"
        imgs = [Image.open(f).convert("RGB").copy() for f in fr]
        fv = vr._embed_images(imgs)
        tv = vr._embed_texts(_FRAMING_OPTIONS)
        probs = ((fv @ tv.T).mean(dim=0) * 100).softmax(dim=-1)
    i = int(probs.argmax())
    return float(probs[2]), ["close-up", "medium", "wide"][i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--scene", default="ep07_s01")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    res = sr.get_resolution_config("480p", "wan")
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)

    vo = (Path("output") / a.series / f"ep{ep_num:02d}" / "audio"
          / f"{a.scene}.mp3")
    spoken = sr._get_video_duration(str(vo)) if vo.exists() else 0.0
    print(f"  {a.scene}: line is {spoken:.2f}s\n"
          f"  authored: {scene.get('visual','')[:72]}\n", flush=True)

    rows = []

    # ── A: what ships today ────────────────────────────────────────────
    cur = sr.find_latest_clip(a.scene)
    if cur:
        rows.append(("A_current_s2v", cur))
        print(f"  A current (S2V)   {sr._get_video_duration(cur):.2f}s  "
              f"{Path(cur).name}", flush=True)

    # ── B: silent I2V wide, held to cover the line ─────────────────────
    prefix = f"wd_{a.scene}_i2v"
    clip = sr.find_latest_clip(prefix)
    if not clip:
        wf = sr.build_video_workflow(
            "wan", "i2v", prompt, SEED, prefix, sr.MAX_FRAMES, res,
            negative_prompt=neg, steps=8, image_name=seed_img)
        print(f"  B rendering silent I2V at {sr.MAX_FRAMES} frames "
              f"({sr.MAX_FRAMES/16:.2f}s) ...", flush=True)
        try:
            pid = sr.queue_prompt(wf)
            if not sr.poll_until_done(pid, max_wait=1800):
                print("    no output"); return 1
        except Exception as e:                                 # noqa: BLE001
            print(f"    {type(e).__name__}: {e}"); return 1
        clip = sr.find_latest_clip(prefix)
    if not clip:
        print("  B produced nothing"); return 1

    held = str(OUT / f"{a.scene}_B_held.mp4")
    if spoken > sr.MAX_FRAMES / 16:
        sr.hold_tail(clip, spoken, held)
        print(f"  B held {sr.MAX_FRAMES/16:.2f}s -> {spoken:.2f}s to cover "
              f"the line", flush=True)
    else:
        subprocess.run(["cp", clip, held], check=True)
    rows.append(("B_i2v_wide_held", held))

    # ── compare ────────────────────────────────────────────────────────
    print(f"\n  {'variant':18} {'secs':>6} {'p(wide)':>11} {'reads as':>10} {'identity':>9}")
    anchor = None
    who = (scene.get("dialogue") or [{}])[0].get("character")
    ref = sr._find_ref(sr.series_path(a.series) / "reference_images", who, "char")
    if ref:
        anchor = vr._embed_images([Image.open(ref).convert("RGB")])
    out = []
    for name, c in rows:
        d = sr._get_video_duration(c)
        wide_p, label = framing(c)
        ident = ""
        if anchor is not None:
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                p = f"{td}/x.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                f"{d*0.4:.2f}", "-i", c, "-frames:v", "1", p],
                               check=True)
                with Image.open(p) as im:
                    v = vr._embed_images([im.convert("RGB").copy()])
            ident = f"{float((v @ anchor.T)[0][0]):.3f}"
        print(f"  {name:18} {d:6.2f} {wide_p:11.3f} {label:>10} {ident:>9}",
              flush=True)
        out.append({"variant": name, "clip": c, "seconds": d,
                    "p_wide": wide_p, "reads_as": label, "identity": ident})
        subprocess.run(["cp", c, str(OUT / f"{name}.mp4")])

    (OUT / f"{a.scene}.json").write_text(json.dumps(out, indent=2))
    print(f"\n  p(wide) is CLIP's probability the shot reads as a landscape "
          f"with a small\n  figure rather than a face. clips in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
