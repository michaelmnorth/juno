"""One-time tokens that prove a calendar change was approved (by Michael's tap or an auto rule).

tools/gcal.py is on the settings allow list like every tools/ script, so a granted tool can't be the gate the way it
is for send_message. Instead the bridge issues a random token to the one run that carries out the approval, in that
run's environment only (COORDINATOR_APPROVAL_TOKEN), and keeps just its hash here with the class, the people who may
be invited and an expiry. gcal.py checks the token before any calendar write and spends it after the write
succeeds. A run the bridge didn't start never sees a token, and the hash can't be turned back into one.

  state/approval-tokens.json   {"tokens": [{"hash", "approval_id", "class", "recipients", "expires", "used"}]}
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

FILE = "approval-tokens.json"
TTL = timedelta(minutes=15)
KEEP = timedelta(days=2)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load(state: Path) -> list[dict]:
    try:
        return json.loads((state / FILE).read_text(encoding="utf-8")).get("tokens", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _save(state: Path, tokens: list[dict]) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / FILE).write_text(json.dumps({"tokens": tokens}, indent=2), encoding="utf-8")


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def issue(state: Path, approval_id: str, cls: str, recipients: list[str], now: datetime | None = None) -> str:
    now = _now(now)
    token = secrets.token_urlsafe(32)
    kept = [t for t in _load(state) if datetime.fromisoformat(t["expires"]) > now - KEEP]
    kept.append({"hash": _hash(token), "approval_id": approval_id, "class": cls,
                 "recipients": sorted({r.strip().lower() for r in recipients if r.strip()}),
                 "expires": (now + TTL).isoformat(timespec="seconds"), "used": None})
    _save(state, kept)
    return token


def check(state: Path, token: str, classes: tuple[str, ...], invited: set[str],
          now: datetime | None = None) -> tuple[dict | None, str]:
    """(the approval record, "") when the token allows this write, else (None, why not)."""
    if not token:
        return None, "calendar changes need an approval: ask with a card (state/pending-approvals.json)"
    now = _now(now)
    record = next((t for t in _load(state) if t.get("hash") == _hash(token)), None)
    if not record:
        return None, "unknown approval token"
    if record.get("used"):
        return None, "this approval was already used"
    if datetime.fromisoformat(record["expires"]) <= now:
        return None, "this approval expired"
    if record.get("class") not in classes:
        return None, f"approved for {record.get('class')}, not this change"
    extra = {e.lower() for e in invited} - set(record.get("recipients", []))
    if extra:
        return None, f"not approved to invite {', '.join(sorted(extra))}"
    return record, ""


def spend(state: Path, token: str, now: datetime | None = None) -> None:
    tokens = _load(state)
    for t in tokens:
        if t.get("hash") == _hash(token):
            t["used"] = _now(now).isoformat(timespec="seconds")
    _save(state, tokens)
