"""Approval cards v2 (Grok Bot pattern, docs/06): Allow once / Always allow / Deny, expiry, audit log, execution.

The coordinator writes an approval to state/pending-approvals.json. Fields beyond summary/action are optional:
  action_class   "email.send", "calendar.hold", "calendar.event.create", "calendar.event.update",
                 "subagent.install", or anything else (no extra tools: the resumed session just gets the answer)
  draft_id, draft_text, to, subject     for email.send (what the card shows; only that draft can be sent)
  attendees      for calendar classes (emails that may be invited)
  from_timer     true when an unattended run asked; such cards expire after 30 minutes
  proposal       for subagent.install: the folder name under proposals/ (its install.json is what runs)
The bridge grants the one tool a class needs only to the run that carries out the approval; .claude/hooks/
gate_outward.py checks the call matches what was approved. Calendar classes get a one-time token instead, which
tools/gcal.py checks (gateway/approval_tokens.py).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import trust  # noqa: E402

import approval_tokens  # noqa: E402

EXECUTABLE = {
    "email.send": ("mcp__claude_ai_Gmail__send_message",),
    # Calendar changes go through tools/gcal.py, which is always allowed; the gate is the one-time token the bridge
    # issues to the approved run (gateway/approval_tokens.py), so no connector tool is granted (since 2026-11-08).
    "calendar.hold": (),
    "calendar.event.create": (),
    "calendar.event.update": (),
    # Installs run in Python (gateway/installer.py), not through a granted tool; the resumed run only reports.
    "subagent.install": (),
    # Form submits run in the bridge's own browser run with a one-time pass (gateway/browser_agent.py); never auto.
    "web.form.submit": (),
}
# "Always allow" is offered only where a standing rule stays narrow: holds on his own calendar, and sends to the
# exact same recipients. Never for installs, money, or events that invite people.
ALWAYS_ALLOWABLE = {"calendar.hold", "email.send"}
TIMER_CARD_TTL = timedelta(minutes=30)


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except json.JSONDecodeError:
        return default


def recipients(entry: dict) -> list[str]:
    values = entry.get("to") or entry.get("attendees") or []
    if isinstance(values, str):
        values = [values]
    return sorted({str(v).strip().lower() for v in values if str(v).strip()})


def trust_of(entry: dict, root: Path) -> str | None:
    """Least trusted person this action reaches (tools/trust.py), None when it reaches nobody. Decided in code
    here, never taken from the entry, so a stranger cannot be made to look known."""
    return trust.lowest(recipients(entry), root)


def rule_key(entry: dict) -> str:
    return f"{entry.get('action_class')}|{','.join(recipients(entry))}"


def expired(entry: dict, now: datetime | None = None) -> bool:
    # Drafts keep: Michael may tap Send hours later. Other timer cards go stale.
    if not entry.get("from_timer") or entry.get("action_class") == "email.send":
        return False
    now = now or datetime.now(timezone.utc)
    return now - datetime.fromisoformat(entry["created"]) > TIMER_CARD_TTL


def add_always_rule(state: Path, entry: dict) -> None:
    path = state / "always-allow.json"
    rules = _read(path, {})
    rules[rule_key(entry)] = {"since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "summary": entry.get("summary", "")}
    path.write_text(json.dumps(rules, indent=2), encoding="utf-8")


def auto_ok(entry: dict, state: Path, automation: dict) -> str | None:
    """Why this approval may run without a tap, or None. An always-allow rule Michael tapped, or a class he set to
    auto / auto_notify in me/automation.yaml (only for classes where a standing rule is safe)."""
    cls = entry.get("action_class")
    if cls not in ALWAYS_ALLOWABLE:
        return None
    if rule_key(entry) in _read(state / "always-allow.json", {}):
        return "always allowed"
    mode = ((automation or {}).get("actions") or {}).get(cls, {}).get("mode")
    if cls == "calendar.hold" and mode in ("auto", "auto_notify"):
        return f"me/automation.yaml: {cls} is {mode}"
    who = recipients(entry)
    self_mode = ((automation or {}).get("actions") or {}).get("email.send.self", {}).get("mode")
    if cls == "email.send" and who and set(who) <= set(trust.ME) and self_mode == "auto":
        return "me/automation.yaml: email.send.self is auto"
    return None


def execution(entry: dict, state: Path | None = None) -> tuple[tuple[str, ...], dict]:
    """Tools to grant and environment for the run that carries out this approval."""
    cls = entry.get("action_class") or ""
    env = {"COORDINATOR_APPROVED_CLASS": cls}
    if cls == "email.send":
        env["COORDINATOR_APPROVED_DRAFT"] = str(entry.get("draft_id") or "")
    if cls.startswith("calendar."):
        env["COORDINATOR_APPROVED_RECIPIENTS"] = ",".join(recipients(entry))
        if state is not None:
            env["COORDINATOR_APPROVAL_TOKEN"] = approval_tokens.issue(state, str(entry.get("id") or ""), cls,
                                                                      recipients(entry))
    return EXECUTABLE.get(cls, ()), env


CALENDAR_HOW = {
    "calendar.hold": "python tools/gcal.py hold --title ... --start ... --end ... [--note ...]",
    "calendar.event.create": "python tools/gcal.py event --title ... --start ... --end ... --attendee ...",
    "calendar.event.update": "python tools/gcal.py update --id ... [only the fields that change]",
}


def how_to(entry: dict) -> str:
    """The one line the approved run gets on how to carry the action out."""
    cls = entry.get("action_class") or ""
    if cls == "email.send":
        return f" Send draft {entry.get('draft_id')} as is with send_message(draftId=...)."
    if cls in CALENDAR_HOW:
        return (f" Use `{CALENDAR_HOW[cls]}` once (times ISO, Eastern unless an offset is given). The approval is in"
                " this run's environment and works one time only.")
    return ""


def audit(state: Path, event: str, entry: dict, note: str = "") -> None:
    state.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, "id": entry.get("id"),
            "class": entry.get("action_class"), "summary": entry.get("summary", "")[:200], "note": note[:300]}
    with (state / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def signal(state: Path, kind: str, entry: dict, **extra) -> None:
    """One row in state/signals.jsonl for an approval or draft outcome (docs/v2/06-LEARNING-LOOP.md, Signals).
    IDs and class only, never the draft text. Bookkeeping: never breaks the action."""
    try:
        state.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "type": kind, "source": "bridge",
               "approval_id": entry.get("id"), "class": entry.get("action_class"), "draft_id": entry.get("draft_id"),
               "to": entry.get("to"), **{k: v for k, v in extra.items() if v is not None}}
        created = entry.get("created")
        if created:
            row["seconds_to_decision"] = int((datetime.now(timezone.utc) - datetime.fromisoformat(
                str(created).replace("Z", "+00:00"))).total_seconds())
        with (state / "signals.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: v for k, v in row.items() if v is not None}, ensure_ascii=False) + "\n")
    except Exception:
        pass


# --- cards (docs/13 sections 2 and 3) ----------------------------------------------------------------
# Every word that says who is reached and what a button does is built here, in code, from the entry's class and
# recipients, never from Juno's summary (idea 12): a card cannot dress up what it does or who it reaches.

SECTION_MAX = 2900
# action_class: (yes label, overflow options). Always is added separately, only for ALWAYS_ALLOWABLE classes.
YES = {
    "calendar.event.create": ("Yes, invite", [("Other time", "othertime")]),
    "calendar.event.update": ("Yes, move it", [("Other time", "othertime")]),
    "calendar.hold": ("Yes, add it", [("Always add holds", "always"), ("Other time", "othertime")]),
    "subagent.install": ("Yes, install", [("Show files", "showfiles")]),
    "web.form.submit": ("Yes, submit", []),
}
CHANGES = {
    "calendar.event.create": "Adds an event to your calendar and emails the invite",
    "calendar.event.update": "Moves the event; everyone invited is told",
    "calendar.hold": "Adds a hold to your calendar only. No one is told",
    "subagent.install": "Installs a new agent into .claude/agents",
    "web.form.submit": "Submits this form in Juno's own browser. A sent form can't be taken back",
}
FIELDS_MAX = 1900  # one Slack field holds 2000 characters


def _people_relationship(addr: str, root: Path) -> str | None:
    for path in sorted((root / "people").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if addr not in text.lower():
            continue
        for line in text.splitlines():
            if line.lower().startswith("- relationship:"):
                rel = line.split(":", 1)[1].strip()
                rel = rel.split(" (")[0].split(";")[0].strip()
                return rel[:1].upper() + rel[1:] if rel else None
    return None


def _mail_history(addr: str) -> tuple[int, bool] | None:
    """(emails received from addr, whether Michael ever wrote to them), from the local mail index; None without it."""
    try:
        import mail_index
        con = mail_index.connect()
        rows = mail_index.with_address(con, addr, 500)
    except Exception:
        return None
    return sum(1 for r in rows if r["direction"] == "received"), any(r["direction"] == "sent" for r in rows)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def who_line(addr: str, root: Path, history=_mail_history) -> str:
    """How Michael knows them (docs/13 screen 2): the profile's relationship, "In your contacts", or for a stranger
    how many times they wrote and whether he answered. Never "known" or "unknown"."""
    tag = trust.label(addr, root)
    if tag == "michael":
        return "You"
    if tag == "known":
        return _people_relationship(addr, root) or "In your people files"
    if tag == "contact":
        return "In your contacts"
    seen = history(addr)
    if not seen or not seen[0]:
        return "1st email from them"
    count, replied = seen
    return f"{_ordinal(count)} email" + (", you've replied before" if replied else ", no reply yet")


ON_OFF = {"true": "on (checked)", "false": "off"}


def _plain(value) -> str:
    """Text a web page had a hand in (form labels, the button): Slack's escapes, so it can't become a link or a
    mention on the card."""
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _field(label: str, value: str) -> dict:
    return {"type": "mrkdwn", "text": f"*{label}*\n{value or '-'}"[:1900]}


def _quoted(text: str) -> list[dict]:
    """The full draft as quote sections, split by lines so nothing is ever cut (a section holds 3,000 characters)."""
    out, chunk = [], []
    for line in (text or "").strip().splitlines() or [""]:
        piece = "> " + line
        if chunk and len("\n".join(chunk + [piece])) > SECTION_MAX:
            out.append("\n".join(chunk))
            chunk = []
        chunk.append(piece[:SECTION_MAX])
    out.append("\n".join(chunk))
    return [{"type": "section", "text": {"type": "mrkdwn", "text": t}} for t in out]


def _expires(entry: dict) -> str:
    at = datetime.fromisoformat(entry["created"]) + TIMER_CARD_TTL
    return _clock(at)


def _clock(at: datetime) -> str:
    from zoneinfo import ZoneInfo
    local = at.astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%I:%M %p").lstrip("0")


def yes_label(entry: dict) -> str:
    cls = entry.get("action_class") or ""
    if cls == "calendar.event.create" and not recipients(entry):
        return "Yes, add it"
    return YES.get(cls, ("Yes", []))[0]


def _overflow(entry: dict, options: list[tuple[str, str]]) -> dict | None:
    if not options:
        return None
    return {"type": "overflow", "action_id": "approval_more",
            "options": [{"text": {"type": "plain_text", "text": label}, "value": f"{verb}:{entry['id']}"}
                        for label, verb in options[:5]]}


def card_text(entry: dict, trust_label: str | None = None) -> str:
    """The notification line and plain fallback: the bold line or question."""
    return entry.get("summary", "")


def blocks(entry: dict, trust_label: str | None = None, root: Path | None = None) -> list[dict]:
    """The waiting card. No standing rule for strangers: "Always" only when everyone it reaches is known or a
    contact, and never for classes outside ALWAYS_ALLOWABLE."""
    root = root or Path(__file__).resolve().parents[1]
    cls = entry.get("action_class") or ""
    who = recipients(entry)
    if cls == "email.send":
        to = "\n".join(who) or "(see draft)"
        whos = "\n".join(who_line(a, root) for a in who) or "-"
        fields = [_field("To", to), _field("Who", whos), _field("Subject", entry.get("subject", ""))]
        if entry.get("attachments"):
            fields.append(_field("Attached", "\n".join(str(a) for a in entry["attachments"])))
        if entry.get("why"):  # plain words from Juno; `action` is the instruction for the run, never shown here
            fields.append(_field("Why", entry["why"]))
        out = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{entry['summary']}*"}},
               {"type": "section", "fields": fields}]
        out += _quoted(entry.get("draft_text") or "")
        buttons = [{"type": "button", "action_id": "approve", "style": "primary", "value": entry["id"],
                    "text": {"type": "plain_text", "text": "Send"}}]
        if entry.get("draft_link"):
            buttons.append({"type": "button", "action_id": "edit_link", "url": entry["draft_link"],
                            "text": {"type": "plain_text", "text": "Edit in Gmail"}})
        more = ([(f"Always send to {who[0].split('@')[0] if len(who) == 1 else 'them'}", "always")]
                if trust_label != "unknown" else []) + [("Skip", "deny")]
        buttons.append(_overflow(entry, more))
        out.append({"type": "actions", "block_id": f"approval_{entry['id']}", "elements": buttons})
        return out

    facts = [_field("What", entry.get("action", ""))]
    if cls == "web.form.submit":
        facts.append(_field("Site", f"{_plain(entry.get('site'))}\n{_plain(entry.get('url'))}"))
        values = "\n".join(f"{_plain(f.get('label'))}: {_plain(ON_OFF.get(str(f.get('value')).lower(), f.get('value')))}"
                           for f in entry.get("fields") or []) or "(none)"
        facts.append(_field("Values", values[:FIELDS_MAX]))
        facts.append(_field("Button", _plain(entry.get("submit_label"))))
    if cls.startswith("calendar."):
        facts.append(_field("Invites", "\n".join(f"{a} ({who_line(a, root)})" for a in who) or "No one"))
    if cls in CHANGES:
        facts.append(_field("Changes", CHANGES[cls]))
    if entry.get("from_timer") and entry.get("created"):
        facts.append(_field("Expires", _expires(entry)))
    question = entry["summary"] if entry["summary"].rstrip().endswith("?") else f"Okay to go ahead? {entry['summary']}"
    buttons = [{"type": "button", "action_id": "approve", "style": "primary", "value": entry["id"],
                "text": {"type": "plain_text", "text": yes_label(entry)}},
               {"type": "button", "action_id": "deny", "value": entry["id"],
                "text": {"type": "plain_text", "text": "Not now"}}]
    options = list(YES.get(cls, ("Yes", []))[1])
    if trust_label == "unknown" or cls not in ALWAYS_ALLOWABLE:
        options = [o for o in options if o[1] != "always"]
    if (more := _overflow(entry, options)):
        buttons.append(more)
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{question}*"}},
            {"type": "section", "fields": facts},
            {"type": "actions", "block_id": f"approval_{entry['id']}", "elements": buttons}]


def expired_blocks(entry: dict, root: Path | None = None, now: datetime | None = None) -> list[dict]:
    """The same card, edited in place after 30 minutes: struck question, What and Invites, Ask again or drop."""
    root = root or Path(__file__).resolve().parents[1]
    now = now or datetime.now(timezone.utc)
    facts = [_field("What", entry.get("action", ""))]
    who = recipients(entry)
    if (entry.get("action_class") or "").startswith("calendar."):
        facts.append(_field("Invites", "\n".join(who) or "No one"))
    nothing = "Nothing changed" + (", no invite sent." if who else ".")
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"~{entry['summary']}~"}},
            {"type": "section", "fields": facts},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"⏱ Expired {_clock(now)}. {nothing}"}]},
            {"type": "section", "text": {"type": "mrkdwn", "text": "Still want it?"}},
            {"type": "actions", "block_id": f"expired_{entry['id']}", "elements": [
                {"type": "button", "action_id": "reask", "style": "primary", "value": entry["id"],
                 "text": {"type": "plain_text", "text": "Yes, ask again"}},
                {"type": "button", "action_id": "drop", "value": entry["id"],
                 "text": {"type": "plain_text", "text": "No, drop it"}}]}]


def answered_blocks(card: list[dict], line: str) -> list[dict]:
    """After a tap: the card as it was, its buttons swapped for one gray line ("Sent 9:20 AM", "Skipped")."""
    kept = [b for b in card if b.get("type") != "actions"]
    return kept + [{"type": "context", "elements": [{"type": "mrkdwn", "text": line}]}]
