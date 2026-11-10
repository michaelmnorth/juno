"""The coach's program sheet (Forge Strength & Power) and the Hevy -> sheet sync, for Rep (the health agent).

Rules (Michael, from Muse's handoff and 2026-11-08, also in domains/health/CONTEXT.md):
- Juno writes only Actual, LsRPE and an "MN:" line in Notes. Coach text and prescriptions are never changed.
- Actual = the top working load (lb) of the sets that row prescribes; AMRAP rows = the best set's reps; an exercise
  prescribed but not logged = "skipped". LsRPE = RPE of the row's last set. Extra unprescribed sets are dropped.
- Weeks go by the order of days done in the block, not the calendar: the first Day 4 done is Week 1's Day 4.
- A cell is written only when empty or already the same; anything else is a conflict, reported and left alone.
- Notes: Michael's own Hevy notes (stream of consciousness) become one cleaned "MN: ..." line at the top of the
  exercise's first-row Notes cell; the coach's text stays below it untouched. The plan carries the raw notes; Juno
  writes the summary into the plan before `write`.

  python tools/sheets.py plan --block 16 [--out plan.json]   what the sync would write, from Hevy (no writes)
  python tools/sheets.py write --plan plan.json [--repair]    write a plan; --repair also clears stale cells (a
                                                              workout placed in the wrong week) and restores coach-
                                                              only notes there. Michael's yes, or the sheet.append_log
                                                              setting, decides whether it may run (see allowed()).

Config (sheet id, exercise names): domains/health/private/coach-sheet.yaml. Exit codes as google_read.py.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import urllib.parse
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import google_read  # noqa: E402
import hevy_pull  # noqa: E402
from google_read import BAD_INPUT, OK, REFUSED, GoogleError  # noqa: E402

ROOT = google_read.ROOT
CONFIG = ROOT / "domains" / "health" / "private" / "coach-sheet.yaml"
API = "https://sheets.googleapis.com/v4/spreadsheets"
# Offsets inside one week's block of columns: Set, Rep, Intensity, %, Suggested, Prescribed, Actual, Notes, LsRPE
SET, REP, ACTUAL, NOTES, LSRPE = 0, 1, 6, 7, 8
DAY_RE = re.compile(r"^Day (\d+)\b")


# --- sheet layout ---------------------------------------------------------------------------------

def col(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def cell(rows: list[list[str]], r: int, c: int) -> str:
    return rows[r][c].strip() if r < len(rows) and c < len(rows[r]) else ""


def parse(rows: list[list[str]]) -> dict:
    """{"weeks": [first column of each week], "days": {n: [group, ...]}}; a group is one exercise with its rows."""
    header = next(i for i, row in enumerate(rows) if any(str(v).strip().startswith("Week 1") for v in row))
    weeks = [i for i, v in enumerate(rows[header]) if str(v).strip().startswith("Week ")]
    days: dict[int, list[dict]] = {}
    current = None
    for r, row in enumerate(rows):
        first = cell(rows, r, 0)
        m = DAY_RE.match(first)
        if m:
            current = days.setdefault(int(m.group(1)), [])
            continue
        if current is None or cell(rows, r, weeks[0] + SET) in ("Set", "") or first.upper() == "CHECK-IN":
            if first.upper() == "CHECK-IN":
                current = None
            continue
        name = cell(rows, r, 1)
        if name:
            current.append({"name": name, "rows": []})
        if current:
            current[-1]["rows"].append(r)
    return {"weeks": weeks, "days": {d: g for d, g in days.items() if g}}


def coach_text(rows: list[list[str]], r: int, weeks: list[int], hevy_notes: set[str]) -> str:
    """The coach's note for a row: what the week cells share once Michael's raw Hevy notes and MN lines are taken out."""
    parts = []
    for w in weeks:
        text = "\n".join(line for line in cell(rows, r, w + NOTES).splitlines() if not line.startswith("MN:"))
        segs = [s.strip() for s in text.split(" | ")]
        parts.append(" | ".join(s for s in segs if s and _norm(s) not in hevy_notes))
    common = Counter(p for p in parts if p).most_common(1)
    return common[0][0] if common else ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[￼​﻿]", "", text or "")).strip().lower()


# --- Hevy side ------------------------------------------------------------------------------------

def block_workouts(db: sqlite3.Connection, block: int) -> dict[int, list[dict]]:
    """Forge workouts of this block, per day, in the order done (that order is the week)."""
    out: dict[int, list[dict]] = {}
    rows = db.execute("SELECT id, title, start_time, description FROM hevy_workouts WHERE title LIKE ? "
                      "ORDER BY start_time", (f"%| B{block} |%",)).fetchall()
    for wid, title, start, desc in rows:
        m = re.search(r"\bDay (\d+)\b", title or "")
        if not m:
            continue
        sets = db.execute("SELECT exercise_index, exercise, set_type, weight_kg, reps, rpe FROM hevy_sets "
                          "WHERE workout_id = ? ORDER BY exercise_index, set_index", (wid,)).fetchall()
        notes = dict(db.execute("SELECT exercise_index, notes FROM hevy_exercise_notes WHERE workout_id = ?",
                                (wid,)).fetchall())
        exercises: dict[int, dict] = {}
        for idx, ex, kind, kg, reps, rpe in sets:
            e = exercises.setdefault(idx, {"title": ex, "sets": [], "notes": notes.get(idx, "")})
            if kind != "warmup":
                e["sets"].append({"kg": kg, "reps": reps, "rpe": rpe})
        out.setdefault(int(m.group(1)), []).append({"id": wid, "title": title, "start": start,
                                                    "notes": (desc or "").strip(),
                                                    "exercises": [exercises[i] for i in sorted(exercises)]})
    return out


def match(groups: list[dict], exercises: list[dict], names: dict[str, list[str]],
          combined=()) -> dict[int, dict | None]:
    """Sheet group index -> the Hevy exercise that counts for it (or None: not logged). A combined row (both hip
    machines on one line) takes every listed exercise done, merged; "parts" keeps the originals."""
    free = list(range(len(exercises)))
    out: dict[int, dict | None] = {}
    for gi, group in enumerate(groups):
        wanted = [_norm(t) for t in names.get(group["name"], [])] or [_norm(group["name"])]
        picks = [i for t in wanted for i in free if _norm(exercises[i]["title"]) == t]
        picks = sorted(set(picks)) if group["name"] in combined else picks[:1]
        for i in picks:
            free.remove(i)
        if len(picks) > 1:
            parts = [exercises[i] for i in picks]
            out[gi] = {"title": " + ".join(p["title"] for p in parts), "sets": [s for p in parts for s in p["sets"]],
                       "notes": "\n".join(p["notes"] for p in parts if p["notes"]), "parts": parts,
                       "combined": True}
        else:
            out[gi] = exercises[picks[0]] if picks else None
    return out


def _count(text: str) -> int:
    return int(text) if text.isdigit() else 1


def row_values(rows, group: dict, week_col: int, exercise: dict | None) -> list[tuple[int, str, str]]:
    """(row, Actual, LsRPE) for each row of a group, sets handed out in order by each row's set count."""
    out = []
    if exercise is None:
        return [(r, "skipped", "") for r in group["rows"]]
    sets = list(exercise["sets"])
    for r in group["rows"]:
        n = len(sets) if exercise.get("combined") and r == group["rows"][-1] else _count(cell(rows, r, week_col + SET))
        mine, sets = sets[:n], sets[n:]
        if not mine:
            out.append((r, "", ""))
            continue
        # Actual is the load; reps only where there is no load to give (bodyweight, assisted AMRAP).
        unloaded = all(not s["kg"] for s in mine) or hevy_pull.assisted(exercise["title"])
        if unloaded:
            actual = str(max(s["reps"] or 0 for s in mine))
        else:
            actual = str(int(math.floor(max(s["kg"] or 0 for s in mine) * hevy_pull.LB + 0.5)))
        rpe = mine[-1]["rpe"]
        out.append((r, actual, "" if rpe is None else f"{rpe:g}"))
    return out


