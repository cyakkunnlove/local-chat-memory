# Local Chat Memory Promote Review

- Generated at: 2026-06-15T20:00:00
- Candidate count: 5
- Redacted: true

These examples use synthetic review items. Check an item only after a human reviewer has distilled the durable fact.

## Client A

- [x] message_id: 1
  - sent_at: 2026-06-15 09:00:00
  - sender: Client A
  - reasons: todo, deadline
  - body: [redacted len=64]
  - distilled_fact: TODO: Send the revised proposal to Client A by Friday.
  - promote_to: todos/client-a.md

- [x] message_id: 2
  - sent_at: 2026-06-15 10:30:00
  - sender: Me
  - reasons: decision
  - body: [redacted len=58]
  - distilled_fact: Decision: Use SQLite as the local source of truth for chat memory.
  - promote_to: decisions/local-chat-memory.md

- [x] message_id: 3
  - sent_at: 2026-06-15 11:15:00
  - sender: Client A
  - reasons: question
  - body: [redacted len=42]
  - distilled_fact: Question: Client A asked whether the package can support group chat exports.
  - promote_to: questions/client-a.md

- [x] message_id: 4
  - sent_at: 2026-06-15 12:00:00
  - sender: Client A
  - reasons: person_note
  - body: [redacted len=36]
  - distilled_fact: Person note: Client A prefers concise status updates before noon.
  - promote_to: people/client-a.md

- [x] message_id: 5
  - sent_at: 2026-06-15 13:00:00
  - sender: Me
  - reasons: project_note
  - body: [redacted len=45]
  - distilled_fact: Project note: Parser fixtures should stay synthetic and public-safe.
  - promote_to: projects/local-chat-memory.md
