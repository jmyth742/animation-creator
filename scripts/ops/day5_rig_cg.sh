#!/bin/bash
# Day-5 prep: UniRig-rig the CharacterGen meshes (mesh-source verdict)
set -u; export HF_HOME=/workspace/hf_cache; E=/workspace/envs/unirig; W=/workspace/loopwork; D5=$W/day5; cd /workspace/UniRig
log(){ echo "[rigcg $(date +%H:%M:%S)] $*"; }
for WHO in oisin niamh; do
  SRC=$W/day2/cg_$WHO.glb
  PATH=$E/bin:$PATH bash launch/inference/generate_skeleton.sh --input $SRC --output $D5/cg_${WHO}_skeleton.fbx > $W/rigcg_${WHO}_skel.log 2>&1 && log "skeleton $WHO" || { log "skeleton $WHO FAILED: $(grep -m1 -iE 'error' $W/rigcg_${WHO}_skel.log | cut -c1-160)"; continue; }
  PATH=$E/bin:$PATH bash launch/inference/generate_skin.sh --input $D5/cg_${WHO}_skeleton.fbx --output $D5/cg_${WHO}_skin.fbx > $W/rigcg_${WHO}_skin.log 2>&1 && log "skin $WHO" || { log "skin $WHO FAILED"; continue; }
  PATH=$E/bin:$PATH bash launch/inference/merge.sh --source $D5/cg_${WHO}_skin.fbx --target $SRC --output $D5/cg_${WHO}_rigged.glb > $W/rigcg_${WHO}_merge.log 2>&1 && log "rigged $WHO -> $D5/cg_${WHO}_rigged.glb" || log "merge $WHO FAILED"
done
cd /workspace/text-to-video
for WHO in oisin niamh; do [ -f $D5/cg_${WHO}_rigged.glb ] && /workspace/blender42/blender -b --factory-startup --python scripts/day4/rig_map.py -- $D5/cg_${WHO}_rigged.glb 2>/dev/null | grep "^MAP" | grep -v _height | sed 's/MAP //' | tr '\n' ' ' | sed "s/^/[rigcg] $WHO map: /"; echo; done
log "RIG CG DONE"
