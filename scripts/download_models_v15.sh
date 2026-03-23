#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "=== Downloading HunyuanVideo 1.5 Models ==="
echo "Total download: ~15GB. Ensure you have enough disk space."
echo ""

# --- DiT (GGUF weights - 480p distilled, best for 8GB VRAM) ---
echo "=== [1/4] DiT GGUF Q4_K_S - 480p CFG-distilled (~5GB) ==="
UNET_DIR="$ROOT/ComfyUI/models/unet"
GGUF_FILE="hunyuanvideo1.5_480p_t2v_cfg_distilled-Q4_K_S.gguf"
if [ -f "$UNET_DIR/$GGUF_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('jayn7/HunyuanVideo-1.5_T2V_480p-GGUF',
    filename='480p_distilled/$GGUF_FILE',
    local_dir='$UNET_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    # Move from subdirectory to unet root if needed
    if [ -f "$UNET_DIR/480p_distilled/$GGUF_FILE" ]; then
        mv "$UNET_DIR/480p_distilled/$GGUF_FILE" "$UNET_DIR/"
        rmdir "$UNET_DIR/480p_distilled" 2>/dev/null || true
    fi
fi

# --- VAE ---
echo ""
echo "=== [2/4] VAE (HunyuanVideo 1.5) ==="
VAE_DIR="$ROOT/ComfyUI/models/vae"
VAE_FILE="hunyuanvideo15_vae_fp16.safetensors"
if [ -f "$VAE_DIR/$VAE_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',
    filename='split_files/vae/$VAE_FILE',
    local_dir='$VAE_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    # Move from subdirectory
    if [ -f "$VAE_DIR/split_files/vae/$VAE_FILE" ]; then
        mv "$VAE_DIR/split_files/vae/$VAE_FILE" "$VAE_DIR/"
        rm -rf "$VAE_DIR/split_files" 2>/dev/null || true
    fi
fi

# --- Text Encoder 1: Qwen2.5-VL FP8 ---
echo ""
echo "=== [3/4] Qwen2.5-VL-7B FP8 text encoder (~9.4GB) ==="
TE_DIR="$ROOT/ComfyUI/models/text_encoders"
QWEN_FILE="qwen_2.5_vl_7b_fp8_scaled.safetensors"
if [ -f "$TE_DIR/$QWEN_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',
    filename='split_files/text_encoders/$QWEN_FILE',
    local_dir='$TE_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    # Move from subdirectory
    if [ -f "$TE_DIR/split_files/text_encoders/$QWEN_FILE" ]; then
        mv "$TE_DIR/split_files/text_encoders/$QWEN_FILE" "$TE_DIR/"
        rm -rf "$TE_DIR/split_files" 2>/dev/null || true
    fi
fi

# --- Text Encoder 2: Glyph-ByT5 ---
echo ""
echo "=== [4/4] Glyph-ByT5 text encoder (~440MB) ==="
BYT5_FILE="byt5_small_glyphxl_fp16.safetensors"
if [ -f "$TE_DIR/$BYT5_FILE" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',
    filename='split_files/text_encoders/$BYT5_FILE',
    local_dir='$TE_DIR/',
    local_dir_use_symlinks=False)
print('Done.')
"
    # Move from subdirectory
    if [ -f "$TE_DIR/split_files/text_encoders/$BYT5_FILE" ]; then
        mv "$TE_DIR/split_files/text_encoders/$BYT5_FILE" "$TE_DIR/"
        rm -rf "$TE_DIR/split_files" 2>/dev/null || true
    fi
fi

echo ""
echo "=== All HunyuanVideo 1.5 models downloaded ==="
echo "You can now launch ComfyUI: bash scripts/launch.sh"
