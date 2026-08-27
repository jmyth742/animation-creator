#!/usr/bin/env python3
"""
Does S2V actually need 15 sampling steps?

The number was inherited and never measured. It matters more than any other
single setting because of what S2V cannot do: the LightX2V distill LoRAs cut
T2V and I2V from ~18 steps to 8 at cfg 1.0 -- about 6x faster AND measurably
better -- but they are trained for the T2V/I2V checkpoints and S2V is a
different model family, so dialogue shots run full steps with no distillation.

Dialogue is roughly 80% of every piece, and a step costs 56.8 seconds:

    9/15  [08:30<05:40, 56.78s/it]

So 15 steps is ~14 minutes per chunk, and a chained two-chunk take is two of
those. If 10 steps holds identity and style, that is a third off the render
time of four fifths of the film, permanently and for every future episode.

Fixed seed across every variant -- steps is the only thing being changed.
Scored on identity against the anchor and cel style via verify_render's own
scorer, plus the wall-clock each one actually took.

    steps_sweep.py <series> --scene ep05_s03
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

STEPS = [6, 8, 10, 12, 15]
SEED = 7700


def _cel(img: Image.Image) -> float:
    sv = vr._embed_texts(vr._STYLE_OPTIONS)
    sims = (vr._embed_images([img]) @ sv.T).mean(dim=0)
    return float((sims * 100).softmax(dim=-1)[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--scene", required=True)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    who = scene["dialogue"][0]["character"]

    res = sr.get_resolution_config("480p", "wan")
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    vo = Path("output") / a.series / f"ep{ep_num:02d}" / "audio" / f"{a.scene}.mp3"
    spoken = sr._get_video_duration(str(vo))
    padded = str(vo.with_name(f"{a.scene}_steps.mp3"))
    sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
    audio = sr.copy_to_input(padded)
    # ONE chunk only: this is about cost per step, and a single sample isolates
    # it from the extra context a chained chunk carries.
    frames = sr.frames_for_duration(min(spoken, 4.6), fps=16)

    anchor = vr._embed_images([Image.open(sr._find_ref(
        sr.series_path(a.series) / "reference_images", who, "char")).convert("RGB")])

    rows = []
    for st in STEPS:
        prefix = f"steps_{a.scene}_{st:02d}"
        clip = sr.find_latest_clip(prefix)
        elapsed = None
        if not clip:
            wf = sr.build_video_workflow(
                "wan", "s2v", prompt, SEED, prefix, frames, res,
                negative_prompt=neg, steps=st, image_name=seed_img,
                audio_path=audio)
            print(f"  {st} steps ...", flush=True)
            t0 = time.time()
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=2400):
                    print("    no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}"); continue
            elapsed = time.time() - t0
            clip = sr.find_latest_clip(prefix)
        if not clip:
            continue
        dur = sr._get_video_duration(clip)
        ids, cels = [], []
        with tempfile.TemporaryDirectory() as td:
            for frac in (0.2, 0.5, 0.8):
                p = f"{td}/f{int(frac*100)}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                f"{dur*frac:.2f}", "-i", clip, "-frames:v", "1", p],
                               check=True)
                with Image.open(p) as im:
                    rgb = im.convert("RGB").copy()
                ids.append(float((vr._embed_images([rgb]) @ anchor.T)[0][0]))
                cels.append(_cel(rgb))
        rows.append({"steps": st, "identity": sum(ids)/3, "cel": sum(cels)/3,
                     "seconds": elapsed})

    if not rows:
        print("  nothing rendered"); return 1
    ref = max(rows, key=lambda r: r["steps"])
    print(f"\n  {a.scene} — {frames} frames, seed {SEED} fixed")
    print(f"  {'steps':>6} {'identity':>9} {'cel':>7} {'render':>9}   vs {ref['steps']} steps")
    for r in rows:
        t = f"{r['seconds']/60:.1f} min" if r["seconds"] else "cached"
        d = r["identity"] - ref["identity"]
        save = (1 - r["steps"] / ref["steps"]) * 100
        v = ("reference" if r["steps"] == ref["steps"] else
             f"identity {d:+.3f}, cel {r['cel']:.3f} — {save:.0f}% cheaper")
        print(f"  {r['steps']:6} {r['identity']:9.3f} {r['cel']:7.3f} {t:>9}   {v}")
    ok = [r for r in rows if r["steps"] < ref["steps"]
          and r["identity"] >= ref["identity"] - 0.010 and r["cel"] >= 0.95]
    print()
    if ok:
        best = min(ok, key=lambda r: r["steps"])
        print(f"  {best['steps']} steps holds identity within 0.010 and keeps the "
              f"style — {(1-best['steps']/ref['steps'])*100:.0f}% off every "
              f"dialogue render")
    else:
        print("  no step count below the reference held up; 15 is earned")
    out = Path("/workspace/review/steps"); out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.scene}.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
