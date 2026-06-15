#!/usr/bin/env python3
"""Import LINE exported chat text into local SQLite for AI-ready diffs."""

from __future__ import annotations

import argparse
import shutil
import csv
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
import shutil as shutil_mod
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

PARSER_VERSION = "local-chat-memory-v0.1"
PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("LOCAL_CHAT_MEMORY_DB", PROJECT_DIR / "data" / "local-chat-memory.db"))
SCHEMA_PATH = PROJECT_DIR / "schema.sql"
CONFIG_TEMPLATE = {
    "download_dir": "~/Downloads",
    "processed_dir": None,
    "default_self_aliases": ["me"],
    "default_wiki_path": None,
    "chats": [
        {
            "chat_name": "Example Chat",
            "chat_kind": "personal",
            "filename_contains": "[LINE]Example Chat",
            "participants": [
                {"display_name": "Example Chat", "aliases": ["Example Chat"], "wiki_path": None},
                {"display_name": "Me", "aliases": ["me"], "wiki_path": None},
            ],
            "purpose": "Example LINE export",
            "wiki_path": None,
        }
    ],
}


DATE_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})(?:\s+.*|[（(].*)?$"),
    re.compile(r"^(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?:\s+.*|[（(].*)?$"),
]

MESSAGE_PATTERNS = [
    re.compile(
        r"^\[(?P<date>\d{4}[./-]\d{1,2}[./-]\d{1,2})\s+"
        r"(?P<time>\d{1,2}:\d{2})(?::\d{2})?\]\s*"
        r"(?P<sender>[^:：]+)[:：]\s*(?P<body>.*)$"
    ),
    re.compile(
        r"^(?P<date>\d{4}[./-]\d{1,2}[./-]\d{1,2})\s+"
        r"(?P<time>\d{1,2}:\d{2})(?::\d{2})?\t"
        r"(?P<sender>[^\t]+)\t(?P<body>.*)$"
    ),
    re.compile(
        r"^(?P<date>\d{4}[./-]\d{1,2}[./-]\d{1,2})\t"
        r"(?P<time>\d{1,2}:\d{2})(?::\d{2})?\t"
        r"(?P<sender>[^\t]+)\t(?P<body>.*)$"
    ),
    re.compile(r"^(?P<time>\d{1,2}:\d{2})(?::\d{2})?\t(?P<sender>[^\t]+)\t(?P<body>.*)$"),
    re.compile(r"^(?P<time>\d{1,2}:\d{2})(?::\d{2})?\s{2,}(?P<sender>.+?)\s{2,}(?P<body>.*)$"),
]

ATTACHMENT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"^\[(photo|image|sticker|video|file|voice message|音声メッセージ|写真|画像|動画|ファイル|スタンプ)\]$",
        r"^(写真|画像|動画|ファイル|スタンプ|音声メッセージ)を送信しました",
    ]
]

SYSTEM_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"トーク履歴",
        r"保存されました",
        r"メンバーがいません",
        r"が参加しました",
        r"が退出しました",
        r"が退会しました",
        r"メッセージの送信を取り消しました",
        r"通話時間",
        r"missed call",
    ]
]

AD_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"キャンペーン",
        r"クーポン",
        r"セール",
        r"割引",
        r"送料無料",
        r"期間限定",
        r"今だけ",
        r"ポイント[0-9０-９]+倍",
        r"promo|promotion|coupon|sale",
    ]
]

OFFICIAL_SENDER_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"公式",
        r"official",
        r"LINE\s*公式",
        r"LINE\s*VOOM",
        r"LINE\s*Pay",
        r"LINE\s*ギフト",
    ]
]


@dataclass
class ParsedMessage:
    sent_date: str | None
    sent_time: str | None
    sender: str
    body: str
    line_start: int
    line_end: int

    @property
    def sent_at(self) -> str | None:
        if self.sent_date and self.sent_time:
            return f"{self.sent_date} {self.sent_time}:00"
        return None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def normalize_alias_key(value: str) -> str:
    return normalize_space(unicodedata.normalize("NFKC", value)).casefold()


def normalize_date(value: str) -> str:
    value = value.replace(".", "/").replace("-", "/")
    year, month, day = [int(part) for part in value.split("/")[:3]]
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_date_line(line: str) -> str | None:
    stripped = line.strip()
    for pattern in DATE_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-{int(match.group('day')):02d}"
    return None


def match_space_participant(line: str, current_date: str | None, participants: list[str]) -> tuple[str | None, str | None, str, str] | None:
    match = re.match(r"^(?P<time>\d{1,2}:\d{2})(?::\d{2})?\s+(?P<rest>.+)$", line.rstrip("\n"))
    if not match:
        return None
    rest = match.group("rest")
    for participant in sorted({p for p in participants if p}, key=len, reverse=True):
        prefix = f"{participant} "
        if rest == participant:
            body = ""
        elif rest.startswith(prefix):
            body = rest[len(prefix) :].strip()
        else:
            continue
        hour, minute = [int(part) for part in match.group("time").split(":")[:2]]
        return current_date, f"{hour:02d}:{minute:02d}", participant, body
    fallback = re.match(r"(?P<sender>\S+)\s+(?P<body>.*)$", rest)
    if fallback:
        hour, minute = [int(part) for part in match.group("time").split(":")[:2]]
        return current_date, f"{hour:02d}:{minute:02d}", fallback.group("sender"), fallback.group("body").strip()
    return None


def parse_message_line(line: str, current_date: str | None, participants: list[str] | None = None) -> tuple[str | None, str | None, str, str] | None:
    stripped = line.rstrip("\n")
    for pattern in MESSAGE_PATTERNS:
        match = pattern.match(stripped)
        if not match:
            continue
        date = match.groupdict().get("date")
        sent_date = normalize_date(date) if date else current_date
        sent_time = match.group("time")
        hour, minute = [int(part) for part in sent_time.split(":")[:2]]
        sender = normalize_space(match.group("sender"))
        body = match.group("body").strip()
        return sent_date, f"{hour:02d}:{minute:02d}", sender, body
    if participants:
        return match_space_participant(stripped, current_date, participants)
    return None


def parse_export_text(text: str, participants: list[str] | None = None) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    current_date: str | None = None
    current: ParsedMessage | None = None
    participants = participants or []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parsed = parse_message_line(line, current_date, participants)
        if parsed:
            if current:
                current.line_end = line_no - 1
                messages.append(current)
            sent_date, sent_time, sender, body = parsed
            current = ParsedMessage(sent_date, sent_time, sender, body, line_no, line_no)
            continue
        date_line = parse_date_line(line)
        if date_line:
            if current:
                current.line_end = line_no - 1
                messages.append(current)
                current = None
            current_date = date_line
            continue
        if current:
            current.body = f"{current.body}\n{line.rstrip()}".strip()
            current.line_end = line_no

    if current:
        messages.append(current)
    return messages


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    ensure_migrations(con)
    con.commit()


