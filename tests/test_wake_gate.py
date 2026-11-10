"""Sweep wake gate (docs/04 queue item 1): gateway/slack_bridge.sweep_should_wake and tools/google_read.changes."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))
sys.path.insert(0, str(ROOT / "tools"))

import google_read  # noqa: E402
import slack_bridge  # noqa: E402

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)


def world(tmp_path: Path, *, swept="2026-11-08T19:00:00+00:00", ok=True, reminders=None) -> Path:
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "last-run.json").write_text(json.dumps({"sweep": {"at": swept, "ok": ok}}), encoding="utf-8")
    if reminders is not None:
        path = tmp_path / "state" / "reminders.yaml"
        path.write_text(reminders, encoding="utf-8")
        old = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc).timestamp()
        os.utime(path, (old, old))  # edited before the last sweep
    return tmp_path


def quiet():
    return {"wake": False, "why": []}


def test_quiet_inbox_sleeps(tmp_path):
    assert slack_bridge.sweep_should_wake(world(tmp_path), NOW, changes=quiet) is False


def test_new_mail_wakes(tmp_path):
    assert slack_bridge.sweep_should_wake(world(tmp_path), NOW, changes=lambda: {"wake": True, "why": ["1 new"]})


def test_fails_open(tmp_path):
    def broken():
        raise RuntimeError("network down")
    assert slack_bridge.sweep_should_wake(world(tmp_path), NOW, changes=broken)
    assert slack_bridge.sweep_should_wake(tmp_path / "nowhere", NOW, changes=quiet)  # no last-run yet
    assert slack_bridge.sweep_should_wake(world(tmp_path / "x", ok=False), NOW, changes=quiet)  # last sweep failed


def test_not_signed_in_wakes(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    assert slack_bridge.sweep_should_wake(world(tmp_path), NOW)


def test_six_hours_without_a_sweep_wakes(tmp_path):
    assert slack_bridge.sweep_should_wake(world(tmp_path, swept="2026-11-08T13:30:00+00:00"), NOW, changes=quiet)


def test_reminder_coming_due_wakes(tmp_path):
    due_soon = "- id: r-1\n  text: call\n  due: \"2026-11-08T21:30:00+00:00\"\n  status: open\n"
    assert slack_bridge.sweep_should_wake(world(tmp_path, reminders=due_soon), NOW, changes=quiet)
    later = due_soon.replace("21:30", "23:30")
    assert slack_bridge.sweep_should_wake(world(tmp_path / "b", reminders=later), NOW, changes=quiet) is False
    done = due_soon.replace("open", "done")
    assert slack_bridge.sweep_should_wake(world(tmp_path / "c", reminders=done), NOW, changes=quiet) is False


def test_reminders_edited_since_last_sweep_wakes(tmp_path):
    root = world(tmp_path, reminders="[]\n")
    os.utime(root / "state" / "reminders.yaml", None)  # touched now, after the 19:00 sweep
    assert slack_bridge.sweep_should_wake(root, NOW, changes=quiet)


# --- google_read.changes --------------------------------------------------------------------------

class FakeGoogle:
    def __init__(self, history="100", added=0, events=0):
        self.history, self.added, self.events, self.calls = history, added, events, []

    def __call__(self, url, token, params=None):
        self.calls.append((url.rsplit("/", 1)[-1], params))
        if url.endswith("/profile"):
            return {"historyId": self.history}
        if url.endswith("/history"):
            return {"history": [{"messagesAdded": [{}] * self.added}]} if self.added else {}
        return {"items": [{}] * self.events}


def test_first_check_sets_cursor_and_wakes(tmp_path):
    cursor = tmp_path / "cursor.json"
    assert google_read.changes(cursor, NOW, get=FakeGoogle(), token="t") == {"wake": True, "why": ["first check"]}
    saved = json.loads(cursor.read_text(encoding="utf-8"))
    assert saved["gmail_history_id"] == "100" and saved["calendar_checked"] == "2026-11-08T20:00:00Z"


def test_unchanged_mailbox_skips_history_call(tmp_path):
    cursor = tmp_path / "cursor.json"
    google_read.changes(cursor, NOW, get=FakeGoogle(), token="t")
    g = FakeGoogle()
    assert google_read.changes(cursor, NOW, get=g, token="t") == {"wake": False, "why": []}
    assert [c[0] for c in g.calls] == ["profile", "events"]


def test_new_inbox_mail_and_calendar_change(tmp_path):
    cursor = tmp_path / "cursor.json"
    google_read.changes(cursor, NOW, get=FakeGoogle(), token="t")
    got = google_read.changes(cursor, NOW, get=FakeGoogle(history="105", added=2, events=1), token="t")
    assert got == {"wake": True, "why": ["2 new in inbox", "1 calendar change"]}


def test_label_only_change_does_not_wake(tmp_path):
    cursor = tmp_path / "cursor.json"
    google_read.changes(cursor, NOW, get=FakeGoogle(), token="t")
    assert google_read.changes(cursor, NOW, get=FakeGoogle(history="101"), token="t")["wake"] is False
    assert json.loads(cursor.read_text(encoding="utf-8"))["gmail_history_id"] == "101"


def test_no_credentials_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    try:
        google_read.access_token()
    except google_read.GoogleError as exc:
        assert exc.code == google_read.NOT_SIGNED_IN
    else:
        raise AssertionError("expected GoogleError")
