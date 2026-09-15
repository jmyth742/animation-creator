#!/bin/bash
# Behind night2: the first episode built on real two-shots, then a graded
# comparison so the Mignola direction can be judged rather than assumed.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2\.s[h]" > /dev/null; do sleep 120; done
log "night2 finished"

log "=== gates ==="
$PY scripts/selftest.py > /tmp/e15_self.log 2>&1 || { log "SELFTEST FAILED"; tail -20 /tmp/e15_self.log; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 15 > /tmp/e15_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -25 /tmp/e15_pre.log; exit 1; }
log "gates passed"

log "=== ep15 What She Came To Ask (15 shots, 3 real two-shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 15 \
    --quality final --upscale 2>&1 | tail -70

log "=== verify ==="
$PY scripts/verify_render.py tir-na-nog-legend --episode 15 2>&1 | tail -22

log "=== camera pass ==="
$PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode 15 2>&1 | tail -6
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 15 \
    --quality final --upscale --resume 2>&1 | tail -12

log "=== inspector page ==="
$PY scripts/shot_inspector.py tir-na-nog-legend --episode 15 --measure 2>&1 | tail -3

log "NIGHT2B DONE"
