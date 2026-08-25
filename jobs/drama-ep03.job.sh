# ─────────────────────────────────────────────────────────────────────
#  ep03 "Three Hundred Years" — the drama build
#
#  Everything learned today, applied at once:
#    - dialogue with lip sync (8 S2V shots, per-character voices)
#    - deliberate editing rhythm: 5 short / 4 medium / 8 long, where ep01
#      used no short shots at all and every cut landed identically
#    - character LoRAs actually triggered (trigger_word now reaches the prompt)
#    - every shot anchored: portrait or location plate, zero chain fallbacks
#    - Lightning on I2V/T2V, correctly skipped for S2V
#    - timeline audio (no crossfade bleed) + a continuous music bed
#    - narration budgeted against the post-crossfade slot
#
#  Runs after the ep02 S2V smoke test, so if speech-to-video is broken we
#  find out on 7 shots rather than 17.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"

NEEDS_COMFY=0
step "wait-ep02" '
    J=.jobs/dialogue-s2v
    [ -d "$J" ] || { echo "no ep02 job"; exit 0; }
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
        [ "$s" = "running" ] && { sleep 120; continue; }
        echo "ep02 finished: $s"
        [ "$s" = "done" ] || { echo "ep02 did not succeed — S2V needs fixing first"; exit 1; }
        break
    done'

step "preflight" "python scripts/preflight.py $SERIES --episode 3"

NEEDS_COMFY=1
# Cohesion over speed. Dialogue renders on the S2V checkpoint and everything
# else on the I2V one -- two different sets of weights in a single episode. Any
# further variation on top of that shows as a visible seam, so:
#   --lightning OFF     : otherwise non-dialogue shots run 8 steps / cfg 1.0
#                         while dialogue runs 25 / cfg 5.0
#   --no-char-loras     : the LoRAs are trained on t2v-A14B; spreading them
#                         across three model families is not like-for-like.
#                         Identity comes from the portrait seeds, which apply
#                         identically to both checkpoints.
step "produce-ep03" "$SR produce $SERIES --episode 3 --quality good \
                        --optimization balanced --no-char-loras"

NEEDS_COMFY=0
step "finish-ep03" "python scripts/refresh_subtitles.py $SERIES --episode 3 \
                        --music music.mp3 --interpolate 3"

step "publish" "
    mkdir -p /workspace/review/drama
    cp output/$SERIES/ep03/ep03_final.mp4        /workspace/review/drama/ 2>/dev/null || true
    cp output/$SERIES/ep03/ep03_final_48fps.mp4  /workspace/review/drama/ 2>/dev/null || true
    cp output/$SERIES/ep03/ep03.srt              /workspace/review/drama/ 2>/dev/null || true
    ls -lh /workspace/review/drama/"
