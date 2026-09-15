#!/bin/bash
# DAY 1 (shift 4): craft & repairs. Diagnose P6, normal editing, adoption
# renders with verification, then the overnight sweep bank so the GPU
# stays warm. Launch: bash /workspace/go4.sh
set -u
cd /workspace/text-to-video
W=/workspace/loopwork
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
R=/workspace/review
F=scripts/blender3d/film.py
log(){ echo "[m4 $(date +%H:%M:%S)] $*"; }
export_pass(){ bash /workspace/export_outcomes.sh 2>&1 | tail -1; }

log "P1: diagnose the P6 failure — replay one verdict render VERBOSE"
mkdir -p $W/diag
CHAR_SMOOTH=40 FILM_LINES=1.4 $B -b --factory-startup /workspace/review/film_nine_waterfalls.blend \
  --python $F -- $W/diag "-14,-6,5" "0,10,1.5" 30 1 3 "orbit:26" < /dev/null > $W/diag.log 2>&1
if ls $W/diag/frame_*.png > /dev/null 2>&1; then
  log "P1: verbose replay RENDERS FINE — P6 bug was in the generated script; using inline renderer below"
else
  log "P1: replay also fails — error follows"; tail -5 $W/diag.log
fi

log "P2: NORMAL EDITING — smooth-normal transfer on both characters"
# adds a DataTransfer modifier sourcing custom normals from a heavily
# smoothed duplicate: cel bands run clean over lumpy geometry
$V - <<'PY'
import pathlib
p = pathlib.Path("scripts/blender3d/character_kit.py"); s = p.read_text()
if "CHAR_NORMALFIX" not in s:
    s = s.replace('''    if os.environ.get("CHAR_SMOOTH"):''',
'''    if os.environ.get("CHAR_NORMALFIX"):
        # anime-industry normal editing, automated: copy custom normals
        # from a blurred proxy so the shading terminator ignores lumps
        proxy = char.copy()
        proxy.data = char.data.copy()
        proxy.name = char.name + "_nproxy"
        bpy.context.scene.collection.objects.link(proxy)
        pm = proxy.modifiers.new("blur", 'SMOOTH')
        pm.factor = 1.0
        pm.iterations = 60
        dg = bpy.context.evaluated_depsgraph_get()
        pe = proxy.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(pe)
        old = proxy.data
        proxy.modifiers.clear()
        proxy.data = me
        dt = char.modifiers.new("normals", 'DATA_TRANSFER')
        dt.object = proxy
        dt.use_loop_data = True
        dt.data_types_loops = {'CUSTOM_NORMAL'}
        dt.loop_mapping = 'NEAREST_POLYNOR'
        proxy.hide_render = True
        proxy.hide_viewport = True
    if os.environ.get("CHAR_SMOOTH"):''')
    p.write_text(s)
    print("normal-editing hook installed")
else:
    print("hook already present")
PY

log "P3: adoption grid v2 — base vs stack vs stack+normals (with faces)"
turn2(){
  WHO=$1; H=$2; SM=$3; NF=$4; LN=$5; TAG=$6
  CHAR_SMOOTH=$SM CHAR_NORMALFIX=$NF FILM_LINES=$LN $B -b --factory-startup --python-expr "
import bpy, sys, math, os, mathutils
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d')
import character_kit as kit
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character('$P/${WHO}_painted.glb', '$WHO', height=$H)
if os.environ.get('FILM_LINES') and os.environ['FILM_LINES'] != '0':
    sc.render.use_freestyle = True
    sc.render.line_thickness = float(os.environ['FILM_LINES'])
    vl = sc.view_layers[0]; vl.use_freestyle = True
    ls = vl.freestyle_settings.linesets.new('c')
    ls.select_silhouette = True; ls.select_crease = True
    ls.linestyle.color = (0.06, 0.04, 0.05)
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s','SUN')); sun.data.energy=3.5
sun.data.color=(1.0,0.85,0.65)
sun.rotation_euler=(math.radians(60),0,math.radians(25)); sc.collection.objects.link(sun)
wd = bpy.data.worlds.new('w'); sc.world=wd; wd.use_nodes=True
wd.node_tree.nodes['Background'].inputs['Color'].default_value=(0.62,0.60,0.58,1)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.view_settings.view_transform='Standard'
dg = bpy.context.evaluated_depsgraph_get()
mn=mathutils.Vector((1e9,)*3); mx=mathutils.Vector((-1e9,)*3)
for c in ch.evaluated_get(dg).bound_box:
    wv=ch.matrix_world@mathutils.Vector(c)
    mn=mathutils.Vector(map(min,mn,wv)); mx=mathutils.Vector(map(max,mx,wv))
ctr=(mn+mx)/2; size=max(mx-mn)
sc.render.resolution_x=380; sc.render.resolution_y=470
a=math.radians(35)
cam.location=(ctr.x+1.9*size*math.sin(a),ctr.y-1.9*size*math.cos(a),ctr.z+0.1*size)
d=mathutils.Vector(ctr)-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
sc.render.filepath='$W/d1_${TAG}_${WHO}.png'
bpy.ops.render.render(write_still=True)
cam.data.lens=85
sc.render.resolution_x=430; sc.render.resolution_y=430
cam.location=(ctr.x, ctr.y-0.95, mx.z-0.13*size)
d=mathutils.Vector((ctr.x, ctr.y, mx.z-0.14*size))-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
sc.render.filepath='$W/d1_${TAG}_${WHO}_face.png'
bpy.ops.render.render(write_still=True)
print('D1_TURN $TAG')
" < /dev/null 2>&1 | grep -c D1_TURN || true
}
for CFG in "oisin_mv 1.75" "niamh_mv 1.68"; do
  set -- $CFG; WHO=$1; H=$2
  turn2 $WHO $H 0 "" 0 base
  turn2 $WHO $H 40 "" 1.4 stack
  turn2 $WHO $H 40 1 1.4 stacknorm
  turn2 $WHO $H 0 1 1.4 normonly
