#!/bin/bash
# A/B: fixed blink cadence (production blend) | LAM blink events, on ep2 s05 (Niamh line 1, frontal)
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[blinkab $(date +%H:%M:%S)] $*"; }
CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_BLINK=lam $B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow_blink.blend $W/film2_shots_blink.json < /dev/null > $W/d5_blink_build.log 2>&1
log "blink blend: $(grep -c 'FILM SCENE SAVED' $W/d5_blink_build.log)"
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
S=$(python3 -c "import json; d=json.load(open('$W/film2_shots.json')); s=[x for x in d['shots'] if x['name']=='s05'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"
for V in fixed lam; do BL=film2_first_snow.blend; [ $V = lam ] && BL=film2_first_snow_blink.blend; D=$W/blink_$V; rm -rf $D; mkdir -p $D
  FILM_RES=1248x720 $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$C" "$T" $L $F0 $F1 "$M" < /dev/null > $D.log 2>&1 &
done; wait
for V in fixed lam; do ffmpeg -v error -y -framerate 16 -start_number $F0 -i $W/blink_$V/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 $W/blink_$V.mp4; done
OFF=$(python3 -c "print(($F0-419)/16.0)")
ffmpeg -v error -y -i $W/blink_fixed.mp4 -i $W/blink_lam.mp4 -ss $OFF -i $W/film2_audio/l1.wav -filter_complex "[0][1]hstack[v]" -map "[v]" -map 2:a -shortest -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac $R/day5_blink_ab_ep2b.mp4 && log "day5_blink_ab_ep2b.mp4 (fixed cadence | LAM events)"
rm -rf $W/blink_fixed $W/blink_lam; bash /workspace/export_outcomes.sh 2>&1 | tail -1; log "BLINK AB DONE"
