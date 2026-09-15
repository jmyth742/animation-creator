#!/bin/bash
# The last measured defect class: 27 lip-sync shots, worst first. Installs
# are incremental, so any interruption point is an optimal one.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "master_audi[o]" > /dev/null; do sleep 60; done
log "=== 1/4 · lip re-roll: all 27, worst first, 2 takes ==="
$PY scripts/reroll_lipsync.py tir-na-nog-legend \
    --from-qc /workspace/review/qc_final.json --takes 2 --min-episode 5 2>&1 | tail -50

log "=== 2/4 · re-stitch touched episodes ==="
TOUCHED=$($PY - <<'PYX'
import json
try:
    d=json.load(open('/workspace/review/lipsync_reroll.json'))
    print(' '.join(sorted({r['shot'][2:4].lstrip('0') for r in d if r['installed']})))
except Exception: print('')
PYX
)
log "touched: $TOUCHED"
for E in $TOUCHED; do
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -4
done

log "=== 3/4 · re-master touched (re-stitch rebuilds the final, losing loudness) ==="
for E in $TOUCHED; do
  $PY scripts/master_audio.py tir-na-nog-legend --episode $E 2>&1 | tail -2
done

log "=== 4/4 · QC against the frozen ruler ==="
$PY scripts/episode_qc.py tir-na-nog-legend --json /workspace/review/qc_day5.json 2>&1 | tail -20
$PY scripts/build_shorts_pack.py 2>&1 | tail -3
rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack
log "DAY5 DONE"
