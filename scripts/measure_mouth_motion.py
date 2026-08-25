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


# The face crop is a proxy, and a proxy needs a control. tir_na_nog is full of
# moving waterfalls, so on a wide shot the "face" region is mostly water and
# the ratio reports motion that has nothing to do with a mouth. Measuring a
# background strip the face never occupies gives a baseline: if silence/speech
# rises by the same factor in BOTH, the scene simply moves more in the tail
# and the mouth is not implicated.
def _frames(clip: str, start: float, dur: float, fps: int = 8,
            region: str = "face") -> list:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}",
                        "-t", f"{dur:.3f}", "-i", clip, "-vf", f"fps={fps}",
                        f"{td}/f_%03d.png"], check=True)
        out = []
        for f in sorted(Path(td).glob("f_*.png")):
            with Image.open(f) as im:
                a = np.asarray(im.convert("L"), dtype=np.float32)
            h, w = a.shape
            if region == "face":
                # Middle horizontally, upper-middle vertically. Deliberately
                # generous -- a motion proxy, not a landmark detector, and cel
                # faces defeat landmark detectors.
                out.append(a[int(h * 0.15):int(h * 0.75), int(w * 0.25):int(w * 0.75)])
            else:
                # Outer thirds: background the speaker's head does not occupy.
                out.append(np.hstack([a[:, :int(w * 0.15)], a[:, int(w * 0.85):]]))
        return out


def motion(clip: str, start: float, dur: float, region: str = "face") -> float:
    fr = _frames(clip, start, dur, region=region)
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
    sp_win = min(2.5, a.speech - 0.9)
    si_win = min(2.5, tail - 0.35)
    spoken = motion(a.clip, 0.6, sp_win)
    silent = motion(a.clip, a.speech + 0.25, si_win)
    bg_sp = motion(a.clip, 0.6, sp_win, region="bg")
    bg_si = motion(a.clip, a.speech + 0.25, si_win, region="bg")
    ratio = silent / spoken if spoken > 0 else 0.0
    bg_ratio = bg_si / bg_sp if bg_sp > 0 else 1.0
    # What the mouth did, net of what the whole scene did -- but a ratio of
    # ratios blows up when the denominator is small. On a calm-sea shot the
    # background barely moves at all (bg 0.10), and dividing by that turned a
    # perfectly good face ratio of 0.30 into "3.05, MOUTH STILL MOVING". The
    # control is only meaningful when the background actually moves.
    CONTROL_MIN, CONTROL_MAX = 0.5, 2.5
    controlled = CONTROL_MIN <= bg_ratio <= CONTROL_MAX
    adj = ratio / bg_ratio if controlled else ratio
    verdict = ("mouth clearly stops" if adj < 0.55 else
               "mouth quietens" if adj < 0.8 else
               "MOUTH STILL MOVING")
    tag = "adjusted" if controlled else "face only"
    note = "" if controlled else "  (bg too still/busy to control with)"
    print(f"  {Path(a.clip).name:30} face {ratio:5.2f}  bg {bg_ratio:5.2f}"
          f"  {tag} {adj:5.2f}   {verdict}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
