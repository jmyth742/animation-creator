#!/bin/bash
# Production blends with the UniRig cast + restaged closes, probe both, then v4 masters
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[prod $(date +%H:%M:%S)] $*"; }
export CHAR_NORMALFIX=0 FILM_RIG=unirig
$B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls.blend $W/film_shots.json < /dev/null > $W/d5_prod1.log 2>&1 &
$B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow.blend $W/film2_shots.json < /dev/null > $W/d5_prod2.log 2>&1 &
wait; N1=$(grep -c 'FILM SCENE SAVED' $W/d5_prod1.log); N2=$(grep -c 'FILM SCENE SAVED' $W/d5_prod2.log); log "blends: ep1 $N1 ep2 $N2  $(grep -h 'feet z' $W/d5_prod1.log $W/d5_prod2.log | grep -oE 'RIGGED [a-z_]+|feet z [0-9.-]+' | tr '\n' ' ')"
[ "$N1" = 1 ] && [ "$N2" = 1 ] || { log "ABORT: a blend failed"; grep -h -A3 Traceback $W/d5_prod1.log $W/d5_prod2.log | head -8; exit 1; }
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
probe(){ SJ=$1; BL=$2; SHOT=$3; TAG=$4; S=$(python3 -c "import json; d=json.load(open('$W/$SJ')); s=[x for x in d['shots'] if x['name']=='$SHOT'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"; FM=$(( (F0+F1)/2 )); D=$W/prod_$TAG; rm -rf $D; mkdir -p $D
  $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$C" "$T" $L $FM $FM static < /dev/null > $D.log 2>&1; }
probe film_shots.json film_nine_waterfalls.blend s04 e1s04 & probe film_shots.json film_nine_waterfalls.blend s05 e1s05 & probe film2_shots.json film2_first_snow.blend s04 e2s04 & probe film2_shots.json film2_first_snow.blend s05 e2s05 & wait
ffmpeg -v error -y -i $(ls $W/prod_e1s04/*.png) -i $(ls $W/prod_e1s05/*.png) -i $(ls $W/prod_e2s04/*.png) -i $(ls $W/prod_e2s05/*.png) -filter_complex "[0][1]hstack[a];[2][3]hstack[b];[a][b]vstack" $R/day5_production_probes.png && log "day5_production_probes.png (ep1 s04|s05 over ep2 s04|s05)"
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "launching v4 masters"; bash /workspace/loopwork/masters_v4.sh
