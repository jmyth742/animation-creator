#!/usr/bin/env bash
# Re-run the two experiments that were invalid, after the current GPU job.
#   camera: every variant used a different seed, so prompt effect and sampling
#           noise were inseparable -- fixed seed now
#   lora:   the cel metric softmaxed raw CLIP similarities and returned ~0.51
#           for everything, so "style holds" measured nothing -- fixed, and the
#           sweep now reaches 0.9/1.0 where the collapse was reported
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

for J in gpunight finishall; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  if [ -n "$P" ]; then
    say "waiting for $J (pid $P)"
    while kill -0 "$P" 2>/dev/null; do sleep 60; done
  fi
done

say "CAMERA, fixed seed — prompt is now the only variable"
$PY scripts/shot_variants.py $S --scene ep05_s03 --camera
$PY scripts/shot_variants.py $S --scene ep05_s01 --camera

say "LORA STRENGTH, working cel metric, out to 1.0"
$PY scripts/lora_strength_sweep.py $S --scene ep05_s03
$PY scripts/lora_strength_sweep.py $S --scene ep07_s05

say "done"
