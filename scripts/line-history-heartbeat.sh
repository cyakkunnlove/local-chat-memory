#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CONFIG="$PROJECT_DIR/config.local.json"
STATE="${LOCAL_CHAT_MEMORY_STATE:-$PROJECT_DIR/var/local-chat-memory-heartbeat-state.json}"
TMP_DIR="${TMPDIR:-$PROJECT_DIR/var/tmp}"

if [ ! -f "$CONFIG" ]; then
  CONFIG="$PROJECT_DIR/config.example.json"
fi

mkdir -p "$(dirname "$STATE")" "$TMP_DIR"

SCAN_JSON="$TMP_DIR/line-history-scan.json"
ALIASES_JSON="$TMP_DIR/line-history-aliases.json"
WIKI_JSON="$TMP_DIR/line-history-wiki-candidates.json"

"${PYTHON:-python3}" "$PROJECT_DIR/line_history_poc.py" scan-downloads --config "$CONFIG" --auto-discover > "$SCAN_JSON"
"${PYTHON:-python3}" "$PROJECT_DIR/line_history_poc.py" alias-candidates --format json > "$ALIASES_JSON"
"${PYTHON:-python3}" "$PROJECT_DIR/line_history_poc.py" wiki-candidates --min-messages 20 --format json > "$WIKI_JSON"

"${PYTHON:-python3}" - "$SCAN_JSON" "$ALIASES_JSON" "$WIKI_JSON" "$STATE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

scan_path, aliases_path, wiki_path, state_path = map(Path, sys.argv[1:])
scan = json.loads(scan_path.read_text(encoding="utf-8"))
aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
wiki = json.loads(wiki_path.read_text(encoding="utf-8"))

inserted = sum(int(item.get("inserted") or 0) for item in scan)
parsed = sum(int(item.get("parsed") or 0) for item in scan)
new_chats = sorted({item.get("chat") for item in scan if int(item.get("inserted") or 0) > 0})
alias_count = len(aliases)
unlinked = [
    item for item in wiki
    if not item.get("wiki_path") and int(item.get("sent_message_count") or 0) >= 20
]

signature_payload = {
    "new_chats": new_chats,
    "alias_keys": [item.get("normalized") for item in aliases],
    "unlinked": [(item.get("display_name"), item.get("sent_message_count")) for item in unlinked[:10]],
}
signature = hashlib.sha256(json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
previous = {}
if state_path.exists():
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        previous = {}

state_path.write_text(
    json.dumps({"signature": signature, "last_scan_count": len(scan), "last_inserted": inserted}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

if inserted == 0 and alias_count == 0 and previous.get("signature") == signature:
    sys.exit(0)

lines = []
if inserted:
    lines.append(f"Local chat memory: imported {inserted} new messages into SQLite (parsed {parsed}).")
    if new_chats:
        lines.append("Chats with new messages: " + ", ".join(new_chats))
if alias_count:
    lines.append(f"Local chat memory: {alias_count} possible alias groups need review.")
if unlinked and previous.get("signature") != signature:
    top = ", ".join(f"{item['display_name']}({item['sent_message_count']})" for item in unlinked[:5])
    lines.append(f"Local chat memory: unlinked promotion candidates: {top}")

if lines:
    print("\n".join(lines))
PY
