#!/bin/bash
# MoMask (MIT) text-to-motion in its own python3.10 venv. Checkpoints from the
# HF mirror geedog/momask-codes-models (same layout as prepare/download_models.sh).
set -u
E=/workspace/envs/momask; R=/workspace/momask-codes
export HF_HOME=/workspace/hf_cache PIP_CACHE_DIR=/workspace/.pipcache
log(){ echo "[momask $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q https://github.com/EricGuo5513/momask-codes.git $R
[ -x $E/bin/python ] || python3.10 -m venv --without-pip $E
P=$E/bin/python
$P -m pip --version > /dev/null 2>&1 || curl -sS https://bootstrap.pypa.io/get-pip.py | $P - -q || { log "pip bootstrap FAILED"; exit 1; }
$P -m pip install -q --upgrade pip wheel setuptools
# the repo pins torch 1.12/cu113; torch 2.1.2 cu121 runs it fine and matches the driver
$P -m pip install -q torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu121
for PKG in "numpy<2" "einops==0.6.1" ffmpy ftfy "matplotlib<3.9" "Pillow<11" PyYAML scikit-learn scipy "smplx==0.1.28" tqdm trimesh "vector-quantize-pytorch==1.6.30" chumpy joblib huggingface_hub; do
  $P -m pip install -q "$PKG" || log "pip $PKG FAILED"
done
$P -m pip install -q git+https://github.com/openai/CLIP.git || log "CLIP FAILED"
cd $R
if [ ! -f checkpoints/t2m/t2m_nlayer8_nhead6_ld384_ff1024_cdp0.1_rvq6ns/model/latest.tar ]; then
  HF=$E/bin/hf; [ -x $HF ] || HF=$E/bin/huggingface-cli
  $HF download geedog/momask-codes-models --local-dir checkpoints > /workspace/loopwork/momask_dl.log 2>&1 || log "checkpoint download FAILED"
fi
ls checkpoints/t2m 2>/dev/null | head
$P -c "import clip; clip.load('ViT-B/32', device='cpu')" > /dev/null 2>&1 && log "CLIP ViT-B/32 cached" || log "CLIP weights prefetch failed (runtime retries)"
rm -rf $PIP_CACHE_DIR
$P - <<'PYX' && echo "INSTALL momask OK" || echo "INSTALL momask FAIL"
import torch, clip, einops, smplx, scipy, numpy
import sys; sys.path.insert(0, "."); from visualization.joints2bvh import Joint2BVHConvertor
print("momask imports ok torch", torch.__version__, "cuda", torch.cuda.is_available())
PYX
