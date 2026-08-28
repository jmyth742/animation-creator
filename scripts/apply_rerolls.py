#!/usr/bin/env python3
"""
Act on the re-roll results, deliberately and reversibly.

reroll_weak_shots.py renders extra seeds for the worst-scoring shots and
reports which take won. It swaps nothing, for a good reason: a higher CLIP
identity score is not the same as a better shot -- a take can score well
because the face is squarely lit and still be worse to watch.

But "nothing is swapped automatically" had quietly become "nothing can be
swapped at all". The first run found ep07_s01 at +0.070 and the results file
recorded only the number, not the file, so there was no way to act on it
without re-deriving which render had won. Eight shots of GPU time produced a
table nobody could use.

This closes that gap without removing the human decision. It lists what is
available, and applies only what is asked for.

    apply_rerolls.py                    # show candidates, change nothing
    apply_rerolls.py --min-gain 0.02    # narrow the list
    apply_rerolls.py --apply ep07_s01   # swap these shots in
    apply_rerolls.py --apply-all --min-gain 0.02

A swap copies the winning take alongside the original with a higher sequence
number, so find_latest_clip() picks it up. The original is never deleted --
--revert puts it back by touching it, and both files stay on disk.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

RESULTS = Path("/workspace/review/reroll/results.json")
SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$", re.IGNORECASE)


def next_name(original: Path) -> Path:
    """Same stem, next sequence number, so it sorts newest by mtime anyway."""
    m = SEQ.match(original.name)
    if not m:
        return original.with_name(f"{original.stem}_99999_.mp4")
    n = int(m.group("n"))
    d = original.parent
    while True:
        n += 1
        cand = d / f"{m.group('stem')}_{n:05d}_.mp4"
        if not cand.exists():
            return cand


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-gain", type=float, default=0.005)
    ap.add_argument("--apply", nargs="*", default=None,
                    help="shot ids to swap in")
    ap.add_argument("--apply-all", action="store_true")
    ap.add_argument("--revert", nargs="*", default=None)
    a = ap.parse_args()

    if not RESULTS.exists():
        print(f"  no results at {RESULTS} — run reroll_weak_shots.py first")
        return 1
    rows = json.loads(RESULTS.read_text())

    if not rows or "winner" not in rows[0]:
        print(f"  {RESULTS} predates path recording — it has scores but no\n"
              f"  file paths, so nothing here can be applied. Re-run\n"
              f"  reroll_weak_shots.py to regenerate it with paths.")
        return 1

    cands = [r for r in rows
             if r["gain"] >= a.min_gain and r["source"] != "original"
             and r.get("winner")]
    print(f"  {len(cands)} of {len(rows)} shots gained >= {a.min_gain:.3f}\n")
    print(f"  {'shot':12} {'was':>7} {'best':>7} {'gain':>8}  winner")
    for r in cands:
        print(f"  {r['shot']:12} {r['was']:7.3f} {r['best']:7.3f} "
              f"{r['gain']:+8.3f}  {Path(r['winner']).name}")

    if a.revert is not None:
        n = 0
        for r in rows:
            if a.revert and r["shot"] not in a.revert:
                continue
            orig = Path(r.get("original") or "")
            if orig.exists():
                os.utime(orig, (time.time(), time.time()))
                print(f"  reverted {r['shot']} -> {orig.name}")
                n += 1
        print(f"\n  {n} reverted (nothing deleted)")
        return 0

    targets = cands if a.apply_all else \
        [r for r in cands if a.apply and r["shot"] in a.apply]
    if not targets:
        print("\n  nothing applied — pass --apply <shot> or --apply-all")
        return 0

    print()
    for r in targets:
        win, orig = Path(r["winner"]), Path(r.get("original") or "")
        if not win.exists():
            print(f"  {r['shot']}: winning take is gone ({win.name})")
            continue
        dst = next_name(orig if orig.name else win)
        shutil.copy(win, dst)
        print(f"  {r['shot']:12} {win.name} -> {dst.name}  ({r['gain']:+.3f})")
    print(f"\n  {len(targets)} applied. Originals kept; --revert undoes it.")
    print("  Re-assemble the film for these to appear in a cut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
