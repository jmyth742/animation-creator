#!/bin/bash
# TRELLIS.2 (Microsoft, MIT) in its own venv: mirrors setup.sh without conda.
# torch 2.6.0+cu124 (nvcc 12.4 is on the box), prebuilt flash-attn wheel,
# CUDA extensions compiled for sm_86 (RTX 3090). Slow: 30-90 min of compiles.
set -u
E=/workspace/envs/trellis2; R=/workspace/TRELLIS.2; X=/workspace/loopwork/t2ext
log(){ echo "[trellis2 $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q --recursive https://github.com/microsoft/TRELLIS.2.git $R
[ -x $E/bin/python ] || python3.11 -m venv $E
P=$E/bin/python
export HF_HOME=/workspace/hf_cache PIP_CACHE_DIR=/workspace/.pipcache
export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}; [ -d /usr/local/cuda-12.4 ] && export CUDA_HOME=/usr/local/cuda-12.4
export TORCH_CUDA_ARCH_LIST="8.6"; export MAX_JOBS=32; export PATH=$CUDA_HOME/bin:$PATH
$P -m pip install -q --upgrade pip wheel setuptools ninja
$P -m pip install -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
$P -m pip install -q imageio imageio-ffmpeg tqdm easydict opencv-python-headless trimesh transformers tensorboard pandas lpips zstandard kornia timm pillow huggingface_hub
$P -m pip install -q git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8
$P -m pip install -q https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp311-cp311-linux_x86_64.whl || log "flash-attn wheel failed"
mkdir -p $X
[ -d $X/nvdiffrast ] || git clone -q -b v0.4.0 https://github.com/NVlabs/nvdiffrast.git $X/nvdiffrast
$P -c "import nvdiffrast" 2>/dev/null || $P -m pip install -q $X/nvdiffrast --no-build-isolation || log "nvdiffrast FAILED"
[ -d $X/nvdiffrec ] || git clone -q -b renderutils https://github.com/JeffreyXiang/nvdiffrec.git $X/nvdiffrec
$P -c "import nvdiffrec" 2>/dev/null || $P -m pip install -q $X/nvdiffrec --no-build-isolation || log "nvdiffrec FAILED"
[ -d $X/CuMesh ] || git clone -q --recursive https://github.com/JeffreyXiang/CuMesh.git $X/CuMesh
$P -c "import cumesh" 2>/dev/null || $P -m pip install -q $X/CuMesh --no-build-isolation || log "CuMesh FAILED"
[ -d $X/FlexGEMM ] || git clone -q --recursive https://github.com/JeffreyXiang/FlexGEMM.git $X/FlexGEMM
$P -c "import flex_gemm" 2>/dev/null || $P -m pip install -q $X/FlexGEMM --no-build-isolation || log "FlexGEMM FAILED"
rm -rf $X/o-voxel; cp -r $R/o-voxel $X/o-voxel
$P -c "import o_voxel" 2>/dev/null || $P -m pip install -q $X/o-voxel --no-build-isolation || log "o-voxel FAILED"
cd $R && $P - <<'PY' && echo "INSTALL trellis2 OK" || echo "INSTALL trellis2 FAIL"
import torch, flash_attn, nvdiffrast, cumesh, flex_gemm, o_voxel
from trellis2.pipelines import Trellis2ImageTo3DPipeline
print("trellis2 imports ok torch", torch.__version__, "cuda", torch.cuda.is_available())
PY
# weights (16GB) — pull now so inference never waits on the network
HF=$E/bin/hf; [ -x $HF ] || HF=$E/bin/huggingface-cli
$HF download microsoft/TRELLIS.2-4B > /workspace/loopwork/t2_dl.log 2>&1 && log "weights cached" || log "weights download FAILED"
