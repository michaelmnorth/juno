"""Typed tools for owner DMs (02-ARCHITECTURE.md, Tool contract).

Each tool wraps an existing script through a Backend object (v2/backend.py for the real one, a fake in tests). The
model sees name, description and schema; the policy engine sees the rest. There is no shell, file or generic HTTP
tool, and no T4 tool: what a run should not do is simply not here.

Only the tools DMs use are ported (P1 brief, deliverable 2). Health, YouTube, finance and research stay on v1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal


class Tier(str, Enum):
    T0 = "T0"    # read
    T1 = "T1"    # private write (drafts, reminders, notes)
    T2 = "T2"    # notify the owner
    T3a = "T3a"  # reversible, owner-only (a hold on his own calendar)
    T3b = "T3b"  # visible to others (send, invite): always a tap


@dataclass
class ToolResult:
    content: object
    untrusted_text: bool = False      # free text an outsider could have written is in `content`
    touched: list[dict] = field(default_factory=list)   # working-set items: {"kind","id","label"}
    is_error: bool = False


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    tier: Tier
    data_classes: frozenset[str]
    returns_untrusted: bool
    idempotency: Literal["safe", "keyed", "none"]
    handler: Callable[..., ToolResult]
    max_result_tokens: int = 800
    action_class: str = ""            # for T3: the approval card's class
    propose: Callable[..., dict] | None = None   # T3: builds the card fields from the input

    def api(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": api_schema(self.input_schema),
                "strict": True}


UNSUPPORTED = ("minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems")


def api_schema(schema):
    """Strict tool schemas reject numeric, string-length and array-size constraints; they stay in our copy and
    `validate` enforces them in code."""
    if isinstance(schema, dict):
        return {k: api_schema(v) for k, v in schema.items() if k not in UNSUPPORTED}
    if isinstance(schema, list):
        return [api_schema(v) for v in schema]
    return schema


def validate(spec: "ToolSpec", args: dict) -> str | None:
    """Returns why the input is invalid, or None. Checks what strict mode cannot."""
    if not isinstance(args, dict):
        return "input must be an object"
    props = spec.input_schema.get("properties", {})
    extra = set(args) - set(props)
    if extra:
        return f"unknown fields: {sorted(extra)}"
    missing = [k for k in spec.input_schema.get("required", []) if k not in args]
    if missing:
        return f"missing: {missing}"
    for key, rule in props.items():
        if key not in args:
            continue
        v = args[key]
        kind = rule.get("type")
        if kind == "integer" and (not isinstance(v, int) or isinstance(v, bool)):
            return f"{key} must be an integer"
        if kind == "string" and not isinstance(v, str):
            return f"{key} must be a string"
        if kind == "boolean" and not isinstance(v, bool):
            return f"{key} must be true or false"
        if kind == "array" and not isinstance(v, list):
            return f"{key} must be a list"
        if kind == "integer" and not rule.get("minimum", v) <= v <= rule.get("maximum", v):
            return f"{key} must be between {rule.get('minimum')} and {rule.get('maximum')}"
        if kind == "array" and not rule.get("minItems", 0) <= len(v) <= rule.get("maxItems", len(v)):
            return f"{key} needs {rule.get('minItems', 0)} to {rule.get('maxItems')} items"
    return None


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required if required is not None else list(props),
            "additionalProperties": False}


S = {"type": "string"}
DATE = {"type": "string", "description": "YYYY-MM-DD, Eastern"}
TIME = {"type": "string", "description": "ISO local time, e.g. 2026-01-31T16:00, Eastern"}


def _ev_items(events: list[dict]) -> list[dict]:
    return [{"kind": "event", "id": e.get("id", ""), "label": f"{e.get('title', '')} {e.get('start', '')}"[:80]}
            for e in events if e.get("id")]


# --- handlers (backend, args, ctx) -> ToolResult -------------------------------------------------------------------

def h_calendar_events(b, a, ctx):
    evs = b.events(a["start_date"], a["days"])
    # Titles of events he made are his words; an invite someone else sent carries their text and taints.
    shown = [{k: e.get(k) for k in ("id", "title", "start", "end", "location", "attendees", "juno_hold")}
             for e in evs[:25]]
    others = any(e.get("attendees") and not e.get("organizer_self", False) for e in evs)
    return ToolResult({"events": shown, "more": max(0, len(evs) - 25)}, untrusted_text=others,
                      touched=_ev_items(evs[:5]))


def h_calendar_free(b, a, ctx):
    slots = b.free(a["start_date"], a["days"], a["minutes"], a["window"])
    return ToolResult({"slots": slots[:12], "more": max(0, len(slots) - 12)})


def h_calendar_check(b, a, ctx):
    return ToolResult(b.check(a["start"], a["end"]))


def h_calendar_hold(b, a, ctx):
    made = b.hold(a["title"], a["start"], a["end"], a.get("note", ""))
    return ToolResult({"done": True, "hold": made},
                      touched=[{"kind": "hold", "id": made.get("id", ""), "label": f"{a['title']} {a['start']}"}])


def h_calendar_undo_hold(b, a, ctx):
    return ToolResult({"done": True, "removed": b.undo_hold(a["event_id"])})


def h_mail_search(b, a, ctx):
    found = b.mail_search(a["query"], min(a["limit"], 10))
    return ToolResult({"messages": found}, untrusted_text=bool(found),
                      touched=[{"kind": "message", "id": m["id"], "label": f"from {m.get('from', '')}"[:80]}
                               for m in found[:5]])


def h_mail_read(b, a, ctx):
    """The reader class: a separate no-tool call digests the body into typed fields. Only those reach this run."""
    msg = b.mail_body(a["message_id"])
    fields = ctx.reader(msg)
    fields["from"] = msg.get("from", "")
    fields["trust"] = b.trust(msg.get("from", ""))
    gist = fields.pop("gist", "")
    if msg.get("attachments"):  # types and sizes only, from code: a file name is the sender's text
        fields["attachments"] = [{"type": str(x.get("type", ""))[:60], "kb": int(x.get("kb", 0))}
                                 for x in msg["attachments"][:10]]
        fields["attachments_note"] = ("You can't open attachments. If he wants one read or reviewed, set hand_off: "
                                      "the full assistant can open it.")
    if a.get("include_gist"):
        fields["gist"] = gist  # free text: taints the run
    return ToolResult(fields, untrusted_text=bool(a.get("include_gist")),
                      touched=[{"kind": "message", "id": a["message_id"], "label": f"from {fields['from']}"[:80]}])


def h_mail_draft(b, a, ctx):
    made = b.draft(a["to"], a["subject"], a["body"], a.get("reply_to_message_id", ""), a.get("context", ""))
    return ToolResult({"draft": made},
                      touched=[{"kind": "draft", "id": made.get("draft_id", ""), "label": f"to {a['to']}"[:80]}])


def h_people(b, a, ctx):
    return ToolResult({"people": b.people(a["name"])})


def h_contact_email(b, a, ctx):
    return ToolResult({"matches": b.contact_email(a["name"])})


def h_reminders_add(b, a, ctx):
    made = b.reminder_add(a["text"], a["due"], tainted=ctx.tainted)
    return ToolResult({"done": True, "reminder": made},
                      touched=[{"kind": "reminder", "id": made.get("id", ""), "label": a["text"][:60]}])


def h_reminders_list(b, a, ctx):
    return ToolResult({"reminders": b.reminders()[:20]})


def h_notes_add(b, a, ctx):
    return ToolResult({"done": True, "note": b.note_add(a["text"], tainted=ctx.tainted)})


def h_notes_search(b, a, ctx):
    return ToolResult({"notes": b.notes_search(a["terms"])[:15]})


def h_proposed(b, a, ctx):  # T3b tools never run a handler; the policy engine turns them into a card
    return ToolResult({"error": "this action needs Michael's tap"}, is_error=True)


# --- proposals: the card fields, built by code from the typed input ------------------------------------------------

def p_hold(b, a):
    return {"action_class": "calendar.hold", "summary": f"Hold on your calendar: {a['title']}",
            "action": f"Hold \"{a['title']}\" from {a['start']} to {a['end']}", "title": a["title"],
            "start": a["start"], "end": a["end"]}


def p_invite(b, a):
    who = ", ".join(a["attendees"])
    return {"action_class": "calendar.event.create", "summary": f"Invite {who}: {a['title']}",
            "action": f"Create \"{a['title']}\" from {a['start']} to {a['end']}"
                      + (f" at {a['location']}" if a.get("location") else "") + f", inviting {who}",
            "title": a["title"], "start": a["start"], "end": a["end"], "attendees": a["attendees"]}


def p_move(b, a):
    return {"action_class": "calendar.event.update", "summary": f"Move an event to {a['start']}",
            "action": f"Move the event to {a['start']} until {a['end']} (invitees get the update)",
            "event_id": a["event_id"], "start": a["start"], "end": a["end"]}


def p_send(b, a):
    d = b.draft_info(a["draft_id"])
    return {"action_class": "email.send", "summary": f"Send your reply to {d['to']}: {d['subject']}",
            "action": f"Send the draft to {d['to']}", "draft_id": a["draft_id"], "to": d["to"],
            "subject": d["subject"], "draft_text": d["text"], "draft_link": d.get("link", "")}


# --- the registry ------------------------------------------------------------------------------------------------

def _t(name, desc, props, tier, classes, handler, *, required=None, untrusted=False, idem="safe", action="",
       propose=None) -> ToolSpec:
    return ToolSpec(name, desc, _schema(props, required), tier, frozenset(classes), untrusted, idem, handler,
                    action_class=action, propose=propose)


TOOLS: dict[str, ToolSpec] = {t.name: t for t in [
    _t("calendar_events", "List his calendar events for a date range.",
       {"start_date": DATE, "days": {"type": "integer", "minimum": 1, "maximum": 31}}, Tier.T0, ["calendar"],
       h_calendar_events, untrusted=True),  # invites carry other people's titles
    _t("calendar_free", "Free slots in his calendar. Window like 08:00-21:00.",
       {"start_date": DATE, "days": {"type": "integer", "minimum": 1, "maximum": 14},
        "minutes": {"type": "integer", "minimum": 5, "maximum": 600}, "window": S}, Tier.T0, ["calendar"],
       h_calendar_free),
    _t("calendar_check", "Check one time range for conflicts.", {"start": TIME, "end": TIME}, Tier.T0,
       ["calendar"], h_calendar_check),
    _t("calendar_hold", "Put a private hold on his calendar (nobody invited).",
       {"title": S, "start": TIME, "end": TIME, "note": S}, Tier.T3a, ["calendar"], h_calendar_hold,
       required=["title", "start", "end", "note"], idem="none", action="calendar.hold", propose=p_hold),
    _t("calendar_undo_hold", "Remove a hold Juno made.", {"event_id": S}, Tier.T3a, ["calendar"],
       h_calendar_undo_hold, idem="safe", action="calendar.hold"),
    _t("calendar_invite", "Propose an event that invites people. Michael approves with a tap.",
       {"title": S, "start": TIME, "end": TIME, "location": S,
        "attendees": {"type": "array", "items": S, "minItems": 1, "maxItems": 10}}, Tier.T3b, ["calendar"],
       h_proposed, action="calendar.event.create", propose=p_invite),
    _t("calendar_move", "Propose moving an existing event. Michael approves with a tap.",
       {"event_id": S, "start": TIME, "end": TIME}, Tier.T3b, ["calendar"], h_proposed,
       action="calendar.event.update", propose=p_move),
    _t("mail_search", "Search his Gmail (Gmail query syntax). Returns sender, date, subject, ids.",
       {"query": S, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, Tier.T0, ["mail"], h_mail_search,
       untrusted=True),
    _t("mail_read", "Read one email as typed fields (what it asks for, dates, amounts). include_gist adds a "
                    "one-line summary, which limits what you can do afterwards.",
       {"message_id": S, "include_gist": {"type": "boolean"}}, Tier.T0, ["mail"], h_mail_read, untrusted=True),
    _t("mail_draft", "Save a Gmail draft in his voice. Never sends. context: friend, family, date or business, "
                     "with the name.",
       {"to": S, "subject": S, "body": S, "reply_to_message_id": S, "context": S}, Tier.T1, ["mail"],
       h_mail_draft, idem="keyed"),
    _t("mail_send", "Propose sending one saved draft. Michael approves with a tap.", {"draft_id": S}, Tier.T3b,
       ["mail"], h_proposed, action="email.send", propose=p_send),
    _t("people_lookup", "What Juno knows about a person in his life, by name.", {"name": S}, Tier.T0, ["people"],
       h_people),
    _t("contact_email", "Email address for a name from his Contacts.", {"name": S}, Tier.T0, ["people"],
       h_contact_email),
    _t("reminder_add", "Set a reminder. due is ISO local time, Eastern.", {"text": S, "due": TIME}, Tier.T1,
       ["notes"], h_reminders_add, idem="none"),
    _t("reminders_list", "His open reminders.", {}, Tier.T0, ["notes"], h_reminders_list),
    _t("note_add", "Save a dated note in his words.", {"text": S}, Tier.T1, ["notes"], h_notes_add, idem="none"),
    _t("notes_search", "Search his notes and what he said before.", {"terms": S}, Tier.T0, ["notes"],
       h_notes_search),
]}

# Tool sets per playbook (block 1). Sorted so the serialised tool list is byte-stable for the cache.
PLAYBOOK_TOOLS = {
    "calendar": ["calendar_check", "calendar_events", "calendar_free", "calendar_hold", "calendar_invite",
                 "calendar_move", "calendar_undo_hold", "contact_email", "people_lookup", "reminder_add"],
    "mail": ["contact_email", "mail_draft", "mail_read", "mail_search", "mail_send", "people_lookup"],
    "people": ["calendar_events", "contact_email", "note_add", "notes_search", "people_lookup"],
    "notes": ["note_add", "notes_search", "reminder_add", "reminders_list"],
    "general": ["calendar_events", "note_add", "notes_search", "people_lookup", "reminder_add", "reminders_list"],
}


def for_playbook(playbook: str) -> list[ToolSpec]:
    return [TOOLS[n] for n in sorted(PLAYBOOK_TOOLS.get(playbook, PLAYBOOK_TOOLS["general"]))]


def api_tools(specs: list[ToolSpec]) -> list[dict]:
    return [s.api() for s in specs]


def cap(content: object, max_tokens: int) -> str:
    """Serialise a result compactly and cap it (about 4 characters a token)."""
    text = json.dumps(content, ensure_ascii=False, separators=(",", ":"), default=str)
    limit = max_tokens * 4
    return text if len(text) <= limit else text[:limit] + '..."(cut: ask for less)"'
