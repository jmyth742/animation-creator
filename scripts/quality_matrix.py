#!/usr/bin/env python3
"""
Render one scene under several settings and put the results side by side.

Answers "what settings actually give the best video" empirically rather than by
argument: same scene, same seed, one variable at a time.

    python scripts/quality_matrix.py tir-na-nog-legend --episode 1 \
        --scene ep01_s11 --character niamh --lora niamh-wan22-r64.safetensors
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

OUT = Path("/workspace/review/matrix")


def variants(lora: str | None):
    """(label, steps, lora_list, seed_mode, resolution) — one variable at a time."""
    v = [("A_base_l8_i2v",      8, None,            "i2v", "480p")]
    if lora:
        v += [
            ("B_lora10_l8_i2v",  8, [(lora, 1.0)],  "i2v", "480p"),
            ("C_lora07_l8_i2v",  8, [(lora, 0.7)],  "i2v", "480p"),
            ("D_lora10_l8_t2v",  8, [(lora, 1.0)],  "t2v", "480p"),
            ("E_lora10_l4_i2v",  4, [(lora, 1.0)],  "i2v", "480p"),
            ("F_lora10_l8_720p", 8, [(lora, 1.0)],  "i2v", "720p"),
        ]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--lora", default=None)
    ap.add_argument("--frames", type=int, default=49)
    a = ap.parse_args()
    sr.set_current_series(a.series)

    # _resolve_wan_dual_loras() only WARNS when a LoRA file is missing, so a
    # matrix run would quietly render every "with LoRA" variant without it and
    # produce six identical clips that look like a conclusive result. Refuse.
    if a.lora:
        base = a.lora.removesuffix(".safetensors")
        ld = sr.COMFYUI_DIR / "models" / "loras"
        missing = [f"{base}-{half}.safetensors" for half in ("high", "low")
                   if not (ld / f"{base}-{half}.safetensors").exists()
                   and not (ld / a.lora).exists()]
        if missing:
            sys.exit(f"  ABORT: LoRA files not found in {ld}: {', '.join(missing)}\n"
                     f"  Without them every variant would render identically.")

    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    scene = next((s for s in ep["scenes"] if s["id"] == a.scene), None)
    if not scene:
        sys.exit(f"no scene {a.scene}")

    tag = a.scene
    OUT.mkdir(parents=True, exist_ok=True)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    results = []

    for label, steps, loras, mode, res in variants(a.lora):
        rc = dict(sr.get_resolution_config(res, "wan"))
        if res == "480p":
            rc["width"], rc["height"] = 832, 480
        seed_image = None
        if mode == "i2v":
            seed_image = sr.get_scene_seed_image(scene, a.series, None)
            if not seed_image:
                print(f"  {label}: no seed image available, using t2v"); mode = "t2v"
        build_loras = list(loras or [])
        build_loras += (sr.LIGHTNING["i2v"] if mode == "i2v" else sr.LIGHTNING["t2v"])
        prefix = f"qm_{tag}_{label}"
        wf = sr.build_video_workflow("wan", mode, prompt, seed=31337, clip_prefix=prefix,
                                     frames=a.frames, res_config=rc, negative_prompt=neg,
                                     steps=steps, loras=build_loras, image_name=seed_image,
                                     optimization="none")
        sr.apply_lightning(wf, steps=steps)
        print(f"  {label}: {mode} {res} steps={steps} lora={loras}", flush=True)
        t0 = time.time()
        try:
            pid = sr.queue_prompt(wf)
            ok = sr.poll_until_done(pid)
        except Exception as e:
            print(f"    ERROR: {e}"); results.append((label, None, 0)); continue
        dt = time.time() - t0
        got = sr.find_latest_clip(prefix) if ok else None
        if got:
            dst = OUT / f"{tag}_{label}.mp4"
            shutil.copy2(got, dst)
            print(f"    {dt:.0f}s -> {dst.name}")
            results.append((label, dst, dt))
        else:
            print(f"    FAILED after {dt:.0f}s")
            results.append((label, None, dt))

    # ── Wide-shot test ────────────────────────────────────────────────
    # A quarter of this episode is wide shots that feature a character. Those
    # deliberately go to T2V (a portrait seed would force portrait framing on
    # them), so they have NO identity anchor at all. A character LoRA lives in
    # the weights rather than a seed image, so it should be able to give them
    # identity without touching composition -- which is the single biggest open
    # question about these LoRAs. Test it on a real wide shot, not a close-up.
    if a.lora:
        import re as _re
        who = scene.get("characters", [None])[0]
        wide = next((sc for sc in ep["scenes"]
                     if who in sc.get("characters", [])
                     and (_re.search(r"\bwide\b[^.]{0,20}?\bshot\b", sc["visual"].lower())
                          or "aerial" in sc["visual"].lower())), None)
        if wide:
            print(f"\n  wide-shot test on {wide['id']} ({who}):")
            wprompt = sr.build_scene_prompt(wide, bible)
            wneg = sr.build_negative_prompt(wide)
            for wlabel, wloras in (("W1_wide_nolora", []), ("W2_wide_lora10", [(a.lora, 1.0)])):
                rc = dict(sr.get_resolution_config("480p", "wan"))
                rc["width"], rc["height"] = 832, 480
                bl = list(wloras) + sr.LIGHTNING["t2v"]
                prefix = f"qm_{wide['id']}_{wlabel}"
                wf = sr.build_video_workflow("wan", "t2v", wprompt, seed=31337,
                                             clip_prefix=prefix, frames=a.frames,
                                             res_config=rc, negative_prompt=wneg,
                                             steps=8, loras=bl, optimization="none")
                sr.apply_lightning(wf, steps=8)
                t0 = time.time()
                try:
                    ok = sr.poll_until_done(sr.queue_prompt(wf))
                except Exception as e:
                    print(f"    {wlabel}: ERROR {e}"); continue
                got = sr.find_latest_clip(prefix) if ok else None
                if got:
                    dst = OUT / f"{wide['id']}_{wlabel}.mp4"
                    shutil.copy2(got, dst)
                    print(f"    {wlabel}: {time.time()-t0:.0f}s -> {dst.name}")
                    results.append((f"{wide['id']}_{wlabel}", dst, time.time() - t0))
                else:
                    print(f"    {wlabel}: FAILED")

    # contact sheet of the midpoint frame of each variant
    good = [(l, p) for l, p, _ in results if p]
    if good:
        pngs = []
        for label, path in good:
            d = sr._get_video_duration(str(path)) or 3.0
            png = OUT / f"{tag}_{label}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d/2:.2f}",
                            "-i", str(path), "-frames:v", "1", str(png)], timeout=60)
            if png.exists():
                pngs.append(png)
        if pngs:
            ins, filt = [], ""
            for i, p in enumerate(pngs):
                ins += ["-i", str(p)]; filt += f"[{i}:v]scale=420:243[v{i}];"
            filt += "".join(f"[v{i}]" for i in range(len(pngs))) + f"hstack={len(pngs)}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", filt,
                            str(OUT / f"{tag}_compare.png")], timeout=120)
    print("\n  timings:")
    for label, path, dt in results:
        print(f"    {label:22} {dt:6.0f}s  {'ok' if path else 'FAILED'}")
    (OUT / f"{tag}_timings.json").write_text(json.dumps(
        [{"variant": l, "seconds": round(d), "ok": bool(p)} for l, p, d in results], indent=2))


if __name__ == "__main__":
    main()
