#!/bin/bash
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960; unset CHAR_SMOOTH
while ps -eo args | grep -qE "[m]asters_v4_ep2.sh|[e]p3_v2master.sh"; do sleep 60; done
bash scripts/ops/render_episode.sh film3_shots.json film3_farewell_cliff.blend film3V4 "The Farewell Cliff" film3_audio $R/farewell_cliff_v4.mp4 3; rm -rf $W/film3V4 $W/film3V4.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
echo "[v4 $(date +%H:%M:%S)] EP3 V4 DONE"
