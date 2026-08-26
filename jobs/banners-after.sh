#!/usr/bin/env bash
set -u
cd /workspace/text-to-video
P=$(cat .jobs/pids/finishfilm.pid 2>/dev/null || echo "")
[ -n "$P" ] && while kill -0 "$P" 2>/dev/null; do sleep 30; done
echo "════ banners ════"; date '+%H:%M:%S'
/workspace/venv/bin/python /workspace/review/banner/retry.py
ls -la /workspace/review/banner/*.jpg
