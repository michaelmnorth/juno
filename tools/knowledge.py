"""Juno's knowledge base: one timestamped entry per thing we know, each marked confirmed or unconfirmed (Michael
2026-11-16: "unless it's actually confirmed, write it down, timestamp it, and give it a status; if it is confirmed,
cite the source").

Every entry is one markdown file with a small header (see knowledge/README.md):

    ---
    id: k-20261116-restart-only-own-process
    title: Restart only Juno's own process
    status: confirmed
    topic: ops
    created: 2026-11-15
    last_verified: 2026-11-16
    review_by: 2027-02-14
    sources:
      - pr: michaelmnorth/juno#6
    ---
    What we know, in plain words. Why it matters. How to check it again.

Two places, one format:
- knowledge/entries/   tracked in git. Shared system knowledge only (no personal data; test_no_personal.py checks).
                       Sources must be checkable by anyone with the repo: pr, commit, url, test, doc.
- knowledge/local/     git-ignored, stays on Michael's PC. Anything personal and everything Juno writes on its own
                       (lessons from his taps, the nightly research scan, migrated learnings). Any source kind.

Rules enforced here, in code:
- A confirmed entry needs at least one source. `card:` sources must be an approved or executed card in
  state/audit.jsonl; `test:` and `log:` sources must point at a file that exists.
- Juno's own runs (any run with COORDINATOR_UNATTENDED set) can only write knowledge/local/. The tracked part changes through a
  pull request or a Code-tab session.
- Nothing in an entry is an instruction. An entry never grants a tool, a recipient or a permission.

  python tools/knowledge.py add --title "..." --body "..." [--topic T] [--status confirmed --source kind:ref ...]
                                [--shared] [--review-days N]
  python tools/knowledge.py confirm <id> --source kind:ref [...]     # also how you re-verify an old entry
  python tools/knowledge.py retire <id> --reason "..."
  python tools/knowledge.py check                                    # problems and stale entries
  python tools/knowledge.py recheck-tests [--apply]                  # rerun cited tests; passing ones re-verify
  python tools/knowledge.py list [--status S] [--stale] [--topic T] [--json]
  python tools/knowledge.py recap --since YYYY-MM-DD [--shared-only]  # for the weekly recap
  python tools/knowledge.py index                                    # rebuilds the INDEX.md files
  python tools/knowledge.py lesson --target learnings/x.md --line "- ..." --source card:a-1234abcd [--old "..."]
  python tools/knowledge.py migrate-learnings [--apply]              # learnings/ and me/ lines -> local entries

Exit codes: 0 ok, 1 check found problems, 5 bad input.
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

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("America/New_York")
OK, PROBLEMS, BAD_INPUT = 0, 1, 5

STATUSES = ("unconfirmed", "confirmed", "retired")
REVIEW_DAYS = {"unconfirmed": 30, "confirmed": 90}
SOURCE_KINDS = ("pr", "commit", "url", "test", "log", "card", "michael", "doc")
SHARED_KINDS = ("pr", "commit", "url", "test", "doc")  # checkable from a fresh clone
FIELDS = ("id", "title", "status", "topic", "created", "last_verified", "review_by", "retired_reason", "supersedes")
TOPIC_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_TITLE, MAX_BODY = 120, 4000


class KnowledgeError(Exception):
    pass


# --- places ------------------------------------------------------------------------------------------------------

def shared_dir(root: Path) -> Path:
    return Path(root) / "knowledge" / "entries"


def local_dir(root: Path) -> Path:
    return Path(root) / "knowledge" / "local"


def today_eastern() -> str:
    return datetime.now(ZONE).date().isoformat()


def juno_run(env=None) -> bool:
    """Any run the bridge starts (timer or DM) sets COORDINATOR_UNATTENDED; a Code-tab session with Michael doesn't."""
    return "COORDINATOR_UNATTENDED" in (env if env is not None else os.environ)


# --- one entry ---------------------------------------------------------------------------------------------------

