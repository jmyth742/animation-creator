#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "=== Downloading HunyuanVideo Models ==="
echo "Total download: ~13-14GB. Ensure you have enough disk space."
echo ""

# --- DiT (GGUF weights) ---
echo "=== [1/4] DiT GGUF Q4_K_S (~7.5GB) ==="
if [ -f "$ROOT/ComfyUI/models/unet/hunyuan-video-t2v-720p-Q4_K_S.gguf" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('city96/HunyuanVideo-gguf',
    filename='hunyuan-video-t2v-720p-Q4_K_S.gguf',
    local_dir='$ROOT/ComfyUI/models/unet/')
print('Done.')
"
fi

# --- DiT Q3_K_S fallback ---
echo ""
echo "=== [2/4] DiT GGUF Q3_K_S fallback (~6GB) ==="
read -rp "Download Q3_K_S fallback weights too? [y/N] " dl_q3
if [[ "$dl_q3" =~ ^[Yy]$ ]]; then
    if [ -f "$ROOT/ComfyUI/models/unet/hunyuan-video-t2v-720p-Q3_K_S.gguf" ]; then
        echo "Already downloaded. Skipping."
    else
        python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('city96/HunyuanVideo-gguf',
    filename='hunyuan-video-t2v-720p-Q3_K_S.gguf',
    local_dir='$ROOT/ComfyUI/models/unet/')
print('Done.')
"
    fi
else
    echo "Skipping Q3_K_S."
fi

# --- VAE ---
echo ""
echo "=== [3/4] VAE ==="
VAE_DIR="$ROOT/ComfyUI/models/vae/hunyuan-video-vae"
if [ -f "$VAE_DIR/hunyuan-video-t2v-720p/vae/pytorch_model.pt" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('tencent/HunyuanVideo',
    filename='hunyuan-video-t2v-720p/vae/pytorch_model.pt',
    local_dir='$VAE_DIR/')
print('Done.')
"
fi

# --- Text Encoders ---
echo ""
echo "=== [4a/4] CLIP-L text encoder (~500MB) ==="
CLIP_DIR="$ROOT/ComfyUI/models/text_encoders/clip-vit-large-patch14"
if [ -f "$CLIP_DIR/pytorch_model.bin" ] || [ -f "$CLIP_DIR/model.safetensors" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import snapshot_download
snapshot_download('openai/clip-vit-large-patch14',
    local_dir='$CLIP_DIR/')
print('Done.')
"
fi

echo ""
echo "=== [4b/4] LLaVA LLM encoder (~5GB, offloads to CPU) ==="
LLAVA_DIR="$ROOT/ComfyUI/models/text_encoders/llava-llama-3-8b"
if [ -f "$LLAVA_DIR/config.json" ]; then
    echo "Already downloaded. Skipping."
else
    python -c "
from huggingface_hub import snapshot_download
snapshot_download('xtuner/llava-llama-3-8b-v1_1-transformers',
    local_dir='$LLAVA_DIR/')
print('Done.')
"
fi

echo ""
echo "=== All models downloaded ==="
echo "You can now launch ComfyUI: bash scripts/launch.sh"
