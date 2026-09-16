#!/bin/bash
# flat-palette IN MOTION: ep2 Niamh close, current textures | flattened textures (48 frames)
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender
log(){ echo "[flatab $(date +%H:%M:%S)] $*"; }
CHAR_NORMALFIX=0 FILM_RIG=unirig FILM_FACE_SUFFIX=_flat $B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow_flat.blend $W/film2_shots_flat.json < /dev/null > $W/d5_flat_build.log 2>&1
log "flat blend: $(grep -c 'FILM SCENE SAVED' $W/d5_flat_build.log) $(grep -m1 -E 'Traceback|Error' $W/d5_flat_build.log)"
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
S=$(python3 -c "import json; d=json.load(open('$W/film2_shots.json')); s=[x for x in d['shots'] if x['name']=='s05'][0]; print(s['cam'],s['tgt'],s['lens'],s['f0'],s['f1'],s['move'])"); read C T L F0 F1 M <<< "$S"; F1=$((F0+47))
for V in cur flat; do BL=film2_first_snow.blend; [ $V = flat ] && BL=film2_first_snow_flat.blend; D=$W/flat_$V; rm -rf $D; mkdir -p $D
  $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$C" "$T" $L $F0 $F1 "$M" < /dev/null > $D.log 2>&1 &
done; wait
for V in cur flat; do ffmpeg -v error -y -framerate 16 -start_number $F0 -i $W/flat_$V/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 $W/flat_$V.mp4; done
OFF=$(python3 -c "print(($F0-419)/16.0)")
ffmpeg -v error -y -i $W/flat_cur.mp4 -i $W/flat_flat.mp4 -ss $OFF -i $W/film2_audio/l1.wav -filter_complex "[0][1]hstack[v]" -map "[v]" -map 2:a -shortest -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac $R/day5_flat_ab_ep2b.mp4 && log "day5_flat_ab_ep2b.mp4 (current | flat palette)"
ffmpeg -v error -y -ss 1.0 -i $R/day5_flat_ab_ep2b.mp4 -frames:v 1 $R/day5_flat_ab_ep2b.png
rm -rf $W/flat_cur $W/flat_flat; bash /workspace/export_outcomes.sh 2>&1 | tail -1; log "FLAT AB DONE"
