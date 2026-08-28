#!/usr/bin/env bash
# Both questions I closed too early, reopened properly.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
P=$(cat .jobs/pids/overnightfull.pid 2>/dev/null || echo "")
[ -n "$P" ] && { say "waiting for the overnight run"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }

say "1  TWO-SHOT, seeded from a composite of two staged plates"
# The first test seeded from an EMPTY plate and scored 0.62. It gave the model
# no face for either character and then blamed it for guessing.
$PY scripts/two_shot_composite.py $S --location tir_na_nog --setup master --framing full_body
$PY scripts/two_shot_composite.py $S --location farewell_cliff --setup master --framing full_body
$PY scripts/two_shot_composite.py $S --location tir_na_nog --setup master --framing three_quarter

say "2  WHICH ACTION VERBS ACTUALLY MOVE A BODY"
# ep11 showed whole-body verbs work and small ones do not:
#   stands up 5.70   rises 5.59   walks 5.44   crouches 3.62
#   turns 2.97/2.56  lowers 2.25   (still shots average 3.01)
# Test the strong ones against more, on a shot that did NOT move.
$PY scripts/action_test.py $S --scene ep06_s02

say "done"
