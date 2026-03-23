#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# LoRA Training Script for HunyuanVideo 1.5
#
# Usage:
#   bash runpod/train_lora.sh /path/to/dataset my_character_name
#
# Dataset structure:
#   dataset/
#   ├── image_01.png        # Character images (15-30 recommended)
#   ├── image_01.txt        # Caption: "ohwx person, description..."
#   ├── video_01.mp4        # Optional: short video clips (2-5s)
#   ├── video_01.txt        # Caption for video
#   └── ...
#
# The script will:
#   1. Cache latents and text encoder outputs
#   2. Train a rank-32 LoRA
#   3. Convert for ComfyUI use
#   4. Copy to ComfyUI/models/loras/
# ═══════════════════════════════════════════════════════════════════

VOLUME="/workspace"
MUSUBI="$VOLUME/musubi-tuner"
PROJECT="$VOLUME/text-to-video"
TRAIN_MODELS="$VOLUME/training_models"

DATASET_DIR="${1:?Usage: train_lora.sh /path/to/dataset character_name}"
CHARACTER_NAME="${2:?Usage: train_lora.sh /path/to/dataset character_name}"

# Training config
RANK=32
ALPHA=32
LR="1e-4"
EPOCHS=150
SAVE_EVERY=25
RESOLUTION="480,320"
BLOCKS_TO_SWAP=32  # Adjust based on GPU VRAM: 32 for 24GB, 20 for 48GB

source "$VOLUME/venv/bin/activate"

echo "═══════════════════════════════════════════════"
echo "  LoRA Training: $CHARACTER_NAME"
echo "  Dataset: $DATASET_DIR"
echo "  Rank: $RANK, LR: $LR, Epochs: $EPOCHS"
echo "═══════════════════════════════════════════════"

# ─── Check full-precision model exists ────────────────────────────
DIT_PATH="$TRAIN_MODELS/split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors"
if [ ! -f "$DIT_PATH" ]; then
    echo ""
    echo "Downloading full-precision DiT model for training (~16.7GB)..."
    python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Comfy-Org/HunyuanVideo_1.5_repackaged',
    filename='split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp16.safetensors',
    local_dir='$TRAIN_MODELS/')
print('Done.')
"
fi

VAE_PATH="$PROJECT/ComfyUI/models/vae/hunyuanvideo15_vae_fp16.safetensors"
TE_PATH="$PROJECT/ComfyUI/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
BYT5_PATH="$PROJECT/ComfyUI/models/text_encoders/byt5_small_glyphxl_fp16.safetensors"

OUTPUT_DIR="$VOLUME/lora_outputs/$CHARACTER_NAME"
CACHE_DIR="$VOLUME/lora_cache/$CHARACTER_NAME"
mkdir -p "$OUTPUT_DIR" "$CACHE_DIR"

# ─── Create dataset config ───────────────────────────────────────
CONFIG_PATH="$CACHE_DIR/config.toml"
cat > "$CONFIG_PATH" << EOF
[general]
resolution = [$RESOLUTION]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true

[[datasets]]
image_directory = "$DATASET_DIR"
cache_directory = "$CACHE_DIR/latents"
num_repeats = 1
EOF

# Add video config if videos exist
if ls "$DATASET_DIR"/*.mp4 1>/dev/null 2>&1; then
    cat >> "$CONFIG_PATH" << EOF

[[datasets]]
video_directory = "$DATASET_DIR"
cache_directory = "$CACHE_DIR/latents_video"
num_repeats = 1
target_frames = [1, 25, 45]
frame_extraction = "head"
EOF
fi

echo ""
echo "=== [1/4] Caching latents ==="
cd "$MUSUBI"
python hv_1_5_cache_latents.py \
    --dataset_config "$CONFIG_PATH" \
    --vae "$VAE_PATH" \
    --vae_chunk_size 32 \
    --vae_tiling

echo ""
echo "=== [2/4] Caching text encoder outputs ==="
python hv_1_5_cache_text_encoder_outputs.py \
    --dataset_config "$CONFIG_PATH" \
    --text_encoder "$TE_PATH" \
    --byt5 "$BYT5_PATH" \
    --batch_size 16

echo ""
echo "=== [3/4] Training LoRA ==="
accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 \
    hv_1_5_train_network.py \
    --dit "$DIT_PATH" \
    --dataset_config "$CONFIG_PATH" \
    --network_module networks.lora_hv_1_5 \
    --network_dim "$RANK" \
    --network_alpha "$ALPHA" \
    --learning_rate "$LR" \
    --optimizer_type adamw8bit \
    --mixed_precision bf16 \
    --max_train_epochs "$EPOCHS" \
    --save_every_n_epochs "$SAVE_EVERY" \
    --gradient_checkpointing \
    --fp8_base \
    --blocks_to_swap "$BLOCKS_TO_SWAP" \
    --timestep_sampling shift \
    --discrete_flow_shift 2.0 \
    --weighting_scheme none \
    --sdpa \
    --split_attn \
    --output_dir "$OUTPUT_DIR" \
    --output_name "$CHARACTER_NAME"

echo ""
echo "=== [4/4] Converting for ComfyUI ==="
# Find the latest checkpoint
LATEST=$(ls -t "$OUTPUT_DIR"/"${CHARACTER_NAME}"*.safetensors 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "  ERROR: No checkpoint found."
    exit 1
fi

CONVERTED="${OUTPUT_DIR}/${CHARACTER_NAME}-comfyui.safetensors"
python convert_lora.py \
    --input "$LATEST" \
    --output "$CONVERTED" \
    --target other

# Copy to ComfyUI loras directory
LORA_DIR="$PROJECT/ComfyUI/models/loras"
mkdir -p "$LORA_DIR"
cp "$CONVERTED" "$LORA_DIR/"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Training complete!"
echo ""
echo "  LoRA: $CONVERTED"
echo "  Copied to: $LORA_DIR/$(basename "$CONVERTED")"
echo ""
echo "  To use in workflows, add LoraLoaderModelOnly node"
echo "  between UnetLoaderGGUF and the sampler."
echo ""
echo "  Strength: start at 0.7, adjust 0.5–1.0"
echo "═══════════════════════════════════════════════"
