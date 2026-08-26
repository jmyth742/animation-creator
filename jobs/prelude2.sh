#!/usr/bin/env bash
# Staging is already done; resume from the render.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
say "gates"
$PY scripts/selftest.py || exit 1
$PY scripts/preflight.py $S --episode 10 || exit 1
$PY scripts/validate_workflow.py $S --episode 10 || exit 1
say "render ep10 — The Woman on the White Horse"
rm -f ComfyUI/output/video/$S/ep10_s*.mp4
$PY scripts/showrunner.py produce $S --episode 10
$PY scripts/design_episode_audio.py $S --episode 10
say "1080p"
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
