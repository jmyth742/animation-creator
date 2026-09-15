#!/bin/bash
# Behind ep12: does a wide-authored dialogue shot survive as a wide?
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "ep12_queue\.sh" > /dev/null; do sleep 60; done
log "ep12 finished"
for s in ep07_s01 ep10_s02 ep06_s06; do
  log "=== wide dialogue test: $s ==="
  $PY scripts/wide_dialogue_test.py tir-na-nog-legend --scene $s 2>&1 | tail -22
done
log "WIDE TEST DONE"
