"""Hevy workouts into data/health.sqlite, for Rep (the health agent). Read-only toward Hevy.

The API key is Hevy Pro's (hevy.com, Settings, Developer), kept in 1Password as Agent-Secrets/Hevy-Juno/api_key and
read with Juno's service account, like the Google tools. HEVY_API_KEY in the environment wins, for `op run`.

  python tools/hevy_pull.py check                checks the key: {"username", "is_pro", "weight_unit"} (expect michaelmnorth)
  python tools/hevy_pull.py pull                 new and changed workouts since the last pull (all of them the first
                                                 time); deleted ones are removed. Prints {"added", "updated", "deleted"}.
  python tools/hevy_pull.py summary [--days 7]   sessions, and per exercise: sets, top set, best estimated 1RM, volume
  python tools/hevy_pull.py lift "Squat" [--weeks 12]   that lift week by week: top set and best estimated 1RM

Weights are stored in kg as Hevy keeps them (the API is kg-only) and reported in lb, top sets to the nearest 5 with
ties up (Michael's rule) and estimates to 1 lb. The rules from Muse's handoff, in
domains/health/private/hevy-handoff.md: pageSize caps at 10, a read can time out on a cold start (retried once),
the events feed (workouts/events; the handoff says workout_events, which 404s) is the sync source. Estimated 1RM is Epley, from sets of 10 reps or fewer, warm-ups excluded.
Exit codes: 0 ok, 3 no key yet, 4 Hevy refused, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import google_read  # noqa: E402  (venv relaunch and the 1Password service account helpers)

ROOT = google_read.ROOT
DB = ROOT / "data" / "health.sqlite"
CURSOR = ROOT / "state" / "hevy-cursor.json"
API = "https://api.hevyapp.com/v1"
REF = "op://Agent-Secrets/Hevy-Juno/api_key"
LB = 2.20462
PAGE = 10  # Hevy's maximum page size
OK, NO_KEY, REFUSED, BAD_INPUT = 0, 3, 4, 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS hevy_workouts (
    id TEXT PRIMARY KEY, title TEXT, start_time TEXT, end_time TEXT, updated_at TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS hevy_sets (
    workout_id TEXT REFERENCES hevy_workouts(id) ON DELETE CASCADE, exercise_index INTEGER, exercise TEXT,
    template_id TEXT, set_index INTEGER, set_type TEXT, weight_kg REAL, reps INTEGER, rpe REAL,
    distance_m REAL, duration_s REAL);
CREATE INDEX IF NOT EXISTS hevy_sets_by_exercise ON hevy_sets(exercise);
CREATE TABLE IF NOT EXISTS hevy_exercise_notes (
    workout_id TEXT REFERENCES hevy_workouts(id) ON DELETE CASCADE, exercise_index INTEGER, exercise TEXT,
    notes TEXT);
"""


class HevyError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def api_key() -> str:
    if os.environ.get("HEVY_API_KEY"):
        return os.environ["HEVY_API_KEY"]
    token_store = google_read._token_store()
    try:
        key = token_store.read_ref(token_store.find_op(), REF, google_read._sa_key(token_store))
    except (token_store.TokenError, google_read.GoogleError) as exc:
        raise HevyError(NO_KEY, f"no Hevy key yet (fill Agent-Secrets/Hevy-Juno/api_key): {exc}")
    if not key or key == "FILL-ME":
        raise HevyError(NO_KEY, "the Hevy-Juno item in 1Password is still empty")
    return key


def _get(path: str, key: str, params: dict | None = None) -> dict:
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"api-key": key, "accept": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:  # Hevy's message, never the key
            raise HevyError(REFUSED, f"Hevy {path}: HTTP {exc.code} {exc.read()[:200].decode(errors='replace')}")
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt == 2:
                raise HevyError(REFUSED, f"Hevy {path}: no answer ({exc})")
    raise AssertionError("unreachable")


def check(key: str, fetch=_get) -> dict:
    info = fetch("user/info", key, None).get("data", {})
    return {k: info.get(k) for k in ("username", "is_pro", "weight_unit", "distance_unit")}


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    if "routine_id" not in {row[1] for row in db.execute("PRAGMA table_info(hevy_workouts)")}:
        db.execute("ALTER TABLE hevy_workouts ADD COLUMN routine_id TEXT")  # added 2026-11-08 for the sheet sync
    return db


