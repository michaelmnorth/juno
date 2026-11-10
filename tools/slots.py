"""Tempo's time math, in code: free slots, conflict checks and exact times, from Michael's calendar.

The calendar agent never adds minutes or converts zones in its head; it asks this. Read-only toward Google.

  python tools/slots.py free --from YYYY-MM-DD [--days 7] [--min 30] [--window 08:00-21:00] [--buffer 15]
      Free gaps between busy events inside the daily window, at least --min minutes after the buffer on both sides.
  python tools/slots.py check --start ISO --end ISO [--buffer 0]
      The busy events that overlap that time (with the buffer). {"free": bool, "conflicts": [...]}
  python tools/slots.py when "YYYY-MM-DD HH:MM" [--zone America/New_York] [--minutes 60]
      The exact time with its offset and weekday, plus Michael's Eastern time: check a parsed day before using it.

Times without an offset are Eastern. Exit codes: 0 ok, 5 bad input; Google errors as in gcal.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

ZONE = ZoneInfo("America/New_York")
OK, BAD_INPUT = 0, 5
MAX_DAYS = 31


def _dt(value: str, zone: ZoneInfo = ZONE) -> datetime:
    v = value.strip().replace("Z", "+00:00")
    if len(v) == 10:  # an all-day event's date
        return datetime.combine(date.fromisoformat(v), time.min, tzinfo=zone)
    d = datetime.fromisoformat(v.replace(" ", "T", 1))
    return d if d.tzinfo else d.replace(tzinfo=zone)


def busy_spans(events: list[dict]) -> list[tuple[datetime, datetime, str]]:
    """Busy events from `gcal.py events` as sorted (start, end, title). Free ("transparent") events don't block."""
    spans = [(_dt(e["start"]), _dt(e["end"]), e.get("title", "")) for e in events
             if e.get("busy", True) and e.get("start") and e.get("end")]
    return sorted(spans)


def label(start: datetime, end: datetime) -> str:
    a, b = start.astimezone(ZONE), end.astimezone(ZONE)
    def hm(d: datetime) -> str:
        return f"{d:%I:%M %p}".lstrip("0").replace(":00 ", " ")
    return f"{a:%a %b} {a.day}, {hm(a)} to {hm(b)}"


def free(spans, first: date, days: int, minimum: int, window: tuple[time, time], buffer: int,
         now: datetime | None = None) -> list[dict]:
    if not 1 <= days <= MAX_DAYS or minimum < 5 or buffer < 0 or window[0] >= window[1]:
        raise ValueError(f"need 1-{MAX_DAYS} days, --min of 5 or more, --buffer of 0 or more, and a window start before its end")
    pad, need = timedelta(minutes=buffer), timedelta(minutes=minimum)
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    out = []
    for n in range(days):
        day = first + timedelta(days=n)
        cursor = max(datetime.combine(day, window[0], tzinfo=ZONE), now)
        stop = datetime.combine(day, window[1], tzinfo=ZONE)
        for s, e, _ in spans:
            if e + pad <= cursor or s - pad >= stop:
                continue
            if s - pad - cursor >= need:
                out.append((cursor, s - pad))
            cursor = max(cursor, e + pad)
        if stop - cursor >= need:
            out.append((cursor, stop))
    return [{"start": a.isoformat(), "end": b.isoformat(), "minutes": int((b - a).total_seconds() // 60),
             "label": label(a, b)} for a, b in out]


def check(spans, start: datetime, end: datetime, buffer: int = 0) -> dict:
    if end <= start:
        raise ValueError("the end must be after the start")
    pad = timedelta(minutes=buffer)
    hits = [{"title": t, "start": s.isoformat(), "end": e.isoformat(), "label": label(s, e)}
            for s, e, t in spans if s - pad < end and e + pad > start]
    return {"free": not hits, "conflicts": hits, "asked": label(start, end)}


def when(value: str, zone: str = "America/New_York", minutes: int = 0) -> dict:
    z = ZoneInfo(zone)
    start = _dt(value, z)
    out = {"iso": start.isoformat(), "weekday": f"{start:%A}", "eastern": label(start, start).split(" to ")[0]}
    if minutes:
        end = start + timedelta(minutes=minutes)
        out.update(end=end.isoformat(), label=label(start, end))
    return out


def _window(text: str) -> tuple[time, time]:
    a, b = text.split("-", 1)
    return time.fromisoformat(a.strip()), time.fromisoformat(b.strip())


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("free")
    f.add_argument("--from", dest="start", default="")
    f.add_argument("--days", type=int, default=7)
    f.add_argument("--min", dest="minimum", type=int, default=30)
    f.add_argument("--window", default="08:00-21:00")
    f.add_argument("--buffer", type=int, default=15)
    c = sub.add_parser("check")
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--buffer", type=int, default=0)
    w = sub.add_parser("when")
    w.add_argument("at")
    w.add_argument("--zone", default="America/New_York")
    w.add_argument("--minutes", type=int, default=0)
    return p


def main(argv: list[str], get_events=None) -> int:
    import google_read
    from gcal import GoogleError, events
    if get_events is None:
        relaunched = google_read.ensure_venv([__file__, *argv])
        if relaunched is not None:
            return relaunched
    try:
        args = parser().parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        if args.cmd == "when":
            out = when(args.at, args.zone, args.minutes)
        else:
            if get_events is None:
                google_read.load_secrets()
            fetch = get_events or events
            if args.cmd == "free":
                first = date.fromisoformat(args.start) if args.start else datetime.now(ZONE).date()
                spans = busy_spans(fetch(first.isoformat(), args.days))
                out = free(spans, first, args.days, args.minimum, _window(args.window), args.buffer)
            else:
                start, end = _dt(args.start), _dt(args.end)
                first = start.astimezone(ZONE).date()
                spans = busy_spans(fetch(first.isoformat(), (end.astimezone(ZONE).date() - first).days + 1))
                out = check(spans, start, end, args.buffer)
    except ValueError as exc:
        print(f"Bad input: {exc}", file=sys.stderr)
        return BAD_INPUT
    except GoogleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    print(json.dumps(out))
    return OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
