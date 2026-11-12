"""The real backend for v2's typed tools: thin calls into the existing scripts in tools/ (keep the code; wrap, type
and tier it). Tests use a fake with the same methods. Secrets stay inside those scripts; nothing here sees one.

It reads the instance's own files (me/, people/, observed/, state/, domains/admin/notes/) at run time. The build
plane never opens them (docs/v2/BUILD-RULES.md).
"""
from __future__ import annotations

import base64
import email
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("America/New_York")
for _p in (ROOT / "tools", ROOT / "gateway"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _lines(path: Path, limit: int = 60) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")][:limit]


def attachment_parts(payload: dict) -> list[dict]:
    """Attached files in a Gmail payload: mime type and size only (the name is the sender's text)."""
    out, stack = [], [payload]
    while stack:
        part = stack.pop()
        stack.extend(part.get("parts") or [])
        body = part.get("body") or {}
        if part.get("filename") and body.get("attachmentId"):
            out.append({"type": part.get("mimeType", ""), "kb": round((body.get("size") or 0) / 1024)})
    return out


def _undated(line: str) -> str:
    return re.sub(r"^- \d{4}-\d{2}-\d{2}: ", "- ", line)


class RealBackend:
    def __init__(self, root: Path = ROOT, quiet_hours=None):
        self.root = Path(root)
        self._quiet = quiet_hours or (lambda: False)

    # --- calendar ---------------------------------------------------------------------------------------------
    def events(self, start: str, days: int) -> list[dict]:
        import gcal
        return gcal.events(start, days)

    def free(self, start: str, days: int, minutes: int, window: str) -> list[dict]:
        import slots
        from datetime import date
        first = date.fromisoformat(start)
        spans = slots.busy_spans(self.events(first.isoformat(), days))
        return slots.free(spans, first, days, minutes, slots._window(window), 15)

    def check(self, start: str, end: str) -> dict:
        import slots
        a, b = slots._dt(start), slots._dt(end)
        first = a.astimezone(ZONE).date()
        spans = slots.busy_spans(self.events(first.isoformat(), (b.astimezone(ZONE).date() - first).days + 1))
        return slots.check(spans, a, b)

    def hold(self, title: str, start: str, end: str, note: str = "") -> dict:
        import gcal
        return gcal.hold(title, start, end, note)

    def undo_hold(self, event_id: str) -> dict:
        import gcal
        return gcal.undo_hold(event_id)

    # --- mail ---------------------------------------------------------------------------------------------------
    def mail_search(self, query: str, limit: int) -> list[dict]:
        import google_read
        token = google_read.access_token()
        got = google_read._get(f"{google_read.GMAIL}/messages", token, {"q": query, "maxResults": limit})
        out = []
        for m in got.get("messages", [])[:limit]:
            meta = google_read._get(f"{google_read.GMAIL}/messages/{m['id']}", token,
                                    {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
            h = {x["name"].lower(): x["value"] for x in meta.get("payload", {}).get("headers", [])}
            addr = next((a for _, a in getaddresses([h.get("from", "")]) if a), "")
            out.append({"id": m["id"], "thread_id": meta.get("threadId", ""), "from": addr.lower(),
                        "trust": self.trust(addr), "date": h.get("date", "")[:31], "subject": h.get("subject", "")[:120]})
        return out

    def mail_body(self, message_id: str) -> dict:
        import google_read
        import inbox
        token = google_read.access_token()
        msg = google_read._get(f"{google_read.GMAIL}/messages/{message_id}", token, {"format": "full"})
        payload = msg.get("payload", {})
        h = {x["name"].lower(): x["value"] for x in payload.get("headers", [])}
        addr = next((a for _, a in getaddresses([h.get("from", "")]) if a), "")
        return {"from": addr.lower(), "subject": h.get("subject", ""), "date": h.get("date", ""),
                "text": inbox.body_text(payload)[:12000], "attachments": attachment_parts(payload)}

    def trust(self, address: str) -> str:
        import trust
        return trust.label(address, self.root) if address else "unknown"

    def draft(self, to: str, subject: str, body: str, reply_to: str = "", context: str = "") -> dict:
        import gmail
        return gmail.draft([to], [], subject, body, reply_to=reply_to, context=context or "unspecified")

    def draft_info(self, draft_id: str) -> dict:
        import gmail
        import google_read
        token = google_read.access_token()
        got = google_read._get(f"{google_read.GMAIL}/drafts/{draft_id}", token, {"format": "raw"}).get("message", {})
        raw = got.get("raw", "")
        msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        to = ", ".join(a for _, a in getaddresses(msg.get_all("To", [])) if a)
        return {"to": to, "subject": str(msg.get("Subject", "")), "text": gmail._norm(gmail._plain_body(msg)),
                "link": gmail.link(got.get("id", "")), "attachments": gmail.attachment_names(msg)}

    # --- people -------------------------------------------------------------------------------------------------
    def people(self, name: str) -> list[dict]:
        import people_match
        q = name.strip().lower()
        out = []
        for p in people_match.profiles(self.root / "people"):
            names = {p["name"].lower(), *(f.lower() for f in p["firsts"]), *(a.lower() for a in p["aliases"])}
            if q and any(q == n or q in n.split() for n in names):
                out.append({"name": p["name"], "lines": [_undated(l) for l in _lines(self.root / p["file"], 25)]})
        return out[:3]

    def contact_email(self, name: str) -> dict:
        import contacts
        try:
            return contacts.email_for(contacts.load(), name)
        except contacts.ToolError as exc:
            return {"ambiguous": False, "candidates": [], "note": str(exc)}

    # --- reminders and notes ------------------------------------------------------------------------------------
    def reminder_add(self, text: str, due: str, tainted: bool = False) -> dict:
        import yaml
        path = self.root / "state" / "reminders.yaml"
        items = (yaml.safe_load(path.read_text(encoding="utf-8")) or []) if path.exists() else []
        at = datetime.fromisoformat(due)
        at = at if at.tzinfo else at.replace(tzinfo=ZONE)
        item = {"id": f"r-{datetime.now(ZONE):%Y-%m-%d}-{uuid.uuid4().hex[:4]}", "text": text[:300],
                "due": at.isoformat(timespec="seconds"), "created": datetime.now(ZONE).isoformat(timespec="seconds"),
                "status": "open", **({"tainted": True} if tainted else {})}
        items.append(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return {"id": item["id"], "due": item["due"]}

    def reminders(self) -> list[dict]:
        import yaml
        path = self.root / "state" / "reminders.yaml"
        items = (yaml.safe_load(path.read_text(encoding="utf-8")) or []) if path.exists() else []
        return sorted([{"text": r.get("text", ""), "due": str(r.get("due", ""))} for r in items
                       if r.get("status", "open") == "open"], key=lambda r: r["due"])

    def note_add(self, text: str, tainted: bool = False) -> dict:
        now = datetime.now(ZONE)
        path = self.root / "domains" / "admin" / "notes" / f"{now:%Y-%m}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        head = f"## {now:%Y-%m-%d}"
        add = ("" if head in existing else f"\n{head}\n") + f"- {text.strip()[:500]}" + \
            (" (from a conversation with outside text, unverified)" if tainted else "") + "\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(add)
        return {"saved": f"{now:%Y-%m-%d}"}

    def notes_search(self, terms: str) -> list[str]:
        words = [w.lower() for w in terms.split() if len(w) > 2][:6]
        if not words:
            return []
        hits = []
        for path in sorted((self.root / "domains" / "admin" / "notes").glob("*.md"), reverse=True):
            day = ""
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("## "):
                    day = line[3:].strip()
                elif any(w in line.lower() for w in words):
                    hits.append(f"{day} {line.strip()}")
        return hits[:15]

    # --- context for the assembler ------------------------------------------------------------------------------
    def core_card(self) -> str:
        """Block 3: how he wants Juno to work first, then who he is, undated, from me/profile.md."""
        lines = _lines(self.root / "me" / "profile.md", 200)
        text = (self.root / "me" / "profile.md")
        try:
            raw = text.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        sections, current = {}, ""
        for line in raw.splitlines():
            if line.startswith("## "):
                current = line[3:].strip()
            elif line.startswith("- ") and current:
                sections.setdefault(current, []).append(_undated(line.strip()))
        order = ["How he wants Juno to work", "Michael"]
        picked = [l for s in order for l in sections.get(s, [])]
        return "\n".join(picked or lines)

    def voice(self) -> str:
        return "\n".join(_undated(l) for l in _lines(self.root / "me" / "voice.md", 40))

    def snapshot(self, now: datetime) -> list[str]:
        out = []
        try:
            local = now.astimezone(ZONE)
            for e in self.events(local.date().isoformat(), 2)[:8]:
                who = f", with {e['attendees']} people" if e.get("attendees") else ""
                title = "an event" if e.get("attendees") else e.get("title", "")  # invite titles are others' text
                out.append(f"- {e.get('start', '')}: {title}{who} (id {e.get('id', '')})")
        except Exception:
            out.append("- calendar unavailable right now")
        for r in self.reminders():
            try:
                due = datetime.fromisoformat(r["due"])
            except ValueError:
                continue
            if due <= now + timedelta(days=2):
                out.append(f"- reminder {r['due']}: {r['text']}")
        try:
            pending = json.loads((self.root / "state" / "pending-approvals.json").read_text(encoding="utf-8-sig"))
            waiting = [p for p in pending.get("pending", []) if p.get("status") in ("new", "posted")]
            if waiting:
                out.append(f"- {len(waiting)} card(s) waiting for his tap")
        except (OSError, ValueError):
            pass
        return out

    def memory(self, entities: list[str], slots: list[str]) -> list[dict]:
        out = []
        for name in entities:
            for p in self.people(name):
                out.append({"source": f"profile of {p['name']}", "trust": "confirmed",
                            "text": " ".join(p["lines"][:12])})
        files = {"routines": ("me/schedule.md", "confirmed"), "goals": ("me/goals.md", "confirmed"),
                 "preferences": ("observed/preferences.md", "observed")}
        for slot in slots:
            if slot in files:
                rel, trust = files[slot]
                out.append({"source": rel.split("/")[-1].removesuffix(".md"), "trust": trust,
                            "text": " ".join(_undated(l) for l in _lines(self.root / rel, 20))})
        return out

    def quiet_hours(self) -> bool:
        try:
            return bool(self._quiet())
        except Exception:
            return False

    def automation_mode(self, cls: str) -> str:
        import google_read
        return google_read.automation_mode(cls, self.root)
