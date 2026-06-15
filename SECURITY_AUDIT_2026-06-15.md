# Security And Privacy Audit - 2026-06-15

## Summary

Result: ready for initial public repository creation after excluding local workspace metadata.

The repository candidate contains synthetic fixtures, source code, docs, tests, and relative helper scripts. It does not contain real chat exports, private SQLite databases, local config, export backups, API keys, or hard-coded personal workspace paths in public-visible files.

## Checks

- Secret pattern scan: no matches for common API keys, GitHub tokens, private keys, or OAuth token names.
- Private keyword scan: no matches in public-visible files for known private workspace names or original project names.
- Data file scan: no real DB, local config, backup directory, or generated private export artifacts.
- Wrapper scripts: use relative paths rather than a personal absolute path.
- Desktop automation: uses `subprocess.run([...])` without `shell=True`; target text is passed through clipboard/AppleScript quoting and guarded by focus/save-name checks.
- Network behavior: no outbound network/API calls in the core importer.
- External AI behavior: no external AI API calls.
- Privacy docs: `PRIVACY.md`, `SECURITY.md`, and `.gitignore` document non-publishable artifacts.

## Residual Risks

- The optional macOS LINE UI helper controls the local desktop and is inherently fragile. It is documented as optional and guarded by focus checks, filename checks, and staged batch limits.
- Chat names can still be identifying in user-generated configs and reports. Users should review output before posting diagnostics publicly.
- The public repository should not include `.taskconfig.md`; it is ignored in `.gitignore` as local workspace metadata.

## Verification Commands

```bash
python3 -m unittest discover tests
python3 -m py_compile line_history_poc.py local_chat_memory/*.py scripts/export-current-line-chat.py
python3 line_history_poc.py doctor --config config.example.json
python3 -m local_chat_memory doctor --config config.example.json
rg --hidden -n "private-name-or-client-name|private-workspace-path|old-project-name" .
```

## Post-Public Packaging Pass

After adding `pyproject.toml`, the `local-chat-memory` console entrypoint, and additional synthetic fixtures, the privacy scan was rerun against public-visible files. No private workspace path, original private project name, real chat name, secret pattern, or real DB/export artifact was found. The only generated packaging metadata is ignored via `*.egg-info/`.

## Reviewed Promote Workflow Pass

After adding `apply-promote-review`, `promoted`, promote workflow docs, and synthetic examples, the privacy scan was rerun against public-visible files. The promoted output lists human-reviewed `distilled_fact` values and local `promote_to` hints, not raw message bodies. Redacted checklist mode remains available for demos and support.