def ensure_migrations(con: sqlite3.Connection) -> None:
    chat_columns = {row["name"] for row in con.execute("PRAGMA table_info(chats)").fetchall()}
    if "purpose" not in chat_columns:
        con.execute("ALTER TABLE chats ADD COLUMN purpose TEXT")
    if "wiki_path" not in chat_columns:
        con.execute("ALTER TABLE chats ADD COLUMN wiki_path TEXT")
    message_columns = {row["name"] for row in con.execute("PRAGMA table_info(messages)").fetchall()}
    if "sender_person_id" not in message_columns:
        con.execute("ALTER TABLE messages ADD COLUMN sender_person_id INTEGER REFERENCES people(id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender_person ON messages(sender_person_id, sent_at)")
    con.execute(
        """
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
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_export_attempts_chat_started ON export_attempts(chat_id, started_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_export_attempts_target_started ON export_attempts(target_name, started_at)")


def participant_specs(participants: list[object] | None) -> list[dict[str, object]]:
    specs = []
    for item in participants or []:
        if isinstance(item, str):
            specs.append({"display_name": item, "aliases": [item], "wiki_path": None, "role": "member"})
            continue
        if isinstance(item, dict):
            display_name = str(item.get("display_name") or item.get("name") or "").strip()
            if not display_name:
                continue
            aliases = item.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            merged_aliases = list(dict.fromkeys([display_name, *[str(alias) for alias in aliases if str(alias).strip()]]))
            specs.append(
                {
                    "display_name": display_name,
                    "aliases": merged_aliases,
                    "wiki_path": item.get("wiki_path"),
                    "role": item.get("role", "member"),
                }
            )
    return specs


def participant_names(participants: list[object] | None) -> list[str]:
    names = []
    for spec in participant_specs(participants):
        names.extend(str(alias) for alias in spec["aliases"])
    return list(dict.fromkeys(names))


def get_or_create_person(
    con: sqlite3.Connection,
    display_name: str,
    aliases: list[str] | None = None,
    wiki_path: str | None = None,
) -> int:
    existing = find_person(con, display_name)
    if existing:
        person_id = int(existing["id"])
        if wiki_path:
            con.execute(
                "UPDATE people SET wiki_path = COALESCE(wiki_path, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (wiki_path, person_id),
            )
        for alias in list(dict.fromkeys([display_name, *(aliases or [])])):
            con.execute(
                """
                INSERT INTO person_aliases(person_id, alias)
                VALUES(?, ?)
                ON CONFLICT(alias) DO UPDATE SET person_id = excluded.person_id
                """,
                (person_id, alias),
            )
        return person_id
    con.execute(
        """
        INSERT INTO people(display_name, canonical_name, wiki_path)
        VALUES(?, ?, ?)
        ON CONFLICT(display_name) DO UPDATE SET
          wiki_path = COALESCE(excluded.wiki_path, people.wiki_path),
          updated_at = CURRENT_TIMESTAMP
        """,
        (display_name, display_name, wiki_path),
    )
    row = con.execute("SELECT id FROM people WHERE display_name = ?", (display_name,)).fetchone()
    person_id = int(row["id"])
    for alias in list(dict.fromkeys([display_name, *(aliases or [])])):
        con.execute(
            """
            INSERT INTO person_aliases(person_id, alias)
            VALUES(?, ?)
            ON CONFLICT(alias) DO UPDATE SET person_id = excluded.person_id
            """,
            (person_id, alias),
        )
    return person_id


def sync_chat_participants(con: sqlite3.Connection, chat_id: int, participants: list[object] | None) -> dict[str, int]:
    alias_to_person: dict[str, int] = {}
    for spec in participant_specs(participants):
        aliases = [str(alias) for alias in spec["aliases"]]
        person_id = get_or_create_person(
            con,
            str(spec["display_name"]),
            aliases,
            str(spec["wiki_path"]) if spec.get("wiki_path") else None,
        )
        con.execute(
            """
            INSERT INTO chat_participants(chat_id, person_id, role)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id, person_id) DO UPDATE SET role = excluded.role
            """,
            (chat_id, person_id, str(spec.get("role") or "member")),
        )
        for alias in aliases:
            alias_to_person[normalize_alias_key(alias)] = person_id
    return alias_to_person


def resolve_sender_person_id(alias_to_person: dict[str, int], sender: str) -> int | None:
    return alias_to_person.get(normalize_alias_key(sender))


def resolve_or_create_sender_person_id(
    con: sqlite3.Connection,
    chat_id: int,
    alias_to_person: dict[str, int],
    sender: str,
    classification: str,
) -> int | None:
    person_id = resolve_sender_person_id(alias_to_person, sender)
    if person_id is not None:
        return person_id
    if classification == "official":
        return None
    sender_name = normalize_space(sender)
    if not sender_name:
        return None
    person_id = get_or_create_person(con, sender_name, [sender_name])
    con.execute(
        """
        INSERT INTO chat_participants(chat_id, person_id, role)
        VALUES(?, ?, 'member')
        ON CONFLICT(chat_id, person_id) DO NOTHING
        """,
        (chat_id, person_id),
    )
    alias_to_person[normalize_alias_key(sender_name)] = person_id
    return person_id


def backfill_sender_person_ids(con: sqlite3.Connection, chat_id: int, alias_to_person: dict[str, int]) -> int:
    changed = 0
    rows = con.execute(
        "SELECT id, sender FROM messages WHERE chat_id = ? AND sender_person_id IS NULL",
        (chat_id,),
    ).fetchall()
    for row in rows:
        classification_row = con.execute("SELECT classification FROM messages WHERE id = ?", (int(row["id"]),)).fetchone()
        person_id = resolve_or_create_sender_person_id(
            con,
            chat_id,
            alias_to_person,
            row["sender"],
            classification_row["classification"] if classification_row else "message",
        )
        if person_id is None:
            continue
        con.execute("UPDATE messages SET sender_person_id = ? WHERE id = ?", (person_id, int(row["id"])))
        changed += 1
    return changed


def get_or_create_chat(
    con: sqlite3.Connection,
    chat_name: str,
    chat_kind: str,
    purpose: str | None = None,
    wiki_path: str | None = None,
) -> int:
    include_for_ai = 0 if chat_kind == "official" else 1
    con.execute(
        """
        INSERT INTO chats(chat_name, chat_kind, include_for_ai, purpose, wiki_path)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(chat_name) DO UPDATE SET
          chat_kind = excluded.chat_kind,
          include_for_ai = excluded.include_for_ai,
          purpose = COALESCE(excluded.purpose, chats.purpose),
          wiki_path = COALESCE(excluded.wiki_path, chats.wiki_path),
          updated_at = CURRENT_TIMESTAMP
        """,
        (chat_name, chat_kind, include_for_ai, purpose, wiki_path),
    )
    row = con.execute("SELECT id FROM chats WHERE chat_name = ?", (chat_name,)).fetchone()
    return int(row["id"])


def classify_message(chat_kind: str, sender: str, body: str) -> str:
    sender_norm = normalize_space(sender)
    body_norm = normalize_space(body)
    if chat_kind == "official":
        return "official"
    if any(pattern.search(sender_norm) for pattern in OFFICIAL_SENDER_PATTERNS):
        return "official"
    if any(pattern.search(body_norm) for pattern in ATTACHMENT_PATTERNS):
        return "attachment"
    if any(pattern.search(body_norm) for pattern in SYSTEM_PATTERNS):
        return "system"
    if any(pattern.search(body_norm) for pattern in AD_PATTERNS):
        return "ad"
    return "message"


def message_fingerprints(chat_id: int, messages: Iterable[ParsedMessage]) -> list[tuple[ParsedMessage, str, str, int, str]]:
    counts: dict[str, int] = {}
    rows = []
    for msg in messages:
        sender_norm = normalize_space(msg.sender).casefold()
        body_norm = normalize_space(msg.body)
        body_hash = sha256_text(body_norm)
        base = "|".join([str(chat_id), msg.sent_at or "", sender_norm, body_hash])
        counts[base] = counts.get(base, 0) + 1
        occurrence_index = counts[base]
        fingerprint = sha256_text(f"{base}|{occurrence_index}")
        rows.append((msg, body_hash, base, occurrence_index, fingerprint))
    return rows


def import_export(
    con: sqlite3.Connection,
    db_path: Path,
    chat_name: str,
    chat_kind: str,
    file_path: Path,
    participants: list[object] | None = None,
    purpose: str | None = None,
    wiki_path: str | None = None,
) -> dict[str, int | str]:
    init_db(con)
    chat_id = get_or_create_chat(con, chat_name, chat_kind, purpose, wiki_path)
    alias_to_person = sync_chat_participants(con, chat_id, participants)
    backfilled = backfill_sender_person_ids(con, chat_id, alias_to_person)
    source_hash = sha256_file(file_path)
    existing_export = con.execute(
        "SELECT id FROM raw_exports WHERE chat_id = ? AND source_sha256 = ? ORDER BY id LIMIT 1",
        (chat_id, source_hash),
    ).fetchone()
    if existing_export:
        con.commit()
        return {
            "db": str(db_path),
            "chat": chat_name,
            "raw_export_id": int(existing_export["id"]),
            "parsed": 0,
            "inserted": 0,
            "duplicates": 0,
            "skipped": "same_export_hash",
            "sender_backfilled": backfilled,
        }

    source_text = file_path.read_text(encoding="utf-8-sig")
    parser_participants = list(dict.fromkeys([chat_name, *participant_names(participants)]))
    parsed = parse_export_text(source_text, parser_participants)
    cur = con.execute(
        """
        INSERT INTO raw_exports(chat_id, source_path, source_sha256, parser_version, parsed_count)
        VALUES(?, ?, ?, ?, ?)
        """,
        (chat_id, str(file_path), source_hash, PARSER_VERSION, len(parsed)),
    )
    raw_export_id = int(cur.lastrowid)

    inserted = 0
    duplicates = 0
    for msg, body_hash, base, occurrence_index, fingerprint in message_fingerprints(chat_id, parsed):
        classification = classify_message(chat_kind, msg.sender, msg.body)
        sender_person_id = resolve_or_create_sender_person_id(con, chat_id, alias_to_person, msg.sender, classification)
        try:
            con.execute(
                """
                INSERT INTO messages(
                  chat_id, raw_export_id, sent_at, sent_date, sent_time, sender, body,
                  body_hash, fingerprint_base, occurrence_index, fingerprint,
                  line_start, line_end, sender_person_id, classification
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    raw_export_id,
                    msg.sent_at,
                    msg.sent_date,
                    msg.sent_time,
                    msg.sender,
                    msg.body,
                    body_hash,
                    base,
                    occurrence_index,
                    fingerprint,
                    msg.line_start,
                    msg.line_end,
                    sender_person_id,
                    classification,
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            duplicates += 1

    con.execute(
        "UPDATE raw_exports SET inserted_count = ?, duplicate_count = ? WHERE id = ?",
        (inserted, duplicates, raw_export_id),
    )
    con.commit()
    return {
        "db": str(db_path),
        "chat": chat_name,
        "raw_export_id": raw_export_id,
        "parsed": len(parsed),
        "inserted": inserted,
        "duplicates": duplicates,
        "sender_backfilled": backfilled,
    }


def load_config(path: Path) -> dict:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def write_config_template(output: Path, force: bool = False) -> dict:
    target = output.expanduser()
    if target.exists() and not force:
        return {"status": "exists", "output": str(target), "note": "Pass --force to overwrite."}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "written", "output": str(target)}


