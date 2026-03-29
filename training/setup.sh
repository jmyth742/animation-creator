#!/usr/bin/env bash
# =============================================================================
# RunPod Bootstrap — run once after first pod creation
# Sets up musubi-tuner, downloads HunyuanVideo 1.5 weights for training
# =============================================================================
set -euo pipefail

WORKSPACE="/workspace"
TUNER_DIR="$WORKSPACE/musubi-tuner"
MODELS_DIR="$WORKSPACE/models"

echo "============================================"
echo "  HunyuanVideo 1.5 Training Environment"
echo "============================================"

# --- System deps ---
echo "[1/5] Installing system dependencies..."
apt-get update -qq && apt-get install -y -qq git git-lfs aria2 > /dev/null 2>&1
git lfs install --skip-smudge > /dev/null 2>&1

# --- Clone musubi-tuner ---
if [ ! -d "$TUNER_DIR" ]; then
    echo "[2/5] Cloning musubi-tuner..."
    cd "$WORKSPACE"
    git clone https://github.com/kohya-ss/musubi-tuner.git
    cd "$TUNER_DIR"
    pip install -r requirements.txt 2>&1 | tail -5
else
    echo "[2/5] musubi-tuner already installed, pulling latest..."
    cd "$TUNER_DIR"
    git pull
    pip install -r requirements.txt 2>&1 | tail -5
fi

# --- Install extra deps for HunyuanVideo ---
echo "[3/5] Installing additional dependencies..."
pip install accelerate wandb prodigyopt 2>&1 | tail -3

# --- Download HunyuanVideo 1.5 model weights (full precision for training) ---
mkdir -p "$MODELS_DIR"

echo "[4/5] Downloading HunyuanVideo 1.5 model weights..."
echo "       This takes a while on first run (~15-25 GB)."

# HunyuanVideo 1.5 transformer (fp16 — needed for LoRA training, not GGUF)
if [ ! -f "$MODELS_DIR/hunyuan_video_1_5_I2V_fp16.safetensors" ]; then
    echo "  -> Downloading I2V transformer (fp16)..."
    # Use HuggingFace CLI to download the I2V model
    pip install -q huggingface_hub[cli] 2>/dev/null
    python3 -c "
from huggingface_hub import hf_hub_download
import os
# Download the I2V transformer weights
hf_hub_download(
    repo_id='tencent/HunyuanVideo-I2V',
    filename='hunyuan_video_I2V_720_fp16.safetensors',
    local_dir='$MODELS_DIR',
    local_dir_use_symlinks=False,
)
print('I2V transformer downloaded.')
" 2>&1 | tail -5
else
    echo "  -> I2V transformer already present."
fi

# Text encoders
if [ ! -d "$MODELS_DIR/text_encoder" ]; then
    echo "  -> Downloading text encoders (llava-llama-3-8b-text-encoder-tokenizer)..."
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='Kijai/llava-llama-3-8b-text-encoder-tokenizer',
    local_dir='$MODELS_DIR/text_encoder',
    local_dir_use_symlinks=False,
)
print('Text encoder downloaded.')
" 2>&1 | tail -5
else
    echo "  -> Text encoder already present."
fi

# CLIP vision encoder (for I2V conditioning)
if [ ! -f "$MODELS_DIR/clip_vision/sigclip_vision_patch14_384.safetensors" ]; then
    echo "  -> Downloading CLIP vision encoder..."
    mkdir -p "$MODELS_DIR/clip_vision"
    python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='Comfy-Org/sigclip_vision_384',
    filename='sigclip_vision_patch14_384.safetensors',
    local_dir='$MODELS_DIR/clip_vision',
    local_dir_use_symlinks=False,
)
print('CLIP vision encoder downloaded.')
" 2>&1 | tail -5
else
    echo "  -> CLIP vision encoder already present."
fi

# VAE
if [ ! -f "$MODELS_DIR/hunyuan_video_vae_fp16.safetensors" ]; then
    echo "  -> Downloading VAE..."
    python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='hunyuanvideo-community/HunyuanVideo',
    filename='vae/config.json',
    local_dir='$MODELS_DIR/vae_dir',
    local_dir_use_symlinks=False,
)
hf_hub_download(
    repo_id='hunyuanvideo-community/HunyuanVideo',
    filename='vae/pytorch_model.pt',
    local_dir='$MODELS_DIR/vae_dir',
    local_dir_use_symlinks=False,
)
print('VAE downloaded.')
" 2>&1 | tail -5
else
    echo "  -> VAE already present."
fi

# --- Create convenience directories ---
echo "[5/5] Creating workspace directories..."
mkdir -p "$WORKSPACE/datasets"
mkdir -p "$WORKSPACE/outputs"
mkdir -p "$WORKSPACE/cache"

echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Tuner:   $TUNER_DIR"
echo "  Models:  $MODELS_DIR"
echo "  Outputs: $WORKSPACE/outputs"
echo ""
echo "  Next steps:"
echo "    1. Upload your dataset to $WORKSPACE/datasets/"
echo "    2. Copy a config from configs/ and edit it"
echo "    3. Run: bash train.sh <config.toml>"
echo "============================================"