def store(db: sqlite3.Connection, workout: dict) -> bool:
    """Insert or replace one workout and its sets. True when it was new."""
    new = db.execute("SELECT 1 FROM hevy_workouts WHERE id = ?", (workout["id"],)).fetchone() is None
    db.execute("DELETE FROM hevy_sets WHERE workout_id = ?", (workout["id"],))
    db.execute("DELETE FROM hevy_exercise_notes WHERE workout_id = ?", (workout["id"],))
    db.execute("INSERT OR REPLACE INTO hevy_workouts (id, title, start_time, end_time, updated_at, description, "
               "routine_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (workout["id"], workout.get("title"), workout.get("start_time"), workout.get("end_time"),
                workout.get("updated_at"), workout.get("description"), workout.get("routine_id")))
    for ex in workout.get("exercises", []):
        if (ex.get("notes") or "").strip():
            db.execute("INSERT INTO hevy_exercise_notes VALUES (?, ?, ?, ?)",
                       (workout["id"], ex.get("index"), ex.get("title"), ex["notes"].strip()))
        for s in ex.get("sets", []):
            db.execute("INSERT INTO hevy_sets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (workout["id"], ex.get("index"), ex.get("title"), ex.get("exercise_template_id"),
                        s.get("index"), s.get("type"), s.get("weight_kg"), s.get("reps"), s.get("rpe"),
                        s.get("distance_meters"), s.get("duration_seconds")))
    return new


def _pages(fetch, path: str, key: str, params: dict, field: str):
    page = 1
    while True:
        got = fetch(path, key, {**params, "page": page, "pageSize": PAGE})
        yield from got.get(field, [])
        if page >= int(got.get("page_count") or 1):
            return
        page += 1


