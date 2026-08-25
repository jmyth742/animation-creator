# ─────────────────────────────────────────────────────────────────────
#  ep04 v2 — everything together
#
#      scripts/jobctl start jobs/ep04-v2-full.job.sh
#
#  Four changes over the 13:39 render, in one pass so the comparison is clean:
#
#    1. cel character LoRAs      identity: Oisin was ~5 different men
#    2. persistent set library   geography: two people on one headland came
#                                back on two separate sea stacks
#    3. eyeline coverage         the 180-degree rule, authored into ep04.json
#    4. palette fix              five S2V shots predate it; s03 is green-cast
#
#  Run AFTER jobs/cel-loras.job.sh completes. That job wires the bible, so if
#  it has not run, the LoRA steps here find nothing and the render silently
#  falls back to no-LoRA -- which is the whole defect we are fixing.
# ─────────────────────────────────────────────────────────────────────
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

# ─── Confirm the LoRAs actually landed ───────────────────────────────
# A missing LoRA renders without it, looks plausible and proves nothing.
# Strict mode aborts on it at render time, but failing here costs seconds
# instead of finding out forty minutes into a render.
NEEDS_COMFY=0
RETRIES=1

step "loras-present" \
    "set -e
     for c in oisin niamh; do
       f=/workspace/text-to-video/ComfyUI/models/loras/\$c-wan22-high.safetensors
       [ -f \"\$f\" ] || { echo \"  missing \$f — run jobs/cel-loras.job.sh first\"; exit 1; }
       echo \"  \$c: \$(stat -c%s \"\$f\") bytes  \$(stat -c%y \"\$f\" | cut -d. -f1)\"
     done
     $PY - <<'EOF'
import json, sys
b = json.load(open('series/$SERIES/bible.json'))
# A non-empty lora_path is not enough: before the training job runs, these
# still point at the Aug-23 photoreal LoRAs, which is exactly the defect
# being fixed. Assert the bible names the NEW files.
bad = []
for k in ('oisin', 'niamh'):
    c = b['characters'].get(k, {})
    if c.get('lora_path') != f'{k}-wan22.safetensors' or not c.get('trigger_word'):
        bad.append(k + ' -> ' + str(c.get('lora_path')))
if bad:
    sys.exit(f'  bible still points at the old LoRAs: {bad}\n'
             f'  run jobs/cel-loras.job.sh (its wire-bible step fixes this)')
for k in ('oisin','niamh'):
    c = b['characters'][k]
    print(f\"  bible {k}: {c['lora_path']} trigger={c['trigger_word']} @{c.get('lora_strength')}\")
EOF"

# The new LoRAs must be NEWER than the reference images, or lora_is_stale()
# drops them from every S2V shot and the identity fix silently does nothing.
step "loras-not-stale" \
    "$PY - <<'EOF'
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
import showrunner as sr
rd = sr.series_path('$SERIES') / 'reference_images'
stale = [n for n in ('oisin-wan22.safetensors', 'niamh-wan22.safetensors')
         if sr.lora_is_stale(n, rd)]
if stale:
    sys.exit(f'  these read as stale and would be dropped from S2V: {stale}')
print('  both LoRAs are newer than the anchors — they will apply to S2V')
EOF"

# ─── Build the set library ───────────────────────────────────────────
# Camera setups derived from each location plate, then the two characters
# staged into the setups ep04 actually uses. Only farewell_cliff is needed
# for this episode; --all would build five locations we do not shoot.
NEEDS_COMFY=1
RETRIES=2

step "sets-setups" \
    "$PY scripts/build_sets.py setups $SERIES farewell_cliff"

step "sets-stage-oisin" \
    "$PY scripts/build_sets.py stage $SERIES farewell_cliff oisin --only master,side --staging close"

step "sets-stage-niamh" \
    "$PY scripts/build_sets.py stage $SERIES farewell_cliff niamh --only reverse --staging close"

step "sets-list" \
    "$PY scripts/build_sets.py list $SERIES"

# ─── Gates ───────────────────────────────────────────────────────────
NEEDS_COMFY=0
RETRIES=1

step "selftest"  "$PY scripts/selftest.py"
step "preflight" "$PY scripts/preflight.py $SERIES --episode $EP"

# ─── Render ──────────────────────────────────────────────────────────
# Every clip is regenerated: the existing ones predate the LoRAs, the sets
# and (for five S2V shots) the palette fix, so --resume would keep them.
NEEDS_COMFY=1
RETRIES=3

step "archive-v1" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v1-cel;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-v1-cel/; n=\$((n+1)); done;
     cp output/$SERIES/ep04/ep04_final.mp4 output/$SERIES/ep04/ep04_final_v1cel.mp4 2>/dev/null || true;
     echo \"  archived \$n clip(s) from the 13:39 render\""

step "render" \
    "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

# ─── Verify against the recorded baseline ────────────────────────────
NEEDS_COMFY=0
RETRIES=1

step "verify" \
    "$PY scripts/verify_render.py $SERIES --episode $EP --flag || true"

step "compare" \
    "echo '── identity vs the pre-LoRA baseline ──';
     cat /workspace/review/baselines/ep04_preLoRA_identity.txt;
     echo;
     echo '  target was: Oisin above 0.85 and CLUSTERED, not spread 0.63-0.90'"
