"""Ask for a change to Juno herself to be built in Claude Code (Michael 2026-11-15).

    python tools/build_queue.py add --title "Remind before Link runs out" \
        --task "<the whole brief: what to change, why, files if known, how to test>" --why "He said yes in his DM" \
        [--named] [--session-id <this session>]
    python tools/build_queue.py list

Michael wants to say yes to Juno in his DM, to his own idea or to one Juno suggested (a research idea, a token
saving, a fix), and have the work start right there instead of him going back to the claude.ai project. `add` writes
the request to state/build-requests.json. The bridge then starts a Claude Code session in the cloud on his Max plan
(`claude --cloud`), which clones the repository from GitHub, works on its own branch and opens a draft pull request.
He watches it in the Claude app. Nothing merges without him, and the session never turns on real-money payments.

`--named` only when his own DM said yes to this exact change: the session starts at once. Without it, or from a timer
run, he gets a card with Start build / Not now first.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "state" / "build-requests.json"
TASK_MAX = 6000
# These stay Michael's own explicit step, outside any build: merging a pull request, and real-money payments.
HIS_STEP = re.compile(r"\bmerge\b[^.\n]{0,30}\b(pr|pull request|main|branch)\b|\bauto-?merge|\bgo(es|ing)?[- ]live\b|"
                      r"\blive (mode|payments?|card)\b|\blive:\s*true\b|\breal[- ]money\b|"
                      r"\b(move|transfer|send) (the )?money\b", re.I)
SECRET = re.compile(r"(?:\d[ -]?){12,18}\d|\b(?:sk|rk)_(?:live|test)_\w{8,}|\bxox[abprs]-|\bxapp-|op://|"
                    r"\bghp_\w{20,}|\bgithub_pat_|\bsk-ant-", re.I)


class Bad(ValueError):
    pass


def load(path: Path = PATH) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("requests", [])
    except (OSError, ValueError):
        return []


def save(requests: list[dict], path: Path = PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"requests": requests}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def update(request_id: str, path: Path = PATH, **changes) -> dict | None:
    requests = load(path)
    for r in requests:
        if r.get("id") == request_id:
            r.update(changes)
            save(requests, path)
            return r
    return None


def add(title: str, task: str, why: str = "", session_id: str | None = None, path: Path = PATH,
        named: bool = False, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    title, task = " ".join(title.split())[:80], task.strip()
    if named and env.get("COORDINATOR_UNATTENDED") == "1":
        raise Bad("--named is only for a DM where Michael said yes to this change; a timer run gets a card")
    if not title or not task:
        raise Bad("--title and --task are both needed")
    if len(task) > TASK_MAX:
        raise Bad(f"keep --task under {TASK_MAX} characters")
    if HIS_STEP.search(title) or HIS_STEP.search(task):
        raise Bad("merging and real-money payments stay Michael's own step; leave them out of the build")
    if SECRET.search(task) or SECRET.search(title) or SECRET.search(why):
        raise Bad("the brief looks like it holds a number, key or token; leave secrets out")
    req = {"id": f"k-{uuid.uuid4().hex[:8]}", "title": title, "task": task, "why": " ".join(why.split())[:300],
           "named": bool(named), "status": "new", "session_id": session_id,
           "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    requests = load(path)
    requests.append(req)
    save(requests, path)
    return req


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--title", required=True, help="a few plain words, shown on the card and in the Claude app")
    a.add_argument("--task", required=True, help="the whole brief the cloud session gets")
    a.add_argument("--why", default="")
    a.add_argument("--named", action="store_true", help="Michael's own DM said yes to this change: start at once")
    a.add_argument("--session-id", default="")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            req = add(args.title, args.task, args.why, args.session_id or os.environ.get("CLAUDE_SESSION_ID") or None,
                      named=args.named)
            print(json.dumps({"id": req["id"], "status": "queued", "next": (
                "The bridge starts it in Claude Code now and sends Michael the link." if req["named"] else
                "Michael gets a Start build card first.")}))
        else:
            print(json.dumps([{k: r.get(k) for k in ("id", "title", "status", "url", "created")} for r in load()],
                             indent=2))
    except Bad as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
