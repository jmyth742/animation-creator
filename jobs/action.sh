#!/usr/bin/env bash
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
for J in gpunight finishall retest stepstest; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  [ -n "$P" ] && { say "waiting for $J"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }
done
say "WILL S2V LET A CHARACTER DO SOMETHING WHILE THEY SPEAK?"
$PY scripts/action_test.py $S --scene ep05_s04
$PY scripts/action_test.py $S --scene ep06_s02
say "done"
