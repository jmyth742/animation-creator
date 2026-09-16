#!/bin/bash
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[cgfilm $(date +%H:%M:%S)] $*"; }
CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_CAST=cg $B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls_cg.blend $W/film_shots_cg.json < /dev/null > $W/d5_build_cg.log 2>&1
log "unirig blend: $(grep -c 'FILM SCENE SAVED' $W/d5_build_cg.log) $(grep -m2 -E 'Error|Traceback|RIGGED' $W/d5_build_unirig.log | tr '\n' ' ' | cut -c1-200)"
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
for SHOT in s02_walk s03_meet s04; do
  S=$(python3 -c "import json; d=json.load(open('$W/film_shots.json')); s=[x for x in d['shots'] if x['name']=='$SHOT'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"
  FM=$(( (F0+F1)/2 ))
  for V in cur unirig; do BL=film_nine_waterfalls.blend; [ $V = unirig ] && BL=film_nine_waterfalls_cg.blend; D=$W/cgfilm_${SHOT}_$V; rm -rf $D; mkdir -p $D
    $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$C" "$T" $L $FM $FM static < /dev/null > $D.log 2>&1 &
  done; wait
  ffmpeg -v error -y -i $(ls $W/cgfilm_${SHOT}_cur/*.png | head -1) -i $(ls $W/cgfilm_${SHOT}_unirig/*.png | head -1) -filter_complex hstack $R/day5_cg_cast_${SHOT}.png && log "day5_cg_cast_${SHOT}.png (numpy | unirig)"
done
log "RIGFILM DONE"
