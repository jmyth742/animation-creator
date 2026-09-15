#!/bin/bash
# Fourth tranche: ep16, then ep12's dialogue closes which predate the grammar.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2c\.s[h]" > /dev/null; do sleep 180; done
log "night2c finished"

log "=== gates ==="
$PY scripts/selftest.py > /tmp/e16_self.log 2>&1 || { log "SELFTEST FAILED"; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 16 > /tmp/e16_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -20 /tmp/e16_pre.log; exit 1; }
log "gates passed"

log "=== ep16 The First Morning (13 shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 16 --quality final --upscale 2>&1 | tail -60
$PY scripts/verify_render.py tir-na-nog-legend --episode 16 2>&1 | tail -18
log "=== camera pass on ep16 ==="
$PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode 16 2>&1 | tail -5
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 16 --quality final --upscale --resume 2>&1 | tail -8

log "=== ep12 dialogue closes (predates the grammar entirely) ==="
$PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode 12 2>&1 | tail -14

log "=== inspector pages for the new episodes ==="
for E in 15 16; do $PY scripts/shot_inspector.py tir-na-nog-legend --episode $E --measure 2>&1 | tail -2; done
log "NIGHT2D DONE"
