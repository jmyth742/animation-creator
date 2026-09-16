#!/bin/bash
# CharacterGen leads: auto face calibration -> face_paint variants -> rigged check render
set -u; cd /workspace/text-to-video; W=/workspace/loopwork; R=/workspace/review; B=/workspace/blender42/blender; P=series/tir-na-nog-legend/meshes/props; D5=$W/day5
log(){ echo "[cgface $(date +%H:%M:%S)] $*"; }
for CFG in "oisin 1.75 0.35,0.2,0.1 " "niamh 1.68 0.2,0.6,0.35 --keep-eyes"; do set -- $CFG; WHO=$1; H=$2; IRIS=$3; KEEP=${4:-}
  cp $D5/../day2/cg_$WHO.glb $P/cg_${WHO}_painted.glb
  CHAR_YAW=180 $B -b --factory-startup --python-expr "
import bpy, sys, json
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d'); import character_kit as kit
for ob in list(bpy.context.scene.objects): bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character('$P/cg_${WHO}_painted.glb', 'cg_$WHO', height=$H)
a = kit.probe_face(ch)
calib = {'mouth_z': a['mouth'][2], 'eye_z': a['eye_L'][2], 'eye_x': a['eye_L'][0], 'face_x': 0.0}
json.dump(calib, open('$D5/cg_${WHO}_calib.json', 'w')); print('CALIB', calib)
" < /dev/null 2>&1 | grep CALIB
  CHAR_YAW=180 $B -b --factory-startup --python scripts/blender3d/face_paint.py -- $KEEP $P/cg_${WHO}_painted.glb $D5/cg_${WHO}_calib.json $H $P cg_$WHO $IRIS < /dev/null > $W/cg_facepaint_$WHO.log 2>&1
  N=$(ls $P/cg_${WHO}_face_*.png 2>/dev/null | wc -l); log "face variants $WHO: $N files $(grep -m1 -iE 'error|Traceback' $W/cg_facepaint_$WHO.log | cut -c1-120)"
  [ "$N" -ge 7 ] || continue
  $B -b --factory-startup --python scripts/day5/cg_face_check.py -- $D5/cg_${WHO}_rigged.glb cg_$WHO $H $P $D5/cgface_$WHO.png < /dev/null > $W/cg_facecheck_$WHO.log 2>&1
  ffmpeg -v error -y -i $D5/cgface_${WHO}_base.png -i $D5/cgface_${WHO}_m3.png -i $D5/cgface_${WHO}_blink.png -filter_complex hstack=3 $R/day5_cg_faces_$WHO.png && log "day5_cg_faces_$WHO.png (base | open | blink)"
done
bash /workspace/export_outcomes.sh 2>&1 | tail -1; log "CG FACES DONE"
