# ─────────────────────────────────────────────────────────────────────
#  Follow-ups — runs after day2-characters releases the GPU
#
#    1. s16 regression: it rendered as a double-exposed face because an
#       explicit seed:location override fell through to the frame chain.
#       Fixed in code; needs one clip re-rendered and the episode restitched.
#    2. Native 720p: does 1280x720 fit in 24GB, and what does it cost?
#       Real resolution beats upscaling, and distilled sampling bought room.
#    3. Prompt adherence: distilled sampling renders "towering storm waves"
#       as pleasant surf. Do more steps recover the epic scale?
#
#  NOT attempted: rife-ncnn-vulkan. There is no Vulkan loader or NVIDIA ICD
#  on this box, so it would need driver-level installs on a working GPU
#  machine. FFmpeg minterpolate stays the stand-in until that is a decision
#  taken deliberately.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"
EP_OUT="output/$SERIES/ep01"

NEEDS_COMFY=0
step "wait-day2" '
    J=.jobs/day2-characters
    [ -d "$J" ] || { echo "no day2 job"; exit 0; }
    echo "waiting for day2-characters..."
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
        [ "$s" = "running" ] && { sleep 120; continue; }
        echo "day2-characters finished: $s"; break
    done'

step "archive-v4" "
    if [ -f '$EP_OUT/ep01_final.mp4' ] && [ ! -f '$EP_OUT/ep01_final_v4.mp4' ]; then
        cp '$EP_OUT/ep01_final.mp4' '$EP_OUT/ep01_final_v4.mp4'; echo 'kept v4'
    else echo 'v4 already archived'; fi"

# ─── 1. s16 ──────────────────────────────────────────────────────────
NEEDS_COMFY=1
step "flag-s16" "printf '%s\n' '[\"ep01_s16\"]' > '$EP_OUT/flags.json'; cat '$EP_OUT/flags.json'"
step "regen-s16" "$SR produce $SERIES --episode 1 --lightning --lightning-steps 8 \
                     --optimization none --flagged-only"
step "verify-s16" "
    f=\$(ls -t ComfyUI/output/video/$SERIES/ep01_s16_*.mp4 | head -1)
    echo \"newest s16: \$(basename \$f)\"
    grep -a -A2 '\\[16/16\\]' .jobs/day2-followups/job.log | tr '\\r' '\\n' | grep -i 'mode:' | tail -1"

# ─── 2 & 3. Evidence for the next decisions ──────────────────────────
step "test-720p"  "python scripts/shot_test.py $SERIES --scene ep01_s02 --test resolution"
step "test-steps" "python scripts/shot_test.py $SERIES --scene ep01_s02 --test steps"

# ─── Deliverable ─────────────────────────────────────────────────────
NEEDS_COMFY=0
step "final-cut" "python scripts/refresh_subtitles.py $SERIES --episode 1 --interpolate 3"
step "publish" "
    mkdir -p /workspace/review/episodes
    cp $EP_OUT/ep01_final.mp4       /workspace/review/episodes/6_v5_s16fixed.mp4
    cp $EP_OUT/ep01_final_48fps.mp4 /workspace/review/episodes/7_v5_s16fixed_48fps.mp4 2>/dev/null || true
    ls -lh /workspace/review/episodes/ /workspace/review/shot_tests/ 2>/dev/null"
