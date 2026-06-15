# Public Release Checklist

## v0.1.0 Status

Release target: `v0.1.0`

- [x] Confirm no real chat exports are present.
- [x] Confirm no SQLite database is present.
- [x] Confirm no `config.local.json` is present.
- [x] Confirm no export backups or generated private reports are present.
- [x] Run a private-name scan over the repository.
- [x] Confirm no common secret/token patterns are present.
- [x] Confirm license is Apache-2.0.
- [x] Confirm privacy statement is present in `PRIVACY.md`.
- [x] Confirm security policy is present in `SECURITY.md`.
- [x] Confirm package metadata and CLI entrypoint work.
- [x] Confirm GitHub Actions pass.
- [x] Add changelog or release notes.
- [x] Add release audit summary.
- [x] Verify GitHub Actions on release-prep commit.
- [x] Verify a clean checkout from GitHub.
- [x] Create and push `v0.1.0` tag.
- [x] Create GitHub release.

Audit summary: `RELEASE_AUDIT_2026-06-15_v0.1.0.md`
Release URL: https://github.com/cyakkunnlove/local-chat-memory/releases/tag/v0.1.0

## Original Public Seed Checklist

Before publishing this repository:

- Confirm no real chat exports are present.
- Confirm no SQLite database is present.
- Confirm no `config.local.json` is present.
- Confirm no export backups or generated private reports are present.
- Run a private-name scan over the repository.
- Choose and add a license.
- Confirm package metadata and CLI entrypoint work.
- Create the GitHub repository.
- Enable GitHub Actions.
- Open initial issues for parser variants, packaging, and docs.

Suggested private-name scan:

```bash
rg -n "private-name-or-client-name" .
```

Verification:

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py
python3 line_history_poc.py doctor --config config.example.json
python3 -m local_chat_memory doctor --config config.example.json
```
