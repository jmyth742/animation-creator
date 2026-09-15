#!/bin/bash
# The night is over-committed (~25h queued, ~12h night). Everything installs
# incrementally as it renders, so the only thing that must NOT be squeezed
# out is the finale: re-stitch all episodes + the after-QC report.
#
# At 04:15, if night4 is still in the lip re-roll, kill just the re-roller.
# Each finished shot is already installed, only the in-flight take is lost,
# and night4.sh then falls through to stage 5 on its own.
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while true; do
  H=$(date +%H); M=$(date +%M)
  [ "$H" = "04" ] && [ "$M" -ge 15 ] && break
  [ "$H" = "05" ] && break
  sleep 300
done
if pgrep -f "reroll_lipsync\.p[y]" > /dev/null; then
  log "04:15 — re-roll still running; cutting it so the re-stitches happen"
  PIDS=$(pgrep -f "reroll_lipsync\.p[y]")
  kill $PIDS 2>/dev/null; sleep 10
  for p in $PIDS; do kill -9 $p 2>/dev/null; done
  log "re-roller stopped; night4 proceeds to stage 5"
else
  log "04:15 — re-roll already finished, nothing to do"
fi
