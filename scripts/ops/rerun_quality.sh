#!/bin/bash
# Re-run quality pipeline with fixed RIFE + FFmpeg lanczos upscaling
export PYTHONUNBUFFERED=1
cd /workspace/text-to-video

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

SERIES="palestine-stories"
EPISODES="1 2 3 4 5"

echo ""
echo "============================================================"
echo "  Palestine Stories — Quality Re-run ($(date))"
echo "  RIFE: fixed | ESRGAN: FFmpeg lanczos fallback"
echo "============================================================"

# ─── Pass 2: Regenerate flagged clips at good quality ───────
echo ""
echo "━━━ PASS 2: Regenerate flagged clips (25 steps) ━━━"
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' $ep)
    FLAGS_FILE="output/$SERIES/ep${EP_NUM}/flags.json"
    if [ -f "$FLAGS_FILE" ] && [ "$(cat "$FLAGS_FILE")" != "[]" ]; then
        FLAGGED=$(python3 -c "import json; print(len(json.load(open('$FLAGS_FILE'))))")
        echo ""
        echo "  Episode $ep — Regenerating $FLAGGED flagged clips..."
        python scripts/showrunner.py produce "$SERIES" \
            --episode "$ep" \
            --quality good \
            --optimization balanced \
            --enhance \
            --flagged-only \
            2>&1
    else
        echo "  Episode $ep — No flagged clips, skipping"
    fi
done

# ─── Pass 3: Post-processing ────────────────────────────────
echo ""
echo "━━━ PASS 3: Post-processing (interpolate + upscale + grade) ━━━"
for ep in $EPISODES; do
    echo ""
    echo "  Episode $ep — Post-processing..."
    python scripts/showrunner.py produce "$SERIES" \
        --episode "$ep" \
        --quality good \
        --optimization balanced \
        --enhance \
        --interpolate \
        --upscale \
        --upscale-factor 2 \
        --resume \
        2>&1
done

# ─── Compile season reel ────────────────────────────────────
echo ""
echo "━━━ Compiling season reel ━━━"
python scripts/showrunner.py compile "$SERIES"

# ─── Summary ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Production Complete ($(date))"
echo "============================================================"
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' $ep)
    FINAL="output/$SERIES/ep${EP_NUM}/ep${EP_NUM}_final.mp4"
    if [ -f "$FINAL" ]; then
        SIZE=$(du -h "$FINAL" | cut -f1)
        echo "  Episode $ep: $SIZE"
    fi
done
SEASON="output/$SERIES/${SERIES}_season.mp4"
if [ -f "$SEASON" ]; then
    SIZE=$(du -h "$SEASON" | cut -f1)
    echo "  Season reel: $SIZE"
fi

# Restore ESRGAN binary
if [ -f /usr/local/bin/realesrgan-ncnn-vulkan.bak ]; then
    mv /usr/local/bin/realesrgan-ncnn-vulkan.bak /usr/local/bin/realesrgan-ncnn-vulkan
    echo "  (ESRGAN binary restored)"
fi
