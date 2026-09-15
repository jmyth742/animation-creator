#!/bin/bash
# Quality-research shift, chained after night14: A/B the untested levers
# and produce morning judgment sheets. All best-effort.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
ST=/workspace/review/film_nine_waterfalls.blend
F=scripts/blender3d/film.py
log(){ echo "[$(date +%H:%M:%S)] Q $*"; }

for i in $(seq 1 840); do grep -q "NIGHT14 DONE" /workspace/night14.log && break; sleep 60; done
log "quality shift starts"

log "A: DOF A/B on the dialogue close"
rm -rf $S/q_dof; mkdir -p $S/q_dof
FILM_DOF=2.2 $B -b --factory-startup $ST --python $F -- $S/q_dof "-1.6,8.5,1.75" "0.6,10.15,1.45" 55 300 316 static > /dev/null 2>&1 || \
FILM_DOF=2.2 $B -b --factory-startup $ST --python $F -- $S/q_dof "1.2,6.85,1.8" "-1.55,8.05,1.45" 55 300 316 static > /dev/null 2>&1
log "A done"

log "B: sample-count A/B (64 vs 160) on a petal wide"
rm -rf $S/q_s64 $S/q_s160; mkdir -p $S/q_s64 $S/q_s160
$B -b --factory-startup $ST --python $F -- $S/q_s64 "-0.5,-12,2.2" "0,6,1.2" 35 150 152 static > /dev/null 2>&1
FILM_SAMPLES=160 $B -b --factory-startup $ST --python $F -- $S/q_s160 "-0.5,-12,2.2" "0,6,1.2" 35 150 152 static > /dev/null 2>&1
log "B done"

