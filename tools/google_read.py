"""Read-only Google access for Juno: Gmail and Calendar, through Michael's own OAuth app (Cloud project "Juno",
juno-514120, created 2026-11-08). First user: the sweep wake gate (docs/04 queue item 1), which asks "did anything
change since the last sweep?" in Python, so an unchanged inbox costs no model call.

Secrets come from 1Password item Agent-Secrets/Google-Juno (client_id, client_secret, refresh_token) as
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN. Run plainly, they're read with Juno's read-write service
account (gateway/token_store.py), so there's no desktop prompt. `op run --env-file=tools/google.env` still works.
Nothing here prints a token.

  python tools/google_read.py signin    one-time browser sign-in; saves the refresh token to 1Password
  python tools/google_read.py changes   {"wake": true|false, "why": [...]}

Scopes: gmail.modify, calendar.events, spreadsheets and contacts.readonly (see SCOPES). This script itself only reads; tools/gmail.py (drafts, Juno/
labels) and tools/gcal.py (holds, approved events) reuse its sign-in and call(). Exit codes: 0 ok, 3 not signed in,
4 Google refused, 5 bad input.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CURSOR = ROOT / "state" / "sweep-cursor.json"
# Widened 2026-11-08 (Michael: "full access"): gmail.modify covers reading, labels and drafts; Google has no
# drafts-only scope, so the grant also allows sending. Sending and invites stay behind Michael's tap in code
# (CLAUDE.md T3), never in the scope. calendar.events reads and edits events. No permanent mail delete.
# spreadsheets (2026-11-08): the coach's sheet sync (tools/sheets.py), which writes only Actual, LsRPE and MN notes.
# contacts.readonly (2026-11-09, Michael: connect all my contacts): tools/contacts.py sync, read-only.
SCOPES = ("https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar.events "
          "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/contacts.readonly")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
OP_ITEM, OP_VAULT = "Google-Juno", "Agent-Secrets"
OK, NOT_SIGNED_IN, REFUSED, BAD_INPUT = 0, 3, 4, 5


class GoogleError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _post(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:  # the body names the OAuth error ("invalid_grant"), never a token
        raise GoogleError(REFUSED, f"Google refused: {exc.code} {exc.read()[:200].decode(errors='replace')}")


def _get(url: str, token: str, params: dict | None = None) -> dict:
    full = url + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise GoogleError(REFUSED, f"{url.rsplit('/', 1)[-1]}: HTTP {exc.code}")


def call(method: str, url: str, token: str, body: dict | None = None, params: dict | None = None) -> dict:
    """One authorized JSON request (POST, PUT, PATCH, DELETE) for gmail.py and gcal.py."""
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # Google's error message, never a token
        raise GoogleError(REFUSED, f"{method} {url.rsplit('/', 1)[-1]}: HTTP {exc.code} "
                                   f"{exc.read()[:200].decode(errors='replace')}")


def ensure_venv(argv: list[str]) -> int | None:
    """Juno's runs call `python tools/...` with the system Python, which lacks keyring. Rerun in the project venv
    when that's the case; returns the child's exit code, or None to carry on here."""
    venv = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        import keyring  # noqa: F401
        return None
    except ImportError:
        if not venv.exists() or Path(sys.executable).resolve() == venv.resolve():
            return None
    return subprocess.run([str(venv), *argv]).returncode


def automation_mode(cls: str, root: Path = ROOT) -> str:
    """Michael's setting for an action class in me/automation.yaml (ask, auto, auto_notify, never). Missing = ask."""
    import yaml
    try:
        data = yaml.safe_load((root / "me" / "automation.yaml").read_text(encoding="utf-8")) or {}
    except OSError:
        return "ask"
    return str(((data.get("actions") or {}).get(cls) or {}).get("mode") or "ask")


def client() -> tuple[str, str]:
    cid, secret = os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not cid or not secret:
        raise GoogleError(NOT_SIGNED_IN, "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing; run inside op run")
    return cid, secret


def access_token(post=_post) -> str:
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    if not refresh:
        raise GoogleError(NOT_SIGNED_IN, "not signed in to Google yet (signin)")
    cid, secret = client()
    return post(TOKEN_URL, {"client_id": cid, "client_secret": secret, "refresh_token": refresh,
                            "grant_type": "refresh_token"})["access_token"]


# --- one-time sign-in -----------------------------------------------------------------------------

