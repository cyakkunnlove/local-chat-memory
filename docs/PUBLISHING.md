# Publishing Checklist

This project is public on GitHub, but PyPI publishing should be a separate,
explicit release action.

The package is still alpha software. TestPyPI and PyPI installs should be used
at the user's own risk, with local backups and human review before any promoted
facts are copied into another system.

`v0.1.0` already exists as a GitHub tag. Any future TestPyPI/PyPI upload should
use a new release tag, `v0.1.1` or later, so package artifacts match the tagged
source exactly.

## Pre-Publish Checks

Run these checks from a clean checkout:

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py scripts/audit-dist.py
python3 -m local_chat_memory doctor --config config.example.json
python3 -m venv /tmp/local-chat-memory-build-venv
/tmp/local-chat-memory-build-venv/bin/python -m pip install --upgrade pip build twine
rm -rf dist build
find . -maxdepth 1 -name "*.egg-info" -exec rm -rf {} +
/tmp/local-chat-memory-build-venv/bin/python -m build
/tmp/local-chat-memory-build-venv/bin/python -m twine check dist/*
python3 scripts/audit-dist.py dist/*
python3 -m venv /tmp/local-chat-memory-wheel-smoke
/tmp/local-chat-memory-wheel-smoke/bin/python -m pip install dist/*.whl
LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-wheel-smoke.db \
  /tmp/local-chat-memory-wheel-smoke/bin/local-chat-memory init
LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-wheel-smoke.db \
  /tmp/local-chat-memory-wheel-smoke/bin/local-chat-memory status
```

Before uploading anywhere, confirm:

- the package name is still available and acceptable on TestPyPI/PyPI
- the built wheel can initialize and inspect a fresh SQLite database outside the source tree
- `dist/` contains only the current sdist and wheel
- the distribution audit passes
- no real chat exports, SQLite databases, private configs, or export backups are included
- the release notes match the version being published
- the README alpha safety notice still reflects the current risk level

## Upload Order

1. Upload to TestPyPI first.
2. Install from TestPyPI into a new virtual environment.
3. Run `local-chat-memory doctor --config config.example.json`.
4. Only then consider publishing the same version to PyPI.

Do not upload from a working tree that contains private local data. Do not
publish to PyPI without explicit release approval.

See [TESTPYPI.md](TESTPYPI.md) for the credential guardrails and copy-paste
TestPyPI upload/install verification commands.