def validate_config(path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    config = load_config(path)
    download_dir = Path(config.get("download_dir", "~/Downloads")).expanduser()
    if not download_dir.exists():
        errors.append(f"download_dir does not exist: {download_dir}")
    chats = config.get("chats")
    if not isinstance(chats, list):
        errors.append("chats must be a list")
        chats = []
    seen_names: set[str] = set()
    seen_markers: set[str] = set()
    matches = []
    for index, chat in enumerate(chats):
        if not isinstance(chat, dict):
            errors.append(f"chats[{index}] must be an object")
            continue
        chat_name = str(chat.get("chat_name") or "").strip()
        marker = str(chat.get("filename_contains") or "").strip()
        chat_kind = str(chat.get("chat_kind") or "personal")
        if not chat_name:
            errors.append(f"chats[{index}].chat_name is required")
        if chat_name in seen_names:
            warnings.append(f"duplicate chat_name: {chat_name}")
        if chat_name:
            seen_names.add(chat_name)
        if chat_kind not in {"personal", "group", "official"}:
            errors.append(f"{chat_name or f'chats[{index}]'} has invalid chat_kind: {chat_kind}")
        if not marker:
            errors.append(f"{chat_name or f'chats[{index}]'} filename_contains is required")
        if marker in seen_markers:
            warnings.append(f"duplicate filename_contains: {marker}")
        if marker:
            seen_markers.add(marker)
        participants = chat.get("participants", [])
        if participants is not None and not isinstance(participants, list):
            errors.append(f"{chat_name or f'chats[{index}]'} participants must be a list")
        matched_files = sorted([p.name for p in download_dir.glob("*.txt") if marker and marker in p.name])
        if marker and not matched_files:
            warnings.append(f"no files currently match {marker}")
        matches.append({"chat_name": chat_name, "filename_contains": marker, "matched_files": matched_files[:5]})
    return {
        "status": "ok" if not errors else "invalid",
        "config": str(path.expanduser()),
        "download_dir": str(download_dir),
        "chat_count": len(chats),
        "errors": errors,
        "warnings": warnings,
        "matches": matches,
    }


def doctor_report(config_path: Path | None = None) -> dict:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "project_dir": str(PROJECT_DIR),
        "default_db": str(DEFAULT_DB),
        "tools": {
            "sqlite3_module": True,
            "osascript": shutil_mod.which("osascript") is not None,
            "cliclick": shutil_mod.which("cliclick") is not None,
        },
    }
    if config_path:
        report["config"] = validate_config(config_path)
    return report


