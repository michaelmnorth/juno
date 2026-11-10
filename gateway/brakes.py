"""Stopping Juno in code, with no model (docs/v2/05-SECURITY.md control 8, brief P0).

- Pause: "pause" in the DM, or the flag file state/PAUSED (create it by hand on the PC to stop everything).
  While it exists no Claude run starts: no DM answers, no timer jobs, no approved actions. "resume" removes it.
  Fixed-text timers (leave-by reminders) still post: they need no model.
- Spend notices, never a stop (Michael 2026-11-10): when today's runs (Eastern day, from state/costs.jsonl) pass
  each amount in NOTICE_AT_USD, the bridge adds one line with the dollars and tokens so far. Nothing pauses.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")
NOTICE_AT_USD = (5.00, 10.00)
PAUSE_WORDS = {"pause", "/pause", "stop everything"}
RESUME_WORDS = {"resume", "/resume", "unpause"}


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(ZONE).date().isoformat()


def flag(root: Path) -> Path:
    return root / "state" / "PAUSED"


def paused(root: Path) -> bool:
    return flag(root).exists()


def pause(root: Path, why: str = "Michael said pause") -> None:
    flag(root).parent.mkdir(parents=True, exist_ok=True)
    flag(root).write_text(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {why}\n", encoding="utf-8")


def resume(root: Path) -> None:
    flag(root).unlink(missing_ok=True)


def spent_today(root: Path, now: datetime | None = None) -> float:
    return today_totals(root, now)[0]


def today_totals(root: Path, now: datetime | None = None) -> tuple[float, int]:
    """(dollars, tokens) of today's per-run rows. Rows from before 2026-11-10 hold the session's running total, not the run's
    own cost (docs/v2/AUDIT.md section 2); only rows with `session_total_usd` are per-run, so only those count."""
    path = root / "state" / "costs.jsonl"
    if not path.exists():
        return 0.0, 0
    today, total, tokens = _today(now), 0.0, 0
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            try:
                row = json.loads(raw)
                if "session_total_usd" not in row:
                    continue
                at = datetime.fromisoformat(row["at"]).astimezone(ZONE).date().isoformat()
            except (ValueError, KeyError, TypeError):
                continue
            if at == today:
                total += float(row.get("cost_usd") or 0)
                tokens += sum(int(v or 0) for v in (row.get("tokens") or {}).values())
    return total, tokens


def _tokens(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{round(n / 1000)}K"


def spend_notice(root: Path, now: datetime | None = None) -> str | None:
    """One line the first time today's spend passes each NOTICE_AT_USD amount; None otherwise. Never stops a run."""
    dollars, tokens = today_totals(root, now)
    passed = [a for a in NOTICE_AT_USD if dollars >= a]
    if not passed:
        return None
    path = root / "state" / "spend-notice.json"
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {}
    day = _today(now)
    if seen.get("day") == day and float(seen.get("at") or 0) >= passed[-1]:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"day": day, "at": passed[-1]}), encoding="utf-8")
    return (f"Heads up: today's runs are at ${dollars:.2f} ({_tokens(tokens)} tokens). Nothing's paused, "
            "I just figured you'd want to know where the money goes. 💸")


def blocked(root: Path, now: datetime | None = None) -> str | None:
    """Why no model run may start now, or None."""
    return "paused" if paused(root) else None
