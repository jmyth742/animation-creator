#!/usr/bin/env python3
"""
Find the lever that actually improves lip sync.

Resolution is not it -- 720p cost 2.75x and came back smoother, not sharper.
The remaining candidates are how much of the frame the mouth occupies, and how
much sampling the S2V model gets. Both are tested here on the same line.

    python scripts/lipsync_test.py <series> --episode 2 --scene ep02_s03
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

OUT = Path("/workspace/review/lipsync")

# label, steps, prompt prefix that changes how much frame the face occupies
VARIANTS = [
    ("A_std25",      25, ""),
    ("B_std40",      40, ""),
    ("C_tight25",    25, "Extreme close-up filling the frame with the face from brow to chin, "
                         "lips and teeth clearly visible, "),
    ("D_tight40",    40, "Extreme close-up filling the frame with the face from brow to chin, "
                         "lips and teeth clearly visible, "),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=2)
    ap.add_argument("--scene", required=True)
    a = ap.parse_args()
    sr.set_current_series(a.series)

    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    if not scene.get("dialogue"):
        sys.exit(f"{a.scene} has no dialogue")

    ep_out = sr.OUTPUT_DIR / a.series / f"ep{a.episode:02d}"
    audio_src = ep_out / "audio" / f"{scene['id']}.mp3"
    if not audio_src.exists():
        sys.exit(f"no audio at {audio_src}")
    audio = sr.copy_to_input(str(audio_src))
    seed_image = sr.get_scene_seed_image(scene, a.series, None)
    base_prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    rc = dict(sr.get_resolution_config("480p", "wan")); rc["width"], rc["height"] = 832, 480
    OUT.mkdir(parents=True, exist_ok=True)
    frames = min(sr.MAX_FRAMES, max(sr.MIN_FRAMES, int(sr._get_video_duration(str(audio_src)) * 16) | 1))

    results = []
    for label, steps, prefix in VARIANTS:
        prompt = prefix + base_prompt
        prefix_id = f"ls_{a.scene}_{label}"
        wf = sr.build_video_workflow("wan", "s2v", prompt, seed=13579, clip_prefix=prefix_id,
                                     frames=frames, res_config=rc, negative_prompt=neg,
                                     steps=steps, image_name=seed_image,
                                     audio_path=audio, optimization="none")
        print(f"  {label}: steps={steps} frames={frames} tight={'yes' if prefix else 'no'}", flush=True)
        t0 = time.time()
        try:
            ok = sr.poll_until_done(sr.queue_prompt(wf))
        except Exception as e:
            print(f"    ERROR {e}"); results.append((label, None, 0)); continue
        dt = time.time() - t0
        got = sr.find_latest_clip(prefix_id) if ok else None
        if got:
            dst = OUT / f"{a.scene}_{label}.mp4"
            shutil.copy2(got, dst); print(f"    {dt:.0f}s -> {dst.name}")
            results.append((label, dst, dt))
        else:
            print("    FAILED"); results.append((label, None, dt))

    # mouth strip per variant: 6 moments through the line, cropped to the lower face
    for label, path, _ in results:
        if not path:
            continue
        d = sr._get_video_duration(str(path)) or 3.0
        tiles = []
        for k in range(1, 7):
            t = d * (0.12 + 0.13 * k)
            png = OUT / f"{a.scene}_{label}_m{k}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path),
                            "-frames:v", "1", "-vf",
                            "crop=iw*0.5:ih*0.3:iw*0.25:ih*0.45,scale=240:-1", str(png)], timeout=60)
            if png.exists():
                tiles.append(png)
        if tiles:
            ins, filt = [], ""
            for i, p in enumerate(tiles):
                ins += ["-i", str(p)]; filt += f"[{i}:v]scale=240:144[v{i}];"
            filt += "".join(f"[v{i}]" for i in range(len(tiles))) + f"hstack={len(tiles)}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", filt,
                            str(OUT / f"{a.scene}_{label}_MOUTH.png")], timeout=120)
    print("\n  timings:")
    for label, path, dt in results:
        print(f"    {label:12} {dt:6.0f}s  {'ok' if path else 'FAILED'}")
    (OUT / f"{a.scene}_lipsync.json").write_text(json.dumps(
        [{"variant": l, "seconds": round(d), "ok": bool(p)} for l, p, d in results], indent=2))


if __name__ == "__main__":
    main()
