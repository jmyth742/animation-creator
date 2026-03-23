#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="hunyuan-comfy"

echo "=== Setting up conda environment: $ENV_NAME ==="

# Check conda is available
if ! command -v conda &>/dev/null; then
    echo "ERROR: conda not found. Install Miniconda/Anaconda first."
    exit 1
fi

# Create environment if it doesn't exist
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "Environment '$ENV_NAME' already exists. Skipping creation."
else
    echo "Creating conda environment with Python 3.10.9..."
    conda create -n "$ENV_NAME" python=3.10.9 -y
fi

echo ""
echo "=== Installing PyTorch with CUDA 12.1 ==="
echo "Run the following commands manually (conda activate must run in your shell):"
echo ""
echo "  conda activate $ENV_NAME"
echo "  conda install pytorch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 pytorch-cuda=12.1 -c pytorch -c nvidia"
echo "  pip install huggingface_hub"
echo ""
echo "=== Verify GPU ==="
echo "  python -c \"import torch; print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_properties(0).total_memory // 1024**3, 'GB')\""
echo ""
echo "Then run: bash scripts/install_comfyui.sh"
