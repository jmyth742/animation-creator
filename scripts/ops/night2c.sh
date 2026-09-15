#!/bin/bash
# Third tranche: bring ep12/13/14's wides up to the generated-plate standard,
# which also replaces the two split panels with real two-shots.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while pgrep -f "night2b\.s[h]" > /dev/null; do sleep 120; done
log "night2b finished"

log "=== plates for the locations that had none ==="
$PY - <<'PYX' 2>&1 | tail -6
import sys, subprocess
sys.path.insert(0,'scripts')
import gen_real_plates as g
# sunlight_path and storm_cliffs were never given generated plates
extra = [
 ("gen__path_wide_oisin", f"Extreme wide shot. A narrow sunlit path winding "
  f"through open green country under a bright sky. Far away on the path, small "
  f"in the frame, {g.OISIN} walks away from camera, his whole body visible."),
 ("gen__path_twoshot", f"Wide two shot. A narrow sunlit path through open green "
  f"country. {g.OISIN} on the left and {g.NIAMH} on the right, a few paces apart "
  f"on the same path, both full-length and at the same scale, facing each other."),
]
g.PLATES.extend(extra)
sys.argv = ["x", "tir-na-nog-legend"]
g.main()
PYX

for E in 13 14 12; do
  log "=== upgrade ep$E wides to generated plates ==="
  $PY scripts/upgrade_wides.py tir-na-nog-legend --episode $E 2>&1 | tail -16
  log "=== re-stitch ep$E ==="
  $PY scripts/showrunner.py produce tir-na-nog-legend --episode $E \
      --quality final --upscale --resume 2>&1 | tail -10
done

log "=== final repackage ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -4
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'
log "NIGHT2C DONE"
