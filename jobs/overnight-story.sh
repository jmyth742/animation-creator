#!/usr/bin/env bash
# Overnight: finish ep05's fixes, unlock two more locations, render two more
# pieces in the ep05 format (6 shots, long takes, one location, designed audio).
#
# Sequenced, not parallel: one GPU. Each stage gates the next, so a failure
# stops rather than cascading into six hours of wrong renders.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
SERIES=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

say "1/9  invariants"
$PY scripts/selftest.py || { echo "selftest FAILED — stopping"; exit 1; }

say "2/9  ep05 s04 re-render (wider framing + padded audio)"
rm -f ComfyUI/output/video/$SERIES/ep05_s04_*.mp4
$PY scripts/showrunner.py produce $SERIES --episode 5 --resume

say "3/9  stage tir_na_nog"
$PY scripts/build_sets.py stage $SERIES tir_na_nog niamh \
    --only master,reverse,side --staging full_body,medium,close,three_quarter,over_shoulder
$PY scripts/build_sets.py stage $SERIES tir_na_nog oisin \
    --only master,reverse,side --staging three_quarter,over_shoulder,medium,close,full_body

say "4/9  stage ruined_ireland"
$PY scripts/build_sets.py stage $SERIES ruined_ireland oisin \
    --only master,reverse,side,closer,wider --staging full_body,three_quarter,medium,over_shoulder,close

say "5/9  gates for ep06 and ep07"
for E in 6 7; do
  $PY scripts/preflight.py $SERIES --episode $E   || { echo "preflight ep0$E FAILED"; exit 1; }
  $PY scripts/validate_workflow.py $SERIES --episode $E || { echo "graph ep0$E FAILED"; exit 1; }
done

say "6/9  design ep05 audio"
$PY scripts/design_episode_audio.py $SERIES --episode 5

say "7/9  render ep06 — Nothing Here Is Ever Lost"
$PY scripts/showrunner.py produce $SERIES --episode 6

$PY scripts/design_episode_audio.py $SERIES --episode 6

say "8/9  render ep07 — The Ground"
$PY scripts/showrunner.py produce $SERIES --episode 7
$PY scripts/design_episode_audio.py $SERIES --episode 7

say "9/9  collect deliverables"
mkdir -p /workspace/review/wow/deliver
for E in 05 06 07; do
  for V in designed final; do
    F=output/$SERIES/ep$E/ep${E}_$V.mp4
    [ -f "$F" ] && cp "$F" /workspace/review/wow/deliver/ep${E}_$V.mp4
  done
done
ls -la /workspace/review/wow/deliver/

say "done"
