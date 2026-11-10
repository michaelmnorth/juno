"""Tempo's time math (tools/slots.py), offline with a fake calendar."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import slots  # noqa: E402

ET = ZoneInfo("America/New_York")
EVENTS = [
    {"start": "2026-11-11T09:00:00-05:00", "end": "2026-11-11T10:00:00-05:00", "title": "Standup", "busy": True},
    {"start": "2026-11-11T12:00:00-05:00", "end": "2026-11-11T13:00:00-05:00", "title": "Lunch", "busy": True},
    {"start": "2026-11-11T15:00:00-05:00", "end": "2026-11-11T16:00:00-05:00", "title": "Maybe", "busy": False},
    {"start": "2026-11-12", "end": "2026-11-13", "title": "Out all day", "busy": True},
]
EARLY = datetime(2026, 11, 10, 7, 0, tzinfo=ET)


def test_free_gaps_respect_buffer_and_window():
    out = slots.free(slots.busy_spans(EVENTS), date(2026, 11, 11), 1, 30, (time(8), time(18)), 15, now=EARLY)
    assert [(s["start"][11:16], s["end"][11:16]) for s in out] == [("08:00", "08:45"), ("10:15", "11:45"),
                                                                    ("13:15", "18:00")]
    assert out[0]["label"] == "Wed Nov 11, 8 AM to 8:45 AM"


def test_transparent_events_do_not_block_and_all_day_busy_does():
    out = slots.free(slots.busy_spans(EVENTS), date(2026, 11, 11), 2, 60, (time(13), time(18)), 0, now=EARLY)
    assert [s["start"][:10] for s in out] == ["2026-11-11"] and out[0]["minutes"] == 300


def test_past_time_is_never_offered():
    now = datetime(2026, 11, 11, 14, 10, tzinfo=ET)
    out = slots.free(slots.busy_spans(EVENTS), date(2026, 11, 11), 1, 30, (time(8), time(18)), 0, now=now)
    assert out[0]["start"].startswith("2026-11-11T14:10")


def test_check_finds_overlaps_with_buffer():
    spans = slots.busy_spans(EVENTS)
    assert slots.check(spans, slots._dt("2026-11-11 10:00"), slots._dt("2026-11-11 11:00"))["free"]
    hit = slots.check(spans, slots._dt("2026-11-11 10:00"), slots._dt("2026-11-11 11:00"), buffer=15)
    assert not hit["free"] and hit["conflicts"][0]["title"] == "Standup"


def test_when_gives_weekday_and_offset():
    out = slots.when("2026-11-12 16:00", minutes=90)
    assert out["weekday"] == "Thursday" and out["iso"] == "2026-11-12T16:00:00-05:00"
    assert out["label"] == "Thu Nov 12, 4 PM to 5:30 PM"


def test_cli_free_uses_the_calendar(capsys):
    assert slots.main(["free", "--from", "2026-11-11", "--days", "1", "--window", "08:00-09:00"],
                      get_events=lambda start, days: EVENTS) == slots.OK
    assert isinstance(json.loads(capsys.readouterr().out), list)  # the real clock decides whether 8:00 is past


def test_cli_bad_input_exit_code():
    assert slots.main(["free", "--from", "2026-11-11", "--min", "1"], get_events=lambda s, d: []) == slots.BAD_INPUT