done
for WHO in oisin_mv niamh_mv; do
  ffmpeg -v error -y -i $W/d1_base_${WHO}.png -i $W/d1_stack_${WHO}.png -i $W/d1_stacknorm_${WHO}.png -i $W/d1_normonly_${WHO}.png -filter_complex hstack=4 $R/day1_stack_${WHO}.png
  ffmpeg -v error -y -i $W/d1_base_${WHO}_face.png -i $W/d1_stack_${WHO}_face.png -i $W/d1_stacknorm_${WHO}_face.png -i $W/d1_normonly_${WHO}_face.png -filter_complex hstack=4 $R/day1_faces_${WHO}.png
  log "day1 grids $WHO"
done
export_pass

log "P4: verdict renders, INLINE this time, frame-verified per shot"
for CFG in "film_shots.json film_nine_waterfalls.blend filmS" "film2_shots.json film2_first_snow.blend film2S"; do
  set -- $CFG; SJ=$1; BL=$2; TAG=$3
  $V - "$SJ" > $W/order_$TAG.txt <<'PY'
import json, sys
d = json.load(open(f"/workspace/loopwork/{sys.argv[1]}"))
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    print(s["name"], s["cam"], s["tgt"], s["lens"], f0, s["f1"], s["move"])
PY
  OK=1
  while read NAME CAM TGT LENS F0 F1 MOVE; do
    D=$W/$TAG/$NAME; rm -rf $D; mkdir -p $D
    CHAR_SMOOTH=40 CHAR_NORMALFIX=1 FILM_LINES=1.4 $B -b --factory-startup /workspace/review/$BL \
      --python $F -- $D "$CAM" "$TGT" $LENS $F0 $F1 "$MOVE" < /dev/null > /dev/null 2>&1
    N=$(ls $D/frame_*.png 2>/dev/null | wc -l)
    EXP=$((F1 - F0 + 1))
    [ "$N" -ge "$EXP" ] && log "P4 $TAG/$NAME $N/$EXP ok" || { log "P4 $TAG/$NAME FAILED $N/$EXP"; OK=0; }
  done < $W/order_$TAG.txt
  [ "$OK" = 1 ] && log "P4 $TAG complete"
done
$V scripts/blender3d/assemble_film.py $W $R/nine_waterfalls_v2cast.mp4 "The Nine Waterfalls" filmS film_shots.json film_audio && log "ep1 v2cast assembled"
$V scripts/blender3d/assemble_film.py $W $R/first_snow_v2cast.mp4 "The First Snow" film2S film2_shots.json film2_audio && log "ep2 v2cast assembled"
for FF in $R/nine_waterfalls_v2cast.mp4 $R/first_snow_v2cast.mp4; do
  [ -f $FF ] && ffmpeg -v error -y -i $FF -c:v libx264 -pix_fmt yuv420p -crf 20 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $W/x.mp4 && mv $W/x.mp4 $FF
done
export_pass

log "P5: overnight sweep bank — keep the card warm"
# line thickness in motion
for LT in 1.0 2.0; do
  D=$W/lt_$LT; rm -rf $D; mkdir -p $D
  CHAR_SMOOTH=40 CHAR_NORMALFIX=1 FILM_LINES=$LT $B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python $F -- $D "1.2,6.85,1.8" "-1.55,8.05,1.45" 55 246 330 static < /dev/null > /dev/null 2>&1
  ffmpeg -v error -y -framerate 16 -start_number 246 -i $D/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 19 $W/lt_$LT.mp4
done
ffmpeg -v error -y -i $W/lt_1.0.mp4 -i $W/clip_stack.mp4 -i $W/lt_2.0.mp4 -filter_complex "[0]scale=520:300[a];[1]scale=520:300[b];[2]scale=520:300[c];[a][b][c]hstack=3" -c:v libx264 -pix_fmt yuv420p -crf 19 $R/day1_linewidth_ab.mp4 2>/dev/null || true
# extra prop seed variants for world variety
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
for VSPEC in "tree_v4:tree:911" "bush_v3:bush:911" "rock_v3:rock:911" "stones_v2:stones:311"; do
  IFS=: read NAME BASE SHIFT <<< "$VSPEC"
  timeout 400 $V scripts/blender3d/prop_sheet.py $NAME $P/${NAME}_sheet.png $BASE $SHIFT || continue
  $V scripts/blender3d/character_from_image.py $P/${NAME}_sheet.png $P/${NAME}_shape.glb && \
  $V scripts/blender3d/paint_character.py $P/${NAME}_shape.glb $P/${NAME}_sheet.png $P/${NAME}_painted.glb && log "variant $NAME"
done
export_pass
log "DAY1 DONE — judge day1_stack_*.png, day1_faces_*.png, day1_linewidth_ab.mp4, then the v2cast episodes"