def signin() -> None:
    """Loopback OAuth with PKCE: open the browser, catch the code on 127.0.0.1, trade it for a refresh token and
    hand that straight to 1Password with Juno's service account (read-write on Agent-Secrets since 2026-11-08)."""
    import http.server
    import webbrowser

    cid, secret = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, got = secrets.token_urlsafe(16), {}

    class Catch(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Juno: done. You can close this tab.".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Catch)
    redirect = f"http://127.0.0.1:{server.server_port}"
    webbrowser.open(AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
        **({"login_hint": owner.primary()} if owner.primary() else {})}))
    print("A Google sign-in tab opened. Choose your personal Gmail and allow the access it asks for.")
    while "code" not in got and "error" not in got:
        server.handle_request()
    if "error" in got:
        raise GoogleError(REFUSED, f"sign-in cancelled: {got['error']}")
    tokens = _post(TOKEN_URL, {"client_id": cid, "client_secret": secret, "code": got["code"],
                               "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code"})
    if "refresh_token" not in tokens:
        raise GoogleError(REFUSED, "Google returned no refresh token; remove Juno at myaccount.google.com and retry")
    token_store = _token_store()
    done = subprocess.run([token_store.find_op(), "item", "edit", OP_ITEM, "--vault", OP_VAULT,
                           f"refresh_token[password]={tokens['refresh_token']}"],
                          env=token_store.op_env(_sa_key(token_store)), stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise GoogleError(REFUSED, "1Password did not save the refresh token: " + done.stderr.strip()[:200])
    print("Signed in. The refresh token is in 1Password (Agent-Secrets/Google-Juno).")


# --- wake gate ------------------------------------------------------------------------------------

def _read_cursor(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def changes(path: Path = CURSOR, now: datetime | None = None, get=_get, token: str | None = None) -> dict:
    """New inbox mail or a changed calendar event since the last call. Moves the cursor forward. The first call
    only sets the cursor and says wake, so nothing is missed on the way in."""
    now = now or datetime.now(timezone.utc)
    token = token or access_token()
    cur, why = _read_cursor(path), []
    history = get(f"{GMAIL}/profile", token)["historyId"]
    if not cur.get("gmail_history_id"):
        why.append("first check")
    elif str(history) != str(cur["gmail_history_id"]):
        added = get(f"{GMAIL}/history", token, {"startHistoryId": cur["gmail_history_id"],
                                                 "historyTypes": "messageAdded", "labelId": "INBOX"})
        n = sum(len(h.get("messagesAdded", [])) for h in added.get("history", []))
        if n:
            why.append(f"{n} new in inbox")
    since = cur.get("calendar_checked")
    if since:
        events = get(CALENDAR, token, {"updatedMin": since, "showDeleted": "true", "maxResults": 5})
        if events.get("items"):
            why.append(f"{len(events['items'])} calendar change{'s' if len(events['items']) > 1 else ''}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**cur, "gmail_history_id": str(history),
                                "calendar_checked": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                                "checked": now.isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
    return {"wake": bool(why), "why": why}


def _token_store():
    sys.path.insert(0, str(ROOT / "gateway"))
    import token_store
    return token_store


def _sa_key(token_store) -> str:
    import keyring
    key = keyring.get_password(token_store.SERVICE, token_store.OP_KEY)
    if not key:
        raise GoogleError(NOT_SIGNED_IN, "no 1Password service account key stored (gateway/token_store.py)")
    return key


def load_secrets() -> None:
    """Fill any missing GOOGLE_* from 1Password with the service account. A field it can't read stays unset, so a
    first sign-in (no refresh token yet) still works."""
    token_store = _token_store()
    missing = {n: r for n, r in token_store.OPTIONAL_REFS.items() if not os.environ.get(n)}
    if not missing:
        return
    try:
        op, key = token_store.find_op(), _sa_key(token_store)
    except (token_store.TokenError, GoogleError):
        return  # client() or access_token() then says what's missing
    for name, ref in missing.items():
        try:
            value = token_store.read_ref(op, ref, key)
        except token_store.TokenError:
            continue
        if value and value != "filled-by-signin":
            os.environ[name] = value


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("signin", "changes"):
        print(__doc__.strip().splitlines()[0])
        return BAD_INPUT
    try:
        load_secrets()
        if argv[0] == "signin":
            signin()
        else:
            print(json.dumps(changes()))
        return OK
    except GoogleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
