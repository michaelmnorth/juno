"""The coach-sheet sync, lean: Python does every number, one small model call does the words.

Steps: pull Hevy, plan the block tab (tools/sheets.py), write Actual and LsRPE, then, only when there is a new
session or a raw note to summarize, one words-only model call (no tools, no project context, about 2 to 4k tokens)
for the MN lines and the coach note, then write the notes and build Michael's message. The model never sees or
touches a cell number. Rules: domains/health/CONTEXT.md.

  python tools/coach_sheet.py sync [--plan state/sheet-plan.json]   with --plan, skip the pull and plan (the bridge
                                                                    already did both); prints {"ok", "message"}
  python tools/coach_sheet.py note-cardio                           no model, no sheet: notes cardio-only workouts
                                                                    (a treadmill walk) in state/cardio-log.jsonl;
                                                                    the next sync message mentions them once

The message always says where each new session went ("Logged as Week 2, Day 4.") and says so when that place was a
best guess (sheets.placement_guess). After a session is fully logged, one line goes to state/workout-events.jsonl
(once per workout, with its start and end time) and each module named under `after_log:` in the coach-sheet config
runs: tools/<name>.py, function after_log(event) -> str | None. That is where Phase 2 (lift video clips) plugs in;
a failing hook is logged and never undoes or blocks the sheet.
Writes go through sheets.write as an unattended run: sheet.append_log must be auto, and moves, clears and overwrites
are refused here (those stay in the Code tab with Michael).
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import google_read  # noqa: E402
import hevy_pull  # noqa: E402
import sheets  # noqa: E402
from google_read import BAD_INPUT, OK, GoogleError  # noqa: E402

ROOT = google_read.ROOT
PLAN = ROOT / "state" / "sheet-plan.json"
CARDIO_LOG = ROOT / "state" / "cardio-log.jsonl"
EVENTS = ROOT / "state" / "workout-events.jsonl"
CARDIO_LOOKBACK_DAYS = 21  # the first run doesn't backfill a year of walks
HOOK_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
UNATTENDED = {"COORDINATOR_UNATTENDED": "1"}
MODEL = "claude-sonnet-5-5"
SYSTEM = ("You tidy a powerlifter's own workout notes and write his short update to his coach. "
          "Reply with one JSON object and nothing else.")
RULES = """Write three things from the data below.
"mn": for each note id, a cleaned summary of what happened in his own words: first person, dictation slips fixed,
nothing added or guessed, no dashes, under 170 characters, no "MN:" prefix.
"coach": for each session label, 1 to 3 short sentences from him to his coach: plain, warm, first person, no
dashes, no emoji, no greeting or sign-off. Lead with the heavy lifts (the first two, every working set as logged,
e.g. "Squats were 145x8, 145x8 and 150x8"), then anything he noted (pain, how it felt, what he changed). On assisted
lifts the load is the assist. Mention a skipped exercise only if it matters.
Both: leave out anything he asked his assistant or an app to do (make an exercise, update a routine); that is not
for the sheet or for the coach.
"line": one short line to him from his friend Juno, dry and deadpan (think Norm MacDonald), about this session, with
one emoji. No medical advice.
Shape: {"mn": {"<note id>": "..."}, "coach": {"<label>": "..."}, "line": "..."}"""


def words_prompt(new: list[dict], todo: list[dict]) -> str:
    data = {"sessions": [{k: s[k] for k in ("label", "date", "lifts", "skipped", "notes")} for s in new],
            "notes": [{"id": n["cell"], "session": f"W{n['week']}D{n['day']}", "exercise": n["exercise"],
                       "raw": n["raw"]} for n in todo]}
    return f"{RULES}\n\nData:\n{json.dumps(data, ensure_ascii=False)}"


def parse_words(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    try:
        out = json.loads(text[start:end + 1]) if start != -1 else {}
    except json.JSONDecodeError:
        out = {}
    clean = lambda s: re.sub(r"\s*[–—]\s*", ", ", str(s)).strip()  # noqa: E731  (his no-dash rule)
    return {"mn": {k: clean(v) for k, v in (out.get("mn") or {}).items()},
            "coach": {k: clean(v) for k, v in (out.get("coach") or {}).items()},
            "line": str(out.get("line") or "").strip()}


def placement(session: dict) -> str:
    """'Logged as Week 2, Day 4.' plus the reason when the place was a best guess."""
    m = re.match(r"W(\d+)D(\d+)", session["label"])
    week, day = session.get("week") or int(m.group(1)), session.get("day") or int(m.group(2))
    line = f"Logged as Week {week}, Day {day}"
    if session.get("date"):
        line += f" ({session['date']})"
    if session.get("guess"):
        return f"{line}. That's my best guess: {session['guess']}. Tell me if it belongs somewhere else."
    return line + "."


def message(new: list[dict], words: dict, first: dict, second: dict | None, issues: list[str],
            cardio: list[dict] = (), extra: list[str] = ()) -> str | None:
    labels = {s["label"] for s in new}
    if not labels and not first["written"]:
        return None
    parts = [words.get("line") or f"{', '.join(sorted(labels)) or 'Your workout'} is on the coach's sheet. 🫡"]
    parts += [placement(s) for s in new]
    for s in new:
        note = words["coach"].get(s["label"])
        if note:
            parts.append(f"```\n{s['label']}\n{note}\n```")
    alone = [w for w in (second or first).get("left_alone_where", []) if w.split(" ", 1)[0] in labels]
    if alone:
        parts.append("Left alone because they already had something different in them: " + ", ".join(alone) + ".")
    prefixes = tuple("Day {1} week {0}:".format(*re.match(r"W(\d+)D(\d+)", s["label"]).groups()) for s in new)
    parts += [i for i in issues if i.startswith(prefixes)]
    if any(not words["coach"].get(s["label"]) for s in new):
        parts.append("The numbers are in. The notes didn't come through this time; I'll try again on the next check.")
    if cardio:
        parts.append("Kept off the coach's sheet, noted here instead: " + "; ".join(cardio_text(c) for c in cardio)
                     + ".")
    parts += [x for x in extra if x]
    return "\n\n".join(parts)


# --- cardio-only sessions: noted, never on the sheet ----------------------------------------------

def cardio_text(entry: dict) -> str:
    bits = []
    for e in entry.get("exercises", []):
        size = ", ".join(x for x in (f"{e['minutes']} min" if e.get("minutes") else "",
                                     f"{e['miles']:g} mi" if e.get("miles") else "") if x)
        bits.append(f"{e['title'].lower()}{f' ({size})' if size else ''}")
    return f"{' and '.join(bits) or 'cardio'} on {entry.get('date', '?')}"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def note_cardio(db, log: Path = CARDIO_LOG, now: datetime | None = None) -> list[dict]:
    """Append cardio-only workouts not noted yet; returns the new entries. Model-free, local only."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=CARDIO_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    seen = {e.get("id") for e in _read_jsonl(log)}
    fresh = [dict(w, noted=now.isoformat(timespec="seconds"), told=False)
             for w in sheets.cardio_workouts(db, since) if w["id"] not in seen]
    if fresh:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            for e in fresh:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return fresh


