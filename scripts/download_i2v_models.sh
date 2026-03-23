#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "=== Downloading HunyuanVideo 1.5 I2V Models ==="
echo "Additional download: ~5.8GB"
echo ""

# --- I2V DiT (GGUF weights - 480p distilled) ---
echo "=== [1/2] I2V DiT GGUF Q4_K_S - 480p CFG-distilled (~5GB) ==="
UNET_DIR="$ROOT/ComfyUI/models/unet"
GGUF_FILE="hunyuanvideo1.5_480p_i2v_cfg_distilled-Q4_K_S.gguf"
if [ -f "$UNET_DIR/$GGUF_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('jayn7/HunyuanVideo-1.5_I2V_480p-GGUF',
    filename='480p_distilled/$GGUF_FILE',
    local_dir='$UNET_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    if [ -f "$UNET_DIR/480p_distilled/$GGUF_FILE" ]; then
        mv "$UNET_DIR/480p_distilled/$GGUF_FILE" "$UNET_DIR/"
        rmdir "$UNET_DIR/480p_distilled" 2>/dev/null || true
    fi
fi

# --- CLIP Vision (SigCLIP) ---
echo ""
echo "=== [2/2] SigCLIP Vision model (~857MB) ==="
CLIP_VISION_DIR="$ROOT/ComfyUI/models/clip_vision"
mkdir -p "$CLIP_VISION_DIR"
CLIP_FILE="sigclip_vision_patch14_384.safetensors"
if [ -f "$CLIP_VISION_DIR/$CLIP_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',
    filename='split_files/clip_vision/$CLIP_FILE',
    local_dir='$CLIP_VISION_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    if [ -f "$CLIP_VISION_DIR/split_files/clip_vision/$CLIP_FILE" ]; then
        mv "$CLIP_VISION_DIR/split_files/clip_vision/$CLIP_FILE" "$CLIP_VISION_DIR/"
        rm -rf "$CLIP_VISION_DIR/split_files" 2>/dev/null || true
    fi
fi

echo ""
echo "=== I2V models downloaded ==="
echo "Restart ComfyUI to pick up new models."
