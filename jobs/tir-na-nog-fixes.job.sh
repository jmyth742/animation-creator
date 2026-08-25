# ─────────────────────────────────────────────────────────────────────
#  Tir na nOg legend — targeted fixes after the v2 draft
#
#  Run with:  scripts/jobctl start jobs/tir-na-nog-fixes.job.sh
#
#  Regenerates only the three shots that need it, at 25 steps with the
#  less aggressive EasyCache preset, then restitches the episode:
#
#    s02  Niamh riding from the sea   — T2V wide action broke up at 15
#    s04  the leap over the wave      — steps with EasyCache "fast"
#    s16  empty ground after the fall — horse was still in frame; the
#         location-plate fix landed after the v2 run had started
#
#  IMPORTANT: this waits for the jonny-lora job to finish first. That job
#  stops ComfyUI and hands all 24GB to musubi, so a render started
#  alongside it would have ComfyUI killed underneath it mid-clip.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"
EP_OUT="output/$SERIES/ep01"

# ─── Wait for the GPU ────────────────────────────────────────────────
NEEDS_COMFY=0
step "wait-for-lora" '
    J=.jobs/jonny-lora
    if [ ! -d "$J" ]; then echo "no jonny-lora job — proceeding"; exit 0; fi
    echo "waiting for jonny-lora to release the GPU..."
    while true; do
        s=$(cat "$J/state" 2>/dev/null || echo unknown)
        p=$(cat "$J/pid" 2>/dev/null)
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
        [ "$s" = "running" ] && { sleep 120; continue; }
        echo "jonny-lora finished with state: $s"
        break
    done'

# ─── Keep the v2 cut before anything overwrites it ───────────────────
step "archive-v2" "
    if [ -f '$EP_OUT/ep01_final.mp4' ] && [ ! -f '$EP_OUT/ep01_final_v2.mp4' ]; then
        cp '$EP_OUT/ep01_final.mp4' '$EP_OUT/ep01_final_v2.mp4'
        echo 'kept v2 as ep01_final_v2.mp4'
    else
        echo 'v2 already archived'
    fi"

# ─── Flag the three shots and regenerate just those ──────────────────
NEEDS_COMFY=1
step "flag-shots" "
    mkdir -p '$EP_OUT'
    printf '%s\n' '[\"ep01_s02\", \"ep01_s04\", \"ep01_s16\"]' > '$EP_OUT/flags.json'
    cat '$EP_OUT/flags.json'"

step "regen-flagged" \
    "$SR produce $SERIES --episode 1 --quality good --optimization balanced --flagged-only"

step "report" "
    echo '--- final ---'
    ls -lh '$EP_OUT'/ep01_final*.mp4
    ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 '$EP_OUT/ep01_final.mp4'"
