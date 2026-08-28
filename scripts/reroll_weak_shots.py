#!/usr/bin/env python3
"""
Re-roll only the shots that scored badly.

The coverage experiment was cancelled at 19 of 30 takes, and the partial data
answered the question better than the full run would have. Rendering the same
shot three times and keeping the best is worth about 27% of the total identity
spread -- but the effect is BIMODAL:

    ep07_s06   spread 0.003     re-rolling gains nothing
    ep08_s06   spread 0.005
    ep07_s05   spread 0.006
    ep06_s05   spread 0.035     re-rolling gains a lot
    ep09_s03   spread 0.039
    ep05_s03   spread 0.040

So three-takes-everywhere is mostly waste. Re-rolling the shots that score LOW
captures most of the benefit at a fraction of the cost, and that is a better
rule than the one the experiment set out to test.

This scores every shot in the films, takes the worst N, renders two more seeds
each, and reports which take won. Nothing is swapped automatically -- the new
takes sit alongside the old ones and the assembly picks them up only if told to,
because a higher CLIP score is not the same as a better shot.

    reroll_weak_shots.py <series> --worst 8
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402
import verify_render as vr                                     # noqa: E402

EPISODES = ["ep05", "ep06", "ep07", "ep08", "ep09", "ep10"]


def identity(clip: str, anchor_vec) -> float:
    dur = sr._get_video_duration(clip)
    vals = []
    with tempfile.TemporaryDirectory() as td:
        for frac in (0.2, 0.5, 0.8):
            p = f"{td}/f{int(frac*100)}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss",
                            f"{dur*frac:.2f}", "-i", clip, "-frames:v", "1", p],
                           check=True)
            with Image.open(p) as im:
                vals.append(float((vr._embed_images([im.convert("RGB").copy()])
                                   @ anchor_vec.T)[0][0]))
    return sum(vals) / len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--worst", type=int, default=8)
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()

    sr.set_current_series(a.series)
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    ref_dir = sr.series_path(a.series) / "reference_images"
    anchors = {}

    print("  scoring every dialogue shot ...", flush=True)
    scored = []
    for ep in EPISODES:
        f = sr.series_path(a.series) / "episodes" / f"{ep}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        for sc in data["scenes"]:
            if not sc.get("dialogue"):
                continue
            clip = sr.find_latest_clip(sc["id"])
            if not clip:
                continue
            who = sc["dialogue"][0]["character"]
            if who not in anchors:
                anchors[who] = vr._embed_images(
                    [Image.open(sr._find_ref(ref_dir, who, "char")).convert("RGB")])
            scored.append((identity(clip, anchors[who]), sc["id"], ep, who))
    scored.sort()
    worst = scored[:a.worst]
    print(f"  {len(scored)} shots scored; median {scored[len(scored)//2][0]:.3f}")
    print(f"\n  the {len(worst)} weakest:")
    for s, sid, ep, who in worst:
        print(f"    {sid:11} {who:6} {s:.3f}")

    print(f"\n  re-rolling each with {a.takes} new seed(s)\n", flush=True)
    results = []
    for base_score, sid, ep, who in worst:
        ep_num = int(ep.replace("ep", ""))
        data = sr.load_json(sr.episode_path(a.series, ep_num))
        sc = next(s for s in data["scenes"] if s["id"] == sid)
        res = sr.get_resolution_config("480p", "wan")
        seed_img = sr.get_scene_seed_image(sc, a.series, None)
        prompt = sr.build_scene_prompt(sc, bible)
        neg = sr.build_negative_prompt(sc)
        vo = Path("output") / a.series / ep / "audio" / f"{sid}.mp3"
        if not vo.exists():
            continue
        spoken = sr._get_video_duration(str(vo))
        padded = str(vo.with_name(f"{sid}_rr.mp3"))
        sr.pad_audio_to(str(vo), spoken + sr.S2V_LIVE_TAIL, padded)
        audio = sr.copy_to_input(padded)
        frames, extra, tail = sr.s2v_chunks_for_duration(
            spoken + sr.S2V_LIVE_TAIL, fps=16, floor_seconds=spoken)
        orig_clip = sr.find_latest_clip(sid)
        best = (base_score, "original", orig_clip)
        for k in range(a.takes):
            prefix = f"rr_{sid}_t{k}"
            clip = sr.find_latest_clip(prefix)
            if not clip:
                wf = sr.build_video_workflow(
                    "wan", "s2v", prompt, 9300 + k * 733, prefix, frames, res,
                    negative_prompt=neg, steps=a.steps, image_name=seed_img,
                    audio_path=audio, extra_chunks=extra, last_chunk_frames=tail)
                try:
                    pid = sr.queue_prompt(wf)
                    if not sr.poll_until_done(pid, max_wait=1800 * (1 + extra)):
                        continue
                except Exception as e:                         # noqa: BLE001
                    print(f"    {sid} take {k}: {type(e).__name__}"); continue
                clip = sr.find_latest_clip(prefix)
            if not clip:
                continue
            s = identity(clip, anchors[who])
            if s > best[0]:
                best = (s, f"take{k}", clip)
        gain = best[0] - base_score
        results.append((sid, base_score, best[0], best[1], gain, best[2],
                        orig_clip))
        print(f"    {sid:11} {base_score:.3f} -> {best[0]:.3f}  "
              f"({best[1]}, {gain:+.3f})", flush=True)

    print(f"\n  {'shot':11} {'was':>7} {'best':>7} {'source':>9} {'gain':>7}")
    for sid, b, n, src, g, _w, _o in results:
        print(f"  {sid:11} {b:7.3f} {n:7.3f} {src:>9} {g:+7.3f}")
    improved = [r for r in results if r[4] > 0.005]
    print(f"\n  {len(improved)} of {len(results)} improved by more than 0.005")
    out = Path("/workspace/review/reroll")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps([
        {"shot": sid, "was": b, "best": n, "source": src, "gain": g,
         "winner": w, "original": o} for sid, b, n, src, g, w, o in results
    ], indent=2))
    print(f"  wrote {out / 'results.json'} (with clip paths, so apply_rerolls"
          f" can act on it)")
    print("  nothing swapped automatically — see apply_rerolls.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
