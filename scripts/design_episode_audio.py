#!/usr/bin/env python3
"""
Lay the designed soundtrack over a finished episode.

The pipeline's own stitcher gives every location one flat mono noise bed. This
replaces that with the layered design in sound_design.py: a bed chosen for the
location, per-shot microphone perspective, a drone rooted differently per
place, and the voice ducked in front of it.

Two things it must get right, both of which have already gone wrong once:

  - Offsets come from the STITCHER, never recomputed. Summing them again with
    a crossfade put the voice 1.70s ahead of picture by the last shot.
  - The voice sits at frame 0 of its shot, with no lead. S2V generated the
    mouths FROM that audio, so nudging it later breaks lip sync.

    design_episode_audio.py <series> --episode N
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import sound_design as sd                                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    ep_dir = Path("output") / a.series / f"ep{a.episode:02d}"
    graded = ep_dir / f"ep{a.episode:02d}_graded.mp4"
    if not graded.exists():
        graded = ep_dir / f"ep{a.episode:02d}_final.mp4"
    if not graded.exists():
        print(f"  no rendered episode at {ep_dir}")
        return 1

    locs = {s.get("location") for s in ep["scenes"]}
    if len(locs) != 1:
        print(f"  {len(locs)} locations in this episode: {locs}")
        print("  the bed is chosen per location; this tool assumes one set")
    loc = ep["scenes"][0].get("location")
    preset = sd.PRESET_BY_LOCATION.get(loc)
    if not preset:
        print(f"  no ambience bed mapped for '{loc}'. Add one to "
              f"PRESET_BY_LOCATION rather than letting it fall through to "
              f"whatever happens to be first.")
        return 1

    plan, missing = [], []
    for sc in ep["scenes"]:
        clip = sr.find_latest_clip(sc["id"])
        if not clip:
            missing.append(sc["id"])
            continue
        plan.append({"id": sc["id"],
                     "seconds": round(sr._get_video_duration(clip), 3),
                     "staging": sc.get("staging", "medium")})
    if missing:
        print(f"  missing clips: {missing}")
        return 1

    offsets = sr.scene_start_offsets(ep["scenes"])
    vo_dir = ep_dir / "audio"
    out_wav = ep_dir / f"ep{a.episode:02d}_designed.wav"
    out_mp4 = Path(a.out) if a.out else ep_dir / f"ep{a.episode:02d}_designed.mp4"

    print(f"  {loc} -> '{preset}' bed, {len(plan)} shots, "
          f"{sum(p['seconds'] for p in plan):.2f}s")
    sd.mix_episode(plan, vo_dir, out_wav, preset=preset,
                   offsets=offsets, vo_lead=0.0)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(graded),
                    "-i", str(out_wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(out_mp4)], check=True)
    print(f"  {out_mp4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
