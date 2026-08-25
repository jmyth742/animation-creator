# ep04 FINAL — with the S2V reference fix.
#
# WanSoundImageToVideo writes the character reference into its CONDITIONING
# output; the sampler was reading raw text conditioning and using only the
# node's latent, so ref_image was discarded on every dialogue shot. Measured
# on the two worst shots in the episode:
#     s15  0.694 -> 0.921   (+0.227)
#     s07  0.719 -> 0.914   (+0.195)
# both now above the I2V average of 0.876, with cel style unchanged at 1.000.
#
# Plus everything already measured: plate seeding for wides, portrait for the
# rest, palette fix, eyeline coverage, absolute-timeline audio. No character
# LoRA on S2V (cross-family, destroys the style).
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

NEEDS_COMFY=0
RETRIES=1
step "selftest"  "$PY scripts/selftest.py"
step "preflight" "$PY scripts/preflight.py $SERIES --episode $EP"

NEEDS_COMFY=1
RETRIES=3
step "archive-v3" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v3-keep;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-v3-keep/; n=\$((n+1)); done;
     echo \"  archived \$n v3 clip(s)\""

step "render" "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

NEEDS_COMFY=0
RETRIES=1
step "verify"  "$PY scripts/verify_render.py $SERIES --episode $EP || true"
step "lipsync" "$PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"