def parse_source(text: str) -> dict:
    kind, sep, ref = str(text or "").partition(":")
    kind, ref = kind.strip().lower(), ref.strip()
    if not sep or kind not in SOURCE_KINDS or not ref:
        raise KnowledgeError(f"A source looks like kind:ref, with kind one of {', '.join(SOURCE_KINDS)} "
                             f"(got {text!r}).")
    if kind == "url" and not ref.startswith("https://"):
        raise KnowledgeError("A url source must start with https://.")
    if kind == "commit" and not re.fullmatch(r"[0-9a-f]{7,40}", ref):
        raise KnowledgeError("A commit source is a 7 to 40 character commit hash.")
    if kind == "pr" and not re.fullmatch(r"([\w.-]+/[\w.-]+)?#\d+|https://github\.com/\S+/pull/\d+", ref):
        raise KnowledgeError("A pr source looks like owner/repo#12, #12 or a github.com pull request link.")
    if kind == "card" and not re.fullmatch(r"a-[0-9a-f]{8}", ref):
        raise KnowledgeError("A card source is the approval id, a- plus 8 hex characters.")
    if kind == "michael" and not re.search(r"\d{4}-\d{2}-\d{2}", ref):
        raise KnowledgeError("A michael source says when he said it, with a date (YYYY-MM-DD).")
    return {"kind": kind, "ref": ref}


def parse(text: str) -> dict:
    """Header plus body. Raises KnowledgeError on a broken header."""
    if not text.startswith("---\n"):
        raise KnowledgeError("missing the --- header")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise KnowledgeError("the header never closes with ---")
    entry: dict = {"sources": [], "body": body.strip()}
    in_sources = False
    for raw in head.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if in_sources and line.startswith("  - "):
            entry["sources"].append(parse_source(line[4:]))
            continue
        in_sources = False
        key, sep, value = line.partition(":")
        if not sep:
            raise KnowledgeError(f"header line without a colon: {line!r}")
        key, value = key.strip(), value.strip()
        if key == "sources":
            in_sources = True
            continue
        if key not in FIELDS:
            raise KnowledgeError(f"unknown header field {key!r}")
        entry[key] = value
    for key in FIELDS:
        entry.setdefault(key, "")
    return entry


def render(entry: dict) -> str:
    lines = ["---"]
    for key in FIELDS:
        value = str(entry.get(key) or "")
        if key in ("retired_reason", "supersedes") and not value:
            continue
        lines.append(f"{key}: {value}".rstrip())
    lines.append("sources:")
    lines += [f"  - {s['kind']}: {s['ref']}" for s in entry.get("sources", [])]
    lines += ["---", str(entry.get("body") or "").strip(), ""]
    return "\n".join(lines)


