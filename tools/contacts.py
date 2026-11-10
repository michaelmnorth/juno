"""Michael's Google Contacts, for the relationships agent (Kin), calendar invites (the right email) and, later, the
day planner (addresses). `sync` reads them straight from Google (People API, contacts.readonly, read-only) with
the same sign-in as Gmail and Calendar; `import` still takes a vCard export (contacts.google.com -> Export). Stored
in data/contacts/ (git-ignored), never in the repo. This is the phone book for everyone; people/ holds profiles only
for the people who matter (see people/README.md).

  python tools/contacts.py sync
  python tools/contacts.py import <path to .vcf>
  python tools/contacts.py find "<name or email>"
  python tools/contacts.py email-for "<name>"
  python tools/contacts.py stats

Exit codes: 0 ok, 3 not signed in to Google (or the sign-in lacks contacts), 4 no contacts yet or no match,
5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "contacts" / "contacts.json"
OK, NOT_SIGNED_IN, NOT_FOUND, BAD_INPUT = 0, 3, 4, 5
PEOPLE_API = "https://people.googleapis.com/v1/people/me/connections"
FIELDS = "names,nicknames,emailAddresses,phoneNumbers,addresses,birthdays,events,organizations,relations,biographies"
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LABEL = re.compile(r"^_\$!<(.+)>!\$_$")  # Apple/Google wrap standard labels like _$!<Anniversary>!$_


class ToolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _unescape(value: str) -> str:
    value = value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    return CONTROL.sub("", value).strip()


def parse_date(value: str) -> str | None:
    """vCard dates come as 1955-03-14, 19550314, --03-14, --0314 or with a time. Returns YYYY-MM-DD or --MM-DD."""
    value = value.strip().split("T")[0]
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", value)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}" if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 else None
    m = re.match(r"^--(\d{2})-?(\d{2})$", value)
    if m:
        mo, d = m.groups()
        return f"--{mo}-{d}" if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 else None
    return None


def parse_vcards(text: str) -> list[dict]:
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold continuation lines
    cards = []
    for block in re.findall(r"(?ims)^BEGIN:VCARD\s*$(.*?)^END:VCARD\s*$", text):
        lines = []
        for raw in block.splitlines():
            if ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            parts = key.split(";")
            group, _, name = parts[0].rpartition(".")
            params = {}
            for p in parts[1:]:
                k, _, v = p.partition("=")
                params.setdefault(k.upper(), []).extend(v.lower().split(","))
            lines.append((group, name.upper(), params, value))
        labels = {g: _unescape(v) for g, n, _, v in lines if n == "X-ABLABEL" and g}
        labels = {g: (LABEL.match(v).group(1) if LABEL.match(v) else v) for g, v in labels.items()}
        c = {"name": "", "nickname": "", "emails": [], "phones": [], "birthday": None, "dates": [],
             "addresses": [], "org": "", "title": "", "related": [], "note": ""}
        for group, name, params, value in lines:
            kind = ",".join(t for t in params.get("TYPE", []) if t and t not in ("internet", "pref")) or labels.get(group, "")
            if name == "FN":
                c["name"] = _unescape(value)
            elif name == "N" and not c["name"]:
                fam, given = (value.split(";") + ["", ""])[:2]
                c["name"] = _unescape(f"{given} {fam}")
            elif name == "NICKNAME":
                c["nickname"] = _unescape(value)
            elif name == "EMAIL" and "@" in value:
                c["emails"].append({"address": value.strip().lower(), "type": kind})
            elif name == "TEL":
                c["phones"].append({"number": _unescape(value), "type": kind})
            elif name == "BDAY":
                c["birthday"] = parse_date(value)
            elif name in ("ANNIVERSARY", "X-ANNIVERSARY", "X-ABDATE"):
                d = parse_date(value)
                if d:
                    c["dates"].append({"label": "anniversary" if name != "X-ABDATE" else (labels.get(group) or "date"),
                                       "date": d})
            elif name == "ADR":
                text_parts = [_unescape(x) for x in value.split(";") if x.strip()]
                if text_parts:
                    c["addresses"].append({"type": kind, "text": ", ".join(text_parts)})
            elif name == "ORG":
                c["org"] = _unescape(value.replace(";", " "))
            elif name == "TITLE":
                c["title"] = _unescape(value)
            elif name in ("RELATED", "X-ABRELATEDNAMES"):
                c["related"].append({"label": labels.get(group) or ",".join(params.get("TYPE", [])), "name": _unescape(value)})
            elif name == "NOTE":
                c["note"] = _unescape(value)[:1000]
        if c["name"] or c["emails"]:
            cards.append(c)
    return cards


def _date(d: dict) -> str | None:
    """People API date {year?, month, day} as YYYY-MM-DD, or --MM-DD without a year (the vCard import's shape)."""
    if not d or not d.get("month") or not d.get("day"):
        return None
    return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}" if d.get("year") else f"--{d['month']:02d}-{d['day']:02d}"


