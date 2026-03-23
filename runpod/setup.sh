#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# RunPod Setup Script
# Run this ONCE when you first create your network volume.
# After this, every new pod attached to the volume is ready to go.
# ═══════════════════════════════════════════════════════════════════

VOLUME="/workspace"  # RunPod network volume mount point
PROJECT="$VOLUME/text-to-video"

echo "═══════════════════════════════════════════════"
echo "  RunPod Setup — HunyuanVideo 1.5 Pipeline"
echo "═══════════════════════════════════════════════"

# ─── System deps ──────────────────────────────────────────────────
echo ""
echo "=== [1/6] System dependencies ==="
apt-get update -qq && apt-get install -y -qq ffmpeg git-lfs > /dev/null 2>&1
echo "  Done."

# ─── Python environment ──────────────────────────────────────────
echo ""
echo "=== [2/6] Python environment ==="
if [ ! -d "$VOLUME/venv" ]; then
    python -m venv "$VOLUME/venv"
    echo "  Created venv at $VOLUME/venv"
else
    echo "  Venv exists."
fi

source "$VOLUME/venv/bin/activate"

pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -q huggingface_hub anthropic edge-tts requests websocket-client
echo "  PyTorch + dependencies installed."

# ─── Project files ────────────────────────────────────────────────
echo ""
echo "=== [3/6] Project files ==="
if [ ! -d "$PROJECT" ]; then
    echo "  ERROR: Copy your text-to-video project to $PROJECT first."
    echo "  From your local machine:"
    echo "    rsync -avz --exclude 'ComfyUI/models' --exclude 'ComfyUI/.git' \\"
    echo "      ~/text-to-video/ runpod:$PROJECT/"
    exit 1
fi
echo "  Project found at $PROJECT"

# ─── ComfyUI ──────────────────────────────────────────────────────
echo ""
echo "=== [4/6] ComfyUI ==="
if [ ! -d "$PROJECT/ComfyUI/.git" ]; then
    git clone https://github.com/comfyanonymous/ComfyUI "$PROJECT/ComfyUI_tmp"
    cp -r "$PROJECT/ComfyUI_tmp/." "$PROJECT/ComfyUI/"
    rm -rf "$PROJECT/ComfyUI_tmp"
    echo "  Cloned ComfyUI."
else
    echo "  ComfyUI exists."
fi

cd "$PROJECT/ComfyUI"
pip install -q -r requirements.txt

# Custom nodes
cd custom_nodes
for repo in \
    "https://github.com/city96/ComfyUI-GGUF" \
    "https://github.com/kijai/ComfyUI-HunyuanVideoWrapper" \
    "https://github.com/ltdrdata/ComfyUI-Manager"; do
    name=$(basename "$repo")
    if [ ! -d "$name" ]; then
        git clone "$repo"
        [ -f "$name/requirements.txt" ] && pip install -q -r "$name/requirements.txt"
        echo "  Installed $name"
    fi
done

# Flash attention (should work on RunPod GPUs)
pip install -q flash-attn --no-build-isolation 2>/dev/null || echo "  Flash attention skipped."

echo "  ComfyUI ready."

# ─── Models ───────────────────────────────────────────────────────
echo ""
echo "=== [5/6] Models ==="
cd "$PROJECT"

UNET_DIR="$PROJECT/ComfyUI/models/unet"
VAE_DIR="$PROJECT/ComfyUI/models/vae"
TE_DIR="$PROJECT/ComfyUI/models/text_encoders"
CV_DIR="$PROJECT/ComfyUI/models/clip_vision"
mkdir -p "$UNET_DIR" "$VAE_DIR" "$TE_DIR" "$CV_DIR"

download_hf() {
    local repo="$1" file="$2" dest="$3"
    if [ -f "$dest" ]; then
        echo "  EXISTS: $(basename "$dest")"
        return
    fi
    echo "  Downloading: $(basename "$dest")..."
    python -c "
from huggingface_hub import hf_hub_download
import shutil, os
path = hf_hub_download('$repo', filename='$file')
os.makedirs(os.path.dirname('$dest'), exist_ok=True)
shutil.copy2(path, '$dest')
print('    Done.')
"
}

