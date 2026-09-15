#!/bin/bash
# Day-3 redo after marathon6: recalibrated bridge -> rebuild LAM blends -> A/Bs
set -u; cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender; R=/workspace/review; D3=$W/day3
log(){ echo "[d3redo $(date +%H:%M:%S)] $*"; }
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=2.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0; unset CHAR_SMOOTH
CHAR_NORMALFIX=0 FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam $B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls_lam.blend $W/film_shots_lam.json < /dev/null > $W/d3r_build1.log 2>&1; log "ep1 lam blend: $(grep -c 'FILM SCENE SAVED' $W/d3r_build1.log)"
CHAR_NORMALFIX=0 FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam $B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow_lam.blend $W/film2_shots_lam.json < /dev/null > $W/d3r_build2.log 2>&1; log "ep2 lam blend: $(grep -c 'FILM SCENE SAVED' $W/d3r_build2.log)"
ab(){ TAG=$1; BL0=$2; BL1=$3; CAM=$4; TGT=$5; LENS=$6; F0=$7; F1=$8; MOVE=$9; AUD=${10}; LF0=${11}
  for V2 in base lam; do D=$W/ab_${TAG}_$V2; rm -rf $D; mkdir -p $D; BL=$BL0; [ $V2 = lam ] && BL=$BL1
    FILM_RES=1248x720 $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$CAM" "$TGT" $LENS $F0 $F1 "$MOVE" < /dev/null > $D.log 2>&1 &
  done; wait
  for V2 in base lam; do ffmpeg -v error -y -framerate 16 -start_number $F0 -i $W/ab_${TAG}_$V2/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 $W/ab_${TAG}_$V2.mp4; done
  OFF=$(python3 -c "print(($F0-$LF0)/16.0)")
  ffmpeg -v error -y -i $W/ab_${TAG}_base.mp4 -i $W/ab_${TAG}_lam.mp4 -ss $OFF -i $AUD -filter_complex "[0][1]hstack[v]" -map "[v]" -map 2:a -shortest -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac $R/day3_lipsync_ab_$TAG.mp4 && log "day3_lipsync_ab_$TAG.mp4 (Rhubarb | LAM)"
  ffmpeg -v error -y -ss 1.5 -i $R/day3_lipsync_ab_$TAG.mp4 -frames:v 1 $R/day3_lipsync_ab_$TAG.png
  rm -rf $W/ab_${TAG}_base $W/ab_${TAG}_lam
}
ab ep1 film_nine_waterfalls.blend film_nine_waterfalls_lam.blend "1.2,6.85,1.8" "-1.55,8.05,1.45" 45 253 381 "dolly:1.035,6.922,1.779" $W/film_audio/l0.wav 246
ab ep2 film2_first_snow.blend film2_first_snow_lam.blend "1.7,7.4,1.62" "-0.75,8.75,1.57" 55 253 409 "dolly:1.553,7.481,1.617" $W/film2_audio/l0.wav 246
ab ep1b film_nine_waterfalls.blend film_nine_waterfalls_lam.blend "-2.2,6.0,1.62" "-0.45,7.25,1.57" 55 398 506 "dolly:-2.095,6.075,1.617" $W/film_audio/l1.wav 391
ab ep2b film2_first_snow.blend film2_first_snow_lam.blend "-1.6,8.5,1.75" "0.6,10.15,1.45" 45 426 571 "dolly:-1.468,8.599,1.732" $W/film2_audio/l1.wav 419
bash /workspace/export_outcomes.sh 2>&1 | tail -1
log "DAY3 REDO DONE"
