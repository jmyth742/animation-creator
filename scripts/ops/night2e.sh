#!/bin/bash
# Last tranche: install the verified repaired closes and re-stitch, so the
# fix reaches the episodes instead of sitting beside them.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2d\.s[h]" > /dev/null; do sleep 180; done
log "night2d finished"

# ep15 is in this list because it lost its audio the same way ep13 did: its
# camera pass re-upscaled through the ESRGAN path before that path carried
# sound. ep14 was re-stitched after the fix and already has both streams, but
# re-running it is harmless and picks up its repaired closes.
for E in 13 15 14; do
  log "=== install repaired closes into ep$E ==="
  $PY scripts/install_repaired_closes.py tir-na-nog-legend --episode $E 2>&1 | tail -12
  log "=== re-stitch ep$E with repaired closes + upgraded wides ==="
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -10
  $PY scripts/shot_inspector.py tir-na-nog-legend --episode $E --measure 2>&1 | tail -2
done

log "=== final repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -4
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "NIGHT2E DONE"
