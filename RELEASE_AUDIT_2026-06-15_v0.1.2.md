# Release Audit: v0.1.2

Date: 2026-06-15

Release target: `v0.1.2`

## Scope

This patch release fixes the installed CLI default data path before production
PyPI publication.

Changes since `v0.1.1`:

- Use the current working directory for the default SQLite database path in
  installed CLI runs, matching the documented `./data/local-chat-memory.db`
  behavior.
- Keep schema loading tied to the package/source location so installed wheels
  can initialize databases outside the source tree.
- Add unit coverage for default DB path resolution and
  `LOCAL_CHAT_MEMORY_DB` override behavior.
- Update GitHub Actions and TestPyPI publish smoke checks to install the built
  wheel and run `local-chat-memory init` without `LOCAL_CHAT_MEMORY_DB`, then
  assert that `./data/local-chat-memory.db` was created.

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
tree without setting `LOCAL_CHAT_MEMORY_DB`:

```bash
python3 -m venv /tmp/local-chat-memory-wheel-smoke-0.1.2/venv
/tmp/local-chat-memory-wheel-smoke-0.1.2/venv/bin/python -m pip install dist/*.whl
cd /tmp/local-chat-memory-wheel-smoke-0.1.2
/tmp/local-chat-memory-wheel-smoke-0.1.2/venv/bin/local-chat-memory init
test -f /tmp/local-chat-memory-wheel-smoke-0.1.2/data/local-chat-memory.db
/tmp/local-chat-memory-wheel-smoke-0.1.2/venv/bin/local-chat-memory status
```

## Release Gate

- GitHub Release is allowed after all local checks and GitHub Actions pass.
- TestPyPI upload should run before production PyPI.
- PyPI upload requires explicit final approval.
