#!/usr/bin/env python3
"""
Which upscaler suits CEL-SHADED art, measured rather than eyeballed?

Generic "is it sharper" is the wrong question. Cel art is two things at once:
hard confident edges, and large areas of perfectly flat colour. A photoreal
upscaler trained on photographs improves the first and destroys the second --
it invents texture inside the flats, which is exactly the waxy look that made
rendering native 720p worse than upscaling 480p.

So two numbers, and a good result needs BOTH:

    edge      Laplacian energy along detected edges. Higher is sharper line.
    flatness  variance inside non-edge regions. LOWER is better -- it means
              the flat colour stayed flat instead of growing texture.

A model that raises edge AND raises flat-variance has not upscaled the art,
it has photographed it.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402


# Every candidate is scored at ONE output size. Comparing Laplacian energy
# between a 832x480 frame and its 3328x1920 upscale is meaningless: the same
# edge is spread over sixteen times the pixels, so the bigger image always
# scores lower and every model looks worse than doing nothing. The real
# question is "at the delivery resolution, is this better than plain lanczos",
# so everything is resampled to TARGET before measuring.
TARGET = (1920, 1080)


def _scores(path: Path) -> tuple[float, float]:
    with Image.open(path) as im:
        im = im.convert("L")
        if im.size != TARGET:
            im = im.resize(TARGET, Image.LANCZOS)
        a = np.asarray(im, dtype=np.float32)
    # Laplacian
    lap = (-4 * a
           + np.roll(a, 1, 0) + np.roll(a, -1, 0)
           + np.roll(a, 1, 1) + np.roll(a, -1, 1))[2:-2, 2:-2]
    mag = np.abs(lap)
    # Edges are the top decile of |laplacian|; flats are the bottom half.
    thr_hi = np.quantile(mag, 0.90)
    thr_lo = np.quantile(mag, 0.50)
    edge = float(mag[mag >= thr_hi].mean())
    # Local variance inside flat regions, at native scale so the comparison is
    # not just "bigger image has more pixels".
    # `<` not `<=` produced an EMPTY mask on a good cel upscale: more than half
    # the frame came back with a Laplacian of exactly zero, so the median was
    # zero and nothing was strictly below it. That reported nan, which reads
    # like a failure when it is in fact the best possible result -- large areas
    # of genuinely flat colour. Inclusive bound, and the degenerate case is
    # perfect flatness, not missing data.
    flat_mask = mag <= thr_lo
    if not flat_mask.any():
        return edge, 0.0
    win = a[2:-2, 2:-2]
    local = np.abs(win - 0.25 * (np.roll(win, 1, 0) + np.roll(win, -1, 0)
                                 + np.roll(win, 1, 1) + np.roll(win, -1, 1)))
    flat = float(local[flat_mask].mean())
    return edge, flat


def upscale_via_comfy(img_name: str, model: str, prefix: str) -> Path | None:
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": img_name}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": model}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "SaveImage",
              "inputs": {"images": ["3", 0], "filename_prefix": prefix}},
    }
    try:
        pid = sr.queue_prompt(wf)
    except Exception as e:                                     # noqa: BLE001
        print(f"    queue failed: {e}")
        return None
    if not sr.poll_until_done(pid, poll_interval=5, max_wait=600):
        return None
    hits = sorted((sr.COMFYUI_DIR / "output").rglob(f"{prefix}*.png"),
                  key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--models", default="RealESRGAN_x4plus_anime_6B.pth,4x-AnimeSharp.pth")
    a = ap.parse_args()

    tmp = Path("/workspace/review/upscale"); tmp.mkdir(parents=True, exist_ok=True)
    dur = sr._get_video_duration(a.clip)
    picks = [dur * f for f in (0.15, 0.5, 0.85)][:a.frames]

    rows = []
    for i, t in enumerate(picks):
        src = tmp / f"src_{i}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                        "-i", a.clip, "-frames:v", "1", str(src)], check=True)
        # Baseline is the honest alternative: plain lanczos to the delivery
        # size, which is what the pipeline does today.
        e0, f0 = _scores(src)
        rows.append(("lanczos to 1080p", i, e0, f0, 1.0, 1.0))
        staged = sr.copy_to_input(str(src))
        for m in a.models.split(","):
            out = upscale_via_comfy(staged, m, f"upcmp_{m.split('.')[0]}_{i}")
            if not out:
                print(f"    {m}: no output")
                continue
            keep = tmp / f"{m.split('.')[0]}_{i}.png"
            keep.write_bytes(out.read_bytes())
            e1, f1 = _scores(keep)
            rows.append((m.split(".")[0], i, e1, f1, e1 / e0, f1 / f0))

    print(f"\n  {'model':28} {'edge':>8} {'flat':>8}   {'edge x':>7} {'flat x':>7}")
    agg = {}
    for name, i, e, f, er, fr in rows:
        agg.setdefault(name, []).append((e, f, er, fr))
    for name, vals in agg.items():
        e = sum(v[0] for v in vals) / len(vals)
        f = sum(v[1] for v in vals) / len(vals)
        er = sum(v[2] for v in vals) / len(vals)
        fr = sum(v[3] for v in vals) / len(vals)
        verdict = ""
        if name != "lanczos to 1080p":
            verdict = ("sharper AND flats held" if er > 1.05 and fr <= 1.15 else
                       "sharper but flats grew texture" if er > 1.05 else
                       "no sharper")
        print(f"  {name:28} {e:8.2f} {f:8.3f}   {er:6.2f}x {fr:6.2f}x   {verdict}")
    print("\n  edge higher = better;  flat LOWER = better (flat colour stayed flat)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
