#!/bin/bash
# v4 masters: 1664x960, lines 4.0/minlen 40 (judged recipe), parallel 3, frame-verified, dumps deleted per episode.
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960; unset CHAR_SMOOTH
log(){ echo "[v4 $(date +%H:%M:%S)] $*"; }
bash scripts/ops/render_episode.sh film_shots.json film_nine_waterfalls.blend filmV4 "The Nine Waterfalls" film_audio $R/nine_waterfalls_v4.mp4 3; rm -rf $W/filmV4 $W/filmV4.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
bash scripts/ops/render_episode.sh film2_shots.json film2_first_snow.blend film2V4 "The First Snow" film2_audio $R/first_snow_v4.mp4 3; rm -rf $W/film2V4 $W/film2V4.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "V4 MASTERS DONE"
