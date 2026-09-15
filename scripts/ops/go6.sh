#!/bin/bash
if [ -f /workspace/marathon6.pid ] && ps -p "$(cat /workspace/marathon6.pid)" > /dev/null 2>&1; then echo "day 3 already running (pid $(cat /workspace/marathon6.pid))"; exit 0; fi
setsid nohup bash /workspace/studio_marathon6.sh > /workspace/marathon6.log 2>&1 < /dev/null &
echo $! > /workspace/marathon6.pid; sleep 2; echo "day 3 launched, pid $(cat /workspace/marathon6.pid)"; head -2 /workspace/marathon6.log
