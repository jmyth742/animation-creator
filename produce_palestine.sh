#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Palestine Stories — Full Coherent Production Run
#
# Pipeline features used:
#   - Scene-type routing: T2V (establishing) / I2V (character) / S2V (dialogue)
#   - Character LoRAs: reemi-wan22 (0.7), bibi-wan22 (0.7)
#   - Location LoRA: haifa_port-wan22 (0.4)
#   - Dual high/low noise LoRA variants for I2V
#   - Cross-episode continuity (end-frame carry-over)
#   - Within-episode frame chaining (I2V seed from previous scene)
#   - Claude prompt enhancement (cinematographer-style rewrites)
#   - EasyCache balanced (~30% faster, minimal quality loss)
#   - Per-character TTS voices (Jenny=Reemi, Ryan=Bibi, Sonia=narrator)
#   - Negative prompts per scene type
#   - Denoise 0.70 for close-ups, 0.82 default
#   - WAN 2.2 VAE + 14B dual-model I2V
#   - Colour grading + subtitle burn
# ─────────────────────────────────────────────────────────────
set -e

# ─── Config ─────────────────────────────────────────────────
SERIES="palestine-stories"
QUALITY="good"            # draft=15 steps, good=25, final=40
OPTIMIZATION="balanced"   # none, balanced (~30% faster), fast, turbo
RESOLUTION="auto"         # auto (720p if 24GB+, else 480p)
EPISODES="1 2 3 4 5"

# Set to 1 to regenerate everything from scratch (ignore existing clips)
FRESH_RUN=0

# ─── Environment ────────────────────────────────────────────
export PYTHONUNBUFFERED=1
cd /workspace/text-to-video

# Source API key from .env if available
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set. Export it or add to .env"
    exit 1
fi

# ─── Pre-flight checks ─────────────────────────────────────
echo ""
echo "============================================================"
echo "  Palestine Stories — Production Run"
echo "  Quality: $QUALITY | Optimization: $OPTIMIZATION | Resolution: $RESOLUTION"
echo "  Episodes: $EPISODES"
echo "============================================================"

# Check ComfyUI is running
if ! curl -s http://localhost:8188/system_stats > /dev/null 2>&1; then
    echo ""
    echo "WARNING: ComfyUI not responding at localhost:8188"
    echo "  Start it with: bash scripts/launch.sh"
    echo "  Waiting 30s for startup..."
    sleep 30
    if ! curl -s http://localhost:8188/system_stats > /dev/null 2>&1; then
        echo "ERROR: ComfyUI still not available. Exiting."
        exit 1
    fi
fi

# Check S2V audio encoder (enables dialogue lip sync)
S2V_MODEL="ComfyUI/models/audio_encoders/wav2vec2_large_english_fp16.safetensors"
if [ -f "$S2V_MODEL" ]; then
    echo "  S2V audio encoder: AVAILABLE (dialogue scenes will use speech-to-video)"
else
    echo "  S2V audio encoder: NOT FOUND (dialogue scenes will fall back to I2V)"
    echo "    To enable: run setup.sh or download wav2vec2_large_english_fp16.safetensors"
fi

# Check LoRA files
echo "  LoRAs:"
for lora in reemi-wan22-high reemi-wan22-low bibi-wan22-high bibi-wan22-low haifa_port-wan22-high haifa_port-wan22-low; do
    if [ -f "ComfyUI/models/loras/${lora}.safetensors" ]; then
        echo "    $lora: OK"
    else
        echo "    $lora: MISSING"
    fi
done

echo ""

# ─── Build resume flag ──────────────────────────────────────
RESUME_FLAG=""
if [ "$FRESH_RUN" != "1" ]; then
    RESUME_FLAG="--resume"
fi

# ─── Produce each episode sequentially ──────────────────────
# Sequential is required for cross-episode continuity (end-frame carry-over).
FAILED_EPS=""
for ep in $EPISODES; do
    echo ""
    echo "============================================================"
    echo "  Episode $ep — Starting"
    echo "============================================================"

    python scripts/showrunner.py produce "$SERIES" \
        --episode "$ep" \
        --quality "$QUALITY" \
        --optimization "$OPTIMIZATION" \
        --resolution "$RESOLUTION" \
        --enhance \
        $RESUME_FLAG \
        2>&1 | tee "produce_ep$(printf '%02d' $ep).log"

    EXIT_CODE=${PIPESTATUS[0]}
    if [ $EXIT_CODE -ne 0 ]; then
        echo "  Episode $ep FAILED (exit code $EXIT_CODE)"
        FAILED_EPS="$FAILED_EPS $ep"
    else
        echo "  Episode $ep complete!"
    fi
done

# ─── Retry flagged clips ────────────────────────────────────
echo ""
echo "============================================================"
echo "  Retrying flagged clips (if any)"
echo "============================================================"
for ep in $EPISODES; do
    FLAGS_FILE="output/$SERIES/ep$(printf '%02d' $ep)/flags.json"
    if [ -f "$FLAGS_FILE" ] && [ "$(cat "$FLAGS_FILE")" != "[]" ]; then
        echo "  Episode $ep has flagged clips — retrying..."
        python scripts/showrunner.py produce "$SERIES" \
            --episode "$ep" \
            --quality "$QUALITY" \
            --optimization "$OPTIMIZATION" \
            --resolution "$RESOLUTION" \
            --enhance \
            --flagged-only \
            2>&1 | tee -a "produce_ep$(printf '%02d' $ep).log"
    fi
done

# ─── Summary ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Production Complete"
echo "============================================================"
echo ""
echo "  Outputs:"
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' $ep)
    FINAL="output/$SERIES/ep${EP_NUM}/ep${EP_NUM}_final.mp4"
    if [ -f "$FINAL" ]; then
        SIZE=$(du -h "$FINAL" | cut -f1)
        echo "    Episode $ep: $FINAL ($SIZE)"
    else
        echo "    Episode $ep: NOT PRODUCED"
    fi
done

if [ -n "$FAILED_EPS" ]; then
    echo ""
    echo "  FAILED episodes:$FAILED_EPS"
    echo "  Check logs: produce_epNN.log"
    exit 1
fi

echo ""
echo "  All episodes produced successfully!"
