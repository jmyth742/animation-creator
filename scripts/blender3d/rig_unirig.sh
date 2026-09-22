#!/bin/bash
# Rig a mesh with UniRig: extract -> skeleton -> skin -> merge.
# UniRig is template-free, so it handles a chibi build as readily as a realistic one,
# which is why it suits generated characters.
#
# PATHS MATTER HERE. UniRig derives its intermediate npz location from the INPUT path,
# so a nested relative path makes the skin stage look for raw_data.npz under a directory
# the extract stage never created, and the merge then silently produces nothing. Work
# from a flat copy inside the UniRig tree and copy the result back.
set -u
IN=$(readlink -f "$1"); OUT=$(readlink -f "$2")
[ -f "$IN" ] || { echo "RIGWRAP: no input $IN"; exit 1; }
cd /workspace/UniRig
PY=/workspace/envs/unirig/bin/python
export PATH=/workspace/envs/unirig/bin:$PATH
NAME=rigin
WORK=/workspace/UniRig/rigwork
rm -rf "$WORK"; mkdir -p "$WORK"
cp "$IN" "$WORK/$NAME.glb"
log(){ echo "[rig $(date +%H:%M:%S)] $*"; }
L=/workspace/loopwork
log "extract mesh"
bash launch/inference/extract.sh --input "rigwork/$NAME.glb" >$L/rig_extract.log 2>&1 \
  || { log "extract FAILED: $(tail -3 $L/rig_extract.log | tr '\n' ' ' | cut -c1-200)"; exit 1; }
log "skeleton"
bash launch/inference/generate_skeleton.sh --input "rigwork/$NAME.glb" --output "rigwork/skel.fbx" >$L/rig_skel.log 2>&1 \
  || { log "skeleton FAILED: $(tail -3 $L/rig_skel.log | tr '\n' ' ' | cut -c1-200)"; exit 1; }
[ -f rigwork/skel.fbx ] || { log "skeleton produced no fbx"; exit 1; }
# The skin stage must be fed the PREDICTED SKELETON, not the original mesh. Given the mesh
# it reads raw_data.npz, which carries no joints, and dies with "unsupported operand
# NoneType - float". The launch scripts never write a skeleton npz because run.py flips
# into user_mode whenever an output path is given, and user_mode skips the npz export.
log "extract skeleton"
bash launch/inference/extract.sh --input "rigwork/skel.fbx" >$L/rig_ex2.log 2>&1 \
  || { log "extract(skel) FAILED"; exit 1; }
log "skin"
bash launch/inference/generate_skin.sh --input "rigwork/skel.fbx" --output "rigwork/skin.fbx" >$L/rig_skin.log 2>&1 \
  || { log "skin FAILED: $(tail -3 $L/rig_skin.log | tr '\n' ' ' | cut -c1-200)"; exit 1; }
[ -f rigwork/skin.fbx ] || { log "skin produced no fbx"; exit 1; }
log "merge"
bash launch/inference/merge.sh --source "rigwork/skin.fbx" --target "rigwork/$NAME.glb" --output "rigwork/rigged.glb" >$L/rig_merge.log 2>&1 \
  || { log "merge FAILED: $(tail -3 $L/rig_merge.log | tr '\n' ' ' | cut -c1-200)"; exit 1; }
if [ -f "rigwork/rigged.glb" ]; then
  cp "rigwork/rigged.glb" "$OUT"; log "RIGWRAP_DONE $OUT"
else
  log "RIGWRAP FAILED: merge produced nothing"; exit 1
fi
