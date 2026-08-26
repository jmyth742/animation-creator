#!/usr/bin/env bash
# Overnight GPU work. Three things the card can do that post-production cannot.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

P=$(cat .jobs/pids/prelude2.pid 2>/dev/null || echo "")
if [ -n "$P" ]; then
  say "waiting for the prelude to finish (pid $P)"
  while kill -0 "$P" 2>/dev/null; do sleep 30; done
fi

say "1  CAN WAN MOVE THE CAMERA?  (open question, zero research claims)"
# One close-up and one wide, each rendered static / dolly / pan / handheld /
# crane. If a move is real, motion rises without identity falling. If the model
# just warps, identity drops and the question is closed.
$PY scripts/shot_variants.py $S --scene ep05_s03 --camera
$PY scripts/shot_variants.py $S --scene ep05_s01 --camera

say "2  COVERAGE — alternate takes on the shots that carry the films"
# Every shot in both films is a first take. Three takes each on the ten that
# matter most, chosen on measured identity.
for SC in ep05_s03 ep07_s05 ep08_s06 ep07_s06 ep09_s03 \
          ep06_s05 ep06_s06 ep08_s05 ep05_s06 ep10_s09; do
  $PY scripts/shot_variants.py $S --scene $SC --seeds 2
done

say "3  MORE COVERAGE PER LOCATION — angles we do not have"
# 3-5 camera positions per place means the same framings keep recurring.
$PY scripts/build_sets.py setups $S --all
$PY scripts/build_sets.py check $S --threshold 0.55

say "done"
