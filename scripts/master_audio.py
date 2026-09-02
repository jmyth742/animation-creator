#!/usr/bin/env python3
"""
A delivery mastering pass: bring an episode to platform loudness.

Measured 2 Sep, no episode had ever had its levels checked: integrated
loudness sat at -21 to -24 LUFS with a 14-19 LU range. YouTube normalises
DOWN to -14 and never up, so the episodes played at roughly half the
perceived loudness of everything beside them, with dialogue that a phone
speaker would lose in the wide range.

Two-pass ffmpeg loudnorm to the online delivery standard:
    integrated -14 LUFS · true peak -1.5 dBTP · range 11 LU

Video stream is copied untouched. Writes ep{N}_mastered.mp4 beside the
final, then replaces the final only after the result decodes AND measures
within 1 LU of target -- the lesson of every silent failure this month.

    master_audio.py <series> --episode 13
    master_audio.py <series> --all
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


def measure(path):
    r = subprocess.run(["ffmpeg", "-i", str(path), "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    t = r.stderr
    i = t.rfind("{")
    return json.loads(t[i:]) if i >= 0 else {}


def master(final: Path) -> bool:
    m1 = measure(final)
    if not m1:
        print("    could not measure"); return False
    af = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
          f":measured_I={m1['input_i']}:measured_TP={m1['input_tp']}"
          f":measured_LRA={m1['input_lra']}"
          f":measured_thresh={m1['input_thresh']}"
          f":offset={m1['target_offset']}:linear=true")
    out = final.with_name(final.stem.replace("_final", "_mastered") + ".mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final),
                        "-c:v", "copy", "-af", af, "-c:a", "aac",
                        "-b:a", "192k", "-ar", "48000", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not sr._decodes(out) \
            or not sr._preserves_streams(final, out):
        print(f"    mastering failed: {r.stderr[:120]}"); return False
    m2 = measure(out)
    got = float(m2.get("input_i", -99))
    if abs(got - TARGET_I) > 1.0:
        print(f"    landed at {got} LUFS, off target — keeping the original")
        out.unlink(missing_ok=True); return False
    shutil.copy(out, final)
    print(f"    {float(m1['input_i']):.1f} -> {got:.1f} LUFS  "
          f"(range {m1['input_lra']} -> {m2['input_lra']} LU)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    eps = [a.episode] if a.episode else (
        list(range(5, 18)) if a.all else sys.exit("need --episode or --all"))
    ok = 0
    for e in eps:
        f = Path("output") / a.series / f"ep{e:02d}" / f"ep{e:02d}_final.mp4"
        if not f.exists():
            continue
        print(f"  ep{e:02d}:", flush=True)
        ok += master(f)
    print(f"\n  {ok} episode(s) mastered to {TARGET_I} LUFS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
