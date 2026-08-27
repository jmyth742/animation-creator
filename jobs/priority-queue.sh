#!/usr/bin/env bash
# Reordered after coverage was cancelled. Most consequential first: the two
# experiments that change what we BUILD, then the corrected re-tests.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

P=$(cat .jobs/pids/finishall.pid 2>/dev/null || echo "")
if [ -n "$P" ]; then
  say "waiting for the complete film (pid $P)"
  while kill -0 "$P" 2>/dev/null; do sleep 30; done
fi

say "1  CAN A CHARACTER DO SOMETHING WHILE THEY SPEAK?"
# 42 of 55 shots are a person standing still talking. If S2V can direct a body,
# the ceiling has been the scripts, not the model.
$PY scripts/action_test.py $S --scene ep05_s04
$PY scripts/action_test.py $S --scene ep06_s02

say "2  DOES S2V NEED 15 STEPS?"
# 56.8s per step on ~80% of every film. A third off, permanently, if 10 holds.
$PY scripts/steps_sweep.py $S --scene ep05_s03

say "3  CAMERA, fixed seed this time"
$PY scripts/shot_variants.py $S --scene ep05_s03 --camera

say "4  LORA STRENGTH, working cel metric, out to 1.0"
$PY scripts/lora_strength_sweep.py $S --scene ep05_s03

say "5  TWO CHARACTERS IN ONE FRAME"
$PY scripts/two_shot_test.py $S --location tir_na_nog --setup master

say "done"
