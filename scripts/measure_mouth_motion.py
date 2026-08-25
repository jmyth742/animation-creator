#!/usr/bin/env python3
"""
Is the mouth moving when nobody is speaking?

S2V drives the mouth from the audio it is given. When a shot is held longer
than its line, the tail has no audio covering it and the character keeps
mouthing words after the line has ended. That is invisible to every check the
pipeline has: the clip is the right length, the right person, the right style.

Measured here as frame-to-frame change in the face region, compared between a
window DURING speech and a window AFTER it. The ratio is what matters -- a
talking face should move a lot more than a silent one. A ratio near 1.0 means
the mouth never stopped.

    measure_mouth_motion.py <clip> --speech <seconds>
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _frames(clip: str, start: float, dur: float, fps: int = 8) -> list:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}",
                        "-t", f"{dur:.3f}", "-i", clip, "-vf", f"fps={fps}",
                        f"{td}/f_%03d.png"], check=True)
        out = []
        for f in sorted(Path(td).glob("f_*.png")):
            with Image.open(f) as im:
                a = np.asarray(im.convert("L"), dtype=np.float32)
            h, w = a.shape
            # Face/mouth region: the middle horizontally, upper-middle
            # vertically. Deliberately generous -- this is a motion proxy, not
            # a landmark detector, and cel faces defeat landmark detectors.
            out.append(a[int(h * 0.15):int(h * 0.75), int(w * 0.25):int(w * 0.75)])
        return out


def motion(clip: str, start: float, dur: float) -> float:
    fr = _frames(clip, start, dur)
    if len(fr) < 2:
        return 0.0
    return float(np.mean([np.mean(np.abs(fr[i + 1] - fr[i]))
                          for i in range(len(fr) - 1)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--speech", type=float, required=True,
                    help="seconds of actual speech in this clip")
    a = ap.parse_args()
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", a.clip], capture_output=True, text=True).stdout.strip())
    tail = dur - a.speech
    if tail < 0.6:
        print(f"  {Path(a.clip).name}: only {tail:.2f}s of tail, nothing to measure")
        return 0
    # Sample inside the line, and inside the silence, avoiding both edges.
    spoken = motion(a.clip, 0.6, min(2.5, a.speech - 0.9))
    silent = motion(a.clip, a.speech + 0.25, min(2.5, tail - 0.35))
    ratio = silent / spoken if spoken > 0 else 0.0
    verdict = ("mouth clearly stops" if ratio < 0.55 else
               "mouth quietens" if ratio < 0.8 else
               "MOUTH STILL MOVING")
    print(f"  {Path(a.clip).name:34} speech {spoken:6.3f}   silence {silent:6.3f}"
          f"   ratio {ratio:4.2f}   {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
