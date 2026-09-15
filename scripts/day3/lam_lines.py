"""Run LAM Audio2Expression on every line wav of an audio dir.
Run in the lam_a2e venv:  python lam_lines.py <audio_dir> <out_dir>
Writes <out_dir>/l<i>.json (ARKit-52 @30fps). One subprocess per line —
the repo's inference.py is a launcher that takes a single audio_input."""
import json, os, pathlib, subprocess, sys
audio_dir, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
R = "/workspace/LAM_Audio2Expression"
os.environ.setdefault("HF_HOME", "/workspace/hf_cache")
ok = 0
for L in json.load(open(audio_dir / "lines.json")):
    i = L["i"]; wav = audio_dir / f"l{i}.wav"; js = out / f"l{i}.json"
    if js.exists() and js.stat().st_size > 1000:
        ok += 1; continue
    r = subprocess.run([sys.executable, "inference.py", "--config-file", "configs/lam_audio2exp_config_streaming.py",
                        "--options", f"save_path={out}/l{i}_work", "weight=pretrained_models/lam_audio2exp_streaming.tar",
                        f"audio_input={wav}", f"save_json_path={js}"],
                       cwd=R, capture_output=True, text=True)
    if js.exists() and js.stat().st_size > 1000:
        ok += 1; print(f"LAM l{i} ok ({js.stat().st_size} bytes)")
    else:
        tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
        print(f"LAM l{i} FAILED:", " | ".join(t[:160] for t in tail))
print("LAM LINES", ok, "ok")
