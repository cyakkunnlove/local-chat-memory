# Local Chat Memory

Local Chat Memory imports exported chat text files into SQLite so private conversation history can support local AI and knowledge workflows without uploading raw transcripts.

The first supported format is LINE desktop text exports, but the core model is generic:

- import text exports into a local SQLite database
- deduplicate overlapping exports with stable fingerprints
- link people across direct and group chats
- classify noisy/system/attachment-like messages without deleting records
- search locally when context is needed
- produce redacted health reports and review checklists

No credentials, private app database parsing, screenshots, or external AI API calls are required.

## Quick Start

```bash
python3 line_history_poc.py init
python3 line_history_poc.py import --chat "Sample Chat" --file fixtures/sample_line_export_ja.txt
python3 line_history_poc.py health-report
```

Or install the local CLI entrypoint in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
local-chat-memory init
local-chat-memory import --chat "Sample Chat" --file fixtures/sample_line_export_ja.txt
local-chat-memory health-report
```

Default DB path:

```text
./data/local-chat-memory.db
```

Override it with:

```bash
LOCAL_CHAT_MEMORY_DB=/path/to/chat-memory.db python3 line_history_poc.py status
```

## Setup

```bash
python3 line_history_poc.py init-config --output config.local.json
python3 line_history_poc.py validate-config --config config.local.json
python3 line_history_poc.py doctor --config config.local.json
```

Then import downloaded exports:

```bash
python3 line_history_poc.py scan-downloads --config config.local.json
```

Discovery-first local use:

```bash
python3 line_history_poc.py scan-downloads --config config.local.json --auto-discover
```

## Common Commands

```bash
local-chat-memory status
local-chat-memory search "invoice" --limit 20
local-chat-memory people
local-chat-memory person-context "Client A"
local-chat-memory alias-candidates
local-chat-memory wiki-candidates --min-messages 20
local-chat-memory promote-candidates --redact
local-chat-memory export-promote-review --redact --output exports/promote-review.md
local-chat-memory apply-promote-review --input exports/promote-review.md --dry-run
local-chat-memory promoted
```

The original script form remains supported:

```bash
python3 line_history_poc.py status
python3 line_history_poc.py search "invoice" --limit 20
python3 line_history_poc.py people
python3 line_history_poc.py person-context "Client A"
python3 line_history_poc.py alias-candidates
python3 line_history_poc.py wiki-candidates --min-messages 20
python3 line_history_poc.py promote-candidates --redact
python3 line_history_poc.py export-promote-review --redact --output exports/promote-review.md
python3 line_history_poc.py apply-promote-review --input exports/promote-review.md --dry-run
python3 line_history_poc.py promoted
```

## Promote Reviewed Facts

Candidate extraction is local and deterministic. The safer workflow is:

```bash
local-chat-memory export-promote-review --redact --output exports/promote-review.md
# Edit the checklist locally: check reviewed items and fill distilled_fact/promote_to.
local-chat-memory apply-promote-review --input exports/promote-review.md --dry-run
local-chat-memory apply-promote-review --input exports/promote-review.md
local-chat-memory promoted
```

See `docs/PROMOTE_WORKFLOW.md` and `examples/promote-review-reviewed.md` for TODO, decision, question, person note, and project note examples.

## Desktop Export Helper

The macOS LINE helper is optional and intentionally cautious:

```bash
scripts/export-current-line-chat.py --scan-after --auto-discover
```

For DB-backed staged queues:

```bash
scripts/export-current-line-chat.py \
  --from-db \
  --chat-kind personal \
  --skip-success-within-hours 20 \
  --limit 3 \
  --open-first-result \
  --timeout 90
```

It verifies search focus before pasting, verifies save names before saving, stops on mismatched filenames, and records export attempts.

## Privacy

Raw message bodies stay local. Do not publish:

- real chat exports
- SQLite databases
- `config.local.json`
- export backups
- logs or screenshots containing message bodies

Use redacted reports for support:

```bash
python3 line_history_poc.py health-report --format json
python3 line_history_poc.py export-pending --redact --output exports/pending-redacted.md
python3 line_history_poc.py export-promote-review --redact --output exports/promote-review.md
```

## Development

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py
python3 -m local_chat_memory doctor --config config.example.json
```

## Release Notes

- `CHANGELOG.md`
- `RELEASE_AUDIT_2026-06-15_v0.1.0.md`
