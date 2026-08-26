#!/usr/bin/env python3
"""
A colour grade per location, not one grade for the whole film.

Every shot currently shares a single grade, so the otherworld and the ruin have
the same palette. They should not: the valley is a place where nothing is ever
lost and the ruin is where everything was, and colour is the fastest way an
audience is told which one they are in.

These are deliberately restrained. A grade you notice is a grade that has taken
over -- the point is that a cut from the valley to the ruin should FEEL colder
without the viewer being able to say why.

    valley          warm, lifted blacks, gold in the highlights
    farewell_cliff  warm-neutral, low evening sun
    storm_cliffs    cool, hard contrast, desaturated -- Atlantic weather
    sunlight_path   warm, glowing, lifted -- everything tends to gold
    ruin            cool, crushed blacks, desaturated -- nothing lives here

Applied with eq/curves, which is deterministic and CPU-only, so the grade can
be re-judged and changed without touching the GPU.
"""
import argparse
import subprocess
import sys
from pathlib import Path

# saturation, contrast, gamma, gamma_r, gamma_b, brightness
GRADES = {
    "tir_na_nog":     dict(sat=1.06, con=1.02, gam=1.04, gr=1.03, gb=0.97, bri=0.012),
    "farewell_cliff": dict(sat=1.03, con=1.03, gam=1.01, gr=1.02, gb=0.99, bri=0.006),
    "sunlight_path":  dict(sat=1.08, con=0.99, gam=1.06, gr=1.05, gb=0.95, bri=0.020),
    "storm_cliffs":   dict(sat=0.90, con=1.10, gam=0.97, gr=0.98, gb=1.04, bri=-0.012),
    "ruined_ireland": dict(sat=0.84, con=1.08, gam=0.95, gr=0.97, gb=1.05, bri=-0.020),
}
DEFAULT = dict(sat=1.0, con=1.0, gam=1.0, gr=1.0, gb=1.0, bri=0.0)


def grade_filter(location: str) -> str:
    g = GRADES.get(location, DEFAULT)
    return (f"eq=saturation={g['sat']}:contrast={g['con']}:gamma={g['gam']}:"
            f"gamma_r={g['gr']}:gamma_b={g['gb']}:brightness={g['bri']}")


def apply_grade(src: str, location: str, out: str) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-vf", grade_filter(location) + ",format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-an", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("location")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    print(f"  {apply_grade(a.src, a.location, a.out)}  [{a.location}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
