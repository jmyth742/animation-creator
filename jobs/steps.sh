#!/usr/bin/env bash
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
for J in gpunight finishall retest; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  [ -n "$P" ] && { say "waiting for $J"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }
done
say "DOES S2V NEED 15 STEPS?  (80% of the film renders at 56.8s per step)"
$PY scripts/steps_sweep.py $S --scene ep05_s03
$PY scripts/steps_sweep.py $S --scene ep07_s05
say "done"
