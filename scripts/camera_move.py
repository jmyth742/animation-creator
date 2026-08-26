#!/usr/bin/env python3
"""
Give every shot a camera.

Every shot in the film is locked off. Each one is well composed and the
characters hold, but 27 static frames in a row reads as a slideshow of moving
portraits rather than as animation. Real cutting breathes: a slow push as
someone decides, a drift across a landscape, a pull back to leave someone
alone in the frame.

WHY THIS COSTS NOTHING
The 1080p pass already upscales each frame to 3328x1920 before resampling down
to 1920x1080. That is 1.73x linear headroom sitting unused. Cropping a MOVING
1920x1080 window out of the 4x frame is therefore a real camera move at full
delivery resolution -- no softening, no black edges, no re-render. The move is
free because the pixels were already paid for.

    push    slow move in    -- decisions, confessions, a line that costs something
    pull    slow move out   -- isolation, endings, someone left alone
    drift   lateral         -- landscapes and establishing shots
    hold    none            -- reserved; a still shot among moving ones now reads
                               as deliberate rather than as the default

The moves are deliberately small (4-7% over a shot). A move you notice is a
move that is too big -- the audience should feel it, not see it.
"""
import argparse
import subprocess
import sys
from pathlib import Path

OUT_W, OUT_H = 1920, 1080

# Which move suits which framing. A close-up pushes in; a wide drifts or pulls.
MOVE_BY_STAGING = {
    "close": "push", "ecu": "push",
    "medium": "push", "three_quarter": "push",
    "over_shoulder": "drift", "low_angle": "push",
    "full_body": "pull", "walking_away": "drift",
}
AMOUNT = {"push": 0.065, "pull": 0.065, "drift": 0.055, "hold": 0.0}


def move_filter(kind: str, n_frames: int, src_w: int, src_h: int) -> str:
    """A crop expression that walks a 1920x1080 window across the source."""
    amt = AMOUNT.get(kind, 0.0)
    if kind == "hold" or amt <= 0 or n_frames <= 1:
        return f"crop={OUT_W}:{OUT_H}:(in_w-{OUT_W})/2:(in_h-{OUT_H})/2"
    # Zoom is expressed as the crop window shrinking (push) or growing (pull).
    # Start and end window widths, clamped to what the source actually has.
    wide = min(src_w, int(OUT_W * (1 + amt)))
    if kind == "push":
        w0, w1 = wide, OUT_W
    elif kind == "pull":
        w0, w1 = OUT_W, wide
    else:                                    # drift: constant size, moves across
        w0 = w1 = OUT_W
    prog = f"(n/{max(1, n_frames - 1)})"
    w = f"({w0}+({w1}-{w0})*{prog})"
    h = f"({w}*{OUT_H}/{OUT_W})"
    if kind == "drift":
        # Travel a little over half the spare width, so the frame never runs out.
        travel = (src_w - OUT_W) * 0.55
        x = f"((in_w-{w})/2 + {travel:.1f}*({prog}-0.5))"
    else:
        x = f"((in_w-{w})/2)"
    y = f"((in_h-{h})/2)"
    return (f"crop=w='{w}':h='{h}':x='{x}':y='{y}',"
            f"scale={OUT_W}:{OUT_H}:flags=lanczos")


def apply_move(src: str, kind: str, out: str) -> str:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames", "-of", "csv=p=0", src],
        capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    try:
        n = int(probe[2])
    except (IndexError, ValueError):
        n = 0
    if n <= 0:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip())
        n = max(1, int(dur * 16))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-vf", move_filter(kind, n, w, h),
                    "-c:v", "libx264", "-crf", "16", "-an", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--kind", default="push", choices=list(AMOUNT))
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    print(f"  {apply_move(a.src, a.kind, a.out)}  [{a.kind}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
