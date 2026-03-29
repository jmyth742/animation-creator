#!/usr/bin/env bash
# =============================================================================
# Training Runner — caches latents/text, then launches LoRA training
# Usage: bash train.sh configs/style_lora.toml
# =============================================================================
set -euo pipefail

CONFIG="${1:?Usage: bash train.sh <config.toml>}"

if [ ! -f "$CONFIG" ]; then
    echo "Error: Config file not found: $CONFIG"
    exit 1
fi

WORKSPACE="/workspace"
TUNER_DIR="$WORKSPACE/musubi-tuner"
CACHE_DIR="$WORKSPACE/cache"

# --- Parse key settings from TOML (basic extraction) ---
get_toml_value() {
    grep -m1 "^$1" "$CONFIG" | sed 's/.*=\s*"\?\([^"]*\)"\?.*/\1/' | tr -d ' '
}

DATASET_CONFIG=$(get_toml_value "dataset_config")
MODEL_PATH=$(get_toml_value "pretrained_model_name_or_path")
OUTPUT_DIR=$(get_toml_value "output_dir")

echo "============================================"
echo "  HunyuanVideo LoRA Training"
echo "  Config:  $CONFIG"
echo "  Output:  $OUTPUT_DIR"
echo "============================================"

mkdir -p "$CACHE_DIR" "$OUTPUT_DIR"

cd "$TUNER_DIR"

# --- Step 1: Cache latents ---
echo ""
echo "[1/3] Caching latents (VAE encode)..."
echo "       This pre-encodes images/video so VAE isn't needed during training."
python cache_latents.py \
    --dataset_config "$WORKSPACE/training/$DATASET_CONFIG" \
    --vae "$WORKSPACE/models/vae_dir/vae" \
    --vae_chunk_size 32 \
    --vae_tiling

# --- Step 2: Cache text encoder outputs ---
echo ""
echo "[2/3] Caching text encoder outputs..."
echo "       This pre-encodes captions so the LLM isn't needed during training."
python cache_text_encoder_outputs.py \
    --dataset_config "$WORKSPACE/training/$DATASET_CONFIG" \
    --text_encoder1 "$WORKSPACE/models/text_encoder" \
    --batch_size 1

# --- Step 3: Launch training ---
echo ""
echo "[3/3] Starting LoRA training..."
echo "       Monitor with: tail -f $OUTPUT_DIR/training.log"

accelerate launch \
    --mixed_precision bf16 \
    --num_cpu_threads_per_process 1 \
    hv_train_network.py \
    --config_file "$WORKSPACE/training/$CONFIG" \
    2>&1 | tee "$OUTPUT_DIR/training.log"

echo ""
echo "============================================"
echo "  Training complete!"
echo "  LoRA saved to: $OUTPUT_DIR"
echo ""
echo "  To download to your local machine:"
echo "    runpodctl send $OUTPUT_DIR/*.safetensors"
echo "============================================"
