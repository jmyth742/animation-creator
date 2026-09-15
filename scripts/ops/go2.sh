#!/bin/bash
# Launcher for marathon shift 2 (waits for shift 1 to finish by itself).
if [ -f /workspace/marathon2.pid ] && ps -p "$(cat /workspace/marathon2.pid)" > /dev/null 2>&1; then
  echo "shift 2 already running (pid $(cat /workspace/marathon2.pid))"
  exit 0
fi
setsid nohup bash /workspace/studio_marathon2.sh > /workspace/marathon2.log 2>&1 < /dev/null &
echo $! > /workspace/marathon2.pid
sleep 2
echo "shift 2 armed, pid $(cat /workspace/marathon2.pid) — waiting for shift 1 to finish"
