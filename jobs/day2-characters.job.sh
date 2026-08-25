# ─────────────────────────────────────────────────────────────────────
#  Day 2 — deliver the fixed cut, then train Niamh + Oisin, then test
#
#  Run with:  scripts/jobctl start jobs/day2-characters.job.sh
#
#  Waits for the Lightning re-render to finish first (it owns the GPU).
#  Only rank 64 is trained: the Jonny comparison showed r32 at full
#  strength hijacks composition while r64 holds the face AND respects the
#  prompt's framing, so training r32 as well would just burn 1.5h each.
# ─────────────────────────────────────────────────────────────────────
SR="python scripts/showrunner.py"
BUILD="python scripts/build_character_dataset.py"
TRAIN="bash /workspace/training_models/wan22/train_character.sh"
MATRIX="python scripts/quality_matrix.py"
SERIES="tir-na-nog-legend"
LORAS=/workspace/text-to-video/ComfyUI/models/loras

# ─── 1. Wait for the Lightning render to release the GPU ─────────────
NEEDS_COMFY=0
step "wait-lightning" '
    J=.jobs/tir-na-nog-lightning
    [ -d "$J" ] || { echo "no lightning job"; exit 0; }
    echo "waiting for tir-na-nog-lightning..."
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
        [ "$s" = "running" ] && { sleep 120; continue; }
        echo "lightning finished: $s"; break
    done'

# ─── 2. Deliverable: correct subtitles + a smooth 48fps cut (CPU only) ─
step "fix-subs" "python scripts/refresh_subtitles.py $SERIES --episode 1 --interpolate 3"
step "publish-review" "
    mkdir -p /workspace/review/episodes
    cp output/$SERIES/ep01/ep01_final.mp4        /workspace/review/episodes/4_v4_lightning_fixedsubs.mp4
    cp output/$SERIES/ep01/ep01_final_48fps.mp4  /workspace/review/episodes/5_v4_lightning_48fps.mp4 2>/dev/null || true
    cp output/$SERIES/ep01/ep01.srt              /workspace/review/episodes/ep01_fixed.srt
    ls -lh /workspace/review/episodes/"

# ─── 3. Niamh: dataset then train ────────────────────────────────────
NEEDS_COMFY=1
step "niamh-clips"  "$BUILD clips  niamh --count 8 --steps 18"
step "niamh-frames" "$BUILD frames niamh --per-clip 5"
step "niamh-config" "$BUILD config niamh"
step "niamh-free-gpu" "bash scripts/ensure_comfyui.sh stop; sleep 5"
NEEDS_COMFY=0
step "niamh-train"  "$TRAIN niamh 64 16"
step "niamh-install" "
    cp /workspace/lora_outputs_v3/niamh_r64/niamh-wan22-high-r64.safetensors $LORAS/niamh-r64-high.safetensors
    cp /workspace/lora_outputs_v3/niamh_r64/niamh-wan22-low-r64.safetensors  $LORAS/niamh-r64-low.safetensors
    ls -la $LORAS/ | grep niamh"

# ─── 4. Oisin: dataset then train ────────────────────────────────────
NEEDS_COMFY=1
step "oisin-clips"  "$BUILD clips  oisin --count 8 --steps 18"
step "oisin-frames" "$BUILD frames oisin --per-clip 5"
step "oisin-config" "$BUILD config oisin"
step "oisin-free-gpu" "bash scripts/ensure_comfyui.sh stop; sleep 5"
NEEDS_COMFY=0
step "oisin-train"  "$TRAIN oisin 64 16"
step "oisin-install" "
    cp /workspace/lora_outputs_v3/oisin_r64/oisin-wan22-high-r64.safetensors $LORAS/oisin-r64-high.safetensors
    cp /workspace/lora_outputs_v3/oisin_r64/oisin-wan22-low-r64.safetensors  $LORAS/oisin-r64-low.safetensors
    ls -la $LORAS/ | grep oisin"

# ─── 5. Quality matrix on a close shot of each character ─────────────
NEEDS_COMFY=1
step "matrix-niamh" "$MATRIX $SERIES --episode 1 --scene ep01_s11 --lora niamh-r64.safetensors"
step "matrix-oisin" "$MATRIX $SERIES --episode 1 --scene ep01_s03 --lora oisin-r64.safetensors"
step "matrix-report" "ls -lh /workspace/review/matrix/ | head -30; cat /workspace/review/matrix/*_timings.json"
