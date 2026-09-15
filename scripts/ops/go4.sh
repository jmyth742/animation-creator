#!/bin/bash
if [ -f /workspace/marathon4.pid ] && ps -p "$(cat /workspace/marathon4.pid)" > /dev/null 2>&1; then
  echo "day 1 already running (pid $(cat /workspace/marathon4.pid))"
  exit 0
fi
setsid nohup bash /workspace/studio_marathon4.sh > /workspace/marathon4.log 2>&1 < /dev/null &
echo $! > /workspace/marathon4.pid
sleep 2
echo "day 1 launched, pid $(cat /workspace/marathon4.pid)"
head -2 /workspace/marathon4.log 2>/dev/null
