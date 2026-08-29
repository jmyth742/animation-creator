#!/usr/bin/env python3
"""
Give an already-rendered episode a camera, without re-rendering anything.

Measured across ep13 and ep14, every shot sits between 1.9 and 4.9 motion. A
walking shot measures 12.1. So the episodes are, in motion terms, a slideshow:
each frame is well composed and almost nothing moves inside it. That is the
single biggest thing between what we have and something watchable, and it does
not need the GPU at all.

camera_move.py crops a MOVING window out of the frame. The clips are 832x480,
which is smaller than delivery, so this version works on the 4x upscaled shots
where there is real headroom to crop into.

Moves are assigned by what the shot is doing, not at random:

    establishing wide, nobody in it   drift    the eye travels the landscape
    wide with a figure                push     slowly toward them
    dialogue                          push     small, into the face on a line
    the last shot of the episode      pull     leave them alone in the frame

Writes each moved shot with a higher sequence number, so find_latest_clip picks
it up and `produce --resume` re-stitches from the moved takes without
re-rendering a frame. The originals stay on disk.

    add_camera_to_episode.py <series> --episode 13
    add_camera_to_episode.py <series> --episode 13 --dry-run
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import camera_move as cm                                       # noqa: E402
import showrunner as sr                                        # noqa: E402

SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$", re.IGNORECASE)


def next_name(original: Path) -> Path:
    m = SEQ.match(original.name)
    if not m:
        return original.with_name(f"{original.stem}_90001_.mp4")
    n = int(m.group("n"))
    d = original.parent
    while True:
        n += 1
        cand = d / f"{m.group('stem')}_{n:05d}_.mp4"
        if not cand.exists():
            return cand


def pick_move(scene: dict, index: int, total: int) -> str:
    """
    Vary the move, or it is as monotonous as having none.

    A first pass assigned "push" to twelve of thirteen shots. A film where
    every shot creeps forward reads exactly as flat as one where nothing
    moves -- the eye stops noticing after the third. Roughly a third of the
    shots hold, so the moves that do happen land.

    The split panel holds on purpose: it is the beat where neither of them
    speaks, and a camera crawling into a stitched frame draws attention to
    the seam.
    """
    if index == total - 1:
        return "pull"                      # leave them alone at the end
    if (scene.get("visual") or "").lower().startswith("split panel"):
        return "hold"
    if not (scene.get("characters") or []):
        return "drift"                     # empty landscape, let the eye travel
    if scene.get("dialogue"):
        # Alternate: a line delivered on a still frame reads as weight, and
        # makes the next push mean something.
        return "push" if index % 2 == 0 else "hold"
    # Wides with a figure alternate push and drift so the landscape shots do
    # not all creep the same direction.
    return "push" if index % 3 else "drift"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    scenes = ep["scenes"]

    done = 0
    for i, scene in enumerate(scenes):
        src = sr.find_latest_clip(scene["id"])
        if not src:
            print(f"  {scene['id']}: no clip"); continue
        kind = pick_move(scene, i, len(scenes))
        dst = next_name(Path(src))
        print(f"  {scene['id']:10} {kind:6} -> {dst.name}", flush=True)
        if a.dry_run:
            continue
        try:
            cm.apply_move(src, kind, str(dst))
        except Exception as e:                                 # noqa: BLE001
            print(f"    FAILED {type(e).__name__}: {e}"); continue
        # A move that changed the duration would desynchronise the whole
        # episode against its audio, so check rather than assume.
        d0 = sr._get_video_duration(src)
        d1 = sr._get_video_duration(str(dst))
        if abs(d0 - d1) > 0.05:
            print(f"    duration changed {d0:.2f} -> {d1:.2f}; reverting")
            dst.unlink(missing_ok=True); continue
        done += 1

    print(f"\n  {done}/{len(scenes)} shots given a camera.")
    if done and not a.dry_run:
        print(f"  Re-stitch with:\n    showrunner.py produce {a.series} "
              f"--episode {a.episode} --quality final --upscale --no-grade "
              f"--resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
