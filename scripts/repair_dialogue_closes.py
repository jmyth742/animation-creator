#!/usr/bin/env python3
"""
Re-render dialogue close-ups so they are set where the scene is set.

Every dialogue shot in the series seeds from a bare character portrait. That
gives the strongest possible identity signal and no location at all, so on
ep13 the wides are a grey ruin under low cloud and the closes are a bright
teal sea. Cut together they are two different scenes.

stage_composite.py builds the seed that fixes it: the character pasted into
the location plate behind a feathered ellipse. Rendered against both
alternatives on ep13_s06, only the composite put him in the ruin.

This re-renders the dialogue shots of an episode from those seeds and leaves
the originals in place. Nothing is swapped and no film is rebuilt -- run
showrunner produce --resume afterwards to re-assemble with the new takes,
after looking at them.

    repair_dialogue_closes.py <series> --episode 13
    repair_dialogue_closes.py <series> --episode 13 --shots ep13_s06,ep13_s08
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

OUT = Path("/workspace/review/repaired_closes")
SEED = 4321


def inplace_seed(series: str, scene: dict, who: str) -> Path | None:
    """The composite for this scene's setup and framing, if one exists."""
    d = sr.series_path(series) / "sets" / scene.get("location", "")
    setup = scene.get("setup") or "master"
    for framing in (scene.get("staging") or "close", "close", "medium"):
        for su in (setup, "master", "reverse"):
            p = d / f"{su}__{who}_{framing}__inplace.png"
            if p.exists():
                return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--shots", default=None)
    ap.add_argument("--steps", type=int, default=10)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    res = sr.get_resolution_config("480p", "wan")
    want = {s.strip() for s in a.shots.split(",")} if a.shots else None

    done = []
    for scene in ep["scenes"]:
        if not scene.get("dialogue"):
            continue
        sid = scene["id"]
        if want and sid not in want:
            continue
        who = scene["dialogue"][0].get("character")
        seed_img = inplace_seed(a.series, scene, who)
        if not seed_img:
            print(f"  {sid}: no in-place seed for {who} at "
                  f"{scene.get('location')}; run stage_composite.py first")
            continue
        prefix = f"rc_{sid}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            vo = (Path("output") / a.series / f"ep{a.episode:02d}" / "audio"
                  / f"{sid}.mp3")
            if not vo.exists():
                print(f"  {sid}: no voice track at {vo}"); continue
            spoken = sr._get_video_duration(str(vo))
            padded = str(vo.with_name(f"{sid}_rc.mp3"))
            sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
            frames, extra, tail = sr.s2v_chunks_for_duration(
                spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
            wf = sr.build_video_workflow(
                "wan", "s2v", sr.build_scene_prompt(scene, bible), SEED, prefix,
                frames, res, negative_prompt=sr.build_negative_prompt(scene),
                steps=a.steps, image_name=sr.copy_to_input(str(seed_img)),
                audio_path=sr.copy_to_input(padded), extra_chunks=extra,
                last_chunk_frames=tail)
            print(f"  {sid}: re-rendering from {seed_img.name} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=2400 * (1 + extra)):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        subprocess.run(["cp", clip, str(OUT / f"{sid}.mp4")])
        done.append(sid)
        print(f"    {sid} -> {OUT / f'{sid}.mp4'}", flush=True)

    print(f"\n  {len(done)} dialogue shot(s) re-rendered in place.")
    print(f"  Look at them before swapping: the seed is a collage and the "
          f"join can\n  show. Nothing has been substituted into the episode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
