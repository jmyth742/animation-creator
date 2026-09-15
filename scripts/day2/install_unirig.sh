#!/bin/bash
# UniRig in its own venv (python 3.11, torch 2.5.1 cu121 — same family as the
# main venv so the wheels are known-good on this box). Idempotent.
set -u
E=/workspace/envs/unirig; R=/workspace/UniRig
export HF_HOME=/workspace/hf_cache PIP_CACHE_DIR=/workspace/.pipcache
log(){ echo "[unirig $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q https://github.com/VAST-AI-Research/UniRig.git $R
[ -x $E/bin/python ] || python3.11 -m venv $E
P=$E/bin/python
$P -m pip install -q --upgrade pip wheel setuptools
$P -m pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
cd $R
# requirements minus flash_attn (prebuilt wheel below) and bpy (pin the 4.2 wheel)
grep -vE "^(flash_attn|bpy)" requirements.txt > /workspace/loopwork/unirig_req.txt
$P -m pip install -q -r /workspace/loopwork/unirig_req.txt
$P -m pip install -q "bpy==4.2.*" || log "bpy wheel failed (fbx export needs it)"
$P -m pip install -q https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.5cxx11abiFALSE-cp311-cp311-linux_x86_64.whl || log "flash-attn wheel failed (optional)"
$P -m pip install -q spconv-cu120
$P -m pip install -q torch_scatter torch_cluster -f https://data.pyg.org/whl/torch-2.5.1+cu121.html --no-cache-dir
$P -m pip install -q numpy==1.26.4
$P - <<'PY' && echo "INSTALL unirig OK" || echo "INSTALL unirig FAIL"
import torch, spconv, torch_scatter, torch_cluster, transformers, trimesh
print("unirig imports ok torch", torch.__version__, "cuda", torch.cuda.is_available())
import bpy; print("bpy", bpy.app.version_string)
PY
