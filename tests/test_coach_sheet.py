"""tools/coach_sheet.py offline: the sheet, Google and the model are fakes."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import coach_sheet  # noqa: E402

SESSION = {"label": "W2D1", "date": "2026-11-10", "new": True, "skipped": [], "notes": ["shin ok today"],
           "lifts": [{"sheet": "Comp Deadlift", "hevy": "Deadlift (Barbell)", "sets": "255x5"}]}
NOTE = {"cell": "T19", "day": 1, "week": 2, "exercise": "Comp Deadlift", "have": "", "coach": "", "mn": None,
        "raw": ["shin ok today"]}


def _plan(tmp_path, **extra):
    p = {"tab": "B16", "cells": [], "notes": [dict(NOTE)], "sessions": [dict(SESSION)], "issues": [], **extra}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(p), encoding="utf-8")
    return path


def _fakes(monkeypatch):
    writes = []

    def write(plan, sid, token, notes=True, env=None, **kw):
        assert env == {"COORDINATOR_UNATTENDED": "1"}  # Juno's own rules: auto setting, no repairs
        writes.append((notes, [n.get("mn") for n in plan["notes"]]))
        return {"written": 2 if not notes else 1, "left_alone_where": []}
    monkeypatch.setattr(coach_sheet.sheets, "config", lambda: {"sheet_id": "S"})
    monkeypatch.setattr(coach_sheet.google_read, "access_token", lambda: "t")
    monkeypatch.setattr(coach_sheet.sheets, "write", write)
    return writes


def test_numbers_first_then_one_lean_call_for_the_words(tmp_path, monkeypatch):
    writes, seen = _fakes(monkeypatch), {}

    def runner(prompt, **kw):
        seen.update(kw, prompt=prompt)
        return SimpleNamespace(is_error=False, text=json.dumps({
            "mn": {"T19": "Shin felt fine today — no pain."}, "coach": {"W2D1": "Deadlift 255x5. Shin felt fine."},
            "line": "Shin's back on speaking terms. \U0001fae1"}))
    out = coach_sheet.sync(_plan(tmp_path), fresh=False, runner=runner)
    assert writes == [(False, [None]), (True, ["Shin felt fine today, no pain."])]  # dash gone, numbers went first
    assert seen["lean_system"] and seen["model"] == "claude-sonnet-5-5" and "255x5" in seen["prompt"]
    assert out["ok"] and "```\nW2D1\nDeadlift 255x5. Shin felt fine.\n```" in out["message"]
    assert out["message"].startswith("Shin's back")


def test_a_failed_model_call_keeps_the_numbers_and_retries(tmp_path, monkeypatch):
    writes = _fakes(monkeypatch)
    out = coach_sheet.sync(_plan(tmp_path), fresh=False,
                           runner=lambda prompt, **kw: SimpleNamespace(is_error=True, text="overloaded"))
    assert writes == [(False, [None])] and not out["ok"]
    assert "try again" in out["message"]


def test_nothing_new_is_silent_and_costs_no_model_call(tmp_path, monkeypatch):
    writes = _fakes(monkeypatch)
    monkeypatch.setattr(coach_sheet.sheets, "write", lambda *a, **k: {"written": 0, "left_alone_where": []})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"tab": "B16", "cells": [], "notes": [], "sessions": [dict(SESSION, new=False)],
                                "issues": []}), encoding="utf-8")
    out = coach_sheet.sync(path, fresh=False, runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert out == {"ok": True, "message": None, "written": 0}


def test_issues_and_conflicts_for_the_new_session_are_in_the_message():
    msg = coach_sheet.message([SESSION], {"mn": {}, "coach": {"W2D1": "ok"}, "line": "Done."},
                              {"written": 1, "left_alone_where": ["W2D1 Comp Bench", "W1D3 RDL"]}, None,
                              ["Day 1 week 2: Hip Thrust is logged but not on the sheet", "Day 3 week 1: other"])
    assert "W2D1 Comp Bench" in msg and "W1D3 RDL" not in msg
    assert "Hip Thrust" in msg and "other" not in msg
