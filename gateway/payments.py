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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import pay_queue  # noqa: E402

ACTION = "payment.link"
WAITING = ("created", "pending_approval", "requires_action")
APPROVAL_WINDOW = timedelta(minutes=35)  # Link gives him 30 minutes; a little slack for the clock
LINK_MINUTES = 30
# Nudges while Link waits on his passkey, in minutes after the request. On 2026-11-14 he tapped Pay in Discord,
# took that as done, and the Link approval ran out 35 minutes later with nothing charged.
REMINDERS = (10, 25)
NOT_INSTALLED = ("Link isn't set up on this PC yet, so I couldn't ask it for a card. Nothing was charged. Michael "
                 "installs it once: `npm i -g @stripe/link-cli`, then `link-cli auth login`. 🙃")


class LinkError(RuntimeError):
    pass


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


class CardExpired(LinkError):
    pass


LINK_HOSTS = ("link.com", "stripe.com")
STOP_RESOLUTIONS = ("create_new_spend_request", "create_new_spend_request_after_completion",
                    "reauthorize_with_additional_scope")


def find_link(env: dict | None = None, which=shutil.which, windows: bool | None = None) -> list[str] | None:
    """The command that runs link-cli. On Windows npm installs a .cmd shim, and cmd.exe reads its arguments again
    (an "&" in a store name would be taken as a second command), so Juno runs node on Link's own script instead, as
    Stripe's skill says. No script found: None, and nothing is asked of Link."""
    env = os.environ if env is None else env
    windows = os.name == "nt" if windows is None else windows
    found = env.get("JUNO_LINK_CLI") or which("link-cli")
    if not found:
        return None
    shim = Path(found)
    if not windows or shim.suffix.lower() == ".exe":
        return [found]
    package = shim.parent / "node_modules" / "@stripe" / "link-cli"
    try:
        bin_ = json.loads((package / "package.json").read_text(encoding="utf-8")).get("bin")
    except (OSError, ValueError):
        return None
    rel = bin_.get("link-cli") if isinstance(bin_, dict) else bin_
    script = package / rel if isinstance(rel, str) else None
    node = str(shim.parent / "node.exe") if (shim.parent / "node.exe").exists() else which("node")
    if script is None or not script.is_file() or not node:
        return None
    return [str(node), str(script)]


def link_url(url: str) -> str:
    """Only a Link or Stripe https page goes to Michael; anything else becomes "open your Link app"."""
    try:
        parts = urlparse(url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    ok = parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in LINK_HOSTS)
    return url if ok else ""


