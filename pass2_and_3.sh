#!/bin/bash
# Pass 2+3: Regenerate flagged clips + post-processing
# Pass 1 (analysis) already completed
cd /workspace/text-to-video
export PYTHONUNBUFFERED=1
set -a; source .env; set +a

SERIES="palestine-stories"
EPISODES="1 2 3 4 5"

# Clear old audio for per-character regeneration
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' $ep)
    rm -f "output/$SERIES/ep${EP_NUM}/audio/"*.mp3
done

echo ""
echo "━━━ PASS 2: Regenerate flagged clips (25 steps) ━━━"
for ep in $EPISODES; do
    FLAGS_FILE="output/$SERIES/ep$(printf '%02d' $ep)/flags.json"
    if [ -f "$FLAGS_FILE" ] && [ "$(cat "$FLAGS_FILE")" != "[]" ]; then
        COUNT=$(python3 -c "import json;print(len(json.load(open('$FLAGS_FILE'))))")
        echo ""
        echo "  Episode $ep — Regenerating $COUNT flagged clips..."
        python scripts/showrunner.py produce "$SERIES" \
            --episode "$ep" \
            --quality good \
            --optimization balanced \
            --enhance \
            --flagged-only
    else
        echo "  Episode $ep — No flagged clips"
    fi
done

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
        --resume
done

echo ""
echo "━━━ Compiling season reel ━━━"
python scripts/showrunner.py compile "$SERIES"

echo ""
echo "━━━ DONE ━━━"
date
