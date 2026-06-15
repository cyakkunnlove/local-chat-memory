# Changelog

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
