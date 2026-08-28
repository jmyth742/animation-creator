#!/usr/bin/env bash
# Vertical b-roll for shorts, AFTER everything else. 480x832 portrait is a
# native WAN resolution, so these are rendered vertical rather than cropped --
# a cel-shaded wide loses its composition when cropped to 9:16.
set -u
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
S=tir-na-nog-legend
say () { echo; echo "════ $* ════"; date '+%H:%M:%S'; }
for J in overnightfull movetest walktest negab; do
  P=$(cat .jobs/pids/$J.pid 2>/dev/null || echo "")
  [ -n "$P" ] && { say "waiting for $J"; while kill -0 "$P" 2>/dev/null; do sleep 60; done; }
done
say "vertical b-roll for shorts"
$PY scripts/render_vertical_broll.py $S
say "rebuild the shorts pack with whatever landed"
export CUDA_VISIBLE_DEVICES=""
$PY scripts/build_shorts.py
say "done"
