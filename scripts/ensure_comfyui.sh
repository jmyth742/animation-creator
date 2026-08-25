#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ensure_comfyui.sh — make sure ComfyUI is up, start it detached if not.
#
# Idempotent and safe to call before every pipeline step. ComfyUI runs
# as its own setsid'd daemon so it is NOT a child of your SSH session:
# if you get disconnected mid-clip, ComfyUI keeps rendering and writes
# the mp4, and showrunner's --resume picks it up on restart.
#
#   bash scripts/ensure_comfyui.sh          # start / verify
#   bash scripts/ensure_comfyui.sh restart  # force restart
#   bash scripts/ensure_comfyui.sh stop
#   bash scripts/ensure_comfyui.sh status
# ─────────────────────────────────────────────────────────────────────
set -uo pipefail

PROJECT="${PROJECT:-/workspace/text-to-video}"
VENV_PY="${VENV_PY:-/workspace/venv/bin/python}"
PORT="${COMFY_PORT:-8188}"
STATE="$PROJECT/.jobs"
LOG="$STATE/comfyui.log"
PIDFILE="$STATE/comfyui.pid"
BOOT_TIMEOUT="${COMFY_BOOT_TIMEOUT:-420}"

mkdir -p "$STATE"

say() { echo "[comfyui] $*"; }

is_up() {
    curl -sf -m 5 "http://127.0.0.1:$PORT/system_stats" >/dev/null 2>&1
}

pid_alive() {
    [ -f "$PIDFILE" ] || return 1
    local p; p=$(cat "$PIDFILE" 2>/dev/null)
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

stop_comfy() {
    if pid_alive; then
        local p; p=$(cat "$PIDFILE")
        say "stopping pid $p"
        kill "$p" 2>/dev/null
        for _ in $(seq 1 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
        kill -0 "$p" 2>/dev/null && { say "force kill"; kill -9 "$p" 2>/dev/null; }
    fi
    pkill -f "ComfyUI/main.py.*--port $PORT" 2>/dev/null
    rm -f "$PIDFILE"
}

start_comfy() {
    say "starting on :$PORT (log: $LOG)"
    # rotate log so a boot failure is easy to spot
    [ -f "$LOG" ] && mv "$LOG" "$LOG.prev"
    cd "$PROJECT/ComfyUI" || { say "ERROR: $PROJECT/ComfyUI not found"; return 1; }

    local py="$VENV_PY"
    [ -x "$py" ] || py="$(command -v python3)"

    # setsid + nohup + </dev/null → fully detached from this shell and from SSH
    setsid nohup "$py" main.py --listen 0.0.0.0 --port "$PORT" \
        >>"$LOG" 2>&1 </dev/null &
    echo $! > "$PIDFILE"
    say "pid $(cat "$PIDFILE"), waiting for API (up to ${BOOT_TIMEOUT}s)..."

    local waited=0
    while [ "$waited" -lt "$BOOT_TIMEOUT" ]; do
        if is_up; then say "ready after ${waited}s"; return 0; fi
        if ! pid_alive; then
            say "ERROR: process died during boot — last 20 log lines:"
            tail -20 "$LOG" | sed 's/^/    /'
            return 1
        fi
        sleep 5; waited=$((waited + 5))
    done
    say "ERROR: not ready after ${BOOT_TIMEOUT}s — last 20 log lines:"
    tail -20 "$LOG" | sed 's/^/    /'
    return 1
}

case "${1:-ensure}" in
    ensure)
        if is_up; then say "already up on :$PORT"; exit 0; fi
        # not answering — clear anything stale, then boot
        stop_comfy
        start_comfy
        ;;
    restart) stop_comfy; start_comfy ;;
    stop)    stop_comfy; say "stopped" ;;
    status)
        if is_up; then
            say "UP on :$PORT (pid $(cat "$PIDFILE" 2>/dev/null || echo '?'))"
            curl -s -m 5 "http://127.0.0.1:$PORT/queue" 2>/dev/null | \
              python3 -c "import sys,json;q=json.load(sys.stdin);print(f\"[comfyui] queue: {len(q.get('queue_running',[]))} running, {len(q.get('queue_pending',[]))} pending\")" 2>/dev/null
        else
            say "DOWN"; exit 1
        fi
        ;;
    *) echo "usage: ensure_comfyui.sh [ensure|restart|stop|status]"; exit 2 ;;
esac
