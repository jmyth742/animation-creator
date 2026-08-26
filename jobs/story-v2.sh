#!/usr/bin/env bash
# Re-render the whole film with two changes:
#   - picture is sampled only as far as the LINE, then holds a frozen frame,
#     so a mouth cannot move after the words stop (34% of the film was
#     generated picture over silence)
#   - four rewritten lines: "three hundred years" cut from five uses to two,
#     and ep07's peak no longer recaps a scene the audience just watched
# Plus ep09, the ending the film was missing.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

say "gates"
$PY scripts/selftest.py || exit 1

for E in 5 6 7 8 9; do
  EP=$(printf "%02d" $E)
  say "render ep$EP"
  $PY scripts/preflight.py $S --episode $E   || { echo "preflight ep$EP FAILED"; exit 1; }
  $PY scripts/validate_workflow.py $S --episode $E || { echo "graph ep$EP FAILED"; exit 1; }
  rm -f ComfyUI/output/video/$S/ep${EP}_s*.mp4
  $PY scripts/showrunner.py produce $S --episode $E
  $PY scripts/design_episode_audio.py $S --episode $E
done

say "done"
