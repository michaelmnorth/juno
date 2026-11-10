"""Upcoming birthdays, anniversaries and milestone years for the relationships agent (Kin) and the morning brief.
All date math happens here, never in the model: next occurrence, days away, how many years, and whether it is a
round number (the "his book turns 30 this year" kind of thing).

Sources: people/occasions.yaml (Kin and Michael keep it) plus birthdays and dates in data/contacts/contacts.json.

  python tools/occasions.py upcoming [--days 30] [--today YYYY-MM-DD]
  python tools/occasions.py cold [--today YYYY-MM-DD]
  python tools/occasions.py check

`cold` lists people overdue for a check-in (docs/04 proposal 5): only confirmed profiles with a
`- check in every: N days` line. Last contact is the profile's `- last contact: YYYY-MM-DD` line (what Michael said,
a calendar event with them). Mail does not count: he keeps up with family and friends by text and in person, so
"31 days since you talked" from mail was wrong (Michael 2026-11-09). A `(mail)` last-contact line is ignored.

people/occasions.yaml is a list of entries:
  - person: Dad (Dr. Ray Rivera)
    kind: birthday | anniversary | milestone
    what: Published his virtual reality therapy book
    date: 1955-03-14        # or --03-14 when the year is unknown
    year: 1996              # instead of date, for a milestone known only by year
    confidence: stated | inferred
    source: Michael, 2026-11-07

Exit codes: 0 ok, 5 bad input (check lists the bad entries).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
OCCASIONS = ROOT / "people" / "occasions.yaml"
CONTACTS = ROOT / "data" / "contacts" / "contacts.json"
PEOPLE = ROOT / "people"
EVERY_RE = re.compile(r"^- check in every:\s*(\d+)\s*days?", re.I | re.M)
LAST_RE = re.compile(r"^- last contact:\s*(\d{4}-\d{2}-\d{2})(.*)$", re.I | re.M)
MAIL_SOURCE = re.compile(r"\s*\(mail\b", re.I)
OK, BAD_INPUT = 0, 5
DATE_RE = re.compile(r"^(\d{4}|-)-?(\d{2})-(\d{2})$")


def parse(value) -> tuple[int | None, int, int] | None:
    """'1955-03-14' -> (1955, 3, 14); '--03-14' -> (None, 3, 14). YAML may hand over a date object."""
    if isinstance(value, date):
        return value.year, value.month, value.day
    m = DATE_RE.match(str(value or "").strip())
    if not m:
        return None
    y, mo, d = m.groups()
    mo, d = int(mo), int(d)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return (int(y) if y != "-" else None), mo, d


def _on(year: int, month: int, day: int) -> date:
    if month == 2 and day == 29:
        try:
            return date(year, 2, 29)
        except ValueError:
            return date(year, 2, 28)
    return date(year, month, day)


def is_round(n: int | None) -> bool:
    return bool(n) and (n % 5 == 0 or n == 1)


def load_entries() -> tuple[list[dict], list[str]]:
    entries, problems = [], []
    if OCCASIONS.exists():
        import yaml
        raw = yaml.safe_load(OCCASIONS.read_text(encoding="utf-8")) or []
        if not isinstance(raw, list):
            return [], ["people/occasions.yaml must be a list of entries"]
        for i, e in enumerate(raw):
            if not isinstance(e, dict) or not e.get("person"):
                problems.append(f"entry {i + 1}: needs at least person")
                continue
            if e.get("date") is not None:
                if not parse(e["date"]):
                    problems.append(f"entry {i + 1} ({e['person']}): date '{e['date']}' is not YYYY-MM-DD or --MM-DD")
                    continue
            elif not str(e.get("year", "")).isdigit():
                problems.append(f"entry {i + 1} ({e['person']}): needs date or year")
                continue
            entries.append({**e, "source": e.get("source", "people/occasions.yaml")})
    if CONTACTS.exists():
        for c in json.loads(CONTACTS.read_text(encoding="utf-8")).get("contacts", []):
            if c.get("birthday"):
                entries.append({"person": c["name"], "kind": "birthday", "what": "Birthday", "date": c["birthday"],
                                "confidence": "stated", "source": "Google Contacts"})
            for d in c.get("dates", []):
                entries.append({"person": c["name"], "kind": "anniversary", "what": d["label"].capitalize(),
                                "date": d["date"], "confidence": "stated", "source": "Google Contacts"})
    return entries, problems


def upcoming(entries: list[dict], today: date, days: int) -> dict:
    soon, this_year, seen = [], [], set()
    for e in entries:
        kind = e.get("kind", "milestone")
        if e.get("date") is not None:
            y, mo, d = parse(e["date"])
            key = (str(e["person"]).lower(), kind, mo, d)
            if key in seen:
                continue
            seen.add(key)
            nxt = _on(today.year, mo, d)
            if nxt < today:
                nxt = _on(today.year + 1, mo, d)
            gap = (nxt - today).days
            if gap > days:
                continue
            years = nxt.year - y if y else None
            soon.append({"person": e["person"], "kind": kind, "what": e.get("what", kind.capitalize()),
                         "on": nxt.isoformat(), "days": gap, "years": years, "round": is_round(years),
                         "confidence": e.get("confidence", "stated"), "source": e["source"]})
        else:
            years = today.year - int(e["year"])
            if is_round(years) and years >= 5:
                this_year.append({"person": e["person"], "kind": kind, "what": e.get("what", ""),
                                  "since": int(e["year"]), "years": years,
                                  "confidence": e.get("confidence", "stated"), "source": e["source"]})
    soon.sort(key=lambda x: x["days"])
    return {"today": today.isoformat(), "window_days": days, "upcoming": soon, "round_this_year": this_year}


def cold(today: date, folder: Path = PEOPLE) -> list[dict]:
    """Confirmed people with a check-in rhythm whose last contact is older than it (or unknown), most overdue first."""
    out = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        every = EVERY_RE.search(text)
        if path.name.lower() == "readme.md" or not every or not re.search(r"^- confirmed:\s*yes", text, re.I | re.M):
            continue
        name = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), path.stem)
        stated = LAST_RE.search(text)
        last = stated.group(1) if stated and not MAIL_SOURCE.match(stated.group(2) or "") else None
        days = (today - date.fromisoformat(last)).days if last else None
        if days is None or days >= int(every.group(1)):
            out.append({"person": name, "file": f"people/{path.name}", "every_days": int(every.group(1)),
                        "last_contact": last, "days_since": days})
    # Unknown last contact first (a gentle nudge, no day count), then the most overdue.
    return sorted(out, key=lambda p: (p["days_since"] is not None, p["every_days"] - (p["days_since"] or 0)))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("upcoming"); u.add_argument("--days", type=int, default=30); u.add_argument("--today")
    c = sub.add_parser("cold"); c.add_argument("--today")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    entries, problems = load_entries()
    if args.cmd == "check":
        print(json.dumps({"entries": len(entries), "problems": problems}, indent=1))
        return BAD_INPUT if problems else OK
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(json.dumps({"error": "--today must be YYYY-MM-DD", "code": BAD_INPUT}))
        return BAD_INPUT
    if args.cmd == "cold":
        print(json.dumps({"today": today.isoformat(), "overdue": cold(today)}, ensure_ascii=False, indent=1))
        return OK
    data = upcoming(entries, today, min(max(args.days, 0), 366))
    if problems:
        data["problems"] = problems
    print(json.dumps(data, ensure_ascii=False, indent=1))
    return OK


if __name__ == "__main__":
    # Settings allow `python tools/*`, and plain `python` is the system install without PyYAML.
    if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise SystemExit(subprocess.run([str(VENV_PYTHON), __file__, *sys.argv[1:]]).returncode)
    raise SystemExit(main())
