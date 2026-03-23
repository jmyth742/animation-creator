#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# RunPod Start Script
# Run this each time you start a NEW pod attached to your volume.
# Activates the environment and launches ComfyUI.
# ═══════════════════════════════════════════════════════════════════

VOLUME="/workspace"
PROJECT="$VOLUME/text-to-video"

echo "Activating environment..."
source "$VOLUME/venv/bin/activate"

# Set API key if stored
if [ -f "$VOLUME/.env" ]; then
    export $(grep -v '^#' "$VOLUME/.env" | xargs)
fi

echo "Starting ComfyUI..."
echo "  Access via RunPod proxy → port 8188"
echo ""

cd "$PROJECT/ComfyUI"
python main.py --listen 0.0.0.0 --port 8188 &
COMFY_PID=$!

echo ""
echo "ComfyUI running (PID: $COMFY_PID)"
echo ""
echo "Commands:"
echo "  cd $PROJECT && python scripts/showrunner.py status my_series"
echo "  cd $PROJECT && python scripts/showrunner.py produce my_series --episode 1"
echo ""
echo "To train a LoRA:"
echo "  cd $VOLUME/musubi-tuner"
echo "  bash $PROJECT/runpod/train_lora.sh /path/to/dataset my_character"
echo ""

# Keep the script running
wait $COMFY_PID