def pull(db: sqlite3.Connection, key: str, cursor: Path = CURSOR, fetch=_get,
         now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = (json.loads(cursor.read_text(encoding="utf-8")) if cursor.exists() else {}).get("since")
    added = updated = deleted = 0
    if not since:
        for workout in _pages(fetch, "workouts", key, {}, "workouts"):
            added += store(db, workout)
    else:
        for event in _pages(fetch, "workouts/events", key, {"since": since}, "events"):
            if event.get("type") == "deleted":
                deleted += db.execute("DELETE FROM hevy_workouts WHERE id = ?", (event.get("id"),)).rowcount
            elif event.get("workout"):
                if store(db, event["workout"]):
                    added += 1
                else:
                    updated += 1
    db.commit()
    cursor.parent.mkdir(parents=True, exist_ok=True)
    cursor.write_text(json.dumps({"since": now.isoformat(timespec="seconds").replace("+00:00", "Z")}),
                      encoding="utf-8")
    return {"added": added, "updated": updated, "deleted": deleted}


def _lb5(kg: float | None) -> int | None:
    """Nearest 5 lb, ties up (Michael's rule; Python's round() would send ties to even)."""
    return None if kg is None else int(5 * math.floor(kg * LB / 5 + 0.5))


def epley(kg: float, reps: int) -> float:
    return kg * (1 + reps / 30) if reps > 1 else kg


def assisted(exercise: str) -> bool:
    """On assisted lifts Hevy's weight is the help, so more is easier: no estimated max for them."""
    name = (exercise or "").lower()
    return "assisted" in name or any(c in name for c in ASSISTED_CUSTOM)


# Michael's own exercises of Hevy's "bodyweight assisted" type whose names don't say so.
ASSISTED_CUSTOM = ("chin ups parallel hand position",)


def _work_sets(db: sqlite3.Connection, start: str, end: str, exercise: str | None = None) -> list[tuple]:
    sql = ("SELECT w.start_time, s.exercise, s.weight_kg, s.reps FROM hevy_sets s JOIN hevy_workouts w "
           "ON w.id = s.workout_id WHERE w.start_time >= ? AND w.start_time < ? AND s.set_type != 'warmup' "
           "AND s.weight_kg IS NOT NULL AND s.reps > 0")
    args: list = [start, end]
    if exercise:
        sql += " AND lower(s.exercise) LIKE ?"
        args.append(f"%{exercise.lower()}%")
    return db.execute(sql + " ORDER BY w.start_time", args).fetchall()


def summary(db: sqlite3.Connection, days: int = 7, now: datetime | None = None) -> dict:
    if not 1 <= days <= 365:
        raise HevyError(BAD_INPUT, "--days must be 1 to 365")
    now = now or datetime.now(timezone.utc)
    start, end = (now - timedelta(days=days)).isoformat(), now.isoformat()
    sessions = db.execute("SELECT count(*) FROM hevy_workouts WHERE start_time >= ? AND start_time < ?",
                          (start, end)).fetchone()[0]
    per: dict[str, dict] = {}
    for _, ex, kg, reps in _work_sets(db, start, end):
        row = per.setdefault(ex, {"sets": 0, "top_kg": 0.0, "top_reps": 0, "e1rm_kg": 0.0, "volume_kg": 0.0})
        row["sets"] += 1
        row["volume_kg"] += kg * reps
        if (kg, reps) > (row["top_kg"], row["top_reps"]):
            row["top_kg"], row["top_reps"] = kg, reps
        if reps <= 10 and not assisted(ex):
            row["e1rm_kg"] = max(row["e1rm_kg"], epley(kg, reps))
    lifts = [{"exercise": ex, "sets": r["sets"], "top_set": f"{_lb5(r['top_kg'])}x{r['top_reps']}",
              "e1rm_lb": round(r["e1rm_kg"] * LB) or None, "volume_lb": round(r["volume_kg"] * LB)}
             for ex, r in sorted(per.items(), key=lambda kv: -kv[1]["volume_kg"])]
    return {"days": days, "sessions": sessions, "exercises": lifts}


def lift(db: sqlite3.Connection, name: str, weeks: int = 12, now: datetime | None = None) -> dict:
    if not name.strip() or not 1 <= weeks <= 104:
        raise HevyError(BAD_INPUT, "give a lift name and --weeks 1 to 104")
    now = now or datetime.now(timezone.utc)
    rows = _work_sets(db, (now - timedelta(weeks=weeks)).isoformat(), now.isoformat(), name)
    exact = [r for r in rows if r[1].lower() == name.strip().lower()]
    rows = exact or rows  # "Deadlift (Barbell)" must not pull in "Romanian Deadlift (Barbell)"
    by_week: dict[str, dict] = {}
    for when, ex, kg, reps in rows:
        day = datetime.fromisoformat(when.replace("Z", "+00:00")).date()
        week = (day - timedelta(days=day.weekday())).isoformat()
        w = by_week.setdefault(week, {"week_of": week, "top_kg": 0.0, "top_reps": 0, "e1rm_kg": 0.0, "sets": 0})
        w["sets"] += 1
        if (kg, reps) > (w["top_kg"], w["top_reps"]):
            w["top_kg"], w["top_reps"] = kg, reps
        if reps <= 10 and not assisted(ex):
            w["e1rm_kg"] = max(w["e1rm_kg"], epley(kg, reps))
    return {"lift": name, "matched": sorted({r[1] for r in rows}),
            "weeks": [{"week_of": w["week_of"], "sets": w["sets"], "top_set": f"{_lb5(w['top_kg'])}x{w['top_reps']}",
                       "e1rm_lb": round(w["e1rm_kg"] * LB) or None} for w in by_week.values()]}


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    p = argparse.ArgumentParser(prog="hevy_pull.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("pull")
    s = sub.add_parser("summary")
    s.add_argument("--days", type=int, default=7)
    lf = sub.add_parser("lift")
    lf.add_argument("name")
    lf.add_argument("--weeks", type=int, default=12)
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        db = connect()
        if args.cmd == "check":
            out = check(api_key())
        elif args.cmd == "pull":
            out = pull(db, api_key())
        elif args.cmd == "summary":
            out = summary(db, args.days)
        else:
            out = lift(db, args.name, args.weeks)
        print(json.dumps(out))
        return OK
    except HevyError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
