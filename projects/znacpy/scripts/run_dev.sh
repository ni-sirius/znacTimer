#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [[ ! -x "$PROJECT_PYTHON" ]]; then
    echo "Error: project Python was not found at $PROJECT_PYTHON." >&2
    echo "Run uv sync --locked --group build first." >&2
    exit 1
fi

cd "$PROJECT_ROOT"
exec "$PROJECT_PYTHON" -m znactime "$@"
