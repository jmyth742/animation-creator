#!/bin/bash
# Overnight v2 — ALL 3D (user call: previous approach parked).
# assets -> extra assets -> QA -> 2mv A/B -> dressed valley stills+flythrough
# -> film draft re-render in the storybook set.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== 1. wait for the base asset chain ==="
for i in $(seq 1 200); do
  grep -q ALL_ASSETS_DONE $S/asset_chain.log && break
  sleep 30
done
grep -c ASSET_DONE $S/asset_chain.log || true

log "=== 2. extra assets: niamh34, stones, bush ==="
for A in niamh34 stones bush; do
  timeout 400 $V scripts/blender3d/prop_sheet.py $A $P/${A}_sheet.png || continue
done
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
for A in niamh34 stones bush; do
  [ -f $P/${A}_sheet.png ] || continue
  $V scripts/blender3d/character_from_image.py $P/${A}_sheet.png $P/${A}_shape.glb && \
  $V scripts/blender3d/paint_character.py $P/${A}_shape.glb $P/${A}_sheet.png $P/${A}_painted.glb && \
  log "extra asset $A done"
done

log "=== 3. QA turntables ==="
for A in oisin34 niamh34 hall tree cross rock stones bush; do
  [ -f $P/${A}_painted.glb ] || continue
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
w.node_tree.nodes['Background'].inputs['Color'].default_value=(0.65,0.65,0.65,1)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=sc.render.resolution_y=420
sc.view_settings.view_transform='Standard'
for i,ang in enumerate([0,60,120,180,240,300]):
    a=math.radians(ang)
    cam.location=(ctr.x+2.0*size*math.sin(a),ctr.y-2.0*size*math.cos(a),ctr.z+0.25*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath='$S/qa_${A}_%d.png'%i
    bpy.ops.render.render(write_still=True)
" > /dev/null 2>&1
  ffmpeg -loglevel error -i $S/qa_${A}_0.png -i $S/qa_${A}_1.png -i $S/qa_${A}_2.png -i $S/qa_${A}_3.png -i $S/qa_${A}_4.png -i $S/qa_${A}_5.png -filter_complex "hstack=6" -y /workspace/review/qa_${A}.png && log "qa_${A}"
done

log "=== 4. Hunyuan3D-2mv A/B ==="
$V -c "
from huggingface_hub import snapshot_download
snapshot_download('tencent/Hunyuan3D-2mv', local_dir='/workspace/training_models/hunyuan3d-2mv',
                  allow_patterns=['hunyuan3d-dit-v2-mv/*','*.json','*.md'])
print('2mv down')" && \
$V -c "
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.rembg import BackgroundRemover
img = BackgroundRemover()(Image.open('$P/oisin34_sheet.png').convert('RGB'))
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    '/workspace/training_models/hunyuan3d-2mv', subfolder='hunyuan3d-dit-v2-mv', use_safetensors=True)
mesh = pipe(image=img, num_inference_steps=30, generator=torch.manual_seed(6100))[0]
mesh.export('$P/oisin34_2mv.glb')
print('2mv mesh out')" && log "2mv A/B mesh done" || log "2mv skipped"

log "=== 5. the dressed valley: stills + flythrough ==="
mkdir -p $S/dressed
$B -b --factory-startup --python scripts/blender3d/build_film.py -- $S/film_audio /workspace/review/film_nine_waterfalls.blend $S/film_shots.json 2>&1 | grep -E "DRESSED|FILM SCENE SAVED"
for i in 1 2 3 4; do rm -rf $S/dv$i; mkdir -p $S/dv$i; done
$B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python scripts/blender3d/film.py -- $S/dv1 "-0.5,-12,2.2" "0,6,1.2" 35 40 40 static > /dev/null 2>&1
$B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python scripts/blender3d/film.py -- $S/dv2 "-13,-7,4.5" "0,8,1.5" 32 40 40 static > /dev/null 2>&1
$B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python scripts/blender3d/film.py -- $S/dv3 "6.8,8.8,1.65" "-0.9,7.6,1.35" 42 220 220 static > /dev/null 2>&1
$B -b --factory-startup /workspace/review/film_nine_waterfalls.blend --python scripts/blender3d/film.py -- $S/dv4 "2,16,3.2" "7.5,26,4" 40 40 40 static > /dev/null 2>&1
ffmpeg -loglevel error -i $S/dv1/*.png -i $S/dv2/*.png -i $S/dv3/*.png -i $S/dv4/*.png -filter_complex "[0]scale=700:404[a];[1]scale=700:404[b];[2]scale=700:404[c];[3]scale=700:404[d];[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack" -y /workspace/review/dressed_valley.png && log "dressed_valley.png"

log "=== 6. film draft in the storybook set ==="
bash $S/film_render6.sh > $S/film_render7.log 2>&1 || true
$V scripts/blender3d/assemble_film.py $S /workspace/review/nine_waterfalls_storybook_draft.mp4 && \
ffmpeg -v error -y -i /workspace/review/nine_waterfalls_storybook_draft.mp4 -c:v libx264 -pix_fmt yuv420p -crf 20 -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 $S/nwsb.mp4 && mv $S/nwsb.mp4 /workspace/review/nine_waterfalls_storybook_draft.mp4 && log "storybook draft assembled"
log "OVERNIGHT V2 DONE"
