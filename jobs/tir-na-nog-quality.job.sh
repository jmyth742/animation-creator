# ─────────────────────────────────────────────────────────────────────
#  Tir na nOg — 3-pass quality production
#
#  Run with:  scripts/jobctl start jobs/tir-na-nog-quality.job.sh
#
#  Each `step` is checkpointed. If the job dies (SSH drop, OOM, ComfyUI
#  crash, pod restart) just start it again — completed steps are skipped
#  and the interrupted one is retried from its own --resume point.
#
#  Granularity is one pass per episode: the most you ever redo is the
#  unfinished clips of a single episode-pass.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog"
EPISODES="1"
SR="python scripts/showrunner.py"

# ─── Pass 1: draft generation (15 steps, fast) ───────────────────────
for ep in $EPISODES; do
    step "p1-draft-ep$ep" \
        "$SR produce $SERIES --episode $ep \
            --quality draft --optimization fast \
            --enhance --auto-analyse --resume"
done

# ─── Pass 2: regenerate clips Claude flagged as weak (25 steps) ──────
for ep in $EPISODES; do
    EP_NUM=$(printf '%02d' "$ep")
    FLAGS="output/$SERIES/ep$EP_NUM/flags.json"
    step "p2-regen-ep$ep" \
        "if [ -s '$FLAGS' ] && [ \"\$(cat '$FLAGS')\" != '[]' ]; then
             $SR produce $SERIES --episode $ep \
                 --quality good --optimization balanced \
                 --enhance --flagged-only
         else
             echo 'no flagged clips for ep$ep — nothing to regenerate'
         fi"
done

# ─── Pass 3: interpolate + upscale + stitch ──────────────────────────
for ep in $EPISODES; do
    step "p3-final-ep$ep" \
        "$SR produce $SERIES --episode $ep \
            --quality good --optimization balanced \
            --enhance --interpolate --upscale --upscale-factor 2 --resume"
done

# ─── Season reel ─────────────────────────────────────────────────────
step "compile-season" "$SR compile $SERIES"
