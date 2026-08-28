#!/usr/bin/env python3
"""
Will S2V let a character DO something while they speak?

42 of 55 shots across every piece are a person standing still, talking. Only 13
describe any physical action and most of those are "turns to look". That is the
deepest remaining difference from studio animation: bodies do things there, and
here they do not.

It is two questions wearing one coat, and they need separating:

  WRITING   -- nearly every visual I wrote ends "Static camera. He speaks."
               If the prompts never ask for action, none will appear.
  CAPABILITY-- S2V drives a mouth from audio. Whether it will also walk a
               character across frame, or have them turn, kneel, raise a hand,
               is untested. It may ignore the instruction, or it may take it and
               lose the lip sync or the face.

Same line, same seed, same plate; only the action clause changes. Measured:

    identity   does the face survive the movement
    motion     did anything actually happen
    mouth      does the lip sync survive -- motion during speech vs after it,
               which is the same proxy used to catch the trailing-lips bug

A prompt that raises motion while holding identity AND keeping the mouth ratio
is a shot the pipeline can direct. One that raises motion by warping the face
is not.

    action_test.py <series> --scene ep05_s04
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

SEED = 8800

# ep11 rendered 7 shots with action written in, and the pattern was clear:
#
#   stands up 5.70   rises 5.59   walks 5.44   crouches 3.62   <- whole body
#   turns 2.97/2.56  lowers 2.25                               <- barely moves
#   (shots with no action asked for averaged 3.01)
#
# Whole-body verbs move a body. Small ones are ignored. The first version of
# this test used mostly small verbs on two shots and concluded movement was not
# possible, which was wrong.
ACTIONS = [
    ("still",     ""),
    ("walk",      " He walks slowly across the ground as he speaks."),
    ("stand_up",  " He stands up from the stone as he speaks."),
    ("crouch",    " He crouches down toward the ground as he speaks."),
    ("turn_away", " He turns his whole body away and back as he speaks."),
]


def _motion(clip: str, start: float, dur: float, region: str = "face") -> float:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}",
                        "-t", f"{dur:.2f}", "-i", clip, "-vf", "fps=8",
                        f"{td}/f_%03d.png"], check=True)
        fr = []
        for f in sorted(Path(td).glob("f_*.png")):
            a = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
            h, w = a.shape
            fr.append(a[int(h*0.15):int(h*0.75), int(w*0.25):int(w*0.75)]
                      if region == "face" else a)
    if len(fr) < 2:
        return 0.0
    return float(np.mean([np.abs(fr[i+1]-fr[i]).mean() for i in range(len(fr)-1)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--scene", required=True)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    who = scene["dialogue"][0]["character"]

    res = sr.get_resolution_config("480p", "wan")
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    base = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    vo = Path("output") / a.series / f"ep{ep_num:02d}" / "audio" / f"{a.scene}.mp3"
    spoken = sr._get_video_duration(str(vo))
    padded = str(vo.with_name(f"{a.scene}_act.mp3"))
    sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
    audio = sr.copy_to_input(padded)
    frames, extra, tail = sr.s2v_chunks_for_duration(
        spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)

    anchor = vr._embed_images([Image.open(sr._find_ref(
        sr.series_path(a.series) / "reference_images", who, "char")).convert("RGB")])

    rows = []
    for name, clause in ACTIONS:
        prefix = f"act_{a.scene}_{name}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "s2v", base + clause, SEED, prefix, frames, res,
                negative_prompt=neg, steps=a.steps, image_name=seed_img,
                audio_path=audio, extra_chunks=extra, last_chunk_frames=tail)
            print(f"  {name} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800 * (1 + extra)):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        dur = sr._get_video_duration(clip)
        ids = []
        with tempfile.TemporaryDirectory() as td:
            for frac in (0.2, 0.5, 0.8):
                p = f"{td}/f{int(frac*100)}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                f"{dur*frac:.2f}", "-i", clip, "-frames:v", "1", p],
                               check=True)
                with Image.open(p) as im:
                    ids.append(float((vr._embed_images([im.convert("RGB").copy()])
                                      @ anchor.T)[0][0]))
        whole = _motion(clip, 0.4, min(4.0, dur - 0.8), region="whole")
        sp = _motion(clip, 0.5, min(2.5, spoken - 0.9))
        si = _motion(clip, spoken + 0.15, max(0.5, min(1.5, dur - spoken - 0.3)))
        rows.append({"name": name, "identity": sum(ids)/3, "min": min(ids),
                     "motion": whole, "mouth": (si/sp if sp else 0)})

    if not rows:
        print("  nothing rendered"); return 1
    base_row = rows[0]
    print(f"\n  {a.scene} — {who}, seed {SEED} fixed, only the action clause varies")
    print(f"  {'action':10} {'identity':>9} {'min':>7} {'motion':>8} {'mouth':>7}   verdict")
    for r in rows:
        rel = r["motion"] / base_row["motion"] if base_row["motion"] else 1
        d = r["identity"] - base_row["identity"]
        if r["name"] == "still":
            v = "reference"
        elif rel < 1.15:
            v = "nothing happened"
        elif d < -0.030:
            v = "moved, but the face went"
        elif r["mouth"] > 1.0:
            v = "moved, lip sync suspect"
        else:
            v = f"USABLE — {rel:.2f}x motion, identity {d:+.3f}"
        print(f"  {r['name']:10} {r['identity']:9.3f} {r['min']:7.3f} "
              f"{r['motion']:8.3f} {r['mouth']:7.2f}   {v}")
    out = Path("/workspace/review/action"); out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.scene}.json").write_text(json.dumps(rows, indent=2))
    print(f"\n  scores in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
