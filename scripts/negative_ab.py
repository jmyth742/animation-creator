#!/usr/bin/env python3
"""
Does fixing the negative prompt make a shot move?

The walk test moved (motion 12.1) and ep11's shots did not (2.2-5.7). Same
model, same day. The difference was the negative prompt: walk_test.py had one
written inline that contained "static, frozen, still image, no motion,
motionless", while the episodes ran the pipeline's hand-built list, which
contained six motion-SUPPRESSING terms and no anti-static term at all.

That is a hypothesis, not a finding, until the same shot is rendered both ways.
So: take shots that measurably failed to move, render each with the OLD
negative and the NEW one, hold everything else fixed, and measure.

    negative_ab.py <series> --shots ep11_s03,ep11_s04
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

# The list as it stood before the audit, reproduced exactly.
OLD_NEG = ("low quality, blurry, distorted, deformed, ugly, watermark, "
           "text overlay, oversaturated, smeared, melting, warped anatomy, "
           "extra fingers, photorealistic, live action, photograph, 3d render, "
           "cgi, computer generated, smooth plastic skin, video game cutscene, "
           "unreal engine, realistic rendering, green skin, tinted skin, "
           "monster, ogre, orc, fast movement, shaky camera, motion blur, "
           "erratic motion, camera shake, blurry faces, extreme camera "
           "movement, multiple people merging, face distortion")


def motion(clip: str) -> tuple[float, float]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vf",
                        "fps=6", f"{td}/f_%03d.png"], check=True)
        fr = [np.asarray(Image.open(f).convert("L"), dtype=np.float32)
              for f in sorted(Path(td).glob("f_*.png"))]
    if len(fr) < 2:
        return 0.0, 0.0
    m = float(np.mean([np.abs(fr[i+1]-fr[i]).mean() for i in range(len(fr)-1)]))
    return m, float(np.abs(fr[-1] - fr[0]).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--shots", required=True)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    res = sr.get_resolution_config("480p", "wan")
    rows = []
    for sid in a.shots.split(","):
        sid = sid.strip()
        ep_num = int(sid.split("_")[0].replace("ep", ""))
        ep = sr.load_json(sr.episode_path(a.series, ep_num))
        sc = next(s for s in ep["scenes"] if s["id"] == sid)
        who = sc["dialogue"][0]["character"] if sc.get("dialogue") else None
        seed_img = sr.get_scene_seed_image(sc, a.series, None)
        prompt = sr.build_scene_prompt(sc, bible)
        vo = (Path("output") / a.series / f"ep{ep_num:02d}" / "audio"
              / f"{sid}.mp3")
        if not vo.exists():
            print(f"  {sid}: no audio"); continue
        spoken = sr._get_video_duration(str(vo))
        padded = str(vo.with_name(f"{sid}_ab.mp3"))
        sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
        audio = sr.copy_to_input(padded)
        frames, extra, tail = sr.s2v_chunks_for_duration(
            spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
        anchor = vr._embed_images([Image.open(sr._find_ref(
            sr.series_path(a.series) / "reference_images", who, "char")
        ).convert("RGB")]) if who else None

        for label, neg in (("old", OLD_NEG),
                           ("new", sr.build_negative_prompt(sc))):
            prefix = f"ab_{sid}_{label}"
            clip = sr.find_latest_clip(prefix)
            if not clip:
                wf = sr.build_video_workflow(
                    "wan", "s2v", prompt, 9900, prefix, frames, res,
                    negative_prompt=neg, steps=a.steps, image_name=seed_img,
                    audio_path=audio, extra_chunks=extra,
                    last_chunk_frames=tail)
                print(f"  {sid} [{label} negative] ...", flush=True)
                try:
                    pid = sr.queue_prompt(wf)
                    if not sr.poll_until_done(pid, max_wait=1800 * (1 + extra)):
                        print("    no output"); continue
                except Exception as e:                         # noqa: BLE001
                    print(f"    {type(e).__name__}: {e}"); continue
                clip = sr.find_latest_clip(prefix)
            if not clip:
                continue
            m, t = motion(clip)
            idn = 0.0
            if anchor is not None:
                d = sr._get_video_duration(clip)
                with tempfile.TemporaryDirectory() as td:
                    p = f"{td}/x.png"
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                                    f"{d*0.5:.2f}", "-i", clip, "-frames:v",
                                    "1", p], check=True)
                    with Image.open(p) as im:
                        idn = float((vr._embed_images(
                            [im.convert("RGB").copy()]) @ anchor.T)[0][0])
            rows.append({"shot": sid, "negative": label, "motion": m,
                         "travel": t, "identity": idn})
            print(f"    motion {m:6.3f}  travel {t:6.2f}  identity {idn:.3f}",
                  flush=True)

    print(f"\n  {'shot':11} {'negative':>9} {'motion':>8} {'travel':>8} {'identity':>9}")
    for r in rows:
        print(f"  {r['shot']:11} {r['negative']:>9} {r['motion']:8.3f} "
              f"{r['travel']:8.2f} {r['identity']:9.3f}")
    by = {}
    for r in rows:
        by.setdefault(r["shot"], {})[r["negative"]] = r
    print()
    for sid, d in by.items():
        if "old" in d and "new" in d:
            dm = d["new"]["motion"] / d["old"]["motion"] if d["old"]["motion"] else 0
            print(f"  {sid}: motion {dm:.2f}x, identity "
                  f"{d['new']['identity'] - d['old']['identity']:+.3f}")
    out = Path("/workspace/review/negative_ab")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=2))
    for r in rows:
        c = sr.find_latest_clip(f"ab_{r['shot']}_{r['negative']}")
        if c:
            subprocess.run(["cp", c, str(out / f"{r['shot']}_{r['negative']}.mp4")])
    print(f"\n  clips in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
