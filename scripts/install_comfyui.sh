#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "=== Installing ComfyUI ==="

# Check we're in the right conda env
if [[ "${CONDA_DEFAULT_ENV:-}" != "hunyuan-comfy" ]]; then
    echo "WARNING: Expected conda env 'hunyuan-comfy' but got '${CONDA_DEFAULT_ENV:-none}'."
    echo "Run: conda activate hunyuan-comfy"
    exit 1
fi

# Clone ComfyUI
if [ ! -d "$ROOT/ComfyUI/.git" ]; then
    echo "Cloning ComfyUI..."
    git clone https://github.com/comfyanonymous/ComfyUI "$ROOT/ComfyUI_tmp"
    # Move contents into existing ComfyUI dir (which has our model dirs)
    cp -r "$ROOT/ComfyUI_tmp/." "$ROOT/ComfyUI/"
    rm -rf "$ROOT/ComfyUI_tmp"
else
    echo "ComfyUI already cloned."
fi

cd "$ROOT/ComfyUI"
echo "Installing ComfyUI requirements..."
python -m pip install -r requirements.txt

echo ""
echo "=== Installing Custom Nodes ==="

cd "$ROOT/ComfyUI/custom_nodes"

# ComfyUI-GGUF (required for GGUF weight loading)
if [ ! -d "ComfyUI-GGUF" ]; then
    echo "Cloning ComfyUI-GGUF..."
    git clone https://github.com/city96/ComfyUI-GGUF
else
    echo "ComfyUI-GGUF already present."
fi
python -m pip install -r ComfyUI-GGUF/requirements.txt

# ComfyUI-HunyuanVideoWrapper (Kijai)
if [ ! -d "ComfyUI-HunyuanVideoWrapper" ]; then
    echo "Cloning ComfyUI-HunyuanVideoWrapper..."
    git clone https://github.com/kijai/ComfyUI-HunyuanVideoWrapper
else
    echo "ComfyUI-HunyuanVideoWrapper already present."
fi
python -m pip install -r ComfyUI-HunyuanVideoWrapper/requirements.txt

# ComfyUI Manager (optional but useful)
if [ ! -d "ComfyUI-Manager" ]; then
    echo "Cloning ComfyUI-Manager..."
    git clone https://github.com/ltdrdata/ComfyUI-Manager
else
    echo "ComfyUI-Manager already present."
fi

echo ""
echo "=== Attempting Flash Attention install ==="
python -m pip install flash-attn --no-build-isolation 2>/dev/null || {
    echo "Flash attention build failed. Trying with conda cuda-nvcc..."
    conda install -c nvidia cuda-nvcc -y 2>/dev/null || true
    python -m pip install flash-attn --no-build-isolation 2>/dev/null || {
        echo "WARNING: Flash attention not installed. This is optional but helps reduce VRAM ~10-15%."
    }
}

echo ""
echo "=== ComfyUI installation complete ==="
echo "Next: run 'bash scripts/download_models.sh' to download model weights."
