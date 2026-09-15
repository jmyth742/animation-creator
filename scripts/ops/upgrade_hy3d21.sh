#!/bin/bash
# Recommendation 1+2: Hunyuan3D-2.1 upgrade, and verify/test 2.5 if its
# weights are public. Run from any fresh session: bash /workspace/upgrade_hy3d21.sh
set -u
cd /workspace/text-to-video
S=/workspace/loopwork
V=/workspace/venv/bin/python
P=series/tir-na-nog-legend/meshes/props
log(){ echo "[hy3d21 $(date +%H:%M:%S)] $*"; }

log "0: is 2.5 actually open? (records evidence, non-fatal)"
curl -s --max-time 30 "https://huggingface.co/api/models/tencent/Hunyuan3D-2.5" \
  -o $S/hy3d25_probe.json && head -c 200 $S/hy3d25_probe.json || log "2.5 probe failed"

log "1: fetch 2.1 repo + weights"
[ -d /workspace/Hunyuan3D-2.1 ] || git clone -q --depth 1 \
  https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git /workspace/Hunyuan3D-2.1
$V -c "
from huggingface_hub import snapshot_download
snapshot_download('tencent/Hunyuan3D-2.1',
                  local_dir='/workspace/training_models/hunyuan3d-2.1')
print('2.1 weights down')"

log "2: install hy3dshape/hy3dpaint (2.1 restructured the modules)"
cd /workspace/Hunyuan3D-2.1
/workspace/venv/bin/pip install -q -r requirements.txt 2>&1 | tail -1 || true
# 2.1 paint needs its own rasterizer build — same drill as 2.0:
for D in hy3dpaint/custom_rasterizer hy3dpaint/DifferentiableRenderer; do
  [ -d "$D" ] && (cd $D && $V setup.py -q install 2>&1 | tail -1) || true
done
cd /workspace/text-to-video

log "3: A/B — same MV view sets through 2.1 shape+paint"
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' \
  -d '{"unload_models":true,"free_memory":true}' > /dev/null
$V - <<'PY'
# NOTE: verify import paths against /workspace/Hunyuan3D-2.1/demo.py before
# trusting this block — the spec warned the 2.1 modules moved.
import sys, torch
sys.path.insert(0, "/workspace/Hunyuan3D-2.1")
from PIL import Image
try:
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dshape.rembg import BackgroundRemover
except ImportError:
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dgen.rembg import BackgroundRemover
rb = BackgroundRemover()
P = "series/tir-na-nog-legend/meshes/props"
R = "series/tir-na-nog-legend/reference_images"
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "/workspace/training_models/hunyuan3d-2.1")
for who, front in (("oisin", f"{R}/sheet_oisin.png"),
                   ("niamh", f"{R}/sheet_niamh.png")):
    views = {"front": rb(Image.open(front).convert("RGB")),
             "left": rb(Image.open(f"{P}/{who}_left.png").convert("RGB")),
             "back": rb(Image.open(f"{P}/{who}_back.png").convert("RGB"))}
    try:
        mesh = pipe(image=views, num_inference_steps=40,
                    generator=torch.manual_seed(6100))[0]
    except Exception:
        mesh = pipe(image=views["front"], num_inference_steps=40,
                    generator=torch.manual_seed(6100))[0]
    mesh.export(f"{P}/{who}_v21.glb")
    print("2.1 shape", who)
PY
# paint via 2.1 (PBR) — consult demo.py for the exact paint API, then:
#   hy3dpaint pipeline on {who}_v21.glb with the front sheet
# Fall back to the 2.0 painter if 2.1 paint fights the env:
for WHO in oisin niamh; do
  [ -f $P/${WHO}_v21.glb ] && \
  $V scripts/blender3d/paint_character.py $P/${WHO}_v21.glb \
     series/tir-na-nog-legend/reference_images/sheet_${WHO}.png \
     $P/${WHO}_v21_painted.glb && log "painted ${WHO}_v21 (2.0 painter fallback)"
done

log "4: QA turntables for morning judgment"
for A in oisin_v21 niamh_v21; do
  [ -f $P/${A}_painted.glb ] || continue
  /workspace/blender42/blender -b --factory-startup --python-expr "
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
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera=cam
sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=380; sc.render.resolution_y=460
sc.view_settings.view_transform='Standard'
for i,ang in enumerate([0,60,120,180,240,300]):
    a=math.radians(ang)
    cam.location=(ctr.x+1.95*size*math.sin(a),ctr.y-1.95*size*math.cos(a),ctr.z+0.12*size)
    d=mathutils.Vector(ctr)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath='$S/v21_${A}_%d.png'%i
    bpy.ops.render.render(write_still=True)
" < /dev/null > /dev/null 2>&1
  ffmpeg -v error -y -i $S/v21_${A}_0.png -i $S/v21_${A}_1.png -i $S/v21_${A}_2.png \
    -i $S/v21_${A}_3.png -i $S/v21_${A}_4.png -i $S/v21_${A}_5.png \
    -filter_complex hstack=6 /workspace/review/qa_${A}.png && log "qa_${A}"
done
log "5: face-region HD repaint on whichever mesh wins"
echo "  run: $V scripts/blender3d/face_repaint.py <painted.glb> <face.json> <height> <name>"
log "UPGRADE SCRIPT DONE — judge review/qa_*_v21.png against the mv turntables"
