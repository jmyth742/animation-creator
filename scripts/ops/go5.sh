#!/bin/bash
if [ -f /workspace/marathon5.pid ] && ps -p "$(cat /workspace/marathon5.pid)" > /dev/null 2>&1; then
  echo "day 2 already running (pid $(cat /workspace/marathon5.pid))"; exit 0
fi
setsid nohup bash /workspace/studio_marathon5.sh > /workspace/marathon5.log 2>&1 < /dev/null &
echo $! > /workspace/marathon5.pid
sleep 2; echo "day 2 launched, pid $(cat /workspace/marathon5.pid)"; head -2 /workspace/marathon5.log
