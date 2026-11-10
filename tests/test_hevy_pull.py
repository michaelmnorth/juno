"""tools/hevy_pull.py offline: Hevy is a fake that serves pages."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import hevy_pull  # noqa: E402

NOW = datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc)


def _workout(wid: str, start: str, sets: list[tuple], title: str = "Lower") -> dict:
    return {"id": wid, "title": title, "start_time": start, "end_time": start, "updated_at": start,
            "exercises": [{"index": 0, "title": "Squat (Barbell)", "exercise_template_id": "T1",
                           "sets": [{"index": i, "type": t, "weight_kg": kg, "reps": r}
                                    for i, (t, kg, r) in enumerate(sets)]}]}


class Fake:
    def __init__(self, pages: dict):
        self.pages, self.calls = pages, []

    def __call__(self, path, key, params):
        self.calls.append((path, params))
        return self.pages[path][params["page"] - 1]


@pytest.fixture
def db(tmp_path):
    return hevy_pull.connect(tmp_path / "health.sqlite")


def test_first_pull_takes_every_page_then_events(db, tmp_path):
    cursor = tmp_path / "cursor.json"
    first = Fake({"workouts": [
        {"page_count": 2, "workouts": [_workout("w1", "2026-11-03T14:00:00Z", [("normal", 120, 5)])]},
        {"page_count": 2, "workouts": [_workout("w2", "2026-11-06T14:00:00Z", [("normal", 125, 3)])]}]})
    assert hevy_pull.pull(db, "k", cursor, first, NOW) == {"added": 2, "updated": 0, "deleted": 0}
    assert [c[1]["page"] for c in first.calls] == [1, 2]
    later = Fake({"workouts/events": [{"page_count": 1, "events": [
        {"type": "updated", "workout": _workout("w2", "2026-11-06T14:00:00Z", [("normal", 130, 3)])},
        {"type": "deleted", "id": "w1"},
        {"type": "updated", "workout": _workout("w3", "2026-11-08T14:00:00Z", [("normal", 100, 8)])}]}]})
    assert hevy_pull.pull(db, "k", cursor, later, NOW) == {"added": 1, "updated": 1, "deleted": 1}
    assert later.calls[0][1]["since"] == "2026-11-09T02:00:00Z"
    assert db.execute("SELECT count(*) FROM hevy_sets WHERE workout_id = 'w1'").fetchone()[0] == 0
    assert db.execute("SELECT weight_kg FROM hevy_sets WHERE workout_id = 'w2'").fetchone()[0] == 130


def test_summary_skips_warmups_and_reports_pounds(db):
    hevy_pull.store(db, _workout("w1", "2026-11-05T14:00:00Z",
                                 [("warmup", 140, 1), ("normal", 120, 5), ("normal", 125, 3), ("normal", 100, 12)]))
    out = hevy_pull.summary(db, 7, NOW)
    squat = out["exercises"][0]
    assert out["sessions"] == 1 and squat["sets"] == 3
    assert squat["top_set"] == "275x3"  # 125 kg = 275.6 lb, nearest 5
    assert squat["e1rm_lb"] == round(hevy_pull.epley(120, 5) * hevy_pull.LB)  # 12-rep set not used for 1RM


def test_lift_groups_by_week(db):
    hevy_pull.store(db, _workout("w1", "2026-10-27T14:00:00Z", [("normal", 120, 5)]))
    hevy_pull.store(db, _workout("w2", "2026-11-04T14:00:00Z", [("normal", 125, 5)]))
    out = hevy_pull.lift(db, "squat", 4, NOW)
    assert [w["week_of"] for w in out["weeks"]] == ["2026-10-26", "2026-11-02"]
    assert out["matched"] == ["Squat (Barbell)"]


def test_no_key_is_a_clear_exit(monkeypatch):
    monkeypatch.delenv("HEVY_API_KEY", raising=False)
    monkeypatch.setattr(hevy_pull.google_read, "_token_store", lambda: (_ for _ in ()).throw(
        hevy_pull.HevyError(hevy_pull.NO_KEY, "no key")))
    with pytest.raises(hevy_pull.HevyError) as err:
        hevy_pull.api_key()
    assert err.value.code == hevy_pull.NO_KEY


def test_rounding_is_nearest_five_ties_up():
    assert [hevy_pull._lb5(lb / hevy_pull.LB) for lb in (132.4, 132.5, 137.5, 135)] == [130, 135, 140, 135]


def test_check_reads_only_safe_fields():
    out = hevy_pull.check("k", lambda path, key, params: {"data": {"username": "michaelmnorth", "is_pro": True,
                                                                     "weight_unit": "lb", "id": "x", "url": "u"}})
    assert out == {"username": "michaelmnorth", "is_pro": True, "weight_unit": "lb", "distance_unit": None}


def test_exact_lift_name_wins_and_assisted_gets_no_max(db):
    w = _workout("w1", "2026-11-04T14:00:00Z", [("normal", 120, 5)])
    w["exercises"].append({"index": 1, "title": "Romanian Deadlift (Barbell)", "sets": [
        {"index": 0, "type": "normal", "weight_kg": 90, "reps": 8}]})
    w["exercises"].append({"index": 2, "title": "Chin Up (Assisted)", "sets": [
        {"index": 0, "type": "normal", "weight_kg": 70, "reps": 7}]})
    w["exercises"][0]["title"] = "Deadlift (Barbell)"
    hevy_pull.store(db, w)
    assert hevy_pull.lift(db, "Deadlift (Barbell)", 4, NOW)["matched"] == ["Deadlift (Barbell)"]
    chin = next(e for e in hevy_pull.summary(db, 7, NOW)["exercises"] if e["exercise"] == "Chin Up (Assisted)")
    assert chin["e1rm_lb"] is None
