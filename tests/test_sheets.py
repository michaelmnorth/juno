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


# --- placement: by order, with a flag when the order can't settle it (2026-11-19) -----------------------------------

def _w(day, start, block=16):
    return {"id": f"{day}-{start}", "title": f"Forge | B{block} | Day {day}", "start": start, "notes": "",
            "exercises": [{"title": "Squat (Barbell)", "notes": "", "cardio": False,
                           "sets": [{"kg": 300 * KG, "reps": 3, "rpe": None}]}]}


def _block(*days_and_dates):
    out = {}
    for day, date in days_and_dates:
        out.setdefault(day, []).append(_w(day, f"{date}T14:00:00Z"))
    return out


def test_running_a_week_behind_still_lands_in_the_right_week_with_no_guess():
    # Week 1 over two calendar weeks, Week 2 starting a week "late": the calendar never matters.
    done = _block((1, "2026-11-02"), (2, "2026-11-04"), (3, "2026-11-09"), (4, "2026-11-12"),
                  (1, "2026-11-17"), (2, "2026-11-19"))
    out = sheets.plan(_rows(), done, NAMES, "B16")
    assert [(s["label"], s["week"], s["day"], s["guess"]) for s in out["sessions"]] == [
        ("W1D1", 1, 1, None), ("W2D1", 2, 1, None)]
    assert sheets.placement_guess(done, 2, 1, done[2][1]) is None
    assert sheets.placement_guess(done, 4, 0, done[4][0]) is None


def test_days_out_of_order_inside_a_week_are_fine():
    done = _block((1, "2026-11-02"), (3, "2026-11-03"), (2, "2026-11-05"), (4, "2026-11-06"))
    assert all(sheets.placement_guess(done, d, 0, done[d][0]) is None for d in done)


def test_a_day_skipped_in_an_earlier_week_is_flagged_as_a_guess():
    done = _block((1, "2026-11-02"), (2, "2026-11-03"), (3, "2026-11-04"),
                  (1, "2026-11-09"), (2, "2026-11-10"), (3, "2026-11-11"), (4, "2026-11-12"))
    guess = sheets.placement_guess(done, 4, 0, done[4][0])  # first Day 4 ever, but the others are on Week 2
    assert guess and "Week 2" in guess


def test_a_day_done_too_often_and_a_same_date_double_are_flagged():
    done = _block((1, "2026-11-02"), (2, "2026-11-03"), (1, "2026-11-04"), (1, "2026-11-05"))
    assert "ahead" in sheets.placement_guess(done, 1, 2, done[1][2])
    assert sheets.placement_guess(done, 1, 1, done[1][1]) is None  # Week 2 Day 1 after Week 1: normal
    twice = _block((1, "2026-11-02"), (1, "2026-11-02"))
    twice[1][1]["start"] = "2026-11-02T18:00:00Z"
    assert "two Day 1 sessions" in sheets.placement_guess(twice, 1, 1, twice[1][1])


def test_a_session_with_nothing_matching_the_sheet_is_a_guess():
    w = _w(1, "2026-11-02T14:00:00Z")
    w["exercises"][0]["title"] = "Leg Press"
    out = sheets.plan(_rows(), {1: [w]}, NAMES, "B16")
    assert "none of its lifts matched" in out["sessions"][0]["guess"]


def test_cardio_is_told_apart_from_lifts_with_similar_names():
    assert sheets.is_cardio("Treadmill", [{"kg": None, "reps": None}])
    assert sheets.is_cardio("Cycling", [{"kg": 0, "reps": 0}])
    assert not sheets.is_cardio("Walking Lunge (Dumbbell)", [{"kg": 20, "reps": 10}])
    assert not sheets.is_cardio("Farmers Walk", [{"kg": 40, "reps": None}])
    assert not sheets.is_cardio("Seated Cable Row", [{"kg": 40, "reps": 10}])


def test_a_treadmill_warmup_is_not_reported_as_missing_from_the_sheet():
    w = _workout([(300, 3, None)], [9])
    w["exercises"].append({"title": "Treadmill", "notes": "", "cardio": True, "sets": []})
    out = sheets.plan(_rows(), {1: [w]}, NAMES, "B16")
    assert not any("Treadmill" in i for i in out["issues"])


def test_a_cardio_only_forge_session_never_takes_a_week(tmp_path):
    import hevy_pull
    db = hevy_pull.connect(tmp_path / "h.sqlite")
    sq = {"index": 0, "title": "Squat (Barbell)", "notes": "", "sets": [
        {"index": 0, "type": "normal", "weight_kg": 136, "reps": 3}]}
    walk = {"index": 0, "title": "Treadmill", "notes": "", "sets": [
        {"index": 0, "type": "normal", "weight_kg": None, "reps": None, "duration_seconds": 1500}]}
    for wid, start, ex in (("a", "2026-11-02T14:00:00Z", [sq]), ("b", "2026-11-05T14:00:00Z", [walk]),
                           ("c", "2026-11-09T14:00:00Z", [sq, dict(walk, index=1)])):
        hevy_pull.store(db, {"id": wid, "title": "Forge | B16 | Day 1", "start_time": start,
                             "end_time": start.replace("14:00", "15:00"), "exercises": ex})
    done = sheets.block_workouts(db, 16)
    assert [w["id"] for w in done[1]] == ["a", "c"]  # the walk didn't become Week 2
    assert done[1][1]["end"] == "2026-11-09T15:00:00Z" and done[1][1]["exercises"][1]["cardio"]
    assert [w["id"] for w in sheets.cardio_workouts(db, "2026-11-01")] == ["b"]
    labels = [s["label"] for s in sheets.plan(_rows(), done, NAMES, "B16")["sessions"]]
    assert labels == ["W1D1", "W2D1"]
