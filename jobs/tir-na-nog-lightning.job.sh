# ─────────────────────────────────────────────────────────────────────
#  Tir na nOg legend — full re-render with step-distilled sampling
#
#  Measured on this box (49 frames, 480x832): 18 steps/cfg 5.0 = 490s and
#  a smeared result; 8 steps/cfg 1.0 with the LightX2V LoRA = 120s and a
#  clearly better one. So this is a FINAL-quality pass that costs less
#  than the old draft did.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
SR="python scripts/showrunner.py"
EP_OUT="output/$SERIES/ep01"

step "archive-v3" "
    if [ -f '$EP_OUT/ep01_final.mp4' ] && [ ! -f '$EP_OUT/ep01_final_v3.mp4' ]; then
        cp '$EP_OUT/ep01_final.mp4' '$EP_OUT/ep01_final_v3.mp4'; echo 'kept v3'
    else echo 'v3 already archived'; fi"

# Move the old clips aside so every shot regenerates under the new sampler.
step "park-old-clips" "
    V=ComfyUI/output/video/$SERIES
    mkdir -p \$V/pre-lightning
    mv \$V/*.mp4 \$V/pre-lightning/ 2>/dev/null || true
    echo \"parked \$(ls \$V/pre-lightning/*.mp4 2>/dev/null | wc -l) clips\""

step "render-lightning" \
    "$SR produce $SERIES --episode 1 --lightning --lightning-steps 8 --optimization none"

step "report" "ls -lh '$EP_OUT'/ep01_final*.mp4; ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 '$EP_OUT/ep01_final.mp4'"
