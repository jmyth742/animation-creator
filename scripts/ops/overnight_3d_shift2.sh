#!/bin/bash
# Second shift: chains after overnight v2, fills the rest of the night.
# GPU: 2mv sweep, hi-res shape A/B, variety + new-location inventory,
#      2.5D backlot library, B-cam film coverage.
# CPU (parallel throughout): QuadriFlow remesh of every painted asset.
cd /workspace/text-to-video
S=/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad
V=/workspace/venv/bin/python
B=/workspace/blender42/blender
P=series/tir-na-nog-legend/meshes/props
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "waiting for overnight v2"
for i in $(seq 1 700); do
  grep -q "OVERNIGHT V2 DONE" /workspace/overnight_3d_v2.log && break
  sleep 60
done

# ── CPU shift starts immediately after v2: remesh everything, 2 workers ──
remesh_all(){
  for A in hall tree cross rock stones bush oisin34 niamh34; do
    [ -f $P/${A}_painted.glb ] || continue
    case $A in hall) BUDGET=18000;; oisin34|niamh34) BUDGET=22000;;
      tree|stones) BUDGET=8000;; *) BUDGET=5000;; esac
    $B -b --factory-startup --python scripts/blender3d/remesh_asset.py -- \
      $P/${A}_painted.glb $P/${A}_quad.glb $BUDGET 2>&1 | grep REMESH_DONE
  done
  log "CPU remesh shift complete"
}
remesh_all > $S/remesh.log 2>&1 &
REMESH_PID=$!

log "=== A. 2mv sweep over every sheet ==="
for A in hall tree cross rock stones bush niamh34; do
  [ -f $P/${A}_sheet.png ] || continue
  [ -d /workspace/training_models/hunyuan3d-2mv/hunyuan3d-dit-v2-mv ] || break
  $V -c "
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.rembg import BackgroundRemover
img = BackgroundRemover()(Image.open('$P/${A}_sheet.png').convert('RGB'))
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    '/workspace/training_models/hunyuan3d-2mv', subfolder='hunyuan3d-dit-v2-mv', use_safetensors=True)
mesh = pipe(image=img, num_inference_steps=30, generator=torch.manual_seed(6100))[0]
mesh.export('$P/${A}_2mv.glb')
print('2mv $A')" && log "2mv $A"
done

log "=== B. hi-res shape A/B (octree 380, 50 steps) ==="
for A in hall oisin34 niamh34; do
  [ -f $P/${A}_sheet.png ] || continue
  $V -c "
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.rembg import BackgroundRemover
img = BackgroundRemover()(Image.open('$P/${A}_sheet.png').convert('RGB'))
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    '/workspace/training_models/hunyuan3d-2', subfolder='hunyuan3d-dit-v2-0', use_safetensors=True)
mesh = pipe(image=img, num_inference_steps=50, octree_resolution=380,
            generator=torch.manual_seed(6100))[0]
mesh.export('$P/${A}_hires.glb')
print('hires $A')" && log "hires $A"
done

log "=== C. variety + new-location inventory ==="
for VSPEC in "tree_v2:tree:311" "tree_v3:tree:747" "rock_v2:rock:311" "bush_v2:bush:311"; do
  IFS=: read NAME BASE SHIFT <<< "$VSPEC"
  timeout 400 $V scripts/blender3d/prop_sheet.py $NAME $P/${NAME}_sheet.png $BASE $SHIFT || true
done
for A in ruinfort benttree seastack boat well bridge; do
  timeout 400 $V scripts/blender3d/prop_sheet.py $A $P/${A}_sheet.png || true
done
curl -s -X POST http://127.0.0.1:8188/free -H 'Content-Type: application/json' -d '{"unload_models":true,"free_memory":true}' > /dev/null
for A in tree_v2 tree_v3 rock_v2 bush_v2 ruinfort benttree seastack boat well bridge; do
  [ -f $P/${A}_sheet.png ] || continue
  $V scripts/blender3d/character_from_image.py $P/${A}_sheet.png $P/${A}_shape.glb && \
  $V scripts/blender3d/paint_character.py $P/${A}_shape.glb $P/${A}_sheet.png $P/${A}_painted.glb && \
  log "inventory $A done"
done

log "=== D. 2.5D backlot library from every location plate ==="
mkdir -p $S/backlots
for PL in series/tir-na-nog-legend/sets/*/master.png; do
  LOC=$(basename $(dirname $PL))
  $V scripts/blender3d/depth_from_plate.py $PL $S/backlots/${LOC}_depth.png || continue
  mkdir -p $S/backlots/$LOC
  $B -b --factory-startup --python scripts/blender3d/scene_from_image.py -- \
    $PL $S/backlots/${LOC}_depth.png $S/backlots/$LOC 1.6 0.3 > /dev/null 2>&1
  ffmpeg -loglevel error -framerate 16 -i $S/backlots/$LOC/frame_%04d.png \
    -c:v libx264 -pix_fmt yuv420p -crf 20 -y /workspace/review/backlot_${LOC}.mp4 && log "backlot $LOC"
done

log "=== E. B-cam coverage pass of the film ==="
mkdir -p $S/bcam
$V - <<'PY' > $S/bcam_render.sh
import json
d = json.load(open("/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/film_shots.json"))
print("set -e")
prev = 0
for s in d["shots"]:
    f0 = max(s["f0"], prev + 1)
    prev = s["f1"]
    cam = [float(v) for v in s["cam"].split(",")]
    tgt = [float(v) for v in s["tgt"].split(",")]
    # B-cam: mirrored-ish offset, slightly longer lens
    cam2 = [cam[0] + 0.35 * (tgt[0] - cam[0]) + 1.2, cam[1] + 0.35 * (tgt[1] - cam[1]) - 0.6, cam[2] + 0.25]
    out = f"/tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/bcam/{s['name']}"
    print(f"mkdir -p {out}")
    print(f"/workspace/blender42/blender -b --factory-startup /workspace/review/film_nine_waterfalls.blend "
          f"--python /workspace/text-to-video/scripts/blender3d/film.py -- {out} "
          f"\"{cam2[0]:.2f},{cam2[1]:.2f},{cam2[2]:.2f}\" \"{s['tgt']}\" {min(70, s['lens'] + 10)} {f0} {s['f1']} static")
print("echo BCAM_DONE")
PY
bash $S/bcam_render.sh > $S/bcam.log 2>&1 && log "B-cam pass done"
i=0; rm -rf $S/bcamseq; mkdir $S/bcamseq
for dir in $S/bcam/*/; do for f in $dir/frame_*.png; do i=$((i+1)); ln -s $f $S/bcamseq/b_$(printf %05d $i).png; done; done
ffmpeg -loglevel error -framerate 16 -i $S/bcamseq/b_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 22 -y /workspace/review/nine_waterfalls_bcam.mp4 && log "bcam assembled"

wait $REMESH_PID
log "SECOND SHIFT DONE"
