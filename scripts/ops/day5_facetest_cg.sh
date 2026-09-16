#!/bin/bash
# meet-shot probe for both casts with baked auto-facing
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[facetest $(date +%H:%M:%S)] $*"; }
for CAST in cg; do
  CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_CAST=$CAST $B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls_$CAST.blend $W/film_shots_$CAST.json < /dev/null > $W/d5_build_$CAST.log 2>&1 &
done; wait
grep -h "^FACING" $W/d5_build_mv.log $W/d5_build_cg.log | cut -c1-120
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
S=$(python3 -c "import json; d=json.load(open('$W/film_shots.json')); s=[x for x in d['shots'] if x['name']=='s03_meet'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"; FM=$(( (F0+F1)/2 ))
S4=$(python3 -c "import json; d=json.load(open('$W/film_shots.json')); s=[x for x in d['shots'] if x['name']=='s04'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C4 T4 L4 F04 F14 M4 <<< "$S4"; FM4=$(( (F04+F14)/2 ))
for CAST in cg; do D=$W/ft_${CAST}; rm -rf $D; mkdir -p $D; $B -b --factory-startup $R/film_nine_waterfalls_$CAST.blend --python scripts/blender3d/film.py -- $D "$C" "$T" $L $FM $FM static < /dev/null > $D.log 2>&1 &
  D4=$W/ft4_${CAST}; rm -rf $D4; mkdir -p $D4; $B -b --factory-startup $R/film_nine_waterfalls_$CAST.blend --python scripts/blender3d/film.py -- $D4 "$C4" "$T4" $L4 $FM4 $FM4 static < /dev/null > $D4.log 2>&1 & done; wait
ffmpeg -v error -y -i $(ls $W/ft_cg/*.png) -i $(ls $W/ft4_cg/*.png) -filter_complex hstack $R/day5_cg_cast_facing.png && log "day5_cast_facing.png (meet: mv|cg over close: mv|cg)"
log "FACETEST DONE"
