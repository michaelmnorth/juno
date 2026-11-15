"""Ask to pay for something (Michael 2026-11-15). This is Juno's only way near money, and it moves none.

    python tools/pay_queue.py add --store "Example Tickets" --url https://tickets.example.com/checkout/123 \
        --amount 42.50 --what "2 tickets, Jazz night, Sat Nov 22" --why "He asked for two seats" [--named]
    python tools/pay_queue.py list

`add` checks the request in code against me/payments.yaml (the amount cap, the day's total, the allowed stores) and
writes it to state/payment-requests.json. The bridge then posts a card with the store, the amount and what it's
for. Only his tap asks Link for a one-time card, only his passkey in the Link app approves it, and the bridge's own
code (gateway/checkout.py) types it into that checkout page. Juno never sees, stores or types a card number.
`--named` only when his own DM named this store; a timer run never gets it.
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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "state" / "payment-requests.json"
CONFIG = ROOT / "me" / "payments.yaml"
ZONE = ZoneInfo("America/New_York")
LINK_MAX_USD = 500.0
# Requests that hold money for the day's total: asked, waiting on his passkey, or paid.
COUNTS = ("new", "carded", "requested", "approved", "paying", "paid", "unsure")
DIGITS = re.compile(r"\d[\d -]{11,}\d")


class Bad(ValueError):
    pass


def config(path: Path = CONFIG) -> dict:
    """Missing or broken config means the strictest settings: test mode, $0 caps, no stores."""
    try:
        import yaml
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    def usd(key: str) -> float:
        try:
            return max(0.0, min(float(cfg.get(key) or 0), LINK_MAX_USD))
        except (TypeError, ValueError):
            return 0.0
    stores = [str(s).strip().lower().removeprefix("www.") for s in cfg.get("stores") or [] if str(s).strip()]
    return {"live": cfg.get("live") is True, "per_purchase_usd": usd("per_purchase_usd"),
            "daily_usd": usd("daily_usd"), "stores": stores}


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


def domain(url: str) -> str | None:
    p = urlparse(url or "")
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        return None
    return p.hostname.lower().removeprefix("www.")


def store_allowed(host: str, stores: list[str]) -> bool:
    return any(host == s or host.endswith("." + s) for s in stores)


def _day(at: str) -> str:
    try:
        return datetime.fromisoformat(at).astimezone(ZONE).date().isoformat()
    except (TypeError, ValueError):
        return ""


def spent_today(requests: list[dict], now: datetime | None = None, skip: str = "") -> int:
    """Cents held or paid today, from requests still in play."""
    today = (now or datetime.now(timezone.utc)).astimezone(ZONE).date().isoformat()
    return sum(int(r.get("amount_cents") or 0) for r in requests
               if r.get("id") != skip and r.get("status") in COUNTS and _day(r.get("created")) == today)


def cents(amount: str) -> int:
    m = re.fullmatch(r"\$?\s*(\d{1,4})(?:\.(\d{2}))?", str(amount).strip())
    if not m:
        raise Bad("--amount is dollars and cents, like 42.50")
    value = int(m.group(1)) * 100 + int(m.group(2) or 0)
    if value <= 0:
        raise Bad("--amount must be more than zero")
    return value


def check(req: dict, cfg: dict, requests: list[dict], now: datetime | None = None) -> None:
    """The rules, in code. Run when the request is added and again when Michael taps."""
    if req["amount_cents"] > round(cfg["per_purchase_usd"] * 100):
        raise Bad(f"${req['amount_cents'] / 100:.2f} is over the ${cfg['per_purchase_usd']:.2f} cap per purchase")
    total = spent_today(requests, now, skip=req.get("id", "")) + req["amount_cents"]
    if total > round(cfg["daily_usd"] * 100):
        raise Bad(f"that would bring today to ${total / 100:.2f}, over the ${cfg['daily_usd']:.2f} daily cap")
    if not req.get("named") and not store_allowed(req["host"], cfg["stores"]):
        raise Bad(f"{req['host']} isn't one of his allowed stores; only his own DM naming it can ask for this")


def add(store: str, url: str, amount: str, what: str, why: str = "", session_id: str | None = None,
        named: bool = False, path: Path = PATH, cfg: dict | None = None, env: dict | None = None,
        now: datetime | None = None) -> dict:
    env = os.environ if env is None else env
    cfg = cfg or config()
    if named and env.get("COORDINATOR_UNATTENDED") == "1":
        raise Bad("--named is only for a DM where Michael asked to buy this himself; a timer run can't")
    host = domain(url)
    if host is None:
        raise Bad("--url must be the store's https checkout page")
    for label, text in (("--store", store), ("--what", what), ("--why", why)):
        if DIGITS.search(text or ""):
            raise Bad(f"{label} has a long number in it; card and account numbers never go in a request")
    if not store.strip() or not what.strip():
        raise Bad("--store and --what say who gets paid and for what")
    req = {"id": f"p-{uuid.uuid4().hex[:8]}", "store": store.strip()[:80], "url": url, "host": host,
           "amount_cents": cents(amount), "currency": "usd", "what": what.strip()[:200], "why": why.strip()[:300],
           "named": bool(named), "session_id": session_id, "status": "new",
           "created": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    requests = load(path)
    check(req, cfg, requests, now)
    requests.append(req)
    save(requests, path)
    return req


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--store", required=True)
    a.add_argument("--url", required=True, help="the https checkout page")
    a.add_argument("--amount", required=True, help="the total, tax and fees included, e.g. 42.50")
    a.add_argument("--what", required=True)
    a.add_argument("--why", default="")
    a.add_argument("--named", action="store_true", help="Michael's own DM named this store")
    a.add_argument("--session-id", default="")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            req = add(args.store, args.url, args.amount, args.what, args.why,
                      args.session_id or os.environ.get("CLAUDE_SESSION_ID") or None, named=args.named)
            print(json.dumps({"id": req["id"], "status": "queued",
                              "next": "Michael gets a card; his tap and his passkey in Link pay it."}))
        else:
            print(json.dumps([{k: r.get(k) for k in ("id", "store", "amount_cents", "status", "created")}
                              for r in load()], indent=2))
    except Bad as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
