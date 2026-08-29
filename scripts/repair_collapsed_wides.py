#!/usr/bin/env python3
"""
Re-render the shots that were written as wides and came back as faces.

Eleven shots across ep05-ep11 were authored "the warrior small among the
stones" and rendered head-and-shoulders. Measured: p(wide) 0.048 against 0.937
for the same kind of shot with no line in it. The cause is not the prompt or
the plate -- both were right -- it is that a dialogue shot goes through the
speech checkpoint, which is a talking-head model and pulls to the face.

Tested on three of them: seeded from a full-body plate and rendered SILENT,
two went to 0.953 and 0.846. The third stayed tight because its plate was a
three-quarter framing, not because it had a line. So the fix is two conditions,
not one: silent AND seeded wide enough.

This renders the silent version alongside the original. It swaps nothing --
the voice still has to be laid over in the edit, and whether a given shot is
better as a wide with voiceover or a close with lip sync is a directorial
call, not a score.

    repair_collapsed_wides.py <series> [--shots ep07_s01,...]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import wide_dialogue_test as wd                                # noqa: E402

OUT = Path("/workspace/review/repaired_wides")
SEED = 8800
WIDE_ENOUGH = ("full_body", "three_quarter", "wide_figure", "walking_away")



# The staged library has no real wide plate for anybody -- every framing name
# resolves to the same head-and-shoulders portrait. The generated library does.
GEN = {"ruined_ireland": "ruin", "tir_na_nog": "valley",
       "farewell_cliff": "cliff", "sunlight_path": "valley"}


def generated_wide(series, location, who):
    """A real wide plate for this place and person, if one was generated."""
    stem = GEN.get(location)
    if not stem:
        return None
    p = (sr.series_path(series) / "sets" / "_generated"
         / f"gen__{stem}_wide_{who}.png")
    return p if p.exists() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--shots", default=None)
    ap.add_argument("--force", action="store_true",
                    help="re-render even if a take exists")
    ap.add_argument("--generated", action="store_true",
                    help="seed from the generated wide plates")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    res = sr.get_resolution_config("480p", "wan")

    ids = (a.shots.split(",") if a.shots
           else json.loads(Path("/tmp/wide_dialogue.json").read_text()))
    rows = []
    for sid in ids:
        ep_num = int(sid.split("_")[0].replace("ep", ""))
        ep = sr.load_json(sr.episode_path(a.series, ep_num))
        scene = next((s for s in ep["scenes"] if s["id"] == sid), None)
        if not scene:
            print(f"  {sid}: not found"); continue
        seed_img = sr.get_scene_seed_image(scene, a.series, None)
        if a.generated:
            who = (scene.get("dialogue") or [{}])[0].get("character") \
                  or (scene.get("characters") or [None])[0]
            g = generated_wide(a.series, scene.get("location", ""), who)
            if g:
                seed_img = sr.copy_to_input(str(g))
                print(f"  {sid}: seeding from generated plate {g.name}")
            else:
                print(f"  {sid}: no generated wide for "
                      f"{scene.get('location')}/{who}; skipping")
                continue
        elif not any(k in str(seed_img) for k in WIDE_ENOUGH):
            print(f"  {sid}: seed '{Path(str(seed_img)).name}' is too tight — "
                  f"a wide needs a full-body plate; skipping rather than "
                  f"rendering something that will collapse anyway")
            continue
        prefix = f"rw_{sid}"
        prefix = f"rwg_{sid}" if a.generated else prefix
        clip = None if a.force else sr.find_latest_clip(prefix)
        if not clip:
            prompt = sr.build_scene_prompt(scene, bible)
            neg = sr.build_negative_prompt(scene)
            wf = sr.build_video_workflow(
                "wan", "i2v", prompt, SEED, prefix, sr.MAX_FRAMES, res,
                negative_prompt=neg, steps=8, image_name=seed_img)
            print(f"  {sid}: rendering silent wide ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            prefix = f"rwg_{sid}" if a.generated else prefix
        clip = None if a.force else sr.find_latest_clip(prefix)
        if not clip:
            continue
        old = sr.find_latest_clip(sid)
        p_new, lab_new = wd.framing(clip)
        p_old, lab_old = wd.framing(old) if old else (0.0, "?")
        subprocess.run(["cp", clip, str(OUT / f"{sid}_wide.mp4")])
        rows.append({"shot": sid, "p_wide_before": p_old, "p_wide_after": p_new,
                     "reads_as": lab_new, "clip": str(OUT / f"{sid}_wide.mp4")})
        print(f"    {sid:10} p(wide) {p_old:.3f} -> {p_new:.3f}  ({lab_new})",
              flush=True)

    (OUT / "results.json").write_text(json.dumps(rows, indent=2))
    fixed = sum(1 for r in rows if r["p_wide_after"] > 0.5)
    print(f"\n  {fixed} of {len(rows)} now read as wides. Nothing swapped; the "
          f"voice\n  still has to be laid over these in the edit.")
    print(f"  clips in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
