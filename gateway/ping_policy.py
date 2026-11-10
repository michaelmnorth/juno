"""What the bridge does with a timer's result, decided in code rather than in the prompt.

Research 2026-11-07 (docs/06): both OpenClaw and Hermes stay quiet mostly through prompt rules; Hermes adds a
code gate before the model runs and keeps failures visible. Here:
- The sweep ends its reply with a JSON verdict: {"notify", "urgency", "items": [...], "hold": [...]}.
- Items already pinged are dropped (state/pinged.json). Quiet hours and the daily cap from me/proactivity.yaml are
  enforced here; anything held back goes to state/holding.md, which the morning brief and evening check-in empty.
- Kinds in `always_allowed` (leave_by, approval_needed, urgent) skip the daily cap, never quiet hours.
- A failing job posts once per failure streak (state/failures.json), so silence never hides a broken run.
- state/sweep-last.md keeps the last thing a sweep posted, so the next one does not repeat it.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Pinned by Michael's plan, never chosen by the model (docs/06, Hermes "model pins are user-owned").
# Exact IDs, not aliases, so a new model release never changes Juno silently (docs/v2 brief P0, 2026-11-10).
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
JOB_MODELS = {
    "sweep": HAIKU,
    "morning-brief": SONNET,
    "evening-checkin": SONNET,
    "weekly-reflection": OPUS,
    "coach-sheet": SONNET,
    "handoff": HAIKU,
}
# DMs and the approval runs that resume them: Sonnet at low effort instead of the account default (Opus), the
# interim cost relief in docs/v2 brief P0. One model for both keeps the session's cache. Env overrides for a test.
DM_MODEL = os.environ.get("JUNO_DM_MODEL", SONNET)
DM_EFFORT = os.environ.get("JUNO_DM_EFFORT", "low")
# Per-run caps (docs/04 proposal 6): (max turns, max dollars). About ten times a normal run in state/costs.jsonl
# (sweep ~$0.03, brief ~$0.30), so only a runaway hits them; the failure notice then says so once. DMs have none:
# Michael is there and can stop them.
JOB_LIMITS = {
    "sweep": (30, 0.50),
    "morning-brief": (40, 2.00),
    "evening-checkin": (30, 1.50),
    "weekly-reflection": (60, 5.00),
    "coach-sheet": (1, 0.25),  # lean: one words-only call (tools/coach_sheet.py)
    "approval": (12, 0.75),
    "handoff": (4, 0.15),
    # A DM resumes its session; --max-budget-usd counts only this invocation (CLI reference), so it caps one
    # message. Sonnet at low effort; the audited Opus max was $2.53 (docs/v2/reports/P0-ledger.md).
    "dm": (None, 1.50),
}
DEFAULT_CAP = 5
PINGED_KEEP_DAYS = 14


@dataclass
class Verdict:
    notify: bool
    urgency: str = "normal"
    items: list[dict] = field(default_factory=list)
    hold: list[dict] = field(default_factory=list)


def parse_verdict(text: str) -> Verdict | None:
    """The last JSON object in the reply that has a "notify" key. None when the reply has no verdict."""
    for match in reversed(list(re.finditer(r"\{", text))):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "notify" in data:
            items = [i for i in data.get("items") or [] if isinstance(i, dict) and i.get("text")]
            hold = [i for i in data.get("hold") or [] if isinstance(i, dict) and i.get("text")]
            return Verdict(bool(data["notify"]), str(data.get("urgency") or "normal"), items, hold)
    return None


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except json.JSONDecodeError:
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _now(cfg: dict, now: datetime | None) -> datetime:
    tz = ZoneInfo((cfg or {}).get("timezone", "America/New_York"))
    return (now or datetime.now(tz)).astimezone(tz)


def _hold(state: Path, items: list[dict], now: datetime, why: str) -> None:
    if not items:
        return
    state.mkdir(parents=True, exist_ok=True)
    with (state / "holding.md").open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(f"- {now:%Y-%m-%d %H:%M} [{item.get('kind', 'other')}] {item['text']} ({why})\n")


def decide_sweep(verdict: Verdict, cfg: dict, state: Path, *, quiet: bool, now: datetime | None = None) -> str | None:
    """Apply de-duplication, quiet hours and the daily cap. Returns the text to post, or None."""
    now = _now(cfg, now)
    _hold(state, verdict.hold, now, "batched")
    if not verdict.notify or not verdict.items:
        return None

    pinged = _read(state / "pinged.json", {"ids": {}, "days": {}})
    cutoff = (now - timedelta(days=PINGED_KEEP_DAYS)).isoformat()
    pinged["ids"] = {k: v for k, v in pinged.get("ids", {}).items() if v >= cutoff}
    fresh = [i for i in verdict.items if str(i.get("id") or i["text"]) not in pinged["ids"]]
    if not fresh:
        _write(state / "pinged.json", pinged)
        return None
    if quiet:
        _hold(state, fresh, now, "quiet hours")
        _write(state / "pinged.json", pinged)
        return None

    always = set((cfg or {}).get("always_allowed") or [])
    cap = int((cfg or {}).get("unprompted_pings_per_day", DEFAULT_CAP))
    today = now.strftime("%Y-%m-%d")
    used = int(pinged.get("days", {}).get(today, 0))
    send = [i for i in fresh if i.get("kind") in always or verdict.urgency == "high"]
    rest = [i for i in fresh if i not in send]
    if used < cap:
        send += rest
        rest = []
    _hold(state, rest, now, "daily cap reached")
    if not send:
        _write(state / "pinged.json", pinged)
        return None

    for item in send:
        pinged["ids"][str(item.get("id") or item["text"])] = now.isoformat()
    # Leave-by, approvals and urgent items do not use up the daily budget.
    counts = any(i.get("kind") not in always for i in send) and verdict.urgency != "high"
    pinged["days"] = {today: used + (1 if counts else 0)}
    _write(state / "pinged.json", pinged)
    text = "\n".join(f"• {i['text']}" for i in send)
    (state / "sweep-last.md").write_text(f"# Last sweep ping {now:%Y-%m-%d %H:%M}\n\n{text}\n", encoding="utf-8")
    return text


def failure_notice(job: str, ok: bool, detail: str, state: Path) -> str | None:
    """Post on the first failure of a streak only; a success resets the streak."""
    path = state / "failures.json"
    data = _read(path, {})
    streak = int(data.get(job, 0))
    data[job] = 0 if ok else streak + 1
    _write(path, data)
    if ok or streak:
        return None
    return f"{job} failed and I will keep retrying on schedule. Detail: {detail[:600]}"


def pop_due_timers(state: Path, cfg: dict, *, now: datetime | None = None) -> list[str]:
    """One-shot timers the morning brief writes to state/timers.json: [{"id", "at" (ISO with offset), "text"}].
    Due ones are removed and returned as text to post; inside quiet hours they go to holding instead."""
    path = state / "timers.json"
    timers = _read(path, [])
    if not timers:
        return []
    now = _now(cfg, now)
    due, keep = [], []
    for t in timers:
        try:
            at = datetime.fromisoformat(t["at"])
        except (KeyError, ValueError):
            continue  # drop malformed entries instead of failing every minute
        (due if at <= now else keep).append(t)
    if not due:
        return []
    _write(path, keep)
    pinged = _read(state / "pinged.json", {"ids": {}, "days": {}})
    fresh = [t for t in due if str(t.get("id")) not in pinged.get("ids", {})]
    for t in fresh:
        pinged.setdefault("ids", {})[str(t.get("id"))] = now.isoformat()
    _write(state / "pinged.json", pinged)
    return [t["text"] for t in fresh if t.get("text")]
