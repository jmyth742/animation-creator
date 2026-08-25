#!/usr/bin/env python3
"""
Move legacy flat clips into per-series subdirectories.

Clips used to be written to ComfyUI/output/video/<scene_id>_00007_.mp4 with no
series component, so clips from different series collided on the same scene id
(every series has an ep01_s01). showrunner.py now writes to
ComfyUI/output/video/<series>/, which leaves the pre-existing flat clips
invisible to --resume.

This reconstructs which flat clip each episode actually used, by replaying the
old selection rule ("newest clip for this scene id at the time the episode was
stitched") against each episode's stitched/final mp4 timestamp, and links the
winners into the series subdirectory.

    python scripts/migrate_clips_to_series.py              # dry run
    python scripts/migrate_clips_to_series.py --apply
    python scripts/migrate_clips_to_series.py --apply --series tir-na-nog
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SERIES_DIR = ROOT / "series"
OUTPUT_DIR = ROOT / "output"
VIDEO_DIR = ROOT / "ComfyUI" / "output" / "video"

CLIP_SUFFIX_RE = re.compile(r"^(_\d+_?)?\.mp4$", re.IGNORECASE)


def flat_clips():
    """Legacy clips: mp4s directly in the video dir, newest first per name."""
    if not VIDEO_DIR.is_dir():
        return []
    return [f for f in VIDEO_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".mp4"]


def candidates_for(clips, scene_id):
    return [f for f in clips
            if f.name.startswith(scene_id) and CLIP_SUFFIX_RE.match(f.name[len(scene_id):])]


def episode_cutoff(series, ep_name):
    """When this episode was stitched — the moment the old code picked its clips."""
    d = OUTPUT_DIR / series / ep_name
    for suffix in ("_stitched.mp4", "_final.mp4", "_graded.mp4"):
        f = d / f"{ep_name}{suffix}"
        if f.exists():
            return f.stat().st_mtime, f.name
    return None, None


def scene_ids(series, ep_name):
    f = SERIES_DIR / series / "episodes" / f"{ep_name}.json"
    if not f.exists():
        return []
    data = json.loads(f.read_text())
    scenes = data.get("scenes", data if isinstance(data, list) else [])
    return [s["id"] for s in scenes if s.get("id")]


def link(src: Path, dst: Path):
    """Hardlink to avoid duplicating GBs; copy if that is not possible."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return "exists"
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        shutil.copy2(src, dst)
        return "copied"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually link (default: dry run)")
    ap.add_argument("--series", help="only migrate this series")
    args = ap.parse_args()

    clips = flat_clips()
    print(f"{len(clips)} legacy flat clip(s) in {VIDEO_DIR}\n")
    if not clips:
        return 0

    all_series = sorted(d.name for d in SERIES_DIR.iterdir() if d.is_dir()) \
        if not args.series else [args.series]

    claimed, total_missing = set(), 0
    for series in all_series:
        eps = sorted(d.name for d in (OUTPUT_DIR / series).iterdir() if d.is_dir()) \
            if (OUTPUT_DIR / series).is_dir() else []
        if not eps:
            continue
        print(f"── {series}")
        for ep_name in eps:
            cutoff, src_name = episode_cutoff(series, ep_name)
            ids = scene_ids(series, ep_name)
            if cutoff is None:
                print(f"   {ep_name}: no stitched episode — skipped "
                      f"(cannot tell which clips it used)")
                continue
            if not ids:
                print(f"   {ep_name}: no episode JSON — skipped")
                continue

            resolved, missing = [], []
            for sid in ids:
                elig = [c for c in candidates_for(clips, sid) if c.stat().st_mtime <= cutoff]
                if not elig:
                    missing.append(sid)
                    continue
                elig.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                resolved.append((sid, elig[0]))

            acts = {}
            for sid, src in resolved:
                dst = VIDEO_DIR / series / src.name
                claimed.add(src)
                if args.apply:
                    result = link(src, dst)
                    acts[result] = acts.get(result, 0) + 1
            total_missing += len(missing)
            note = f" ({', '.join(f'{v} {k}' for k, v in acts.items())})" if acts else ""
            print(f"   {ep_name}: {len(resolved)}/{len(ids)} scenes resolved "
                  f"vs {src_name}{note}")
            if missing:
                print(f"      no clip found for: {', '.join(missing)}")
        print()

    orphans = [c for c in clips if c not in claimed]
    print(f"summary: {len(claimed)} clip(s) attributed, {len(orphans)} unattributed "
          f"(superseded takes / older versions), {total_missing} scene(s) with no clip")
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to link them.")
    else:
        print(f"\nDone. Legacy flat clips were left in place; "
              f"delete them once you've confirmed a --resume run behaves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
