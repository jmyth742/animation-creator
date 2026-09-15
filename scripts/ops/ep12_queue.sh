#!/bin/bash
# ep12 "The Ride Back", after the b-roll and re-roll finish.
#
# Settings confirmed rather than assumed: the sampler A/B tested shift 3, 8
# and 12 at fixed seed and every alternative LOST motion (0.91-0.95x) while
# identity moved 0.018 across the whole range. shift 12 stays.
#
# It also found an interaction the earlier steps sweep could not see, because
# that sweep only ever ran at shift 12: dropping 15->10 steps costs 0.006
# identity at shift 12 and 0.032 at shift 8. Our undocumented shift is the
# one that makes the cheap step count affordable.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }

while pgrep -f "gpu_queue\.sh" > /dev/null; do sleep 60; done
log "upstream queue finished"

log "=== gates ==="
$PY scripts/selftest.py > /tmp/ep12_selftest.log 2>&1 || { log "SELFTEST FAILED"; tail -20 /tmp/ep12_selftest.log; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 12 > /tmp/ep12_preflight.log 2>&1 || { log "PREFLIGHT FAILED"; tail -20 /tmp/ep12_preflight.log; exit 1; }
log "gates passed"

log "=== ep12 The Ride Back (11 shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 12 --quality final --upscale 2>&1 | tail -60

log "=== verify ==="
$PY scripts/verify_render.py tir-na-nog-legend --episode 12 2>&1 | tail -20
log "EP12 DONE"