def from_person(p: dict) -> dict:
    """One People API person in the same shape as a parsed vCard, so find/email-for/occasions read both."""
    first = lambda key: (p.get(key) or [{}])[0]
    kind = lambda x: x.get("formattedType") or x.get("type") or ""
    birthday = next((_date(b.get("date")) for b in p.get("birthdays") or [] if b.get("date")), None)
    return {
        "name": first("names").get("displayName", ""),
        "nickname": first("nicknames").get("value", ""),
        "emails": [{"address": e["value"].strip().lower(), "type": kind(e)}
                   for e in p.get("emailAddresses") or [] if "@" in e.get("value", "")],
        "phones": [{"number": t["value"], "type": kind(t)} for t in p.get("phoneNumbers") or [] if t.get("value")],
        "birthday": birthday,
        "dates": [{"label": kind(e) or "date", "date": _date(e.get("date"))}
                  for e in p.get("events") or [] if _date(e.get("date"))],
        "addresses": [{"type": kind(a), "text": " ".join(a.get("formattedValue", "").split())}
                      for a in p.get("addresses") or [] if a.get("formattedValue")],
        "org": first("organizations").get("name", ""),
        "title": first("organizations").get("title", ""),
        "related": [{"label": kind(r), "name": r.get("person", "")} for r in p.get("relations") or []],
        "note": first("biographies").get("value", "")[:1000],
    }


def fetch(get=None, token: str | None = None) -> list[dict]:
    """Every contact, page by page. Read-only: this script never writes to Google."""
    sys.path.insert(0, str(ROOT / "tools"))
    import google_read
    get = get or google_read._get
    if token is None:
        google_read.load_secrets()
        try:
            token = google_read.access_token()
        except google_read.GoogleError as exc:
            raise ToolError(NOT_SIGNED_IN, str(exc)) from exc
    cards, page = [], None
    while True:
        params = {"personFields": FIELDS, "pageSize": 1000, **({"pageToken": page} if page else {})}
        try:
            data = get(PEOPLE_API, token, params)
        except google_read.GoogleError as exc:
            raise ToolError(NOT_SIGNED_IN, "Google refused the contacts read; sign in again with "
                                           "`python tools/google_read.py signin` to add contacts. " + str(exc)) from exc
        cards += [c for c in map(from_person, data.get("connections") or []) if c["name"] or c["emails"]]
        page = data.get("nextPageToken")
        if not page:
            return cards


def save(cards: list[dict], source: str) -> dict:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({"imported": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": source,
                                 "contacts": cards}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"imported": len(cards), "with_birthday": sum(1 for c in cards if c["birthday"]),
            "with_address": sum(1 for c in cards if c["addresses"]), "store": str(STORE)}


def load() -> list[dict]:
    if not STORE.exists():
        raise ToolError(NOT_FOUND, "No contacts yet. Run: python tools/contacts.py sync")
    return json.loads(STORE.read_text(encoding="utf-8"))["contacts"]


def find(contacts: list[dict], query: str) -> list[dict]:
    q = query.strip().lower()
    if not q or len(q) > 120:
        raise ToolError(BAD_INPUT, "Give a name or email to look for.")
    words = q.split()
    hits = []
    for c in contacts:
        hay = " ".join([c["name"], c["nickname"]] + [e["address"] for e in c["emails"]]).lower()
        if all(w in hay for w in words):
            hits.append(c)
    hits.sort(key=lambda c: (c["name"].lower() != q, len(c["name"])))
    return hits


def email_for(contacts: list[dict], name: str) -> dict:
    """The address to put on an invite. Ambiguous or missing -> say so, never guess."""
    hits = [c for c in find(contacts, name) if c["emails"]]
    if not hits:
        raise ToolError(NOT_FOUND, f"No contact with an email matches '{name}'.")
    exact = [c for c in hits if c["name"].lower() == name.strip().lower()]
    pick = exact if len(exact) == 1 else hits
    return {"ambiguous": len(pick) > 1,
            "candidates": [{"name": c["name"], "emails": [e["address"] for e in c["emails"]]} for c in pick[:5]]}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    i = sub.add_parser("import"); i.add_argument("vcf")
    f = sub.add_parser("find"); f.add_argument("query")
    e = sub.add_parser("email-for"); e.add_argument("name")
    sub.add_parser("stats")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "sync":
            sys.path.insert(0, str(ROOT / "tools"))
            import google_read
            relaunched = google_read.ensure_venv([__file__, *(sys.argv[1:] if argv is None else argv)])
            if relaunched is not None:
                return relaunched
            data = save(fetch(), "google")
        elif args.cmd == "import":
            path = Path(args.vcf)
            if not path.is_file():
                raise ToolError(BAD_INPUT, f"No such file: {path}")
            data = save(parse_vcards(path.read_text(encoding="utf-8", errors="replace")), "vcard")
        elif args.cmd == "find":
            data = find(load(), args.query)[:10]
        elif args.cmd == "email-for":
            data = email_for(load(), args.name)
        else:
            cards = load()
            data = {"contacts": len(cards), "with_email": sum(1 for c in cards if c["emails"]),
                    "with_birthday": sum(1 for c in cards if c["birthday"]),
                    "with_address": sum(1 for c in cards if c["addresses"])}
        print(json.dumps(data, ensure_ascii=False, indent=1))
    except ToolError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}))
        return exc.code
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
