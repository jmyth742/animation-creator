#!/bin/bash
# DAY 2 (shift 5). Day-1 completion (verdict masters with the ADOPTED stack)
# runs on CPU/GPU while the Day-2 model installs run on CPU/network; then the
# Day-2 A/Bs (UniRig walk test, CharacterGen + TRELLIS.2 vs current cast),
# then the sweep bank. Launch: bash /workspace/go5.sh
set -u
cd /workspace/text-to-video
W=/workspace/loopwork; V=/workspace/venv/bin/python; B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props; R=/workspace/review; D2=$W/day2; mkdir -p $D2
log(){ echo "[m5 $(date +%H:%M:%S)] $*"; }
export_pass(){ bash /workspace/export_outcomes.sh 2>&1 | tail -1; }
free_gpu(){ curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null; sleep 5; }
# THE ADOPTED DAY-1 STACK (judged from review/day1b_*, day1c_*, day1d_*):
#   normal editing on (interpolated), NO Laplacian smooth (it shreds the mesh),
#   silhouette-only lines at 2.0 px, crease off, chains < 20 px dropped.
export CHAR_NORMALFIX=1 CHAR_NORMALFIX_INTERP=1 FILM_LINES=4.0 FILM_LINE_MINLEN=20 FILM_LINE_CREASE=0
unset CHAR_SMOOTH

log "P0: waiting for marathon4 (Day-1 sweep bank) to release the GPU"
while [ -f /workspace/marathon4.pid ] && ps -p "$(cat /workspace/marathon4.pid)" > /dev/null 2>&1; do sleep 30; done
free_gpu; log "P0: GPU after free: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"

log "P1: Day-1 verdict masters with the adopted stack — background, 6 shots in parallel"
(
  bash scripts/ops/render_episode.sh film_shots.json film_nine_waterfalls.blend filmS "The Nine Waterfalls" film_audio $R/nine_waterfalls_v2cast.mp4 6
  bash scripts/ops/render_episode.sh film2_shots.json film2_first_snow.blend film2S "The First Snow" film2_audio $R/first_snow_v2cast.mp4 6
  bash /workspace/export_outcomes.sh 2>&1 | tail -1
  # Day-1 sweep: line weight IN MOTION (1.4 / 2.0 / 2.6) on the dialogue close
  for LT in 1.4 2.0 2.6; do
    D=$W/lt_$LT; rm -rf $D; mkdir -p $D
    FILM_LINES=$LT $B -b --factory-startup $R/film_nine_waterfalls.blend --python scripts/blender3d/film.py -- $D "1.2,6.85,1.8" "-1.55,8.05,1.45" 55 246 330 static < /dev/null > $D.log 2>&1 &
  done; wait
  for LT in 1.4 2.0 2.6; do ffmpeg -v error -y -framerate 16 -start_number 246 -i $W/lt_$LT/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $W/lt_$LT.mp4; done
  ffmpeg -v error -y -i $W/lt_1.4.mp4 -i $W/lt_2.0.mp4 -i $W/lt_2.6.mp4 -filter_complex "[0]scale=520:300[a];[1]scale=520:300[b];[2]scale=520:300[c];[a][b][c]hstack=3" -c:v libx264 -pix_fmt yuv420p -crf 19 $R/day1_linewidth_ab.mp4 && echo "[m5 $(date +%H:%M:%S)] day1_linewidth_ab.mp4 done (1.4 | 2.0 | 2.6)"
  bash /workspace/export_outcomes.sh 2>&1 | tail -1
) > $W/m5_render.log 2>&1 &
RENDER_PID=$!

log "P2: Day-2 installs in parallel (own venvs under /workspace/envs): UniRig, CharacterGen, TRELLIS.2"
bash scripts/day2/install_unirig.sh       > $W/m5_install_unirig.log 2>&1 &
bash scripts/day2/install_charactergen.sh > $W/m5_install_cg.log 2>&1 &
bash scripts/day2/install_trellis2.sh     > $W/m5_install_t2.log 2>&1 &
wait $RENDER_PID
log "P1 done: $(grep -c ': master ' $W/m5_render.log) masters; $(grep -c FAILED $W/m5_render.log) shot failures logged"
grep -E ": master |NOT assembling|linewidth" $W/m5_render.log
wait
for L in unirig cg t2; do log "install $L: $(grep -E '^INSTALL' $W/m5_install_$L.log | tail -1)"; done
export_pass

