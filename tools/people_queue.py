"""What Juno learns about people, waiting for Michael's Save tap, then written into people/ by code.

Juno's Slack and timer runs may not write people/ (the memory hook), so they queue here instead. The bridge posts
the waiting entries as a small card with Save and Skip; a Save writes exactly the line Michael saw, in Python, with
no model in between. Code-tab sessions with Michael can apply entries directly.

  python tools/people_queue.py add --file people/chris-hale.md --line "- Moving gyms in December" \
      --section "Life now" --source "Michael 2026-11-09"
  python tools/people_queue.py add --new "chris@example.com" --source "mail 2026-11-09"   (starter from Contacts)
  python tools/people_queue.py list
  python tools/people_queue.py apply --id pq-1a2b3c4d   (Code tab only; the bridge applies on a tap)

A line that starts with a top field ("- last contact:", "- address:") replaces that field. Otherwise it goes at the
end of its section, replacing a "None seen." placeholder. Exit codes: 0 ok, 4 nothing to do, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import people_match  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "state" / "people-queue.jsonl"
OK, NOTHING, BAD_INPUT = 0, 4, 5
FILE_RE = re.compile(r"^people/[a-z0-9][a-z0-9-]{0,60}\.md$")
SECTIONS = ("Dates", "Interests and tastes (gift-useful)", "Life now", "Working together", "Open threads")
FIELDS = ("last contact", "address", "relationship", "also called", "emails", "phone", "check in every")
PLACEHOLDER = re.compile(r"^- (None seen|Nothing known yet)\b.*$")
MAX_LINE = 300


class QueueError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def load(queue: Path = QUEUE) -> list[dict]:
    if not queue.exists():
        return []
    return [json.loads(l) for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save(entries: list[dict], queue: Path) -> None:
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")


def pending(queue: Path = QUEUE) -> list[dict]:
    return [e for e in load(queue) if e.get("status") == "new"]


def _field(line: str) -> str | None:
    m = re.match(r"^- ([a-z ]+):", line, re.I)
    return m.group(1).lower() if m and m.group(1).lower() in FIELDS else None


def add(*, file: str = "", line: str = "", section: str = "", new: str = "", source: str,
        queue: Path = QUEUE, folder: Path | None = None, store: Path = people_match.CONTACTS,
        now: datetime | None = None) -> dict:
    """Queue one change. Duplicates of a waiting entry, and starters for people who already have a file, are
    no-ops (returns the existing entry or a note)."""
    root = folder.parent if folder else ROOT
    source = " ".join(source.split())[:80]
    if not source:
        raise QueueError(BAD_INPUT, "Say where it came from (--source \"Michael 2026-11-09\", \"mail 2026-11-09\").")
    if new:
        draft = people_match.starter(new, store)
        if not draft:
            raise QueueError(NOTHING, f"'{new}' is not in Google Contacts; ask Michael who they are.")
        file, text, kind = draft["file"], draft["text"], "new"
        if (root / file).exists():
            return {"note": f"{file} already exists", "file": file}
    else:
        line = " ".join(line.split())
        if not FILE_RE.match(file) or not line.startswith("- ") or len(line) > MAX_LINE:
            raise QueueError(BAD_INPUT, "Need --file people/<slug>.md and one --line starting with '- ' "
                                        f"(at most {MAX_LINE} characters).")
        if section and section not in SECTIONS:
            raise QueueError(BAD_INPUT, f"--section must be one of: {', '.join(SECTIONS)}")
        if not (root / file).exists() and not any(e["file"] == file and e["kind"] == "new" for e in pending(queue)):
            raise QueueError(BAD_INPUT, f"No profile {file} yet; queue it with --new first.")
        text, kind = line, "line"
    entries = load(queue)
    same = next((e for e in entries if e["status"] == "new" and e["file"] == file and e["text"] == text), None)
    if same:
        return same
    entry = {"id": "pq-" + secrets.token_hex(4), "kind": kind, "file": file, "section": section or None,
             "text": text, "source": source, "status": "new",
             "created": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    _save(entries + [entry], queue)
    return entry


def _insert(profile: str, line: str, section: str | None) -> str:
    lines = profile.rstrip("\n").split("\n")
    field = _field(line)
    if field:
        for i, l in enumerate(lines):
            if _field(l) == field:
                lines[i] = line
                return "\n".join(lines) + "\n"
        top_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
        while top_end > 0 and not lines[top_end - 1].strip():
            top_end -= 1
        lines.insert(top_end, line)
        return "\n".join(lines) + "\n"
    section = section or "Life now"
    head = next((i for i, l in enumerate(lines) if l.strip() == f"## {section}"), None)
    if head is None:
        return "\n".join(lines + ["", f"## {section}", line]) + "\n"
    end = next((i for i in range(head + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = [i for i in range(head + 1, end) if lines[i].strip()]
    if len(body) == 1 and PLACEHOLDER.match(lines[body[0]]):
        lines[body[0]] = line
    else:
        at = (body[-1] + 1) if body else head + 1
        lines.insert(at, line)
    return "\n".join(lines) + "\n"


def _mark(entry_id: str, status: str, queue: Path) -> dict:
    entries = load(queue)
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry or entry["status"] != "new":
        raise QueueError(NOTHING, "That one was already handled.")
    entry["status"] = status
    entry["done"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save(entries, queue)
    return entry


def apply(entry_id: str, queue: Path = QUEUE, root: Path = ROOT) -> dict:
    """Write one waiting entry into people/ exactly as queued. Called by the bridge on Michael's Save tap."""
    entry = next((e for e in pending(queue) if e["id"] == entry_id), None)
    if not entry:
        raise QueueError(NOTHING, "That one was already handled.")
    if not FILE_RE.match(entry["file"]):
        raise QueueError(BAD_INPUT, "Not a people/ file.")
    path = root / entry["file"]
    if entry["kind"] == "new":
        if not path.exists():
            path.write_text(entry["text"], encoding="utf-8")
    else:
        if not path.exists():
            raise QueueError(NOTHING, f"{entry['file']} doesn't exist yet; save the new profile first.")
        path.write_text(_insert(path.read_text(encoding="utf-8"), f"{entry['text']} ({entry['source']})"
                                if "(" not in entry["text"] else entry["text"], entry.get("section")),
                        encoding="utf-8")
    return _mark(entry_id, "saved", queue)


