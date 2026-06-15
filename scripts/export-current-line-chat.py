#!/usr/bin/env python3
"""Best-effort helper to export the currently open LINE desktop chat.

This intentionally starts as a semi-automatic helper. Open the target
chat in LINE, then this script tries known menu labels and waits for a new
[LINE]*.txt export to appear in Downloads.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
import re
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_DIR / "config.local.json"
DEFAULT_DB = Path(os.environ.get("LOCAL_CHAT_MEMORY_DB", PROJECT_DIR / "data" / "local-chat-memory.db"))
DOWNLOADS = Path("~/Downloads").expanduser()


APPLE_SCRIPT = r'''
on clickTargetMenuItem()
  set targetNames to {"トーク履歴を保存", "トーク履歴を保存...", "トークを保存", "トークを保存...", "Save Chat", "Save Chat...", "Export Chat", "Export Chat...", "Export Chat History", "Export Chat History..."}
  tell application "LINE" to activate
  delay 0.8
  tell application "System Events"
    if not (exists process "LINE") then error "LINE process is not running"
    tell process "LINE"
      set frontmost to true
      delay 0.5
      repeat with barItem in menu bar items of menu bar 1
        try
          click barItem
          delay 0.2
          repeat with item1 in menu items of menu 1 of barItem
            try
              if (name of item1) is in targetNames then
                click item1
                return "clicked menu item: " & (name of item1)
              end if
              if exists menu 1 of item1 then
                repeat with item2 in menu items of menu 1 of item1
                  try
                    if (name of item2) is in targetNames then
                      click item2
                      return "clicked submenu item: " & (name of item2)
                    end if
                  end try
                end repeat
              end if
            end try
          end repeat
        end try
      end repeat
    end tell
  end tell
  return "not_found"
end clickTargetMenuItem

clickTargetMenuItem()
'''


def line_exports(download_dir: Path) -> dict[Path, float]:
    return {
        path: path.stat().st_mtime
        for path in download_dir.glob("[[]LINE[]]*.txt")
        if path.is_file()
    }


def run_osascript() -> str:
    proc = subprocess.run(
        ["osascript", "-e", APPLE_SCRIPT],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout.strip()


def run_script(script: str, timeout: int = 5) -> str:
    proc = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout.strip()


def apple_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def get_line_window_frame() -> tuple[int, int, int, int]:
    script = r'''
tell application "LINE" to activate
delay 0.3
tell application "System Events"
  tell process "LINE"
    repeat with w in windows
      try
        set value of attribute "AXMinimized" of w to false
      end try
    end repeat
    set frontmost to true
    set bestWindow to missing value
    set bestArea to 0
    repeat with candidateWindow in windows
      try
        set candidateSize to size of candidateWindow
        set candidateWidth to item 1 of candidateSize
        set candidateHeight to item 2 of candidateSize
        set candidateArea to candidateWidth * candidateHeight
        if candidateWidth > 500 and candidateHeight > 300 and candidateArea > bestArea then
          set bestWindow to candidateWindow
          set bestArea to candidateArea
        end if
      end try
    end repeat
    if bestWindow is missing value then set bestWindow to window 1
    set w to bestWindow
    set p to position of w
    set s to size of w
    return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
  end tell
end tell
'''
    raw = run_script(script)
    x, y, w, h = [int(part) for part in raw.split(",")]
    return x, y, w, h


def press_key_code(key_code: int, repeat: int = 1) -> None:
    script = "\n".join([f'tell application "System Events" to key code {key_code}' for _ in range(repeat)])
    run_script(script)


def paste_text(value: str) -> None:
    script = f'''
set savedClipboard to the clipboard
set the clipboard to {apple_quote(value)}
tell application "System Events"
  keystroke "a" using command down
  delay 0.1
  keystroke "v" using command down
end tell
delay 0.1
set the clipboard to savedClipboard
'''
    run_script(script)


def focused_element_info(retries: int = 3, delay: float = 0.2) -> dict[str, object]:
    script = r'''
tell application "System Events"
  tell process "LINE"
    try
      set focusedElement to value of attribute "AXFocusedUIElement"
      if focusedElement is missing value then return "missing|0,0,0,0"
      set p to position of focusedElement
      set s to size of focusedElement
      return ((role of focusedElement) as text) & "|" & (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
    on error errMsg
      return "error:" & errMsg & "|0,0,0,0"
    end try
  end tell
end tell
'''
    last_info: dict[str, object] | None = None
    for attempt in range(max(1, retries)):
        raw = run_script(script)
        role, frame = raw.split("|", 1)
        x, y, width, height = [int(part) for part in frame.split(",")]
        info = {"role": role, "x": x, "y": y, "width": width, "height": height}
        last_info = info
        if role not in {"missing"} and not role.startswith("error:"):
            return info
        if attempt + 1 < retries:
            time.sleep(delay)
    return last_info or {"role": "missing", "x": 0, "y": 0, "width": 0, "height": 0}


def is_search_field_focus(window_frame: tuple[int, int, int, int], focus: dict[str, object]) -> bool:
    win_x, win_y, win_w, _win_h = window_frame
    fx = int(focus["x"])
    fy = int(focus["y"])
    fw = int(focus["width"])
    fh = int(focus["height"])
    return (
        focus["role"] == "AXTextField"
        and win_x + 40 <= fx <= win_x + min(390, win_w // 2)
        and win_y + 45 <= fy <= win_y + 130
        and fw >= 150
        and 20 <= fh <= 60
    )


def is_save_dialog_name_focus(window_frame: tuple[int, int, int, int], focus: dict[str, object]) -> bool:
    win_x, win_y, _win_w, _win_h = window_frame
    fx = int(focus["x"])
    fy = int(focus["y"])
    fw = int(focus["width"])
    fh = int(focus["height"])
    return (
        focus["role"] == "AXTextField"
        and win_x + 220 <= fx <= win_x + 360
        and win_y + 130 <= fy <= win_y + 230
        and fw >= 180
        and 20 <= fh <= 40
    )


def is_left_pane_list_focus(window_frame: tuple[int, int, int, int], focus: dict[str, object]) -> bool:
    win_x, _win_y, win_w, _win_h = window_frame
    fx = int(focus["x"])
    return focus["role"] == "AXList" and win_x <= fx <= win_x + min(390, win_w // 2)


def navigation_search_text(target: str) -> str:
    return unicodedata.normalize("NFKC", target)


def navigation_search_candidates(target: str) -> list[str]:
    normalized = navigation_search_text(target)
    candidates = [normalized]
    if "）" in normalized:
        tail = normalized.rsplit("）", 1)[-1].strip()
        if tail:
            candidates.append(tail)
    if ")" in normalized:
        before = normalized.split("(", 1)[0].strip() if "(" in normalized else ""
        inside = normalized.split("(", 1)[-1].split(")", 1)[0].strip() if "(" in normalized else ""
        tail = normalized.rsplit(")", 1)[-1].strip()
        for value in [before, inside]:
            if value:
                candidates.append(value)
        if tail:
            candidates.append(tail)
    if "株式会社" in normalized:
        before, after = normalized.split("株式会社", 1)
        for value in [before.strip(), after.strip()]:
            if value:
                candidates.append(value)
    parts = normalized.split()
    if len(parts) > 1:
        candidates.append(" ".join(parts[1:]))
        candidates.append(parts[-1])
    ascii_words = re.findall(r"[A-Za-z0-9]+", normalized)
    for word in ascii_words:
        if len(word) >= 2:
            candidates.append(word)
    return list(dict.fromkeys(candidates))


def navigate_to_chat(target: str, open_first_result: bool = False) -> dict[str, object]:
    if not shutil.which("cliclick"):
        return {"status": "navigate_unavailable_no_cliclick", "target": target}
    frame = get_line_window_frame()
    x, y, _width, _height = frame
    if _width < 500 or _height < 300:
        return {"status": "line_main_window_not_found", "target": target, "window_frame": frame}
    # Verified on the current LINE for macOS build: search field sits near the
    # top-left of the main LINE window. The AX focused-frame check below is the
    # safety gate; if focus is not the search field, no text is pasted.
    search_x = x + 200
    search_y = y + 85
    last_failure: dict[str, object] | None = None
    for search_text in navigation_search_candidates(target):
        subprocess.run(["cliclick", f"c:{search_x},{search_y}"], check=False)
        time.sleep(0.3)
        focus = focused_element_info()
        if not is_search_field_focus(frame, focus):
            return {"status": "search_focus_not_verified", "target": target, "window_frame": frame, "focused": focus}
        paste_text(search_text)
        time.sleep(1.0)
        focus_after_paste = focused_element_info()
        if not is_search_field_focus(frame, focus_after_paste):
            return {
                "status": "search_focus_lost_after_paste",
                "target": target,
                "search_text": search_text,
                "window_frame": frame,
                "focused": focus_after_paste,
            }
        if open_first_result:
            result_x = x + 165
            result_y = y + 155
            subprocess.run(["cliclick", f"c:{result_x},{result_y}"], check=False)
            time.sleep(1.0)
            focus_after_result_click = focused_element_info()
            if is_search_field_focus(frame, focus_after_result_click):
                last_failure = {
                    "status": "result_click_did_not_leave_search",
                    "target": target,
                    "search_text": search_text,
                    "window_frame": frame,
                    "focused_before_paste": focus,
                    "focused_after_paste": focus_after_paste,
                    "focused_after_result_click": focus_after_result_click,
                }
                continue
            if is_left_pane_list_focus(frame, focus_after_result_click):
                last_failure = {
                    "status": "result_click_stayed_in_left_list",
                    "target": target,
                    "search_text": search_text,
                    "window_frame": frame,
                    "focused_before_paste": focus,
                    "focused_after_paste": focus_after_paste,
                    "focused_after_result_click": focus_after_result_click,
                }
                continue
        else:
            focus_after_result_click = None
        return {
            "status": "opened_first_result" if open_first_result else "search_filled",
            "target": target,
            "search_text": search_text,
            "search_candidates": navigation_search_candidates(target),
            "window_frame": frame,
            "focused_before_paste": focus,
            "focused_after_paste": focus_after_paste,
            "focused_after_result_click": focus_after_result_click,
        }
    return last_failure or {"status": "navigation_failed_no_candidates", "target": target, "window_frame": frame}


def backup_existing_download_export(download_dir: Path, chat_name: str) -> str | None:
    source = download_dir / f"[LINE]{chat_name}.txt"
    if not source.exists():
        return None
    backup_dir = PROJECT_DIR / "var" / "export-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{source.stem}-{datetime_suffix()}{source.suffix}"
    shutil.move(str(source), str(target))
    return str(target)


def restore_backup_download_export(backup_path: str | None, download_dir: Path, chat_name: str) -> str | None:
    if not backup_path:
        return None
    backup = Path(backup_path)
    destination = download_dir / f"[LINE]{chat_name}.txt"
    if not backup.exists() or destination.exists():
        return None
    shutil.move(str(backup), str(destination))
    return str(destination)


def cancel_blocking_line_dialog_if_present() -> str | None:
    script = r'''
tell application "System Events"
  tell process "LINE"
    repeat with w in windows
      try
        if (exists button "置き換え" of w) and (exists button "キャンセル" of w) then
          click button "キャンセル" of w
          return "replace_confirmation_cancelled"
        end if
        if (exists button "保存" of w) and (exists button "キャンセル" of w) then
          click button "キャンセル" of w
          return "save_dialog_cancelled"
        end if
      end try
    end repeat
  end tell
end tell
return ""
'''
    try:
        result = run_script(script)
    except Exception:
        return None
    return result or None


def save_dialog_file_name() -> str | None:
    script = r'''
tell application "System Events"
  tell process "LINE"
    try
      set focusedElement to value of attribute "AXFocusedUIElement"
      if focusedElement is not missing value and (role of focusedElement as text) is "AXTextField" then
        set focusedValue to value of focusedElement as text
        if focusedValue starts with "[LINE]" then return focusedValue
      end if
    end try
    repeat with w in windows
      try
        if (exists button "保存" of w) and (exists text field 1 of w) then
          return value of text field 1 of w as text
        end if
      end try
      try
        if (exists sheet 1 of w) then
          set sheetElement to sheet 1 of w
          if (exists text field 1 of sheetElement) then
            return value of text field 1 of sheetElement as text
          end if
        end if
      end try
    end repeat
  end tell
end tell
return ""
'''
    try:
        result = run_script(script)
    except Exception:
        return None
    return result or None


def cancel_save_dialog_if_present() -> str | None:
    script = r'''
tell application "System Events"
  tell process "LINE"
    repeat with w in windows
      try
        if (exists button "保存" of w) and (exists button "キャンセル" of w) then
          click button "キャンセル" of w
          return "save_dialog_cancelled"
        end if
      end try
    end repeat
  end tell
end tell
return ""
'''
    try:
        result = run_script(script)
    except Exception:
        return None
    return result or None


def handle_replace_confirmation(auto_replace: bool) -> str | None:
    script = f'''
tell application "System Events"
  tell process "LINE"
    repeat with w in windows
      try
        if (exists button "置き換え" of w) and (exists button "キャンセル" of w) then
          if {str(auto_replace).lower()} then
            click button "置き換え" of w
            return "replace_confirmation_accepted"
          else
            click button "キャンセル" of w
            return "replace_confirmation_cancelled"
          end if
        end if
      end try
    end repeat
  end tell
end tell
return ""
'''
    try:
        result = run_script(script)
    except Exception:
        return None
    return result or None


def expected_save_dialog_name(chat_name: str) -> str:
    return f"[LINE]{unicodedata.normalize('NFKC', chat_name)}"


def expected_export_file_names(chat_name: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", chat_name)
    return {f"[LINE]{chat_name}.txt", f"[LINE]{normalized}.txt"}


def save_dialog_name_matches(actual: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not actual:
        return False
    actual_candidates = {actual, unicodedata.normalize("NFKC", actual)}
    expected_candidates = {
        expected,
        f"{expected}.txt",
        unicodedata.normalize("NFKC", expected),
        f"{unicodedata.normalize('NFKC', expected)}.txt",
    }
    return bool(actual_candidates & expected_candidates)


def run_right_menu_fallback(expected_name: str | None = None) -> str:
    if not shutil.which("cliclick"):
        return "right_menu_unavailable_no_cliclick"
    cancelled = cancel_blocking_line_dialog_if_present()
    if cancelled:
        return cancelled
    x, y, width, _height = get_line_window_frame()
    # LINE's chat menu is the vertical-ellipsis button near the right edge of the chat header.
    menu_x = x + width - 22
    menu_y = y + 83
    subprocess.run(["cliclick", f"c:{menu_x},{menu_y}"], check=False)
    time.sleep(0.4)
    # Current LINE for macOS renders the menu to the right of the window. Click
    # the visible "トークを保存" row directly instead of using fragile arrow-key counts.
    save_item_x = x + width + 48
    save_item_y = y + 327
    subprocess.run(["cliclick", f"c:{save_item_x},{save_item_y}"], check=False)
    time.sleep(0.8)
    try:
        focus = focused_element_info()
    except Exception:
        focus = None
    if focus and is_save_dialog_name_focus((x, y, width, _height), focus):
        actual_name = save_dialog_file_name()
        if not save_dialog_name_matches(actual_name, expected_name):
            cancelled = cancel_save_dialog_if_present()
            return f"unexpected_save_dialog_name: expected={expected_name}; actual={actual_name}; {cancelled or 'save_dialog_not_cancelled'}"
        save_button_x = x + 480
        save_button_y = y + 304
        subprocess.run(["cliclick", f"c:{save_button_x},{save_button_y}"], check=False)
        time.sleep(0.5)
        replace_result = handle_replace_confirmation(auto_replace=expected_name is not None)
        if replace_result:
            return f"clicked right menu item: トークを保存; clicked save dialog default; {replace_result}"
        return "clicked right menu item: トークを保存; clicked save dialog default"
    return "clicked right menu item: トークを保存"


def scan_after(config: Path, auto_discover: bool) -> list[dict]:
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "line_history_poc.py"),
        "scan-downloads",
        "--config",
        str(config),
    ]
    if auto_discover:
        cmd.append("--auto-discover")
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def ensure_export_attempts_table(con: sqlite3.Connection) -> None:
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
    con.commit()


def load_db_targets(
    db_path: Path,
    chat_kind: str | None = None,
    skip_success_within_hours: float = 0,
) -> list[dict[str, object]]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        ensure_export_attempts_table(con)
        where = ["include_for_ai = 1"]
        params: list[object] = []
        if chat_kind:
            where.append("chat_kind = ?")
            params.append(chat_kind)
        if skip_success_within_hours > 0:
            where.append(
                """
                NOT EXISTS (
                  SELECT 1
                  FROM export_attempts recent
                  WHERE recent.chat_id = chats.id
                    AND recent.status = 'export_triggered'
                    AND recent.started_at >= datetime('now', ?)
                )
                """
            )
            params.append(f"-{skip_success_within_hours:g} hours")
        rows = con.execute(
            f"""
            SELECT
              chats.chat_name,
              chats.chat_kind,
              chats.purpose,
              chats.wiki_path,
              (
                SELECT MAX(started_at)
                FROM export_attempts
                WHERE export_attempts.chat_id = chats.id
                  AND export_attempts.status = 'export_triggered'
              ) AS last_success_at,
              (
                SELECT MAX(started_at)
                FROM export_attempts
                WHERE export_attempts.chat_id = chats.id
              ) AS last_attempt_at
            FROM chats
            WHERE {' AND '.join(where)}
            ORDER BY
              CASE WHEN last_success_at IS NULL THEN 0 ELSE 1 END,
              COALESCE(last_success_at, ''),
              chats.chat_name
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def record_export_attempt(
    db_path: Path,
    chat: dict[str, object] | None,
    mode: str,
    status: str,
    started_at_epoch: float,
    payload: dict[str, object],
) -> None:
    if not chat or not db_path.exists():
        return
    chat_name = str(chat["chat_name"])
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        ensure_export_attempts_table(con)
        chat_row = con.execute("SELECT id FROM chats WHERE chat_name = ?", (chat_name,)).fetchone()
        chat_id = int(chat_row["id"]) if chat_row else None
        started_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at_epoch))
        finished_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        con.execute(
            """
            INSERT INTO export_attempts(chat_id, target_name, mode, status, started_at, finished_at, result_json)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                chat_name,
                mode,
                status,
                started_at,
                finished_at,
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )
        con.commit()
    finally:
        con.close()


def load_db_target(db_path: Path, chat_name: str) -> dict[str, object] | None:
    if not db_path.exists():
        return None
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            SELECT chat_name, chat_kind, purpose, wiki_path
            FROM chats
            WHERE chat_name = ?
            LIMIT 1
            """,
            (chat_name,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def direct_import(db_path: Path, chat: dict[str, object], file_path: Path) -> dict:
    chat_name = str(chat["chat_name"])
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "line_history_poc.py"),
        "--db",
        str(db_path),
        "import",
        "--chat",
        chat_name,
        "--chat-kind",
        str(chat.get("chat_kind") or "personal"),
        "--file",
        str(file_path),
        "--participant",
        chat_name,
        "--participant",
        "Me",
    ]
    if chat.get("purpose"):
        cmd.extend(["--purpose", str(chat["purpose"])])
    if chat.get("wiki_path"):
        cmd.extend(["--wiki-path", str(chat["wiki_path"])])
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def export_one(
    chat: dict[str, object] | None,
    download_dir: Path,
    timeout: int,
    db_path: Path,
    scan_current_after: bool,
    config: Path,
    auto_discover: bool,
    open_first_result: bool = False,
    navigate_only: bool = False,
) -> dict[str, object]:
    started_at_epoch = time.time()
    before = line_exports(download_dir)
    navigation_result = None
    backup_path = None
    cancelled = cancel_blocking_line_dialog_if_present()
    if cancelled:
        payload = {"status": "blocked_dialog_cancelled", "ui_result": cancelled, "target": chat["chat_name"] if chat else None}
        record_export_attempt(db_path, chat, "target-ui", str(payload["status"]), started_at_epoch, payload)
        return payload
    if chat:
        chat_name = str(chat["chat_name"])
        if not open_first_result:
            payload = {
                "status": "needs_user_open_target",
                "target": chat_name,
                "note": "Target mode will not type into LINE unless --open-first-result is set.",
            }
            record_export_attempt(db_path, chat, "target-ui", str(payload["status"]), started_at_epoch, payload)
            return payload
        navigation_result = navigate_to_chat(chat_name, open_first_result)
        if navigation_result["status"] not in {"opened_first_result", "search_filled"}:
            payload = {"status": "navigation_failed", "target": chat_name, "navigation_result": navigation_result}
            record_export_attempt(db_path, chat, "target-ui", str(payload["status"]), started_at_epoch, payload)
            return payload
        if navigate_only:
            payload = {"status": "navigated_only", "target": chat_name, "navigation_result": navigation_result}
            record_export_attempt(db_path, chat, "target-ui", str(payload["status"]), started_at_epoch, payload)
            return payload
        backup_path = backup_existing_download_export(download_dir, chat_name)

    if chat:
        result = run_right_menu_fallback(expected_save_dialog_name(str(chat["chat_name"])))
    else:
        result = run_osascript()
        if result == "not_found":
            result = run_right_menu_fallback()

    deadline = time.time() + timeout
    new_files: list[Path] = []
    while time.time() < deadline:
        after = line_exports(download_dir)
        candidates = [path for path, mtime in after.items() if path not in before or mtime > before[path]]
        if candidates:
            new_files = sorted(candidates, key=lambda p: p.stat().st_mtime)
            break
        time.sleep(2)

    payload: dict[str, object] = {
        "status": "export_triggered" if new_files else "needs_manual_export",
        "target": chat["chat_name"] if chat else None,
        "navigation_result": navigation_result,
        "backed_up_existing_export": backup_path,
        "ui_result": result,
        "new_files": [str(path) for path in new_files],
    }
    if chat and new_files:
        expected_names = expected_export_file_names(str(chat["chat_name"]))
        exported_file = new_files[-1]
        if exported_file.name not in expected_names:
            payload["status"] = "exported_unexpected_chat_file"
            payload["expected_file_names"] = sorted(expected_names)
            payload["actual_file_name"] = exported_file.name
            payload["import_skipped"] = True
        else:
            payload["import_result"] = direct_import(db_path, chat, exported_file)
    elif chat and not new_files:
        restored = restore_backup_download_export(backup_path, download_dir, str(chat["chat_name"]))
        if restored:
            payload["restored_existing_export"] = restored
    elif scan_current_after and new_files:
        payload["scan_results"] = scan_after(config.expanduser(), auto_discover)
    record_export_attempt(db_path, chat, "target-ui" if chat else "current-chat", str(payload["status"]), started_at_epoch, payload)
    return payload


