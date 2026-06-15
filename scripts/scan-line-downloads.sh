#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"

CONFIG="$PROJECT_DIR/config.local.json"
if [ ! -f "$CONFIG" ]; then
  CONFIG="$PROJECT_DIR/config.example.json"
fi

exec "${PYTHON:-python3}" "$PROJECT_DIR/line_history_poc.py" \
  scan-downloads \
  --config "$CONFIG" \
  --auto-discover
