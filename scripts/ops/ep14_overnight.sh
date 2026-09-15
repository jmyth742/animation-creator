#!/bin/bash
# ep14 "What He Told the Ground" — 20 shots, 3:08, behind ep13.
#
# Present is wide and far away; memory is close enough to touch. That is not
# only a device: there are no aged-Oisin plates and no LoRA for one, so putting
# the present in wides and the memories in close-ups keeps his face off screen
# exactly where it would have to look older. The constraint and the grammar
# agree, which is how you know it is the right structure.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "ep13_overnight\.sh" > /dev/null; do sleep 60; done
log "ep13 finished"

log "=== gates ==="
$PY scripts/selftest.py > /tmp/e14_self.log 2>&1 || { log "SELFTEST FAILED"; tail -20 /tmp/e14_self.log; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 14 > /tmp/e14_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -25 /tmp/e14_pre.log; exit 1; }
log "gates passed"

log "=== ep14 What He Told the Ground (20 shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 14 \
    --quality final --upscale --no-grade --resume 2>&1 | tail -80

log "=== verify ==="
$PY scripts/verify_render.py tir-na-nog-legend --episode 14 2>&1 | tail -28
log "EP14 DONE"
