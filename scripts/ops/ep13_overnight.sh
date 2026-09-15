#!/bin/bash
# ep13 "The Ground Between Them" — the first episode authored to the grammar.
#
# --no-grade is deliberate, not a preference change: on ep12 the grade timed
# out at 180s mid-write (it runs AFTER the 4x upscale, so on 16x the pixels),
# leaving a file with no moov atom that subtitle burn-in then propagated into
# ep12_final.mp4 while the job reported success. Skipping it protects the
# render; the ordering fix is a pipeline change awaiting a decision.
cd /workspace/text-to-video
PY=/workspace/venv/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "=== gates ==="
$PY scripts/selftest.py > /tmp/e13_self.log 2>&1 || { log "SELFTEST FAILED"; tail -20 /tmp/e13_self.log; exit 1; }
$PY scripts/preflight.py tir-na-nog-legend --episode 13 > /tmp/e13_pre.log 2>&1 || { log "PREFLIGHT FAILED"; tail -25 /tmp/e13_pre.log; exit 1; }
log "gates passed"

log "=== ep13 The Ground Between Them (13 shots) ==="
$PY scripts/showrunner.py produce tir-na-nog-legend --episode 13 \
    --quality final --upscale --no-grade 2>&1 | tail -70

log "=== verify ==="
$PY scripts/verify_render.py tir-na-nog-legend --episode 13 2>&1 | tail -22

log "=== repackage the shorts pack ==="
$PY scripts/build_shorts_pack.py 2>&1 | tail -6
cd /workspace && rm -f shorts_pack.tar.gz && tar czf shorts_pack.tar.gz shorts_pack \
  && ls -l shorts_pack.tar.gz | awk '{printf "  shorts_pack.tar.gz %.0f MB\n",$5/1048576}'

log "EP13 DONE"
