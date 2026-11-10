"""Juno's own Google Calendar access: read events, add holds, and make approved changes, through the same OAuth app
as google_read.py. Michael's primary calendar only.

  python tools/gcal.py events [--from 2026-11-09] [--days 7]
      Compact list: id, start, end, title, location, attendee count, busy, and whether Juno made it.
  python tools/gcal.py hold --title "..." --start ISO --end ISO [--note "..."]
      A block on his own calendar, no attendees, no Meet link, nobody notified. Marked as Juno's, so it can be undone.
  python tools/gcal.py undo-hold --id EVENT_ID
      Deletes a hold, only one Juno made and only while it has no attendees.
  python tools/gcal.py event --title "..." --start ISO --end ISO [--location ...] [--description ...]
                             [--attendee a@b.com ...]
  python tools/gcal.py update --id EVENT_ID [--title] [--start] [--end] [--location] [--description] [--attendee ...]
      Invites go out (sendUpdates=all), so these need an approval: the bridge gives the run that carries it out a
      one-time token (gateway/approval_tokens.py), and only the approved people may be invited.

Holds run straight away while me/automation.yaml has calendar.hold as auto or auto_notify (Juno then tells Michael
in plain words), and are logged to state/audit.jsonl; set it to ask and they need an approval like events. Times are ISO 8601; without an offset they're Eastern. Exit codes as google_read.py: 0 ok, 3 not
signed in, 4 Google refused or not approved, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import approval_policy  # noqa: E402
import approval_tokens  # noqa: E402
import google_read  # noqa: E402
from google_read import BAD_INPUT, CALENDAR, OK, REFUSED, GoogleError  # noqa: E402

STATE = google_read.ROOT / "state"
ZONE = "America/New_York"
MARK = {"private": {"juno": "hold"}}
EMAIL_RE = re.compile(r"^[^@\s,<>]+@[^@\s,<>]+\.[^@\s,<>]+$")
MAX_HOLD, MAX_EVENT = timedelta(hours=12), timedelta(hours=24)
MAX_TITLE, MAX_TEXT, MAX_ATTENDEES = 120, 2000, 20


def _bad(message: str) -> GoogleError:
    return GoogleError(BAD_INPUT, message)


def when(value: str) -> dict:
    """A Calendar API time: ISO with an offset as is, without one in Eastern."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _bad(f"not an ISO time: {value!r} (for example 2026-11-12T18:30)")
    return {"dateTime": parsed.isoformat(timespec="seconds"), "timeZone": ZONE}


def span(start: str, end: str, longest: timedelta) -> tuple[dict, dict]:
    a, b = datetime.fromisoformat(when(start)["dateTime"]), datetime.fromisoformat(when(end)["dateTime"])
    if (a.tzinfo is None) != (b.tzinfo is None):
        raise _bad("give both times with an offset, or both without")
    if b <= a:
        raise _bad("the end must be after the start")
    if b - a > longest:
        raise _bad(f"longer than {int(longest.total_seconds() // 3600)} hours")
    return when(start), when(end)


def one_line(text: str, name: str, limit: int = MAX_TITLE) -> str:
    text = (text or "").strip()
    if not text or "\n" in text or len(text) > limit:
        raise _bad(f"{name} must be one line, 1 to {limit} characters")
    return text


def attendees(values: list[str]) -> list[str]:
    out = sorted({v.strip().lower() for value in values for v in value.split(",") if v.strip()})
    if len(out) > MAX_ATTENDEES:
        raise _bad(f"at most {MAX_ATTENDEES} attendees")
    for a in out:
        if not EMAIL_RE.match(a):
            raise _bad(f"not an email address: {a!r}")
    return out


def approved(classes: tuple[str, ...], invited: set[str], env=None, state: Path = STATE) -> str:
    env = os.environ if env is None else env
    token = env.get("COORDINATOR_APPROVAL_TOKEN", "")
    record, why = approval_tokens.check(state, token, classes, invited)
    if not record:
        raise GoogleError(REFUSED, f"not approved: {why}")
    return token


def _short(event: dict) -> dict:
    start, end = event.get("start", {}), event.get("end", {})
    return {"id": event.get("id"), "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"), "title": event.get("summary", "(no title)"),
            "location": event.get("location", ""), "attendees": len(event.get("attendees", [])),
            "busy": event.get("transparency") != "transparent",
            "juno_hold": event.get("extendedProperties", {}).get("private", {}).get("juno") == "hold",
            "link": event.get("htmlLink", "")}


def events(start: str = "", days: int = 7, token: str | None = None, get=None) -> list[dict]:
    get = get or google_read._get
    if not 1 <= days <= 62:
        raise _bad("--days must be 1 to 62")
    first = date.fromisoformat(start) if start else date.today()
    token = token or google_read.access_token()
    zone = ZoneInfo(ZONE)
    got = get(CALENDAR, token, {"timeMin": datetime(first.year, first.month, first.day, tzinfo=zone).isoformat(),
                                "timeMax": datetime.combine(first + timedelta(days=days), datetime.min.time(),
                                                            tzinfo=zone).isoformat(),
                                "singleEvents": "true", "orderBy": "startTime", "maxResults": 250})
    return [_short(e) for e in got.get("items", []) if e.get("status") != "cancelled"]


