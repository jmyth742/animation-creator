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


def move_filter(kind: str, n_frames: int, src_w: int, src_h: int,
                out_w: int | None = None, out_h: int | None = None,
                fps: int = 16) -> str:
    """A moving window across the source, scaled to the output size.

    Uses zoompan, NOT crop. ffmpeg's crop filter evaluates its `w` and `h`
    expressions ONCE at initialisation -- only `x` and `y` are re-evaluated per
    frame. A push written as a shrinking crop window therefore freezes at
    whatever size frame 0 asked for: measured, `push` came out bit-identical to
    `static` (mean frame delta 2.920 against 2.918), so seventeen of the
    twenty-seven shots in the first graded cut had no camera on them at all.
    Drift worked only because it moves `x`.

    zoompan re-evaluates `z` every frame, which is the whole point.
    """
    out_w = out_w or src_w
    out_h = out_h or src_h
    amt = AMOUNT.get(kind, 0.0)
    if kind == "hold" or amt <= 0 or n_frames <= 1:
        return f"scale={out_w}:{out_h}:flags=lanczos,format=yuv420p"
    last = max(1, n_frames - 1)
    prog = f"(on/{last})"
    if kind == "push":
        z = f"(1+{amt}*{prog})"
    elif kind == "pull":
        z = f"({1+amt}-{amt}*{prog})"
    else:                                   # drift: constant zoom, travels
        z = f"({1+amt})"
    if kind == "drift":
        # Travel across the spare width the zoom created.
        x = f"(iw/2-(iw/zoom/2)) + (iw-iw/zoom)*0.45*({prog}-0.5)*2"
    else:
        x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    return (f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={out_w}x{out_h}:fps={fps},"
            f"format=yuv420p")


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
    fps = 16
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate", "-of",
                        "csv=p=0", src], capture_output=True, text=True).stdout.strip()
    try:
        fps = int(round(eval(r))) if r else 16                 # noqa: S307
    except Exception:                                          # noqa: BLE001
        fps = 16
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-vf", move_filter(kind, n, w, h, fps=fps),
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
