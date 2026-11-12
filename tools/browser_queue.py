"""Ask the browser agent to fill a web form (P2 brief step 7). The coordinator never drives a browser itself.

    python tools/browser_queue.py add --url https://www.example.com/claim --task "File the free drain-pump claim" \
        --value "First name=Sam" --value "Model number=WM1234" [--site https://forms.example.com] [--why "..."]
    python tools/browser_queue.py list

`add` writes a request to state/browser-requests.json. The bridge runs the browser agent headless in its own profile:
it fills the form, never submits, and the bridge posts a card with the site, every field and value, and the button
it would press. Only Michael's tap submits, in a second run that may type only those values. Nothing is ever bought,
paid, logged into or signed up for, and no password, card or ID number is ever typed (.claude/hooks/gate_browser.py).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "state" / "browser-requests.json"
MAX_VALUES = 30


def _gate():
    spec = importlib.util.spec_from_file_location("gate_browser", ROOT / ".claude" / "hooks" / "gate_browser.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def parse_values(raw: list[str]) -> list[dict]:
    out = []
    for item in raw:
        field, sep, value = item.partition("=")
        if not sep or not field.strip() or not value.strip():
            raise Bad(f"--value needs 'Field=value': {item[:60]!r}")
        out.append({"field": field.strip()[:80], "value": value.strip()[:300]})
    if len(out) > MAX_VALUES:
        raise Bad(f"at most {MAX_VALUES} values")
    return out


def add(url: str, task: str, values: list[dict], sites: list[str] | None = None, why: str = "",
        session_id: str | None = None, path: Path = PATH) -> dict:
    gate = _gate()
    origin = gate._origin(url)
    if origin is None:
        raise Bad("the form must be an https page")
    origins = [origin]
    for site in sites or []:
        extra = gate._origin(site)
        if extra is None:
            raise Bad(f"--site must be an https origin: {site[:60]!r}")
        if extra not in origins:
            origins.append(extra)
    for v in values:
        if gate.SECRET_FIELD.search(v["field"]) or gate.secret_value(v["value"]):
            raise Bad(f"{v['field']!r} looks like a password, card, account or ID number; Michael enters those")
    if not task.strip():
        raise Bad("--task says what the form is for")
    req = {"id": f"b-{uuid.uuid4().hex[:8]}", "url": url, "origins": origins, "task": task.strip()[:500],
           "values": values, "why": why.strip()[:300], "status": "new", "session_id": session_id,
           "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    requests = load(path)
    requests.append(req)
    save(requests, path)
    return req


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--url", required=True)
    a.add_argument("--task", required=True)
    a.add_argument("--value", action="append", default=[])
    a.add_argument("--site", action="append", default=[], help="another https origin the form needs")
    a.add_argument("--why", default="")
    a.add_argument("--session-id", default="", help="this session's id, so a Not now tap comes back here")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            req = add(args.url, args.task, parse_values(args.value), args.site, args.why,
                      args.session_id or os.environ.get("CLAUDE_SESSION_ID") or None)
            print(json.dumps({"id": req["id"], "status": "queued",
                              "next": "The browser agent fills it; Michael gets a card before anything is submitted."}))
        else:
            print(json.dumps([{k: r.get(k) for k in ("id", "url", "status", "created")} for r in load()], indent=2))
    except Bad as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