# --- the plan -------------------------------------------------------------------------------------

def _sets_text(exercise: dict) -> str:
    """'145x8, 145x8, 150x8' in lb; assisted lifts say so, since there the load is the help."""
    parts = []
    for s in exercise["sets"]:
        lb = hevy_pull._lb5(s["kg"]) if s["kg"] else None
        parts.append(f"{lb}x{s['reps']}" if lb else f"{s['reps']}")
    text = ", ".join(parts)
    return f"{text} (assist lb)" if hevy_pull.assisted(exercise["title"]) else text


def plan(rows: list[list[str]], workouts: dict[int, list[dict]], names: dict[str, list[str]], tab: str,
         combined=()) -> dict:
    layout = parse(rows)
    weeks = layout["weeks"]
    cells, notes, issues, sessions = [], [], [], []
    # Every Hevy note of the block: pasted into the wrong week, they still aren't the coach's text.
    all_raw = {_norm(n) for done in workouts.values() for w in done
               for n in [w["notes"], *(e["notes"] for e in w["exercises"])] if n}

    def want(r: int, c: int, value: str, kind: str, where: str):
        have = cell(rows, r, c)
        status = "same" if have == value else ("write" if not have else "conflict")
        cells.append({"cell": f"{col(c)}{r + 1}", "kind": kind, "value": value, "have": have, "status": status,
                      "where": where})

    for day, groups in layout["days"].items():
        done = workouts.get(day, [])
        if len(done) > len(weeks):
            issues.append(f"Day {day}: {len(done)} workouts for {len(weeks)} weeks; the extra ones were left out")
        for wk, workout in enumerate(done[:len(weeks)]):
            w = weeks[wk]
            found = match(groups, workout["exercises"], names, combined)
            used = {id(p) for e in found.values() if e for p in e.get("parts", [e])}
            for extra in (e for e in workout["exercises"] if id(e) not in used):
                issues.append(f"Day {day} week {wk + 1}: {extra['title']} is logged but not on the sheet")
            first = len(cells), len(notes)
            for gi, group in enumerate(groups):
                for r, actual, rpe in row_values(rows, group, w, found[gi]):
                    where = f"W{wk + 1}D{day} {group['name']}"
                    if actual:
                        want(r, w + ACTUAL, actual, "actual", where)
                    if rpe:
                        want(r, w + LSRPE, rpe, "lsrpe", where)
                raw = [found[gi]["notes"]] if found[gi] and found[gi]["notes"] else []
                if gi == 0 and workout["notes"]:
                    raw.insert(0, workout["notes"])
                top = group["rows"][0]
                coach = coach_text(rows, top, weeks, all_raw)
                have = cell(rows, top, w + NOTES)
                kept = next((line for line in have.splitlines() if line.startswith("MN:")), None)
                if raw or kept:
                    notes.append({"cell": f"{col(w + NOTES)}{top + 1}", "day": day, "week": wk + 1,
                                  "exercise": group["name"], "have": have, "coach": coach,
                                  "raw": raw, "mn": kept})  # an MN line already there stays; None = to write
            # The copy-paste note for the coach: W1D4, then the session. "new" = this run puts something on the sheet.
            sessions.append({
                "label": f"W{wk + 1}D{day}", "date": workout["start"][:10], "title": workout["title"],
                "new": any(c["status"] == "write" for c in cells[first[0]:])
                or any(n["mn"] is None for n in notes[first[1]:]),
                "lifts": [{"sheet": g["name"], "hevy": found[gi]["title"], "sets": _sets_text(found[gi])}
                          for gi, g in enumerate(groups) if found[gi]],
                "skipped": [g["name"] for gi, g in enumerate(groups) if not found[gi]],
                "notes": [x for x in [workout["notes"], *(e["notes"] for e in workout["exercises"])] if x]})
        # Cells filled in weeks this day hasn't reached: a workout placed in the wrong week.
        for wk in range(len(done), len(weeks)):
            w = weeks[wk]
            for group in groups:
                for r in group["rows"]:
                    for c, kind in ((w + ACTUAL, "actual"), (w + LSRPE, "lsrpe")):
                        if cell(rows, r, c):
                            cells.append({"cell": f"{col(c)}{r + 1}", "kind": kind, "value": "",
                                          "have": cell(rows, r, c), "status": "stale",
                                          "where": f"W{wk + 1}D{day} {group['name']}"})
                top = group["rows"][0]
                have = cell(rows, top, w + NOTES)
                coach = coach_text(rows, top, weeks, all_raw)
                if have and have != coach:
                    notes.append({"cell": f"{col(w + NOTES)}{top + 1}", "day": day, "week": wk + 1,
                                  "exercise": group["name"], "have": have, "coach": coach, "raw": [],
                                  "mn": "", "stale": True})
    counts = Counter(c["status"] for c in cells)
    sessions.sort(key=lambda s: s["date"])
    return {"tab": tab, "cells": cells, "notes": notes, "issues": issues, "counts": dict(counts),
            "sessions": sessions}