log "P4: UniRig — auto-rig both leads, prove the rig animates in Blender (walk test)"
if grep -q "INSTALL unirig OK" $W/m5_install_unirig.log; then
  E=/workspace/envs/unirig; cd /workspace/UniRig
  for WHO in oisin_mv niamh_mv; do
    SRC=/workspace/text-to-video/$P/${WHO}_painted.glb
    PATH=$E/bin:$PATH bash launch/inference/generate_skeleton.sh --input $SRC --output $D2/${WHO}_skeleton.fbx > $W/unirig_${WHO}_skel.log 2>&1 \
      && log "unirig skeleton $WHO" || log "unirig skeleton $WHO FAILED: $(grep -m1 -iE 'error' $W/unirig_${WHO}_skel.log | cut -c1-160)"
    PATH=$E/bin:$PATH bash launch/inference/generate_skin.sh --input $D2/${WHO}_skeleton.fbx --output $D2/${WHO}_skin.fbx > $W/unirig_${WHO}_skin.log 2>&1 \
      && log "unirig skin $WHO" || log "unirig skin $WHO FAILED: $(grep -m1 -iE 'error' $W/unirig_${WHO}_skin.log | cut -c1-160)"
    PATH=$E/bin:$PATH bash launch/inference/merge.sh --source $D2/${WHO}_skin.fbx --target $SRC --output $D2/${WHO}_rigged.glb > $W/unirig_${WHO}_merge.log 2>&1 \
      && log "unirig merged $WHO -> $D2/${WHO}_rigged.glb" || log "unirig merge $WHO FAILED"
    if [ -f $D2/${WHO}_rigged.glb ]; then
      $B -b --factory-startup --python /workspace/text-to-video/scripts/day2/rig_test.py -- $D2/${WHO}_rigged.glb $D2/rig_$WHO $WHO < /dev/null > $W/rigtest_$WHO.log 2>&1
      grep -E "^RIG" $W/rigtest_$WHO.log
      ffmpeg -v error -y -framerate 16 -i $D2/rig_$WHO/${WHO}_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $R/day2_unirig_walk_$WHO.mp4 && log "day2_unirig_walk_$WHO.mp4"
      cp $D2/rig_$WHO/${WHO}_0007.png $R/day2_unirig_pose_$WHO.png 2>/dev/null
    fi
  done
  cd /workspace/text-to-video
else log "P4 skipped: UniRig install failed"; fi
export_pass

log "P5: CharacterGen — anime-native image->3D on both leads' sheets; A/B vs current cast"
if grep -q "INSTALL charactergen OK" $W/m5_install_cg.log; then
  E=/workspace/envs/charactergen
  for CFG in "oisin 1.75" "niamh 1.68"; do set -- $CFG; WHO=$1; H=$2
    $E/bin/python scripts/day2/cg_infer.py $P/${WHO}34_sheet.png $D2/cg_$WHO > $W/cg_$WHO.log 2>&1 \
      && log "charactergen $WHO -> $D2/cg_$WHO/output.glb" || { log "charactergen $WHO FAILED: $(grep -m1 -iE 'error' $W/cg_$WHO.log | cut -c1-160)"; continue; }
    cp $D2/cg_$WHO/views.png $R/day2_charactergen_views_$WHO.png
    cp $D2/cg_$WHO/output.glb $D2/cg_$WHO.glb
    $B -b --factory-startup --python scripts/blender3d/turn_grid.py -- $D2/cg_$WHO.glb $H $D2 ab < /dev/null > $W/cg_turn_$WHO.log 2>&1
    $B -b --factory-startup --python scripts/blender3d/turn_grid.py -- ${WHO}_mv $H $D2 ab < /dev/null > $W/cur_turn_$WHO.log 2>&1
    ffmpeg -v error -y -i $D2/ab_${WHO}_mv.png -i $D2/ab_cg_$WHO.png -filter_complex hstack=2 $R/day2_charactergen_ab_$WHO.png
    ffmpeg -v error -y -i $D2/ab_${WHO}_mv_face.png -i $D2/ab_cg_${WHO}_face.png -filter_complex hstack=2 $R/day2_charactergen_ab_faces_$WHO.png && log "day2_charactergen_ab_$WHO (current | CharacterGen)"
  done
