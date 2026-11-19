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


def _paths(tmp_path):
    return {"cardio_log": tmp_path / "cardio-log.jsonl", "events": tmp_path / "workout-events.jsonl"}


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
    out = coach_sheet.sync(_plan(tmp_path), fresh=False, runner=runner, **_paths(tmp_path))
    assert writes == [(False, [None]), (True, ["Shin felt fine today, no pain."])]  # dash gone, numbers went first
    assert seen["lean_system"] and seen["model"] == "claude-sonnet-5-5" and "255x5" in seen["prompt"]
    assert out["ok"] and "```\nW2D1\nDeadlift 255x5. Shin felt fine.\n```" in out["message"]
    assert out["message"].startswith("Shin's back")


def test_a_failed_model_call_keeps_the_numbers_and_retries(tmp_path, monkeypatch):
    writes = _fakes(monkeypatch)
    out = coach_sheet.sync(_plan(tmp_path), fresh=False, **_paths(tmp_path),
                           runner=lambda prompt, **kw: SimpleNamespace(is_error=True, text="overloaded"))
    assert writes == [(False, [None])] and not out["ok"]
    assert "try again" in out["message"]


def test_nothing_new_is_silent_and_costs_no_model_call(tmp_path, monkeypatch):
    writes = _fakes(monkeypatch)
    monkeypatch.setattr(coach_sheet.sheets, "write", lambda *a, **k: {"written": 0, "left_alone_where": []})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"tab": "B16", "cells": [], "notes": [], "sessions": [dict(SESSION, new=False)],
                                "issues": []}), encoding="utf-8")
    out = coach_sheet.sync(path, fresh=False, **_paths(tmp_path),
                           runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert out == {"ok": True, "message": None, "written": 0}


def test_issues_and_conflicts_for_the_new_session_are_in_the_message():
    msg = coach_sheet.message([SESSION], {"mn": {}, "coach": {"W2D1": "ok"}, "line": "Done."},
                              {"written": 1, "left_alone_where": ["W2D1 Comp Bench", "W1D3 RDL"]}, None,
                              ["Day 1 week 2: Hip Thrust is logged but not on the sheet", "Day 3 week 1: other"])
    assert "W2D1 Comp Bench" in msg and "W1D3 RDL" not in msg
    assert "Hip Thrust" in msg and "other" not in msg


# --- Phase 1 tightening (2026-11-19): where it went, cardio notes, the after-log hook -------------------------------

def test_the_message_says_where_each_session_went():
    msg = coach_sheet.message([dict(SESSION, week=2, day=1)], {"mn": {}, "coach": {"W2D1": "ok"}, "line": "Done."},
                              {"written": 1, "left_alone_where": []}, None, [])
    assert "Logged as Week 2, Day 1 (2026-11-10)." in msg and "best guess" not in msg


def test_a_best_guess_place_says_so_and_why():
    s = dict(SESSION, label="W1D4", week=1, day=4, guess="your other days are already on Week 2, so ...")
    line = coach_sheet.placement(s)
    assert line.startswith("Logged as Week 1, Day 4 (2026-11-10). That's my best guess: your other days")
    assert "Tell me if it belongs somewhere else." in line
    assert coach_sheet.placement({"label": "W3D2"}) == "Logged as Week 3, Day 2."  # an older plan without week/day


def _cardio_db(tmp_path):
    import hevy_pull
    db = hevy_pull.connect(tmp_path / "h.sqlite")
    walk = {"id": "walk1", "title": "Morning Workout", "start_time": "2026-11-17T12:00:00Z",
            "end_time": "2026-11-17T12:30:00Z", "exercises": [
                {"index": 0, "title": "Treadmill", "notes": "", "sets": [
                    {"index": 0, "type": "normal", "weight_kg": None, "reps": None, "distance_meters": 3218.7,
                     "duration_seconds": 1800}]}]}
    lift = {"id": "lift1", "title": "Forge | B16 | Day 1", "start_time": "2026-11-18T12:00:00Z", "exercises": [
        {"index": 0, "title": "Squat (Barbell)", "notes": "", "sets": [
            {"index": 0, "type": "normal", "weight_kg": 100, "reps": 5}]}]}
    for w in (walk, lift):
        hevy_pull.store(db, w)
    return db


def test_cardio_only_sessions_are_noted_once_and_told_once(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    db, log = _cardio_db(tmp_path), tmp_path / "cardio-log.jsonl"
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    fresh = coach_sheet.note_cardio(db, log, now=now)
    assert [e["id"] for e in fresh] == ["walk1"]  # the lift is not cardio
    assert coach_sheet.cardio_text(fresh[0]) == "treadmill (30 min, 2 mi) on 2026-11-17"
    assert coach_sheet.note_cardio(db, log, now=now) == []  # never twice

    writes = _fakes(monkeypatch)
    out = coach_sheet.sync(_plan(tmp_path), fresh=False, cardio_log=log, events=tmp_path / "ev.jsonl",
                           runner=lambda prompt, **kw: SimpleNamespace(is_error=False, text=json.dumps(
                               {"mn": {"T19": "ok"}, "coach": {"W2D1": "ok"}, "line": "Done."})))
    assert writes and "Kept off the coach's sheet, noted here instead: treadmill (30 min, 2 mi)" in out["message"]
    assert coach_sheet.untold_cardio(log) == []  # mentioned once
    assert json.loads(log.read_text().splitlines()[0])["id"] == "walk1"  # the note itself stays


def test_after_log_writes_one_event_per_workout_and_runs_hooks(tmp_path):
    events, called = tmp_path / "ev.jsonl", []

    class Hook:
        @staticmethod
        def after_log(event):
            called.append(event["label"])
            return "Clips are on their way."

    class Broken:
        @staticmethod
        def after_log(event):
            raise RuntimeError("no videos")

    loader = {"lift_clips": Hook, "broken": Broken}.__getitem__
    s = dict(SESSION, id="w1", week=2, day=1, start="2026-11-10T14:00:00Z", end="2026-11-10T15:10:00Z")
    out = coach_sheet.after_log([s], 16, ["broken", "../evil", "lift_clips"], events, loader)
    assert out == ["Clips are on their way."] and called == ["W2D1"]
    ev = json.loads(events.read_text())
    assert ev["type"] == "workout.logged" and ev["block"] == 16 and ev["end"] == "2026-11-10T15:10:00Z"
    assert coach_sheet.after_log([s], 16, ["lift_clips"], events, loader) == []  # once per workout
    assert called == ["W2D1"] and len(events.read_text().splitlines()) == 1


def test_hooks_wait_until_the_session_is_fully_logged(tmp_path, monkeypatch):
    _fakes(monkeypatch)
    monkeypatch.setattr(coach_sheet.sheets, "config", lambda: {"sheet_id": "S", "after_log": ["lift_clips"]})
    plan = _plan(tmp_path)
    p = json.loads(plan.read_text())
    p["sessions"][0]["id"] = "w1"
    plan.write_text(json.dumps(p))
    loader = lambda name: (_ for _ in ()).throw(AssertionError("not before the notes are in"))  # noqa: E731
    coach_sheet.sync(plan, fresh=False, **_paths(tmp_path), loader=loader,
                     runner=lambda prompt, **kw: SimpleNamespace(is_error=True, text="overloaded"))
    assert not (tmp_path / "workout-events.jsonl").exists()
