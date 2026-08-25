#!/usr/bin/env python3
"""
Is the character LoRA doing nothing, or is the Lightning LoRA swamping it?

The matrix compared "character LoRA + Lightning at 8 steps" against a seeded
baseline and found no difference -- but the earlier test where a character LoRA
clearly DID work used the LoRA alone at 18 steps / cfg 5.0. Two variables moved
at once, so that null result proves nothing.

Everything here is T2V with no seed image, so identity can only come from the
LoRA. One variable at a time.

    python scripts/lora_isolate.py tir-na-nog-legend --scene ep01_s11 \
        --lora niamh-r64.safetensors
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

OUT = Path("/workspace/review/lora_isolate")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--scene", required=True); ap.add_argument("--lora", required=True)
    ap.add_argument("--frames", type=int, default=49)
    a = ap.parse_args()
    sr.set_current_series(a.series)

    base = a.lora.removesuffix(".safetensors")
    ld = sr.COMFYUI_DIR / "models" / "loras"
    if not (ld / f"{base}-high.safetensors").exists():
        sys.exit(f"  ABORT: {base}-high.safetensors not installed")

    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    bible = sr.load_json(sr.series_path(a.series) / "bible.json")
    scene = next(s for s in ep["scenes"] if s["id"] == a.scene)
    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    OUT.mkdir(parents=True, exist_ok=True)

    #  label,                  char-lora strength, use lightning, steps
    VARIANTS = [
        ("1_control_nolora_base",   None, False, 18),   # no LoRA at all, normal sampling
        ("2_lora10_base",           1.0,  False, 18),   # LoRA alone  <- Jonny's config
        ("3_lora10_lightning",      1.0,  True,   8),   # LoRA + Lightning  <- matrix config
        ("4_lora15_lightning",      1.5,  True,   8),   # can strength overcome Lightning?
    ]
    results = []
    for label, strength, lightning, steps in VARIANTS:
        rc = dict(sr.get_resolution_config("480p", "wan"))
        rc["width"], rc["height"] = 832, 480
        loras = []
        if strength is not None:
            loras.append((a.lora, strength))
        if lightning:
            loras += sr.LIGHTNING["t2v"]
        prefix = f"iso_{a.scene}_{label}"
        wf = sr.build_video_workflow("wan", "t2v", prompt, seed=24680, clip_prefix=prefix,
                                     frames=a.frames, res_config=rc, negative_prompt=neg,
                                     steps=steps, loras=loras or None, optimization="none")
        if lightning:
            sr.apply_lightning(wf, steps=steps)
        cfg = {v["inputs"]["cfg"] for v in wf.values()
               if v.get("class_type") in ("KSampler", "KSamplerAdvanced")}
        print(f"  {label}: steps={steps} cfg={cfg} lora={strength} lightning={lightning}", flush=True)
        t0 = time.time()
        try:
            ok = sr.poll_until_done(sr.queue_prompt(wf))
        except Exception as e:
            print(f"    ERROR {e}"); results.append((label, None, 0)); continue
        dt = time.time() - t0
        got = sr.find_latest_clip(prefix) if ok else None
        if got:
            dst = OUT / f"{a.scene}_{label}.mp4"
            shutil.copy2(got, dst); print(f"    {dt:.0f}s -> {dst.name}")
            results.append((label, dst, dt))
        else:
            print(f"    FAILED"); results.append((label, None, dt))

    good = [(l, p) for l, p, _ in results if p]
    pngs = []
    for label, path in good:
        d = sr._get_video_duration(str(path)) or 3.0
        png = OUT / f"{a.scene}_{label}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d/2:.2f}", "-i", str(path),
                        "-frames:v", "1", str(png)], timeout=60)
        if png.exists(): pngs.append(png)
    if pngs:
        ins, filt = [], ""
        for i, p in enumerate(pngs):
            ins += ["-i", str(p)]; filt += f"[{i}:v]scale=420:243[v{i}];"
        filt += "".join(f"[v{i}]" for i in range(len(pngs))) + f"hstack={len(pngs)}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", filt,
                        str(OUT / f"{a.scene}_isolate_compare.png")], timeout=120)
    (OUT / f"{a.scene}_isolate.json").write_text(json.dumps(
        [{"variant": l, "seconds": round(d), "ok": bool(p)} for l, p, d in results], indent=2))
    print("\n  If 2 differs from 1 but 3 looks like 1 -> Lightning is swamping the LoRA.")
    print("  If 2 also looks like 1 -> the LoRA itself is weak.")


if __name__ == "__main__":
    main()
