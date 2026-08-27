#!/usr/bin/env python3
"""
Match shots to each other within a location.

Every shot is an independent diffusion sample, so its exposure and colour
balance are its own. Measured across the finished film, shots in the SAME
location and the same light drift by:

    valley   luminance spread 19.5   R/B balance spread 63.0
    cliff    luminance spread 26.7   R/B balance spread 55.9
    ruin     luminance spread 20.0   R/B balance spread 11.4

In a film shot on a real set those numbers are a few units. This is the
clearest remaining signal that the shots were generated separately rather than
photographed in one place, and unlike identity or style it is entirely a
finishing problem: nothing needs re-rendering.

Each shot is pulled toward the MEDIAN of its location -- median rather than
mean so one blown-out shot does not drag the whole scene. Corrections are
capped: the point is to remove drift, not to flatten every shot into the same
picture, and a shot that genuinely differs (a close-up lit from the west) should
stay different.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

MAX_GAIN = 0.18          # +/- 18% luminance; beyond that something is wrong
MAX_TINT = 0.10          # per-channel


def sample(clip: str, n: int = 3) -> tuple[np.ndarray, float]:
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", clip], capture_output=True, text=True).stdout.strip() or 1)
    vals = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = dur * (0.2 + 0.3 * i)
            p = f"{td}/f{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                            "-i", clip, "-frames:v", "1", p], check=True)
            vals.append(np.asarray(Image.open(p).convert("RGB"),
                                   dtype=np.float32).mean(axis=(0, 1)))
    rgb = np.mean(vals, axis=0)
    return rgb, float(rgb.mean())


def match_filter(rgb: np.ndarray, lum: float,
                 target_rgb: np.ndarray, target_lum: float) -> str | None:
    """eq + colorbalance that pulls this shot toward the location's median."""
    if lum <= 1:
        return None
    gain = float(np.clip(target_lum / lum, 1 - MAX_GAIN, 1 + MAX_GAIN))
    # Per-channel tint, expressed relative to the luminance-corrected shot.
    corrected = rgb * gain
    tint = np.clip((target_rgb - corrected) / 255.0, -MAX_TINT, MAX_TINT)
    parts = []
    if abs(gain - 1.0) > 0.005:
        parts.append(f"eq=brightness={(gain - 1.0) * 0.35:.4f}:gamma={gain:.4f}")
    if np.abs(tint).max() > 0.004:
        parts.append(f"colorbalance=rm={tint[0]:.4f}:gm={tint[1]:.4f}:"
                     f"bm={tint[2]:.4f}")
    return ",".join(parts) if parts else None


def apply_match(clip: str, filt: str, out: str) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip,
                    "-vf", filt + ",format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-an", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    stats = [sample(c) for c in a.clips]
    med_rgb = np.median(np.array([s[0] for s in stats]), axis=0)
    med_lum = float(np.median([s[1] for s in stats]))
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    print(f"  median luminance {med_lum:.1f}, rgb {med_rgb.round(1)}")
    for c, (rgb, lum) in zip(a.clips, stats):
        f = match_filter(rgb, lum, med_rgb, med_lum)
        dst = out / Path(c).name
        if f:
            apply_match(c, f, str(dst))
            print(f"  {Path(c).name:28} lum {lum:5.1f} -> matched")
        else:
            subprocess.run(["cp", c, str(dst)])
            print(f"  {Path(c).name:28} lum {lum:5.1f} -- already close")
    return 0


if __name__ == "__main__":
    sys.exit(main())
