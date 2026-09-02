#!/bin/bash
# idle_hibernate.sh — stop this pod when the studio has been idle long enough.
#
# OPT-IN: only runs while scripts/workbench_data/hibernate_enabled exists
# (toggled from the SHOWRUNNER console, admin only). Kill by pidfile only —
# never pkill patterns (see ensure_workbench.sh for why).
#
# Idle means ALL of, continuously for IDLE_MIN minutes:
#   - render queue empty (workbench_data/render_queue.txt)
#   - no showrunner/forge/reroll python jobs running
#   - ComfyUI queue empty
#   - GPU utilisation < 15%
#
# Firing requires a WORKING RunPod API key (runpodctl config --apiKey ...).
# Without one the script logs "would stop now" and does nothing — honest,
# not silent. Restart later from the RunPod app; ensure_all.sh reboots
# the studio.
set -u
cd /workspace/text-to-video
WB=scripts/workbench_data
IDLE_MIN=${IDLE_MIN:-30}
LOG=$WB/hibernate.log
echo $$ > $WB/hibernate.pid
idle_since=""

say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
say "hibernate watcher up (threshold ${IDLE_MIN}m)"

while true; do
  sleep 60
  [ -f $WB/hibernate_enabled ] || { idle_since=""; continue; }

  busy=""
  # 1. queue
  [ -s $WB/render_queue.txt ] && busy="queue"
  # 2. jobs (match on script names in argv of *other* processes)
  if [ -z "$busy" ]; then
    for pat in showrunner.py forge_assets.py reroll_shot.py reroll_lipsync.py; do
      pids=$(pgrep -f "python.*scripts/$pat" | grep -v "^$$\$" || true)
      [ -n "$pids" ] && { busy="job:$pat"; break; }
    done
  fi
  # 3. comfy queue
  if [ -z "$busy" ]; then
    q=$(curl -s --max-time 5 http://127.0.0.1:8188/queue | /workspace/venv/bin/python -c \
      "import sys,json;d=json.load(sys.stdin);print(len(d['queue_running'])+len(d['queue_pending']))" 2>/dev/null || echo 0)
    [ "$q" != "0" ] && busy="comfy:$q"
  fi
  # 4. gpu
  if [ -z "$busy" ]; then
    util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null || echo 0)
    [ "${util:-0}" -ge 15 ] && busy="gpu:${util}%"
  fi

  if [ -n "$busy" ]; then
    [ -n "$idle_since" ] && say "busy again ($busy) — idle clock reset"
    idle_since=""
    continue
  fi

  now=$(date +%s)
  [ -z "$idle_since" ] && { idle_since=$now; say "idle — clock started"; }
  mins=$(( (now - idle_since) / 60 ))
  if [ "$mins" -ge "$IDLE_MIN" ]; then
    if /workspace/runpodctl pod list >/dev/null 2>&1; then
      say "idle ${mins}m — STOPPING POD ${RUNPOD_POD_ID:-?}"
      /workspace/runpodctl stop pod "${RUNPOD_POD_ID}" >> "$LOG" 2>&1
      idle_since=""
    else
      say "idle ${mins}m — would stop pod, but RunPod API key is not authorised. Run: runpodctl config --apiKey <key>"
      idle_since=$now   # don't spam every minute
    fi
  fi
done
