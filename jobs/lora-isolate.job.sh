# ─────────────────────────────────────────────────────────────────────
#  Is the character LoRA weak, or is Lightning swamping it?
#
#  The matrix found no difference from the character LoRA -- but it was
#  stacked under the Lightning distill LoRA at 8 steps / cfg 1.0, whereas
#  the earlier test where a character LoRA plainly DID work used the LoRA
#  alone at 18 steps / cfg 5.0. Two variables moved, so the null result
#  proves nothing. This moves one at a time, all T2V with no seed image
#  so identity can only come from the LoRA.
# ─────────────────────────────────────────────────────────────────────
SERIES="tir-na-nog-legend"
ISO="python scripts/lora_isolate.py"

NEEDS_COMFY=0
step "wait-queue" '
    for J in .jobs/day2-characters .jobs/day2-followups; do
        [ -d "$J" ] || continue
        while true; do
            s=$(cat "$J/state" 2>/dev/null || echo unknown)
            p=$(cat "$J/pid" 2>/dev/null)
            if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then sleep 120; continue; fi
            [ "$s" = "running" ] && { sleep 120; continue; }
            echo "$(basename $J) finished: $s"; break
        done
    done'

NEEDS_COMFY=1
step "isolate-niamh" "$ISO $SERIES --scene ep01_s11 --lora niamh-r64.safetensors"
step "isolate-oisin" "$ISO $SERIES --scene ep01_s03 --lora oisin-r64.safetensors"
step "report" "ls -lh /workspace/review/lora_isolate/; cat /workspace/review/lora_isolate/*_isolate.json"
