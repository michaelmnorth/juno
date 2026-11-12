"""Small JSON state helpers used by the bridge: per-DM Claude sessions, pending approvals, heartbeat.

All files live in <coordinator>/state and are git-ignored. Writes are atomic (temp file + replace).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
SESSION_IDLE_RESET = timedelta(hours=12)


def _read(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig") or "null") or default
    except json.JSONDecodeError:
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Slack DM -> Claude session -------------------------------------------------------------------

class SessionMap:
    """channel_id -> {"session_id", "last_used"}. A session is reused until /new or 12 h of silence."""

    def __init__(self, path: Path | None = None, idle_reset: timedelta = SESSION_IDLE_RESET):
        self.path = path or STATE / "slack-sessions.json"
        self.idle_reset = idle_reset

    def get(self, channel: str, *, now: datetime | None = None) -> str | None:
        data = _read(self.path, {})
        entry = data.get(channel)
        if not entry:
            return None
        now = now or datetime.now(timezone.utc)
        last = datetime.fromisoformat(entry["last_used"])
        if now - last > self.idle_reset:
            return None
        return entry.get("session_id")

    def stale(self, channel: str, *, now: datetime | None = None) -> str | None:
        """The session that went quiet for longer than idle_reset, still on record (for a handoff note)."""
        entry = _read(self.path, {}).get(channel)
        if not entry or not entry.get("session_id"):
            return None
        now = now or datetime.now(timezone.utc)
        return entry["session_id"] if now - datetime.fromisoformat(entry["last_used"]) > self.idle_reset else None

    def set(self, channel: str, session_id: str | None, *, now: datetime | None = None) -> None:
        if not session_id:
            return
        data = _read(self.path, {})
        data[channel] = {"session_id": session_id, "last_used": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
        _write(self.path, data)

    def reset(self, channel: str) -> None:
        data = _read(self.path, {})
        if channel in data:
            del data[channel]
            _write(self.path, data)


# --- Pending approvals ----------------------------------------------------------------------------

# Everything an approval card shows about what will happen. Hashed when the card is posted and checked again on the
# tap, so an entry edited after Michael saw it is refused instead of carried out.
PAYLOAD_KEYS = ("action_class", "summary", "action", "to", "subject", "draft_id", "draft_text", "attendees",
                "title", "start", "end", "calendar", "event_id")


# Form cards (web.form.submit) also bind the site, page, every field and value, and the button. Hashed only when
# present, so cards posted before these keys existed keep their hash.
FORM_KEYS = ("site", "url", "fields", "submit_label", "origins")


def payload_hash(entry: dict) -> str:
    keyed = {k: entry.get(k) for k in PAYLOAD_KEYS}
    keyed.update({k: entry[k] for k in FORM_KEYS if k in entry})
    canon = json.dumps(keyed, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# The coordinator appends entries with status "new"; the bridge posts a card and marks them "posted";
# a tap sets "approved" or "denied" and the bridge resumes the recorded session with the answer.

class Approvals:
    def __init__(self, path: Path | None = None):
        self.path = path or STATE / "pending-approvals.json"

    def _load(self) -> dict:
        data = _read(self.path, {"pending": []})
        data.setdefault("pending", [])
        return data

    def add(self, summary: str, action: str, *, session_id: str | None = None, kind: str = "action") -> dict:
        data = self._load()
        entry = {"id": f"a-{uuid.uuid4().hex[:8]}", "kind": kind, "summary": summary, "action": action,
                 "session_id": session_id, "status": "new", "created": now_iso()}
        data["pending"].append(entry)
        _write(self.path, data)
        return entry

    def append(self, entry: dict) -> dict:
        """A complete entry built in code (a form card from gateway/browser_agent.py); the watcher posts it."""
        data = self._load()
        data["pending"].append(entry)
        _write(self.path, data)
        return entry

    def new_entries(self) -> list[dict]:
        return [e for e in self._load()["pending"] if e.get("status") == "new"]

    def mark(self, approval_id: str, status: str, *, slack_ts: str | None = None, channel: str | None = None) -> dict | None:
        data = self._load()
        for e in data["pending"]:
            if e["id"] == approval_id:
                e["status"] = status
                e["updated"] = now_iso()
                if status == "posted":  # bind the tap to what the card showed (docs/v2/05-SECURITY.md control 3)
                    e.setdefault("payload_sha256", payload_hash(e))
                if slack_ts:
                    e["slack_ts"] = slack_ts
                if channel:
                    e["slack_channel"] = channel
                _write(self.path, data)
                return e
        return None

    def get(self, approval_id: str) -> dict | None:
        return next((e for e in self._load()["pending"] if e["id"] == approval_id), None)

    def posted(self) -> list[dict]:
        return [e for e in self._load()["pending"] if e.get("status") == "posted"]

    def refresh(self, approval_id: str, **changes) -> dict | None:
        """The same request with what changed (a draft edited after its card), as a new card under a new id. The old
        entry keeps its closed status; the watcher posts the new one."""
        data = self._load()
        old = next((e for e in data["pending"] if e["id"] == approval_id), None)
        if not old:
            return None
        drop = ("slack_ts", "slack_channel", "updated", "payload_sha256")
        new = {k: v for k, v in old.items() if k not in drop}
        new.update(changes, id=f"a-{uuid.uuid4().hex[:8]}", status="new", created=now_iso(), refreshed_from=approval_id)
        data["pending"].append(new)
        _write(self.path, data)
        return new

    def reask(self, approval_id: str) -> dict | None:
        """Yes, ask again on an expired card: the same request under a new id and a fresh clock, posted as a new
        card by the watcher. The old entry is closed as "reasked"."""
        data = self._load()
        old = next((e for e in data["pending"] if e["id"] == approval_id), None)
        if not old or old.get("status") != "expired":
            return None
        new = {k: v for k, v in old.items() if k not in ("slack_ts", "slack_channel", "updated")}
        new.update(id=f"a-{uuid.uuid4().hex[:8]}", status="new", created=now_iso(), reasked_from=approval_id)
        old["status"], old["updated"] = "reasked", now_iso()
        data["pending"].append(new)
        _write(self.path, data)
        return new

    def prune(self, keep_days: int = 14) -> int:
        data = self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        before = len(data["pending"])
        data["pending"] = [e for e in data["pending"]
                           if e.get("status") in ("new", "posted") or datetime.fromisoformat(e["created"]) > cutoff]
        _write(self.path, data)
        return before - len(data["pending"])


# --- Heartbeat ------------------------------------------------------------------------------------

def heartbeat(job: str, ok: bool, note: str = "", path: Path | None = None) -> None:
    path = path or STATE / "last-run.json"
    data = _read(path, {})
    data[job] = {"at": now_iso(), "ok": ok, "note": note[:300]}
    data["_last"] = {"job": job, "at": data[job]["at"], "ok": ok}
    _write(path, data)
