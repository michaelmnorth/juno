"""Paying through Stripe Link (Michael 2026-11-15). Code runs every step; no model holds a card or a tool that pays.

1. Juno asks with tools/pay_queue.py (store, checkout page, amount, what it's for). Caps and allowed stores are
   checked in code against me/payments.yaml.
2. Card. The bridge posts a payment.link card: store, amount, what, and whether it's test mode. Never automatic,
   no Always button.
3. Tap. The bridge checks the rules again, then asks Link for a one-time card for exactly that amount and store
   (`link-cli spend-request create --request-approval`). Link sends Michael a push; he approves with his passkey.
4. Approved. The bridge fetches the card to a 0600 file, reads it into memory, deletes the file, and
   gateway/checkout.py types it into that checkout page and presses its pay button. Anything off and it presses
   nothing, cancels the Link request, and gives him the link to finish himself.

Link CLI: github.com/stripe/link-cli, installed and signed in by Michael (`npm i -g @stripe/link-cli`,
`link-cli auth login`). In test mode (`live: false`, the default) Link returns test cards and charges nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import pay_queue  # noqa: E402

ACTION = "payment.link"
WAITING = ("created", "pending_approval", "requires_action")
APPROVAL_WINDOW = timedelta(minutes=35)  # Link gives him 30 minutes; a little slack for the clock
NOT_INSTALLED = ("Link isn't set up on this PC yet, so I couldn't ask it for a card. Nothing was charged. Michael "
                 "installs it once: `npm i -g @stripe/link-cli`, then `link-cli auth login`. 🙃")


class LinkError(RuntimeError):
    pass


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def find_link(env: dict | None = None) -> str | None:
    env = os.environ if env is None else env
    return env.get("JUNO_LINK_CLI") or shutil.which("link-cli")


class Link:
    """The few link-cli commands Juno uses. `run` is subprocess.run (a fake in tests)."""

    def __init__(self, binary: str, folder: Path, test: bool, run=subprocess.run):
        self.binary, self.folder, self.test, self._run = binary, Path(folder), test, run

    def _call(self, *args: str) -> dict:
        done = self._run([self.binary, *args, "--format", "json"], capture_output=True, text=True, encoding="utf-8",
                         timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if done.returncode != 0:
            raise LinkError((done.stdout or done.stderr or "link-cli failed").strip()[-300:])
        try:
            out = json.loads(done.stdout)
        except ValueError as exc:
            raise LinkError("link-cli printed something that isn't JSON") from exc
        if isinstance(out, list):
            out = out[0] if out and isinstance(out[0], dict) else {}
        return out if isinstance(out, dict) else {}

    def create(self, entry: dict) -> dict:
        args = ["spend-request", "create", "--merchant-name", entry["store"], "--merchant-url", entry["url"],
                "--amount", str(entry["amount_cents"]), "--currency", entry.get("currency", "usd"),
                "--context", context(entry), "--request-approval"]
        return self._call(*args, *(["--test"] if self.test else []))

    def status(self, spend_id: str) -> str:
        return str(self._call("spend-request", "retrieve", spend_id).get("status") or "")

    def card(self, spend_id: str) -> dict:
        """The card, read from Link's 0600 file and the file removed at once. Stdout only ever has it redacted."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{spend_id}-{uuid.uuid4().hex[:6]}.json"
        try:
            self._call("spend-request", "retrieve", spend_id, "--include", "card", "--output-file", str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
        card = data.get("card") if isinstance(data.get("card"), dict) else data
        if not all(card.get(k) for k in ("number", "cvc", "exp_month", "exp_year")):
            raise LinkError("Link's card came back incomplete")
        return card

    def cancel(self, spend_id: str) -> None:
        try:
            self._call("spend-request", "cancel", spend_id)
        except LinkError:
            pass


def context(entry: dict) -> str:
    """Link wants at least 100 characters on what the money is for."""
    text = (f"Michael approved paying {entry['store']} {money(entry['amount_cents'])} for {entry['what']}, tax and "
            f"fees included, as a one-time purchase at {entry['host']}. Requested by his assistant Juno from a card "
            "he tapped in Discord.")
    return text if len(text) >= 100 else text + " " + "No other charges are approved." * 2


def card_entry(req: dict, cfg: dict) -> dict:
    amount = money(req["amount_cents"])
    return {"id": f"a-{uuid.uuid4().hex[:8]}", "kind": "action", "action_class": ACTION,
            "summary": f"Pay {amount} to {req['store']}?",
            "action": f"Pay {amount} to {req['store']} for {req['what']}.",
            "why": req.get("why") or req["what"], "store": req["store"], "host": req["host"], "url": req["url"],
            "amount_cents": req["amount_cents"], "currency": req.get("currency", "usd"), "what": req["what"],
            "live": cfg["live"], "request_id": req["id"], "session_id": req.get("session_id"), "status": "new",
            "from_timer": False, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def process(root: Path, approvals_add, audit=None, path: Path | None = None, cfg: dict | None = None) -> list[str]:
    """New payment requests → cards, after checking the rules once more. Returns lines for refused requests."""
    path = path or root / "state" / "payment-requests.json"
    cfg = cfg or pay_queue.config(root / "me" / "payments.yaml")
    lines = []
    for req in [r for r in pay_queue.load(path) if r.get("status") == "new"]:
        try:
            pay_queue.check(req, cfg, pay_queue.load(path))
        except pay_queue.Bad as exc:
            pay_queue.update(req["id"], path, status="refused", note=str(exc))
            lines.append(f"I didn't ask to pay {req.get('store')}: {exc}. Nothing was charged. 🙃")
            continue
        entry = card_entry(req, cfg)
        approvals_add(entry)
        pay_queue.update(req["id"], path, status="carded", approval_id=entry["id"])
        if audit:
            audit("payment_carded", entry, money(req["amount_cents"]))
    return lines


def start(root: Path, entry: dict, link: Link | None, path: Path | None = None, cfg: dict | None = None,
          now: datetime | None = None) -> str:
    """Michael tapped Pay. Rules again (the caps may have changed since the card), then the Link request."""
    path = path or root / "state" / "payment-requests.json"
    cfg = cfg or pay_queue.config(root / "me" / "payments.yaml")
    req = next((r for r in pay_queue.load(path) if r.get("id") == entry.get("request_id")), None)
    if not req or req.get("status") != "carded":
        return "That payment isn't waiting anymore, so nothing was charged. 🧐"
    if any(req.get(k) != entry.get(k) for k in ("amount_cents", "url", "store")):
        pay_queue.update(req["id"], path, status="refused", note="card and request differ")
        return "That card doesn't match the request anymore, so I didn't pay. Ask again for a fresh one. 🧐"
    if bool(cfg["live"]) != bool(entry.get("live")):
        pay_queue.update(req["id"], path, status="refused", note="test or live mode changed since the card")
        return "Test mode was switched since that card, so I didn't pay. Ask again for a fresh one. 🧐"
    try:
        pay_queue.check(req, cfg, pay_queue.load(path), now)
    except pay_queue.Bad as exc:
        pay_queue.update(req["id"], path, status="refused", note=str(exc))
        return f"I didn't pay: {exc}. Nothing was charged. 🙃"
    if link is None:
        pay_queue.update(req["id"], path, status="stopped", note="link-cli not installed")
        return NOT_INSTALLED
    try:
        out = link.create(entry)
    except LinkError as exc:
        pay_queue.update(req["id"], path, status="stopped", note=str(exc)[:200])
        return f"Link wouldn't take the request, so nothing was charged ({str(exc)[:120]}). 🙃"
    spend_id = str(out.get("id") or "")
    if not spend_id:
        pay_queue.update(req["id"], path, status="stopped", note="no spend request id")
        return "Link didn't give me a request to approve, so nothing was charged. 🙃"
    pay_queue.update(req["id"], path, status="requested", spend_id=spend_id,
                     requested_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                     approval_id=entry["id"])
    test = "" if entry.get("live") else " It's test mode, so nothing real gets charged."
    return (f"Asked Link for {money(entry['amount_cents'])} at {entry['store']}. Approve it in your Link app in the "
            f"next 30 minutes and I'll finish the checkout.{test} 🔐")


def deny(root: Path, entry: dict, path: Path | None = None) -> None:
    path = path or root / "state" / "payment-requests.json"
    if entry.get("request_id"):
        pay_queue.update(entry["request_id"], path, status="denied")


def step(root: Path, link: Link | None, open_browser, path: Path | None = None, now: datetime | None = None,
         audit=None) -> list[str]:
    """Requests waiting on his passkey: check each once; pay the approved ones. Returns lines for Michael."""
    path = path or root / "state" / "payment-requests.json"
    now = now or datetime.now(timezone.utc)
    lines = []
    for req in [r for r in pay_queue.load(path) if r.get("status") == "requested"]:
        if link is None:
            break
        try:
            status = link.status(req["spend_id"])
        except LinkError:
            continue  # try again on the next pass
        if status in WAITING:
            asked = datetime.fromisoformat(req.get("requested_at") or now.isoformat())
            if now - asked > APPROVAL_WINDOW:
                link.cancel(req["spend_id"])
                pay_queue.update(req["id"], path, status="expired")
                lines.append(f"The Link approval for {req['store']} ran out, so nothing was charged. Ask again if "
                             "you still want it. 😴")
            continue
        if status != "approved":
            pay_queue.update(req["id"], path, status="declined", note=status)
            lines.append(f"Link says the {req['store']} payment wasn't approved ({status}), so nothing was charged.")
            continue
        pay_queue.update(req["id"], path, status="paying")
        lines.append(pay(req, link, open_browser, path, audit))
    return lines


def pay(req: dict, link: Link, open_browser, path: Path, audit=None) -> str:
    import checkout
    amount, store = money(req["amount_cents"]), req["store"]
    browser = None
    try:
        card = link.card(req["spend_id"])
        browser = open_browser()
        if browser is None:
            outcome = checkout.Outcome(False, False, "the browser isn't set up on this PC")
        else:
            outcome = checkout.complete(browser, req["url"], card, req["amount_cents"], store)
    except Exception as exc:  # never with card text: exceptions here are ours or Link's, both card-free
        outcome = checkout.Outcome(False, False, f"something broke before I pressed pay ({type(exc).__name__})")
    finally:
        card = None
        if browser is not None:
            browser.close()
    if audit:
        audit("payment_paid" if outcome.paid else "payment_stopped", {"id": req.get("approval_id"),
              "action_class": ACTION, "summary": f"{amount} to {store}"}, outcome.line[:200])
    if outcome.paid:
        pay_queue.update(req["id"], path, status="paid", confirmation=outcome.confirmation)
        said = f" The page said: \"{outcome.confirmation}\"" if outcome.confirmation else ""
        return f"Paid {amount} to {store} for {req['what']}.{said} 🫡"
    if not outcome.pressed:
        link.cancel(req["spend_id"])
        pay_queue.update(req["id"], path, status="stopped", note=outcome.line[:200])
        return (f"I didn't pay {store}: {outcome.line}. I cancelled the Link card, so nothing was charged. You can "
                f"finish it yourself here: {req['url']} 🙃")
    pay_queue.update(req["id"], path, status="unsure", note=outcome.line[:200])
    return (f"Heads up: {outcome.line}. The card was used on {store} ({amount}), so check your Link app and email "
            "before trying again. 👀")


def link_for(root: Path, cfg: dict | None = None) -> Link | None:
    cfg = cfg or pay_queue.config(root / "me" / "payments.yaml")
    binary = find_link()
    return Link(binary, root / "state" / "pay", test=not cfg["live"]) if binary else None


def browser_for(root: Path):
    """The Playwright MCP server Hands uses, opened for one checkout; None when it isn't installed."""
    import browser_agent
    import checkout
    cli = browser_agent.find_cli()
    if cli is None:
        return None
    browser_agent.write_configs(root, [], cli)
    return checkout.Browser(cli, browser_agent.browser_dir(root) / "playwright.json")
