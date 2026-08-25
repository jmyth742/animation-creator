# ─────────────────────────────────────────────────────────────────────
#  ep04 v2 — staged plates, eyeline coverage, palette fix, timeline audio
#
#      scripts/jobctl start jobs/ep04-v2.job.sh
#
#  Deliberately does NOT use the new cel LoRA. It measured worse than nothing:
#  identity +0.006/+0.008 on wides, -0.027 on the close-up, and it dragged the
#  close-up's style score from 1.000 to 0.576. Oisin stays on the Aug-23 LoRA,
#  which lora_is_stale() drops from S2V automatically -- exactly the v1
#  behaviour. That makes STAGED PLATES the only changed variable for identity,
#  so if v2 improves we know why.
#
#  What changed since the 13:39 render:
#    1. staged plates   every shot seeds from a picture with the character IN it
#    2. eyeline coverage  master/reverse per the 180-degree rule, in ep04.json
#    3. palette fix     the green-ogre clause no longer leads the prompt
#    4. timeline audio  lip sync laid at absolute offsets, no per-cut drift
# ─────────────────────────────────────────────────────────────────────
SERIES=tir-na-nog-legend
EP=4
PY=/workspace/venv/bin/python

NEEDS_COMFY=0
RETRIES=1

# The staged plates are the whole point of this render. If they are missing,
# every close-up falls back to the bare portrait and v2 is just v1 again with
# a different audio track -- so fail here rather than discovering it after 80
# minutes of GPU.
step "plates-present" \
    "$PY - <<'EOF'
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
import showrunner as sr
sr.set_current_series('$SERIES')
ep = sr.load_json(sr.episode_path('$SERIES', $EP))
missing, staged = [], 0
for s in ep['scenes']:
    if not (s.get('staging') and s.get('characters') and s.get('location')):
        continue
    who = s['characters'][0]
    if s.get('dialogue'):
        spk = s['dialogue'][0].get('character', who)
        who = spk if spk in s['characters'] else who
    base = s.get('setup') or 'master'
    d = sr.series_path('$SERIES') / 'sets' / s['location']
    hits = list(d.glob(f'{base}__{who}_*.png')) if d.is_dir() else []
    if hits:
        staged += 1
    else:
        missing.append(f\"{s['id']} needs {base}__{who}_*\")
print(f'  {staged} shot(s) will seed from a staged plate')
if missing:
    sys.exit('  missing staged plates:\\n    ' + '\\n    '.join(missing))
EOF"

step "selftest"  "$PY scripts/selftest.py"
step "preflight" "$PY scripts/preflight.py $SERIES --episode $EP"

# ─── Render ──────────────────────────────────────────────────────────
# No --resume: every existing clip predates the plates, the coverage and the
# palette fix, so resuming would keep exactly what we are trying to replace.
NEEDS_COMFY=1
RETRIES=3

step "archive-v1" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v1-cel;
     n=0; for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] || continue; mv \"\$f\" \$d/ep04-v1-cel/; n=\$((n+1)); done;
     cp output/$SERIES/ep04/ep04_final_lipsync_fixed.mp4 output/$SERIES/ep04/ep04_v1_final.mp4 2>/dev/null || true;
     echo \"  archived \$n v1 clip(s)\""

step "render" \
    "$PY scripts/showrunner.py produce $SERIES --episode $EP --lightning"

# ─── Verify ──────────────────────────────────────────────────────────
NEEDS_COMFY=0
RETRIES=1

step "verify" "$PY scripts/verify_render.py $SERIES --episode $EP --flag || true"

step "compare" \
    "echo '── v2 vs the recorded pre-plate baseline ──';
     cat /workspace/review/baselines/ep04_preLoRA_identity.txt;
     echo;
     echo '  the number that matters is SPREAD: 0.27 before.';
     echo '  a character at a steady 0.85 reads as one person;';
     echo '  one averaging 0.85 across 0.63-0.92 reads as several.'"

step "lipsync-check" \
    "$PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"
