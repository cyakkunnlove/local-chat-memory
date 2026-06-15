# v0.1.0 Release Audit - 2026-06-15

Repository: https://github.com/cyakkunnlove/local-chat-memory

## Result

Ready for the first GitHub tag/release as `v0.1.0`.

## Scope

Included:

- source code
- SQLite schema
- synthetic fixtures
- unit tests
- documentation
- GitHub Actions workflow
- release checklist and audit notes

Excluded:

- real chat exports
- SQLite databases
- `config.local.json`
- export backups
- generated private reports
- local workspace metadata
- secrets or API keys

## Verification

Local verification:

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py
python3 line_history_poc.py doctor --config config.example.json
python3 -m local_chat_memory doctor --config config.example.json
```

Additional workflow smoke:

- temporary DB import
- `apply-promote-review --dry-run`
- `apply-promote-review`
- `promoted`

GitHub Actions:

- `Initial public release`: success
- `Package CLI and expand parser fixtures`: success
- `Update Actions to Node 24 compatible versions`: success
- `Add reviewed promote workflow`: success
- `Prepare v0.1.0 release notes`: success

Clean checkout verification:

- cloned `https://github.com/cyakkunnlove/local-chat-memory.git` into a temporary directory
- ran unit tests: 18 OK
- ran py_compile: OK
- ran `python3 -m local_chat_memory doctor --config config.example.json`: OK

Public-visible privacy/security scan:

- no private workspace paths found
- no original private project name found
- no real chat participant names from the private source project found
- no common secret/token patterns found
- no real DB/export/config artifacts tracked

## v0.1.0 Release Notes

Local Chat Memory is a local-first chat export importer for SQLite-backed AI memory workflows.

Highlights:

- import LINE desktop text exports into local SQLite
- deduplicate overlapping exports
- link people across direct and group chats
- classify noisy/system/attachment-like messages without deleting records
- search locally
- produce redacted health reports and review checklists
- apply reviewed promote checklists into local `promoted` events
- install a local CLI entrypoint with `local-chat-memory`

## Residual Risks

- Chat names and reviewed facts can still be identifying in a user's own local DB or generated reports.
- Users should review any diagnostics before sharing them publicly.
- The optional macOS LINE helper is desktop automation and can be fragile; core importer usage does not require it.
- This release is source/GitHub focused. PyPI publishing is intentionally deferred.