else log "P5 skipped: CharacterGen install failed"; fi
export_pass

log "P6: TRELLIS.2 — leads + hero props vs Hunyuan (needs the whole card)"
if grep -q "INSTALL trellis2 OK" $W/m5_install_t2.log; then
  free_gpu; E=/workspace/envs/trellis2; cd /workspace/TRELLIS.2
  ITEMS="oisin34_sheet:oisin:1.75 niamh34_sheet:niamh:1.68 hall_sheet:hall:6 benttree_sheet:benttree:5"
  for ITEM in $ITEMS; do IFS=: read SHEET NAME H <<< "$ITEM"
    $E/bin/python /workspace/text-to-video/scripts/day2/trellis_infer.py /workspace/text-to-video/$P/$SHEET.png $D2/t2_$NAME.glb 200000 > $W/t2_$NAME.log 2>&1 \
      && log "trellis2 $NAME -> $D2/t2_$NAME.glb" || log "trellis2 $NAME FAILED: $(grep -m1 -iE 'error|out of memory' $W/t2_$NAME.log | cut -c1-160)"
    [ -f $D2/t2_${NAME}_turn.mp4 ] && cp $D2/t2_${NAME}_turn.mp4 $R/day2_trellis_pbr_$NAME.mp4
  done
  cd /workspace/text-to-video
  for ITEM in $ITEMS; do IFS=: read SHEET NAME H <<< "$ITEM"
    [ -f $D2/t2_$NAME.glb ] || continue
    $B -b --factory-startup --python scripts/blender3d/turn_grid.py -- $D2/t2_$NAME.glb $H $D2 ab < /dev/null > $W/t2_turn_$NAME.log 2>&1
    CUR=""; [ -f $D2/ab_${NAME}_mv.png ] && CUR=$D2/ab_${NAME}_mv.png
    if [ -z "$CUR" ] && [ -f $P/${NAME}_painted.glb ]; then
      $B -b --factory-startup --python scripts/blender3d/turn_grid.py -- $P/${NAME}_painted.glb $H $D2 ab < /dev/null > $W/cur_turn_$NAME.log 2>&1
      CUR=$D2/ab_${NAME}_painted.png
    fi
    if [ -n "$CUR" ] && [ -f "$CUR" ]; then ffmpeg -v error -y -i $CUR -i $D2/ab_t2_$NAME.png -filter_complex hstack=2 $R/day2_trellis_ab_$NAME.png
    else cp $D2/ab_t2_$NAME.png $R/day2_trellis_ab_$NAME.png; fi
    log "day2_trellis_ab_$NAME.png (current | TRELLIS.2)"
  done
else log "P6 skipped: TRELLIS.2 install failed — see $W/m5_install_t2.log"; fi
export_pass

log "P7: sweep bank — prop seed variants keep the card warm while verdicts await judgment"
free_gpu
for VSPEC in "hall_v2:hall:1213" "benttree_v2:benttree:1213" "boat_v2:boat:1213"; do
  IFS=: read NAME BASE SHIFT <<< "$VSPEC"
  timeout 400 $V scripts/blender3d/prop_sheet.py $NAME $P/${NAME}_sheet.png $BASE $SHIFT || continue
  $V scripts/blender3d/character_from_image.py $P/${NAME}_sheet.png $P/${NAME}_shape.glb && \
  $V scripts/blender3d/paint_character.py $P/${NAME}_shape.glb $P/${NAME}_sheet.png $P/${NAME}_painted.glb && log "variant $NAME"
done
export_pass
log "DAY2 DONE — judge: nine_waterfalls_v2cast.mp4, first_snow_v2cast.mp4, day1_linewidth_ab.mp4, day2_unirig_walk_*.mp4, day2_charactergen_ab_*.png, day2_trellis_ab_*.png"