def hold(title: str, start: str, end: str, note: str = "", env=None, state: Path = STATE,
         token: str | None = None, call=None, mode=google_read.automation_mode) -> dict:
    call = call or google_read.call
    begin, finish = span(start, end, MAX_HOLD)
    body = {"summary": one_line(title, "the title"), "start": begin, "end": finish, "extendedProperties": MARK,
            "transparency": "opaque", "visibility": "private"}
    if note:
        body["description"] = note.strip()[:MAX_TEXT]
    env = os.environ if env is None else env
    direct = not env.get("COORDINATOR_APPROVAL_TOKEN") and mode("calendar.hold") in ("auto", "auto_notify")
    spent = "" if direct else approved(("calendar.hold",), set(), env, state)
    token = token or google_read.access_token()
    made = call("POST", CALENDAR, token, body, {"sendUpdates": "none"})
    if spent:
        approval_tokens.spend(state, spent)
    out = _short(made)
    if direct:
        approval_policy.audit(state, "auto_hold", {"id": out["id"], "action_class": "calendar.hold",
                                                   "summary": f"{body['summary']} {begin['dateTime']}"},
                              "me/automation.yaml calendar.hold")
    return out


def undo_hold(event_id: str, token: str | None = None, call=None, get=None) -> dict:
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    event = get(f"{CALENDAR}/{event_id}", token)
    if not _short(event)["juno_hold"]:
        raise GoogleError(REFUSED, "not a hold Juno made; Michael removes it himself")
    if event.get("attendees"):
        raise GoogleError(REFUSED, "this hold has attendees now; Michael removes it himself")
    call("DELETE", f"{CALENDAR}/{event_id}", token, None, {"sendUpdates": "none"})
    return {"removed": event_id, "title": event.get("summary", "")}


def event(title: str, start: str, end: str, location: str = "", description: str = "",
          invite: list[str] | None = None, env=None, state: Path = STATE, token: str | None = None,
          call=None) -> dict:
    call = call or google_read.call
    begin, finish = span(start, end, MAX_EVENT)
    people = attendees(invite or [])
    body = {"summary": one_line(title, "the title"), "start": begin, "end": finish,
            "attendees": [{"email": a} for a in people]}
    if location:
        body["location"] = one_line(location, "the location", 300)
    if description:
        body["description"] = description.strip()[:MAX_TEXT]
    spent = approved(("calendar.event.create",), set(people), env, state)
    token = token or google_read.access_token()
    made = call("POST", CALENDAR, token, body, {"sendUpdates": "all"})
    approval_tokens.spend(state, spent)
    return _short(made)


def update(event_id: str, title: str = "", start: str = "", end: str = "", location: str = "",
           description: str = "", invite: list[str] | None = None, env=None, state: Path = STATE,
           token: str | None = None, call=None, get=None) -> dict:
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    current = get(f"{CALENDAR}/{event_id}", token)
    patch: dict = {}
    if title:
        patch["summary"] = one_line(title, "the title")
    if start or end:
        old_start = current.get("start", {}).get("dateTime", "")
        old_end = current.get("end", {}).get("dateTime", "")
        patch["start"], patch["end"] = span(start or old_start, end or old_end, MAX_EVENT)
    if location:
        patch["location"] = one_line(location, "the location", 300)
    if description:
        patch["description"] = description.strip()[:MAX_TEXT]
    new_people: set[str] = set()
    if invite:
        have = {a.get("email", "").lower() for a in current.get("attendees", [])}
        people = attendees(invite)
        new_people = set(people) - have
        patch["attendees"] = current.get("attendees", []) + [{"email": a} for a in sorted(new_people)]
    if not patch:
        raise _bad("nothing to change")
    spent = approved(("calendar.event.update",), new_people, env, state)
    made = call("PATCH", f"{CALENDAR}/{event_id}", token, patch, {"sendUpdates": "all"})
    approval_tokens.spend(state, spent)
    return _short(made)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gcal.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("events")
    ev.add_argument("--from", dest="start", default="")
    ev.add_argument("--days", type=int, default=7)
    h = sub.add_parser("hold")
    h.add_argument("--title", required=True)
    h.add_argument("--start", required=True)
    h.add_argument("--end", required=True)
    h.add_argument("--note", default="")
    u = sub.add_parser("undo-hold")
    u.add_argument("--id", required=True)
    for name in ("event", "update"):
        e = sub.add_parser(name)
        if name == "update":
            e.add_argument("--id", required=True)
        e.add_argument("--title", required=name == "event", default="")
        e.add_argument("--start", required=name == "event", default="")
        e.add_argument("--end", required=name == "event", default="")
        e.add_argument("--location", default="")
        e.add_argument("--description", default="")
        e.add_argument("--attendee", action="append", default=[])
    return p


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    try:
        args = parser().parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        google_read.load_secrets()
        if args.cmd == "events":
            out = events(args.start, args.days)
        elif args.cmd == "hold":
            out = hold(args.title, args.start, args.end, args.note)
        elif args.cmd == "undo-hold":
            out = undo_hold(args.id)
        elif args.cmd == "event":
            out = event(args.title, args.start, args.end, args.location, args.description, args.attendee)
        else:
            out = update(args.id, args.title, args.start, args.end, args.location, args.description, args.attendee)
        print(json.dumps(out))  # ASCII-safe: the Windows console chokes on emoji in titles
        return OK
    except GoogleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
