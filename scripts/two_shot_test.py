#!/usr/bin/env python3
"""
Can this pipeline put both characters in one frame?

Across six finished pieces there are 55 shots and NOT ONE contains two
characters. Every conversation is two people who are never seen together --
which is why the cutting still reads as alternating monologues however good
each shot is. Real animated series use two-shots constantly: it is how an
audience is told these people share a space.

The pipeline has never tried. Staged plates are built one character at a time,
and classify_scene_type routes any dialogue scene to S2V, which drives ONE
mouth. So there are two separate questions:

  1. Can a PLATE hold both characters recognisably? (I2V from a setup plate,
     both prompted.) If identities merge or a third person appears, stop here.
  2. If yes, a two-shot is usable for reaction and listening coverage even if
     only one of them can be lip-synced -- which is exactly how a two-shot is
     used in practice: one speaks, the other reacts.

Scored per attempt: both identities against their anchors, and a face count
proxy. A merged pair scores high on one and low on the other.

    two_shot_test.py <series> --location tir_na_nog --setup master
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

FRAMES = 33            # short: this is a plate, not a shot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--location", required=True)
    ap.add_argument("--setup", default="master")
    ap.add_argument("--chars", default="oisin,niamh")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    c1, c2 = a.chars.split(",")
    plate = sr.series_path(a.series) / "sets" / a.location / f"{a.setup}.png"
    if not plate.exists():
        print(f"  no setup plate at {plate}"); return 1
    seed = sr.copy_to_input(str(plate))
    res = sr.get_resolution_config("480p", "wan")

    style = bible["series"]["style"].split(",")[0].strip()
    d1 = bible["characters"][c1]["visual"].split(".")[0]
    d2 = bible["characters"][c2]["visual"].split(".")[0]
    variants = {
        "side_by_side":
            f"{style}, clean confident linework, flat blocks of colour. "
            f"Two people standing together in the same shot, several feet "
            f"apart, both fully visible. On the left, {d1}. On the right, "
            f"{d2}. Wide two-shot, both from head to foot, facing each other. "
            f"Static camera.",
        "over_shoulder":
            f"{style}, clean confident linework, flat blocks of colour. "
            f"Over-the-shoulder two-shot. In the foreground on the left, the "
            f"back and shoulder of {d1}. Facing camera beyond him, {d2}, from "
            f"the waist up. Static camera.",
    }
    neg = (sr.build_negative_prompt({"id": "x", "visual": "wide two-shot",
                                    "characters": [c1, c2]})
           + ", merged faces, duplicate person, three people, crowd, "
             "conjoined figures, extra limbs")

    anchors = {c: vr._embed_images([Image.open(
        sr._find_ref(sr.series_path(a.series) / "reference_images", c, "char")
    ).convert("RGB")]) for c in (c1, c2)}

    out = Path("/workspace/review/two_shot"); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, prompt in variants.items():
        prefix = f"twoshot_{a.location}_{a.setup}_{name}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "i2v", prompt, 6100, prefix, FRAMES, res,
                negative_prompt=neg, steps=8, image_name=seed,
                loras=sr.LIGHTNING["i2v"])
            sr.apply_lightning(wf, steps=8)
            print(f"  {name} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1200):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        # Score the final frame -- that is what would become the plate.
        png = out / f"{name}.png"
        sr.extract_last_frame(clip, str(png))
        with Image.open(png) as im:
            v = vr._embed_images([im.convert("RGB").copy()])
        s1 = float((v @ anchors[c1].T)[0][0])
        s2 = float((v @ anchors[c2].T)[0][0])
        rows.append((name, s1, s2, str(png)))

    print(f"\n  two-shot plates on {a.location}/{a.setup}")
    print(f"  {'variant':16} {c1:>9} {c2:>9}   verdict")
    for name, s1, s2, _ in rows:
        lo, hi = min(s1, s2), max(s1, s2)
        v = ("both present" if lo >= 0.75 else
             "one dominates — likely merged" if hi >= 0.80 else
             "neither recognisable")
        print(f"  {name:16} {s1:9.3f} {s2:9.3f}   {v}")
    ok = [r for r in rows if min(r[1], r[2]) >= 0.75]
    verdict = {"usable": bool(ok),
               "best": ok[0][0] if ok else None,
               "rows": [{"variant": r[0], c1: r[1], c2: r[2]} for r in rows]}
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2))
    print(f"\n  {'TWO-SHOTS ARE USABLE — ' + verdict['best'] if ok else 'no variant held both characters'}")
    print(f"  frames + verdict in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
