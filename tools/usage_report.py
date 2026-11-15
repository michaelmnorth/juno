"""Token usage, per request and per day, from state/costs.jsonl (Michael 2026-11-15).

Every model run writes one line there (gateway/claude_runner.py log_cost, v2/converse.py _log_cost): when, which job,
which model, tokens, what it would cost at API prices, and `what` it was for. Juno runs on Michael's Max plan, so the
dollars are a yardstick, not a bill. This script rolls the lines up by Eastern day. No model, read-only (apart from
--write, which saves the rollup under state/usage/ for the daily token optimizer).

  python tools/usage_report.py day [--date YYYY-MM-DD] [--write]   one day (default: yesterday), JSON
  python tools/usage_report.py week [--end YYYY-MM-DD]             seven daily totals, JSON

`hints` are plain checks in code (an Opus run on a routine job, a long run, low cache reuse, errors); the optimizer
reads them first and only digs into a job when one stands out.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("America/New_York")
TOKEN_KEYS = ("in", "out", "cache_read", "cache_write")
TOP_N = 8
LONG_RUN_TURNS = 20
ROUTINE_JOBS = ("sweep", "dm-router", "dm-reader", "handoff", "coach-sheet", "token-optimizer")


def _day(at: str) -> str | None:
    try:
        stamp = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(ZONE).date().isoformat()


def load(root: Path = ROOT) -> list[dict]:
    path = Path(root) / "state" / "costs.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and _day(row.get("at")):
                rows.append(row)
    return rows


def _tokens(row: dict) -> dict:
    t = row.get("tokens") or {}
    return {k: int(t.get(k) or 0) for k in TOKEN_KEYS}


def _usd(row: dict) -> float:
    # Rows from before 2026-11-10 hold a session's running total, not the run's own cost (gateway/brakes.py).
    return float(row.get("cost_usd") or 0) if "session_total_usd" in row else 0.0


def _model(row: dict) -> str:
    return str(row.get("model") or ",".join(row.get("models") or []) or "unknown")


def rollup(rows: list[dict], day: str) -> dict:
    """One Eastern day. A v2 summary row (Max plan) says what a DM did; its parts carry the tokens, so it only
    counts as a request, never twice."""
    todays = [r for r in rows if _day(r.get("at")) == day]
    runs = [r for r in todays if not r.get("summary")]
    totals = {k: 0 for k in TOKEN_KEYS}
    jobs: dict[str, dict] = defaultdict(lambda: {"runs": 0, "errors": 0, "usd": 0.0, "turns": 0,
                                                 "tokens": {k: 0 for k in TOKEN_KEYS}, "models": set()})
    for r in runs:
        t, j = _tokens(r), jobs[str(r.get("job") or "other")]
        for k in TOKEN_KEYS:
            totals[k] += t[k]
            j["tokens"][k] += t[k]
        j["runs"] += 1
        j["errors"] += bool(r.get("is_error"))
        j["usd"] += _usd(r)
        j["turns"] += int(r.get("turns") or 0)
        j["models"].add(_model(r))
    by_job = []
    for name, j in sorted(jobs.items(), key=lambda kv: -kv[1]["usd"]):
        by_job.append({"job": name, "runs": j["runs"], "errors": j["errors"], "usd": round(j["usd"], 4),
                       "avg_usd": round(j["usd"] / j["runs"], 4) if j["runs"] else 0.0,
                       "avg_turns": round(j["turns"] / j["runs"], 1) if j["runs"] else 0.0,
                       "tokens": j["tokens"], "models": sorted(j["models"])})
    top = sorted(runs, key=_usd, reverse=True)[:TOP_N]
    requests = [r for r in todays if r.get("summary") or str(r.get("job")) in ("dm", "dm-v2")]
    return {"date": day, "runs": len(runs), "requests": len(requests),
            "errors": sum(bool(r.get("is_error")) for r in runs),
            "tokens": {**totals, "total": sum(totals.values())}, "api_price_usd": round(sum(map(_usd, runs)), 4),
            "billing": "Max plan (dollars are what the runs would cost at API prices, not a bill)",
            "by_job": by_job,
            "top": [{"at": r.get("at"), "job": r.get("job"), "model": _model(r), "usd": round(_usd(r), 4),
                     "turns": r.get("turns"), "tokens": _tokens(r), "what": r.get("what") or ""} for r in top],
            "done": [{"at": r.get("at"), "what": r.get("what")} for r in todays if r.get("summary") and r.get("what")],
            "hints": hints(by_job, runs)}


def hints(by_job: list[dict], runs: list[dict]) -> list[str]:
    out = []
    for j in by_job:
        name, t = j["job"], j["tokens"]
        if name in ROUTINE_JOBS and any("opus" in m for m in j["models"]):
            out.append(f"{name} ran on Opus; it is a routine job (Haiku or Sonnet would do).")
        fresh = t["in"] + t["cache_write"]
        if j["runs"] >= 3 and fresh + t["cache_read"] and t["cache_read"] / (fresh + t["cache_read"]) < 0.5:
            out.append(f"{name}: under half its input came from cache over {j['runs']} runs; check that its "
                       "system prompt stays byte-stable.")
        if j["errors"]:
            out.append(f"{name}: {j['errors']} of {j['runs']} runs failed.")
        if j["avg_turns"] >= LONG_RUN_TURNS:
            out.append(f"{name}: {j['avg_turns']} turns a run on average; a search first (grep) and smaller reads "
                       "may cut it.")
    long_runs = [r for r in runs if int(r.get("turns") or 0) >= LONG_RUN_TURNS * 2]
    if long_runs:
        out.append(f"{len(long_runs)} run(s) took {LONG_RUN_TURNS * 2}+ turns.")
    return out


def week(rows: list[dict], end: str) -> list[dict]:
    last = date.fromisoformat(end)
    days = [(last - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    out = []
    for d in days:
        r = rollup(rows, d)
        out.append({"date": d, "runs": r["runs"], "requests": r["requests"], "errors": r["errors"],
                    "tokens": r["tokens"]["total"], "api_price_usd": r["api_price_usd"]})
    return out


def _yesterday() -> str:
    return (datetime.now(timezone.utc).astimezone(ZONE).date() - timedelta(days=1)).isoformat()


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("day")
    d.add_argument("--date", default=None)
    d.add_argument("--write", action="store_true")
    w = sub.add_parser("week")
    w.add_argument("--end", default=None)
    args = ap.parse_args(argv)
    rows = load(root)
    if args.cmd == "day":
        day = args.date or _yesterday()
        out = rollup(rows, day)
        if args.write:
            folder = Path(root) / "state" / "usage"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{day}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    else:
        out = week(rows, args.end or _yesterday())
    sys.stdout.write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
