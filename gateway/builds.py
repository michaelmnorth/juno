"""Start a build of a change to Juno in Claude Code, from a yes in Michael's DM (Michael 2026-11-15).

1. Juno asks with tools/build_queue.py (title, the whole brief, why). `--named` when his own DM said yes to it.
2. Named: the bridge starts it at once. Otherwise it posts a build.start card (Start build / Not now) and only his
   tap starts it. Never automatic from a timer, never an Always button.
3. Start: code, not a model, runs `claude --cloud "<brief>"` in this folder. That makes a Claude Code session in the
   cloud on his Max plan (the CLI's claude.ai login; no API key reaches it, see claude_runner.child_env). It clones
   the repository from GitHub, works on its own branch and opens a draft pull request. He follows it in the Claude
   app, and the link goes to his DM and the conversation log.

The brief every session gets says: draft pull request only, never merge, never change payments to live, never put
personal data in tracked files (tests/test_no_personal.py), and run the tests. Merging stays his tap on GitHub.
"""
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import build_queue  # noqa: E402

ACTION = "build.start"
START_TIMEOUT = 240  # seconds for the CLI to make the session; the work itself runs in the cloud
SESSION_URL = re.compile(r"https://claude\.ai/code/(?:session_|cse_)[A-Za-z0-9_-]+")

RULES = """You are building a change to Juno, Michael's personal assistant (this repository). Michael said yes to it
in his Discord DM with Juno. Rules that always hold:
- Work on a new branch and open a DRAFT pull request when the change is ready. Never merge, never push to main,
  never enable auto-merge. Michael reviews and merges himself.
- Never set payments to live (me/payments.yaml `live`), never raise payment caps, never add a way for a model to pay
  or move money. Card numbers and secrets never go in code, tests, logs or the PR.
- The repository is public: no personal data in tracked files (tests/test_no_personal.py). Personal files stay in
  the git-ignored folders listed in .gitignore.
- Read CLAUDE.md, docs/02-ARCHITECTURE.md and the code you touch first; follow the existing patterns and voice.
- Run `python -m pytest -q` and keep it green. Say in the PR what you could not test offline.
- Juno runs only on Michael's Max plan through Claude Code; never add an API key or API billing.
- If the request is unclear or would break one of these rules, stop and explain in the session instead of guessing.

The change:"""


def brief(req: dict) -> str:
    why = f"\n\nWhy he wants it: {req['why']}" if req.get("why") else ""
    return f"{RULES}\n{req['title']}\n\n{req['task']}{why}"


def card_entry(req: dict) -> dict:
    return {"id": f"a-{uuid.uuid4().hex[:8]}", "kind": "action", "action_class": ACTION,
            "summary": f"Start building this in Claude Code? {req['title']}",
            "action": req["title"], "why": req.get("why") or req["title"], "request_id": req["id"],
            "session_id": req.get("session_id"), "status": "new", "from_timer": False,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def launch(prompt: str, cwd: Path, run=subprocess.run, claude: str | None = None) -> tuple[str | None, str]:
    """Run `claude --cloud`. Returns (session link or None, a short note for the log). A slow CLI that already
    printed the link counts as started: the session lives in the cloud, not in this process."""
    import claude_runner
    try:
        binary = claude or claude_runner.find_claude()
    except FileNotFoundError as exc:
        return None, str(exc)
    cmd = [binary, "--cloud", prompt]
    try:
        done = run(cmd, cwd=str(cwd), env=claude_runner.child_env(), stdin=subprocess.DEVNULL, capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=START_TIMEOUT,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out, code = f"{done.stdout or ''}\n{done.stderr or ''}", done.returncode
    except subprocess.TimeoutExpired as exc:
        out = "\n".join(x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
                        for x in (exc.stdout, exc.stderr))
        code = "timeout"
    except OSError as exc:
        return None, f"couldn't run Claude Code ({type(exc).__name__})"
    found = SESSION_URL.search(out)
    if found:
        return found.group(0), "started"
    last = " ".join(out.split())[-200:] or "no output"
    return None, f"no session link (exit {code}): {last}"


def start(root: Path, req: dict, path: Path | None = None, launcher=launch) -> str:
    path = path or root / "state" / "build-requests.json"
    url, note = launcher(brief(req), root)
    if not url:
        build_queue.update(req["id"], path, status="failed", note=note[:300])
        return (f"I couldn't start \"{req['title']}\" in Claude Code ({note[:120]}). Nothing changed. To start it "
                "by hand: open the Claude app, tap Code, pick the juno repository, and paste the request from "
                "today's conversation log. Or say \"try the build again\". 🙃")
    build_queue.update(req["id"], path, status="started", url=url,
                       started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return (f"Started \"{req['title']}\" in Claude Code: {url}\nIt works on its own branch and opens a draft pull "
            "request when it's done. Follow along in the Claude app; merging stays with you. 🛠️")


def process(root: Path, approvals_add, audit=None, path: Path | None = None, launcher=launch) -> list[str]:
    """New requests: named ones start now, the rest become cards. Returns lines for Michael."""
    path = path or root / "state" / "build-requests.json"
    lines = []
    for req in [r for r in build_queue.load(path) if r.get("status") == "new"]:
        if req.get("named"):
            build_queue.update(req["id"], path, status="starting")
            line = start(root, req, path, launcher)
            if audit:
                status = next((r.get("status") for r in build_queue.load(path) if r.get("id") == req["id"]), "")
                audit("build_started" if status == "started" else "build_failed",
                      {"id": req["id"], "action_class": ACTION, "summary": req["title"]}, line.splitlines()[0][:200])
            lines.append(line)
            continue
        entry = card_entry(req)
        approvals_add(entry)
        build_queue.update(req["id"], path, status="carded", approval_id=entry["id"])
        if audit:
            audit("build_carded", entry, req["title"])
    return lines


def tapped(root: Path, entry: dict, approved: bool, path: Path | None = None, launcher=launch) -> str:
    """Michael tapped Start build or Not now on a build card."""
    path = path or root / "state" / "build-requests.json"
    req = next((r for r in build_queue.load(path) if r.get("id") == entry.get("request_id")), None)
    if not req or req.get("status") != "carded":
        return "That build isn't waiting anymore. 🧐"
    if not approved:
        build_queue.update(req["id"], path, status="skipped")
        return "Skipped. Nothing was built. 👍"
    build_queue.update(req["id"], path, status="starting")
    return start(root, req, path, launcher)
