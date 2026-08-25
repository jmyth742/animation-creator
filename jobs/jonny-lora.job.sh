# ─────────────────────────────────────────────────────────────────────
#  Jonny — persistent character LoRA (overnight)
#
#  Run with:  scripts/jobctl start jobs/jonny-lora.job.sh
#
#  Assumes the canonical portrait has already been chosen:
#     build_character_dataset.py portraits jonny
#     build_character_dataset.py pick jonny --candidate N
#
#  Every step is checkpointed, so a crash or a disconnect resumes at the
#  step it died on rather than regenerating the dataset from scratch.
# ─────────────────────────────────────────────────────────────────────
BUILD="python scripts/build_character_dataset.py"
TRAIN="bash /workspace/training_models/wan22/train_character.sh"

# ─── Dataset: animate the canonical portrait, harvest frames ─────────
# These need ComfyUI up.
NEEDS_COMFY=1

step "ds-clips"  "$BUILD clips  jonny --count 8 --steps 18"
step "ds-frames" "$BUILD frames jonny --per-clip 5"
step "ds-config" "$BUILD config jonny"

# ─── Hand the GPU over to the trainer ────────────────────────────────
# ComfyUI holds ~15GB of VRAM once a model is loaded; musubi needs all of
# it. Stop the daemon before training and do not health-check it again.
step "free-gpu" "bash scripts/ensure_comfyui.sh stop; sleep 5; nvidia-smi --query-gpu=memory.used --format=csv,noheader"
NEEDS_COMFY=0

# ─── Train: proven rank first, then the higher-capacity run ──────────
# Rank 32 is the config that produced the existing reemi/bibi LoRAs, so if
# anything is wrong with the dataset it surfaces on the cheaper run.
step "train-r32" "$TRAIN jonny 32 16"
step "train-r64" "$TRAIN jonny 64 16"

# ─── Install the rank-32 pair for immediate use ──────────────────────
step "install-r32" \
    "cp /workspace/lora_outputs_v3/jonny/jonny-wan22-low.safetensors \
        /workspace/lora_outputs_v3/jonny/jonny-wan22-high.safetensors \
        /workspace/text-to-video/ComfyUI/models/loras/ && ls -la /workspace/text-to-video/ComfyUI/models/loras/ | grep jonny"
