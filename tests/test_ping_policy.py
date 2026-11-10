"""Ping rules enforced in code: de-duplication, quiet hours, the daily cap, holding, failure streaks."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import ping_policy  # noqa: E402
from ping_policy import Verdict, decide_sweep, failure_notice, parse_verdict  # noqa: E402

CFG = {"timezone": "America/New_York", "unprompted_pings_per_day": 2, "always_allowed": ["leave_by", "approval_needed", "urgent"]}
NOON = datetime(2026, 11, 9, 12, 0, tzinfo=ZoneInfo("America/New_York"))


def item(i, kind="reply_needed"):
    return {"id": f"m{i}", "kind": kind, "text": f"thing {i}"}


def test_parse_verdict_takes_last_json_with_notify():
    text = 'Did the sweep. {"x": 1}\n{"notify": true, "items": [{"id": "a", "kind": "reminder", "text": "Call mom"}], "hold": []}'
    v = parse_verdict(text)
    assert v.notify and v.items[0]["text"] == "Call mom"


def test_parse_verdict_none_without_verdict():
    assert parse_verdict("NOTHING_TO_REPORT") is None


def test_notify_false_posts_nothing_but_holds(tmp_path):
    v = Verdict(False, hold=[{"kind": "receipt", "text": "Chase receipt"}])
    assert decide_sweep(v, CFG, tmp_path, quiet=False, now=NOON) is None
    assert "Chase receipt" in (tmp_path / "holding.md").read_text(encoding="utf-8")


def test_same_item_is_not_pinged_twice(tmp_path):
    v = Verdict(True, items=[item(1)])
    assert decide_sweep(v, CFG, tmp_path, quiet=False, now=NOON) == "• thing 1"
    assert decide_sweep(v, CFG, tmp_path, quiet=False, now=NOON) is None


def test_quiet_hours_hold_instead_of_ping(tmp_path):
    v = Verdict(True, items=[item(1, "urgent")], urgency="high")
    assert decide_sweep(v, CFG, tmp_path, quiet=True, now=NOON) is None
    assert "quiet hours" in (tmp_path / "holding.md").read_text(encoding="utf-8")


def test_daily_cap_holds_routine_but_not_leave_by(tmp_path):
    for i in range(2):
        assert decide_sweep(Verdict(True, items=[item(i)]), CFG, tmp_path, quiet=False, now=NOON)
    assert decide_sweep(Verdict(True, items=[item(9)]), CFG, tmp_path, quiet=False, now=NOON) is None
    assert "daily cap" in (tmp_path / "holding.md").read_text(encoding="utf-8")
    assert decide_sweep(Verdict(True, items=[item(10, "leave_by")]), CFG, tmp_path, quiet=False, now=NOON) == "• thing 10"


def test_leave_by_does_not_use_the_budget(tmp_path):
    decide_sweep(Verdict(True, items=[item(1, "leave_by")]), CFG, tmp_path, quiet=False, now=NOON)
    assert decide_sweep(Verdict(True, items=[item(2)]), CFG, tmp_path, quiet=False, now=NOON)
    assert decide_sweep(Verdict(True, items=[item(3)]), CFG, tmp_path, quiet=False, now=NOON)


def test_last_ping_kept_for_continuity(tmp_path):
    decide_sweep(Verdict(True, items=[item(1)]), CFG, tmp_path, quiet=False, now=NOON)
    assert "thing 1" in (tmp_path / "sweep-last.md").read_text(encoding="utf-8")


def test_failure_posts_once_per_streak(tmp_path):
    assert failure_notice("sweep", False, "boom", tmp_path).startswith("sweep failed")
    assert failure_notice("sweep", False, "boom", tmp_path) is None
    assert failure_notice("sweep", True, "", tmp_path) is None
    assert failure_notice("sweep", False, "boom again", tmp_path)


def test_models_are_pinned_per_job():
    assert ping_policy.JOB_MODELS["sweep"] == "claude-haiku-5-5"
    assert set(ping_policy.JOB_MODELS) == {"sweep", "morning-brief", "evening-checkin", "weekly-reflection",
                                           "coach-sheet", "handoff"}


def test_due_timers_post_once_and_keep_future(tmp_path):
    import json
    (tmp_path / "timers.json").write_text(json.dumps([
        {"id": "leave-1", "at": "2026-11-09T11:30:00-05:00", "text": "Leave by 11:30"},
        {"id": "leave-2", "at": "2026-11-09T18:00:00-05:00", "text": "Leave by 6"},
        {"id": "bad", "at": "not a time", "text": "x"}]), encoding="utf-8")
    from ping_policy import pop_due_timers
    assert pop_due_timers(tmp_path, CFG, now=NOON) == ["Leave by 11:30"]
    assert pop_due_timers(tmp_path, CFG, now=NOON) == []
    left = json.loads((tmp_path / "timers.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in left] == ["leave-2"]
