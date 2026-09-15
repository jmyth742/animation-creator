#!/bin/bash
# The QC-driven night: fix what the validated instruments actually found.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "episode_qc\.py" > /dev/null; do sleep 60; done
log "=== 1/5 · QC re-run with the location check ==="
$PY scripts/episode_qc.py tir-na-nog-legend --json /workspace/review/qc_series.json 2>&1 | tail -40

log "=== 2/5 · fix the wrong-place sea-crossing shots ==="
# correct plates now exist and the map is fixed; --force ignores stale takes
$PY scripts/upgrade_wides.py tir-na-nog-legend --episode 12 2>&1 | tail -10
$PY scripts/upgrade_wides.py tir-na-nog-legend --episode 10 2>&1 | tail -10

log "=== 3/5 · in-place composites for storm_cliffs and sunlight_path, then ep10 closes ==="
for loc in storm_cliffs sunlight_path; do
  for ch in oisin niamh; do
    $PY scripts/stage_composite.py tir-na-nog-legend $loc $ch --setups master,closer --stagings close,medium 2>&1 | tail -2
  done
done
$PY scripts/repair_dialogue_closes.py tir-na-nog-legend --episode 10 2>&1 | tail -12
$PY scripts/install_repaired_closes.py tir-na-nog-legend --episode 10 2>&1 | tail -8

log "=== 4/5 · lip-sync re-roll from the QC list ==="
$PY scripts/reroll_lipsync.py tir-na-nog-legend --from-qc /workspace/review/qc_series.json --takes 2 --limit 20 --min-episode 5 2>&1 | tail -40

log "=== 5/5 · re-stitch touched episodes + final verify ==="
for E in 10 12 13 14 15 16 17 5 6 7 8 9 11; do
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -4
done
$PY scripts/episode_qc.py tir-na-nog-legend --json /workspace/review/qc_after.json 2>&1 | tail -30
$PY scripts/build_shorts_pack.py 2>&1 | tail -3
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack
log "NIGHT4 DONE"
