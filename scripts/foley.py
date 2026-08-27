#!/usr/bin/env python3
"""
Spot effects: the sound of things happening.

There is not one footstep, hoofbeat, cloth movement or spear-butt in either
film. Only beds -- wind, water, drizzle -- which is ambience, not sound design.
A bed tells you where you are; a spot effect tells you something HAPPENED, and
its absence is why the films sound like a place rather than a scene.

Everything here is synthesised with ffmpeg rather than sampled, for the same
reason the ambience beds are: no licence to worry about, nothing to download,
and it can be re-tuned without leaving the pipeline. Synthesised foley will not
beat a good sample library, but silence loses to both.

Each effect is an envelope over filtered noise plus, where it matters, a tonal
body:

    step      soft low thud, damp, grass or wet stone
    hoof      harder, two-part -- the strike and the roll after it
    cloth     brief pink-noise swell, no transient
    spear     wooden knock, a short resonant tail
    gust      slow swell in the wind bed, for a beat that needs punctuation

Placement is deliberate and sparse. Three or four in a shot is a scene; a
footstep on every frame of movement is a video game.

    foley.py step -o step.wav
    foley.py place --plan plan.json --duration 197 -o spots.wav
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

SR = 48000

# name -> (ffmpeg source chain, seconds, default level)
EFFECTS = {
    "step": ("anoisesrc=r=48000:c=brown:a=0.9:d=0.30,"
             "lowpass=f=260,highpass=f=45,"
             "afade=t=in:st=0:d=0.006,afade=t=out:st=0.05:d=0.24",
             0.30, 0.22),
    "hoof": ("anoisesrc=r=48000:c=brown:a=0.9:d=0.34,"
             "lowpass=f=420,highpass=f=60,"
             "afade=t=in:st=0:d=0.004,afade=t=out:st=0.03:d=0.18,"
             "aecho=0.8:0.5:38:0.35",
             0.34, 0.26),
    "cloth": ("anoisesrc=r=48000:c=pink:a=0.9:d=0.45,"
              "highpass=f=900,lowpass=f=5200,"
              "afade=t=in:st=0:d=0.16,afade=t=out:st=0.20:d=0.25",
              0.45, 0.10),
    "spear": ("anoisesrc=r=48000:c=white:a=0.9:d=0.26,"
              "bandpass=f=520:width_type=q:w=1.4,"
              "afade=t=in:st=0:d=0.003,afade=t=out:st=0.02:d=0.22",
              0.26, 0.16),
    "gust": ("anoisesrc=r=48000:c=pink:a=0.9:d=1.80,"
             "lowpass=f=1100,highpass=f=110,"
             "afade=t=in:st=0:d=0.7,afade=t=out:st=0.9:d=0.9",
             1.80, 0.13),
}


def render(name: str, out: str, level: float | None = None) -> str:
    chain, dur, lvl = EFFECTS[name]
    lvl = level if level is not None else lvl
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", f"{chain},volume={lvl:.3f}",
                    "-t", f"{dur}", "-ar", str(SR), "-ac", "2", out], check=True)
    return out


def place(plan: list[dict], duration: float, out: str) -> str:
    """plan: [{'at': seconds, 'effect': 'step', 'level': 0.2}, ...]"""
    tmp = Path(out).parent / "_foley"
    tmp.mkdir(parents=True, exist_ok=True)
    ins, filt, tags = [], [], []
    for i, ev in enumerate(plan):
        name = ev["effect"]
        if name not in EFFECTS:
            continue
        f = str(tmp / f"{i:03d}_{name}.wav")
        render(name, f, ev.get("level"))
        ins += ["-i", f]
        ms = int(max(0.0, ev["at"]) * 1000)
        filt.append(f"[{len(tags)}:a]adelay={ms}|{ms}[e{len(tags)}]")
        tags.append(f"[e{len(tags)}]")
    if not tags:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{duration}",
                        out], check=True)
        return out
    filt.append("".join(tags) +
                f"amix=inputs={len(tags)}:normalize=0:dropout_transition=0,"
                f"apad,atrim=duration={duration:.3f}[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins +
                   ["-filter_complex", ";".join(filt), "-map", "[out]",
                    "-ar", str(SR), "-ac", "2", out], check=True)
    return out


# Which effects suit which shot, and how many. Sparse on purpose.
BY_STAGING = {
    "full_body": [("step", 0.9), ("step", 1.7), ("cloth", 2.4)],
    "walking_away": [("step", 0.8), ("step", 1.5), ("step", 2.2)],
    "three_quarter": [("cloth", 1.1)],
    "medium": [("cloth", 1.3)],
    "over_shoulder": [("cloth", 1.0)],
    "close": [],
    "ecu": [],
}


def plan_for(shots: list[dict]) -> list[dict]:
    """Build a placement plan from an edit list: [{'id','seconds','staging','at'}]"""
    plan, t = [], 0.0
    for sc in shots:
        for eff, off in BY_STAGING.get(sc.get("staging", "medium"), []):
            if off < sc["seconds"] - 0.4:
                plan.append({"at": round(t + off, 3), "effect": eff})
        # a gust every few shots, on the wider ones, as punctuation
        if sc.get("staging") in ("full_body", "walking_away", "wider") and \
                sc["seconds"] > 6:
            plan.append({"at": round(t + sc["seconds"] * 0.55, 3), "effect": "gust"})
        t += sc["seconds"]
    return plan


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("render"); one.add_argument("effect", choices=list(EFFECTS))
    one.add_argument("-o", "--out", required=True)
    pl = sub.add_parser("place"); pl.add_argument("--plan", required=True)
    pl.add_argument("--duration", type=float, required=True)
    pl.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if a.cmd == "render":
        print("  " + render(a.effect, a.out))
    else:
        print("  " + place(json.loads(Path(a.plan).read_text()), a.duration, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
