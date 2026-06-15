# Contributing

Thanks for helping improve this local-first LINE export importer.

## Development

Use Python 3. No external runtime dependencies are required for the core importer.

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py scripts/export-current-line-chat.py
```

## Fixtures

Only commit synthetic or sanitized export samples.

Do not commit:

- real LINE exports
- real SQLite databases
- private config files
- screenshots with chat content
- logs containing message bodies

When adding parser coverage, preserve the date/time/sender separators and replace all private names and message text.

## Pull Requests

Good PRs include:

- a focused description of the format or workflow being improved
- synthetic fixture updates when parser behavior changes
- tests for migrations, parsing, dedupe, and redaction
- no raw private message content

The project favors local-first behavior and explicit safety checks over silent automation.
