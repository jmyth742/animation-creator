#!/bin/bash
# Outstanding GPU work, back to back. ep12 is deliberately NOT here: the
# sampler A/B decides what shift it should render at, and rendering 11 shots
# at a setting the A/B is about to reject wastes two hours.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log() { echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "sampler_ab\.py" > /dev/null; do sleep 30; done
log "sampler A/B finished"
log "=== vertical b-roll ==="
$PY scripts/render_vertical_broll.py tir-na-nog-legend 2>&1 | tail -30
log "=== reroll: remaining weak shots ==="
$PY scripts/reroll_weak_shots.py tir-na-nog-legend --worst 8 --takes 2 --steps 12 2>&1 | tail -30
log "QUEUE DONE"