def note_value(entry: dict) -> str:
    """MN line on top, the coach's text below, unchanged."""
    mn = (entry.get("mn") or "").strip()
    mn = mn if not mn or mn.startswith("MN:") else f"MN: {mn}"
    return "\n".join(x for x in (mn, entry.get("coach", "")) if x)


# --- Google Sheets I/O ----------------------------------------------------------------------------

def config(path: Path = CONFIG) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def block_tab(sheet_id: str, block: int, token: str, get=None) -> tuple[str, int]:
    """(tab title, sheet gid) of the block's tab."""
    get = get or google_read._get
    tabs = [s["properties"] for s in get(f"{API}/{sheet_id}", token,
                                         {"fields": "sheets.properties(title,sheetId)"})["sheets"]]
    tab = next((t for t in tabs if re.match(rf"^Block {block}\b", t["title"])), None)
    if not tab:
        raise GoogleError(BAD_INPUT, f"no tab for Block {block}")
    return tab["title"], tab["sheetId"]


def current_block(db: sqlite3.Connection) -> int:
    """The block of the newest Forge workout in Hevy ("| B16 |")."""
    for (title,) in db.execute("SELECT title FROM hevy_workouts ORDER BY start_time DESC LIMIT 50"):
        m = re.search(r"\| B(\d+) \|", title or "")
        if m:
            return int(m.group(1))
    raise GoogleError(BAD_INPUT, "no Forge workout in Hevy yet")


