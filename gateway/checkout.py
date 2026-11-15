"""Type a one-time Link card into a checkout page and press its pay button, in code (Michael 2026-11-15).

No model is involved. The bridge drives the same Playwright MCP server Hands uses (its own headless profile,
state/browser/profile) directly over JSON-RPC: open the page, read its accessibility snapshot, find the card fields
and the one pay button by their labels, type, press, read the result. The card lives only in this process's memory
for those few calls and is never logged, returned, or put in an error message.

It stops, and presses nothing, when the page's total isn't the approved amount, when a card field can't be found, or
when there isn't exactly one pay button. Then the caller cancels the Link request and hands Michael the link.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LINE = re.compile(r'-\s+(textbox|spinbutton|combobox|button|link)\s+"([^"]*)"[^\n]*?\[ref=([A-Za-z0-9]+)\]')
CARD_NUMBER = re.compile(r"(?i)card ?number|cc-?number|^number$")
EXPIRY = re.compile(r"(?i)expir|mm ?/ ?yy|exp\.? date|cc-?exp")
EXP_MONTH = re.compile(r"(?i)^(exp(iration)?\.? )?month$|^mm$")
EXP_YEAR = re.compile(r"(?i)^(exp(iration)?\.? )?year$|^yy(yy)?$")
CVC = re.compile(r"(?i)\bcvc\b|\bcvv\b|security code|cc-?csc")
NAME = re.compile(r"(?i)name on card|cardholder|card holder")
ZIP = re.compile(r"(?i)\bzip\b|postal")
PAY = re.compile(r"(?i)^\s*(pay\b|place (my |your )?order|complete (purchase|order|payment)|buy now|purchase\b|"
                 r"confirm (and |& )?pay|submit (payment|order))")
DONE = re.compile(r"(?i)thank you|order (number|confirmed|#)|payment (successful|received|complete)|"
                  r"confirmation (number|#)|you'?re (all set|going)|receipt")
DECLINED = re.compile(r"(?i)declined|card (was|is) (not|in)valid|payment failed|couldn'?t (process|charge)")


@dataclass
class Outcome:
    paid: bool
    pressed: bool  # True once the pay button was pressed: from then on, never say nothing was charged
    line: str
    confirmation: str = ""


class Browser:
    """A tiny MCP client for @playwright/mcp (0.0.85: elements are addressed by `target`) over stdio."""

    def __init__(self, cli: Path, config: Path, popen=subprocess.Popen):
        node = shutil.which("node") or "node"
        self.proc = popen([node, str(cli), "--config", str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.next_id = 0
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "juno-checkout", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method: str, params: dict) -> dict:
        self.next_id += 1
        mid = self.next_id
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"browser {method} failed")  # no detail: it could echo typed text
                return msg.get("result") or {}
        raise RuntimeError("browser closed")

    def call(self, tool: str, args: dict) -> str:
        out = self._rpc("tools/call", {"name": tool, "arguments": args})
        if out.get("isError"):
            raise RuntimeError(f"browser {tool} refused")  # no detail: the error text could echo typed text
        return "\n".join(c.get("text", "") for c in out.get("content") or [] if isinstance(c, dict))

    def close(self) -> None:
        try:
            self.call("browser_close", {})
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass


def elements(snapshot: str) -> list[tuple[str, str, str]]:
    return [(m.group(1), m.group(2).strip(), m.group(3)) for m in LINE.finditer(snapshot or "")]


def _find(items, pattern, roles=("textbox", "spinbutton", "combobox")):
    hits = [(label, ref) for role, label, ref in items if role in roles and pattern.search(label)]
    return hits[0] if hits else None


def amount_shown(snapshot: str, cents: int) -> bool:
    dollars = f"{cents / 100:,.2f}"
    return dollars in snapshot or dollars.replace(",", "") in snapshot


def plan(snapshot: str, card: dict, cents: int) -> tuple[list[tuple[str, str, str]], tuple[str, str] | None, str]:
    """(fields to type as (label, ref, text), the pay button, why not). Pure, so it is tested without a browser."""
    if not amount_shown(snapshot, cents):
        return [], None, f"the page doesn't show the approved total of ${cents / 100:,.2f}"
    items = elements(snapshot)
    mm, yy = int(card["exp_month"]), int(card["exp_year"]) % 100
    fields = []
    number = _find(items, CARD_NUMBER)
    cvc = _find(items, CVC)
    if not number or not cvc:
        return [], None, "I couldn't find the card number and security code boxes on the page"
    fields.append((number[0], number[1], str(card["number"])))
    expiry = _find(items, EXPIRY)
    month, year = _find(items, EXP_MONTH), _find(items, EXP_YEAR)
    if expiry and expiry[1] not in (month or ("", ""))[1:]:
        fields.append((expiry[0], expiry[1], f"{mm:02d} / {yy:02d}"))
    elif month and year:
        fields += [(month[0], month[1], f"{mm:02d}"), (year[0], year[1], f"{int(card['exp_year'])}")]
    else:
        return [], None, "I couldn't find the expiry date box on the page"
    fields.append((cvc[0], cvc[1], str(card["cvc"])))
    name, zip_box = _find(items, NAME), _find(items, ZIP)
    billing = card.get("billing_address") or {}
    holder = card.get("name") or billing.get("name")
    if name and holder:
        fields.append((name[0], name[1], str(holder)))
    if zip_box and billing.get("postal_code"):
        fields.append((zip_box[0], zip_box[1], str(billing["postal_code"])))
    buttons = [(label, ref) for role, label, ref in items if role == "button" and PAY.search(label)]
    if len(buttons) != 1:
        return fields, None, ("I couldn't find the pay button" if not buttons else
                              "there's more than one pay button, so I didn't guess")
    return fields, buttons[0], ""


def complete(browser, url: str, card: dict, cents: int, store: str) -> Outcome:
    """Open the checkout, type the card, press pay once, read the result. Never raises with card text in it."""
    try:
        browser.call("browser_navigate", {"url": url})
        snap = browser.call("browser_snapshot", {})
        fields, button, why = plan(snap, card, cents)
        if why:
            return Outcome(False, False, why)
        for label, ref, text in fields:
            browser.call("browser_type", {"element": label, "target": ref, "text": text})
        browser.call("browser_click", {"element": button[0], "target": button[1]})
    except Exception as exc:
        return Outcome(False, False, f"the checkout page broke before I pressed pay ({type(exc).__name__})")
    try:
        browser.call("browser_wait_for", {"time": 5})
        after = browser.call("browser_snapshot", {})
    except Exception:
        after = ""
    for value in (str(card.get("number") or ""), str(card.get("cvc") or "")):
        if value:
            after = after.replace(value, "•")
    if DECLINED.search(after):
        return Outcome(False, True, f"{store} said the card didn't go through")
    hit = next((line for line in after.splitlines() if DONE.search(line)), None)
    if hit:
        text = re.sub(r"\[[^\]]*\]|\"", "", re.sub(r"^\s*-\s*[a-z]+\s*:?\s*", "", hit))
        return Outcome(True, True, "paid", re.sub(r"\s+", " ", text).strip(" :")[:160])
    return Outcome(False, True, f"I pressed pay on {store} but didn't see a confirmation")
