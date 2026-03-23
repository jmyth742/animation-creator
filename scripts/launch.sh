#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Check conda env
if [[ "${CONDA_DEFAULT_ENV:-}" != "hunyuan-comfy" ]]; then
    echo "ERROR: Activate the conda env first: conda activate hunyuan-comfy"
    exit 1
fi

PORT="${1:-8188}"

echo "Launching ComfyUI on port $PORT with --lowvram..."
echo "Open: http://localhost:$PORT"
echo ""

cd ComfyUI
python main.py --lowvram --port "$PORT"
