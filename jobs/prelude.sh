#!/usr/bin/env bash
# The prelude: stage two new locations, render, then re-upscale both films.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

say "gates"
$PY scripts/selftest.py || exit 1

say "stage storm_cliffs"
$PY scripts/build_sets.py stage $S storm_cliffs oisin \
    --only master,side,closer --staging close,full_body,medium,over_shoulder,three_quarter
$PY scripts/build_sets.py stage $S storm_cliffs niamh \
    --only master,side,closer --staging close,full_body,medium,three_quarter

say "stage sunlight_path"
$PY scripts/build_sets.py stage $S sunlight_path oisin \
    --only master,side,closer --staging close,full_body,three_quarter
$PY scripts/build_sets.py stage $S sunlight_path niamh \
    --only master,side,closer --staging close,medium

say "check the new plates for invented people"
# The ruined_ireland wider plate shipped three strangers into two shots because
# nothing caught it. Look before rendering 28 shots off these.
$PY scripts/build_sets.py check $S --threshold 0.55

say "gates for ep10"
$PY scripts/preflight.py $S --episode 10 || { echo "preflight FAILED"; exit 1; }
$PY scripts/validate_workflow.py $S --episode 10 || { echo "graph FAILED"; exit 1; }

say "render ep10"
rm -f ComfyUI/output/video/$S/ep10_s*.mp4
$PY scripts/showrunner.py produce $S --episode 10
$PY scripts/design_episode_audio.py $S --episode 10

say "1080p — the prelude, then the main film"
$PY scripts/upscale_episode.py $S --episode 10
$PY scripts/upscale_episode.py $S --episode 5 --source /workspace/review/wow/film.mp4

say "collect"
mkdir -p /workspace/review/wow/deliver
cp /workspace/review/wow/film.mp4 /workspace/review/wow/deliver/ 2>/dev/null
[ -f output/$S/ep05/ep05_1080p.mp4 ] && cp output/$S/ep05/ep05_1080p.mp4 /workspace/review/wow/deliver/film_1080p.mp4
[ -f output/$S/ep10/ep10_designed.mp4 ] && cp output/$S/ep10/ep10_designed.mp4 /workspace/review/wow/deliver/prelude.mp4
[ -f output/$S/ep10/ep10_1080p.mp4 ] && cp output/$S/ep10/ep10_1080p.mp4 /workspace/review/wow/deliver/prelude_1080p.mp4
ls -la /workspace/review/wow/deliver/
say "done"
