#!/bin/bash
# MARATHON SHIFT 3 — CHARACTER QUALITY, 24 hours, four fronts at once:
#   A. line work (Freestyle outlines on the cast)
#   B. texture discipline (patchy fusion -> clean flat cel fills)
#   C. silhouette cleanup (heavy smoothing, UVs preserved)
#   D. every combination A/B'd on identical turntables + in-scene closes,
#      then the best stack re-renders both episodes
# Judgment artifacts: review/char_*  |  launch: bash /workspace/go3.sh
set -u
cd /workspace/text-to-video
W=/workspace/loopwork
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
R=/workspace/review
F=scripts/blender3d/film.py
log(){ echo "[m3 $(date +%H:%M:%S)] $*"; }
export_pass(){ bash /workspace/export_outcomes.sh 2>&1 | tail -1; }
freegpu(){ curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null; sleep 2; }

# turntable helper: WHO HEIGHT TEXTURE SMOOTH LINES TAG
turn(){
  WHO=$1; H=$2; TEX=$3; SMOOTH=$4; LINES=$5; TAG=$6
  CHAR_SMOOTH=$SMOOTH FILM_LINES=$LINES $B -b --factory-startup --python-expr "
import bpy, sys, math, os
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d')
import character_kit as kit
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character('$P/${WHO}_painted.glb', '$WHO', height=$H)
if '$TEX' != 'native':
    tex = [n for n in ch.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE'][0]
    tex.image = bpy.data.images.load('$TEX')
if os.environ.get('FILM_LINES') and os.environ['FILM_LINES'] != '0':
    sc.render.use_freestyle = True
    sc.render.line_thickness = float(os.environ['FILM_LINES'])
    vl = sc.view_layers[0]; vl.use_freestyle = True
    ls = vl.freestyle_settings.linesets.new('c')
    ls.select_silhouette = True; ls.select_crease = True; ls.select_border = False
    ls.linestyle.color = (0.06, 0.04, 0.05)
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s','SUN')); sun.data.energy=3.5
sun.data.color=(1.0,0.85,0.65)
sun.rotation_euler=(math.radians(60),0,math.radians(25)); sc.collection.objects.link(sun)
rim = bpy.data.lights.new('r','SUN'); rim.energy=1.4; rim.use_shadow=False
ro = bpy.data.objects.new('r', rim); ro.rotation_euler=(math.radians(65),0,math.radians(200))
sc.collection.objects.link(ro)
wd = bpy.data.worlds.new('w'); sc.world=wd; wd.use_nodes=True
wd.node_tree.nodes['Background'].inputs['Color'].default_value=(0.62,0.60,0.58,1)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform='Standard'
import mathutils
mn=mathutils.Vector((1e9,)*3); mx=mathutils.Vector((-1e9,)*3)
dg = bpy.context.evaluated_depsgraph_get()
for c in ch.evaluated_get(dg).bound_box:
    wv=ch.matrix_world@mathutils.Vector(c)
    mn=mathutils.Vector(map(min,mn,wv)); mx=mathutils.Vector(map(max,mx,wv))
ctr=(mn+mx)/2; size=max(mx-mn)
# full turntable + face close
sc.render.resolution_x=340; sc.render.resolution_y=430
for i,ang in enumerate([0, 45, 90, 180]):
    a=math.radians(ang)
    cam.location=(ctr.x+1.95*size*math.sin(a),ctr.y-1.95*size*math.cos(a),ctr.z+0.1*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath='$W/ct_${TAG}_${WHO}_%d.png'%i
    bpy.ops.render.render(write_still=True)
sc.render.resolution_x=420; sc.render.resolution_y=420
cam.data.lens=85
cam.location=(ctr.x, ctr.y-0.16*size*6.0, mx.z-0.13*size)
d=mathutils.Vector((ctr.x, ctr.y, mx.z-0.14*size))-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
sc.render.filepath='$W/ct_${TAG}_${WHO}_face.png'
bpy.ops.render.render(write_still=True)
print('TURN_DONE $TAG $WHO')
" < /dev/null 2>&1 | grep -c "TURN_DONE" || true
}

log "P0: baseline turntables (current look, for honest comparison)"
for CFG in "oisin_mv 1.75" "niamh_mv 1.68"; do
  set -- $CFG; turn $1 $2 native 0 0 base
done

log "P1-B: texture discipline — flatten sweep (10/14/20 colours)"
for WHO in oisin_mv niamh_mv; do
  # export the embedded texture once via blender
  $B -b --factory-startup --python-expr "
import bpy, sys
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d')
import character_kit as kit
for ob in list(bpy.context.scene.objects): bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character('$P/${WHO}_painted.glb', 'x', height=1.7)
img = [n.image for m in ch.data.materials for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image][0]
img.filepath_raw = '$W/${WHO}_native_tex.png'; img.file_format='PNG'; img.save()
print('TEX_SAVED')
" < /dev/null 2>&1 | grep -c TEX_SAVED
  for K in 10 14 20; do
    $V scripts/blender3d/flatten_texture.py $W/${WHO}_native_tex.png $W/${WHO}_flat${K}.png $K 2 && log "flat$K $WHO"
  done
done

log "P1-A/C/D: the combination grid — texture x smoothing x lines"
for CFG in "oisin_mv 1.75" "niamh_mv 1.68"; do
  set -- $CFG; WHO=$1; H=$2
  turn $WHO $H $W/${WHO}_flat14.png 0 0 flat
  turn $WHO $H native 40 0 smooth
  turn $WHO $H native 0 1.4 lines
  turn $WHO $H $W/${WHO}_flat14.png 40 1.4 stack
  turn $WHO $H $W/${WHO}_flat10.png 60 1.8 stackmax
done
for WHO in oisin_mv niamh_mv; do
  ffmpeg -v error -y -i $W/ct_base_${WHO}_1.png -i $W/ct_flat_${WHO}_1.png -i $W/ct_smooth_${WHO}_1.png -i $W/ct_lines_${WHO}_1.png -i $W/ct_stack_${WHO}_1.png -i $W/ct_stackmax_${WHO}_1.png -filter_complex hstack=6 $R/char_grid_${WHO}.png
  ffmpeg -v error -y -i $W/ct_base_${WHO}_face.png -i $W/ct_flat_${WHO}_face.png -i $W/ct_smooth_${WHO}_face.png -i $W/ct_lines_${WHO}_face.png -i $W/ct_stack_${WHO}_face.png -i $W/ct_stackmax_${WHO}_face.png -filter_complex hstack=6 $R/char_faces_${WHO}.png
  log "grids for $WHO"
done
export_pass

log "P2: the stack in MOTION — dialogue close A/B clip (base vs stack)"
for MODE in base stack; do
  SM=0; LN=0; [ "$MODE" = "stack" ] && { SM=40; LN=1.4; }
  D=$W/clip_$MODE; rm -rf $D; mkdir -p $D
  CHAR_SMOOTH=$SM FILM_LINES=$LN $B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python $F -- $D "1.2,6.85,1.8" "-1.55,8.05,1.45" 55 246 360 static < /dev/null > /dev/null 2>&1
  ffmpeg -v error -y -framerate 16 -start_number 246 -i $D/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $W/clip_$MODE.mp4
done
ffmpeg -v error -y -i $W/clip_base.mp4 -i $W/clip_stack.mp4 -filter_complex "[0]scale=700:404[a];[1]scale=700:404[b];[a][b]hstack" -c:v libx264 -pix_fmt yuv420p -crf 19 $R/char_motion_ab.mp4 && log "motion A/B"
export_pass

log "P3: apply flat textures INTO the face-variant chain (visemes on flat)"
for CFG in "oisin_mv 1.75 0.45,0.30,0.16" "niamh_mv 1.68 0.25,0.55,0.35"; do
  set -- $CFG; WHO=$1; H=$2; IRIS=$3
  FACE_BASE=$W/${WHO}_flat14.png $B -b --factory-startup \
    --python scripts/blender3d/face_paint.py -- --keep-eyes \
    $P/${WHO}_painted.glb $P/${WHO}_face.json $H $P ${WHO}_flat "$IRIS" \
    < /dev/null 2>&1 | grep -c "FACE PAINT DONE" && log "flat variants $WHO"
done
export_pass

log "P4: fixed denoise sweep (with verification this time)"
freegpu
for DN in 0.2 0.35 0.5; do
  for CFG in "oisin_mv 1.75" "niamh_mv 1.68"; do
    set -- $CFG; WHO=$1; H=$2
    OUT=$P/${WHO}_dn${DN/0./}_face_hdbase.png
    $B -b --factory-startup --python scripts/blender3d/face_repaint.py -- \
      $P/${WHO}_painted.glb $P/${WHO}_face.json $H ${WHO}_dn${DN/0./} $DN < /dev/null 2>&1 | tail -1
    [ -f "$OUT" ] && log "repaint $WHO@$DN ok" || log "repaint $WHO@$DN MISSING"
  done
done
for WHO in oisin_mv niamh_mv; do
  H=1.75; [ "$WHO" = "niamh_mv" ] && H=1.68
  ROW=""
  for VAR in dn2 dn35 dn5; do
    HD=$P/${WHO}_${VAR}_face_hdbase.png
    [ -f "$HD" ] || continue
    turn $WHO $H $HD 0 0 $VAR
    ROW="$ROW -i $W/ct_${VAR}_${WHO}_face.png"
  done
  [ -n "$ROW" ] && ffmpeg -v error -y -i $W/ct_base_${WHO}_face.png $ROW -filter_complex "hstack=inputs=$((1 + $(echo $ROW | grep -o '\-i' | wc -l)))" $R/char_denoise_${WHO}.png && log "denoise sheet $WHO"
done
export_pass

log "P5: determinism seed hunt (render same frame 2x with fixed filter seed)"
$B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python-expr "
import bpy
sc = bpy.context.scene
print('taa_samples', sc.eevee.taa_render_samples)
for attr in dir(sc.eevee):
    if 'seed' in attr.lower() or 'noise' in attr.lower():
        print('EEVEE ATTR', attr, getattr(sc.eevee, attr, None))
for attr in dir(sc.render):
    if 'seed' in attr.lower():
        print('RENDER ATTR', attr, getattr(sc.render, attr, None))
" < /dev/null 2>&1 | grep -E "ATTR|taa_samples" >> $R/sys_selftest3d.txt
log "determinism attrs recorded"

log "P6: THE VERDICT RENDER — best stack on both episodes' dialogue shots"
# conservative auto-adopt: flat14 texture + smooth40 + lines1.4 (the 'stack')
for CFG in "film_shots.json film_nine_waterfalls.blend filmS" "film2_shots.json film2_first_snow.blend film2S"; do
  set -- $CFG; SJ=$1; BL=$2; TAG=$3
  $V - "$SJ" "$BL" "$TAG" <<'PY' > $W/vr_$3.sh
import json, sys
sj, bl, tag = sys.argv[1:4]
d = json.load(open(f"/workspace/loopwork/{sj}"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    out = f"/workspace/loopwork/{tag}/{s['name']}"
    print(f"rm -rf {out}; mkdir -p {out}")
    print(f"CHAR_SMOOTH=40 FILM_LINES=1.4 /workspace/blender42/blender -b --factory-startup /workspace/review/{bl} "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{s['cam']}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} \"{s['move']}\" < /dev/null")
print(f"echo {tag}_DONE")
PY
  bash $W/vr_$TAG.sh > $W/vr_$TAG.log 2>&1 && log "$TAG rendered"
done
$V scripts/blender3d/assemble_film.py $W $R/nine_waterfalls_v2cast.mp4 "The Nine Waterfalls" filmS film_shots.json film_audio && log "ep1 v2-cast cut"
$V scripts/blender3d/assemble_film.py $W $R/first_snow_v2cast.mp4 "The First Snow" film2S film2_shots.json film2_audio && log "ep2 v2-cast cut"
for FF in $R/nine_waterfalls_v2cast.mp4 $R/first_snow_v2cast.mp4; do
  ffmpeg -v error -y -i $FF -c:v libx264 -pix_fmt yuv420p -crf 20 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $W/x.mp4 && mv $W/x.mp4 $FF
done
export_pass
log "MARATHON3 DONE — judge char_grid_*.png, char_faces_*.png, char_motion_ab.mp4, char_denoise_*.png, then the *_v2cast.mp4 episodes"
