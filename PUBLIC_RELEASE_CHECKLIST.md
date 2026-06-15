# Public Release Checklist

Before publishing this repository:

- Confirm no real chat exports are present.
- Confirm no SQLite database is present.
- Confirm no `config.local.json` is present.
- Confirm no export backups or generated private reports are present.
- Run a private-name scan over the repository.
- Choose and add a license.
- Decide whether to rename `line_history_poc.py` to a package/CLI entrypoint.
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
python3 -m py_compile line_history_poc.py scripts/export-current-line-chat.py
python3 line_history_poc.py doctor --config config.example.json
```
