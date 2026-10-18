#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8501}"

if [[ -z "${PITCHROOM_ACCESS_TOKEN//[[:space:]]/}" ]]; then
    printf 'PITCHROOM_ACCESS_TOKEN must be configured for the public deployment.\n' >&2
    exit 1
fi

cd "$ROOT_DIR/backend"
exec "$PYTHON_BIN" -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
