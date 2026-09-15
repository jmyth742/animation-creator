#!/bin/bash
# Third shift: paint the A/B meshes, winter prop set, C-cam pass,
# multi-move backlots, character turntable videos.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
log(){ echo "[$(date +%H:%M:%S)] $*"; }

for i in $(seq 1 700); do
  grep -q "SECOND SHIFT DONE" /workspace/overnight_3d_shift2.log && break
  sleep 60
done
log "=== F. paint the 2mv and hires meshes for like-for-like A/B ==="
for A in oisin34 niamh34 hall tree cross rock stones bush; do
  for VAR in 2mv hires; do
    [ -f $P/${A}_${VAR}.glb ] && [ -f $P/${A}_sheet.png ] && \
      $V scripts/blender3d/paint_character.py $P/${A}_${VAR}.glb $P/${A}_sheet.png $P/${A}_${VAR}_painted.glb && log "painted ${A}_${VAR}"
  done
done

log "=== G. winter prop set ==="
for A in snowtree snowbush snowrock frozenwell; do
  timeout 400 $V scripts/blender3d/prop_sheet.py $A $P/${A}_sheet.png || true
done
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
for A in snowtree snowbush snowrock frozenwell; do
  [ -f $P/${A}_sheet.png ] || continue
  $V scripts/blender3d/character_from_image.py $P/${A}_sheet.png $P/${A}_shape.glb && \
  $V scripts/blender3d/paint_character.py $P/${A}_shape.glb $P/${A}_sheet.png $P/${A}_painted.glb && log "winter $A"
done

log "=== H. C-cam low-angle pass ==="
mkdir -p $S/ccam
$V - <<'PY' > $S/ccam_render.sh
import json
d = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film_shots.json"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    cam = [float(v) for v in s["cam"].split(",")]
    tgt = [float(v) for v in s["tgt"].split(",")]
    cam2 = [cam[0] - 0.9, cam[1] + 0.20 * (tgt[1] - cam[1]), max(0.55, cam[2] - 0.9)]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/ccam/{s['name']}"
    print(f"mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup /workspace/review/film_nine_waterfalls.blend "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{cam2[0]:.2f},{cam2[1]:.2f},{cam2[2]:.2f}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} static")
print("echo CCAM_DONE")
PY
bash $S/ccam_render.sh > $S/ccam.log 2>&1 && log "C-cam pass done"
i=0; rm -rf $S/ccamseq; mkdir $S/ccamseq
for dir in $S/ccam/*/; do for f in $dir/frame_*.png; do i=$((i+1)); ln -s $f $S/ccamseq/c_$(printf %05d $i).png; done; done
ffmpeg -loglevel error -framerate 16 -i $S/ccamseq/c_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 22 -y /workspace/review/nine_waterfalls_ccam.mp4 && log "ccam assembled"

log "=== I. multi-move backlot flythroughs ==="
for PL in series/tir-na-nog-legend/sets/*/master.png; do
  LOC=$(basename $(dirname $PL))
  [ -f $S/backlots/${LOC}_depth.png ] || continue
  for MV in "0.0:0.9" "2.2:-0.5"; do
    IFS=: read PUSH DRIFT <<< "$MV"
    D2=$S/backlots/${LOC}_m${PUSH}
    mkdir -p $D2
    $B -b --factory-startup --python scripts/blender3d/scene_from_image.py -- \
      $PL $S/backlots/${LOC}_depth.png $D2 $PUSH $DRIFT > /dev/null 2>&1
    ffmpeg -loglevel error -framerate 16 -i $D2/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 -y /workspace/review/backlot_${LOC}_v${PUSH}.mp4 && log "backlot $LOC $PUSH"
  done
done

log "=== J. character turntable videos ==="
for A in oisin34 niamh34; do
  [ -f $P/${A}_painted.glb ] || continue
  D2=$S/tt_$A; mkdir -p $D2
  $B -b --factory-startup --python-expr "
import bpy, math, mathutils
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath='$P/${A}_painted.glb')
meshes=[o for o in sc.objects if o.type=='MESH']
for o in meshes:
    for p in o.data.polygons: p.use_smooth=True
mn=mathutils.Vector((1e9,)*3); mx=mathutils.Vector((-1e9,)*3)
for o in meshes:
    for c in o.bound_box:
        w=o.matrix_world@mathutils.Vector(c)
        mn=mathutils.Vector(map(min,mn,w)); mx=mathutils.Vector(map(max,mx,w))
ctr=(mn+mx)/2; size=max(mx-mn)
sun=bpy.data.objects.new('sun',bpy.data.lights.new('s','SUN')); sun.data.energy=3
sun.rotation_euler=(math.radians(55),0,math.radians(30)); sc.collection.objects.link(sun)
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True
w.node_tree.nodes['Background'].inputs['Color'].default_value=(0.68,0.68,0.68,1)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=480; sc.render.resolution_y=640
sc.view_settings.view_transform='Standard'
sc.frame_start, sc.frame_end = 1, 96
for f in range(1, 97):
    a=math.radians(f/96*360)
    cam.location=(ctr.x+1.9*size*math.sin(a),ctr.y-1.9*size*math.cos(a),ctr.z+0.12*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    cam.keyframe_insert('location', frame=f)
    cam.keyframe_insert('rotation_euler', frame=f)
sc.render.filepath='$D2/f_'
bpy.ops.render.render(animation=True)
" > /dev/null 2>&1
  ffmpeg -loglevel error -framerate 16 -i $D2/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 -y /workspace/review/turntable_${A}.mp4 && log "turntable $A"
done
log "THIRD SHIFT DONE"
