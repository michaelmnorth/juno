"""Life cycle and upkeep for Juno's silent notes in observed/ (docs/04 proposals 3 and 10).

Every pattern line looks like `- [context] pattern (seen N, last YYYY-MM-DD)`, optionally `..., promoted)` once
Michael confirmed it into me/ or learnings/. The tool works out the rest in code, never in the model:
- confidence: seen 1 is low, 2 is medium, 3 or more is high (high is what drafts follow, CLAUDE.md).
- stale: a pending guess not seen again for a while (low 30 days, medium 60, high 120) is retired, so a wrong guess
  fades instead of hardening. Promoted lines never expire here.
- promote: high-confidence pending lines, for the weekly reflection to put to Michael.
- duplicates: lines in the same file and context whose words mostly overlap, for a merge.
- size: characters per file against the 8,000 cap the write hook enforces, with a warning at 80 percent.

  python tools/observed.py check [--today YYYY-MM-DD]
  python tools/observed.py retire [--today YYYY-MM-DD] [--apply]

`retire --apply` moves stale lines to observed/retired.md and logs each one in observed/changelog.md; without
--apply it only lists them. Exit codes: 0 ok, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = ROOT / "observed"
SKIP = {"README.md", "changelog.md", "retired.md"}
CAP = 8000
WARN_AT = 0.8
STALE_DAYS = {"low": 30, "medium": 60, "high": 120}
DUPLICATE_OVERLAP = 0.5
OK, BAD_INPUT = 0, 5

LINE = re.compile(r"^- \[(?P<ctx>[^\]]+)\]\s+(?P<text>.+?)\s+\((?P<meta>seen \d+[^()]*)\)\s*$")
SEEN = re.compile(r"seen (\d+)")
LAST = re.compile(r"last (\d{4}-\d{2}-\d{2})")
WORD = re.compile(r"[a-z0-9']+")
STOP = {"the", "and", "for", "with", "his", "him", "her", "that", "this", "not", "but", "from", "when", "into",
        "are", "was", "has", "have", "you", "your", "use", "one", "per"}


def confidence(seen: int) -> str:
    return "high" if seen >= 3 else "medium" if seen == 2 else "low"


def parse_line(line: str) -> dict | None:
    m = LINE.match(line.rstrip())
    if not m:
        return None
    meta = m.group("meta")
    last = LAST.search(meta)
    seen = int(SEEN.search(meta).group(1))
    return {"context": m.group("ctx").strip(), "text": m.group("text").strip(), "seen": seen,
            "last": last.group(1) if last else None, "confidence": confidence(seen),
            "status": "promoted" if "promoted" in meta else "pending"}


def notes_files(folder: Path) -> list[Path]:
    return [p for p in sorted(folder.glob("*.md")) if p.name not in SKIP]


def _words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if len(w) > 2 and w not in STOP}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_stale(note: dict, today: date) -> bool:
    if note["status"] != "pending" or not note["last"]:
        return False
    try:
        age = (today - date.fromisoformat(note["last"])).days
    except ValueError:
        return False
    return age > STALE_DAYS[note["confidence"]]


def scan(folder: Path, today: date) -> dict:
    files, stale, promote, duplicates, unparsed = [], [], [], [], []
    for path in notes_files(folder):
        text = path.read_text(encoding="utf-8", errors="replace")
        size = len(text)
        files.append({"file": path.name, "chars": size, "cap": CAP, "over_warn": size >= CAP * WARN_AT})
        notes = []
        for n, line in enumerate(text.splitlines(), 1):
            if not line.startswith("- "):
                continue
            note = parse_line(line)
            if note is None:
                unparsed.append({"file": path.name, "line": n, "text": line[:120]})
                continue
            note.update(file=path.name, line=n)
            notes.append(note)
            if is_stale(note, today):
                stale.append(note)
            elif note["status"] == "pending" and note["confidence"] == "high":
                promote.append(note)
        for i, a in enumerate(notes):
            for b in notes[i + 1:]:
                if a["context"].lower() != b["context"].lower():
                    continue
                score = _overlap(_words(a["text"]), _words(b["text"]))
                if score >= DUPLICATE_OVERLAP:
                    duplicates.append({"file": path.name, "lines": [a["line"], b["line"]], "overlap": round(score, 2),
                                       "texts": [a["text"][:100], b["text"][:100]]})
    return {"today": today.isoformat(), "files": files, "stale": stale, "promote": promote,
            "duplicates": duplicates, "unparsed": unparsed}


def retire(folder: Path, today: date, apply: bool) -> list[dict]:
    """Move stale lines out of the notes files into retired.md, with one changelog line each."""
    stale = scan(folder, today)["stale"]
    if not apply or not stale:
        return stale
    by_file: dict[str, set[int]] = {}
    for note in stale:
        by_file.setdefault(note["file"], set()).add(note["line"])
    for name, numbers in by_file.items():
        path = folder / name
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        path.write_text("".join(l for i, l in enumerate(lines, 1) if i not in numbers), encoding="utf-8")
    retired = folder / "retired.md"
    head = "" if retired.exists() else ("# Retired notes\n\nGuesses that were never seen again, moved here by "
                                        "`tools/observed.py retire`. Kept for reference; nothing reads them.\n\n")
    with retired.open("a", encoding="utf-8") as fh:
        fh.write(head + "".join(f"- {today.isoformat()} from {n['file']}: [{n['context']}] {n['text']} "
                                f"(seen {n['seen']}, last {n['last']})\n" for n in stale))
    with (folder / "changelog.md").open("a", encoding="utf-8") as fh:
        fh.write("".join(f"- {today.isoformat()} | {n['file']} | retired | dropped an old guess: {n['text'][:80]} "
                         f"(seen {n['seen']}, last {n['last']}) | observed.py\n" for n in stale))
    return stale


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--today")
    r = sub.add_parser("retire"); r.add_argument("--today"); r.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(json.dumps({"error": "--today must be YYYY-MM-DD", "code": BAD_INPUT}))
        return BAD_INPUT
    if args.cmd == "check":
        print(json.dumps(scan(OBSERVED, today), ensure_ascii=False, indent=1))
    else:
        moved = retire(OBSERVED, today, args.apply)
        print(json.dumps({"applied": args.apply, "retired": moved}, ensure_ascii=False, indent=1))
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
