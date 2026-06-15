# Promote Workflow

The promote workflow turns noisy chat history into reviewed local memory without publishing raw transcripts.

## 1. Export Candidates

Use redaction when preparing a demo or support artifact:

```bash
local-chat-memory export-promote-review \
  --redact \
  --limit 50 \
  --output exports/promote-review.md
```

The generated checklist contains candidate message IDs, reasons, and empty review fields.

## 2. Review Locally

Open the checklist and only check items after a human reviewer has written a safe distilled fact:

```markdown
- [x] message_id: 42
  - distilled_fact: TODO: Send the revised proposal to Client A by Friday.
  - promote_to: todos/client-a.md
```

Good `distilled_fact` examples:

- `TODO: Send the revised proposal to Client A by Friday.`
- `Decision: Use SQLite as the local source of truth for chat memory.`
- `Question: Client A asked whether group chat exports are supported.`
- `Person note: Client A prefers concise status updates before noon.`
- `Project note: Parser fixtures should stay synthetic and public-safe.`

`promote_to` is a local destination hint. It can be a wiki page, a task file, a project note, or any local path-like label.

## 3. Apply The Review

Preview first:

```bash
local-chat-memory apply-promote-review \
  --input exports/promote-review.md \
  --dry-run
```

Apply it:

```bash
local-chat-memory apply-promote-review \
  --input exports/promote-review.md
```

Checked items with both `distilled_fact` and `promote_to` are recorded as `promoted` message events. By default, those source messages are marked processed so they do not keep appearing as pending. Use `--keep-pending` if you want to record the promotion without changing pending status.

## 4. List Promoted Items

```bash
local-chat-memory promoted
local-chat-memory promoted --format json
```

The promoted list prints reviewed distilled facts only. It does not print raw message bodies.
