#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Fix disk space issue and resume setup
# Run this on the RunPod pod after the initial setup failed
# ═══════════════════════════════════════════════════════════════════

echo "=== Fixing disk space + cache locations ==="

# Clear HF cache from root disk
rm -rf /root/.cache/huggingface /root/.cache/pip 2>/dev/null || true

# Set up caches on network volume
mkdir -p /workspace/.cache/huggingface /workspace/.cache/pip /workspace/.npm-global

# Write persistent env config
cat > /workspace/.env.sh << 'EOF'
export HF_HOME=/workspace/.cache/huggingface
export PIP_CACHE_DIR=/workspace/.cache/pip
export NPM_CONFIG_PREFIX=/workspace/.npm-global
export PATH="/workspace/.npm-global/bin:$PATH"
# Source the API key env if it exists
[ -f /workspace/.env ] && export $(grep -v '^#' /workspace/.env | xargs)
EOF

# Source it now
source /workspace/.env.sh

# Add to bashrc so every new shell gets it
grep -q "workspace/.env.sh" /root/.bashrc 2>/dev/null || \
    echo 'source /workspace/.env.sh 2>/dev/null || true' >> /root/.bashrc

echo "  Cache dirs moved to /workspace/"
echo "  Root disk freed: $(df -h / | tail -1 | awk '{print $4}') available"

# ─── Install Claude Code CLI ─────────────────────────────────────
echo ""
echo "=== Installing Claude Code CLI ==="
npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
echo "  Claude installed at: $(which claude 2>/dev/null || echo '/workspace/.npm-global/bin/claude')"

# ─── Resume model downloads ──────────────────────────────────────
echo ""
echo "=== Resuming model downloads ==="
bash /workspace/text-to-video/runpod/setup.sh

echo ""
echo "═══════════════════════════════════════════════"
echo "  All done!"
echo ""
echo "  Set your Anthropic API key:"
echo "    echo 'ANTHROPIC_API_KEY=sk-ant-your-key' > /workspace/.env"
echo ""
echo "  Start ComfyUI:"
echo "    bash /workspace/text-to-video/runpod/start.sh"
echo ""
echo "  Start Claude Code:"
echo "    claude"
echo "═══════════════════════════════════════════════"
