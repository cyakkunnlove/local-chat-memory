# Privacy

This project is designed for local-first chat history processing.

## Principles

- Raw message bodies stay on the user's machine.
- SQLite is the local source of truth.
- Public fixtures must be synthetic or sanitized.
- Wiki or knowledge-base writeback should contain distilled facts, not full transcripts.
- Redacted reports are preferred for debugging and support.

## What The Tool Stores

The local SQLite database can store:

- chat names
- sender display names
- message timestamps
- raw message bodies
- message fingerprints and hashes
- classification state
- AI processing state

Because message bodies and relationship metadata can be sensitive, do not publish the database.

## Safe Sharing

For public issues or maintenance reports, use:

```bash
python3 line_history_poc.py health-report
python3 line_history_poc.py export-pending --redact --output exports/pending-redacted.md
```

Review any output before sharing it publicly. Even chat names can be identifying.

## Out Of Scope

The public tool should not:

- parse private LINE app databases
- collect credentials
- upload raw chat logs to external AI APIs
- run unattended full-account desktop scraping
- publish raw transcripts to a wiki