def chat_name_from_line_export(path: Path) -> str:
    name = path.stem
    if name.startswith("[LINE]"):
        name = name[len("[LINE]") :]
    return name.strip()


def guess_chat_kind(chat_name: str) -> str:
    group_markers = [
        "PJ",
        "プロジェクト",
        "グループ",
        "チーム",
        "✖",
        "×",
        "アプリ",
        "Improve",
        "インプルーブ",
        "昇天の日",
    ]
    if any(marker in chat_name for marker in group_markers):
        return "group"
    if "公式" in chat_name or "LINE" in chat_name.upper():
        return "official"
    return "personal"


def discover_line_exports(download_dir: Path) -> list[dict]:
    entries = []
    candidates = [
        path
        for path in download_dir.glob("*.txt")
        if path.name.startswith("[LINE]") and path.name.endswith(".txt")
    ]
    for file_path in sorted(candidates, key=lambda p: p.stat().st_mtime):
        chat_name = chat_name_from_line_export(file_path)
        entries.append(
            {
                "chat_name": chat_name,
                "chat_kind": guess_chat_kind(chat_name),
                "filename_contains": file_path.name,
                "participants": [
                    {"display_name": chat_name, "aliases": [chat_name], "wiki_path": None},
                    {
                        "display_name": "Me",
                        "aliases": ["me"],
                        "wiki_path": None,
                    },
                ],
                "purpose": "auto-discovered LINE export",
                "wiki_path": None,
            }
        )
    return entries


def scan_downloads(
    con: sqlite3.Connection,
    db_path: Path,
    config_path: Path,
    move_processed: bool = False,
    auto_discover: bool = False,
) -> list[dict]:
    config = load_config(config_path) if config_path.exists() else {}
    download_dir = Path(config.get("download_dir", "~/Downloads")).expanduser()
    processed_dir_value = config.get("processed_dir")
    processed_dir = Path(processed_dir_value).expanduser() if processed_dir_value else None
    chat_entries = list(config.get("chats", []))
    if auto_discover:
        known_markers = [str(entry.get("filename_contains") or "") for entry in chat_entries]
        for entry in discover_line_exports(download_dir):
            filename = str(entry["filename_contains"])
            if not any(marker and marker in filename for marker in known_markers):
                chat_entries.append(entry)
    results = []
    for chat in chat_entries:
        marker = chat["filename_contains"]
        candidates = sorted(
            [p for p in download_dir.glob("*.txt") if marker in p.name],
            key=lambda p: p.stat().st_mtime,
        )
        for file_path in candidates:
            result = import_export(
                con,
                db_path,
                chat["chat_name"],
                chat.get("chat_kind", "personal"),
                file_path,
                chat.get("participants", []),
                chat.get("purpose"),
                chat.get("wiki_path"),
            )
            results.append(result)
            if move_processed and processed_dir:
                processed_dir.mkdir(parents=True, exist_ok=True)
                target = processed_dir / file_path.name
                if target.exists():
                    target = processed_dir / f"{file_path.stem}-{datetime.now().strftime('%Y%m%d%H%M%S')}{file_path.suffix}"
                shutil.move(str(file_path), target)
                result["moved_to"] = str(target)
    return results


def pending_rows(con: sqlite3.Connection, chat: str | None, limit: int) -> list[sqlite3.Row]:
    params: list[object] = []
    where = ["m.ai_processed = 0", "m.classification = 'message'", "c.include_for_ai = 1"]
    if chat:
        where.append("c.chat_name = ?")
        params.append(chat)
    params.append(limit)
    return list(
        con.execute(
            f"""
            SELECT m.id, c.chat_name, m.sent_at, m.sender, m.body
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(m.sent_at, ''), m.id
            LIMIT ?
            """,
            params,
        )
    )


def search_rows(
    con: sqlite3.Connection,
    query: str,
    chat: str | None,
    limit: int,
    since: str | None = None,
    until: str | None = None,
    include_noise: bool = False,
) -> list[sqlite3.Row]:
    params: list[object] = [f"%{query}%"]
    where = ["m.body LIKE ?"]
    if chat:
        where.append("c.chat_name = ?")
        params.append(chat)
    if since:
        where.append("m.sent_at >= ?")
        params.append(since)
    if until:
        where.append("m.sent_at <= ?")
        params.append(until)
    if not include_noise:
        where.append("m.classification = 'message'")
        where.append("c.include_for_ai = 1")
    params.append(limit)
    return list(
        con.execute(
            f"""
            SELECT
              m.id,
              c.chat_name,
              c.purpose,
              c.wiki_path,
              m.sent_at,
              m.sender,
              m.body,
              m.classification
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(m.sent_at, ''), m.id
            LIMIT ?
            """,
            params,
        )
    )


def print_search(rows: list[sqlite3.Row], fmt: str, redact: bool = False) -> None:
    payload = []
    for row in rows:
        item = dict(row)
        body = str(item["body"])
        if redact:
            item["body"] = f"[redacted len={len(body)}]"
        payload.append(item)
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    current_chat = None
    for item in payload:
        if item["chat_name"] != current_chat:
            current_chat = item["chat_name"]
            wiki = f" ({item['wiki_path']})" if item.get("wiki_path") else ""
            print(f"\n## {current_chat}{wiki}")
            if item.get("purpose"):
                print(f"- purpose: {item['purpose']}")
        body = str(item["body"]).replace("\n", "\n  ")
        print(f"- [{item['id']}] {item['sent_at'] or 'unknown-time'} {item['sender']}: {body}")


def print_pending(rows: list[sqlite3.Row], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=["id", "chat_name", "sent_at", "sender", "body"])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return
    current_chat = None
    for row in rows:
        if row["chat_name"] != current_chat:
            current_chat = row["chat_name"]
            print(f"\n## {current_chat}")
        sent = row["sent_at"] or "unknown-time"
        body = str(row["body"]).replace("\n", "\n  ")
        print(f"- [{row['id']}] {sent} {row['sender']}: {body}")


def pending_payload(rows: list[sqlite3.Row], redact: bool = False) -> dict:
    messages = []
    for row in rows:
        body = str(row["body"])
        messages.append(
            {
                "id": row["id"],
                "chat_name": row["chat_name"],
                "sent_at": row["sent_at"],
                "sender": row["sender"],
                "body": f"[redacted len={len(body)}]" if redact else body,
            }
        )
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "message_count": len(messages),
        "messages": messages,
    }


def render_pending_markdown(payload: dict) -> str:
    lines = [
        "# LINE Pending Messages",
        "",
        f"- Exported at: {payload['exported_at']}",
        f"- Message count: {payload['message_count']}",
        "",
    ]
    current_chat = None
    for msg in payload["messages"]:
        if msg["chat_name"] != current_chat:
            current_chat = msg["chat_name"]
            lines.extend([f"## {current_chat}", ""])
        body = str(msg["body"]).replace("\n", "\n  ")
        lines.append(f"- [{msg['id']}] {msg['sent_at'] or 'unknown-time'} {msg['sender']}: {body}")
    lines.append("")
    return "\n".join(lines)


