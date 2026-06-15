# TestPyPI Upload Runbook

This runbook is for publishing a release artifact to TestPyPI first. It does not
cover production PyPI publication.

## Current Target

- Release tag: `v0.1.1`
- Release commit: `026d262787717152e8c029d0fa57b3f9d786aa48`
- Production PyPI upload: deferred until explicit final approval

## Credential Rules

- Do not paste API tokens into chat, shell history, GitHub issues, or files.
- Do not commit `.pypirc`.
- Prefer short-lived environment variables, 1Password injection, or PyPI trusted
  publishing.
- Use `TWINE_NON_INTERACTIVE=1` so upload fails closed when credentials are
  missing.

Expected credential environment for TestPyPI:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD="$TESTPYPI_API_TOKEN"
```

The token value itself should come from a secret store or local prompt, not from
a committed file.

## Build From The Release Tag

```bash
git clone https://github.com/cyakkunnlove/local-chat-memory.git /tmp/local-chat-memory-release
cd /tmp/local-chat-memory-release
git checkout v0.1.1

python3 -m venv /tmp/local-chat-memory-build-venv
/tmp/local-chat-memory-build-venv/bin/python -m pip install --upgrade pip build twine
/tmp/local-chat-memory-build-venv/bin/python -m build
/tmp/local-chat-memory-build-venv/bin/python -m twine check dist/*
python3 scripts/audit-dist.py dist/*
```

## Upload To TestPyPI

```bash
TWINE_NON_INTERACTIVE=1 \
  /tmp/local-chat-memory-build-venv/bin/python -m twine upload \
  --repository testpypi \
  dist/*
```

If authentication fails, stop and fix credentials. Do not retry by pasting a
token into the command line.

## Verify TestPyPI Install

Use a fresh virtual environment outside the source tree:

```bash
python3 -m venv /tmp/local-chat-memory-testpypi-venv
/tmp/local-chat-memory-testpypi-venv/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  local-chat-memory==0.1.1

LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-testpypi.db \
  /tmp/local-chat-memory-testpypi-venv/bin/local-chat-memory init
LOCAL_CHAT_MEMORY_DB=/tmp/local-chat-memory-testpypi.db \
  /tmp/local-chat-memory-testpypi-venv/bin/local-chat-memory status
/tmp/local-chat-memory-testpypi-venv/bin/python -m local_chat_memory doctor \
  --config /tmp/local-chat-memory-release/config.example.json
```

## Before Production PyPI

Before production PyPI:

- re-run the final privacy/security scan
- confirm the TestPyPI package installs cleanly
- confirm release notes match the uploaded version
- get explicit final approval for production PyPI publication
