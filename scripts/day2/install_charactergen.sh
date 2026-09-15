#!/bin/bash
# CharacterGen (SIGGRAPH'24) in its own venv. README says python3.9; only 3.11
# exists here — diffusers 0.24 + torch 2.5 run on 3.11 (verified by import).
set -u
E=/workspace/envs/charactergen; R=/workspace/CharacterGen
log(){ echo "[cgen $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q https://github.com/zjp-shadow/CharacterGen.git $R
[ -x $E/bin/python ] || python3.11 -m venv $E
P=$E/bin/python
$P -m pip install -q --upgrade pip wheel setuptools
$P -m pip install -q torch==2.5.1 torchvision==0.20.1 xformers==0.0.28.post3 --index-url https://download.pytorch.org/whl/cu121
cd $R
$P -m pip install -q "diffusers==0.24.0" "transformers<4.47" accelerate ipdb einops omegaconf imageio onnxruntime \
  pytorch_lightning jaxtyping wandb lpips ninja open3d trimesh pymeshlab pygltflib rm_anime_bg huggingface_hub \
  "numpy<2" opencv-python-headless
$P -m pip install -q git+https://github.com/NVlabs/nvdiffrast || log "nvdiffrast build failed"
# weights: 2D stage (SD2.1-derived MV unet + image encoder) and 3D stage (LRM)
$E/bin/huggingface-cli download --resume-download zjpshadow/CharacterGen --include "2D_Stage/*" --local-dir . > /workspace/loopwork/cg_dl2d.log 2>&1
$E/bin/huggingface-cli download --resume-download zjpshadow/CharacterGen --include "3D_Stage/*" --local-dir . > /workspace/loopwork/cg_dl3d.log 2>&1
ls 2D_Stage/models/checkpoint/pytorch_model.bin 3D_Stage/models/lrm.ckpt > /dev/null 2>&1 && log "weights present" || log "weights MISSING"
cd $R/2D_Stage && $P - <<'PY' && echo "INSTALL charactergen OK" || echo "INSTALL charactergen FAIL"
import torch, diffusers, xformers, onnxruntime
from tuneavideo.models.unet_mv2d_condition import UNetMV2DConditionModel
import sys; sys.path.insert(0, "../3D_Stage"); import lrm
print("charactergen imports ok torch", torch.__version__, "diffusers", diffusers.__version__)
PY
