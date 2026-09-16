#!/bin/bash
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=8.0 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960; unset CHAR_SMOOTH
while ps aux | grep -q "[m]asters_v4_ep1.sh"; do sleep 60; done
bash scripts/ops/render_episode.sh film2_shots.json film2_first_snow.blend film2V4 "The First Snow" film2_audio $R/first_snow_v4.mp4 3; rm -rf $W/film2V4 $W/film2V4.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
echo "[v4 $(date +%H:%M:%S)] EP2 V4 DONE"
