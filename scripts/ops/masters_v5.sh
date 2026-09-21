#!/bin/bash
# v5 masters: painted worlds (per-shot plate projection, 4x plates), camera-projected HD faces (_hd variants),
# UniRig cast, LAM blinks, anime cel shader; 1664x960, 8 px lines. One episode after another, export after each.
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[v5 $(date +%H:%M:%S)] $*"; }
EPS=${EPS:-"1 2 3"}
for EP in $EPS; do
  case $EP in
    1) SCRIPT=build_film.py;  AUD=film_audio;  BL=film_nine_waterfalls_v5.blend; JS=film_shots_v5.json;  TAG=filmV5;  TITLE="The Nine Waterfalls"; OUT=nine_waterfalls_v5.mp4;;
    2) SCRIPT=build_film2.py; AUD=film2_audio; BL=film2_first_snow_v5.blend;     JS=film2_shots_v5.json; TAG=film2V5; TITLE="The First Snow";       OUT=first_snow_v5.mp4;;
    3) SCRIPT=build_film3.py; AUD=film3_audio; BL=film3_farewell_cliff_v5.blend; JS=film3_shots_v5.json; TAG=film3V5; TITLE="The Farewell Cliff";   OUT=farewell_cliff_v5.mp4;;
  esac
  CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_BLINK=lam FILM_FACE_SUFFIX=_hd $B -b --factory-startup --python scripts/blender3d/$SCRIPT -- $W/$AUD $R/$BL $W/$JS < /dev/null > $W/v5_build$EP.log 2>&1
  log "ep$EP blend: saved=$(grep -c 'FILM SCENE SAVED' $W/v5_build$EP.log) painter=$(grep -c 'PAINTER projected' $W/v5_build$EP.log) $(grep -m1 -A3 Traceback $W/v5_build$EP.log | tail -1)"
  [ -f $R/$BL ] || { log "ep$EP build FAILED — skipping"; continue; }
  export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=8.0 FILM_LINE_MINLEN=40 FILM_LINE_CREASE=0 FILM_RES=1664x960; unset CHAR_SMOOTH
  bash scripts/ops/render_episode.sh $JS $BL $TAG "$TITLE" $AUD $R/$OUT 3; rm -rf $W/$TAG $W/$TAG.*.log
  [ -f $R/$OUT ] && ffmpeg -v error -y -i $R/$OUT -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p -c:a aac -movflags +faststart ${OUT%.mp4}_web.mp4 2>/dev/null && mv ${OUT%.mp4}_web.mp4 $R/ 
  log "ep$EP master: $(ls -la $R/$OUT 2>/dev/null | awk '{print $5}') bytes"
  bash /workspace/export_outcomes.sh 2>&1 | tail -1
done
log "V5 MASTERS DONE"
