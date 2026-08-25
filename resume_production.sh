#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Resume Palestine Stories production in a tmux session
# Run this if the original process died (SSH drop, crash, etc.)
# It uses --resume so it skips already-generated clips.
# ─────────────────────────────────────────────────────────────
set -e

SESSION="palestine-prod"

# Kill any stale production processes
pkill -f "produce_palestine.sh" 2>/dev/null || true
sleep 2

# Start in tmux
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" "
  cd /workspace/text-to-video
  export ANTHROPIC_API_KEY='$(grep ANTHROPIC_API_KEY /workspace/text-to-video/.env | cut -d= -f2-)'
  export PYTHONUNBUFFERED=1
  bash produce_palestine.sh 2>&1 | tee produce_run_resumed.log
  echo ''
  echo 'Production complete. Press Enter to close.'
  read
"

echo "Production resumed in tmux session: $SESSION"
echo "  Attach:  tmux attach -t $SESSION"
echo "  Detach:  Ctrl+B, then D"
echo "  Log:     tail -f /workspace/text-to-video/produce_run_resumed.log"
