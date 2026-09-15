#!/bin/bash
# Chapter two behind chapter one.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "winter1\.s[h]" > /dev/null; do sleep 120; done
log "chapter one finished"
$PY scripts/lint_episode.py tir-na-nog-legend --episode 19 --strict 2>&1 | tail -3
$PY scripts/preflight.py tir-na-nog-legend --episode 19 > /tmp/e19_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -15 /tmp/e19_pre.log; exit 1; }
log "=== ep19 What the Land Hears (ch.2) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 19 --quality final --upscale 2>&1 | tail -30
$PY scripts/add_camera_to_episode.py tir-na-nog-legend --episode 19 2>&1 | tail -3
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 19 --quality final --upscale --resume 2>&1 | tail -5
$PY scripts/master_audio.py tir-na-nog-legend --episode 19 2>&1 | tail -3
$PY scripts/episode_qc.py tir-na-nog-legend --episode 19 2>&1 | tail -8
log "WINTER2 DONE"
