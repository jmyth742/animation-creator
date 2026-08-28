#!/usr/bin/env python3
"""
Test the sampler settings the audit says are wrong.

Two authorities disagree and neither matches what this pipeline runs:

    reference repo   shift 3   40 steps  cfg 4.5
    ComfyUI template shift 8   20 steps  cfg 6.0   (or 4 steps @ cfg 1.0 + LoRA)
    this pipeline    shift 12  15 steps  cfg 5.0   <- in neither

ComfyUI is the execution environment, so its numbers are the ones to test
against. Shift is the one most likely to matter: it warps the noise schedule,
and 12 against a documented 8 is a 1.5x difference applied to every frame of
every shot.

Fixed seed, fixed prompt, one variable at a time. Scored on identity, cel style
and motion -- motion included because the whole point of the current work is
that things should move, and a schedule change could quietly cost that.

    sampler_ab.py <series> --scene ep11_s02
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

SEED = 11200
# name, shift, steps, cfg
VARIANTS = [
    ("current",      12.0, 15, 5.0),   # what we ship
    ("comfy_shift",   8.0, 15, 5.0),   # only shift changes
    ("comfy_full",    8.0, 20, 6.0),   # ComfyUI's documented non-distilled pair
    ("repo_shift",    3.0, 15, 5.0),   # the reference repo's shift
    ("comfy_shift10", 8.0, 10, 5.0),   # shift fix + the 10 steps already proven
]


def _cel(img: Image.Image) -> float:
    sv = vr._embed_texts(vr._STYLE_OPTIONS)
    return float(((vr._embed_images([img]) @ sv.T).mean(dim=0) * 100)
                 .softmax(dim=-1)[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--scene", default="ep11_s02")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    sc = next(s for s in ep["scenes"] if s["id"] == a.scene)
    who = sc["dialogue"][0]["character"]
    res = dict(sr.get_resolution_config("480p", "wan"))
    seed_img = sr.get_scene_seed_image(sc, a.series, None)
    prompt = sr.build_scene_prompt(sc, bible, image_conditioned=bool(seed_img))
    neg = sr.build_negative_prompt(sc)
    vo = Path("output") / a.series / f"ep{ep_num:02d}" / "audio" / f"{a.scene}.mp3"
    spoken = sr._get_video_duration(str(vo))
    padded = str(vo.with_name(f"{a.scene}_samp.mp3"))
    sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
    audio = sr.copy_to_input(padded)
    frames, extra, tail = sr.s2v_chunks_for_duration(
        spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
    anchor = vr._embed_images([Image.open(sr._find_ref(
        sr.series_path(a.series) / "reference_images", who, "char")).convert("RGB")])

    rows, skipped = [], []
    for name, shift, steps, cfg in VARIANTS:
        prefix = f"samp_{a.scene}_{name}"
        clip = sr.find_latest_clip(prefix)
        if not clip:
            r = dict(res); r["shift"] = shift
            wf = sr.build_video_workflow(
                "wan", "s2v", prompt, SEED, prefix, frames, r,
                negative_prompt=neg, steps=steps, image_name=seed_img,
                audio_path=audio, extra_chunks=extra, last_chunk_frames=tail)
            # cfg is set from the model config; override it on every sampler.
            for n in wf.values():
                if n.get("class_type") in ("KSampler", "KSamplerAdvanced"):
                    n["inputs"]["cfg"] = cfg
            print(f"  {name}: shift {shift}, {steps} steps, cfg {cfg} ...",
                  flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=2400 * (1 + extra)):
                    print("    no output"); skipped.append((name, "no output"))
                    continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {type(e).__name__}: {e}")
                skipped.append((name, type(e).__name__)); continue
            clip = sr.find_latest_clip(prefix)
        if not clip:
            skipped.append((name, "no clip found")); continue
        d = sr._get_video_duration(clip)
        ids, cels = [], []
        with tempfile.TemporaryDirectory() as td:
            for f in (0.25, 0.5, 0.75):
                p = f"{td}/x.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                f"{d*f:.2f}", "-i", clip, "-frames:v", "1", p],
                               check=True)
                with Image.open(p) as im:
                    rgb = im.convert("RGB").copy()
                ids.append(float((vr._embed_images([rgb]) @ anchor.T)[0][0]))
                cels.append(_cel(rgb))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                            "fps=6", f"{td}/m_%03d.png"], check=True)
            fr = [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
                  for f in sorted(Path(td).glob("m_*.png"))]
        mo = float(np.mean([np.abs(fr[i+1]-fr[i]).mean()
                            for i in range(len(fr)-1)])) if len(fr) > 1 else 0
        rows.append({"name": name, "shift": shift, "steps": steps, "cfg": cfg,
                     "identity": sum(ids)/3, "cel": sum(cels)/3, "motion": mo})
        print(f"    identity {rows[-1]['identity']:.3f}  cel {rows[-1]['cel']:.3f}"
              f"  motion {mo:.3f}", flush=True)

    if skipped:
        print(f"\n  {len(skipped)} variant(s) did NOT render:")
        for n, why in skipped:
            print(f"    {n:14} {why}")
    if not rows:
        print("  nothing rendered"); return 1
    # base must be the shipped configuration, by name. Taking rows[0] meant
    # that if "current" failed -- as it did once today, on a disk quota error
    # -- the baseline silently became shift 8 and every delta was measured
    # against the wrong reference, in a table that looked complete.
    base = next((r for r in rows if r["name"] == VARIANTS[0][0]), None)
    if base is None:
        print(f"\n  ABORT: the baseline variant '{VARIANTS[0][0]}' did not "
              f"render, so there is nothing to compare against. Deltas from "
              f"any other variant would be meaningless.")
        return 1
    print(f"\n  {a.scene}, seed {SEED} fixed")
    print(f"  {'variant':14} {'shift':>6} {'steps':>6} {'cfg':>5} "
          f"{'identity':>9} {'cel':>7} {'motion':>8}")
    for r in rows:
        print(f"  {r['name']:14} {r['shift']:6.1f} {r['steps']:6} {r['cfg']:5.1f} "
              f"{r['identity']:9.3f} {r['cel']:7.3f} {r['motion']:8.3f}")
    print()
    for r in rows[1:]:
        print(f"  {r['name']:14} vs current: identity {r['identity']-base['identity']:+.3f}"
              f"   cel {r['cel']-base['cel']:+.3f}"
              f"   motion {r['motion']/base['motion']:.2f}x")
    out = Path("/workspace/review/sampler_ab"); out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.scene}.json").write_text(json.dumps(rows, indent=2))
    for r in rows:
        c = sr.find_latest_clip(f"samp_{a.scene}_{r['name']}")
        if c:
            subprocess.run(["cp", c, str(out / f"{r['name']}.mp4")])
    print(f"\n  clips in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
