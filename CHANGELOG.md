# Changelog

## v0.1.2 - 2026-06-15

Installed CLI default data path fix.

### Fixed

- Use the current working directory for the default SQLite database path in installed CLI runs, matching the documented `./data/local-chat-memory.db` behavior.
- Keep schema loading tied to the package/source location so installed wheels can still initialize databases outside the source tree.

### Changed

- CI and TestPyPI publish smoke checks now install the built wheel and run `local-chat-memory init` without `LOCAL_CHAT_MEMORY_DB`, then assert that `./data/local-chat-memory.db` was created.

## v0.1.1 - 2026-06-15

Packaging and pre-publish safety release.

### Added

- Synthetic fixture and parser coverage for `YYYY-MM-DD HH:MM - sender: body` rows.
- Synthetic fixture and parser coverage for WhatsApp-style `M/D/YY, h:mm PM - sender: body` rows.
- AM/PM timestamp normalization for supported message formats.
- `docs/PUBLISHING.md` with a TestPyPI-first publishing checklist.
- Distribution audit script for checking built sdist/wheel contents before upload.
- CI smoke check that installs the built wheel into a fresh virtual environment.

### Fixed

- Include the SQLite schema in built wheels so installed CLI commands can initialize databases outside the source tree.

### Publishing

- TestPyPI and PyPI publishing remain deferred.
- Use at your own risk while the project is in alpha.
- Keep source exports and SQLite databases backed up.
- Review promoted facts before copying them into another system or sharing them with other people.

## v0.1.0 - 2026-06-15

Initial public release.

### Added

- Local SQLite importer for exported chat text files.
- LINE desktop text export parser with synthetic fixture coverage.
- Stable message fingerprinting for overlapping export deduplication.
- Chat, people, alias, participant, and sender-person linking tables.
- Local search, pending review, person context, alias candidate, wiki candidate, and health report commands.
- Config commands: `init-config`, `validate-config`, and `doctor`.
- Redacted pending export and promote review checklist generation.
- Reviewed promote workflow:
  - `apply-promote-review`
  - `promoted`
  - reviewed Markdown checklist input
  - TODO, decision, question, person note, and project note examples
- Optional cautious macOS LINE desktop export helper.
- Package metadata and local CLI entrypoint:
  - `local-chat-memory`
  - `python -m local_chat_memory`
- Privacy, security, contribution, configuration, and promote workflow documentation.
- GitHub Actions test workflow.

### Privacy And Security

- No real chat exports, SQLite databases, local configs, export backups, or generated private reports are included.
- Core importer does not use credentials, parse private app databases, take screenshots, or call external AI APIs.
- Redacted report modes are available for demos and support.
- Public fixtures are synthetic.

### Known Limits

- The first parser target is LINE desktop text exports; additional chat export variants are tracked in issue #2.
- The macOS LINE helper is optional desktop automation and should be treated as best-effort.
- No PyPI package is published yet; use a virtual environment and editable install from GitHub/source.
