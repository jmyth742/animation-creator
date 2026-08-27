#!/usr/bin/env python3
"""
Lay foley and the motif over an existing cut.

Adds the two things the soundtrack still lacks: spot effects, so events sound
like they happened, and a theme that returns, so the score has structure rather
than only atmosphere.

Both sit UNDER the existing mix rather than replacing it -- the bed, the duck
and the voice are already right and re-deriving them risks the alignment that
was hard won.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import sound_design as sd                                      # noqa: E402
import foley                                                   # noqa: E402
import assemble_film as af                                     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--source", default="/workspace/review/post/film_react.mp4")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    af.ONLY_EPISODES = {e.strip() for e in a.episodes.split(",")}
    edit = af.build_edit(a.series)
    if not edit:
        print("  no shots"); return 1
    total = sum(e["seconds"] for e in edit)
    src = Path(a.source)
    if not src.exists():
        print(f"  no source cut at {src}"); return 1

    work = Path(a.out).parent / "_sound"
    work.mkdir(parents=True, exist_ok=True)

    # ── foley ────────────────────────────────────────────────────────────
    plan = foley.plan_for([{"seconds": e["seconds"], "staging": e["staging"]}
                           for e in edit])
    spots = work / "foley.wav"
    foley.place(plan, total, str(spots))
    print(f"  {len(plan)} spot effects across {total:.1f}s "
          f"({len(plan)/(total/60):.1f} per minute)")

    # ── motif: quietly early, again at the end ───────────────────────────
    motif = work / "motif.wav"
    sd.build_motif(motif, root=73.42, when=6.0, total=total, level=0.075)
    motif2 = work / "motif2.wav"
    sd.build_motif(motif2, root=73.42, when=max(0.0, total - 22.0),
                   total=total, level=0.115, octave=3)
    print(f"  motif at 6.0s and {total-22.0:.1f}s")

    # ── under the existing mix ───────────────────────────────────────────
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(spots),
         "-i", str(motif), "-i", str(motif2),
         "-filter_complex",
         "[1:a]volume=0.85[f];[2:a]volume=1.0[m1];[3:a]volume=1.0[m2];"
         "[0:a][f][m1][m2]amix=inputs=4:normalize=0:duration=first,"
         "alimiter=limit=0.97:level=disabled[out]",
         "-map", "0:v", "-map", "[out]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", a.out], check=True)
    print(f"  {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
