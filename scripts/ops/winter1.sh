#!/bin/bash
# The Quiet Winter, chapter one — behind the winter plate forge.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "gen_real_plate[s]" > /dev/null; do sleep 30; done
log "winter plates forged"
$PY scripts/build_builder_data.py tir-na-nog-legend > /dev/null 2>&1

log "=== gates ==="
$PY scripts/lint_episode.py tir-na-nog-legend --episode 18 --strict 2>&1 | tail -4
$PY scripts/selftest.py > /tmp/e18_self.log 2>&1 || { log "SELFTEST FAILED"; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 18 > /tmp/e18_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -20 /tmp/e18_pre.log; exit 1; }
log "gates passed"

log "=== ep18 The First Cold (ch.1 of The Quiet Winter) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 18 --quality final --upscale 2>&1 | tail -40
log "=== camera + master + verify ==="
$PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode 18 2>&1 | tail -4
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 18 --quality final --upscale --resume 2>&1 | tail -6
$PY scripts/master_audio.py tir-na-nog-legend --episode 18 2>&1 | tail -3
$PY scripts/episode_qc.py tir-na-nog-legend --episode 18 2>&1 | tail -10
log "WINTER1 DONE"
