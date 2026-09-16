#!/bin/bash
# CharacterGen (SIGGRAPH'24) in its own venv. README says python3.9; only 3.11
# exists here — diffusers 0.24 + torch 2.5 run on 3.11 (verified by import).
# rm_anime_bg's metadata pins <3.11 (metadata only) -> --ignore-requires-python.
set -u
E=/workspace/envs/charactergen; R=/workspace/CharacterGen
export HF_HOME=/workspace/hf_cache PIP_CACHE_DIR=/workspace/.pipcache
export CUDA_HOME=/usr/local/cuda-12.4 TORCH_CUDA_ARCH_LIST="8.6" MAX_JOBS=32 PATH=/usr/local/cuda-12.4/bin:$PATH
log(){ echo "[cgen $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q https://github.com/zjp-shadow/CharacterGen.git $R
[ -x $E/bin/python ] || python3.11 -m venv $E
P=$E/bin/python
$P -m pip install -q --upgrade pip wheel setuptools
$P -m pip install -q torch==2.5.1 torchvision==0.20.1 xformers==0.0.28.post3 --index-url https://download.pytorch.org/whl/cu121
cd $R
# one package per call so a single failure cannot abort the rest
for PKG in "huggingface_hub==0.25.2" "diffusers==0.24.0" "transformers<4.47" accelerate ipdb einops omegaconf imageio onnxruntime \
  pytorch_lightning jaxtyping wandb lpips ninja open3d trimesh pymeshlab pygltflib \
  "numpy<2" opencv-python-headless; do
  $P -m pip install -q "$PKG" || log "pip $PKG FAILED"
done
# webui.py imports gradio at module level; a stub avoids gradio's hub>=1.0 pin (breaks diffusers 0.24)
SP=$($P -c "import site; print(site.getsitepackages()[0])"); mkdir -p $SP/gradio
echo '"""stub: CharacterGen webui imports gradio at module level; the UI is never built."""' > $SP/gradio/__init__.py
$P -m pip install -q --ignore-requires-python rm_anime_bg || log "rm_anime_bg FAILED"
$P -c "import nvdiffrast" 2>/dev/null || $P -m pip install -q --no-build-isolation git+https://github.com/NVlabs/nvdiffrast || log "nvdiffrast build failed"
# weights: 2D stage (SD2.1-derived MV unet + image encoder) and 3D stage (LRM)
HF=$E/bin/hf; [ -x $HF ] || HF="$E/bin/huggingface-cli"
$HF download zjpshadow/CharacterGen --include "2D_Stage/*" --local-dir . > /workspace/loopwork/cg_dl2d.log 2>&1
$HF download zjpshadow/CharacterGen --include "3D_Stage/*" --local-dir . > /workspace/loopwork/cg_dl3d.log 2>&1
$HF download stabilityai/stable-diffusion-2-1 --include "scheduler/*" "tokenizer/*" "text_encoder/*" "vae/*" "unet/*" "*.json" > /workspace/loopwork/cg_dlsd.log 2>&1 || log "SD2.1 prefetch failed (runtime will retry)"
ls 2D_Stage/models/checkpoint/pytorch_model.bin 3D_Stage/models/lrm.ckpt > /dev/null 2>&1 && log "weights present" || log "weights MISSING"
cd $R/2D_Stage && $P - <<'PYX' && echo "INSTALL charactergen OK" || echo "INSTALL charactergen FAIL"
import torch, diffusers, xformers, onnxruntime, nvdiffrast, rm_anime_bg
from tuneavideo.models.unet_mv2d_condition import UNetMV2DConditionModel
import sys; sys.path.insert(0, "../3D_Stage"); import lrm
print("charactergen imports ok torch", torch.__version__, "diffusers", diffusers.__version__)
PYX