def export_pending(
    con: sqlite3.Connection,
    chat: str | None,
    limit: int,
    fmt: str,
    output: Path,
    redact: bool = False,
) -> dict:
    rows = pending_rows(con, chat, limit)
    payload = pending_payload(rows, redact)
    output.expanduser().parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        output.expanduser().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output.expanduser().write_text(render_pending_markdown(payload), encoding="utf-8")
    return {"output": str(output.expanduser()), "message_count": len(rows), "redacted": redact}


def status_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT
              c.chat_name,
              c.chat_kind,
              c.purpose,
              c.wiki_path,
              COUNT(m.id) AS message_count,
              SUM(CASE WHEN m.classification = 'message' THEN 1 ELSE 0 END) AS normal_count,
              SUM(CASE WHEN m.classification != 'message' THEN 1 ELSE 0 END) AS excluded_count,
              SUM(CASE WHEN m.ai_processed = 0 AND m.classification = 'message' THEN 1 ELSE 0 END) AS pending_count,
              MAX(m.sent_at) AS latest_sent_at
            FROM chats c
            LEFT JOIN messages m ON m.chat_id = c.id
            GROUP BY c.id
            ORDER BY c.chat_name
            """
        )
    )


def people_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT
              p.id,
              p.display_name,
              p.wiki_path,
              (
                SELECT GROUP_CONCAT(alias)
                FROM (
                  SELECT DISTINCT alias
                  FROM person_aliases
                  WHERE person_id = p.id
                  ORDER BY alias
                )
              ) AS aliases,
              (
                SELECT COUNT(*)
                FROM chat_participants
                WHERE person_id = p.id
              ) AS chat_count,
              (
                SELECT COUNT(*)
                FROM messages
                WHERE sender_person_id = p.id
              ) AS sent_message_count,
              (
                SELECT MAX(sent_at)
                FROM messages
                WHERE sender_person_id = p.id
              ) AS latest_sent_at
            FROM people p
            ORDER BY p.display_name
            """
        )
    )


def alias_candidate_rows(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        """
        SELECT p.id AS person_id, p.display_name, pa.alias
        FROM people p
        LEFT JOIN person_aliases pa ON pa.person_id = p.id
        ORDER BY p.display_name, pa.alias
        """
    ).fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        for value in [row["display_name"], row["alias"]]:
            if not value:
                continue
            key = normalize_alias_key(str(value))
            item = grouped.setdefault(key, {"normalized": key, "people": {}})
            person = item["people"].setdefault(
                int(row["person_id"]),
                {"person_id": int(row["person_id"]), "display_name": row["display_name"], "aliases": set()},
            )
            person["aliases"].add(str(value))
    candidates = []
    for item in grouped.values():
        people = list(item["people"].values())
        if len(people) <= 1:
            continue
        for person in people:
            person["aliases"] = sorted(person["aliases"])
        candidates.append({"normalized": item["normalized"], "people": sorted(people, key=lambda p: p["display_name"])})
    return sorted(candidates, key=lambda item: item["normalized"])


