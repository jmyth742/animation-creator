# ─────────────────────────────────────────────────────────────────────
#  Overnight — fill the GPU for ~10 hours with work that advances the show
#
#      scripts/jobctl start jobs/overnight-full.job.sh
#
#  Every step is checkpointed, so a crash, a disconnect or a deliberate stop
#  resumes at the step it died on rather than starting over.
#
#  The spine:
#    1. wait for the ep04 v2 render already in flight
#    2. generate REAL framing variety with FLUX for both leads
#    3. curate, and GATE on whether the survivors actually differ from each
#       other -- the metric that would have caught both failed datasets
#    4. train, probe, re-render only if that gate passes
#    5. build set libraries for the other five locations regardless, because
#       that work is useful whatever the LoRA does
#
#  Deliberately NOT blind: if the diversity gate fails, training is skipped and
#  the hours go to location work instead of reproducing a known failure.
# ─────────────────────────────────────────────────────────────────────
SERIES=tir-na-nog-legend
PY=/workspace/venv/bin/python
SETS=/workspace/text-to-video/series/$SERIES/sets

# ─── 1. Let the in-flight v2 render finish ───────────────────────────
NEEDS_COMFY=0
RETRIES=1

step "wait-v2" \
    "for i in \$(seq 1 240); do
       s=\$(cat .jobs/ep04-v2/state 2>/dev/null || echo none)
       [ \"\$s\" != \"running\" ] && break
       sleep 30
     done
     echo \"  ep04-v2 state: \$(cat .jobs/ep04-v2/state 2>/dev/null || echo 'never started')\"
     ls -la output/$SERIES/ep04/ep04_final.mp4 2>/dev/null || true"

# ─── 2. Real framing variety, via FLUX T2I ───────────────────────────
# I2V cannot vary framing: it preserves whatever its seed image contains. The
# staged plates came back 0.940 similar to each other -- labelled as eight
# framings, effectively one picture, the same regime that trained a LoRA that
# did nothing. T2I generates from text, so distance and angle are controllable.
NEEDS_COMFY=1
RETRIES=2

step "variety-oisin" "$PY scripts/build_framing_variety.py $SERIES oisin --per-framing 6"
step "variety-niamh" "$PY scripts/build_framing_variety.py $SERIES niamh --per-framing 6"

# ─── 3. Curate, and record whether the data is trainable ─────────────
NEEDS_COMFY=0
RETRIES=1

step "curate-oisin" \
    "$PY scripts/curate_character_dataset.py $SERIES oisin --trigger o1s1nx \
        --keep 28 --min-identity 0.76 2>&1 | tee /workspace/review/curate_oisin.txt | tail -25"

step "curate-niamh" \
    "$PY scripts/curate_character_dataset.py $SERIES niamh --trigger n1amhx \
        --keep 28 --min-identity 0.76 2>&1 | tee /workspace/review/curate_niamh.txt | tail -25"

# The gate. Writes a marker file the training steps read. A dataset whose
# images are >90% similar to each other is one picture wearing eight labels.
step "diversity-gate" \
    "rm -f /workspace/review/TRAINABLE
     $PY - <<'EOF'
import re, sys
from pathlib import Path
ok = True
for who in ('oisin', 'niamh'):
    t = Path(f'/workspace/review/curate_{who}.txt')
    if not t.exists():
        print(f'  {who}: no curate report'); ok = False; continue
    m = re.search(r'pairwise similarity between kept images: mean ([0-9.]+)', t.read_text())
    if not m:
        print(f'  {who}: no diversity number in report'); ok = False; continue
    v = float(m.group(1))
    verdict = 'TRAINABLE' if v <= 0.90 else 'TOO SIMILAR'
    print(f'  {who}: pairwise {v:.3f}  {verdict}')
    if v > 0.90:
        ok = False
if ok:
    Path('/workspace/review/TRAINABLE').write_text('yes\n')
    print('\n  gate PASSED — training will run')
else:
    print('\n  gate FAILED — training skipped, hours go to location work instead')
    print('  (this is the check that would have caught both failed datasets)')
EOF"

# ─── 4. Train, but only on data that passed ──────────────────────────
# Rank 64: the training notes call it the fix for identity drifting across a
# clip, which is the S2V failure mode. Deliberately more epochs than the
# rank-32 run -- for a fictional character, overfitting is the goal, PROVIDED
# the dataset varies in everything except the identity.
NEEDS_COMFY=0
RETRIES=1

# musubi caches encoded latents keyed by DIRECTORY, not by content. A cache
# built from a previous dataset is reused silently: tonight it had 82 entries
# from the Aug-23 photoreal set and reported "total batches: 41" while the
# directory held 28 curated cel images. Training would have consumed the old
# photoreal frames and produced another useless LoRA with no error anywhere.
step "clear-stale-cache" \
    "set -e
     for c in oisin niamh; do
       d=/workspace/training_models/wan22/cache_v3/\$c
       n_img=\$(ls /workspace/datasets/\$c/*.png 2>/dev/null | wc -l)
       if [ -d \"\$d\" ]; then
         n_cache=\$(ls \"\$d\" 2>/dev/null | wc -l)
         echo \"  \$c: \$n_img images, \$n_cache cache entries — clearing cache\"
         rm -rf \"\$d\"
       else
         echo \"  \$c: \$n_img images, no cache\"
       fi
       python scripts/build_character_dataset.py config \$c | tail -1
     done"

step "free-gpu-train" \
    "if [ -f /workspace/review/TRAINABLE ]; then
       bash scripts/ensure_comfyui.sh stop; sleep 5;
       nvidia-smi --query-gpu=memory.used --format=csv,noheader;
     else echo '  skipped — gate did not pass'; fi"

step "train-oisin-r64" \
    "if [ -f /workspace/review/TRAINABLE ]; then
       bash /workspace/training_models/wan22/train_character.sh oisin 64 20;
     else echo '  skipped — gate did not pass'; fi"

step "install-loras" \
    "if [ -f /workspace/review/TRAINABLE ]; then
       set -e
       for c in oisin; do
         src=/workspace/lora_outputs_v3/\${c}_r64
         [ -d \"\$src\" ] || src=/workspace/lora_outputs_v3/\$c
         # Pick the NEWEST match, never a glob. The output directory also held
         # Aug-23 photoreal LoRAs whose names match the same pattern, so a bare
         # glob either errors on two arguments or silently installs the wrong
         # era's weights and the probe then measures nothing useful.
         lo=\$(ls -t \$src/\$c-wan22-*low*.safetensors 2>/dev/null | head -1)
         hi=\$(ls -t \$src/\$c-wan22-*high*.safetensors 2>/dev/null | head -1)
         [ -n "\$lo" ] && [ -n "\$hi" ] || { echo "  no LoRA files for \$c"; exit 1; }
         for f in "\$lo" "\$hi"; do
           now=\$(date +%s); mt=\$(stat -c %Y "\$f"); age=\$((now - mt))
           if [ "\$age" -ge 43200 ]; then
             echo "  refusing to install a stale LoRA: \$f"
             exit 1
           fi
         done
         echo "  low : \$lo"
         echo "  high: \$hi"
         cp "\$lo" ComfyUI/models/loras/\$c-cel64-low.safetensors
         cp "\$hi" ComfyUI/models/loras/\$c-cel64-high.safetensors
         echo \"  installed \$c-cel64\"
       done
       ls -la ComfyUI/models/loras/ | grep cel64
     else echo '  skipped — gate did not pass'; fi"

# ─── 6. Probe the new LoRAs against the recorded baseline ────────────
NEEDS_COMFY=1
step "probe-loras" \
    "if [ -f /workspace/review/TRAINABLE ]; then
       bash scripts/ensure_comfyui.sh ensure >/dev/null 2>&1; sleep 5
       $PY - <<'EOF'
import json, sys
from pathlib import Path
p = Path('series/tir-na-nog-legend/bible.json')
b = json.loads(p.read_text())
for k, t in (('oisin', 'o1s1nx'),):
    # Only wire a LoRA that is actually on disk. Wiring it first left the bible
    # pointing at a file that did not exist yet, and strict mode would have
    # aborted the next render at its first shot.
    f = Path('ComfyUI/models/loras') / f'{k}-cel64-high.safetensors'
    if not f.exists():
        print(f'  {k}: {f.name} not on disk — leaving the bible alone')
        continue
    c = b['characters'][k]
    c['lora_path'] = f'{k}-cel64.safetensors'
    c['trigger_word'] = t
    c['lora_strength'] = 0.9
    print(f\"  {k}: {c['lora_path']} trigger={t}\")
p.write_text(json.dumps(b, indent=2) + '\n')
EOF
       $PY scripts/selftest.py | tail -2
       rm -f /workspace/review/LORA_HELPS
       $PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/probe_lora.py \
           2>&1 | tee /workspace/review/probe_oisin_r64.txt
       $PY - <<'EOF'
import re, sys
from pathlib import Path
t = Path('/workspace/review/probe_oisin_r64.txt').read_text()
m = re.search(r'mean ([0-9.]+) -> ([0-9.]+)', t)
if not m:
    print('  no probe numbers found — treating as NOT helping'); sys.exit(0)
before, after = float(m.group(1)), float(m.group(2))
print(f'  probe: mean {before:.3f} -> {after:.3f}  ({after-before:+.3f})')
if after - before >= 0.02:
    Path('/workspace/review/LORA_HELPS').write_text('yes\n')
    print('  LoRA HELPS — Niamh will be trained too')
else:
    print('  LoRA does not clear +0.020 — skipping Niamh, saving ~3 hours')
    print('  (the first rank-32 attempt moved it +0.006)')
EOF
     else echo '  skipped — gate did not pass'; fi"

# ─── Niamh, but only if Oisin's LoRA earned it ───────────────────────
# 93 minutes per model, four models for two characters. Training Niamh before
# knowing whether the approach works at all would risk seven hours to learn
# what the probe answers in twenty minutes. She also starts from 0.848 while
# Oisin is at 0.757, so she has far less to gain.
NEEDS_COMFY=0
RETRIES=1

step "train-niamh-r64" \
    "if [ -f /workspace/review/LORA_HELPS ]; then
       bash scripts/ensure_comfyui.sh stop; sleep 5
       bash /workspace/training_models/wan22/train_character.sh niamh 64 20
       src=/workspace/lora_outputs_v3/niamh_r64
       [ -d \"\$src\" ] || src=/workspace/lora_outputs_v3/niamh
       cp \$src/niamh-wan22-*low*.safetensors  ComfyUI/models/loras/niamh-cel64-low.safetensors
       cp \$src/niamh-wan22-*high*.safetensors ComfyUI/models/loras/niamh-cel64-high.safetensors
       python - <<'EOF'
import json
from pathlib import Path
p = Path('series/tir-na-nog-legend/bible.json')
b = json.loads(p.read_text())
c = b['characters']['niamh']
c['lora_path'] = 'niamh-cel64.safetensors'
c['trigger_word'] = 'n1amhx'
c['lora_strength'] = 0.9
p.write_text(json.dumps(b, indent=2) + '\n')
print('  niamh wired to the cel64 LoRA')
EOF
     else echo '  skipped — Oisin probe did not show the LoRA helping'; fi"

# ─── 5. Location work — useful whatever the LoRA did ─────────────────
# Five locations still have no set library. Every future episode that visits
# them needs one, and a plate is the only thing that has reliably held
# geography from shot to shot.
NEEDS_COMFY=1
RETRIES=2

step "sets-storm-cliffs"   "$PY scripts/build_sets.py setups $SERIES storm_cliffs"
step "sets-stormy-sea"     "$PY scripts/build_sets.py setups $SERIES stormy_sea"
step "sets-sunlight-path"  "$PY scripts/build_sets.py setups $SERIES sunlight_path"
step "sets-tir-na-nog"     "$PY scripts/build_sets.py setups $SERIES tir_na_nog"
step "sets-ruined-ireland" "$PY scripts/build_sets.py setups $SERIES ruined_ireland"

step "sets-report" "$PY scripts/build_sets.py list $SERIES"

# ─── 7. ep04 v3, only if the probe was worth it ──────────────────────
RETRIES=3
# v3 runs whether or not the LoRAs trained. v2 seeded EVERY shot from a staged
# plate, including tight close-ups -- and that was measured wrong: the portrait
# scores 1.000 against the anchor while a plate scores 0.908, so close-ups lost
# 0.02-0.04 each buying a background the frame barely shows. v3 carries the
# corrected policy (portrait for tight close-ups, staged plate for wides), which
# is worth testing on its own even if the LoRA gate rejected the data.
step "render-v3" \
    "d=ComfyUI/output/video/$SERIES; mkdir -p \$d/ep04-v2;
     for f in \$d/ep04_s*.mp4; do [ -e \"\$f\" ] && mv \"\$f\" \$d/ep04-v2/; done
     cp output/$SERIES/ep04/ep04_final.mp4 output/$SERIES/ep04/ep04_v2_final.mp4 2>/dev/null || true
     [ -f /workspace/review/TRAINABLE ] && echo '  with new LoRAs' || echo '  seeding fix only (LoRA gate did not pass)'
     $PY scripts/showrunner.py produce $SERIES --episode 4 --lightning"

step "verify-v3" \
    "$PY scripts/verify_render.py $SERIES --episode 4 || true;
     $PY /tmp/claude-0/-workspace/ff8063a2-884f-41b0-8ae0-53d58f36b62e/scratchpad/lipsync_align.py || true"

# ─── 8. Report ───────────────────────────────────────────────────────
NEEDS_COMFY=0
RETRIES=1

step "final-report" \
    "echo '════════ OVERNIGHT SUMMARY ════════';
     date '+finished %H:%M';
     echo; echo '--- episodes ---';
     ls -lh output/$SERIES/ep04/*.mp4 2>/dev/null | awk '{print \"  \",\$5,\$9}';
     echo; echo '--- set libraries ---';
     $PY scripts/build_sets.py list $SERIES 2>/dev/null | tail -20;
     echo; echo '--- trainability gate ---';
     [ -f /workspace/review/TRAINABLE ] && echo '  PASSED — LoRAs trained and probed' || echo '  FAILED — training skipped deliberately';
     echo; echo '--- curate reports ---';
     grep -h 'pairwise similarity' /workspace/review/curate_*.txt 2>/dev/null | sed 's/^/  /';
     echo; echo '--- archive ---';
     $PY scripts/archive_asset.py list 2>/dev/null | tail -3"
