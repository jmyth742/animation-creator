#!/bin/bash
# Wait for V1 production (PID 1152166) to finish, then run V2

echo "Waiting for palestine-stories V1 production (PID 1152166) to finish..."

while kill -0 1152166 2>/dev/null; do
    sleep 30
done

echo "V1 finished at $(date). Starting V2 production..."

cd /workspace/text-to-video
python scripts/showrunner.py produce-all palestine-stories-v2 --quality final \
    > /workspace/produce_palestine_v2_director.log 2>&1

echo "V2 finished at $(date)"
