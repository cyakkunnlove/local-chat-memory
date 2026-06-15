PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_name TEXT NOT NULL UNIQUE,
  chat_kind TEXT NOT NULL DEFAULT 'personal',
  include_for_ai INTEGER NOT NULL DEFAULT 1,
  purpose TEXT,
  wiki_path TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL UNIQUE,
  canonical_name TEXT,
  wiki_path TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS person_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES people(id),
  alias TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_participants (
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  person_id INTEGER NOT NULL REFERENCES people(id),
  role TEXT NOT NULL DEFAULT 'member',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(chat_id, person_id)
);

CREATE TABLE IF NOT EXISTS raw_exports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  source_path TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parser_version TEXT NOT NULL,
  parsed_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  raw_export_id INTEGER NOT NULL REFERENCES raw_exports(id),
  sent_at TEXT,
  sent_date TEXT,
  sent_time TEXT,
  sender TEXT NOT NULL,
  body TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  fingerprint_base TEXT NOT NULL,
  occurrence_index INTEGER NOT NULL,
  fingerprint TEXT NOT NULL UNIQUE,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  sender_person_id INTEGER REFERENCES people(id),
  classification TEXT NOT NULL DEFAULT 'message',
  ai_processed INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_sent_at ON messages(chat_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_pending ON messages(ai_processed, classification, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_body_hash ON messages(body_hash);

CREATE TABLE IF NOT EXISTS message_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL REFERENCES messages(id),
  event_type TEXT NOT NULL,
  event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note TEXT
);

CREATE TABLE IF NOT EXISTS export_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER REFERENCES chats(id),
  target_name TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  result_json TEXT,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_export_attempts_chat_started ON export_attempts(chat_id, started_at);
CREATE INDEX IF NOT EXISTS idx_export_attempts_target_started ON export_attempts(target_name, started_at);