def _ref(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return int(m.group(2)) - 1, sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(m.group(1)))) - 1


def bold_center(gid: int, refs: list[str]) -> list[dict]:
    """The sheet's look for Actual, Notes and LsRPE: bold and centered (some of the coach's rows come without it)."""
    out = []
    for ref in refs:
        r, c = _ref(ref)
        out.append({"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": c,
                      "endColumnIndex": c + 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.horizontalAlignment"}})
    return out


def juno_cells(rows: list[list[str]]) -> list[str]:
    """Every Actual, Notes and LsRPE cell of every exercise row, all weeks."""
    layout = parse(rows)
    return [f"{col(w + off)}{r + 1}" for groups in layout["days"].values() for g in groups for r in g["rows"]
            for w in layout["weeks"] for off in (ACTUAL, NOTES, LSRPE)]


def read_tab(sheet_id: str, tab: str, token: str, get=None) -> list[list[str]]:
    get = get or google_read._get
    rng = urllib.parse.quote(f"'{tab}'!A1:AZ200", safe="")
    return get(f"{API}/{sheet_id}/values/{rng}", token).get("values", [])


def allowed(repair: bool, env=None, mode=google_read.automation_mode) -> str:
    """Why this write may run, or raise. A Code-tab session with Michael (no COORDINATOR_UNATTENDED) may; Juno's own
    runs need sheet.append_log on auto, and never --repair or --fix (his call each time)."""
    env = os.environ if env is None else env
    if "COORDINATOR_UNATTENDED" not in env:
        return "Code tab with Michael"
    if repair:
        raise GoogleError(REFUSED, "repairs move or clear cells; Michael does those from the Code tab")
    if mode("sheet.append_log") == "auto":
        return "me/automation.yaml sheet.append_log: auto"
    raise GoogleError(REFUSED, "writing the coach sheet needs Michael's OK (sheet.append_log is not auto)")


def write(the_plan: dict, sheet_id: str, token: str, repair: bool = False, get=None, call=None,
          env=None, fix=(), notes: bool = True) -> dict:
    """Re-reads the tab and writes only what is still safe: empty or same cells, MN notes over coach text. `fix`
    names conflict cells Michael said were wrong; those take the plan's value if they still hold what it saw.
    notes=False writes the numbers only (the lean sync writes notes once the model has summarized them)."""
    why = allowed(repair or bool(fix), env)
    get, call = get or google_read._get, call or google_read.call
    rows = read_tab(sheet_id, the_plan["tab"], token, get)
    data, skipped = [], []

    def now(ref: str) -> str:
        return cell(rows, *_ref(ref))

    for c in the_plan["cells"]:
        have = now(c["cell"])
        if c["status"] == "stale":
            if repair and have == c["have"]:
                data.append((c["cell"], ""))
            else:
                skipped.append(c["cell"])
        elif c["cell"] in fix and c["status"] == "conflict" and have == c["have"]:
            data.append((c["cell"], c["value"]))
        elif have in ("", c["value"]) and c["value"] and have != c["value"]:
            data.append((c["cell"], c["value"]))
        elif have != c["value"]:
            skipped.append(c["cell"])
    for n in the_plan["notes"] if notes else ():
        if n.get("stale") and not repair:
            skipped.append(n["cell"])
            continue
        if not n.get("stale") and n.get("mn") is None:
            continue  # raw notes still waiting for their summary; not a conflict
        value, have = note_value(n), now(n["cell"])
        if n.get("coach") and n["coach"] not in have and have:
            skipped.append(n["cell"])  # the coach's text changed since the plan; leave it
        elif have != value:
            data.append((n["cell"], value))
    if data:
        call("POST", f"{API}/{sheet_id}/values:batchUpdate", token, {
            "valueInputOption": "USER_ENTERED",
            "data": [{"range": f"'{the_plan['tab']}'!{ref}", "values": [[v]]} for ref, v in data]})
        if the_plan.get("gid") is not None:
            call("POST", f"{API}/{sheet_id}:batchUpdate", token,
                 {"requests": bold_center(the_plan["gid"], [ref for ref, v in data if v])})
    where = {x["cell"]: x.get("where") or f"W{x.get('week')}D{x.get('day')} {x.get('exercise')}"
             for x in [*the_plan["cells"], *the_plan["notes"]]}
    return {"written": len(data), "cells": [ref for ref, _ in data], "left_alone": skipped, "why": why,
            "left_alone_where": sorted({where.get(ref, ref) for ref in skipped})}


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    p = argparse.ArgumentParser(prog="sheets.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--block", required=True, help="a number, or current (the newest Forge workout's block)")
    pl.add_argument("--out", default="")
    wr = sub.add_parser("write")
    wr.add_argument("--plan", required=True)
    wr.add_argument("--repair", action="store_true")
    wr.add_argument("--fix", default="", help="comma-separated conflict cells to overwrite (Code tab only)")
    fm = sub.add_parser("format", help="bold and center every Actual, Notes and LsRPE cell of the block")
    fm.add_argument("--block", required=True)
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        google_read.load_secrets()
        cfg, token = config(), google_read.access_token()
        if args.cmd in ("plan", "format"):
            db = hevy_pull.connect()
            block = current_block(db) if args.block == "current" else int(args.block)
            tab, gid = block_tab(cfg["sheet_id"], block, token)
            rows = read_tab(cfg["sheet_id"], tab, token)
        if args.cmd == "format":
            allowed(False)
            refs = juno_cells(rows)
            google_read.call("POST", f"{API}/{cfg['sheet_id']}:batchUpdate", token,
                             {"requests": bold_center(gid, refs)})
            out = {"formatted": len(refs), "tab": tab}
        elif args.cmd == "plan":
            out = plan(rows, block_workouts(db, block), cfg.get("exercises") or {}, tab, cfg.get("combined") or ())
            out["made"], out["gid"], out["block"] = datetime.now().isoformat(timespec="seconds"), gid, block
            if args.out:
                Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
                out = {"saved": args.out, "counts": out["counts"], "notes": len(out["notes"]),
                       "issues": out["issues"], "new_sessions": [s["label"] for s in out["sessions"] if s["new"]]}
        else:
            out = write(json.loads(Path(args.plan).read_text(encoding="utf-8")), cfg["sheet_id"], token,
                        args.repair, fix=tuple(c for c in args.fix.split(",") if c))
        print(json.dumps(out))
        return OK
    except GoogleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
