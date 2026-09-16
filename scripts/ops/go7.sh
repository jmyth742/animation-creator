#!/bin/bash
if [ -f /workspace/marathon7.pid ] && ps -p "$(cat /workspace/marathon7.pid)" > /dev/null 2>&1; then echo "day 4 already running (pid $(cat /workspace/marathon7.pid))"; exit 0; fi
setsid nohup bash /workspace/studio_marathon7.sh > /workspace/marathon7.log 2>&1 < /dev/null &
echo $! > /workspace/marathon7.pid; sleep 2; echo "day 4 launched, pid $(cat /workspace/marathon7.pid)"; head -2 /workspace/marathon7.log
