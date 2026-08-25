#!/usr/bin/env python3
"""
Render one scene under an arbitrary list of settings and compare them.

Purpose-built A/B rig: same scene, same seed, one variable at a time, with
wall-clock timing and a side-by-side contact sheet. Unlike quality_matrix.py
(which is organised around a character LoRA) this takes a free-form variant
list, so it suits questions like "does 720p fit?" and "do more steps recover
prompt adherence?".

    python scripts/shot_test.py <series> --scene ep01_s02 --test resolution
    python scripts/shot_test.py <series> --scene ep01_s02 --test steps
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

OUT = Path("/workspace/review/shot_tests")

TESTS = {
    # Does native 720p fit in 24GB, and is it worth the time?
    "resolution": [("r480_832x480", 8, "480p"), ("r720_1280x720", 8, "720p")],
    # Distilled sampling renders "towering storm waves" as pleasant surf.
    # Do more steps recover prompt adherence, or is it inherent?
    "steps":      [("s04", 4, "480p"), ("s08", 8, "480p"),
                   ("s12", 12, "480p"), ("s16", 16, "480p")],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--test", required=True, choices=sorted(TESTS))
    ap.add_argument("--frames", type=int, default=49)
    a = ap.parse_args()
    sr.set_current_series(a.series)

    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    scene = next((s for s in ep["scenes"] if s["id"] == a.scene), None)
    if not scene:
        sys.exit(f"no scene {a.scene}")

    OUT.mkdir(parents=True, exist_ok=True)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    # Respect the real routing, including speech-to-video: a dialogue scene
    # tested as plain i2v would not exercise lip sync at all.
    seed_image = sr.get_scene_seed_image(scene, a.series, None)
    stype = sr.classify_scene_type(scene)
    audio_path = None
    if stype == "s2v" and scene.get("dialogue"):
        ep_out = sr.OUTPUT_DIR / a.series / f"ep{a.episode:02d}"
        cand = ep_out / "audio" / f"{scene['id']}.mp3"
        if cand.exists():
            audio_path = sr.copy_to_input(str(cand))
            mode = "s2v"
        else:
            print(f"  no audio for {scene['id']} — falling back from s2v")
            mode = "i2v" if seed_image else "t2v"
    else:
        mode = "i2v" if seed_image else "t2v"
    print(f"  {a.scene}: mode={mode} test={a.test}")

    results = []
    for label, steps, res in TESTS[a.test]:
        rc = dict(sr.get_resolution_config(res, "wan"))
        if res == "480p":
            rc["width"], rc["height"] = 832, 480
        # No distill LoRA for the S2V checkpoint — wrong model family.
        loras = ([] if mode == "s2v" else
                 list(sr.LIGHTNING["i2v"] if mode == "i2v" else sr.LIGHTNING["t2v"]))
        prefix = f"st_{a.scene}_{a.test}_{label}"
        wf = sr.build_video_workflow("wan", mode, prompt, seed=90210, clip_prefix=prefix,
                                     frames=a.frames, res_config=rc, negative_prompt=neg,
                                     steps=steps, loras=loras, image_name=seed_image,
                                     audio_path=audio_path, optimization="none")
        if mode != "s2v":
            sr.apply_lightning(wf, steps=steps)
        print(f"    {label}: {rc['width']}x{rc['height']} steps={steps} ...", flush=True)
        t0 = time.time()
        try:
            ok = sr.poll_until_done(sr.queue_prompt(wf))
        except Exception as e:
            print(f"      ERROR: {e}"); results.append((label, None, 0)); continue
        dt = time.time() - t0
        got = sr.find_latest_clip(prefix) if ok else None
        if got:
            dst = OUT / f"{a.scene}_{a.test}_{label}.mp4"
            shutil.copy2(got, dst)
            print(f"      {dt:.0f}s -> {dst.name}")
            results.append((label, dst, dt))
        else:
            print(f"      FAILED after {dt:.0f}s  (720p on 24GB is the likely OOM)")
            results.append((label, None, dt))

    good = [(l, p) for l, p, _ in results if p]
    if good:
        pngs = []
        for label, path in good:
            d = sr._get_video_duration(str(path)) or 3.0
            png = OUT / f"{a.scene}_{a.test}_{label}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d/2:.2f}", "-i", str(path),
                            "-frames:v", "1", "-vf", "scale=480:-1", str(png)], timeout=60)
            if png.exists(): pngs.append(png)
        if pngs:
            ins, filt = [], ""
            for i, p in enumerate(pngs):
                ins += ["-i", str(p)]; filt += f"[{i}:v]scale=480:277[v{i}];"
            filt += "".join(f"[v{i}]" for i in range(len(pngs))) + f"hstack={len(pngs)}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", filt,
                            str(OUT / f"{a.scene}_{a.test}_compare.png")], timeout=120)
    print("\n  timings:")
    for label, path, dt in results:
        print(f"    {label:16} {dt:6.0f}s  {'ok' if path else 'FAILED'}")
    (OUT / f"{a.scene}_{a.test}.json").write_text(json.dumps(
        [{"variant": l, "seconds": round(d), "ok": bool(p)} for l, p, d in results], indent=2))


if __name__ == "__main__":
    main()
