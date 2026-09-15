#!/bin/bash
# LAM Audio2Expression (aigc3d, Apache-2.0): wav -> ARKit-52 curves @30fps.
# Own venv on python3.10 (README target), torch 2.1.2 cu121. Idempotent.
set -u
E=/workspace/envs/lam_a2e; R=/workspace/LAM_Audio2Expression
export HF_HOME=/workspace/hf_cache PIP_CACHE_DIR=/workspace/.pipcache
log(){ echo "[lam $(date +%H:%M:%S)] $*"; }
[ -d $R ] || git clone -q https://github.com/aigc3d/LAM_Audio2Expression.git $R
[ -x $E/bin/python ] || python3.10 -m venv $E
P=$E/bin/python
$P -m pip install -q --upgrade pip wheel setuptools
$P -m pip install -q torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cu121
cd $R
for PKG in "omegaconf==2.3.0" "addict==2.4.0" "yapf==0.40.1" "librosa==0.11.0" "transformers==4.36.2" "termcolor==3.0.1" "numpy==1.26.3" "opencv_python_headless<4.12" patool huggingface_hub matplotlib; do
  $P -m pip install -q "$PKG" || log "pip $PKG FAILED"
done
# spleeter/gradio are for the demo app only (spleeter pins an old tensorflow) — skipped
if [ ! -f pretrained_models/lam_audio2exp_streaming.tar ]; then
  HF=$E/bin/hf; [ -x $HF ] || HF=$E/bin/huggingface-cli
  $HF download 3DAIGC/LAM_audio2exp --local-dir . > /workspace/loopwork/lam_dl.log 2>&1 || log "weights download FAILED"
  [ -f LAM_audio2exp_assets.tar ] && tar -xzf LAM_audio2exp_assets.tar && rm -f LAM_audio2exp_assets.tar
  [ -f LAM_audio2exp_streaming.tar ] && tar -xzf LAM_audio2exp_streaming.tar && rm -f LAM_audio2exp_streaming.tar
fi
ls pretrained_models/ 2>/dev/null | head -3
# wav2vec2-base-960h is pulled from HF at first run; prefetch into the workspace cache
$P -c "from transformers import Wav2Vec2Model; Wav2Vec2Model.from_pretrained('facebook/wav2vec2-base-960h')" > /dev/null 2>&1 && log "wav2vec2 cached" || log "wav2vec2 prefetch failed (runtime will retry)"
$P - <<'PYX' && echo "INSTALL lam_a2e OK" || echo "INSTALL lam_a2e FAIL"
import torch, librosa, transformers, omegaconf, addict, numpy
import sys; sys.path.insert(0, "."); import engines, models, utils
print("lam imports ok torch", torch.__version__, "cuda", torch.cuda.is_available())
PYX
