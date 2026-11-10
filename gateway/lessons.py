"""A Save tap on a weekly lesson card writes exactly the line Michael saw, in code, with no model in between.

Same rule as people notes (tools/people_queue.py) and approvals (docs/v2 05-SECURITY.md, D6): the card shows a
line, the tap is his yes to that line, and the bridge writes it. "Change the wording" still goes to Juno, since that
needs words.

Targets are the confirmed lesson files only. Tier and recipient config (me/automation.yaml, the allowlist) is never a
target: a card built from the reflector's output must not be able to change what Juno may do.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TARGET_RE = re.compile(r"^(learnings/[a-z0-9-]+\.md|me/[a-z0-9-]+\.md|people/[a-z0-9][a-z0-9-]{0,60}\.md|"
                       r"domains/[a-z0-9-]+/CONTEXT\.md)$")
NEVER = ("me/automation.yaml", "me/notify-allowlist.json")
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}:")
MAX_LINE = 700


class LessonError(Exception):
    pass


def _bare(line: str) -> str:
    return re.sub(r"^[-*+]\s+", "", " ".join(str(line or "").split()))


def lesson_line(text: str, today: str | None = None) -> str:
    """The dated list line the lesson skill writes: `- YYYY-MM-DD: <lesson> (Michael)`."""
    body = _bare(text)
    if not body or len(body) > MAX_LINE:
        raise LessonError("That lesson is empty or too long to save as one line.")
    today = today or datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    if not DATED.match(body):
        body = f"{today}: {body}"
    if not body.endswith(")"):
        body += " (Michael)"
    return f"- {body}"


def apply(change: dict, root: Path, today: str | None = None) -> dict:
    """change = {"target", "old", "new"} from the card. Replaces the old line when it is there, else appends."""
    target = str(change.get("target") or "").strip().replace("\\", "/")
    if target in NEVER or not TARGET_RE.match(target):
        raise LessonError("That lesson points somewhere I can't save to from a card. Tell me where it goes.")
    path = root / target
    if not path.exists():
        raise LessonError("That file doesn't exist yet. Save it from the Code tab or tell me where it goes.")
    line = lesson_line(change.get("new", ""), today)
    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    old = _bare(change.get("old", ""))
    hit = next((i for i, l in enumerate(lines) if old and _bare(l) == old), None)
    if hit is not None:
        lines[hit] = line
    elif any(_bare(l) == _bare(line) for l in lines):
        return {"target": target, "line": line, "replaced": False, "already": True}
    else:
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"target": target, "line": line, "replaced": hit is not None, "already": False,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
