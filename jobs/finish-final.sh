#!/usr/bin/env bash
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
say "assemble"
$PY scripts/assemble_film.py $S -o /workspace/review/wow/film.mp4 || exit 1
say "1080p"
$PY scripts/upscale_episode.py $S --episode 5 --source /workspace/review/wow/film.mp4 || echo "  skipped"
say "collect"
mkdir -p /workspace/review/wow/deliver
cp /workspace/review/wow/film.mp4 /workspace/review/wow/deliver/
[ -f output/$S/ep05/ep05_1080p.mp4 ] && cp output/$S/ep05/ep05_1080p.mp4 /workspace/review/wow/deliver/film_1080p.mp4
for E in 05 06 07 08 09; do
  F=output/$S/ep$E/ep${E}_designed.mp4
  [ -f "$F" ] && cp "$F" /workspace/review/wow/deliver/ep${E}_designed.mp4
done
ls -la /workspace/review/wow/deliver/
say "done"
