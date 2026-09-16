#!/bin/bash
# after ep3's v4: rebuild ep1's blend (weld + LAM blinks) and re-render its v4 master
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
while ps -eo args | grep -qE "[m]asters_v4_ep(1|2|3).sh"; do sleep 60; done
CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_BLINK=lam $B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls.blend $W/film_shots.json < /dev/null > $W/v4rb_build1.log 2>&1
echo "[v4 $(date +%H:%M:%S)] ep1 blend rebuilt: $(grep -c 'FILM SCENE SAVED' $W/v4rb_build1.log)"
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=8.0 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960; unset CHAR_SMOOTH
bash scripts/ops/render_episode.sh film_shots.json film_nine_waterfalls.blend filmV4b "The Nine Waterfalls" film_audio $R/nine_waterfalls_v4.mp4 3; rm -rf $W/filmV4b $W/filmV4b.*.log
bash /workspace/export_outcomes.sh 2>&1 | tail -1
echo "[v4 $(date +%H:%M:%S)] EP1 V4b DONE"
