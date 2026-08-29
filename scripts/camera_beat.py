#!/usr/bin/env python3
"""
A camera move that happens AT A MOMENT, and moves TOWARD SOMETHING.

camera_move.py applies one constant move across a whole shot: a push that
creeps from frame one to the last at the same rate. That reads as texture, not
as direction. What a scene actually wants is a move with a cause -- she says
the line, and THEN the camera begins to close on him; he sees the ruin, and the
frame drifts off his face to the empty ground.

Two things this adds:

    WHEN   the move starts at a chosen second, holds still before it, and eases
           rather than beginning at full rate. Nothing announces a cut like a
           camera that is already moving on frame one.

    WHERE  it closes on a POINT, not the centre. A push into the middle of a
           two-shot pushes into the gap between two people; a push into her
           face is a different shot entirely.

zoompan re-evaluates z, x and y every frame, so the centre can travel toward
the target while the zoom tightens. crop cannot do this -- it fixes w and h at
init, which is why an earlier version of the push was bit-identical to a static
frame.

    camera_beat.py in.mp4 out.mp4 --to 0.72,0.38 --start 3.5 --amount 0.14
    camera_beat.py in.mp4 out.mp4 --to face-right --start 4 --ease 1.2
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Where things usually are in our framings, so a caller can say what they mean.
TARGETS = {
    "centre":       (0.50, 0.50),
    "face":         (0.50, 0.38),   # a close-up: the face sits above centre
    "face-left":    (0.30, 0.36),   # left figure of a two-shot
    "face-right":   (0.70, 0.36),
    "figure-left":  (0.28, 0.55),
    "figure-right": (0.72, 0.55),
    "horizon":      (0.50, 0.62),
    "ground":       (0.50, 0.78),
}


def _one(src, entry):
    """
    One field at a time.

    ffprobe emits csv fields in ITS order, not the order they were asked for:
    a request for width,height,nb_frames,r_frame_rate came back as
    rate,rate,frames, so fps was read as 97 and the whole move was built at the
    wrong rate. Asking for one thing at a time cannot be misread.
    """
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", entry, "-of", "csv=p=0", src],
                          capture_output=True, text=True).stdout.strip().split(",")[0]


def probe(src):
    w, h = _one(src, "stream=width"), _one(src, "stream=height")
    nb, rate = _one(src, "stream=nb_frames"), _one(src, "stream=r_frame_rate")
    try:
        fps = int(round(eval(rate)))                           # noqa: S307
    except Exception:                                          # noqa: BLE001
        fps = 16
    try:
        n = int(nb)
    except ValueError:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                  "format=duration", "-of", "csv=p=0", src],
                                 capture_output=True, text=True).stdout.strip())
        n = max(1, int(d * fps))
    return int(w), int(h), n, fps


def build_filter(w, h, n, fps, tx, ty, amount, start_f, ease_f, out_w, out_h):
    """
    Hold, then ease into a zoom whose centre travels to (tx, ty).

    Progress is a smoothstep over the easing window so the move begins and ends
    gently: a linear ramp starts and stops visibly, which is the thing that
    makes a camera look automated.
    """
    s, e = max(0, start_f), max(1, ease_f)
    # p: 0 before the start, smoothstep 0->1 across the ease, 1 after
    raw = f"clip((on-{s})/{e},0,1)"
    p = f"({raw}*{raw}*(3-2*{raw}))"
    z = f"(1+{amount}*{p})"
    # centre travels from the frame centre toward the target as the zoom tightens
    cx = f"({0.5}+({tx}-{0.5})*{p})"
    cy = f"({0.5}+({ty}-{0.5})*{p})"
    x = f"(iw*{cx}-(iw/zoom/2))"
    y = f"(ih*{cy}-(ih/zoom/2))"
    # No quotes around the expressions. A shell strips them; subprocess passes
    # them through as literal characters and ffmpeg then cannot parse the
    # expression -- it falls back to defaults and emits a one-second clip while
    # exiting 0. The same filter string works from a terminal and fails from
    # Python, which is a good way to lose an afternoon.
    # Commas inside clip()/min() are filter-argument separators unless escaped.
    # Quoting works from a shell and not from subprocess, where the quotes
    # arrive as literal characters -- so escape instead of quote.
    esc = lambda e: e.replace(",", r"\,")                      # noqa: E731
    return (f"zoompan=z={esc(z)}:x={esc(x)}:y={esc(y)}:d=1:"
            f"s={out_w}x{out_h}:fps={fps},format=yuv420p")


def apply_beat(src, out, target="face", start=0.0, ease=1.5, amount=0.12):
    w, h, n, fps = probe(src)
    tx, ty = TARGETS.get(target, (None, None))
    if tx is None:
        try:
            tx, ty = (float(v) for v in str(target).split(","))
        except Exception:                                      # noqa: BLE001
            raise SystemExit(f"unknown target '{target}'; use one of "
                             f"{sorted(TARGETS)} or 'x,y' in 0..1")
    vf = build_filter(w, h, n, fps, tx, ty, amount,
                      int(start * fps), max(1, int(ease * fps)), w, h)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf,
                    "-c:v", "libx264", "-crf", "16", "-an", str(out)], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--to", default="face",
                    help=f"{sorted(TARGETS)} or 'x,y' fractions")
    ap.add_argument("--start", type=float, default=0.0, help="seconds before it begins")
    ap.add_argument("--ease", type=float, default=1.5, help="seconds the move takes")
    ap.add_argument("--amount", type=float, default=0.12, help="0.12 = 12% closer")
    a = ap.parse_args()
    apply_beat(a.src, a.out, a.to, a.start, a.ease, a.amount)
    print(f"  {a.out}  push to {a.to}, starts {a.start}s, over {a.ease}s, "
          f"{a.amount*100:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