# T2V model — on RunPod we can use higher quality Q5_K_S
download_hf "jayn7/HunyuanVideo-1.5_T2V_480p-GGUF" \
    "480p_distilled/hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf" \
    "$UNET_DIR/hunyuanvideo1.5_480p_t2v_cfg_distilled-Q5_K_S.gguf"

# Also keep Q4_K_S for compatibility with local workflows
download_hf "jayn7/HunyuanVideo-1.5_T2V_480p-GGUF" \
    "480p_distilled/hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf" \
    "$UNET_DIR/hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf"

# I2V model
download_hf "jayn7/HunyuanVideo-1.5_I2V_480p-GGUF" \
    "480p_distilled/hunyuanvideo1.5_480p_i2v_cfg_distilled-Q5_K_S.gguf" \
    "$UNET_DIR/hunyuanvideo1.5_480p_i2v_cfg_distilled-Q5_K_S.gguf"

download_hf "jayn7/HunyuanVideo-1.5_I2V_480p-GGUF" \
    "480p_distilled/hunyuanvideo1.5_480p_i2v_cfg_distilled-Q4_K_S.gguf" \
    "$UNET_DIR/hunyuanvideo1.5_480p_i2v_cfg_distilled-Q4_K_S.gguf"

# 720p T2V model (RunPod can handle this)
download_hf "jayn7/HunyuanVideo-1.5_T2V_720p-GGUF" \
    "720p_distilled/hunyuanvideo1.5_720p_t2v_cfg_distilled-Q4_K_S.gguf" \
    "$UNET_DIR/hunyuanvideo1.5_720p_t2v_cfg_distilled-Q4_K_S.gguf"

# VAE
download_hf "Comfy-Org/HunyuanVideo_1.5_repackaged" \
    "split_files/vae/hunyuanvideo15_vae_fp16.safetensors" \
    "$VAE_DIR/hunyuanvideo15_vae_fp16.safetensors"

# Text encoders
download_hf "Comfy-Org/HunyuanVideo_1.5_repackaged" \
    "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "$TE_DIR/qwen_2.5_vl_7b_fp8_scaled.safetensors"

download_hf "Comfy-Org/HunyuanVideo_1.5_repackaged" \
    "split_files/text_encoders/byt5_small_glyphxl_fp16.safetensors" \
    "$TE_DIR/byt5_small_glyphxl_fp16.safetensors"

# CLIP Vision
download_hf "Comfy-Org/HunyuanVideo_1.5_repackaged" \
    "split_files/clip_vision/sigclip_vision_patch14_384.safetensors" \
    "$CV_DIR/sigclip_vision_patch14_384.safetensors"

echo "  All models downloaded."

# ─── LoRA training tools ─────────────────────────────────────────
echo ""
echo "=== [6/6] LoRA training tools (musubi-tuner) ==="
MUSUBI="$VOLUME/musubi-tuner"
if [ ! -d "$MUSUBI" ]; then
    git clone https://github.com/kohya-ss/musubi-tuner "$MUSUBI"
    cd "$MUSUBI"
    pip install -q -r requirements.txt
    pip install -q accelerate bitsandbytes prodigyopt
    echo "  Installed musubi-tuner."
else
    echo "  musubi-tuner exists."
fi

# ─── Full-precision model for LoRA training ──────────────────────
TRAIN_DIR="$VOLUME/training_models"
mkdir -p "$TRAIN_DIR"

echo ""
echo "  NOTE: LoRA training requires the full-precision DiT model."
echo "  Download it when you're ready to train:"
echo ""
echo "    python -c \""
echo "    from huggingface_hub import hf_hub_download"
echo "    hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',"
echo "      filename='split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors',"
echo "      local_dir='$TRAIN_DIR/')"
echo "    \""
echo ""
echo "  Size: ~16.7GB. Only needed for training, not inference."

echo ""
echo "═══════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  To start ComfyUI:"
echo "    source $VOLUME/venv/bin/activate"
echo "    cd $PROJECT/ComfyUI"
echo "    python main.py --port 8188"
echo ""
echo "  To access ComfyUI:"
echo "    Use RunPod's HTTP proxy on port 8188"
echo "═══════════════════════════════════════════════"
