#!/usr/bin/env python3
"""
Render one shot several ways and score them.

TWO THINGS THIS ANSWERS

1. COVERAGE. Every shot in both films is a FIRST TAKE. A real production shoots
   a scene several times and picks; this pipeline renders once and accepts
   whatever comes back. Rendering the same shot on different seeds and choosing
   on measured identity is the single biggest gap in method, and it is pure GPU
   time -- exactly what an idle overnight card is for.

2. CAMERA MOVEMENT. Deep research returned ZERO surviving claims on whether WAN
   2.2 can execute a camera move without degrading identity. It is answerable
   empirically: render the same shot as static and as "slow dolly in", "slow
   pan", "handheld", and measure. If the model can move the camera, real
   parallax beats cropping a moving window out of a still frame. If it cannot,
   the post-crop stands and the question is closed rather than open.

Scored per variant:
    identity   CLIP against the character anchor, at four points in the take
    drift      identity at the end minus at the start
    motion     mean frame-to-frame change -- does a "dolly in" actually move?
    style      CLIP against "cel-shaded 2D animation, flat colour"

    shot_variants.py <series> --scene ep05_s03 --seeds 3
    shot_variants.py <series> --scene ep05_s03 --camera
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

# Prompt suffixes to test. "static" is the control and must stay first.
CAMERA_VARIANTS = [
    ("static", ""),
    ("dolly_in", " The camera slowly pushes in toward the subject."),
    ("pan_left", " The camera slowly pans to the left."),
    ("handheld", " Subtle handheld camera movement, gentle drift."),
    ("crane_down", " The camera slowly descends."),
]


def _motion(clip: str, fps: int = 8) -> float:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip,
                        "-vf", f"fps={fps}", f"{td}/f_%03d.png"], check=True)
        fr = []
        for f in sorted(Path(td).glob("f_*.png")):
            with Image.open(f) as im:
                fr.append(np.asarray(im.convert("L"), dtype=np.float32))
    if len(fr) < 2:
        return 0.0
    return float(np.mean([np.mean(np.abs(fr[i + 1] - fr[i]))
                          for i in range(len(fr) - 1)]))


def score(clip: str, anchor_vec) -> dict:
    dur = sr._get_video_duration(clip)
    ids = []
    with tempfile.TemporaryDirectory() as td:
        for frac in (0.08, 0.35, 0.62, 0.92):
            p = f"{td}/f{int(frac*100)}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                            f"{dur*frac:.2f}", "-i", clip, "-frames:v", "1", p],
                           check=True)
            with Image.open(p) as im:
                ids.append(float((vr._embed_images([im.convert("RGB").copy()])
                                  @ anchor_vec.T)[0][0]))
    return {"seconds": round(dur, 2), "identity": sum(ids) / len(ids),
            "min": min(ids), "drift": ids[-1] - ids[0], "motion": _motion(clip)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--scene", required=True)
    ap.add_argument("--seeds", type=int, default=0,
                    help="render N extra takes on different seeds")
    ap.add_argument("--camera", action="store_true",
                    help="test camera-movement prompt patterns")
    ap.add_argument("--steps", type=int, default=15)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ep_num = int(a.scene.split("_")[0].replace("ep", ""))
    ep = sr.load_json(sr.episode_path(a.series, ep_num))
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)

    res = sr.get_resolution_config("480p", "wan")
    mode = sr.classify_scene_type(scene)
    seed_img = sr.get_scene_seed_image(scene, a.series, None)
    base_prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    audio = None
    vo = Path("output") / a.series / f"ep{ep_num:02d}" / "audio" / f"{a.scene}.mp3"
    spoken = 0.0
    if mode == "s2v" and vo.exists():
        spoken = sr._get_video_duration(str(vo))
        padded = str(vo.with_name(f"{a.scene}_var.mp3"))
        sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
        audio = sr.copy_to_input(padded)
    want = (spoken + sr.S2V_LIVE_TAIL) if spoken else 5.0
    frames, extra, tail = sr.s2v_chunks_for_duration(want, fps=res.get("fps", 16)
                                                     if isinstance(res, dict) else 16,
                                                     floor_seconds=spoken)

    variants = ([(f"seed{i}", "") for i in range(a.seeds + 1)] if a.seeds
                else CAMERA_VARIANTS if a.camera else [("static", "")])

    who = scene["dialogue"][0]["character"] if scene.get("dialogue") else None
    ref_dir = sr.series_path(a.series) / "reference_images"
    anchor = vr._embed_images([Image.open(
        sr._find_ref(ref_dir, who, "char")).convert("RGB")]) if who else None

    rows = []
    for i, (name, suffix) in enumerate(variants):
        prefix = f"var_{a.scene}_{name}"
        existing = sr.find_latest_clip(prefix)
        if not existing:
            wf = sr.build_video_workflow(
                "wan", mode, base_prompt + suffix, 4000 + i * 911, prefix,
                frames, res, negative_prompt=neg, steps=a.steps,
                image_name=seed_img, audio_path=audio,
                extra_chunks=extra, last_chunk_frames=tail)
            print(f"  rendering {name} ...", flush=True)
            try:
                pid = sr.queue_prompt(wf)
                if not sr.poll_until_done(pid, max_wait=1800 * (1 + extra)):
                    print(f"    {name}: no output"); continue
            except Exception as e:                             # noqa: BLE001
                print(f"    {name}: {type(e).__name__}: {e}"); continue
            existing = sr.find_latest_clip(prefix)
        if not existing:
            continue
        s = score(existing, anchor) if anchor is not None else {"seconds": 0}
        s["variant"] = name
        s["clip"] = existing
        rows.append(s)

    print(f"\n  {a.scene}  ({mode}, {len(rows)} variants)")
    print(f"  {'variant':12} {'identity':>9} {'min':>7} {'drift':>7} {'motion':>8}")
    base_motion = rows[0]["motion"] if rows else 1.0
    for r in rows:
        rel = r["motion"] / base_motion if base_motion else 1.0
        print(f"  {r['variant']:12} {r['identity']:9.3f} {r['min']:7.3f} "
              f"{r['drift']:+7.3f} {r['motion']:8.3f}  ({rel:4.2f}x)")
    if rows:
        best = max(rows, key=lambda r: r["identity"])
        print(f"\n  best identity: {best['variant']}  ({best['identity']:.3f})")
        out = Path("/workspace/review/variants"); out.mkdir(parents=True, exist_ok=True)
        (out / f"{a.scene}.json").write_text(json.dumps(rows, indent=2, default=str))
        for r in rows:
            subprocess.run(["cp", r["clip"], str(out / f"{a.scene}_{r['variant']}.mp4")])
        print(f"  clips + scores in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