def _until(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class Link:
    """The few link-cli commands Juno uses. `run` is subprocess.run (a fake in tests)."""

    def __init__(self, binary: str | list[str], folder: Path, test: bool, run=subprocess.run):
        self.binary = [binary] if isinstance(binary, str) else list(binary)
        self.folder, self.test, self._run = Path(folder), test, run

    def _call(self, *args: str) -> dict:
        done = self._run([*self.binary, *args, "--format", "json"], capture_output=True, text=True, encoding="utf-8",
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

    def next_action(self, spend_id: str) -> dict:
        """What Link is waiting on (a bank code, an ID check), or {} when nothing is shown."""
        act = self._call("spend-request", "retrieve", spend_id, "--next-action").get("next_action")
        return act if isinstance(act, dict) else {}

    def card(self, spend_id: str, now: datetime | None = None) -> dict:
        """The card, read from Link's 0600 file and the file removed at once. Stdout only ever has it redacted.
        A card whose valid_until has passed (or is under two minutes off) is refused before any typing."""
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
        until = _until(card.get("valid_until"))
        if until is not None and until <= (now or datetime.now(timezone.utc)).timestamp() + 120:
            raise CardExpired("the one-time card from Link had already run out")
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
    by = clock((now or datetime.now(timezone.utc)) + timedelta(minutes=LINK_MINUTES))
    return (f"Step 1 done: your tap. Step 2 is yours, in the Link app: open Link, tap the "
            f"{money(entry['amount_cents'])} request from {entry['store']}, then Approve and use your passkey. "
            f"You have until {by}; I'll finish the checkout the moment it's approved.{test} 🔐")


def clock(at: datetime) -> str:
    """His Eastern time, like 10:31 PM."""
    from zoneinfo import ZoneInfo
    local = at.astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%I:%M %p").lstrip("0")


def reminder(req: dict, now: datetime) -> tuple[str, int] | None:
    """The nudge that is due for a request still waiting on his passkey, with its number, or None."""
    asked = datetime.fromisoformat(req.get("requested_at") or now.isoformat())
    minutes = (now - asked).total_seconds() / 60
    sent = int(req.get("reminders_sent") or 0)
    due = [i for i, at in enumerate(REMINDERS, 1) if minutes >= at and i > sent]
    if not due or minutes >= LINK_MINUTES:
        return None
    left = max(1, round(LINK_MINUTES - minutes))
    amount, store, by = money(req["amount_cents"]), req["store"], clock(asked + timedelta(minutes=LINK_MINUTES))
    if due[-1] < len(REMINDERS):
        line = (f"Still waiting on your passkey for {amount} at {store}. Tapping Pay here was step one; step two is "
                f"in the Link app: open Link, tap the {amount} request, Approve, passkey. About {left} minutes left "
                f"(until {by}). ⏳")
    else:
        line = (f"Last call: the {amount} Link request for {store} runs out in about {left} minutes. Open the Link "
                "app, tap the request, Approve with your passkey, and I'll do the rest. ⏰")
    return line, due[-1]


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
        if status == "requires_action":
            note, stopped = needs_you(req, link, path)
            if note:
                lines.append(note)
            if stopped:
                continue
        about = {"id": req.get("approval_id"), "action_class": ACTION,
                 "summary": f"{money(req['amount_cents'])} to {req['store']}"}
        if status in WAITING:
            asked = datetime.fromisoformat(req.get("requested_at") or now.isoformat())
            if now - asked > APPROVAL_WINDOW:
                link.cancel(req["spend_id"])
                pay_queue.update(req["id"], path, status="expired")
                line = (f"The Link approval for {req['store']} ran out before your passkey, so nothing was charged. "
                        "Say \"pay it again\" if you still want it, and I'll queue a fresh card. 😴")
                if audit:
                    audit("payment_expired", about, "no passkey approval in Link within 30 minutes")
                lines.append(line)
                continue
            nudge = reminder(req, now)
            if nudge:
                pay_queue.update(req["id"], path, reminders_sent=nudge[1])
                if audit:
                    audit("payment_reminded", about, f"reminder {nudge[1]}")
                lines.append(nudge[0])
            continue
        if status != "approved":
            pay_queue.update(req["id"], path, status="declined", note=status)
            if audit:
                audit("payment_declined", about, status)
            lines.append(f"Link says the {req['store']} payment wasn't approved ({status}), so nothing was charged.")
            continue
        pay_queue.update(req["id"], path, status="paying")
        lines.append(pay(req, link, open_browser, path, audit))
    return lines


def needs_you(req: dict, link: Link, path: Path) -> tuple[str | None, bool]:
    """Link is holding the card until Michael does a check (a bank code, an ID check). He gets the link once per
    check. When Link says this request can't go on after it, it is cancelled and he asks again.
    Returns (line for Michael or None, whether the request was stopped)."""
    try:
        act = link.next_action(req["spend_id"])
    except LinkError:
        return None, False
    if not act:
        return None, False
    url = link_url(str(act.get("action_url") or ""))
    where = f" Do it here: {url}" if url else " Open your Link app to do it."
    store, amount = req["store"], money(req["amount_cents"])
    if act.get("resolution") in STOP_RESOLUTIONS:
        link.cancel(req["spend_id"])
        pay_queue.update(req["id"], path, status="stopped", note=f"Link needs {act.get('type') or 'a check'}")
        if act.get("resolution") == "reauthorize_with_additional_scope":
            return (f"Link wants you to sign in to it again before it will pay {store}, so I stopped this one and "
                    "nothing was charged. Ask me to redo the Link sign-in, then ask again. 🔐"), True
        return (f"Link needs one more check from you before it will pay {store}, so I stopped this one and nothing "
                f"was charged.{where} Then ask me again. 🔐"), True
    seen = f"{act.get('type')}|{url}"
    if req.get("action_seen") == seen:
        return None, False
    pay_queue.update(req["id"], path, action_seen=seen)
    return (f"Link needs one more check from you before it releases the card for {store} ({amount}).{where} "
            "I'll finish the checkout once it's done. 🔐"), False


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
    except CardExpired as exc:
        outcome = checkout.Outcome(False, False, str(exc))
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
