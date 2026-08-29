#!/usr/bin/env python3
"""
A post-production PTZ head: pan, tilt and zoom as independent axes.

camera_beat.py coupled them -- the frame only travelled as the zoom tightened,
so a pan without a zoom was impossible. A real PTZ does not work that way. It
can hold focal length and pan across a landscape, tilt down from sky to ground
at a fixed size, or zoom while locked off.

HOW A DIGITAL PTZ HAS TO WORK
There is no optical head; the move is a window cropped out of a larger frame.
So panning needs somewhere to pan INTO. The rig therefore crops in by a base
amount first -- exactly as a security PTZ or a live broadcast crop does -- and
travels within the margin that creates. At base 1.00 there is no margin and no
move is possible; at 1.20 there is 17% of the width to travel across.

Our clips are upscaled 4x for delivery, so cropping a 1.15-1.25 window out of
them costs nothing at 1080p. The pixels were already paid for.

    camera_ptz.py in.mp4 out.mp4 --zoom 1.15:1.15 --pan 0.30:0.70   # pure pan
    camera_ptz.py in.mp4 out.mp4 --zoom 1.10:1.35 --pan 0.5:0.68 --tilt 0.5:0.40
    camera_ptz.py in.mp4 out.mp4 --tilt 0.30:0.70 --start 2 --over 3

Each axis takes from:to. Omit an axis and it holds.
"""
import argparse
import subprocess
import sys


def _one(src, entry):
    """One ffprobe field at a time -- it emits csv in its own order, not ours."""
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", entry, "-of", "csv=p=0", src],
                          capture_output=True, text=True).stdout.strip().split(",")[0]


def probe(src):
    w, h = int(_one(src, "stream=width")), int(_one(src, "stream=height"))
    rate = _one(src, "stream=r_frame_rate")
    try:
        fps = int(round(eval(rate)))                           # noqa: S307
    except Exception:                                          # noqa: BLE001
        fps = 16
    try:
        n = int(_one(src, "stream=nb_frames"))
    except ValueError:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                  "format=duration", "-of", "csv=p=0", src],
                                 capture_output=True, text=True).stdout.strip())
        n = max(1, int(d * fps))
    return w, h, n, fps


def _pair(s, default):
    if not s:
        return default, default
    if ":" in str(s):
        a, b = str(s).split(":", 1)
        return float(a), float(b)
    return float(s), float(s)


def ptz_filter(fps, out_w, out_h, z0, z1, px0, px1, py0, py1,
               start_f, over_f):
    """
    Smoothstep across the move window, each axis interpolated on its own.

    The centre is CLAMPED so the window can never leave the frame: at zoom z
    the visible half-width is 1/(2z), so the centre must stay within
    [1/(2z), 1 - 1/(2z)]. Without that a pan to 0.9 at a modest zoom slides off
    the edge and ffmpeg silently pins it, which looks like the move stopping
    early for no reason.
    """
    s, o = max(0, start_f), max(1, over_f)
    raw = f"clip((on-{s})/{o},0,1)"
    p = f"({raw}*{raw}*(3-2*{raw}))"
    z = f"({z0}+({z1}-{z0})*{p})"
    cx = f"({px0}+({px1}-{px0})*{p})"
    cy = f"({py0}+({py1}-{py0})*{p})"
    # half the visible extent, in fractions of the source
    hx = "(1/(2*zoom))"
    cxc = f"min(max({cx},{hx}),1-{hx})"
    cyc = f"min(max({cy},{hx}),1-{hx})"
    x = f"(iw*{cxc}-(iw/zoom/2))"
    y = f"(ih*{cyc}-(ih/zoom/2))"
    esc = lambda e: e.replace(",", r"\,")                      # noqa: E731
    return (f"zoompan=z={esc(z)}:x={esc(x)}:y={esc(y)}:d=1:"
            f"s={out_w}x{out_h}:fps={fps},format=yuv420p")


def apply_ptz(src, out, zoom="1.12:1.12", pan=None, tilt=None,
              start=0.0, over=2.5, crf=16):
    w, h, n, fps = probe(src)
    z0, z1 = _pair(zoom, 1.12)
    px0, px1 = _pair(pan, 0.5)
    py0, py1 = _pair(tilt, 0.5)
    if max(z0, z1) <= 1.001 and (px0 != px1 or py0 != py1):
        # A pan at zoom 1.0 has nowhere to go. Give it the smallest margin that
        # covers the requested travel rather than silently doing nothing.
        need = max(abs(px1 - px0), abs(py1 - py0))
        z0 = z1 = round(1.0 + need * 1.15 + 0.04, 3)
        print(f"    pan/tilt at zoom 1.0 has no margin — using base zoom {z0}")
    vf = ptz_filter(fps, w, h, z0, z1, px0, px1, py0, py1,
                    int(start * fps), max(1, int(over * fps)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf,
                    "-c:v", "libx264", "-crf", str(crf), "-an", str(out)],
                   check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--zoom", default="1.12:1.12", help="from:to, 1.0 = full frame")
    ap.add_argument("--pan", default=None, help="from:to horizontal centre, 0..1")
    ap.add_argument("--tilt", default=None, help="from:to vertical centre, 0..1")
    ap.add_argument("--start", type=float, default=0.0, help="seconds held first")
    ap.add_argument("--over", type=float, default=2.5, help="seconds the move takes")
    a = ap.parse_args()
    apply_ptz(a.src, a.out, a.zoom, a.pan, a.tilt, a.start, a.over)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", a.out],
                       capture_output=True, text=True).stdout.strip()
    print(f"  {a.out}  zoom {a.zoom} pan {a.pan or 'hold'} tilt {a.tilt or 'hold'}"
          f" · starts {a.start}s over {a.over}s · {float(d):.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
