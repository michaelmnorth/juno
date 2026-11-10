"""Ask Michael to put a secret in 1Password, without Juno ever seeing it.

Juno appends a request to state/vault-requests.json when a task needs a login or key it doesn't have:
  {"requests": [{"id": "v-1a2b3c4d", "item": "Withings-Juno", "fields": [{"name": "client_id", "secret": false},
                {"name": "client_secret", "secret": true}], "why": "Weight sync for the health report",
                "status": "new", "created": "2026-11-08T22:00:00Z", "session_id": "..."}]}
The bridge (never Claude) creates the empty item in Agent-Secrets with the service account and posts a card:
"Fill in Withings-Juno in 1Password", with Done and Skip. If the service account can't write, the card lists what to
create by hand instead. Done checks each field with the service account and reports only filled or still empty.
Values stay inside `op` and this process; nothing here logs, posts or returns one. Tools then read the item through
`op run`, like the Google and Slack ones.
"""
from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import token_store

VAULT = "Agent-Secrets"
PLACEHOLDER = "FILL-ME"
ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,48}$")
FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MAX_FIELDS = 8


def _path(state: Path) -> Path:
    return state / "vault-requests.json"


def load(state: Path) -> list[dict]:
    try:
        return json.loads(_path(state).read_text(encoding="utf-8")).get("requests", [])
    except (OSError, ValueError):
        return []


def save(state: Path, requests: list[dict]) -> None:
    _path(state).write_text(json.dumps({"requests": requests}, indent=2) + "\n", encoding="utf-8")


def update(state: Path, request_id: str, **changes) -> dict | None:
    requests = load(state)
    for r in requests:
        if r.get("id") == request_id:
            r.update(changes)
            save(state, requests)
            return r
    return None


def problem(req: dict) -> str | None:
    """Why a request can't be acted on, or None. Juno writes these, so check them like any input."""
    if not ITEM_RE.match(str(req.get("item", ""))):
        return "item name must be letters, digits and hyphens"
    fields = req.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        return f"needs 1 to {MAX_FIELDS} fields"
    names = [f.get("name") if isinstance(f, dict) else None for f in fields]
    if not all(isinstance(n, str) and FIELD_RE.match(n) for n in names) or len(set(names)) != len(names):
        return "field names must be lowercase letters, digits and underscores, no repeats"
    if not isinstance(req.get("why", ""), str) or len(req.get("why", "")) > 200 or "\n" in req.get("why", ""):
        return "why must be one line under 200 characters"
    return None


def new_request(item: str, fields: list[dict], why: str, session_id: str | None = None) -> dict:
    return {"id": f"v-{uuid.uuid4().hex[:8]}", "item": item, "fields": fields, "why": why, "status": "new",
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "session_id": session_id}


def _key() -> str:
    import keyring
    key = keyring.get_password(token_store.SERVICE, token_store.OP_KEY)
    if not key:
        raise token_store.TokenError("no service account key stored")
    return key


def ref(item: str, field: str) -> str:
    return f"op://{VAULT}/{item}/{field}"


def field_state(req: dict, read=None) -> dict[str, str]:
    """{field: "filled" | "empty" | "missing"} read with the service account. Values never leave this function."""
    if read is None:
        op, key = token_store.find_op(), _key()
        read = lambda r: token_store.read_ref(op, r, key)  # noqa: E731
    out = {}
    for f in req["fields"]:
        try:
            value = read(ref(req["item"], f["name"]))
        except token_store.TokenError:
            out[f["name"]] = "missing"
            continue
        out[f["name"]] = "empty" if not value or value == PLACEHOLDER else "filled"
    return out


def create_item(req: dict, run=None) -> bool:
    """Create the empty item with the service account. False if it can't (a read-only account, say)."""
    args = [f"{f['name']}[{'password' if f.get('secret', True) else 'text'}]={PLACEHOLDER}" for f in req["fields"]]
    notes = f"notesPlain={req.get('why', '')} (asked by Juno {req['created'][:10]})"
    try:
        op, key = token_store.find_op(), _key()
        cmd = [op, "item", "create", "--category", "API Credential", "--vault", VAULT, "--title", req["item"],
               "--format", "json", *args, notes]
        proc = (run or subprocess.run)(cmd, env=token_store.op_env(key), stdin=subprocess.DEVNULL, capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", timeout=60,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (token_store.TokenError, OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0  # stdout (the new item) is dropped unread


def card(req: dict, created: bool) -> tuple[str, list[dict]]:
    """The Slack card. Names and field labels only; there is never a value to show."""
    rows = "\n".join(f"• `{f['name']}`" + (" (hidden)" if f.get("secret", True) else "") for f in req["fields"])
    if created:
        how = (f"I made an empty *{req['item']}* item in *{VAULT}*. Open it in 1Password, replace each "
               f"`{PLACEHOLDER}`, and save.")
    else:
        how = (f"Create an item named *{req['item']}* in *{VAULT}* (type API Credential) with these fields, "
               "spelled exactly.")
    text = f"🔑 1Password: fill in {req['item']}"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{text}*\n{req.get('why', '')}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{how}\n{rows}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Paste values in 1Password only, never here."}]},
        {"type": "actions", "block_id": f"vault_{req['id']}", "elements": [
            {"type": "button", "action_id": "vault_check", "style": "primary", "value": req["id"],
             "text": {"type": "plain_text", "text": "Done, check it"}},
            {"type": "button", "action_id": "vault_skip", "value": req["id"],
             "text": {"type": "plain_text", "text": "Skip"}}]},
    ]
    return text, blocks


def check_line(states: dict[str, str]) -> tuple[bool, str]:
    """(all filled, the line to show) for a Done tap."""
    waiting = [n for n, s in states.items() if s != "filled"]
    if not waiting:
        return True, "✅ Filled in 1Password. Juno can use it now."
    if all(states[n] == "missing" for n in states):
        return False, "I can't see that item yet. Check the name and that it's in Agent-Secrets, then tap Done again."
    return False, "Still empty: " + ", ".join(f"`{n}`" for n in waiting) + ". Tap Done again when they're in."
