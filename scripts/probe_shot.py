#!/usr/bin/env python3
"""
Render ONE shot and show it, before committing to a whole episode.

Every serious problem in this project was found by looking at a picture, never
by a check that passed: a heroine missing from her own entrance, six locations
that were all the same cliff, dialogue close-ups in modern interiors, a shot
double-exposed over the previous one. Each cost a 2.5-hour render to discover
and could have been seen in ten minutes.

preflight.py verifies configuration. This verifies INTENT -- that what comes
out resembles what the script asked for. Run both before any episode.

    python scripts/probe_shot.py <series> --episode 4 --scene ep04_s08
    python scripts/probe_shot.py <series> --episode 4 --auto   # picks 3 shots
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

OUT = Path("/workspace/review/probe")


def pick_auto(ep):
    """One dialogue close-up, one character wide, one establishing — the three
    shapes that have failed differently in the past."""
    scenes = ep["scenes"]
    dlg = next((s for s in scenes if s.get("dialogue")), None)
    wide = next((s for s in scenes if s.get("characters")
                 and "wide" in s["visual"].lower()), None)
    est = next((s for s in scenes if not s.get("characters")), None)
    return [s for s in (dlg, wide, est) if s]


def render(series, episode, scene, bible, steps):
    sid = scene["id"]
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    rc = dict(sr.get_resolution_config("480p", "wan")); rc["width"], rc["height"] = 832, 480
    seed_image = sr.get_scene_seed_image(scene, series, None)
    stype = sr.classify_scene_type(scene)
    audio = None
    mode = "t2v"
    if stype == "s2v" and scene.get("dialogue"):
        f = sr.OUTPUT_DIR / series / f"ep{episode:02d}" / "audio" / f"{sid}.mp3"
        if f.exists():
            audio = sr.copy_to_input(str(f)); mode = "s2v"
    if mode != "s2v":
        mode = "i2v" if seed_image else "t2v"

    print(f"\n  {sid}  mode={mode}  seed={Path(seed_image).name if seed_image else 'none'}")
    print(f"  PROMPT: {prompt[:220]}")
    frames = sr.CLIP_LENGTHS[scene.get("clip_length", "medium")]["frames"]
    wf = sr.build_video_workflow("wan", mode, prompt, seed=4242, clip_prefix=f"probe_{sid}",
                                 frames=frames, res_config=rc, negative_prompt=neg,
                                 steps=steps, image_name=seed_image, audio_path=audio,
                                 optimization="none")
    t0 = time.time()
    ok = sr.poll_until_done(sr.queue_prompt(wf))
    got = sr.find_latest_clip(f"probe_{sid}") if ok else None
    if not got:
        print(f"    FAILED after {time.time()-t0:.0f}s"); return None
    dst = OUT / f"{sid}.mp4"
    shutil.copy2(got, dst)
    png = OUT / f"{sid}.png"
    d = sr._get_video_duration(str(dst)) or 2.0
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d/2:.2f}", "-i", str(dst),
                    "-frames:v", "1", str(png)], timeout=60)
    print(f"    {time.time()-t0:.0f}s -> {png.name}")
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--scene"); ap.add_argument("--auto", action="store_true")
    ap.add_argument("--steps", type=int, default=20)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    OUT.mkdir(parents=True, exist_ok=True)

    if a.auto:
        scenes = pick_auto(ep)
    elif a.scene:
        scenes = [next(s for s in ep["scenes"] if s["id"] == a.scene)]
    else:
        sys.exit("give --scene or --auto")

    pngs = [p for p in (render(a.series, a.episode, s, bible, a.steps) for s in scenes) if p]
    if len(pngs) > 1:
        ins, filt = [], ""
        for i, p in enumerate(pngs):
            ins += ["-i", str(p)]; filt += f"[{i}:v]scale=440:254[v{i}];"
        filt += "".join(f"[v{i}]" for i in range(len(pngs))) + f"hstack={len(pngs)}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", filt,
                        str(OUT / f"ep{a.episode:02d}_probe.png")], timeout=120)
        print(f"\n  -> {OUT}/ep{a.episode:02d}_probe.png")
    print("\n  LOOK AT IT before rendering the episode.")


if __name__ == "__main__":
    main()
