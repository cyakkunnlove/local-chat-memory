# Security Policy

This project handles private chat exports. Treat every real export as sensitive.

## Supported Scope

The public project should contain only:

- parser and importer code
- SQLite schema and migrations
- synthetic fixtures
- redacted operational reports
- example configuration

The project does not need LINE credentials, LINE local database access, screenshots, or external AI API calls.

## Reporting Issues

If you find a security issue, open a private advisory or contact the maintainer privately. Do not include real chat logs in public issues.

## Data Handling Rules

Never commit:

- real `Downloads/[LINE]*.txt` exports
- SQLite databases containing message bodies
- `config.local.json`
- export backups
- raw operational logs with message bodies

When sharing diagnostics, prefer:

```bash
python3 line_history_poc.py health-report --format json
python3 line_history_poc.py export-pending --redact --output exports/pending-redacted.md
```

## Automation Safety

The macOS LINE UI helper is best-effort desktop automation. It should:

- verify focus before pasting search text
- verify the save dialog target name before saving
- stop on mismatched filenames
- avoid unattended full-account scraping
- keep raw message bodies local

If a safety check fails, fix the check or document the limitation rather than bypassing it.
