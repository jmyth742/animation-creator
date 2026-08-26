#!/usr/bin/env bash
# Runs the moment the v2 re-render finishes: cut the film, then upscale it.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }

P1=$(cat .jobs/pids/storyv2.pid 2>/dev/null || echo "")
if [ -n "$P1" ]; then
  say "waiting for the re-render (pid $P1)"
  while kill -0 "$P1" 2>/dev/null; do sleep 30; done
fi

say "assemble the film"
$PY scripts/assemble_film.py $S -o /workspace/review/wow/film.mp4 || exit 1

say "1080p"
# The film is one continuous piece, so upscale it as one rather than per episode.
$PY scripts/upscale_episode.py $S --episode 5 \
    --source /workspace/review/wow/film.mp4 || echo "  upscale skipped"

say "collect"
mkdir -p /workspace/review/wow/deliver
cp /workspace/review/wow/film.mp4 /workspace/review/wow/deliver/ 2>/dev/null
[ -f output/$S/ep05/ep05_1080p.mp4 ] && \
  cp output/$S/ep05/ep05_1080p.mp4 /workspace/review/wow/deliver/film_1080p.mp4
for E in 05 06 07 08 09; do
  F=output/$S/ep$E/ep${E}_designed.mp4
  [ -f "$F" ] && cp "$F" /workspace/review/wow/deliver/ep${E}_designed.mp4
done
ls -la /workspace/review/wow/deliver/

say "done"
