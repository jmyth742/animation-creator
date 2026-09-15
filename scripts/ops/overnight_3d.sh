#!/bin/bash
# Overnight: finish assets -> QA turntables -> 2mv mesh A/B -> resume the
# diffusion restoration. Each stage tolerates the previous one's failure
# except assets (everything downstream wants them).
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== 1. wait for the asset chain ==="
for i in $(seq 1 240); do
  grep -q ALL_ASSETS_DONE $S/asset_chain.log && break
  grep -q "OutOfMemoryError\|Traceback" $S/asset_chain.log && { log "chain error — restarting once"; curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' >/dev/null; bash $S/asset_chain.sh >> $S/asset_chain.log 2>&1 && break; }
  sleep 30
done
grep -c ASSET_DONE $S/asset_chain.log

log "=== 2. QA turntables ==="
P=series/tir-na-nog-legend/meshes/props
for A in oisin34 hall tree cross rock; do
  [ -f $P/${A}_painted.glb ] || continue
  $B -b --factory-startup --python-expr "
import bpy, math, mathutils
sc = bpy.context.scene
for ob in list(sc.objects): bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath='$P/${A}_painted.glb')
meshes = [o for o in sc.objects if o.type == 'MESH']
for o in meshes:
    for p in o.data.polygons: p.use_smooth = True
mn = mathutils.Vector((1e9,)*3); mx = mathutils.Vector((-1e9,)*3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
ctr = (mn+mx)/2; size = max(mx-mn)
sun = bpy.data.objects.new('sun', bpy.data.lights.new('s','SUN')); sun.data.energy=3
sun.rotation_euler=(math.radians(55),0,math.radians(30)); sc.collection.objects.link(sun)
w = bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True
w.node_tree.nodes['Background'].inputs['Color'].default_value=(0.65,0.65,0.65,1)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=sc.render.resolution_y=420
sc.view_settings.view_transform='Standard'
for i, ang in enumerate([0,60,120,180,240,300]):
    a=math.radians(ang)
    cam.location=(ctr.x+2.0*size*math.sin(a), ctr.y-2.0*size*math.cos(a), ctr.z+0.25*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath='$S/qa_${A}_%d.png' % i
    bpy.ops.render.render(write_still=True)
" > /dev/null 2>&1
  ffmpeg -loglevel error -i $S/qa_${A}_0.png -i $S/qa_${A}_1.png -i $S/qa_${A}_2.png -i $S/qa_${A}_3.png -i $S/qa_${A}_4.png -i $S/qa_${A}_5.png -filter_complex "hstack=6" -y /workspace/review/qa_${A}.png
  log "qa_${A}.png"
done

log "=== 3. Hunyuan3D-2mv A/B (best effort) ==="
$V - <<'PY' || log "2mv download failed — skipping"
from huggingface_hub import snapshot_download
snapshot_download("tencent/Hunyuan3D-2mv", local_dir="/workspace/training_models/hunyuan3d-2mv",
                  allow_patterns=["hunyuan3d-dit-v2-mv/*", "*.json", "*.md"])
print("2mv weights down")
PY
# a single-view run through the mv model still tests its geometry quality
if [ -d /workspace/training_models/hunyuan3d-2mv/hunyuan3d-dit-v2-mv ]; then
  $V - <<'PY' && log "2mv mesh done" || log "2mv inference failed — skipping"
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.rembg import BackgroundRemover
img = BackgroundRemover()(Image.open("series/tir-na-nog-legend/meshes/props/oisin34_sheet.png").convert("RGB"))
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "/workspace/training_models/hunyuan3d-2mv", subfolder="hunyuan3d-dit-v2-mv", use_safetensors=True)
mesh = pipe(image=img, num_inference_steps=30, generator=torch.manual_seed(6100))[0]
mesh.export("series/tir-na-nog-legend/meshes/props/oisin34_2mv.glb")
PY
fi

log "=== 4. resume the classic-episode restoration ==="
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
bash /workspace/fix_tir_na_nog.sh
log "OVERNIGHT DONE"
