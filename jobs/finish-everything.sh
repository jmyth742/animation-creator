#!/usr/bin/env bash
# Runs AFTER the overnight GPU job, never alongside it. Two jobs on one ComfyUI
# queue interleave and thrash between models: the prelude's 1080p pass managed
# 18 of 69 segments in eight hours while sharing the card.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

P=$(cat .jobs/pids/gpunight.pid 2>/dev/null || echo "")
if [ -n "$P" ]; then
  say "waiting for the overnight GPU job (pid $P)"
  while kill -0 "$P" 2>/dev/null; do sleep 60; done
fi

say "cut the prelude on its own, with the post pass"
$PY scripts/assemble_film.py $S --episodes ep10 --post \
    --title "The Woman on the White Horse" --subtitle "a prelude" \
    -o /workspace/review/post/prelude_post.mp4 || true

say "cut the COMPLETE film — prelude plus the four movements"
$PY scripts/assemble_film.py $S --post \
    --title "Tir na nOg" --subtitle "a folk tale in five movements" \
    -o /workspace/review/post/complete.mp4 || true

say "1080p — one pass, on the complete film"
$PY scripts/upscale_episode.py $S --episode 10 --source /workspace/review/post/complete.mp4 || true

say "collect"
mkdir -p /workspace/review/wow/deliver
cp /workspace/review/post/complete.mp4 /workspace/review/wow/deliver/ 2>/dev/null
cp /workspace/review/post/prelude_post.mp4 /workspace/review/wow/deliver/ 2>/dev/null
cp /workspace/review/post/film_post.mp4 /workspace/review/wow/deliver/ 2>/dev/null
[ -f output/$S/ep10/ep10_1080p.mp4 ] && cp output/$S/ep10/ep10_1080p.mp4 /workspace/review/wow/deliver/complete_1080p.mp4
ls -la /workspace/review/wow/deliver/*.mp4
say "done"
