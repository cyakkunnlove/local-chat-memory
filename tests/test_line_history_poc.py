import sqlite3
import tempfile
import unittest
import importlib.util
import textwrap
from pathlib import Path

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import line_history_poc as poc

EXPORT_HELPER_PATH = PROJECT_DIR / "scripts" / "export-current-line-chat.py"
spec = importlib.util.spec_from_file_location("export_current_line_chat", EXPORT_HELPER_PATH)
export_helper = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(export_helper)


class LineHistoryPocTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.con = poc.connect(self.db_path)
        poc.init_db(self.con)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def fixture(self, name: str) -> Path:
        return PROJECT_DIR / "fixtures" / name

    def count_messages(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def test_import_dedupes_overlapping_exports(self):
        first = poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )
        second = poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_overlap.txt"),
        )

        self.assertEqual(first["parsed"], 7)
        self.assertEqual(first["inserted"], 7)
        self.assertEqual(second["parsed"], 6)
        self.assertEqual(second["inserted"], 1)
        self.assertEqual(second["duplicates"], 5)
        self.assertEqual(self.count_messages(), 8)

    def test_import_skips_exact_same_export_hash(self):
        first = poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )
        second = poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )

        self.assertEqual(first["inserted"], 7)
        self.assertEqual(second["skipped"], "same_export_hash")
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(self.count_messages(), 7)

    def test_pending_excludes_noise_and_preserves_duplicate_real_messages(self):
        poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )
        rows = poc.pending_rows(self.con, None, 100)
        bodies = [row["body"] for row in rows]

        self.assertEqual(len(rows), 5)
        self.assertEqual(bodies.count("了解です。夕方までに確認します。"), 2)
        self.assertFalse(any("キャンペーン" in body for body in bodies))
        self.assertFalse(any("[スタンプ]" in body for body in bodies))
        self.assertIn("ありがとうございます。\nこの行は前のメッセージの続きです。", bodies)

    def test_official_chat_is_stored_but_not_pending(self):
        poc.import_export(
            self.con,
            self.db_path,
            "Official",
            "official",
            self.fixture("sample_line_export_ja.txt"),
        )
        self.assertEqual(self.count_messages(), 7)
        self.assertEqual(poc.pending_rows(self.con, None, 100), [])

    def test_space_separated_export_with_space_sender_name(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "Client Name",
            "personal",
            self.fixture("sample_line_export_space_sender.txt"),
            ["Client Name"],
        )
        self.assertEqual(result["parsed"], 3)
        rows = self.con.execute(
            "SELECT sent_at, sender FROM messages ORDER BY id"
        ).fetchall()
        self.assertEqual(rows[0]["sent_at"], "2026-01-16 13:24:00")
        self.assertEqual(rows[0]["sender"], "Client Name")
        self.assertEqual(rows[1]["sender"], "Me")
        self.assertEqual(rows[2]["sent_at"], "2026-06-15 12:39:00")

    def test_bracketed_export_format(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "Bracketed Chat",
            "personal",
            self.fixture("sample_line_export_bracketed.txt"),
        )
        rows = self.con.execute("SELECT sent_at, sender, body FROM messages ORDER BY id").fetchall()

        self.assertEqual(result["parsed"], 3)
        self.assertEqual(rows[0]["sent_at"], "2026-06-15 14:20:00")
        self.assertEqual(rows[1]["sender"], "Me")
        self.assertEqual(rows[2]["body"], "Thanks.\nThis is a continuation line.")

    def test_iso_tab_export_format(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "ISO Tabs",
            "personal",
            self.fixture("sample_line_export_iso_tabs.txt"),
        )
        rows = self.con.execute("SELECT sent_at, sender, body FROM messages ORDER BY id").fetchall()

        self.assertEqual(result["parsed"], 3)
        self.assertEqual(rows[0]["sent_at"], "2026-06-15 14:20:00")
        self.assertEqual(rows[2]["sent_at"], "2026-06-16 09:10:00")
        self.assertEqual(rows[2]["body"], "Can you send the invoice by Friday?")

    def test_dash_separated_export_format(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "Dash Chat",
            "personal",
            self.fixture("sample_chat_export_dash.txt"),
        )
        rows = self.con.execute("SELECT sent_at, sender, body FROM messages ORDER BY id").fetchall()

        self.assertEqual(result["parsed"], 3)
        self.assertEqual(rows[0]["sent_at"], "2026-06-15 14:20:00")
        self.assertEqual(rows[1]["sender"], "Me")
        self.assertEqual(rows[2]["body"], "Thanks.\nThis is a continuation line.")

    def test_whatsapp_style_us_export_format(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "WhatsApp Style",
            "personal",
            self.fixture("sample_chat_export_whatsapp_us.txt"),
        )
        rows = self.con.execute("SELECT sent_at, sender, body FROM messages ORDER BY id").fetchall()

        self.assertEqual(result["parsed"], 3)
        self.assertEqual(rows[0]["sent_at"], "2026-06-15 14:20:00")
        self.assertEqual(rows[2]["sent_at"], "2026-06-16 09:05:00")
        self.assertEqual(rows[2]["body"], "Please also add the invoice note.\nAdditional detail on the same message.")

    def test_chat_metadata_and_search_rows_support_wiki_link(self):
        poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
            purpose="project notes",
            wiki_path="02_Projects/sample.md",
        )

        rows = poc.search_rows(self.con, "夕方", None, 10)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["purpose"], "project notes")
        self.assertEqual(rows[0]["wiki_path"], "02_Projects/sample.md")
        self.assertIn("夕方", rows[0]["body"])

    def test_person_context_separates_direct_and_group_chats(self):
        participants = [
            {"display_name": "Client A", "aliases": ["Client A"]},
            {"display_name": "Me", "aliases": ["Me"]},
        ]
        poc.import_export(
            self.con,
            self.db_path,
            "Client A",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
            participants,
            purpose="Client Aとの個別DM",
        )
        poc.import_export(
            self.con,
            self.db_path,
            "Project Group",
            "group",
            self.fixture("sample_line_export_overlap.txt"),
            participants,
            purpose="案件グループ",
        )

        person, rows = poc.person_context_rows(self.con, "Client A")
        contexts = {row["chat_name"]: row for row in rows}

        self.assertEqual(person["display_name"], "Client A")
        self.assertEqual(contexts["Client A"]["chat_kind"], "personal")
        self.assertEqual(contexts["Project Group"]["chat_kind"], "group")
        self.assertGreater(contexts["Client A"]["sent_by_person_count"], 0)
        self.assertGreater(contexts["Project Group"]["sent_by_person_count"], 0)

    def test_get_or_create_person_reuses_normalized_aliases(self):
        first = poc.get_or_create_person(self.con, "かかむかずや", ["かかむかずや"])
        second = poc.get_or_create_person(self.con, "かかむかずや", ["かかむかずや"])
        candidates = poc.alias_candidate_rows(self.con)
        aliases = [
            row["alias"]
            for row in self.con.execute(
                "SELECT alias FROM person_aliases WHERE person_id = ? ORDER BY alias",
                (first,),
            ).fetchall()
        ]

        self.assertEqual(first, second)
        self.assertEqual(candidates, [])
        self.assertIn("かかむかずや", aliases)
        self.assertIn("かかむかずや", aliases)

    def test_merge_people_moves_aliases_and_removes_duplicate_rows(self):
        first = poc.get_or_create_person(self.con, "かかむかずや", ["かかむかずや"])
        self.con.execute(
            "INSERT INTO people(display_name, canonical_name) VALUES(?, ?)",
            ("かかむかずや", "かかむかずや"),
        )
        second = self.con.execute("SELECT id FROM people WHERE display_name = ?", ("かかむかずや",)).fetchone()["id"]
        self.con.execute(
            "INSERT INTO person_aliases(person_id, alias) VALUES(?, ?)",
            (second, "かかむかずや"),
        )
        self.con.commit()

        result = poc.merge_people(self.con, "かかむかずや", ["かかむかずや"])
        remaining = self.con.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        aliases = [
            row["alias"]
            for row in self.con.execute(
                "SELECT alias FROM person_aliases WHERE person_id = ? ORDER BY alias",
                (result["target_id"],),
            ).fetchall()
        ]

        self.assertEqual(remaining, 1)
        self.assertEqual(result["target_id"], first)
        self.assertIn("かかむかずや", aliases)
        self.assertIn("かかむかずや", aliases)

    def test_people_rows_do_not_duplicate_aliases_when_messages_exist(self):
        result = poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
            [{"display_name": "Client A", "aliases": ["Client A"]}],
        )
        self.assertGreater(result["inserted"], 0)

        rows = {row["display_name"]: row for row in poc.people_rows(self.con)}

        self.assertEqual(rows["Client A"]["aliases"], "Client A")

    def test_set_person_wiki_and_wiki_candidates(self):
        poc.get_or_create_person(self.con, "Client A", ["Client A"])
        result = poc.set_person_wiki(self.con, "Client A", "people/client-a.md")
        rows = poc.wiki_candidate_rows(self.con, min_messages=999)

        self.assertEqual(result["wiki_path"], "people/client-a.md")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["wiki_path"], "people/client-a.md")

    def test_init_db_migrates_existing_chat_metadata_columns(self):
        legacy_db = Path(self.tmp.name) / "legacy.db"
        con = sqlite3.connect(legacy_db)
        con.row_factory = sqlite3.Row
        con.execute(
            """
            CREATE TABLE chats (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_name TEXT NOT NULL UNIQUE,
              chat_kind TEXT NOT NULL DEFAULT 'personal',
              include_for_ai INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.commit()

        poc.init_db(con)
        columns = {row["name"] for row in con.execute("PRAGMA table_info(chats)").fetchall()}
        tables = {
            row["name"]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        con.close()

        self.assertIn("purpose", columns)
        self.assertIn("wiki_path", columns)
        self.assertIn("export_attempts", tables)

    def test_export_helper_matches_nfkc_save_names(self):
        decomposed = "かかむかずや"
        composed = "かかむかずや"

        self.assertEqual(export_helper.navigation_search_text(decomposed), composed)
        self.assertIn("佐藤", export_helper.navigation_search_candidates("インプルーブ（株）佐藤"))
        self.assertIn("塩崎誠", export_helper.navigation_search_candidates("塩崎誠（ザッキー）"))
        self.assertIn("Ayumi", export_helper.navigation_search_candidates("꧁𐬺𐮜𐬺𝔸𝕪𝕦𝕞𝕚𐬺𐮜𐬺꧂"))
        self.assertIn(f"[LINE]{composed}.txt", export_helper.expected_export_file_names(decomposed))
        self.assertTrue(
            export_helper.save_dialog_name_matches(
                f"[LINE]{decomposed}.txt",
                f"[LINE]{composed}",
            )
        )

    def test_health_report_is_redacted_and_counts_messages(self):
        poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )
        report = poc.health_report(self.con)

        self.assertEqual(report["totals"]["chat_count"], 1)
        self.assertEqual(report["totals"]["message_count"], 7)
        self.assertFalse(report["privacy"]["raw_message_bodies_included"])
        self.assertIn("classifications", report)

    def test_validate_config_and_promote_candidates(self):
        config_path = Path(self.tmp.name) / "config.json"
        export_path = self.fixture("sample_line_export_ja.txt")
        config_path.write_text(
            """
            {
              "download_dir": "%s",
              "chats": [
                {
                  "chat_name": "Sample Chat",
                  "chat_kind": "personal",
                  "filename_contains": "sample_line_export_ja",
                  "participants": []
                }
              ]
            }
            """
            % export_path.parent,
            encoding="utf-8",
        )
        validation = poc.validate_config(config_path)
        self.assertEqual(validation["status"], "ok")

        poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            export_path,
        )
        candidates = poc.promote_candidate_rows(self.con, "Sample Chat", 100, redact=True)
        self.assertTrue(candidates)
        self.assertTrue(all(item["body"].startswith("[redacted") for item in candidates))
        review_path = Path(self.tmp.name) / "review.md"
        review = poc.export_promote_review(self.con, review_path, "Sample Chat", 100, redact=True)
        self.assertEqual(review["output"], str(review_path))
        self.assertIn("distilled_fact", review_path.read_text(encoding="utf-8"))

    def test_apply_promote_review_records_reviewed_facts_only(self):
        poc.import_export(
            self.con,
            self.db_path,
            "Sample Chat",
            "personal",
            self.fixture("sample_line_export_ja.txt"),
        )
        ids = [
            row["id"]
            for row in self.con.execute(
                "SELECT id FROM messages WHERE classification = 'message' ORDER BY id LIMIT 3"
            ).fetchall()
        ]
        review_path = Path(self.tmp.name) / "review.md"
        review_path.write_text(
            textwrap.dedent(
                f"""
            # LINE Promote Review

            - [x] message_id: {ids[0]}
              - sent_at: 2026-06-15 14:20:00
              - sender: Client A
              - reasons: todo, deadline
              - body: [redacted len=40]
              - distilled_fact: TODO: Send the revised handout by Friday.
              - promote_to: todos/client-a.md

            - [ ] message_id: {ids[1]}
              - sent_at: 2026-06-15 14:21:00
              - sender: Me
              - reasons: decision
              - body: [redacted len=10]
              - distilled_fact: Decision: Ignore unchecked items.
              - promote_to: decisions/sample.md

            - [x] message_id: {ids[2]}
              - sent_at: 2026-06-15 14:23:00
              - sender: Client A
              - reasons: question
              - body: [redacted len=20]
              - distilled_fact:
              - promote_to: questions/client-a.md
            """
            ),
            encoding="utf-8",
        )

        dry_run = poc.apply_promote_review(self.con, review_path, dry_run=True)
        self.assertEqual(dry_run["applied_count"], 1)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM message_events WHERE event_type = 'promoted'").fetchone()[0],
            0,
        )

        result = poc.apply_promote_review(self.con, review_path)
        promoted = poc.promoted_rows(self.con)
        pending_count = self.con.execute(
            "SELECT COUNT(*) FROM messages WHERE id = ? AND ai_processed = 0",
            (ids[0],),
        ).fetchone()[0]

        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(result["skipped_count"], 2)
        self.assertEqual(promoted[0]["distilled_fact"], "TODO: Send the revised handout by Friday.")
        self.assertEqual(promoted[0]["promote_to"], "todos/client-a.md")
        self.assertEqual(pending_count, 0)


if __name__ == "__main__":
    unittest.main()
