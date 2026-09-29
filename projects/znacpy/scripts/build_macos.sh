#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP_BUNDLE="$PROJECT_ROOT/dist/bundle/macos-arm64/znacTime.app"
RUN_AFTER_BUILD=0
PACKAGE_ARGUMENTS=()

usage() {
    echo "Usage: $(basename "$0") [--release] [--run]" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)
            PACKAGE_ARGUMENTS=(--package)
            ;;
        --run)
            RUN_AFTER_BUILD=1
            ;;
        *)
            usage
            ;;
    esac
    shift
done

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    echo "Error: this script requires macOS on Apple silicon." >&2
    exit 1
fi

if [[ ! -x "$PROJECT_PYTHON" ]]; then
    echo "Error: project Python was not found at $PROJECT_PYTHON." >&2
    echo "Run uv sync --locked --group build first." >&2
    exit 1
fi

cd "$PROJECT_ROOT"
"$PROJECT_PYTHON" packaging/build.py \
    --target macos-arm64 \
    --mode unsigned \
    "${PACKAGE_ARGUMENTS[@]}"

if [[ "$RUN_AFTER_BUILD" -eq 0 ]]; then
    exit 0
fi

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "Error: built application was not found at $APP_BUNDLE." >&2
    exit 1
fi

open "$APP_BUNDLE"