def merge_people(con: sqlite3.Connection, target_name: str, source_names: list[str]) -> dict:
    target = find_person(con, target_name)
    if not target:
        raise ValueError(f"Target person not found: {target_name}")
    target_id = int(target["id"])
    merged = []
    for source_name in source_names:
        source = find_person(con, source_name)
        if not source:
            raise ValueError(f"Source person not found: {source_name}")
        source_id = int(source["id"])
        if source_id == target_id:
            continue
        aliases = con.execute("SELECT alias FROM person_aliases WHERE person_id = ?", (source_id,)).fetchall()
        for alias_row in aliases:
            con.execute(
                """
                INSERT INTO person_aliases(person_id, alias)
                VALUES(?, ?)
                ON CONFLICT(alias) DO UPDATE SET person_id = excluded.person_id
                """,
                (target_id, alias_row["alias"]),
            )
        con.execute(
            """
            INSERT INTO person_aliases(person_id, alias)
            VALUES(?, ?)
            ON CONFLICT(alias) DO UPDATE SET person_id = excluded.person_id
            """,
            (target_id, source["display_name"]),
        )
        links = con.execute("SELECT chat_id, role FROM chat_participants WHERE person_id = ?", (source_id,)).fetchall()
        for link in links:
            con.execute(
                """
                INSERT INTO chat_participants(chat_id, person_id, role)
                VALUES(?, ?, ?)
                ON CONFLICT(chat_id, person_id) DO UPDATE SET role = excluded.role
                """,
                (int(link["chat_id"]), target_id, link["role"]),
            )
        con.execute("UPDATE messages SET sender_person_id = ? WHERE sender_person_id = ?", (target_id, source_id))
        con.execute("DELETE FROM chat_participants WHERE person_id = ?", (source_id,))
        con.execute("DELETE FROM person_aliases WHERE person_id = ?", (source_id,))
        con.execute("DELETE FROM people WHERE id = ?", (source_id,))
        merged.append({"source_id": source_id, "source_display_name": source["display_name"]})
    con.execute("UPDATE people SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (target_id,))
    con.commit()
    return {"target_id": target_id, "target_display_name": target["display_name"], "merged": merged}


def set_person_wiki(con: sqlite3.Connection, name_or_alias: str, wiki_path: str) -> dict:
    person = find_person(con, name_or_alias)
    if not person:
        raise ValueError(f"Person not found: {name_or_alias}")
    con.execute(
        "UPDATE people SET wiki_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (wiki_path, int(person["id"])),
    )
    con.commit()
    return {"person_id": int(person["id"]), "display_name": person["display_name"], "wiki_path": wiki_path}


def wiki_candidate_rows(con: sqlite3.Connection, min_messages: int = 20) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            SELECT
              p.id,
              p.display_name,
              p.wiki_path,
              (
                SELECT GROUP_CONCAT(alias)
                FROM (
                  SELECT DISTINCT alias
                  FROM person_aliases
                  WHERE person_id = p.id
                  ORDER BY alias
                )
              ) AS aliases,
              COUNT(DISTINCT cp.chat_id) AS chat_count,
              COUNT(DISTINCT CASE WHEN c.chat_kind = 'personal' THEN c.id ELSE NULL END) AS direct_chat_count,
              COUNT(DISTINCT CASE WHEN c.chat_kind = 'group' THEN c.id ELSE NULL END) AS group_chat_count,
              COUNT(DISTINCT m.id) AS sent_message_count,
              MAX(m.sent_at) AS latest_sent_at
            FROM people p
            LEFT JOIN chat_participants cp ON cp.person_id = p.id
            LEFT JOIN chats c ON c.id = cp.chat_id
            LEFT JOIN messages m ON m.sender_person_id = p.id
            GROUP BY p.id
            HAVING sent_message_count >= ? OR chat_count > 1 OR p.wiki_path IS NOT NULL
            ORDER BY
              CASE WHEN p.wiki_path IS NOT NULL THEN 0 ELSE 1 END,
              sent_message_count DESC,
              p.display_name
            """,
            (min_messages,),
        )
    )


def health_report(con: sqlite3.Connection, recent_attempts_limit: int = 10, min_wiki_messages: int = 20) -> dict:
    init_db(con)
    chat_count = con.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    people_count = con.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    message_count = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    pending_count = con.execute(
        "SELECT COUNT(*) FROM messages WHERE ai_processed = 0 AND classification = 'message'"
    ).fetchone()[0]
    latest_sent_at = con.execute("SELECT MAX(sent_at) FROM messages").fetchone()[0]
    by_kind = [
        dict(row)
        for row in con.execute(
            """
            SELECT c.chat_kind, COUNT(DISTINCT c.id) AS chat_count, COUNT(m.id) AS message_count
            FROM chats c
            LEFT JOIN messages m ON m.chat_id = c.id
            GROUP BY c.chat_kind
            ORDER BY c.chat_kind
            """
        ).fetchall()
    ]
    classifications = [
        dict(row)
        for row in con.execute(
            """
            SELECT classification, COUNT(*) AS message_count
            FROM messages
            GROUP BY classification
            ORDER BY message_count DESC, classification
            """
        ).fetchall()
    ]
    export_attempts = [
        dict(row)
        for row in con.execute(
            """
            SELECT status, COUNT(*) AS attempt_count, MAX(started_at) AS latest_started_at
            FROM export_attempts
            GROUP BY status
            ORDER BY attempt_count DESC, status
            """
        ).fetchall()
    ]
    recent_attempts = [
        dict(row)
        for row in con.execute(
            """
            SELECT target_name, status, started_at
            FROM export_attempts
            ORDER BY id DESC
            LIMIT ?
            """,
            (recent_attempts_limit,),
        ).fetchall()
    ]
    wiki_candidates = wiki_candidate_rows(con, min_messages=min_wiki_messages)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parser_version": PARSER_VERSION,
        "totals": {
            "chat_count": chat_count,
            "people_count": people_count,
            "message_count": message_count,
            "pending_count": pending_count,
            "latest_sent_at": latest_sent_at,
        },
        "by_chat_kind": by_kind,
        "classifications": classifications,
        "alias_candidate_count": len(alias_candidate_rows(con)),
        "wiki_candidate_count": len(wiki_candidates),
        "export_attempts": export_attempts,
        "recent_export_attempts": recent_attempts,
        "privacy": {
            "raw_message_bodies_included": False,
            "sender_names_included": False,
            "chat_names_in_recent_attempts": True,
        },
    }


def print_health_report(report: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    totals = report["totals"]
    print("# LINE History Health Report")
    print("")
    print(f"- generated_at: {report['generated_at']}")
    print(f"- parser_version: {report['parser_version']}")
    print(f"- chats: {totals['chat_count']}")
    print(f"- people: {totals['people_count']}")
    print(f"- messages: {totals['message_count']}")
    print(f"- pending_messages: {totals['pending_count']}")
    print(f"- latest_sent_at: {totals['latest_sent_at'] or ''}")
    print(f"- alias_candidate_count: {report['alias_candidate_count']}")
    print(f"- wiki_candidate_count: {report['wiki_candidate_count']}")
    print("")
    print("## Chat Kinds")
    for row in report["by_chat_kind"]:
        print(f"- {row['chat_kind']}: {row['chat_count']} chats / {row['message_count']} messages")
    print("")
    print("## Classifications")
    for row in report["classifications"]:
        print(f"- {row['classification']}: {row['message_count']}")
    print("")
    print("## Export Attempts")
    if not report["export_attempts"]:
        print("- no attempts recorded")
    for row in report["export_attempts"]:
        print(f"- {row['status']}: {row['attempt_count']} latest={row['latest_started_at'] or ''}")


PROMOTE_PATTERNS = {
    "money": re.compile(r"(¥|円|万円|税込|税抜|見積|請求|入金|支払)"),
    "deadline": re.compile(r"(期限|締切|〆切|まで|明日|今日|来週|今週|\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2})"),
    "todo": re.compile(r"(TODO|todo|確認|対応|送付|提出|予約|連絡|お願いします|お願い|やる|作成)"),
    "decision": re.compile(r"(決定|確定|方針|合意|これで|この方向|進める|承認)"),
    "question": re.compile(r"(？|\?|どう|いつ|どこ|どれ|できますか|でしょうか)"),
}


def promote_candidate_rows(
    con: sqlite3.Connection,
    chat: str | None,
    limit: int,
    redact: bool = False,
) -> list[dict]:
    candidates = []
    for row in pending_rows(con, chat, limit):
        body = str(row["body"])
        reasons = [name for name, pattern in PROMOTE_PATTERNS.items() if pattern.search(body)]
        if not reasons:
            continue
        candidates.append(
            {
                "id": row["id"],
                "chat_name": row["chat_name"],
                "sent_at": row["sent_at"],
                "sender": row["sender"],
                "reasons": reasons,
                "body": f"[redacted len={len(body)}]" if redact else body,
            }
        )
    return candidates


def print_promote_candidates(candidates: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(candidates, ensure_ascii=False, indent=2))
        return
    if not candidates:
        print("No promote candidates found.")
        return
    current_chat = None
    for item in candidates:
        if item["chat_name"] != current_chat:
            current_chat = item["chat_name"]
            print(f"\n## {current_chat}")
        reasons = ",".join(item["reasons"])
        body = str(item["body"]).replace("\n", "\n  ")
        print(f"- [{item['id']}] {item['sent_at'] or 'unknown-time'} {item['sender']} ({reasons}): {body}")


def export_promote_review(
    con: sqlite3.Connection,
    output: Path,
    chat: str | None,
    limit: int,
    redact: bool = False,
) -> dict:
    candidates = promote_candidate_rows(con, chat, limit, redact)
    lines = [
        "# LINE Promote Review",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Candidate count: {len(candidates)}",
        f"- Redacted: {redact}",
        "",
        "Review each item. Keep only distilled facts, TODOs, deadlines, amounts, or decisions worth promoting.",
        "",
    ]
    current_chat = None
    for item in candidates:
        if item["chat_name"] != current_chat:
            current_chat = item["chat_name"]
            lines.extend([f"## {current_chat}", ""])
        reasons = ", ".join(item["reasons"])
        body = str(item["body"]).replace("\n", "\n  ")
        lines.extend(
            [
                f"- [ ] message_id: {item['id']}",
                f"  - sent_at: {item['sent_at'] or ''}",
                f"  - sender: {item['sender']}",
                f"  - reasons: {reasons}",
                f"  - body: {body}",
                "  - distilled_fact:",
                "  - promote_to:",
                "",
            ]
        )
    target = output.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    return {"output": str(target), "candidate_count": len(candidates), "redacted": redact}


def find_person(con: sqlite3.Connection, name_or_alias: str) -> sqlite3.Row | None:
    normalized = normalize_space(name_or_alias)
    direct = con.execute(
        """
        SELECT p.*
        FROM people p
        LEFT JOIN person_aliases pa ON pa.person_id = p.id
        WHERE p.display_name = ? OR pa.alias = ?
        ORDER BY p.id
        LIMIT 1
        """,
        (normalized, normalized),
    ).fetchone()
    if direct:
        return direct
    alias_key = normalize_alias_key(name_or_alias)
    rows = con.execute(
        """
        SELECT p.*
        FROM people p
        LEFT JOIN person_aliases pa ON pa.person_id = p.id
        ORDER BY p.id
        """
    ).fetchall()
    for row in rows:
        if normalize_alias_key(row["display_name"]) == alias_key:
            return row
    alias_rows = con.execute("SELECT person_id, alias FROM person_aliases ORDER BY person_id").fetchall()
    for alias_row in alias_rows:
        if normalize_alias_key(alias_row["alias"]) == alias_key:
            return con.execute("SELECT * FROM people WHERE id = ?", (int(alias_row["person_id"]),)).fetchone()
    return None


def person_context_rows(con: sqlite3.Connection, name_or_alias: str) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    person = find_person(con, name_or_alias)
    if not person:
        return None, []
    rows = list(
        con.execute(
            """
            SELECT
              c.chat_name,
              c.chat_kind,
              c.purpose,
              c.wiki_path AS chat_wiki_path,
              cp.role,
              COUNT(m_all.id) AS chat_message_count,
              SUM(CASE WHEN m_all.sender_person_id = ? THEN 1 ELSE 0 END) AS sent_by_person_count,
              MAX(m_all.sent_at) AS latest_chat_sent_at,
              MAX(CASE WHEN m_all.sender_person_id = ? THEN m_all.sent_at ELSE NULL END) AS latest_person_sent_at
            FROM chat_participants cp
            JOIN chats c ON c.id = cp.chat_id
            LEFT JOIN messages m_all ON m_all.chat_id = c.id
            WHERE cp.person_id = ?
            GROUP BY c.id
            ORDER BY c.chat_kind, c.chat_name
            """,
            (int(person["id"]), int(person["id"]), int(person["id"])),
        )
    )
    return person, rows


def print_person_context(person: sqlite3.Row | None, rows: list[sqlite3.Row], fmt: str) -> None:
    if fmt == "json":
        print(
            json.dumps(
                {
                    "person": dict(person) if person else None,
                    "contexts": [dict(row) for row in rows],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not person:
        print("No person found.")
        return
    wiki = f" ({person['wiki_path']})" if person["wiki_path"] else ""
    print(f"# {person['display_name']}{wiki}")
    if not rows:
        print("\nNo linked chats.")
        return
    for row in rows:
        print(
            "\n".join(
                [
                    f"- {row['chat_name']} [{row['chat_kind']}]",
                    f"  - purpose: {row['purpose'] or ''}",
                    f"  - chat_wiki_path: {row['chat_wiki_path'] or ''}",
                    f"  - chat_messages: {row['chat_message_count']}",
                    f"  - sent_by_person: {row['sent_by_person_count'] or 0}",
                    f"  - latest_chat_sent_at: {row['latest_chat_sent_at'] or ''}",
                    f"  - latest_person_sent_at: {row['latest_person_sent_at'] or ''}",
                ]
            )
        )


def print_alias_candidates(candidates: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(candidates, ensure_ascii=False, indent=2))
        return
    if not candidates:
        print("No alias candidates found.")
        return
    for candidate in candidates:
        print(f"\n## {candidate['normalized']}")
        for person in candidate["people"]:
            aliases = ", ".join(person["aliases"])
            print(f"- [{person['person_id']}] {person['display_name']} aliases: {aliases}")


def print_wiki_candidates(rows: list[sqlite3.Row], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        print("No wiki candidates found.")
        return
    for row in rows:
        wiki = row["wiki_path"] or ""
        aliases = row["aliases"] or ""
        print(
            "\n".join(
                [
                    f"- {row['display_name']}",
                    f"  - wiki_path: {wiki}",
                    f"  - aliases: {aliases}",
                    f"  - chats: {row['chat_count']} (direct {row['direct_chat_count']}, group {row['group_chat_count']})",
                    f"  - sent_messages: {row['sent_message_count']}",
                    f"  - latest_sent_at: {row['latest_sent_at'] or ''}",
                ]
            )
        )


def mark_processed(con: sqlite3.Connection, ids: list[int], event_type: str, note: str | None) -> int:
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    con.execute(f"UPDATE messages SET ai_processed = 1 WHERE id IN ({placeholders})", ids)
    con.executemany(
        "INSERT INTO message_events(message_id, event_type, note) VALUES(?, ?, ?)",
        [(message_id, event_type, note) for message_id in ids],
    )
    con.commit()
    return len(ids)


def mark_chat_processed(con: sqlite3.Connection, chat: str, event_type: str, note: str | None) -> int:
    rows = con.execute(
        """
        SELECT m.id
        FROM messages m
        JOIN chats c ON c.id = m.chat_id
        WHERE c.chat_name = ? AND m.ai_processed = 0
        """,
        (chat,),
    ).fetchall()
    return mark_processed(con, [int(row["id"]) for row in rows], event_type, note)


def parse_ids(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    init_config_p = sub.add_parser("init-config")
    init_config_p.add_argument("--output", type=Path, default=PROJECT_DIR / "config.local.json")
    init_config_p.add_argument("--force", action="store_true")

    validate_config_p = sub.add_parser("validate-config")
    validate_config_p.add_argument("--config", type=Path, default=PROJECT_DIR / "config.example.json")

    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--config", type=Path)

    import_p = sub.add_parser("import")
    import_p.add_argument("--chat", required=True)
    import_p.add_argument("--chat-kind", choices=["personal", "group", "official"], default="personal")
    import_p.add_argument("--file", type=Path, required=True)
    import_p.add_argument("--purpose")
    import_p.add_argument("--wiki-path")
    import_p.add_argument(
        "--participant",
        action="append",
        default=[],
        help="Known sender display name. Repeat for names containing spaces.",
    )

    scan_p = sub.add_parser("scan-downloads")
    scan_p.add_argument("--config", type=Path, default=PROJECT_DIR / "config.example.json")
    scan_p.add_argument("--move-processed", action="store_true")
    scan_p.add_argument("--auto-discover", action="store_true", help="Also import every ~/Downloads/[LINE]*.txt not listed in config")

    discover_p = sub.add_parser("discover-downloads")
    discover_p.add_argument("--download-dir", type=Path, default=Path("~/Downloads"))

    pending_p = sub.add_parser("pending")
    pending_p.add_argument("--chat")
    pending_p.add_argument("--limit", type=int, default=100)
    pending_p.add_argument("--format", choices=["markdown", "json", "csv"], default="markdown")

    search_p = sub.add_parser("search")
    search_p.add_argument("query")
    search_p.add_argument("--chat")
    search_p.add_argument("--limit", type=int, default=50)
    search_p.add_argument("--since", help="Inclusive timestamp, e.g. 2026-06-15 or 2026-06-15 00:00:00")
    search_p.add_argument("--until", help="Inclusive timestamp, e.g. 2026-06-15 23:59:59")
    search_p.add_argument("--include-noise", action="store_true")
    search_p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    search_p.add_argument("--redact", action="store_true")

    export_p = sub.add_parser("export-pending")
    export_p.add_argument("--chat")
    export_p.add_argument("--limit", type=int, default=100)
    export_p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    export_p.add_argument("--output", type=Path, default=PROJECT_DIR / "exports" / "pending.md")
    export_p.add_argument("--redact", action="store_true")

    person_context_p = sub.add_parser("person-context")
    person_context_p.add_argument("person")
    person_context_p.add_argument("--format", choices=["markdown", "json"], default="markdown")

    alias_candidates_p = sub.add_parser("alias-candidates")
    alias_candidates_p.add_argument("--format", choices=["markdown", "json"], default="markdown")

    merge_people_p = sub.add_parser("merge-people")
    merge_people_p.add_argument("--target", required=True)
    merge_people_p.add_argument("--source", action="append", required=True)

    set_person_wiki_p = sub.add_parser("set-person-wiki")
    set_person_wiki_p.add_argument("person")
    set_person_wiki_p.add_argument("--wiki-path", required=True)

    wiki_candidates_p = sub.add_parser("wiki-candidates")
    wiki_candidates_p.add_argument("--min-messages", type=int, default=20)
    wiki_candidates_p.add_argument("--format", choices=["markdown", "json"], default="markdown")

    health_p = sub.add_parser("health-report")
    health_p.add_argument("--recent-attempts-limit", type=int, default=10)
    health_p.add_argument("--min-wiki-messages", type=int, default=20)
    health_p.add_argument("--format", choices=["markdown", "json"], default="markdown")

    promote_p = sub.add_parser("promote-candidates")
    promote_p.add_argument("--chat")
    promote_p.add_argument("--limit", type=int, default=200)
    promote_p.add_argument("--redact", action="store_true")
    promote_p.add_argument("--format", choices=["markdown", "json"], default="markdown")

    promote_review_p = sub.add_parser("export-promote-review")
    promote_review_p.add_argument("--chat")
    promote_review_p.add_argument("--limit", type=int, default=200)
    promote_review_p.add_argument("--redact", action="store_true")
    promote_review_p.add_argument("--output", type=Path, default=PROJECT_DIR / "exports" / "promote-review.md")

    mark_p = sub.add_parser("mark-processed")
    mark_p.add_argument("--ids", required=True, help="Comma-separated message IDs")
    mark_p.add_argument("--event-type", default="summarized")
    mark_p.add_argument("--note")

    mark_chat_p = sub.add_parser("mark-chat-processed")
    mark_chat_p.add_argument("--chat", required=True)
    mark_chat_p.add_argument("--event-type", default="baseline")
    mark_chat_p.add_argument("--note")

    sub.add_parser("chats")
    sub.add_parser("people")
    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with connect(args.db) as con:
        if args.command == "init":
            init_db(con)
            print(json.dumps({"db": str(args.db), "status": "initialized"}, ensure_ascii=False))
            return 0
        if args.command == "init-config":
            print(json.dumps(write_config_template(args.output, args.force), ensure_ascii=False, indent=2))
            return 0
        if args.command == "validate-config":
            print(json.dumps(validate_config(args.config), ensure_ascii=False, indent=2))
            return 0
        if args.command == "doctor":
            print(json.dumps(doctor_report(args.config), ensure_ascii=False, indent=2))
            return 0
        if args.command == "import":
            result = import_export(
                con,
                args.db,
                args.chat,
                args.chat_kind,
                args.file,
                args.participant,
                args.purpose,
                args.wiki_path,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "scan-downloads":
            results = scan_downloads(con, args.db, args.config, args.move_processed, args.auto_discover)
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 0
        if args.command == "discover-downloads":
            init_db(con)
            print(json.dumps(discover_line_exports(args.download_dir.expanduser()), ensure_ascii=False, indent=2))
            return 0
        if args.command == "pending":
            init_db(con)
            print_pending(pending_rows(con, args.chat, args.limit), args.format)
            return 0
        if args.command == "search":
            init_db(con)
            print_search(
                search_rows(con, args.query, args.chat, args.limit, args.since, args.until, args.include_noise),
                args.format,
                args.redact,
            )
            return 0
        if args.command == "export-pending":
            init_db(con)
            result = export_pending(con, args.chat, args.limit, args.format, args.output, args.redact)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "person-context":
            init_db(con)
            person, rows = person_context_rows(con, args.person)
            print_person_context(person, rows, args.format)
            return 0
        if args.command == "alias-candidates":
            init_db(con)
            print_alias_candidates(alias_candidate_rows(con), args.format)
            return 0
        if args.command == "merge-people":
            init_db(con)
            print(json.dumps(merge_people(con, args.target, args.source), ensure_ascii=False, indent=2))
            return 0
        if args.command == "set-person-wiki":
            init_db(con)
            print(json.dumps(set_person_wiki(con, args.person, args.wiki_path), ensure_ascii=False, indent=2))
            return 0
        if args.command == "wiki-candidates":
            init_db(con)
            print_wiki_candidates(wiki_candidate_rows(con, args.min_messages), args.format)
            return 0
        if args.command == "health-report":
            print_health_report(health_report(con, args.recent_attempts_limit, args.min_wiki_messages), args.format)
            return 0
        if args.command == "promote-candidates":
            init_db(con)
            print_promote_candidates(promote_candidate_rows(con, args.chat, args.limit, args.redact), args.format)
            return 0
        if args.command == "export-promote-review":
            init_db(con)
            result = export_promote_review(con, args.output, args.chat, args.limit, args.redact)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "mark-processed":
            init_db(con)
            changed = mark_processed(con, parse_ids(args.ids), args.event_type, args.note)
            print(json.dumps({"changed": changed}, ensure_ascii=False))
            return 0
        if args.command == "mark-chat-processed":
            init_db(con)
            changed = mark_chat_processed(con, args.chat, args.event_type, args.note)
            print(json.dumps({"changed": changed}, ensure_ascii=False))
            return 0
        if args.command == "chats":
            init_db(con)
            rows = con.execute(
                """
                SELECT c.chat_name, c.chat_kind, c.include_for_ai, c.purpose, c.wiki_path, COUNT(m.id) AS message_count
                FROM chats c
                LEFT JOIN messages m ON m.chat_id = c.id
                GROUP BY c.id
                ORDER BY c.chat_name
                """
            ).fetchall()
            print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
            return 0
        if args.command == "people":
            init_db(con)
            print(json.dumps([dict(row) for row in people_rows(con)], ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            init_db(con)
            print(json.dumps([dict(row) for row in status_rows(con)], ensure_ascii=False, indent=2))
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
