# Configuration

The importer can run with one-off `import` commands, but repeated use is easier with a JSON config.

## Create A Config

```bash
python3 line_history_poc.py init-config --output config.local.json
```

Edit `config.local.json`, then validate it:

```bash
python3 line_history_poc.py validate-config --config config.local.json
python3 line_history_poc.py doctor --config config.local.json
```

## Fields

- `download_dir`: folder containing exported `[LINE]*.txt` files.
- `processed_dir`: optional folder to move processed exports into when using `--move-processed`.
- `chats`: list of chat import rules.
- `chat_name`: canonical local name for the chat.
- `chat_kind`: `personal`, `group`, or `official`.
- `filename_contains`: substring used to match export filenames.
- `participants`: known sender display names and aliases.
- `purpose`: local note explaining why the chat matters.
- `wiki_path`: optional local knowledge-base page path.

## Minimal Example

```json
{
  "download_dir": "~/Downloads",
  "processed_dir": null,
  "chats": [
    {
      "chat_name": "Client A",
      "chat_kind": "personal",
      "filename_contains": "[LINE]Client A",
      "participants": [
        { "display_name": "Client A", "aliases": ["Client A"] },
        { "display_name": "Me", "aliases": ["me"] }
      ],
      "purpose": "Client A project context",
      "wiki_path": null
    }
  ]
}
```

## Import

```bash
python3 line_history_poc.py scan-downloads --config config.local.json
```

For discovery-first local use:

```bash
python3 line_history_poc.py scan-downloads --config config.local.json --auto-discover
```

Review the discovered chats before relying on `chat_kind`; group detection is heuristic.
