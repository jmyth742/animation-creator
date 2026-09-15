#!/bin/bash
# after the Day-3 redo: re-master both episodes with the COMPLETE adopted stack
# (render-time normal editing + silhouette lines); delete frame dumps after each.
set -u; cd /workspace/text-to-video
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=2.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0; unset CHAR_SMOOTH
while ps -p 2081692 > /dev/null 2>&1; do sleep 30; done
bash scripts/ops/render_episode.sh film_shots.json film_nine_waterfalls.blend filmS "The Nine Waterfalls" film_audio /workspace/review/nine_waterfalls_v3cast.mp4 6; rm -rf /workspace/loopwork/filmS
bash scripts/ops/render_episode.sh film2_shots.json film2_first_snow.blend film2S "The First Snow" film2_audio /workspace/review/first_snow_v3cast.mp4 6; rm -rf /workspace/loopwork/film2S
bash /workspace/export_outcomes.sh 2>&1 | tail -1
echo "[masters $(date +%H:%M:%S)] V3CAST DONE"
