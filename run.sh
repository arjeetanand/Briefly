#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-4002}"

if [[ ! "$PORT" =~ ^[0-9]{1,5}$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
    printf 'PORT must be an integer between 1 and 65535: %s\n' "$PORT" >&2
    exit 2
fi
if ! command -v lsof >/dev/null 2>&1; then
    printf 'lsof is required to safely check port ownership.\n' >&2
    exit 1
fi

RUN_DIR="$ROOT_DIR/.briefly-voice"
PID_FILE="$RUN_DIR/$PORT.pid"
LOG_FILE="$RUN_DIR/$PORT.log"
umask 077
mkdir -p "$RUN_DIR"

is_owned_process() {
    local pid="$1" process_command cwd process_group
    process_command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    process_group="$(ps -p "$pid" -o pgid= 2>/dev/null | tr -d '[:space:]')"
    [[ "$process_group" == "$pid" && "$cwd" == "$ROOT_DIR/backend" && \
        "$process_command" == *"uvicorn app:app"* && "$process_command" == *"--port $PORT"* ]]
}

if [[ -f "$PID_FILE" ]]; then
    read -r old_pid < "$PID_FILE" || old_pid=""
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
        if ! is_owned_process "$old_pid"; then
            printf 'PID %s does not match this project and port; refusing to stop it.\n' "$old_pid" >&2
            exit 1
        fi
        kill -TERM -- "-$old_pid"
        stopped=0
        for _ in {1..40}; do
            if ! kill -0 -- "-$old_pid" 2>/dev/null; then
                stopped=1
                break
            fi
            sleep 0.25
        done
        if (( ! stopped )); then
            printf 'Project process group %s did not stop gracefully; leaving it running.\n' "$old_pid" >&2
            exit 1
        fi
    fi
    rm -f "$PID_FILE"
fi

listener="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
if [[ -n "$listener" ]]; then
    printf 'Port %s is already used by PID %s; refusing to stop an unowned process.\n' "$PORT" "$listener" >&2
    exit 1
fi

PORT="$PORT" HOST="$HOST" nohup python3 -c \
    'import os, sys; os.getpgid(0) == os.getpid() or os.setsid(); os.execvp("bash", ["bash", sys.argv[1]])' \
    "$ROOT_DIR/run-dev.sh" >>"$LOG_FILE" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"

for _ in {1..60}; do
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$PID_FILE"
        printf 'The server exited during startup. Recent log output:\n' >&2
        tail -n 30 "$LOG_FILE" >&2 || true
        exit 1
    fi
    listener="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
    if [[ -n "$listener" ]] && is_owned_process "$pid"; then
        printf 'Briefly Voice running at http://%s:%s (pid %s)\n' "$HOST" "$PORT" "$pid"
        exit 0
    fi
    sleep 0.5
done

if is_owned_process "$pid"; then
    kill -TERM -- "-$pid"
fi
rm -f "$PID_FILE"
printf 'The server did not become ready on port %s. Recent log output:\n' "$PORT" >&2
tail -n 30 "$LOG_FILE" >&2 || true
exit 1