def untold_cardio(log: Path = CARDIO_LOG) -> list[dict]:
    return [e for e in _read_jsonl(log) if not e.get("told")]


def mark_told(ids: set[str], log: Path = CARDIO_LOG) -> None:
    if not ids:
        return
    entries = _read_jsonl(log)
    for e in entries:
        if e.get("id") in ids:
            e["told"] = True
    log.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")


# --- after logging: the hook Phase 2 plugs into ---------------------------------------------------

def after_log(sessions: list[dict], block, hooks=(), events: Path = EVENTS, loader=None) -> list[str]:
    """One event per newly, fully logged workout (never twice), then each hook in order. Returns the hooks' lines
    for the message. A hook that fails is reported on stderr and skipped; the sheet is already done."""
    loader = loader or importlib.import_module
    seen = {e.get("workout_id") for e in _read_jsonl(events)}
    out = []
    for s in sessions:
        if not s.get("id") or s["id"] in seen:
            continue
        event = {"type": "workout.logged", "workout_id": s["id"], "label": s["label"], "block": block,
                 "week": s.get("week"), "day": s.get("day"), "date": s.get("date"), "start": s.get("start"),
                 "end": s.get("end"), "title": s.get("title"), "guess": s.get("guess"),
                 "lifts": s.get("lifts", []), "logged": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        seen.add(s["id"])
        for name in hooks or ():
            if not HOOK_NAME.match(str(name)):
                print(f"after_log: skipped hook {name!r} (not a tools/ module name)", file=sys.stderr)
                continue
            try:
                line = loader(name).after_log(event)
            except Exception as exc:  # noqa: BLE001  (a hook never breaks the sync)
                print(f"after_log: hook {name} failed: {exc}", file=sys.stderr)
                continue
            if line:
                out.append(str(line))
    return out


def sync(plan_path: Path = PLAN, fresh: bool = True, runner=None, tool_env=UNATTENDED,
         cardio_log: Path = CARDIO_LOG, events: Path = EVENTS, loader=None) -> dict:
    """{"ok": bool, "message": str | None}. ok False = try again later (numbers may already be in)."""
    cfg, token = sheets.config(), google_read.access_token()
    if fresh:
        db = hevy_pull.connect()
        hevy_pull.pull(db, hevy_pull.api_key())
        note_cardio(db, cardio_log)
        block = sheets.current_block(db)
        tab, gid = sheets.block_tab(cfg["sheet_id"], block, token)
        p = sheets.plan(sheets.read_tab(cfg["sheet_id"], tab, token), sheets.block_workouts(db, block),
                        cfg.get("exercises") or {}, tab, cfg.get("combined") or ())
        p["gid"], p["block"] = gid, block
    else:
        p = json.loads(plan_path.read_text(encoding="utf-8"))
    first = sheets.write(p, cfg["sheet_id"], token, notes=False, env=tool_env)
    new = [s for s in p["sessions"] if s["new"]]
    todo = [n for n in p["notes"] if n.get("mn") is None and not n.get("stale") and n.get("raw")]
    words, second, ok = {"mn": {}, "coach": {}, "line": ""}, None, True
    if new or todo:
        if runner is None:
            import claude_runner
            runner = claude_runner.run
        result = runner(words_prompt(new, todo), cwd=ROOT, unattended=True, model=MODEL, lean_system=SYSTEM,
                        max_budget_usd=0.25, timeout=300, job="coach-sheet")
        words = parse_words("" if result.is_error else result.text)
        for n in todo:
            if words["mn"].get(n["cell"]):
                n["mn"] = words["mn"][n["cell"]]
        ok = all(n.get("mn") for n in todo) and all(words["coach"].get(s["label"]) for s in new)
        if any(n.get("mn") for n in todo):
            second = sheets.write(p, cfg["sheet_id"], token, env=tool_env)
        elif ok:
            second = first
    plan_path.write_text(json.dumps(p, indent=1), encoding="utf-8")
    extra = after_log(new, p.get("block"), cfg.get("after_log") or (), events, loader) if ok else []
    cardio = untold_cardio(cardio_log)
    text = message(new, words, first, second, p["issues"], cardio, extra)
    if text and cardio:
        mark_told({c["id"] for c in cardio}, cardio_log)
    return {"ok": ok, "message": text,
            "written": first["written"] + (second["written"] if second and second is not first else 0)}


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    p = argparse.ArgumentParser(prog="coach_sheet.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--plan", default="")
    sub.add_parser("note-cardio")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    if args.cmd == "note-cardio":
        print(json.dumps({"noted": [cardio_text(e) for e in note_cardio(hevy_pull.connect())]}))
        return OK
    try:
        google_read.load_secrets()
        out = sync(Path(args.plan) if args.plan else PLAN, fresh=not args.plan)
        print(json.dumps(out))
        return OK
    except (GoogleError, hevy_pull.HevyError) as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
