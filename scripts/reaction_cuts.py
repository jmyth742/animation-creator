#!/usr/bin/env python3
"""
Cut to the listener in the middle of a line.

Every shot in every piece is ONE COMPLETE LINE. Nobody is ever cut away from
mid-sentence, and nobody is ever seen listening. That is why the conversations
still read as alternating statements however good the individual shots are --
a real scene cuts to the person NOT talking, because their face is where the
line lands.

THE BLOCKER, AND THE WAY ROUND IT
There is no footage of a character silently listening: every shot of them is
them speaking. But since holding the tail replaced generated picture with a
frozen frame, every shot now ENDS with a second or so of that character still,
mouth closed. That is reaction footage. It was being thrown away at the end of
shots where it reads as a stall; used inside someone else's line it is exactly
what it should be.

HOW THE CUT WORKS
The listener slice REPLACES part of the speaker's picture rather than being
added to it, so the shot's duration is unchanged and the soundtrack -- built
against the stitcher's offsets -- stays aligned to the frame. The speaker's
audio runs unbroken underneath, which is the whole point: you hear the line
continue while you watch it land.

    reaction_cuts.py --speaker a.mp4 --listener b.mp4 -o out.mp4
"""
import argparse
import subprocess
import sys
from pathlib import Path

MIN_SPEAKER_LIVE = 3.2      # below this a shot is too short to cut inside
REACTION = 1.15             # seconds on the listener
AT = 0.55                   # how far into the live portion the cut lands


def _dur(p: str) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip() or 0)


def _seg(src: str, start: float, length: float, out: str, w: int, h: int,
         fps: int) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}",
                    "-t", f"{length:.3f}", "-i", src,
                    "-vf", f"scale={w}:{h},fps={fps},format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-an", out], check=True)
    return out


def insert_reaction(speaker: str, listener: str, out: str,
                    speaker_live: float | None = None,
                    reaction: float = REACTION, at: float = AT) -> str | None:
    """Replace a slice of `speaker` with the tail of `listener`. None if unusable."""
    sd = _dur(speaker)
    ld = _dur(listener)
    live = speaker_live if speaker_live else sd
    if live < MIN_SPEAKER_LIVE or ld < reaction + 0.4 or sd < reaction + 1.2:
        return None
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "csv=p=0", speaker],
        capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    try:
        fps = int(round(eval(probe[2])))                       # noqa: S307
    except Exception:                                          # noqa: BLE001
        fps = 16
    # Work in FRAMES, not seconds. Splitting at arbitrary times let the three
    # segments round independently and the shot came out 0.13s longer than it
    # went in -- which would slide the soundtrack against the picture for every
    # shot after it, since the mix is built on the stitcher's offsets.
    total_f = round(sd * fps)
    react_f = round(reaction * fps)
    cut_f = max(round(0.9 * fps),
                min(round(live * at * fps), total_f - react_f - round(0.6 * fps)))
    tail_f = total_f - cut_f - react_f
    if tail_f < round(0.5 * fps):
        return None
    cut_at = cut_f / fps
    reaction = react_f / fps
    tmp = Path(out).parent / "_react"
    tmp.mkdir(parents=True, exist_ok=True)
    stem = Path(out).stem
    a = _seg(speaker, 0, cut_at, str(tmp / f"{stem}_a.mp4"), w, h, fps)
    # The listener's LAST seconds: mouth closed, held. Reaction footage.
    b = _seg(listener, max(0.0, ld - reaction - 0.15), reaction,
             str(tmp / f"{stem}_b.mp4"), w, h, fps)
    c = _seg(speaker, cut_at + reaction, tail_f / fps,
             str(tmp / f"{stem}_c.mp4"), w, h, fps)
    lst = tmp / f"{stem}.txt"
    lst.write_text("".join(f"file '{Path(x).resolve()}'\n" for x in (a, b, c)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", out], check=True)
    got = _dur(out)
    # Duration MUST be preserved or the soundtrack drifts from here on.
    if abs(got - sd) > 0.12:
        print(f"    duration moved {sd:.2f} -> {got:.2f}, refusing the cut")
        return None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--listener", required=True)
    ap.add_argument("--live", type=float)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    r = insert_reaction(a.speaker, a.listener, a.out, a.live)
    print(f"  {r}" if r else "  shot too short to cut inside")
    return 0 if r else 1


if __name__ == "__main__":
    sys.exit(main())
