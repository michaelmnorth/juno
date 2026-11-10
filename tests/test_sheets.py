"""tools/sheets.py offline: a small fake of the coach's block tab, Hevy workouts as plain dicts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import sheets  # noqa: E402

KG = 1 / 2.20462
COACH = "If <5 reps, do assisted"


def _week(s, rep, actual="", notes="", rpe=""):
    return [s, rep, "", "", "", "", actual, notes, rpe, ""]


def _rows(week2=None):
    """Two weeks (columns C and M), Day 1 with two exercises: Squat (2 rows) and Chin-Ups (AMRAP)."""
    week2 = week2 or {}
    head = ["", ""] + ["Week 1"] + [""] * 9 + ["Week 2"] + [""] * 9
    sub = ["", ""] + ["Set", "Rep"] + [""] * 8 + ["Set", "Rep"] + [""] * 8
    body = [
        ("Comp Squat", "1", "3"),
        ("", "2", "5"),
        ("Chin-Ups", "2", "AMRAP"),
    ]
    rows = [head, ["Day 1"], sub]
    for i, (name, s, rep) in enumerate(body):
        w2 = week2.get(i, ("", "", ""))
        rows.append(["", name] + _week(s, rep, notes=COACH if name == "Chin-Ups" else "")
                    + _week(s, rep, w2[0], w2[1] or (COACH if name == "Chin-Ups" else ""), w2[2]))
    return rows


def _workout(squat, chin=None, notes="", start="2026-11-02T14:00:00Z"):
    ex = [{"title": "Squat (Barbell)", "notes": notes, "sets": [{"kg": lb * KG, "reps": r, "rpe": rpe}
                                                              for lb, r, rpe in squat]}]
    if chin:
        ex.append({"title": "Chin Up (Assisted)", "notes": "", "sets": [{"kg": 60, "reps": r, "rpe": None}
                                                                       for r in chin]})
    return {"id": start, "title": "Forge | B16 | Day 1", "start": start, "notes": "", "exercises": ex}


NAMES = {"Comp Squat": ["Squat (Barbell)"], "Chin-Ups": ["Chin Up (Assisted)"]}


def test_parse_finds_weeks_days_and_groups():
    layout = sheets.parse(_rows())
    assert layout["weeks"] == [2, 12]
    assert [(g["name"], g["rows"]) for g in layout["days"][1]] == [("Comp Squat", [3, 4]), ("Chin-Ups", [5])]


def test_first_workout_of_a_day_is_week_one_and_sets_go_by_row():
    out = sheets.plan(_rows(), {1: [_workout([(300, 3, 8), (275, 5, 7), (275, 5, 8.5)], [6, 9])]}, NAMES, "B16")
    got = {c["cell"]: (c["value"], c["status"]) for c in out["cells"]}
    assert got["I4"] == ("300", "write") and got["K4"] == ("8", "write")   # row 1: one set
    assert got["I5"] == ("275", "write") and got["K5"] == ("8.5", "write")  # row 2: the next two
    assert got["I6"] == ("9", "write")  # AMRAP: best reps, not the assist load
    assert not any(c.startswith(("S", "U")) for c in got)


def test_not_logged_is_skipped_and_extras_are_reported():
    w = _workout([(300, 3, None)])
    w["exercises"].append({"title": "Hip Thrust", "notes": "", "sets": [{"kg": 50, "reps": 8, "rpe": None}]})
    out = sheets.plan(_rows(), {1: [w]}, NAMES, "B16")
    assert {c["cell"]: c["value"] for c in out["cells"]}["I6"] == "skipped"
    assert any("Hip Thrust" in i for i in out["issues"])


def test_wrong_week_is_stale_and_its_raw_note_is_not_coach_text():
    raw = "my right shin hurt a bit"
    rows = _rows({0: ("300", raw, ""), 2: ("9", f"{COACH} | {raw}", "")})
    w = _workout([(300, 3, None)], [9], notes=raw)
    out = sheets.plan(rows, {1: [w]}, NAMES, "B16")
    stale = {c["cell"] for c in out["cells"] if c["status"] == "stale"}
    assert {"S4", "S6"} <= stale
    notes = {n["cell"]: n for n in out["notes"]}
    assert notes["T4"]["stale"] and notes["T4"]["coach"] == ""
    assert notes["T6"]["coach"] == COACH
    assert notes["J4"]["raw"] == [raw] and notes["J4"]["mn"] is None


def test_both_hip_machines_fill_one_row():
    groups = [{"name": "Abductor/Adductor Machine", "rows": [5]}]
    ex = [{"title": "Hip Adduction (Machine)", "notes": "", "sets": [{"kg": 110 * KG, "reps": 10, "rpe": None}] * 2},
          {"title": "Hip Abduction (Machine)￼", "notes": "", "sets": [{"kg": 130 * KG, "reps": 10, "rpe": 8}] * 2}]
    names = {"Abductor/Adductor Machine": ["Hip Adduction (Machine)", "Hip Abduction (Machine)"]}
    found = sheets.match(groups, ex, names, combined=["Abductor/Adductor Machine"])
    assert len(found[0]["sets"]) == 4 and len(found[0]["parts"]) == 2
    rows = [[""] * 12 for _ in range(6)]
    rows[5][2], rows[5][3] = "2", "10-12"
    assert sheets.row_values(rows, groups[0], 2, found[0]) == [(5, "130", "8")]  # all four sets, top load
    assert sheets.match(groups, ex, names)[0]["title"] == "Hip Adduction (Machine)"  # not combined: one only


def test_sessions_carry_the_joel_label_and_what_is_new():
    out = sheets.plan(_rows(), {1: [_workout([(300, 3, None)], [9], notes="shin hurt")]}, NAMES, "B16")
    s = out["sessions"][0]
    assert s["label"] == "W1D1" and s["new"]
    assert s["lifts"][0] == {"sheet": "Comp Squat", "hevy": "Squat (Barbell)", "sets": "300x3"}
    assert s["lifts"][1]["sets"].endswith("(assist lb)") and s["notes"] == ["shin hurt"]


def test_mn_line_goes_on_top_of_the_coach_text():
    assert sheets.note_value({"mn": "Shin hurt", "coach": COACH}) == f"MN: Shin hurt\n{COACH}"
    assert sheets.note_value({"mn": "", "coach": COACH}) == COACH


class Sheet:
    def __init__(self, rows):
        self.rows, self.posts = rows, []

    def get(self, url, token, params=None):
        return {"values": self.rows}

    def call(self, method, url, token, body=None, params=None):
        self.posts.append(body)
        return {}


def test_write_keeps_conflicts_and_repairs_only_when_asked():
    raw = "my right shin hurt a bit"
    rows = _rows({0: ("300", raw, "")})
    the_plan = sheets.plan(rows, {1: [_workout([(300, 3, None)], [9], notes=raw)]}, NAMES, "B16")
    for n in the_plan["notes"]:
        n["mn"] = n["mn"] if n.get("stale") else "Shin hurt"
    rows[5][8] = "8"  # someone typed a different Actual into I6 after the plan
    sheet = Sheet(rows)
    out = sheets.write(the_plan, "id", "t", repair=True, get=sheet.get, call=sheet.call, env={})
    written = {d["range"].split("!")[1]: d["values"][0][0] for d in sheet.posts[0]["data"]}
    assert written["I4"] == "300" and written["S4"] == "" and written["T4"] == ""
    assert written["J4"] == "MN: Shin hurt"
    assert "I6" not in written and "I6" in out["left_alone"]

    sheet = Sheet(_rows({0: ("300", raw, "")}))
    out = sheets.write(the_plan, "id", "t", get=sheet.get, call=sheet.call, env={})
    assert "S4" in out["left_alone"] and "T4" in out["left_alone"]


def test_juno_runs_need_the_setting_and_never_repair():
    with pytest.raises(sheets.GoogleError):
        sheets.allowed(False, {"COORDINATOR_UNATTENDED": "1"}, lambda c: "ask")
    with pytest.raises(sheets.GoogleError):
        sheets.allowed(True, {"COORDINATOR_UNATTENDED": "0"}, lambda c: "auto")
    assert "auto" in sheets.allowed(False, {"COORDINATOR_UNATTENDED": "1"}, lambda c: "auto")
    assert sheets.allowed(True, {}, lambda c: "ask") == "Code tab with Michael"
