#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    else
        PYTHON_BIN="python3"
    fi
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-${FRONTEND_PORT:-8501}}"

if [[ ! -x "$PYTHON_BIN" ]] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf 'Python executable not found: %s\n' "$PYTHON_BIN" >&2
    exit 1
fi

printf 'Starting Pitchroom AI at http://%s:%s\n' "$HOST" "$PORT"
printf 'The API and live voice interface share this origin. Press Ctrl+C to stop.\n'
cd "$ROOT_DIR/backend"
exec "$PYTHON_BIN" -m uvicorn app:app --host "$HOST" --port "$PORT" --reload
