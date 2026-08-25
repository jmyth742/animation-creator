#!/usr/bin/env python3
"""
Pre-flight audit: check a series is actually wired the way you think it is.

Written after a day in which every serious bug was silent -- a LoRA that
loaded and did nothing because its trigger word was missing from the prompt,
portraits written under names nothing read, ambience keyword-matching "bar"
inside "bare", flags whose binaries were absent. None of it errored. This
checks the things that fail quietly.

    python scripts/preflight.py <series> --episode 1
"""
import argparse
import subprocess, json, re, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr

FAIL, WARN, OK = "FAIL", "WARN", "ok  "
issues = {"FAIL": 0, "WARN": 0}


def say(level, msg):
    if level in issues:
        issues[level] += 1
    print(f"  [{level}] {msg}")


def section(t):
    print(f"\n─── {t} " + "─" * max(0, 58 - len(t)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series"); ap.add_argument("--episode", type=int, default=1)
    a = ap.parse_args()
    sr.set_current_series(a.series)
    sp = sr.series_path(a.series)
    bible = sr.load_json(sp / "bible.json")
    ep = sr.load_json(sr.episode_path(a.series, a.episode))
    scenes = ep["scenes"]
    loras_dir = sr.COMFYUI_DIR / "models" / "loras"
    unet_dir = sr.COMFYUI_DIR / "models" / "unet"
    ref_dir = sp / "reference_images"

    # ── models ───────────────────────────────────────────────────────
    section("models on disk")
    rc = sr.get_resolution_config("480p", "wan")
    mc = sr.get_model_config("wan")
    te = mc.get("text_encoder", mc)
    for label, rel in [
        ("T2V unet", unet_dir / rc["t2v_unet"]),
        ("I2V unet high", unet_dir / rc["i2v_unet"]),
        ("I2V unet low", unet_dir / rc["i2v_unet_low"]),
        ("S2V unet", unet_dir / rc.get("s2v_unet", "MISSING")),
        ("VAE", sr.COMFYUI_DIR / "models" / "vae" / mc["vae"]),
        ("audio encoder", sr.COMFYUI_DIR / "models" / "audio_encoders" /
         "wav2vec2_large_english_fp16.safetensors"),
    ]:
        say(OK if Path(rel).exists() else FAIL,
            f"{label}: {Path(rel).name}" + ("" if Path(rel).exists() else "  MISSING"))
    for half in ("t2v", "i2v"):
        for lvl in ("high", "low"):
            f = loras_dir / f"lightning-{half}-{lvl}.safetensors"
            say(OK if f.exists() else WARN, f"lightning {half} {lvl}")

    # ── characters ───────────────────────────────────────────────────
    section("characters: LoRA wiring and trigger words")
    for cid, c in bible.get("characters", {}).items():
        lp, tw = c.get("lora_path"), c.get("trigger_word")
        if not lp:
            say(OK, f"{cid}: no LoRA (prompt will use the visual description)")
            continue
        h, l = _resolve(loras_dir, lp)
        if not (h and l):
            say(FAIL, f"{cid}: lora_path={lp} but files missing -> LoRA silently skipped")
        elif not tw:
            say(FAIL, f"{cid}: LoRA set but NO trigger_word -> loads and does nothing")
        else:
            say(OK, f"{cid}: {lp} @ {c.get('lora_strength', 0.7)}  trigger='{tw}'")
        if c.get("voice") and c["voice"] not in sr.VOICE_WPS:
            say(WARN, f"{cid}: voice {c['voice']} not in VOICE_WPS (rate is guessed)")

    nv = (bible.get("narrator") or {}).get("voice")
    say(OK if nv in sr.VOICE_WPS else WARN,
        f"narrator {nv}" + ("" if nv in sr.VOICE_WPS else " not in VOICE_WPS (rate guessed)"))

    # ── scene-by-scene ───────────────────────────────────────────────
    section("scenes: routing, seed, trigger presence, budgets")
    fps = float(mc["fps"])
    wps = sr.VOICE_WPS.get(nv, sr.DEFAULT_WPS)
    locs = bible.get("world", {}).get("locations", {})
    for i, s in enumerate(scenes):
        sid = s["id"]
        if s.get("location") not in locs:
            say(FAIL, f"{sid}: unknown location {s.get('location')}")
        for c in s.get("characters", []):
            if c not in bible.get("characters", {}):
                say(FAIL, f"{sid}: unknown character {c}")
        # Mirror cmd_produce's actual routing, not just classify_scene_type().
        # A scene can classify as i2v and still render as t2v when the seeding
        # policy returns nothing -- reporting the classification alone is
        # misleading, and the seed it computed may be discarded.
        setup_plates = {f.name for f in
                        (sr.series_path(a.series) / "sets").rglob("*.png")}
        stype = sr.classify_scene_type(s)
        seed = sr.get_scene_seed_image(s, a.series, "chain_prev.png")
        override = (s.get("seed") or "").lower()
        if stype == "s2v":
            mode = "s2v"
        elif stype == "i2v" and seed:
            mode = "i2v"
        elif seed and override in ("location", "portrait", "chain"):
            mode = "i2v"
        else:
            mode = "t2v"
        if mode == "t2v":
            seed_kind = "unused" if seed else "none"
        else:
            # The set library names staged plates <setup>__<char>_<framing>.png
            # and setup plates <setup>.png -- neither carries the char_/loc_
            # prefixes this check was written against, so every staged shot was
            # reported as falling back to the frame chain. Six correct shots
            # warning loudly is worse than no check: it teaches you to skip the
            # section that also carries the real failures.
            _s = str(seed)
            seed_kind = ("portrait" if "char_" in _s else
                         "staged" if "__" in _s else
                         "plate" if ("loc_" in _s or _s in setup_plates) else
                         "CHAIN")
        if seed_kind == "CHAIN":
            say(WARN, f"{sid}: falls back to the frame chain — will inherit the previous shot")
        prompt = sr.build_scene_prompt(s, bible)
        missing = [c for c in s.get("characters", [])
                   if (bible["characters"].get(c, {}).get("trigger_word"))
                   and bible["characters"][c]["trigger_word"] not in prompt]
        if missing:
            say(FAIL, f"{sid}: trigger word absent from prompt for {missing} -> LoRA inert")
        slot = s and sr.CLIP_LENGTHS[s["clip_length"]]["frames"] / fps - sr.CROSSFADE_DURATION
        n = (s.get("narration") or "").split()
        budget = int(slot * wps)
        over = " OVER BUDGET" if len(n) > budget else ""
        if over:
            say(WARN, f"{sid}: narration {len(n)}w > {budget}w for a {slot:.1f}s slot{over}")
        # 8 words was the right cap when every clip was 5.06s. A chained take
        # runs to 15s, and a piece written for that format trips this on every
        # single shot -- so the cap now follows the shot's real length.
        hold = float(s.get("hold_seconds") or 0.0)
        spoken_slot = max(slot, hold)
        dlg_budget = max(8, int(spoken_slot * wps))
        for d in s.get("dialogue", []):
            nw = len(d["line"].split())
            if nw > dlg_budget:
                say(WARN, f"{sid}: dialogue line {nw}w > {dlg_budget}w "
                          f"for a {spoken_slot:.1f}s shot")
        print(f"        {sid}  {mode:4}  seed={seed_kind:9} "
              f"narr={len(n)}/{budget}w  dlg={len(s.get('dialogue', []))}")

    # ── audio ────────────────────────────────────────────────────────
    section("audio: ambience mapping")
    for loc in {s.get("location") for s in scenes}:
        amb = sr.get_ambient_file(loc, bible)
        say(OK if amb else WARN,
            f"{loc} -> {amb.name if amb else '(silence)'}")

    # ── reference images ─────────────────────────────────────────────
    section("reference images")
    for cid in bible.get("characters", {}):
        f = sr._find_ref(ref_dir, cid, "char")
        say(OK if f else WARN, f"portrait {cid}: {f.name if f else 'MISSING'}")
    for loc in locs:
        f = sr._find_ref(ref_dir, loc, "loc")
        say(OK if f else WARN, f"plate {loc}: {f.name if f else 'MISSING'}")

    # ── post-processing binaries ─────────────────────────────────────
    section("post-processing")
    say(OK if shutil.which("ffmpeg") else FAIL, "ffmpeg")
    say(WARN if not shutil.which("rife-ncnn-vulkan") else OK,
        "rife-ncnn-vulkan" + ("" if shutil.which("rife-ncnn-vulkan")
                              else " absent -> --interpolate falls back to FFmpeg minterpolate"))
    say(WARN if not shutil.which("realesrgan-ncnn-vulkan") else OK,
        "realesrgan-ncnn-vulkan" + ("" if shutil.which("realesrgan-ncnn-vulkan")
                                    else " absent -> --upscale falls back to lanczos"))

    # ── camera coverage ──────────────────────────────────────────────
    # A scene naming a setup that has no plate falls back silently to the bare
    # portrait or the frame chain, which is precisely the drift the set library
    # exists to stop. Only meaningful once a library has been built.
    section("camera coverage")
    sets_root = sp / "sets"
    used = {(sc.get("location"), sc.get("setup")) for sc in scenes if sc.get("setup")}
    if not sets_root.is_dir():
        say(WARN if used else OK,
            f"no set library built ({len(used)} scene(s) name a setup — they will "
            f"fall back to plates)" if used else "no set library (not required)")
    else:
        missing = []
        for loc, setup in sorted(x for x in used if x[0]):
            f = sets_root / loc / f"{setup}.png"
            say(OK if f.exists() else FAIL, f"{loc}/{setup}.png")
            if not f.exists():
                missing.append(f"{loc}/{setup}")
        # staged plates for close-ups
        for sc in scenes:
            if not (sc.get("staging") and sc.get("characters") and sc.get("location")):
                continue
            who = sc["characters"][0]
            if sc.get("dialogue"):
                spk = sc["dialogue"][0].get("character", who)
                who = spk if spk in sc["characters"] else who
            base = sc.get("setup") or "master"
            hits = list((sets_root / sc["location"]).glob(f"{base}__{who}_*.png")) \
                if (sets_root / sc["location"]).is_dir() else []
            say(OK if hits else WARN,
                f"{sc['id']}: staged plate {base}__{who}_* "
                f"{'found' if hits else 'MISSING — close-up will use the bare portrait'}")

    # ── workflow graphs ──────────────────────────────────────────────
    # The layer that ten silent defects lived in: configuration was right, the
    # data was right, the output looked plausible, and the GRAPH threw away the
    # character reference. Build every shot's workflow and check it.
    section("workflow graphs")
    r = subprocess.run([sys.executable, str(Path(__file__).parent / "validate_workflow.py"),
                        a.series, "--episode", str(a.episode)],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        t = line.strip()
        if t.startswith(("WanSound", "WanImage", "LoadImage", "node ", "sampler ",
                         "S2V checkpoint", "no sampler")):
            say(FAIL, t)
    tail = [l.strip() for l in r.stdout.splitlines() if l.strip().endswith("problem(s)")]
    say(OK if r.returncode == 0 else FAIL, tail[-1] if tail else f"exited {r.returncode}")

    # ── regression suite ─────────────────────────────────────────────
    # preflight checks THIS episode's configuration; selftest checks that the
    # pipeline's own invariants still hold. A green preflight over a regressed
    # stitcher still produces a broken episode, so run both before rendering.
    section("regression suite")
    r = subprocess.run([sys.executable, str(Path(__file__).parent / "selftest.py")],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.strip().startswith("FAIL"):
            say(FAIL, line.strip())
    tally = [l for l in r.stdout.splitlines() if l.strip().endswith(("passed", "skipped"))
             or " passed," in l]
    say(OK if r.returncode == 0 else FAIL,
        tally[-1].strip() if tally else f"selftest exited {r.returncode}")

    print(f"\n═══ {issues['FAIL']} failures, {issues['WARN']} warnings ═══")
    return 1 if issues["FAIL"] else 0


def _resolve(d: Path, name: str):
    base = name.removesuffix(".safetensors")
    if (d / name).exists():
        return (d / name), (d / name)
    h, l = d / f"{base}-high.safetensors", d / f"{base}-low.safetensors"
    return (h if h.exists() else None), (l if l.exists() else None)


if __name__ == "__main__":
    sys.exit(main())
