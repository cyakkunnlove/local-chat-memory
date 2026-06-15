# Release Audit: v0.1.1

Date: 2026-06-15

Release target: `v0.1.1`

## Scope

This release prepares the project for safer package publication without uploading
to TestPyPI or PyPI.

Changes since `v0.1.0`:

- Added synthetic parser coverage for dash-separated chat rows.
- Added synthetic parser coverage for WhatsApp-style AM/PM rows.
- Added AM/PM timestamp normalization.
- Added a TestPyPI-first publishing checklist.
- Added a distribution audit script for sdist/wheel contents.
- Added a built-wheel fresh virtualenv install smoke check in CI.
- Fixed installed-wheel schema packaging by including `local_chat_memory/schema.sql`.

## Privacy Boundary

The release must not include:

- real chat exports
- SQLite databases
- `config.local.json`
- export backups
- generated private reports
- private local filesystem paths
- credentials or API tokens

The public repository contains only synthetic fixtures and public documentation.

## Verification

Run before tagging:

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py scripts/audit-dist.py
python3 -m local_chat_memory doctor --config config.example.json
python3 -m build
python3 -m twine check dist/*
python3 scripts/audit-dist.py dist/*
```

Also verify the built wheel in a fresh virtual environment outside the source
tree:

```bash
LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-wheel-smoke.db local-chat-memory init
LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-wheel-smoke.db local-chat-memory status
python -m local_chat_memory doctor --config /path/to/config.example.json
```

## Release Gate

- GitHub Release is allowed after all local checks and GitHub Actions pass.
- TestPyPI upload is not part of this release issue.
- PyPI upload requires explicit final approval.
