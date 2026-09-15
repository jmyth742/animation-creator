#!/bin/bash
# DAY 3 (shift 6): the facial acting chain. OmniFaceRig has no code and
# NVIDIA's A2F-3D SDK is C++/TensorRT-10.13 (CUDA 12.8; this box is 12.4),
# so the chain is LAM Audio2Expression (Apache-2.0, python): wav -> ARKit-52
# curves @30fps, bridged onto our per-line texture visemes, judged A/B
# against Rhubarb in the dialogue closes of both episodes.
# Launch: bash /workspace/go6.sh
set -u
cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender
R=/workspace/review; D3=$W/day3; mkdir -p $D3; E=/workspace/envs/lam_a2e
log(){ echo "[m6 $(date +%H:%M:%S)] $*"; }
export_pass(){ bash /workspace/export_outcomes.sh 2>&1 | tail -1; }
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=2.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0; unset CHAR_SMOOTH

log "P1: install LAM Audio2Expression (own venv, python3.10)"
bash scripts/day3/install_lam_a2e.sh > $W/m6_install_lam.log 2>&1
log "P1: $(grep -E '^INSTALL' $W/m6_install_lam.log | tail -1)"
grep -q "INSTALL lam_a2e OK" $W/m6_install_lam.log || { log "DAY3 ABORT: LAM install failed — see $W/m6_install_lam.log"; tail -20 $W/m6_install_lam.log; exit 1; }
export_pass

log "P2: ARKit curves for every line of both episodes"
for EP in film_audio film2_audio; do
  $E/bin/python scripts/day3/lam_lines.py $W/$EP $D3/$EP > $W/m6_lam_$EP.log 2>&1; grep -E "LAM " $W/m6_lam_$EP.log
done
export_pass

log "P3: bridge ARKit -> texture visemes (l<i>_vis_lam.npy, _env_lam, _blink_lam) + curve sheets"
for EP in film_audio film2_audio; do
  $V scripts/day3/arkit_bridge.py $W/$EP $D3/$EP 16 2>&1 | tee $W/m6_bridge_$EP.log | grep -vE "^$"
  for f in $D3/$EP/l*_curves.png; do [ -f "$f" ] && cp "$f" $R/day3_curves_${EP%_audio}_$(basename $f); done
done
# one sheet per episode: all lines stacked
for EP in film_audio film2_audio; do
  ls $D3/$EP/l*_curves.png > /dev/null 2>&1 && ffmpeg -v error -y $(for f in $D3/$EP/l*_curves.png; do echo -n "-i $f "; done) -filter_complex "vstack=inputs=$(ls $D3/$EP/l*_curves.png | wc -l)" $R/day3_arkit_curves_${EP%_audio}.png
done
export_pass

log "P4: A/B blends with LAM visemes, render the first dialogue close of each episode (Rhubarb | LAM)"
FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam $B -b --factory-startup --python scripts/blender3d/build_film.py -- $W/film_audio $R/film_nine_waterfalls_lam.blend $W/film_shots_lam.json < /dev/null > $W/m6_build1.log 2>&1; grep -c "FILM SCENE SAVED" $W/m6_build1.log
FILM_VIS_SUFFIX=_lam FILM_ENV_SUFFIX=_lam $B -b --factory-startup --python scripts/blender3d/build_film2.py -- $W/film2_audio $R/film2_first_snow_lam.blend $W/film2_shots_lam.json < /dev/null > $W/m6_build2.log 2>&1; grep -c "FILM SCENE SAVED" $W/m6_build2.log
ab(){  # EPTAG BLEND_BASE BLEND_LAM CAM TGT LENS F0 F1 MOVE AUDIO LINE_F0
  TAG=$1; BL0=$2; BL1=$3; CAM=$4; TGT=$5; LENS=$6; F0=$7; F1=$8; MOVE=$9; AUD=${10}; LF0=${11}
  for V2 in base lam; do D=$W/ab_${TAG}_$V2; rm -rf $D; mkdir -p $D; BL=$BL0; [ $V2 = lam ] && BL=$BL1
    FILM_RES=1248x720 $B -b --factory-startup $R/$BL --python scripts/blender3d/film.py -- $D "$CAM" "$TGT" $LENS $F0 $F1 "$MOVE" < /dev/null > $D.log 2>&1 &
  done; wait
  for V2 in base lam; do ffmpeg -v error -y -framerate 16 -start_number $F0 -i $W/ab_${TAG}_$V2/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 $W/ab_${TAG}_$V2.mp4; done
  OFF=$(python3 -c "print(($F0-$LF0)/16.0)")
  ffmpeg -v error -y -i $W/ab_${TAG}_base.mp4 -i $W/ab_${TAG}_lam.mp4 -ss $OFF -i $AUD -filter_complex "[0][1]hstack[v]" -map "[v]" -map 2:a -shortest -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac $R/day3_lipsync_ab_$TAG.mp4 && log "day3_lipsync_ab_$TAG.mp4 (Rhubarb | LAM)"
  ffmpeg -v error -y -ss 1.5 -i $R/day3_lipsync_ab_$TAG.mp4 -frames:v 1 $R/day3_lipsync_ab_$TAG.png
}
# ep1 s04: Niamh line 0 starts f246; ep2 s04: Oisin line 0 starts f246
[ -f $R/film_nine_waterfalls_lam.blend ] && ab ep1 film_nine_waterfalls.blend film_nine_waterfalls_lam.blend "1.2,6.85,1.8" "-1.55,8.05,1.45" 45 253 381 "dolly:1.035,6.922,1.779" $W/film_audio/l0.wav 246
[ -f $R/film2_first_snow_lam.blend ] && ab ep2 film2_first_snow.blend film2_first_snow_lam.blend "1.7,7.4,1.62" "-0.75,8.75,1.57" 55 253 409 "dolly:1.553,7.481,1.617" $W/film2_audio/l0.wav 246
export_pass

log "P5: sweep bank — line-accurate A/B on the SECOND line of each episode too (other character)"
[ -f $R/film_nine_waterfalls_lam.blend ] && ab ep1b film_nine_waterfalls.blend film_nine_waterfalls_lam.blend "-2.2,6.0,1.62" "-0.45,7.25,1.57" 55 398 506 "dolly:-2.095,6.075,1.617" $W/film_audio/l1.wav 391
[ -f $R/film2_first_snow_lam.blend ] && ab ep2b film2_first_snow.blend film2_first_snow_lam.blend "-1.6,8.5,1.75" "0.6,10.15,1.45" 45 426 571 "dolly:-1.468,8.599,1.732" $W/film2_audio/l1.wav 419
export_pass
log "DAY3 DONE — judge: day3_lipsync_ab_ep1.mp4, day3_lipsync_ab_ep2.mp4 (+ ep1b/ep2b), day3_arkit_curves_film*.png"
