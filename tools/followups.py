"""Follow-ups: things Juno is waiting on for Michael (a part shipping, a refund, a claim decision), each with an
"expect by" date and what would close it (P2 brief, #10). Code keeps the list; the sweep matches new mail against it
and the morning brief lists the overdue ones.

  python tools/followups.py add --what "Replacement drain pump ships" --expect-by 2026-11-20
                                --closes "shipping or delivery mail from the maker" --match "LG,drain pump"
                                [--source "claim 2026-11-12"]
      Prints {"id": "f-xxxxxxxx", ...}. --match is comma-separated words that mark a related email (sender or
      subject); at least one word of 3+ letters.
  python tools/followups.py list [--overdue] [--all]
      Open follow-ups (or overdue ones, or every one), soonest first.
  python tools/followups.py match --items-file path|-
      Takes the JSON of `inbox.py new` (or a list of {id, from, subject}) and prints which open follow-ups each
      email may answer. It never closes one; Juno decides and runs close.
  python tools/followups.py close --id f-xxxxxxxx --how "Delivered 2026-11-18"

State lives in state/followups.json (git-ignored). Exit codes: 0 ok, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "state" / "followups.json"
ZONE = ZoneInfo("America/New_York")
OK, BAD_INPUT = 0, 5
MAX_OPEN = 50


class Bad(ValueError):
    pass


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("open", [])
    data.setdefault("closed", [])
    return data


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _today() -> date:
    return datetime.now(ZONE).date()


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        raise Bad("empty text")
    return text[:limit]


def _words(spec: str) -> list[str]:
    words = [w.strip().lower() for w in str(spec or "").split(",") if w.strip()]
    words = [w[:40] for w in words][:8]
    if not any(len(w) >= 3 for w in words):
        raise Bad("--match needs at least one word of 3 or more letters")
    return words


def add(what: str, expect_by: str, closes: str, match: str, source: str = "", path: Path = PATH,
        today: date | None = None) -> dict:
    try:
        due = date.fromisoformat(expect_by)
    except ValueError:
        raise Bad("--expect-by must be YYYY-MM-DD")
    if due < (today or _today()):
        raise Bad("--expect-by is in the past")
    data = _load(path)
    if len(data["open"]) >= MAX_OPEN:
        raise Bad(f"{MAX_OPEN} follow-ups are already open; close some first")
    item = {"id": f"f-{uuid.uuid4().hex[:8]}", "what": _clean(what, 140), "expect_by": due.isoformat(),
            "closes": _clean(closes, 200), "match": _words(match), "source": str(source or "")[:80],
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    data["open"].append(item)
    _save(path, data)
    return item


def listing(path: Path = PATH, overdue: bool = False, every: bool = False, today: date | None = None) -> list[dict]:
    data = _load(path)
    today = today or _today()
    items = data["open"] + (data["closed"] if every else [])
    out = []
    for it in items:
        days = (date.fromisoformat(it["expect_by"]) - today).days
        row = {**it, "days_left": days, "overdue": days < 0 and it in data["open"]}
        if overdue and not row["overdue"]:
            continue
        out.append(row)
    return sorted(out, key=lambda r: r["expect_by"])


def match(items: list[dict], path: Path = PATH) -> list[dict]:
    """Which open follow-ups each email may answer: a --match word in its sender or subject. Words of 1 or 2
    letters only count as whole words."""
    open_ = _load(path)["open"]
    out = []
    for mail in items:
        hay = f"{mail.get('from', '')} {mail.get('address', '')} {mail.get('subject', '')}".lower()
        hits = []
        for f in open_:
            for w in f["match"]:
                if (len(w) >= 3 and w in hay) or re.search(rf"\b{re.escape(w)}\b", hay):
                    hits.append({"id": f["id"], "what": f["what"], "closes": f["closes"], "word": w})
                    break
        if hits:
            out.append({"message_id": mail.get("id", ""), "subject": str(mail.get("subject", ""))[:120],
                        "followups": hits})
    return out


def close(followup_id: str, how: str, path: Path = PATH) -> dict:
    data = _load(path)
    found = next((f for f in data["open"] if f["id"] == followup_id), None)
    if not found:
        raise Bad(f"no open follow-up {followup_id}")
    data["open"].remove(found)
    found = {**found, "closed": datetime.now(timezone.utc).isoformat(timespec="seconds"), "how": _clean(how, 200)}
    data["closed"] = (data["closed"] + [found])[-200:]
    _save(path, data)
    return found


def _mail_items(raw: str) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, dict):
        return list(data.get("sorted", [])) + list(data.get("unclear", []))
    if isinstance(data, list):
        return data
    raise Bad("expected inbox.py output or a list of emails")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="followups.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--what", required=True)
    a.add_argument("--expect-by", required=True)
    a.add_argument("--closes", required=True)
    a.add_argument("--match", required=True)
    a.add_argument("--source", default="")
    ls = sub.add_parser("list")
    ls.add_argument("--overdue", action="store_true")
    ls.add_argument("--all", action="store_true")
    m = sub.add_parser("match")
    m.add_argument("--items-file", required=True)
    c = sub.add_parser("close")
    c.add_argument("--id", required=True)
    c.add_argument("--how", required=True)
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        if args.cmd == "add":
            out = add(args.what, args.expect_by, args.closes, args.match, args.source)
        elif args.cmd == "list":
            out = listing(overdue=args.overdue, every=args.all)
        elif args.cmd == "match":
            raw = sys.stdin.read() if args.items_file == "-" else Path(args.items_file).read_text(encoding="utf-8")
            out = match(_mail_items(raw))
        else:
            out = close(args.id, args.how)
    except (Bad, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)[:200]}))
        return BAD_INPUT
    print(json.dumps(out, ensure_ascii=False))
    return OK


if __name__ == "__main__":
    sys.exit(main())
