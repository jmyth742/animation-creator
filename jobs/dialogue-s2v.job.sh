# ─────────────────────────────────────────────────────────────────────
#  Dialogue + lip sync — the first S2V run
#
#  ep02 "The Warning" replays the farewell beat as DIALOGUE instead of
#  narration: 6 spoken lines across 5 close/medium shots, plus 2 silent
#  establishing shots. 27.4s total.
#
#  S2V is a separate checkpoint (Wan2.2-S2V-14B-Q5_K_M). The workflow used
#  to load the T2V UNet, which cannot read the audio conditioning at all --
#  it would have rendered video that ignored the voice, with no lip sync and
#  no error. _s2v_unet() now refuses rather than doing that quietly.
#
#  No --lightning: the distill LoRAs are T2V/I2V only.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"

NEEDS_COMFY=0
step "wait-queue" '
    for J in .jobs/lora-isolate; do
        [ -d "$J" ] || continue
        echo "waiting for $(basename $J)..."
        while true; do
            s=$(cat "$J/state" 2>/dev/null || echo unknown)
            p=$(cat "$J/pid" 2>/dev/null)
            if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
            [ "$s" = "running" ] && { sleep 120; continue; }
            echo "$(basename $J): $s"; break
        done
    done'

step "check-s2v" '
    F=ComfyUI/models/unet/Wan2.2-S2V-14B-Q5_K_M.gguf
    for i in $(seq 1 60); do
        [ -s "$F" ] && break
        echo "waiting for S2V download..."; sleep 30
    done
    [ -s "$F" ] || { echo "S2V model never arrived"; exit 1; }
    ls -lh "$F"'

NEEDS_COMFY=1
step "produce-ep02" "$SR produce $SERIES --episode 2 --quality good --optimization balanced"

step "publish" "
    mkdir -p /workspace/review/dialogue
    cp output/$SERIES/ep02/ep02_final.mp4 /workspace/review/dialogue/ 2>/dev/null || true
    cp output/$SERIES/ep02/ep02.srt       /workspace/review/dialogue/ 2>/dev/null || true
    cp output/$SERIES/ep02/audio/*.mp3    /workspace/review/dialogue/ 2>/dev/null || true
    ls -lh /workspace/review/dialogue/"

step "report" "
    grep -a -E 'Mode:|\\[[0-9]+/7\\]' .jobs/dialogue-s2v/job.log | tr '\\r' '\\n' | tail -20"
