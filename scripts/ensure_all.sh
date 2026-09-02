#!/bin/bash
# Bring the whole studio up after a pod restart: ComfyUI + SHOWRUNNER console.
cd /workspace/text-to-video
bash scripts/ensure_comfyui.sh
pgrep -f "ensure_workbenc[h]" >/dev/null || \
  setsid nohup scripts/ensure_workbench.sh >/dev/null 2>&1 < /dev/null &
echo "studio up: comfy :8188, console :8888"
