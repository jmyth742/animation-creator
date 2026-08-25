#!/bin/bash
# Quick progress check for Palestine Stories production
cd /workspace/text-to-video

echo "============================================================"
echo "  Palestine Stories — Production Progress"
echo "  $(date)"
echo "============================================================"

# Check if process is running
PROD_PID=$(pgrep -f "produce_palestine.sh" 2>/dev/null | head -1)
SHOW_PID=$(pgrep -f "showrunner.py.*produce.*palestine" 2>/dev/null | head -1)
if [ -n "$PROD_PID" ]; then
    ELAPSED=$(ps -o etime= -p "$PROD_PID" 2>/dev/null | tr -d ' ')
    echo "  Status: RUNNING (PID $PROD_PID, elapsed $ELAPSED)"
    if [ -n "$SHOW_PID" ]; then
        EP=$(ps -o args= -p "$SHOW_PID" 2>/dev/null | grep -oP '(?<=--episode )\d+')
        echo "  Current episode: $EP"
    fi
else
    echo "  Status: NOT RUNNING"
fi

# ComfyUI queue
QUEUE=$(curl -s http://localhost:8188/queue 2>/dev/null)
if [ -n "$QUEUE" ]; then
    RUNNING=$(echo "$QUEUE" | python3 -c "import sys,json;q=json.load(sys.stdin);print(len(q.get('queue_running',[])))" 2>/dev/null)
    PENDING=$(echo "$QUEUE" | python3 -c "import sys,json;q=json.load(sys.stdin);print(len(q.get('queue_pending',[])))" 2>/dev/null)
    echo "  ComfyUI: $RUNNING running, $PENDING pending"
else
    echo "  ComfyUI: NOT RESPONDING"
fi

echo ""
echo "  Episode outputs:"
for ep in 01 02 03 04 05; do
    FINAL="output/palestine-stories/ep${ep}/ep${ep}_final.mp4"
    FLAGS="output/palestine-stories/ep${ep}/flags.json"
    if [ -f "$FINAL" ]; then
        SIZE=$(du -h "$FINAL" | cut -f1)
        MOD=$(stat -c %y "$FINAL" 2>/dev/null | cut -d. -f1)
        FLAG_COUNT=""
        if [ -f "$FLAGS" ] && [ "$(cat "$FLAGS")" != "[]" ]; then
            FLAG_COUNT=" ($(python3 -c "import json;print(len(json.load(open('$FLAGS'))))" 2>/dev/null) flagged)"
        fi
        echo "    ep$ep: $SIZE  ($MOD)$FLAG_COUNT"
    else
        echo "    ep$ep: not produced yet"
    fi
done

echo ""
echo "  Latest log:"
tail -3 produce_run.log 2>/dev/null | tr '\r' '\n' | grep -v '^$' | tail -3
echo "============================================================"
