#!/bin/bash
# Overflow shift: chained after night14b. 4K-class master, DOF dialogue
# re-renders (full moving A/B), C-cams, backlot ambiences, winter QA.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
log(){ echo "[$(date +%H:%M:%S)] C $*"; }
for i in $(seq 1 840); do grep -q "NIGHT14B DONE" /workspace/night14b.log && break; sleep 60; done
log "overflow starts"

log "1: DOF dialogue re-render, full moving shots (both films)"
for FILM in "film_shots.json /workspace/review/film_nine_waterfalls.blend film_dof" "film2_shots.json /workspace/review/film2_first_snow.blend film2_dof"; do
  set -- $FILM; SJ=$1; BLEND=$2; TAG=$3
  $V - "$SJ" "$BLEND" "$TAG" <<'PY' > $S/dof_$TAG.sh
import json, sys
sj, blend, tag = sys.argv[1:4]
d = json.load(open(f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{sj}"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    if s["lens"] < 45:
        continue                      # DOF only earns its keep on the closes
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{tag}/{s['name']}"
    print(f"rm -rf {out}; mkdir -p {out}")
    print(f"FILM_DOF=2.4 /workspace/blender42/blender -b --factory-startup {blend} "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{s['cam']}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} \"{s['move']}\" < /dev/null")
print(f"echo {tag}_DONE")
PY
  bash $S/dof_$TAG.sh > $S/$TAG.log 2>&1 && log "1: $TAG done"
done
# assemble a DOF variant of ep1 (mix: dof closes over the base edit)
mkdir -p $S/film_mix && rm -rf $S/film_mix && cp -r $S/film $S/film_mix
for d in $S/film_dof/*/; do n=$(basename $d); rm -rf $S/film_mix/$n; cp -r $d $S/film_mix/$n; done
$V scripts/blender3d/assemble_film.py $S /workspace/review/nine_waterfalls_dof.mp4 "The Nine Waterfalls" film_mix film_shots.json film_audio && log "1: DOF cut assembled"

log "2: C-cam passes"
for FILM in "film_shots.json /workspace/review/film_nine_waterfalls.blend ccam_ep1" "film2_shots.json /workspace/review/film2_first_snow.blend ccam_ep2"; do
  set -- $FILM; SJ=$1; BLEND=$2; TAG=$3
  $V - "$SJ" "$BLEND" "$TAG" <<'PY' > $S/cov2_$TAG.sh
import json, sys
sj, blend, tag = sys.argv[1:4]
d = json.load(open(f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{sj}"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    cam = [float(v) for v in s["cam"].split(",")]
    tgt = [float(v) for v in s["tgt"].split(",")]
    cam2 = [cam[0] - 0.8, cam[1] + 0.25 * (tgt[1] - cam[1]), max(0.6, cam[2] - 0.8)]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/{tag}/{s['name']}"
    print(f"mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup {blend} "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{cam2[0]:.2f},{cam2[1]:.2f},{cam2[2]:.2f}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} static < /dev/null")
print(f"echo {tag}_DONE")
PY
  bash $S/cov2_$TAG.sh > $S/$TAG.log 2>&1 && log "2: $TAG done"
done

log "3: backlot ambiences (storm, cliff, ruin) 30-min"
for LOC in storm_cliffs farewell_cliff ruined_ireland; do
  [ -f $S/backlots/${LOC}_m2.2/frame_0001.png ] || continue
  ffmpeg -v error -y -framerate 16 -i $S/backlots/${LOC}_m2.2/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 21 $S/loopb_$LOC.mp4 < /dev/null
  ffmpeg -v error -y -stream_loop 350 -i $S/loopb_$LOC.mp4 -f lavfi -t 1800 -i "anoisesrc=colour=brown:amplitude=0.04,lowpass=f=220" -c:v copy -c:a aac -shortest /workspace/review/ambience_${LOC}_30min.mp4 < /dev/null && log "3: $LOC"
done

log "4: winter set QA + both-cast turntable videos"
for A in snowtree snowbush snowrock frozenwell; do
  P=series/tir-na-nog-legend/meshes/props
  [ -f $P/${A}_painted.glb ] || continue
  D=$S/tt2_$A; mkdir -p $D
  $B -b --factory-startup --python-expr "
import bpy, math, mathutils
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath='$P/${A}_painted.glb')
meshes=[o for o in sc.objects if o.type=='MESH']
mn=mathutils.Vector((1e9,)*3); mx=mathutils.Vector((-1e9,)*3)
for o in meshes:
    for c in o.bound_box:
        w=o.matrix_world@mathutils.Vector(c)
        mn=mathutils.Vector(map(min,mn,w)); mx=mathutils.Vector(map(max,mx,w))
ctr=(mn+mx)/2; size=max(mx-mn)
sun=bpy.data.objects.new('sun',bpy.data.lights.new('s','SUN')); sun.data.energy=3
sun.rotation_euler=(math.radians(55),0,math.radians(30)); sc.collection.objects.link(sun)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=sc.render.resolution_y=420
sc.view_settings.view_transform='Standard'
for i,ang in enumerate([0,60,120,180,240,300]):
    a=math.radians(ang)
    cam.location=(ctr.x+2.0*size*math.sin(a),ctr.y-2.0*size*math.cos(a),ctr.z+0.25*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath='$S/qw_${A}_%d.png'%i
    bpy.ops.render.render(write_still=True)
" < /dev/null > /dev/null 2>&1
  ffmpeg -v error -y -i $S/qw_${A}_0.png -i $S/qw_${A}_1.png -i $S/qw_${A}_2.png -i $S/qw_${A}_3.png -i $S/qw_${A}_4.png -i $S/qw_${A}_5.png -filter_complex hstack=6 /workspace/review/qa_${A}.png < /dev/null && log "4: qa_$A"
done
log "NIGHT14C DONE"
