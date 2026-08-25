# ep04 v3 — the corrected seeding rule, measured. No new LoRA.
#
# v2 seeded EVERY shot from a staged plate. Measured across all 17:
#   wide shots        s09 +0.195   s02 +0.165
#   everything else   -0.020 to -0.073
# because a plate caps identity at 0.908 while the portrait is 1.000.
#
# v3 applies the rule the data supports: staged plate ONLY where the shot is
# too wide for a portrait to fill; portrait everywhere else. It should hold
# both large gains and drop all seven regressions.
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

NEEDS_COMFY=0
RETRIES=1
step "selftest"  "$PY scripts/selftest.py"
step "preflight" "$PY scripts/preflight.py $SERIES --episode $EP"

step "show-seeding" \
    "$PY - <<'PYEOF'
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
import showrunner as sr
sr.set_current_series('$SERIES')
ep = sr.load_json(sr.episode_path('$SERIES', $EP))
for s in ep['scenes']:
    g = sr.get_scene_seed_image(s, '$SERIES', None)
    print(f\"  {s['id'][-3:]}  {s['visual'][:34]:34} {Path(g).name if g else None}\")
PYEOF"

NEEDS_COMFY=1
RETRIES=3
step "archive-v2" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v2;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-v2/; n=\$((n+1)); done;
     cp output/$SERIES/ep04/ep04_final.mp4 output/$SERIES/ep04/ep04_v2_final.mp4 2>/dev/null || true;
     echo \"  archived \$n v2 clip(s)\""

step "render" "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

NEEDS_COMFY=0
RETRIES=1
step "verify" "$PY scripts/verify_render.py $SERIES --episode $EP || true"
step "lipsync" "$PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"
