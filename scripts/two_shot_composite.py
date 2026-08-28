#!/usr/bin/env python3
"""
Two characters in one frame, seeded from a plate that already contains both.

The first two-shot test seeded from an EMPTY location plate and asked the model
to invent two people. It scored 0.62 and 0.68 and I called the question closed.
That test was wrong in three ways:

  1. No face reference for either character. Every good shot in this project
     seeds from a plate that already contains the right face; this one gave the
     model nothing and then blamed it for guessing.
  2. A 0.75 threshold built for close-ups, applied to a wide two-shot. Each face
     occupies a fraction of the frame, so CLIP similarity against a portrait
     anchor falls for reasons that have nothing to do with likeness.
  3. Compositing two staged plates into one seed was never tried, and it is the
     obvious thing to do -- the staged plates already exist, one per character
     per framing, in the same location and the same light.

So: composite them side by side, use that as the I2V seed, and score each half
of the frame against its own anchor rather than scoring the whole frame twice.
That last part matters -- a whole-frame score cannot tell "both present" from
"one person twice".
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402


def composite(left: Path, right: Path, out: Path, w: int, h: int) -> Path:
    """Two staged plates into one frame: left half, right half."""
    canvas = Image.new("RGB", (w, h))
    for i, src in enumerate((left, right)):
        with Image.open(src) as im:
            im = im.convert("RGB")
            # take the middle of each plate so the character is not cropped out
            cw = int(im.width * 0.55)
            box = ((im.width - cw) // 2, 0, (im.width + cw) // 2, im.height)
            half = im.crop(box).resize((w // 2, h), Image.LANCZOS)
        canvas.paste(half, (i * (w // 2), 0))
    canvas.save(out)
    return out


def half_scores(frame: Image.Image, anchors: dict) -> dict:
    """Score each HALF against its own anchor. A whole-frame score cannot tell
    'both are here' from 'one of them is here twice'."""
    w, h = frame.size
    out = {}
    for i, (who, vec) in enumerate(anchors.items()):
        half = frame.crop((i * w // 2, 0, (i + 1) * w // 2, h))
        out[who] = float((vr._embed_images([half]) @ vec.T)[0][0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--location", default="tir_na_nog")
    ap.add_argument("--setup", default="master")
    ap.add_argument("--left", default="oisin")
    ap.add_argument("--right", default="niamh")
    ap.add_argument("--framing", default="full_body")
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    sets = sr.series_path(a.series) / "sets" / a.location
    lp = sets / f"{a.setup}__{a.left}_{a.framing}.png"
    rp = sets / f"{a.setup}__{a.right}_{a.framing}.png"
    for p in (lp, rp):
        if not p.exists():
            print(f"  missing staged plate: {p.name}"); return 1

    res = sr.get_resolution_config("480p", "wan")
    W, H = res["width"], res["height"]
    out = Path("/workspace/review/two_shot_composite")
    out.mkdir(parents=True, exist_ok=True)
    seed_png = composite(lp, rp, out / "seed_composite.png", W, H)
    print(f"  seed built from {lp.name} + {rp.name}")
    seed = sr.copy_to_input(str(seed_png))

    style = bible["series"]["style"].split(",")[0].strip()
    d1 = bible["characters"][a.left]["visual"].split(".")[0]
    d2 = bible["characters"][a.right]["visual"].split(".")[0]
    prompt = (f"{style}, clean confident linework, flat blocks of colour. "
              f"Two people standing together in one shot, facing each other, "
              f"several feet apart. On the left, {d1}. On the right, {d2}. "
              f"Both fully in frame. Static camera.")
    neg = (sr.build_negative_prompt({"id": "x", "visual": "wide two-shot",
                                     "characters": [a.left, a.right]})
           + ", merged faces, duplicate person, three people, crowd")

    anchors = {c: vr._embed_images([Image.open(
        sr._find_ref(sr.series_path(a.series) / "reference_images", c, "char")
    ).convert("RGB")]) for c in (a.left, a.right)}

    # score the SEED first -- if the composite itself does not hold both, the
    # render never will, and that is a cheaper thing to find out.
    with Image.open(seed_png) as im:
        s0 = half_scores(im.convert("RGB").copy(), anchors)
    print(f"  the composite seed itself: "
          + "  ".join(f"{k} {v:.3f}" for k, v in s0.items()))

    prefix = f"twoc_{a.location}_{a.setup}"
    clip = sr.find_latest_clip(prefix)
    if not clip:
        wf = sr.build_video_workflow("wan", "i2v", prompt, 6600, prefix, 33, res,
                                     negative_prompt=neg, steps=8,
                                     image_name=seed, loras=sr.LIGHTNING["i2v"])
        sr.apply_lightning(wf, steps=8)
        print("  rendering ...", flush=True)
        try:
            pid = sr.queue_prompt(wf)
            if not sr.poll_until_done(pid, max_wait=1200):
                print("  no output"); return 1
        except Exception as e:                                 # noqa: BLE001
            print(f"  {type(e).__name__}: {e}"); return 1
        clip = sr.find_latest_clip(prefix)
    png = out / "rendered.png"
    sr.extract_last_frame(clip, str(png))
    with Image.open(png) as im:
        s1 = half_scores(im.convert("RGB").copy(), anchors)
    subprocess.run(["cp", clip, str(out / "two_shot.mp4")])

    print(f"\n  {'':10} {'seed':>8} {'rendered':>10}")
    for c in (a.left, a.right):
        print(f"  {c:10} {s0[c]:8.3f} {s1[c]:10.3f}")
    lo = min(s1.values())
    print(f"\n  both halves above 0.75: {'YES' if lo >= 0.75 else 'no'}  "
          f"(worst {lo:.3f})")
    print(f"  for scale, a WIDE single-character shot scores about 0.90,")
    print(f"  and each face here is half the size it would be in one.")
    (out / "result.json").write_text(json.dumps(
        {"seed": s0, "rendered": s1, "usable": lo >= 0.75}, indent=2))
    print(f"\n  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
