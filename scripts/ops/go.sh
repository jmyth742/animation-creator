#!/bin/bash
# One-shot launcher: daemonizes the studio marathon and returns immediately.
if [ -f /workspace/marathon.pid ] && ps -p "$(cat /workspace/marathon.pid)" > /dev/null 2>&1; then
  echo "marathon already running (pid $(cat /workspace/marathon.pid))"
  exit 0
fi
setsid nohup bash /workspace/studio_marathon.sh > /workspace/marathon.log 2>&1 < /dev/null &
echo $! > /workspace/marathon.pid
sleep 2
echo "marathon launched, pid $(cat /workspace/marathon.pid)"
head -2 /workspace/marathon.log 2>/dev/null
