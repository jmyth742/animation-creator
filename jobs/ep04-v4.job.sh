# ep04 v4 — everything that measured positive, together.
#
#   plate seeding for WIDE shots      s09 +0.195, s02 +0.165 (v3, measured)
#   portrait for everything else      a portrait is a 1.000 identity reference
#   Oisin cel64 LoRA (rank 64)        mean +0.116 on the probe, incl. +0.087 on
#                                     an S2V dialogue shot that plates cannot reach
#   palette fix, eyeline coverage, absolute-timeline audio
#
# Niamh stays on her existing LoRA. She scores 0.848 with a spread of 0.106 --
# she was never the problem, and her rank-64 run is unproven. It resumes after
# this render rather than blocking it.
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

NEEDS_COMFY=0
RETRIES=1

step "loras-present" \
    "set -e
     for f in oisin-cel64-high oisin-cel64-low; do
       [ -f ComfyUI/models/loras/\$f.safetensors ] || { echo \"  missing \$f\"; exit 1; }
     done
     echo '  oisin-cel64 present'
     $PY - <<'PYEOF'
import json, sys
b = json.load(open('series/$SERIES/bible.json'))
c = b['characters']['oisin']
if c.get('lora_path') != 'oisin-cel64.safetensors' or c.get('trigger_word') != 'o1s1nx':
    sys.exit('  bible not wired to the proven LoRA: ' + str(c.get('lora_path')))
print(f\"  oisin -> {c['lora_path']} trigger={c['trigger_word']} @{c.get('lora_strength')}\")
print(f\"  niamh -> {b['characters']['niamh']['lora_path']} (unchanged, she scores 0.848)\")
PYEOF"

step "selftest"  "$PY scripts/selftest.py"
step "preflight" "$PY scripts/preflight.py $SERIES --episode $EP"

NEEDS_COMFY=1
RETRIES=3
step "archive-v3" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v3;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-v3/; n=\$((n+1)); done;
     cp output/$SERIES/ep04/ep04_final.mp4 output/$SERIES/ep04/ep04_v3_final.mp4 2>/dev/null || true;
     echo \"  archived \$n v3 clip(s)\""

step "render" "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

NEEDS_COMFY=0
RETRIES=1
step "verify"  "$PY scripts/verify_render.py $SERIES --episode $EP || true"
step "lipsync" "$PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"
