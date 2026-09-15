#!/bin/bash
# Launcher for marathon shift 3 (character quality).
if [ -f /workspace/marathon3.pid ] && ps -p "$(cat /workspace/marathon3.pid)" > /dev/null 2>&1; then
  echo "shift 3 already running (pid $(cat /workspace/marathon3.pid))"
  exit 0
fi
setsid nohup bash /workspace/studio_marathon3.sh > /workspace/marathon3.log 2>&1 < /dev/null &
echo $! > /workspace/marathon3.pid
sleep 2
echo "shift 3 launched, pid $(cat /workspace/marathon3.pid)"
head -2 /workspace/marathon3.log 2>/dev/null
