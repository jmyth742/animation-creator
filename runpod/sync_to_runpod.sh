#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Sync project to RunPod
#
# Usage:
#   bash runpod/sync_to_runpod.sh SSH_HOST SSH_PORT
#
# Example:
#   bash runpod/sync_to_runpod.sh 194.68.245.X 22077
#
# This transfers only your code, scripts, workflows, and series
# files (~60MB). Models are re-downloaded on RunPod via setup.sh.
# ═══════════════════════════════════════════════════════════════════

SSH_HOST="${1:?Usage: sync_to_runpod.sh SSH_HOST SSH_PORT}"
SSH_PORT="${2:-22}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "═══════════════════════════════════════════════"
echo "  Syncing project to RunPod"
echo "  Host: $SSH_HOST:$SSH_PORT"
echo "  Source: $PROJECT_DIR"
echo "  Dest: /workspace/text-to-video/"
echo "═══════════════════════════════════════════════"
echo ""

# Transfer project files (excluding models, git dirs, large files)
rsync -avz --progress \
    -e "ssh -p $SSH_PORT" \
    --exclude 'ComfyUI/models/' \
    --exclude 'ComfyUI/.git' \
    --exclude 'ComfyUI/custom_nodes/*/.git' \
    --exclude 'ComfyUI/custom_nodes/*/  ' \
    --exclude 'ComfyUI/output/' \
    --exclude 'ComfyUI/temp/' \
    --exclude 'ComfyUI/user/' \
    --exclude 'ComfyUI/venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    "$PROJECT_DIR/" \
    "root@${SSH_HOST}:/workspace/text-to-video/"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Sync complete!"
echo ""
echo "  Next steps (run on the RunPod pod):"
echo ""
echo "  1. SSH in:"
echo "     ssh root@$SSH_HOST -p $SSH_PORT"
echo ""
echo "  2. Run setup (installs everything + downloads models):"
echo "     bash /workspace/text-to-video/runpod/setup.sh"
echo ""
echo "  3. Store your Anthropic API key:"
echo "     echo 'ANTHROPIC_API_KEY=sk-ant-...' > /workspace/.env"
echo ""
echo "  4. Start ComfyUI:"
echo "     bash /workspace/text-to-video/runpod/start.sh"
echo "═══════════════════════════════════════════════"
