# ─────────────────────────────────────────────────────────────────────
#  Cel-shaded character LoRAs — Oisín and Niamh
#
#      scripts/jobctl start jobs/cel-loras.job.sh
#
#  WHY: with the series committed to cel-shaded animation, moving the style to
#  the front of the prompt fixed the LOOK of S2V dialogue shots but not the
#  IDENTITY -- Oisín came back clean-shaven with the wrong hair. Prompt weight
#  cannot carry a specific face; that is what a character LoRA is for, and it
#  locks identity across T2V, I2V and S2V at once rather than per-renderer.
#
#  The canonical portrait is NOT regenerated. The series reference images are
#  already the committed style, so they ARE the canonical face -- generating
#  fresh candidates would train the LoRA on a face that no shot is seeded from.
#
#  After this completes the bible still has to be wired (lora_path +
#  trigger_word per character), or the LoRA loads, wires correctly and does
#  absolutely nothing with no error. selftest.py asserts the trigger reaches
#  the prompt; run it before rendering.
# ─────────────────────────────────────────────────────────────────────
BUILD="python scripts/build_character_dataset.py"
TRAIN="bash /workspace/training_models/wan22/train_character.sh"
REFS=/workspace/text-to-video/series/tir-na-nog-legend/reference_images
BUILDS=/workspace/text-to-video/training/character_builds

# ─── Seed each build from the committed cel-shaded anchor ────────────
NEEDS_COMFY=0
RETRIES=1

# A brief carrying the OLD style trains the LoRA in the old style, silently.
# build_character_dataset builds its clips with brief["style"], so this gate
# is the difference between a cel-shaded LoRA and another photoreal one.
step "sync-briefs" \
    "python scripts/sync_character_briefs.py tir-na-nog-legend &&
     python scripts/sync_character_briefs.py tir-na-nog-legend --check"

step "seed-canonical" \
    "set -e
     for c in oisin niamh; do
       mkdir -p $BUILDS/\$c
       cp -f $REFS/char_\$c.png $BUILDS/\$c/canonical.png
       echo \"  \$c canonical <- char_\$c.png (\$(stat -c%s $BUILDS/\$c/canonical.png) bytes)\"
     done"

# ─── Dataset: animate each portrait, harvest frames ──────────────────
NEEDS_COMFY=1
RETRIES=2

step "ds-oisin-clips"  "$BUILD clips  oisin --count 8 --steps 18 --force"
step "ds-oisin-frames" "$BUILD frames oisin --per-clip 5"
step "ds-oisin-config" "$BUILD config oisin"

step "ds-niamh-clips"  "$BUILD clips  niamh --count 8 --steps 18 --force"
step "ds-niamh-frames" "$BUILD frames niamh --per-clip 5"
step "ds-niamh-config" "$BUILD config niamh"

# A dataset that came out empty trains a LoRA that does nothing, and the
# training run still exits 0. Check before spending two hours on the GPU.
NEEDS_COMFY=0
RETRIES=1
step "ds-verify" \
    "set -e
     for c in oisin niamh; do
       n=\$(ls /workspace/datasets/\$c/*.png 2>/dev/null | wc -l)
       echo \"  \$c dataset: \$n images\"
       [ \"\$n\" -ge 20 ] || { echo \"  too few images for \$c — aborting\"; exit 1; }
     done"

# The brief gate above checks the PROMPT that makes the training clips. This
# checks the PIXELS that came out. Two different mistakes have now produced
# photoreal training data for a cel-shaded series -- a stale brief, and a clips
# stage that skipped regeneration because old clips were still on disk. A LoRA
# learns the style of its frames whatever the intent was, so verify the frames.
step "ds-style-check" \
    "python scripts/check_dataset_style.py tir-na-nog-legend oisin niamh"

# ─── Hand the GPU over to the trainer ────────────────────────────────
# ComfyUI holds ~15GB once a model is loaded; musubi needs all of it.
step "free-gpu" \
    "bash scripts/ensure_comfyui.sh stop; sleep 5; nvidia-smi --query-gpu=memory.used --format=csv,noheader"

# ─── Train ───────────────────────────────────────────────────────────
# Rank 32 is the recipe that produced the working LoRAs on this box. Rank 64
# holds a face across a whole clip rather than just the opening frames, which
# is the failure mode that matters for dialogue shots -- so train both and
# compare rather than assuming.
RETRIES=1
step "train-oisin-r32" "$TRAIN oisin 32 16"
step "train-niamh-r32" "$TRAIN niamh 32 16"

step "install-r32" \
    "set -e
     for c in oisin niamh; do
       cp /workspace/lora_outputs_v3/\$c/\$c-wan22-low.safetensors \
          /workspace/lora_outputs_v3/\$c/\$c-wan22-high.safetensors \
          /workspace/text-to-video/ComfyUI/models/loras/
     done
     ls -la /workspace/text-to-video/ComfyUI/models/loras/ | grep -E 'oisin|niamh'"

# Wire the bible automatically. Doing this by hand is the step that gets
# forgotten, and the failure is silent: the LoRA loads, wires correctly and
# does absolutely nothing because its trigger never reaches the prompt.
step "wire-bible" \
    "python - <<'EOF'
import json
from pathlib import Path
p = Path('series/tir-na-nog-legend/bible.json')
b = json.loads(p.read_text())
for key in ('oisin', 'niamh'):
    c = b['characters'].get(key)
    if not c:
        continue
    c['lora_path'] = f'{key}-wan22.safetensors'
    c['trigger_word'] = key.capitalize()
    c['lora_strength'] = 0.85
    print(f\"  {key}: lora_path={c['lora_path']} trigger={c['trigger_word']} strength={c['lora_strength']}\")
p.write_text(json.dumps(b, indent=2) + '\n')
EOF
     python scripts/selftest.py"

step "report" \
    "echo '── next: wire the bible, then verify ──';
     echo '  each character needs lora_path + trigger_word + lora_strength';
     echo '  then: python scripts/selftest.py   (asserts the trigger reaches the prompt)';
     echo '  then: python scripts/probe_shot.py tir-na-nog-legend --episode 4 --auto'"