def slug(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join(words)[:48].strip("-") or "entry"


def _plus(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


# --- reading the whole base --------------------------------------------------------------------------------------

def load(root: Path) -> list[dict]:
    """Every entry, each with `path`, `shared` (tracked) and `error` (a broken file is reported, never dropped)."""
    out = []
    for folder, shared in ((shared_dir(root), True), (local_dir(root), False)):
        for path in sorted(folder.rglob("*.md")) if folder.exists() else []:
            if path.name in ("INDEX.md", "README.md") or path.name.startswith("_"):
                continue
            try:
                entry = parse(path.read_text(encoding="utf-8"))
                entry["error"] = ""
            except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
                entry = {k: "" for k in FIELDS} | {"sources": [], "body": "", "error": str(exc)}
            entry.update(path=path, shared=shared)
            out.append(entry)
    return out


def find(root: Path, entry_id: str) -> dict:
    hits = [e for e in load(root) if e["id"] == entry_id]
    if not hits:
        raise KnowledgeError(f"No entry with id {entry_id}.")
    return hits[0]


def is_stale(entry: dict, today: str) -> bool:
    return entry.get("status") != "retired" and bool(entry.get("review_by")) and entry["review_by"] < today


def _audit_cards(root: Path) -> set[str]:
    try:
        lines = (Path(root) / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    ids = set()
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") in ("approved", "executed") and row.get("id"):
            ids.add(row["id"])
    return ids


def source_problem(root: Path, source: dict, shared: bool, cards: set[str] | None = None) -> str | None:
    kind, ref = source["kind"], source["ref"]
    if shared and kind not in SHARED_KINDS:
        return f"{kind} sources stay on the PC; a tracked entry needs pr, commit, url, test or doc"
    if kind in ("test", "log", "doc"):
        rel, _, name = ref.partition("::")
        rel = rel.split(":", 1)[0] if kind == "log" else rel.split("#", 1)[0].strip()
        path = Path(root) / rel
        if not path.is_file():
            return f"{kind} source {rel} does not exist"
        if kind == "test" and name and f"def {name}(" not in path.read_text(encoding="utf-8", errors="replace"):
            return f"test {name} is not in {rel}"
    if kind == "card" and cards is not None and ref not in cards:
        return f"card {ref} was never approved (not in state/audit.jsonl)"
    return None


def problems(root: Path, entries: list[dict] | None = None) -> list[str]:
    entries = load(root) if entries is None else entries
    cards = _audit_cards(root) if (Path(root) / "state" / "audit.jsonl").exists() else None
    out, seen = [], {}
    for e in entries:
        where = e["path"].relative_to(root).as_posix() if Path(e["path"]).is_relative_to(root) else str(e["path"])
        if e["error"]:
            out.append(f"{where}: {e['error']}")
            continue
        if e["id"] in seen:
            out.append(f"{where}: id {e['id']} is also used by {seen[e['id']]}")
        seen[e["id"]] = where
        if e["status"] not in STATUSES:
            out.append(f"{where}: status must be one of {', '.join(STATUSES)}")
        for key in ("created", "review_by") + (("last_verified",) if e["last_verified"] else ()):
            if not DATE_RE.match(e[key] or ""):
                out.append(f"{where}: {key} must be a YYYY-MM-DD date")
        if not e["title"]:
            out.append(f"{where}: no title")
        if e["status"] == "confirmed":
            if not e["sources"]:
                out.append(f"{where}: confirmed but cites no source")
            if not e["last_verified"]:
                out.append(f"{where}: confirmed but has no last_verified date")
        if e["status"] == "retired" and not e["retired_reason"]:
            out.append(f"{where}: retired without a reason")
        for s in e["sources"]:
            why = source_problem(root, s, e["shared"], cards)
            if why:
                out.append(f"{where}: {why}")
    return out


# --- writing -----------------------------------------------------------------------------------------------------

def _write(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(entry), encoding="utf-8")


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def add(root: Path, *, title: str, body: str, topic: str = "general", status: str = "unconfirmed",
        sources: list[str] | None = None, shared: bool = False, review_days: int | None = None,
        today: str | None = None, env=None) -> dict:
    """Writes one entry and returns it with `created_new`. The same title (or, for research, the same url) already
    in the base returns that entry instead of a second copy."""
    root = Path(root)
    title, body = " ".join(str(title or "").split()), str(body or "").strip()
    if not title or len(title) > MAX_TITLE:
        raise KnowledgeError(f"A title is 1 to {MAX_TITLE} characters.")
    if len(body) > MAX_BODY:
        raise KnowledgeError(f"Keep the body under {MAX_BODY} characters; split it into two entries.")
    if not TOPIC_RE.match(topic):
        raise KnowledgeError("A topic is a short lowercase word or two joined by hyphens.")
    if status not in ("unconfirmed", "confirmed"):
        raise KnowledgeError("New entries are unconfirmed or confirmed.")
    if shared and juno_run(env):
        raise KnowledgeError("Juno's own runs write knowledge/local/ only; tracked entries change through a PR.")
    parsed = [parse_source(s) for s in sources or []]
    if status == "confirmed" and not parsed:
        raise KnowledgeError("A confirmed entry needs a source. Record it as unconfirmed instead.")
    for s in parsed:
        why = source_problem(root, s, shared, _audit_cards(root) if s["kind"] == "card" else None)
        if why:
            raise KnowledgeError(why)
    existing = load(root)
    urls = {s["ref"] for s in parsed if s["kind"] == "url"}
    for e in existing:
        if e["error"] or e["status"] == "retired":
            continue
        if _norm(e["title"]) == _norm(title) or (urls and urls & {s["ref"] for s in e["sources"]
                                                                  if s["kind"] == "url"}):
            return {**e, "created_new": False}
    today = today or today_eastern()
    base = f"k-{today.replace('-', '')}-{slug(title)}"
    ids = {e["id"] for e in existing}
    entry_id, n = base, 2
    while entry_id in ids:
        entry_id, n = f"{base}-{n}", n + 1
    entry = {"id": entry_id, "title": title, "status": status, "topic": topic, "created": today,
             "last_verified": today if status == "confirmed" else "",
             "review_by": _plus(today, review_days or REVIEW_DAYS[status]), "sources": parsed, "body": body}
    path = (shared_dir(root) if shared else local_dir(root)) / topic / f"{entry_id}.md"
    _write(path, entry)
    return {**entry, "path": path, "shared": shared, "error": "", "created_new": True}


def _guard(entry: dict, env=None) -> None:
    if entry["shared"] and juno_run(env):
        raise KnowledgeError("Juno's own runs can't change tracked entries; that goes through a PR.")


def confirm(root: Path, entry_id: str, sources: list[str], today: str | None = None,
            review_days: int | None = None, env=None) -> dict:
    """Marks an entry confirmed (or re-verifies a confirmed one): adds the sources, stamps last_verified, moves
    review_by out again."""
    entry = find(root, entry_id)
    _guard(entry, env)
    parsed = [parse_source(s) for s in sources or []]
    if not parsed:
        raise KnowledgeError("Confirming needs a source: what shows it is true?")
    cards = _audit_cards(root)
    for s in parsed:
        why = source_problem(root, s, entry["shared"], cards)
        if why:
            raise KnowledgeError(why)
    today = today or today_eastern()
    known = {(s["kind"], s["ref"]) for s in entry["sources"]}
    entry["sources"] += [s for s in parsed if (s["kind"], s["ref"]) not in known]
    entry.update(status="confirmed", last_verified=today,
                 review_by=_plus(today, review_days or REVIEW_DAYS["confirmed"]))
    _write(entry["path"], entry)
    return entry


def retire(root: Path, entry_id: str, reason: str, today: str | None = None, superseded_by: str = "",
           env=None) -> dict:
    """Wrong or replaced: kept for history with the reason, never deleted."""
    entry = find(root, entry_id)
    _guard(entry, env)
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise KnowledgeError("Say why it's retired.")
    today = today or today_eastern()
    entry.update(status="retired", retired_reason=f"{today}: {reason}", review_by=entry["review_by"] or today)
    if superseded_by:
        entry["retired_reason"] += f" (replaced by {superseded_by})"
    _write(entry["path"], entry)
    return entry


def record_lesson(root: Path, *, target: str, line: str, source: str, old: str = "",
                  today: str | None = None) -> dict:
    """A lesson line was just written to learnings/ or me/ (his tap or his words): the matching local entry,
    confirmed with that source. A line it replaced has its entry retired, so the history stays."""
    m = LESSON_LINE.match(str(line).strip())
    text = m.group("text").strip() if m else re.sub(r"^[-*+]\s+", "", str(line)).strip()
    stem = Path(target).stem.lower()
    topic = (("lesson-" if target.startswith("learnings/") else "me-") + re.sub(r"[^a-z0-9-]", "-", stem))[:31]
    title = text[:MAX_TITLE].rstrip(" .,;")
    entry = add(root, title=title, topic=topic, status="confirmed", sources=[source], today=today, env={},
                body=f"{text}\n\nSaved to `{target}` on {today or today_eastern()}.")
    if not entry["created_new"] and entry["status"] != "confirmed":
        entry = confirm(root, entry["id"], [source], today, env={})
    if old:
        om = LESSON_LINE.match(str(old).strip())
        old_title = _norm((om.group("text") if om else old)[:MAX_TITLE].rstrip(" .,;"))
        for e in load(root):
            if not e["error"] and not e["shared"] and e["status"] != "retired" and e["id"] != entry["id"] \
                    and _norm(e["title"]) == old_title:
                retire(root, e["id"], "replaced by a newer lesson", today, entry["id"], env={})
    write_indexes(root, today)
    return entry


def recheck_tests(root: Path, today: str | None = None, apply: bool = False, env=None) -> dict:
    """Runs every test an entry cites. All passing re-verifies the entry (with apply); any failing is reported,
    and the entry is left alone for a person to look at. Only entries whose sources are all tests or docs are
    re-verified this way: a test can't re-prove a card or something Michael said."""
    import subprocess
    out = {"passed": [], "failed": [], "skipped": []}
    for e in load(root):
        tests = [s["ref"] for s in e["sources"] if s["kind"] == "test"]
        if e["error"] or e["status"] == "retired" or not tests:
            continue
        if (e["shared"] and juno_run(env)) or any(s["kind"] not in ("test", "doc") for s in e["sources"]):
            out["skipped"].append(e["id"])
            continue
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                              cwd=root, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            out["passed"].append(e["id"])
            if apply:
                confirm(root, e["id"], [f"test:{t}" for t in tests], today, env=env)
        else:
            out["failed"].append({"id": e["id"], "title": e["title"],
                                  "tail": "\n".join(proc.stdout.strip().splitlines()[-3:])})
    if apply:
        write_indexes(root, today)
    return out


# --- views -------------------------------------------------------------------------------------------------------

def _row(e: dict, today: str) -> str:
    flag = " **stale**" if is_stale(e, today) else ""
    checked = e["last_verified"] or "never"
    return (f"| {e['title'].replace('|', '/')} | {e['status']}{flag} | {e['topic']} | {e['created']} | {checked} | {e['review_by']} | "
            f"{len(e['sources'])} | `{e['id']}` |")


def index_text(entries: list[dict], today: str, heading: str) -> str:
    live = [e for e in entries if not e["error"]]
    head = [f"# {heading}", "",
            "Generated by `python tools/knowledge.py index`; don't edit by hand. Stale means past its review-by date: "
            "check it again (`confirm`) or retire it.", "",
            f"{sum(e['status'] == 'confirmed' for e in live)} confirmed, "
            f"{sum(e['status'] == 'unconfirmed' for e in live)} unconfirmed, "
            f"{sum(is_stale(e, today) for e in live)} stale, {sum(e['status'] == 'retired' for e in live)} retired.",
            "", "| Title | Status | Topic | Created | Last verified | Review by | Sources | Id |",
            "|---|---|---|---|---|---|---|---|"]
    order = {"confirmed": 0, "unconfirmed": 1, "retired": 2}
    rows = sorted(live, key=lambda e: (order.get(e["status"], 3), e["topic"], e["created"], e["id"]))
    return "\n".join(head + [_row(e, today) for e in rows]) + "\n"


def write_indexes(root: Path, today: str | None = None) -> list[Path]:
    today = today or today_eastern()
    entries = load(root)
    out = []
    for folder, shared, heading in ((shared_dir(root), True, "Knowledge base (shared)"),
                                    (local_dir(root), False, "Knowledge base (this PC only)")):
        mine = [e for e in entries if e["shared"] is shared]
        if not mine and not folder.exists():
            continue
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "INDEX.md").write_text(index_text(mine, today, heading), encoding="utf-8")
        out.append(folder / "INDEX.md")
    return out


def recap(root: Path, since: str, today: str | None = None, shared_only: bool = False) -> dict:
    """What changed since a date, for the weekly recap. `shareable` is the tracked part only (safe for Minerva)."""
    today = today or today_eastern()
    entries = [e for e in load(root) if not e["error"] and (e["shared"] or not shared_only)]

    def brief(e):
        return {"id": e["id"], "title": e["title"], "status": e["status"], "topic": e["topic"],
                "created": e["created"], "last_verified": e["last_verified"], "review_by": e["review_by"],
                "sources": [f"{s['kind']}: {s['ref']}" for s in e["sources"]], "shareable": e["shared"]}

    return {"since": since, "today": today,
            "added": [brief(e) for e in entries if e["created"] >= since],
            "verified": [brief(e) for e in entries if e["status"] == "confirmed" and e["last_verified"] >= since
                         and e["created"] < since],
            "retired": [brief(e) for e in entries if e["status"] == "retired"
                        and e["retired_reason"][:10] >= since],
            "stale": [brief(e) for e in entries if is_stale(e, today)],
            "unconfirmed": sum(e["status"] == "unconfirmed" for e in entries)}


# --- migration from learnings/ and me/ ---------------------------------------------------------------------------

LESSON_LINE = re.compile(r"^- (?P<day>\d{4}-\d{2}-\d{2}): (?P<text>.+?)\s*\((?P<tag>[^()]*)\)\s*$")


def _card_saves(root: Path) -> list[tuple[str, str]]:
    """(utc time, card id) for every lesson card the bridge executed."""
    try:
        lines = (Path(root) / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") == "executed" and row.get("class") == "lesson" and row.get("id"):
            out.append((str(row.get("at", "")), row["id"]))
    return out


def migrate_learnings(root: Path, apply: bool = False, today: str | None = None) -> list[dict]:
    """Each dated lesson line becomes a local entry. Confirmed only when the line was on a weekly card
    (state/proposed-lessons.md) and a lesson card was executed in the week after its date; everything else is
    unconfirmed, because no source was recorded when it was written."""
    root = Path(root)
    try:
        proposed = _norm((root / "state" / "proposed-lessons.md").read_text(encoding="utf-8"))
    except OSError:
        proposed = ""
    saves = _card_saves(root)
    files = sorted((root / "learnings").glob("*.md")) + sorted((root / "me").glob("*.md"))
    plan = []
    for path in files:
        if path.name.startswith("_") or ".example." in path.name:
            continue
        rel = path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = LESSON_LINE.match(line.strip())
            if not m:
                continue
            day, text, tag = m.group("day"), m.group("text").strip(), m.group("tag").strip()
            card = next((cid for at, cid in sorted(saves) if day <= at[:10] <= _plus(day, 7)), None) \
                if _norm(line) and _norm(line) in proposed else None
            topic = "lesson-" + path.stem if path.parent.name == "learnings" else "me-" + path.stem
            body = (f"{text}\n\nFrom `{rel}` line {n}, written {day}, tagged ({tag}).")
            if card:
                status, sources = "confirmed", [f"card:{card}", f"log:{rel}"]
                body += f" Saved from weekly lesson card {card}; the bridge recorded it in state/audit.jsonl."
            else:
                status, sources = "unconfirmed", [f"log:{rel}"]
                body += (" No source was recorded when it was written. To confirm, find where he said it in "
                         "logs/conversations/ and run `confirm` with that log line." if tag.lower() == "michael" else
                         " A guess Juno made; it expires unless he confirms it." if tag.lower() == "assumed" else
                         f" Learned {tag}; no source was recorded, so it waits for him to confirm it.")
            plan.append({"title": text[:MAX_TITLE].rstrip(" .,;"), "body": body, "topic": topic[:31],
                         "status": status, "sources": sources, "day": day,
                         "review_days": 30 if tag.lower() == "assumed" else None})
    if apply:
        for p in plan:
            p["result"] = add(root, title=p["title"], body=p["body"], topic=p["topic"], status=p["status"],
                              sources=p["sources"], today=p["day"], review_days=p["review_days"],
                              env={})["id"]
        write_indexes(root, today)
    return plan


# --- command line ------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Juno's timestamped knowledge base")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--title", required=True)
    a.add_argument("--body", default="")
    a.add_argument("--body-file")
    a.add_argument("--topic", default="general")
    a.add_argument("--status", default="unconfirmed", choices=("unconfirmed", "confirmed"))
    a.add_argument("--source", action="append", default=[])
    a.add_argument("--shared", action="store_true")
    a.add_argument("--review-days", type=int)
    c = sub.add_parser("confirm")
    c.add_argument("id")
    c.add_argument("--source", action="append", default=[])
    c.add_argument("--review-days", type=int)
    r = sub.add_parser("retire")
    r.add_argument("id")
    r.add_argument("--reason", required=True)
    r.add_argument("--replaced-by", default="")
    sub.add_parser("check")
    rt = sub.add_parser("recheck-tests")
    rt.add_argument("--apply", action="store_true")
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--stale", action="store_true")
    ls.add_argument("--topic")
    ls.add_argument("--json", action="store_true")
    rc = sub.add_parser("recap")
    rc.add_argument("--since", required=True)
    rc.add_argument("--shared-only", action="store_true")
    sub.add_parser("index")
    le = sub.add_parser("lesson")
    le.add_argument("--target", required=True)
    le.add_argument("--line", required=True)
    le.add_argument("--source", required=True)
    le.add_argument("--old", default="")
    mg = sub.add_parser("migrate-learnings")
    mg.add_argument("--apply", action="store_true")
    for p in sub.choices.values():
        p.add_argument("--today")
        p.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    root, today = Path(args.root), args.today or today_eastern()
    try:
        if args.cmd == "add":
            body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
            e = add(root, title=args.title, body=body, topic=args.topic, status=args.status, sources=args.source,
                    shared=args.shared, review_days=args.review_days, today=today)
            write_indexes(root, today)
            print(json.dumps({"id": e["id"], "status": e["status"], "new": e["created_new"],
                              "path": Path(e["path"]).relative_to(root).as_posix()}))
        elif args.cmd == "confirm":
            e = confirm(root, args.id, args.source, today, args.review_days)
            write_indexes(root, today)
            print(json.dumps({"id": e["id"], "status": e["status"], "last_verified": e["last_verified"],
                              "review_by": e["review_by"]}))
        elif args.cmd == "retire":
            e = retire(root, args.id, args.reason, today, args.replaced_by)
            write_indexes(root, today)
            print(json.dumps({"id": e["id"], "status": e["status"]}))
        elif args.cmd == "check":
            found = problems(root)
            stale = [e for e in load(root) if not e["error"] and is_stale(e, today)]
            print(json.dumps({"problems": found, "stale": [{"id": e["id"], "title": e["title"],
                                                             "review_by": e["review_by"]} for e in stale]},
                             indent=1))
            return PROBLEMS if found else OK
        elif args.cmd == "recheck-tests":
            result = recheck_tests(root, today, args.apply)
            print(json.dumps(result, indent=1))
            return PROBLEMS if result["failed"] else OK
        elif args.cmd == "list":
            rows = [e for e in load(root) if not e["error"] and (not args.status or e["status"] == args.status)
                    and (not args.stale or is_stale(e, today)) and (not args.topic or e["topic"] == args.topic)]
            if args.json:
                print(json.dumps([{k: e[k] for k in FIELDS} | {"shared": e["shared"]} for e in rows], indent=1))
            else:
                for e in rows:
                    print(f"{e['id']}  {e['status']}{' (stale)' if is_stale(e, today) else ''}  {e['title']}")
        elif args.cmd == "recap":
            print(json.dumps(recap(root, args.since, today, args.shared_only), indent=1))
        elif args.cmd == "index":
            print(json.dumps([p.relative_to(root).as_posix() for p in write_indexes(root, today)]))
        elif args.cmd == "lesson":
            e = record_lesson(root, target=args.target, line=args.line, source=args.source, old=args.old,
                              today=today)
            print(json.dumps({"id": e["id"], "status": e["status"]}))
        elif args.cmd == "migrate-learnings":
            plan = migrate_learnings(root, args.apply, today)
            print(json.dumps([{"title": p["title"], "status": p["status"], "sources": p["sources"],
                               **({"id": p["result"]} if "result" in p else {})} for p in plan], indent=1))
    except (KnowledgeError, OSError, ValueError) as exc:
        print(f"knowledge: {exc}", file=sys.stderr)
        return BAD_INPUT
    return OK


if __name__ == "__main__":
    sys.exit(main())
