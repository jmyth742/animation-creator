#!/bin/bash
# Keep the workbench alive on :8888. Kills ONLY the pid it launched --
# pkill -f killed an operator shell whose command line merely mentioned
# the filename (git add scripts/workbench.py was enough to die for).
cd /workspace/text-to-video
PIDFILE=.jobs/workbench.pid
while true; do
  if ! curl -s -m 4 http://127.0.0.1:8888/health >/dev/null 2>&1; then
    if [ -f "$PIDFILE" ]; then
      OLD=$(cat "$PIDFILE")
      kill "$OLD" 2>/dev/null; sleep 2; kill -9 "$OLD" 2>/dev/null
    fi
    setsid nohup /workspace/venv/bin/python scripts/workbench.py \
      >> .jobs/workbench.log 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
  fi
  sleep 30
done
