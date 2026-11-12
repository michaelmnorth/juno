"""PreToolUse hook for the browser agent's Playwright tools (mcp__playwright__*), P2 brief step 7.

The bridge runs the browser agent as its own CLI run (gateway/browser_agent.py) with JUNO_BROWSER_RUN set to "fill"
or "submit" and the sites it may visit in JUNO_BROWSER_ORIGINS. Every Playwright call passes through here:

- Only the listed tools. JavaScript, file upload, network routing, cookies, storage and tabs are never allowed.
- Navigation stays on the allowed https sites.
- No password, card number, Social Security number or similar value is ever typed, whatever the field.
- Buy, checkout, pay, place order, sign up and create account buttons are never pressed.
- A fill run never submits: no Enter key, no type-and-submit, and once a value is in, no more clicks (checkboxes,
  radios and dropdowns go through browser_fill_form). It ends with what it filled; the bridge posts a card.
- A submit run needs the one-time pass the bridge writes after Michael taps (state/browser/pass.json) for this exact
  approval; it may type only the values the card showed.

Anything outside a browser run (no JUNO_BROWSER_RUN) is denied: the Playwright server is never loaded elsewhere.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

PREFIX = "mcp__playwright__"
ALLOWED = {"browser_navigate", "browser_navigate_back", "browser_snapshot", "browser_click", "browser_type",
           "browser_fill_form", "browser_select_option", "browser_press_key", "browser_wait_for",
           "browser_take_screenshot", "browser_close", "browser_hover", "browser_handle_dialog"}
NEVER_CLICK = re.compile(r"(?i)\b(buy|checkout|check out|pay|payment|place (my |your )?order|purchase|add to cart|"
                         r"sign ?up|create (an |my |your )?account|register an account|subscribe|log ?in|sign ?in)\b")
SECRET_FIELD = re.compile(r"(?i)(\bpass(word|code|phrase)?\b|\bpin\b|\bcvv|\bcvc|security code|card number|"
                          r"credit card|debit card|account number|routing number|\bssn\b|social security|tax id|"
                          r"\bein\b|driver'?s? licen[cs]e|passport|one[- ]time code|\botp\b|\b2fa\b|"
                          r"verification code)")
SSN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
DIGITS = re.compile(r"\d[\d -]{11,22}\d")
SUBMIT_KEYS = {"enter", "numpadenter"}
PASS_MAX_AGE = 900  # seconds; the bridge writes the pass right before the submit run


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def secret_value(value: str) -> bool:
    """A card number (13 to 19 digits passing Luhn) or a Social Security number."""
    text = str(value)
    if SSN.search(text) and len(re.sub(r"\D", "", text)) == 9:
        return True
    for m in DIGITS.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    return False


def _origin(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    return f"https://{parts.hostname.lower()}" + (f":{parts.port}" if parts.port else "")


def _entries(tool: str, data: dict) -> list[tuple[str, str]]:
    """(field description, value) pairs a call would type or choose."""
    if tool == "browser_type":
        return [(str(data.get("element") or ""), str(data.get("text") or ""))]
    if tool == "browser_fill_form":
        return [(str(f.get("name") or f.get("element") or ""), str(f.get("value") or ""))
                for f in data.get("fields") or [] if isinstance(f, dict)]
    if tool == "browser_select_option":
        return [(str(data.get("element") or ""), str(v)) for v in data.get("values") or []]
    return []


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _gate_file(root: Path, session: str) -> Path:
    return root / "state" / "browser" / f"gate-{re.sub(r'[^A-Za-z0-9-]', '', session)[:64] or 'run'}.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_pass(root: Path, approval_id: str, now: datetime | None = None) -> dict | None:
    data = _load(root / "state" / "browser" / "pass.json")
    if not approval_id or data.get("approval_id") != approval_id:
        return None
    try:
        made = datetime.fromisoformat(data["created"])
    except (KeyError, ValueError):
        return None
    if ((now or datetime.now(timezone.utc)) - made).total_seconds() > PASS_MAX_AGE:
        return None
    return data


def decide(tool_name: str, data: dict, env: dict, root: Path, session: str = "") -> str | None:
    if not tool_name.startswith(PREFIX):
        return None
    tool = tool_name[len(PREFIX):]
    mode = env.get("JUNO_BROWSER_RUN")
    if mode not in ("fill", "submit"):
        return "Blocked: the browser is only used in the bridge's browser runs."
    if tool not in ALLOWED:
        return f"Blocked: {tool} is not a tool the browser agent uses."
    origins = {o.strip().lower() for o in (env.get("JUNO_BROWSER_ORIGINS") or "").split(",") if o.strip()}
    if tool == "browser_navigate":
        origin = _origin(str(data.get("url") or ""))
        if origin is None or origin not in origins:
            return "Blocked: that page is outside the site this run is for (https only)."
    for field, value in _entries(tool, data):
        if SECRET_FIELD.search(field) or secret_value(value):
            return ("Blocked: passwords, card or account numbers, ID numbers and codes are never typed by Juno. "
                    "Stop and say which field needs Michael.")
    if tool == "browser_click" and NEVER_CLICK.search(str(data.get("element") or "")):
        return "Blocked: buying, paying, logging in and making accounts are Michael's to do. Stop and say so."
    pressed = str(data.get("key") or "").replace(" ", "").lower()
    gate = _gate_file(root, session)
    if mode == "fill":
        if tool == "browser_press_key" and pressed in SUBMIT_KEYS:
            return "Blocked: a fill run never submits. Finish with the JSON of what you filled."
        if tool == "browser_type" and data.get("submit"):
            return "Blocked: a fill run never submits. Type without submit."
        state = _load(gate)
        if tool == "browser_click" and state.get("filled"):
            return ("Blocked: once a value is in, a fill run doesn't click (a click could submit). Set checkboxes, "
                    "radios and dropdowns with browser_fill_form, then finish with the JSON.")
        if _entries(tool, data) and not state.get("filled"):
            gate.parent.mkdir(parents=True, exist_ok=True)
            gate.write_text(json.dumps({"filled": True}), encoding="utf-8")
        return None
    approved = load_pass(root, env.get("JUNO_BROWSER_PASS") or "")
    if approved is None:
        return "Blocked: no valid one-time pass for this submission. Nothing was submitted."
    allowed_values = {_norm(v) for v in approved.get("values") or []}
    for _field, value in _entries(tool, data):
        if _norm(value) not in allowed_values:
            return "Blocked: that value wasn't on the card Michael approved. Don't submit; say what differs."
    return None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig") or "{}"
    data = json.loads(raw)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("COORDINATOR_HOME") or data.get("cwd") or ".")
    reason = decide(data.get("tool_name") or "", data.get("tool_input") or {}, os.environ, root,
                    str(data.get("session_id") or ""))
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
