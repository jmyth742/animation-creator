#!/usr/bin/env python3
"""
Re-render an episode's silent wides from generated plates.

Three seeding methods have now been measured on the same shots:

    portrait                    0 of 11 read as wide
    location plate              correct place, correct framing, but static
    staged character plate      5 of 10
    GENERATED wide plate        5 of 5, every one between 0.991 and 0.998

ep13 and ep14 were built on the location-plate method because the generated
one did not exist yet. Their wides average 0.831 and 0.924 against the 0.99+ a
real wide plate gives, and the generated plates also have composition in them
-- a figure the size of a full stop against a horizon, rather than a figure
standing in the middle of a frame.

Writes each upgraded shot with a higher sequence number so `produce --resume`
picks it up. The originals stay.

    upgrade_wides.py <series> --episode 13
    upgrade_wides.py <series> --episode 13 --dry-run
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

SEQ = re.compile(r"^(?P<stem>.+?)_(?P<n>\d+)_?\.mp4$", re.IGNORECASE)
GEN = {"ruined_ireland": "ruin", "tir_na_nog": "valley",
       "farewell_cliff": "cliff", "sunlight_path": "valley"}


def next_name(original: Path) -> Path:
    m = SEQ.match(original.name)
    if not m:
        return original.with_name(f"{original.stem}_80001_.mp4")
    n, d = int(m.group("n")), original.parent
    while True:
        n += 1
        c = d / f"{m.group('stem')}_{n:05d}_.mp4"
        if not c.exists():
            return c


def pick_plate(series, scene):
    """A generated plate matching this shot's place, people and intent."""
    stem = GEN.get(scene.get("location", ""))
    if not stem:
        return None
    g = sr.series_path(series) / "sets" / "_generated"
    chars = scene.get("characters") or []
    visual = (scene.get("visual") or "").lower()
    cands = []
    if len(chars) > 1:
        cands.append(f"gen__{stem}_twoshot.png")
    elif chars:
        who = chars[0]
        if any(w in visual for w in ("walk", "cross", "stride")):
            cands.append(f"gen__{stem}_walking.png")
        cands.append(f"gen__{stem}_wide_{who}.png")
    for c in cands:
        p = g / c
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--steps", type=int, default=8)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    res = sr.get_resolution_config("480p", "wan")

    done = skipped = 0
    for scene in ep["scenes"]:
        if scene.get("dialogue"):
            continue                       # closes are not this job
        plate = pick_plate(a.series, scene)
        if not plate:
            print(f"  {scene['id']}: no generated plate for "
                  f"{scene.get('location')}; leaving as is")
            skipped += 1
            continue
        src = sr.find_latest_clip(scene["id"])
        if not src:
            print(f"  {scene['id']}: no existing clip"); continue
        print(f"  {scene['id']:10} -> {plate.name}", flush=True)
        if a.dry_run:
            continue
        prefix = f"uw_{scene['id']}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "i2v", sr.build_scene_prompt(scene, bible), 5150, prefix,
                sr.MAX_FRAMES, res,
                negative_prompt=sr.build_negative_prompt(scene),
                steps=a.steps, image_name=sr.copy_to_input(str(plate)))
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        # Hold to the authored length, then install so --resume picks it up.
        want = float(scene.get("hold_seconds") or 0)
        dst = next_name(Path(src))
        if want > sr._get_video_duration(clip) + 0.1:
            sr.hold_tail(clip, want, str(dst))
        else:
            Path(dst).write_bytes(Path(clip).read_bytes())
        done += 1
        print(f"    -> {dst.name}", flush=True)

    print(f"\n  {done} wide(s) upgraded, {skipped} left alone.")
    if done and not a.dry_run:
        print(f"  Re-stitch: showrunner.py produce {a.series} --episode "
              f"{a.episode} --quality final --upscale --resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
