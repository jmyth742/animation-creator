#!/bin/bash
# Fourteen hours, ordered so the cheap work that GATES everything runs first
# and a failure late costs less than a failure early.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== 1/6 · generate the plate library (FLUX, ~10 min) ==="
$PY scripts/gen_real_plates.py tir-na-nog-legend 2>&1 | grep -vE "Running|Queued" | tail -20

log "=== 2/6 · repair the wides that stayed tight, now with real plates ==="
$PY scripts/repair_collapsed_wides.py tir-na-nog-legend 2>&1 | tail -20

log "=== 3/6 · ep13 dialogue closes from in-place composite seeds ==="
$PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode 13 2>&1 | tail -20

log "=== 4/6 · ep14 dialogue closes from in-place composite seeds ==="
$PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode 14 2>&1 | tail -24

log "=== 5/6 · vertical b-roll and shorts refresh ==="
$PY scripts/render_vertical_broll.py tir-na-nog-legend 2>&1 | tail -8
$PY scripts/build_fix_shorts.py 2>&1 | tail -8

log "=== 6/6 · repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -5
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'

log "NIGHT2 DONE"