log "C: Freestyle drawn-outline A/B"
rm -rf $S/q_line; mkdir -p $S/q_line
$B -b --factory-startup $ST --python-expr "
import bpy, math, mathutils, sys
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d')
sc = bpy.context.scene
sc.render.use_freestyle = True
sc.render.line_thickness = 1.6
fs = sc.view_layers[0].freestyle_settings
ls = fs.linesets.new('outline')
ls.select_silhouette = True; ls.select_border = False; ls.select_crease = False
cam = bpy.data.objects.new('qcam', bpy.data.cameras.new('qc')); cam.data.lens = 45
cam.location = (1.2, 6.85, 1.8)
d = mathutils.Vector((-1.55, 8.05, 1.45)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
sc.collection.objects.link(cam); sc.camera = cam
sc.frame_set(300)
sc.render.filepath = '$S/q_line/frame_'
bpy.ops.render.render(write_still=True)
" > /dev/null 2>&1
log "C done"

log "D: 24fps motion A/B (walk segment retimed)"
rm -rf $S/q_24; mkdir -p $S/q_24
$B -b --factory-startup $ST --python-expr "
import bpy, mathutils
sc = bpy.context.scene
sc.render.fps = 24
# stretch existing 16fps animation to 24fps timing
for ob in bpy.data.objects:
    ad = ob.animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.co.x *= 1.5
                kp.handle_left.x *= 1.5
                kp.handle_right.x *= 1.5
cam = bpy.data.objects.new('qcam', bpy.data.cameras.new('qc')); cam.data.lens = 42
cam.location = (-4.2, 0.5, 1.3)
d = mathutils.Vector((0.5, 3.0, 1.2)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
sc.collection.objects.link(cam); sc.camera = cam
sc.frame_start, sc.frame_end = 180, 285
sc.render.filepath = '$S/q_24/frame_'
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
" > /dev/null 2>&1
ffmpeg -v error -y -framerate 24 -i $S/q_24/frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 /workspace/review/quality_24fps_walk.mp4
ffmpeg -v error -y -framerate 16 -start_number 120 -i $S/film/s02_walk/frame_%04d.png -frames:v 70 -c:v libx264 -pix_fmt yuv420p -crf 20 /workspace/review/quality_16fps_walk.mp4
log "D done"

log "E: skin-heal variants for both characters"
P=series/tir-na-nog-legend/meshes/props
$V - <<'PY' > $S/skinheal.log 2>&1 || true
# soft unify pass: blur the skin patches on the painted texture, masked to
# skin-coloured pixels only, then compare renders in the morning
import numpy as np
from PIL import Image, ImageFilter
for who in ("oisin_mv", "niamh_mv"):
    p = f"series/tir-na-nog-legend/meshes/props/{who}_face_base.png"
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    skin = (r > 0.45) & (r > b) & (g > b * 0.9) & (r - g < 0.35) & (r + g + b > 1.1)
    sm = np.asarray(im.filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255
    w = (skin[..., None] * 0.55)
    out = a * (1 - w) + sm * w
    Image.fromarray((out * 255).astype(np.uint8)).save(
        f"series/tir-na-nog-legend/meshes/props/{who}_face_base_healed.png")
    print("healed", who)
PY
for WHO in oisin_mv niamh_mv; do
  H=1.75; [ "$WHO" = "niamh_mv" ] && H=1.68
  for VAR in base base_healed; do
    $B -b --factory-startup --python-expr "
import bpy, sys, math
sys.path.insert(0, '/workspace/text-to-video/scripts/blender3d')
import character_kit as kit
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
ch = kit.load_character('$P/${WHO}_painted.glb', '$WHO', height=$H)
tex = [n for n in ch.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE'][0]
tex.image = bpy.data.images.load('$P/${WHO}_face_${VAR}.png')
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s','SUN')); sun.data.energy=3
sun.rotation_euler=(math.radians(60),0,math.radians(20)); sc.collection.objects.link(sun)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); cam.data.lens=85
cam.location=(0,-1.0,1.52); cam.rotation_euler=(math.radians(90),0,0)
sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=440; sc.render.resolution_y=440
sc.view_settings.view_transform='Standard'
sc.render.filepath='$S/qh_${WHO}_${VAR}.png'
bpy.ops.render.render(write_still=True)
" > /dev/null 2>&1
  done
done
log "E done"

log "F: ep2 hi-res master"
$V - <<'PY' > $S/hires2_render.sh
import json
d = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_shots.json"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1); prev = s["f1"]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film2_hr/{s['name']}"
    print(f"rm -rf {out}; mkdir -p {out}")
    print(f"FILM_SAMPLES=128 /workspace/blender42/blender -b --factory-startup /workspace/review/film2_first_snow.blend "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{s['cam']}\" \"{s['tgt']}\" {s['lens']} {f0} {s['f1']} \"{s['move']}\" 1664 960")
print("echo HIRES2_DONE")
PY
bash $S/hires2_render.sh > $S/hires2.log 2>&1 && \
$V scripts/blender3d/assemble_film.py $S /workspace/review/first_snow_1080.mp4 "The First Snow" film2_hr film2_shots.json film2_audio && \
ffmpeg -v error -y -i /workspace/review/first_snow_1080.mp4 -c:v libx264 -pix_fmt yuv420p -crf 19 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $S/hr2.mp4 && mv $S/hr2.mp4 /workspace/review/first_snow_1080.mp4 && log "F: ep2 hi-res done"

log "G: judgment sheets"
ffmpeg -v error -y -i $S/q_dof/frame_0300.png -i $S/film/s04/frame_0300.png -filter_complex "[0]scale=700:404[a];[1]scale=700:404[b];[a][b]hstack" /workspace/review/quality_dof_ab.png 2>/dev/null || true
ffmpeg -v error -y -i $S/q_s64/frame_0150.png -i $S/q_s160/frame_0150.png -filter_complex hstack /workspace/review/quality_samples_ab.png 2>/dev/null || true
cp $S/q_line/frame_0300.png /workspace/review/quality_freestyle.png 2>/dev/null || cp $S/q_line/frame_*.png /workspace/review/quality_freestyle.png 2>/dev/null || true
ffmpeg -v error -y -i $S/qh_oisin_mv_base.png -i $S/qh_oisin_mv_base_healed.png -i $S/qh_niamh_mv_base.png -i $S/qh_niamh_mv_base_healed.png -filter_complex hstack=4 /workspace/review/quality_skinheal_ab.png 2>/dev/null || true
log "NIGHT14B DONE"
