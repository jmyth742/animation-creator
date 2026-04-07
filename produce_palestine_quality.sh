#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Palestine Stories — Quality-Stepped Production
#
# Three-pass approach:
#   Pass 1: Generate all clips at draft quality (fast, 15 steps)
#   Pass 2: Claude vision analyses clips, flags weak ones, writes improved prompts
#   Pass 3: Regenerate flagged clips at good quality with improved prompts
#
# Then apply post-processing: interpolation + upscale + stitch
# ─────────────────────────────────────────────────────────────
set -e

SERIES="palestine-stories"
EPISODES="1 2 3 4 5"

# ─── Environment ────────────────────────────────────────────
export PYTHONUNBUFFERED=1
cd /workspace/text-to-video

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set"
    exit 1
fi

# Clear old audio for per-character voice regeneration
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' $ep)
    AUDIO_DIR="output/$SERIES/ep${EP_NUM}/audio"
    if [ -d "$AUDIO_DIR" ]; then
        rm -f "$AUDIO_DIR"/*.mp3
    fi
done

echo ""
echo "============================================================"
echo "  Palestine Stories — Quality-Stepped Production"
echo "============================================================"

# ─── Pass 1: Draft generation ───────────────────────────────
echo ""
echo "━━━ PASS 1: Draft generation (15 steps) ━━━"
for ep in $EPISODES; do
    echo ""
    echo "  Episode $ep — Draft..."
    python scripts/showrunner.py produce "$SERIES" \
        --episode "$ep" \
        --quality draft \
        --optimization fast \
        --enhance \
        --auto-analyse \
        --resume \
        2>&1 | tee "produce_ep$(printf '%02d' $ep)_draft.log"
done

# ─── Pass 2: Regenerate flagged clips at good quality ───────
echo ""
echo "━━━ PASS 2: Regenerate flagged clips (25 steps) ━━━"
for ep in $EPISODES; do
    FLAGS_FILE="output/$SERIES/ep$(printf '%02d' $ep)/flags.json"
    if [ -f "$FLAGS_FILE" ] && [ "$(cat "$FLAGS_FILE")" != "[]" ]; then
        echo ""
        echo "  Episode $ep — Regenerating flagged clips..."
        python scripts/showrunner.py produce "$SERIES" \
            --episode "$ep" \
            --quality good \
            --optimization balanced \
            --enhance \
            --flagged-only \
            2>&1 | tee "produce_ep$(printf '%02d' $ep)_regen.log"
    else
        echo "  Episode $ep — No flagged clips, skipping"
    fi
done

# ─── Pass 3: Post-processing ────────────────────────────────
echo ""
echo "━━━ PASS 3: Final production with post-processing ━━━"
for ep in $EPISODES; do
    echo ""
    echo "  Episode $ep — Final pass (interpolate + upscale)..."
    python scripts/showrunner.py produce "$SERIES" \
        --episode "$ep" \
        --quality good \
        --optimization balanced \
        --enhance \
        --interpolate \
        --upscale \
        --upscale-factor 2 \
        --resume \
        2>&1 | tee "produce_ep$(printf '%02d' $ep)_final.log"
done

# ─── Compile season reel ────────────────────────────────────
echo ""
echo "━━━ Compiling season reel ━━━"
python scripts/showrunner.py compile "$SERIES"

# ─── Summary ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Production Complete"
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
