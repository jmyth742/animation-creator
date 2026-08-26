#!/usr/bin/env bash
# Finish ep10: one shot failed on an unsafe tail length, now fixed.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
say "gates"
$PY scripts/selftest.py || exit 1
say "finish ep10 (resume — only the failed shot re-renders)"
$PY scripts/showrunner.py produce $S --episode 10 --resume
$PY scripts/design_episode_audio.py $S --episode 10
say "post pass on the prelude"
$PY scripts/assemble_film.py $S -o /workspace/review/post/prelude_post.mp4 --post \
   --title "The Woman on the White Horse" --subtitle "a prelude" 2>/dev/null || true
say "1080p"
$PY scripts/upscale_episode.py $S --episode 10
say "collect"
mkdir -p /workspace/review/wow/deliver
[ -f output/$S/ep10/ep10_designed.mp4 ] && cp output/$S/ep10/ep10_designed.mp4 /workspace/review/wow/deliver/prelude.mp4
[ -f output/$S/ep10/ep10_1080p.mp4 ] && cp output/$S/ep10/ep10_1080p.mp4 /workspace/review/wow/deliver/prelude_1080p.mp4
cp /workspace/review/post/film_post.mp4 /workspace/review/wow/deliver/film_post.mp4 2>/dev/null
ls -la /workspace/review/wow/deliver/
say "done"
