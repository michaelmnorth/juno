"""The coach-sheet sync, lean: Python does every number, one small model call does the words.

Steps: pull Hevy, plan the block tab (tools/sheets.py), write Actual and LsRPE, then, only when there is a new
session or a raw note to summarize, one words-only model call (no tools, no project context, about 2 to 4k tokens)
for the MN lines and the coach note, then write the notes and build Michael's message. The model never sees or
touches a cell number. Rules: domains/health/CONTEXT.md.

  python tools/coach_sheet.py sync [--plan state/sheet-plan.json]   with --plan, skip the pull and plan (the bridge
                                                                    already did both); prints {"ok", "message"}
Writes go through sheets.write as an unattended run: sheet.append_log must be auto, and moves, clears and overwrites
are refused here (those stay in the Code tab with Michael).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import google_read  # noqa: E402
import hevy_pull  # noqa: E402
import sheets  # noqa: E402
from google_read import BAD_INPUT, OK, GoogleError  # noqa: E402

ROOT = google_read.ROOT
PLAN = ROOT / "state" / "sheet-plan.json"
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


def message(new: list[dict], words: dict, first: dict, second: dict | None, issues: list[str]) -> str | None:
    labels = {s["label"] for s in new}
    if not labels and not first["written"]:
        return None
    parts = [words.get("line") or f"{', '.join(sorted(labels)) or 'Your workout'} is on the coach's sheet. 🫡"]
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
    return "\n\n".join(parts)


def sync(plan_path: Path = PLAN, fresh: bool = True, runner=None, tool_env=UNATTENDED) -> dict:
    """{"ok": bool, "message": str | None}. ok False = try again later (numbers may already be in)."""
    cfg, token = sheets.config(), google_read.access_token()
    if fresh:
        db = hevy_pull.connect()
        hevy_pull.pull(db, hevy_pull.api_key())
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
    return {"ok": ok, "message": message(new, words, first, second, p["issues"]),
            "written": first["written"] + (second["written"] if second and second is not first else 0)}


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    p = argparse.ArgumentParser(prog="coach_sheet.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--plan", default="")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
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
