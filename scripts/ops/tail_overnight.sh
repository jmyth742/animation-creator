#!/bin/bash
# Soaks up whatever is left of the night after ep13 and ep14.
# Ordered by value: repair the collapsed wides first, then shorts material.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "ep14_overnight\.sh" > /dev/null; do sleep 120; done
log "ep14 finished"

log "=== repair the 11 collapsed wide shots (ep05-ep11) ==="
$PY scripts/repair_collapsed_wides.py tir-na-nog-legend 2>&1 | tail -30

log "=== vertical b-roll from the new episodes ==="
$PY scripts/render_vertical_broll.py tir-na-nog-legend 2>&1 | tail -12

log "=== repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -5
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "TAIL DONE"
