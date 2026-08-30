#!/usr/bin/env python3
"""
Install the repaired dialogue closes into an episode, reversibly.

repair_dialogue_closes.py writes its takes to review/repaired_closes and
substitutes nothing, which was the right default while the composite seed was
unproven. It is proven now: ep13_s05 came back with the ruin behind her where
the shipped take had a flat teal sea and no location at all.

Installing copies the repaired take beside the original with a higher sequence
number, so find_latest_clip picks it up and `produce --resume` re-stitches
with it. The original is never deleted -- --revert restores it by touching it.

    install_repaired_closes.py <series> --episode 13
    install_repaired_closes.py <series> --episode 13 --revert
"""
import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

REPAIRED = Path("/workspace/review/repaired_closes")
SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$", re.IGNORECASE)


def next_name(original: Path) -> Path:
    m = SEQ.match(original.name)
    if not m:
        return original.with_name(f"{original.stem}_70001_.mp4")
    n, d = int(m.group("n")), original.parent
    while True:
        n += 1
        c = d / f"{m.group('stem')}_{n:05d}_.mp4"
        if not c.exists():
            return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    ep = sr.load_json(sr.episode_path(a.series, a.episode))

    n = 0
    for scene in ep["scenes"]:
        if not scene.get("dialogue"):
            continue
        sid = scene["id"]
        cur = sr.find_latest_clip(sid)
        if not cur:
            continue
        if a.revert:
            # The oldest take is the original; touching it makes it newest.
            d = Path(cur).parent
            takes = sorted(d.glob(f"{sid}_*.mp4"))
            if takes:
                os.utime(takes[0], (time.time(), time.time()))
                print(f"  {sid}: reverted to {takes[0].name}")
                n += 1
            continue
        src = REPAIRED / f"{sid}.mp4"
        if not src.exists():
            print(f"  {sid}: no repaired take"); continue
        d0 = sr._get_video_duration(cur)
        d1 = sr._get_video_duration(str(src))
        if abs(d0 - d1) > 0.15:
            print(f"  {sid}: duration differs {d0:.2f} vs {d1:.2f} — skipping, "
                  f"installing it would desynchronise the episode")
            continue
        dst = next_name(Path(cur))
        shutil.copy(src, dst)
        print(f"  {sid}: installed -> {dst.name}")
        n += 1
    print(f"\n  {n} close(s) {'reverted' if a.revert else 'installed'}. "
          f"Originals kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