def export_targets(
    targets: list[dict[str, object]],
    download_dir: Path,
    timeout: int,
    db_path: Path,
    config: Path,
    auto_discover: bool,
    open_first_result: bool,
    navigate_only: bool,
    pause_between: float,
    continue_on_error: bool,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    stopped_after_failure = False
    success_statuses = {"export_triggered", "navigated_only"}
    for index, target in enumerate(targets, start=1):
        result = export_one(
            target,
            download_dir,
            timeout,
            db_path,
            False,
            config,
            auto_discover,
            open_first_result,
            navigate_only,
        )
        result["batch_index"] = index
        results.append(result)
        if result.get("status") not in success_statuses and not continue_on_error:
            stopped_after_failure = True
            break
        if index < len(targets) and pause_between > 0:
            time.sleep(pause_between)
    return {
        "status": "batch_completed" if not stopped_after_failure else "batch_stopped_after_failure",
        "target_count": len(targets),
        "attempted_count": len(results),
        "stopped_after_failure": stopped_after_failure,
        "results": results,
    }


def datetime_suffix() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-dir", type=Path, default=DOWNLOADS)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--scan-after", action="store_true", help="Run scan-downloads after an export appears")
    parser.add_argument("--auto-discover", action="store_true", help="Auto-discover new [LINE]*.txt chats during scan-after")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target", action="append", default=[], help="Search this LINE chat name, export it, then import directly. Repeatable.")
    parser.add_argument("--from-db", action="store_true", help="Use already registered DB chats as the export target list")
    parser.add_argument("--chat-kind", choices=["personal", "group", "official"], help="Filter --from-db targets by chat kind")
    parser.add_argument("--exclude", action="append", default=["Keepメモ"], help="Exclude an exact target name from --from-db. Repeatable.")
    parser.add_argument("--limit", type=int, help="Limit target count for staged tests")
    parser.add_argument("--max-automated-targets", type=int, default=3, help="Safety cap for UI-operated target exports unless --allow-large-batch is set")
    parser.add_argument("--allow-large-batch", action="store_true", help="Allow more than --max-automated-targets UI-operated targets")
    parser.add_argument(
        "--skip-success-within-hours",
        type=float,
        default=0,
        help="With --from-db, skip targets whose last successful export attempt is newer than this many hours.",
    )
    parser.add_argument("--pause-between", type=float, default=2.0, help="Seconds to pause between target exports")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue the target batch after a failed export")
    parser.add_argument(
        "--open-first-result",
        action="store_true",
        help="After verifying focus is on LINE's search field, click the first search result.",
    )
    parser.add_argument("--navigate-only", action="store_true", help="Only verify search focus and open the target; do not export")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be attempted")
    args = parser.parse_args(argv)

    download_dir = args.download_dir.expanduser()
    targets: list[dict[str, object]] = []
    if args.from_db:
        excluded = set(args.exclude or [])
        targets.extend(
            [
                row
                for row in load_db_targets(args.db.expanduser(), args.chat_kind, args.skip_success_within_hours)
                if row["chat_name"] not in excluded
            ]
        )
    for target in args.target:
        existing_target = load_db_target(args.db.expanduser(), target)
        targets.append(
            existing_target
            or {
                "chat_name": target,
                "chat_kind": "personal",
                "purpose": "manual LINE export target",
                "wiki_path": None,
            }
        )
    if args.limit is not None:
        targets = targets[: args.limit]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "download_dir": str(download_dir),
                    "existing_line_exports": len(line_exports(download_dir)),
                    "target_count": len(targets),
                    "targets": targets,
                    "note": "Without --target/--from-db, open the target LINE chat manually before rerunning.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if targets:
        if args.open_first_result:
            if len(targets) > args.max_automated_targets and not args.allow_large_batch:
                payload = {
                    "status": "batch_requires_smaller_limit",
                    "target_count": len(targets),
                    "max_automated_targets": args.max_automated_targets,
                    "safe_next_step": f"Rerun with --limit {args.max_automated_targets} for staged testing, or pass --allow-large-batch after small batches are proven stable.",
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 2
            payload = export_targets(
                targets,
                download_dir,
                args.timeout,
                args.db.expanduser(),
                args.config,
                args.auto_discover,
                args.open_first_result,
                args.navigate_only,
                args.pause_between,
                args.continue_on_error,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if all(item.get("status") in {"export_triggered", "navigated_only"} for item in payload["results"]) else 3
        payload = {
            "status": "target_queue_ready",
            "target_count": len(targets),
            "targets": targets,
            "safe_next_step": "Open one target chat manually in LINE, then run scripts/export-current-line-chat.py --scan-after --auto-discover. For controlled testing, use --target NAME --open-first-result --navigate-only first.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    payload = export_one(None, download_dir, args.timeout, args.db.expanduser(), args.scan_after, args.config, args.auto_discover)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("new_files") else 3


if __name__ == "__main__":
    raise SystemExit(main())