def skip(entry_id: str, queue: Path = QUEUE) -> dict:
    return _mark(entry_id, "skipped", queue)


def label(entry: dict) -> str:
    """One plain line for the Slack card: whose profile and what it says. No file names."""
    name = entry["file"].removeprefix("people/").removesuffix(".md").replace("-", " ").title()
    if entry["kind"] == "new":
        rel = next((l for l in entry["text"].splitlines() if l.startswith("- relationship:")), "")
        hint = rel.split("Contacts says", 1)[1].strip(' ";') if "Contacts says" in rel else ""
        return f"New profile: *{name}*" + (f" ({hint})" if hint else "") + ", from your contacts"
    return f"*{name}:* {entry['text'].removeprefix('- ')}"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--file", default="")
    a.add_argument("--line", default="")
    a.add_argument("--section", default="")
    a.add_argument("--new", default="")
    a.add_argument("--source", required=True)
    sub.add_parser("list")
    p = sub.add_parser("apply"); p.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "add":
            out = add(file=args.file, line=args.line, section=args.section, new=args.new, source=args.source)
        elif args.cmd == "list":
            out = pending()
        else:
            import os
            if os.environ.get("COORDINATOR_UNATTENDED") == "1":
                raise QueueError(BAD_INPUT, "Only Michael's Save tap or a Code-tab session applies entries.")
            out = apply(args.id)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return OK
    except QueueError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}))
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
