"""Paying through Stripe Link (Michael 2026-11-15), offline: link-cli and the browser are fakes. The card number is
a Stripe test number and must never show up in anything the code returns or writes."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "gateway", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import approval_policy  # noqa: E402
import checkout  # noqa: E402
import pay_queue  # noqa: E402
import payments  # noqa: E402

NOW = datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)
CFG = {"live": False, "per_purchase_usd": 75.0, "daily_usd": 150.0, "stores": ["tickets.example.com"]}
URL = "https://tickets.example.com/checkout/123"
CARD = {"number": "4000009990001984", "cvc": "321", "exp_month": 4, "exp_year": 2029,
        "billing_address": {"name": "Pat Doe", "postal_code": "02134"}}
SNAP = """- heading "Checkout" [level=1]
- text: Total $42.50
- iframe [ref=e9]:
  - textbox "Card number" [ref=f1e2]
  - textbox "Expiration date MM / YY" [ref=f1e3]
  - textbox "Security code" [ref=f1e4]
- textbox "Name on card" [ref=e11]
- textbox "ZIP code" [ref=e12]
- button "Pay $42.50" [ref=e14] [cursor=pointer]
- link "Back to cart" [ref=e15]"""


def add(tmp_path, amount="42.50", url=URL, named=False, cfg=CFG, env=None, **kw):
    return pay_queue.add("Example Tickets", url, amount, "2 tickets, Jazz night, Sat Nov 22", "He asked",
                         path=tmp_path / "state" / "payment-requests.json", cfg=cfg, named=named,
                         env=env or {}, now=NOW, **kw)


# --- the rules -----------------------------------------------------------------------------------

def test_request_within_the_rules(tmp_path):
    req = add(tmp_path)
    assert req["amount_cents"] == 4250 and req["host"] == "tickets.example.com" and req["status"] == "new"


@pytest.mark.parametrize("amount,url,why", [
    ("80.00", URL, "cap per purchase"),
    ("42.50", "http://tickets.example.com/x", "https checkout"),
    ("42.50", "https://other.example.org/pay", "allowed stores"),
    ("4,250", URL, "dollars and cents"),
    ("0", URL, "more than zero"),
])
def test_requests_outside_the_rules_are_refused(tmp_path, amount, url, why):
    with pytest.raises(pay_queue.Bad, match=why):
        add(tmp_path, amount=amount, url=url)


def test_daily_cap_counts_what_is_in_play(tmp_path):
    add(tmp_path, amount="70.00")
    add(tmp_path, amount="70.00")
    with pytest.raises(pay_queue.Bad, match="daily cap"):
        add(tmp_path, amount="20.00")


def test_named_skips_only_the_store_list_and_never_from_a_timer(tmp_path):
    assert add(tmp_path, url="https://other.example.org/pay", named=True)["named"]
    with pytest.raises(pay_queue.Bad, match="timer"):
        add(tmp_path, named=True, env={"COORDINATOR_UNATTENDED": "1"})
    with pytest.raises(pay_queue.Bad, match="cap per purchase"):
        add(tmp_path, amount="99.00", url="https://other.example.org/pay", named=True)


def test_card_numbers_never_go_in_a_request(tmp_path):
    with pytest.raises(pay_queue.Bad, match="long number"):
        pay_queue.add("Shop", URL, "10.00", "use 4000 0099 9000 1984", path=tmp_path / "r.json", cfg=CFG, env={})


def test_missing_config_is_the_strictest(tmp_path):
    cfg = pay_queue.config(tmp_path / "nope.yaml")
    assert cfg == {"live": False, "per_purchase_usd": 0.0, "daily_usd": 0.0, "stores": []}
    shipped = pay_queue.config(ROOT / "me" / "payments.yaml")
    assert shipped["live"] is False and shipped["per_purchase_usd"] == 75 and shipped["daily_usd"] == 150


# --- Link and the checkout, faked ----------------------------------------------------------------

class FakeLink:
    def __init__(self, statuses=("approved",), action=None, card=None):
        self.statuses, self.created, self.cancelled = list(statuses), [], []
        self.action, self._card = action or {}, card

    def next_action(self, spend_id):
        return dict(self.action)

    def create(self, entry):
        self.created.append(entry)
        return {"id": "lsrq_1", "status": "pending_approval"}

    def status(self, spend_id):
        return self.statuses.pop(0)

    def card(self, spend_id):
        if isinstance(self._card, Exception):
            raise self._card
        return dict(CARD)

    def cancel(self, spend_id):
        self.cancelled.append(spend_id)


class FakeBrowser:
    def __init__(self, page=SNAP, after="Thank you! Order number 88812 is confirmed."):
        self.page, self.after, self.calls, self.closed, self.clicked = page, after, [], False, False

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "browser_click":
            self.clicked = True
        if tool == "browser_snapshot":
            return self.after + " card " + CARD["number"] if self.clicked else self.page
        return ""

    def close(self):
        self.closed = True


def carded(tmp_path):
    root = tmp_path
    (root / "state").mkdir(parents=True, exist_ok=True)
    add(tmp_path)
    cards = []
    lines = payments.process(root, cards.append, cfg=CFG)
    assert lines == [] and len(cards) == 1
    return root, cards[0]


def test_card_shows_store_amount_and_test_mode_with_no_always(tmp_path):
    root, entry = carded(tmp_path)
    assert entry["action_class"] == "payment.link" and entry["summary"] == "Pay $42.50 to Example Tickets?"
    text = json.dumps(approval_policy.blocks(entry, root=root))
    assert "Test mode: nothing is charged" in text and "$42.50" in text and '"Pay"' in text
    assert "Always" not in text and "payment.link" not in approval_policy.ALWAYS_ALLOWABLE
    assert approval_policy.auto_ok(entry, root / "state", {"actions": {"payment.link": {"mode": "auto"}}}) is None


def test_tap_asks_link_in_test_mode(tmp_path):
    root, entry = carded(tmp_path)
    link = FakeLink()
    line = payments.start(root, entry, link, cfg=CFG, now=NOW)
    assert "Approve and use your passkey" in line and "test mode" in line
    req = pay_queue.load(root / "state" / "payment-requests.json")[0]
    assert req["status"] == "requested" and req["spend_id"] == "lsrq_1"
    assert payments.start(root, entry, link, cfg=CFG, now=NOW).startswith("That payment isn't waiting")
    assert len(link.created) == 1


def test_link_command_and_context():
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return NS(returncode=0, stdout=json.dumps({"id": "lsrq_9"}), stderr="")
    entry = {"store": "Example Tickets", "url": URL, "host": "tickets.example.com", "amount_cents": 4250,
             "what": "2 tickets"}
    out = payments.Link("link-cli", Path("."), test=True, run=run).create(entry)
    cmd = seen[0]
    assert out["id"] == "lsrq_9" and cmd[cmd.index("--amount") + 1] == "4250" and "--test" in cmd
    assert "--request-approval" in cmd and len(cmd[cmd.index("--context") + 1]) >= 100


def test_card_file_is_read_and_removed(tmp_path):
    def run(cmd, **kw):
        out = Path(cmd[cmd.index("--output-file") + 1])
        out.write_text(json.dumps({"card": CARD}), encoding="utf-8")
        return NS(returncode=0, stdout=json.dumps({"card": {"last4": "1984"}}), stderr="")
    link = payments.Link("link-cli", tmp_path / "pay", test=True, run=run)
    assert link.card("lsrq_1")["number"] == CARD["number"]
    assert list((tmp_path / "pay").glob("*")) == []


def test_tap_without_link_installed_or_after_caps_change(tmp_path):
    root, entry = carded(tmp_path)
    assert payments.start(root, entry, None, cfg=CFG, now=NOW) == payments.NOT_INSTALLED
    root2, entry2 = carded(tmp_path / "b")
    tighter = {**CFG, "per_purchase_usd": 20.0}
    assert "over the $20.00 cap" in payments.start(root2, entry2, FakeLink(), cfg=tighter, now=NOW)
    root3, entry3 = carded(tmp_path / "c")
    assert "Test mode was switched" in payments.start(root3, entry3, FakeLink(), cfg={**CFG, "live": True}, now=NOW)


def requested(tmp_path, link):
    root, entry = carded(tmp_path)
    payments.start(root, entry, link, cfg=CFG, now=NOW)
    return root


def test_approved_in_link_pays_and_never_leaks_the_card(tmp_path):
    link = FakeLink(["pending_approval", "approved"])
    root = requested(tmp_path, link)
    browser = FakeBrowser()
    assert payments.step(root, link, lambda: browser, now=NOW + timedelta(minutes=1)) == []  # still waiting
    lines = payments.step(root, link, lambda: browser, now=NOW + timedelta(minutes=2))
    assert len(lines) == 1 and lines[0].startswith("Paid $42.50 to Example Tickets") and "88812" in lines[0]
    assert CARD["number"] not in lines[0] and browser.closed
    typed = {a["element"]: a["text"] for t, a in browser.calls if t == "browser_type"}
    assert typed["Card number"] == CARD["number"] and typed["Expiration date MM / YY"] == "04 / 29"
    assert typed["Security code"] == "321" and typed["Name on card"] == "Pat Doe" and typed["ZIP code"] == "02134"
    assert [a["element"] for t, a in browser.calls if t == "browser_click"] == ["Pay $42.50"]
    saved = (root / "state" / "payment-requests.json").read_text(encoding="utf-8")
    assert CARD["number"] not in saved and json.loads(saved)["requests"][0]["status"] == "paid"


def test_wrong_total_presses_nothing_and_cancels(tmp_path):
    link = FakeLink(["approved"])
    root = requested(tmp_path, link)
    browser = FakeBrowser(page=SNAP.replace("$42.50", "$52.50"))
    line = payments.step(root, link, lambda: browser, now=NOW)[0]
    assert "approved total of $42.50" in line and "nothing was charged" in line and URL in line
    assert link.cancelled == ["lsrq_1"] and not browser.clicked


def test_pressed_without_confirmation_says_check(tmp_path):
    link = FakeLink(["approved"])
    root = requested(tmp_path, link)
    line = payments.step(root, link, lambda: FakeBrowser(after="Loading..."), now=NOW)[0]
    assert line.startswith("Heads up") and "check your Link app" in line and link.cancelled == []
    assert pay_queue.load(root / "state" / "payment-requests.json")[0]["status"] == "unsure"


def test_approval_runs_out_or_is_declined(tmp_path):
    link = FakeLink(["pending_approval"])
    root = requested(tmp_path, link)
    line = payments.step(root, link, lambda: None, now=NOW + timedelta(minutes=40))[0]
    assert "ran out" in line and link.cancelled == ["lsrq_1"]
    link2 = FakeLink(["denied"])
    root2 = requested(tmp_path / "b", link2)
    assert "wasn't approved" in payments.step(root2, link2, lambda: None, now=NOW)[0]


CHECK = {"type": "partner_auth_challenge", "resolution": "auto_resume",
         "action_url": "https://app.link.com/verify/abc"}


def test_extra_check_is_sent_once_then_pays(tmp_path):
    link = FakeLink(["requires_action", "requires_action", "approved"], action=CHECK)
    root = requested(tmp_path, link)
    first = payments.step(root, link, lambda: FakeBrowser(), now=NOW + timedelta(minutes=1))
    assert len(first) == 1 and "one more check" in first[0] and CHECK["action_url"] in first[0]
    assert payments.step(root, link, lambda: FakeBrowser(), now=NOW + timedelta(minutes=2)) == []  # told once
    assert payments.step(root, link, lambda: FakeBrowser(), now=NOW + timedelta(minutes=3))[0].startswith("Paid")


def test_extra_check_that_needs_a_new_request_stops_it(tmp_path):
    act = {**CHECK, "resolution": "create_new_spend_request_after_completion"}
    link = FakeLink(["requires_action"], action=act)
    root = requested(tmp_path, link)
    line = payments.step(root, link, lambda: None, now=NOW)[0]
    assert "stopped this one" in line and "nothing was charged" in line and link.cancelled == ["lsrq_1"]
    assert pay_queue.load(root / "state" / "payment-requests.json")[0]["status"] == "stopped"


def test_only_link_pages_are_passed_on():
    assert payments.link_url("https://app.link.com/x") == "https://app.link.com/x"
    assert payments.link_url("https://checkout.stripe.com/y") == "https://checkout.stripe.com/y"
    for bad in ("http://app.link.com/x", "https://link.com.evil.example/x", "https://evil.example/link.com"):
        assert payments.link_url(bad) == ""


def test_expired_card_is_refused_before_typing(tmp_path):
    def run(cmd, **kw):
        Path(cmd[cmd.index("--output-file") + 1]).write_text(
            json.dumps({"card": {**CARD, "valid_until": int(NOW.timestamp()) + 60}}), encoding="utf-8")
        return NS(returncode=0, stdout="{}", stderr="")
    link = payments.Link("link-cli", tmp_path / "pay", test=True, run=run)
    with pytest.raises(payments.CardExpired):
        link.card("lsrq_1", now=NOW)
    assert list((tmp_path / "pay").glob("*")) == []
    fresh = {**CARD, "valid_until": "2026-11-15T18:00:00Z"}
    run2 = lambda cmd, **kw: (Path(cmd[cmd.index("--output-file") + 1]).write_text(  # noqa: E731
        json.dumps({"card": fresh}), encoding="utf-8"), NS(returncode=0, stdout="{}", stderr=""))[1]
    assert payments.Link("link-cli", tmp_path / "pay", test=True, run=run2).card("lsrq_1", now=NOW)["cvc"] == "321"


def test_expired_card_cancels_and_presses_nothing(tmp_path):
    link = FakeLink(["approved"], card=payments.CardExpired("the one-time card from Link had already run out"))
    root = requested(tmp_path, link)
    browser = FakeBrowser()
    line = payments.step(root, link, lambda: browser, now=NOW)[0]
    assert "had already run out" in line and "nothing was charged" in line
    assert link.cancelled == ["lsrq_1"] and not browser.calls


def test_windows_runs_node_on_links_script_not_the_cmd_shim(tmp_path):
    npm = tmp_path / "npm"
    pkg = npm / "node_modules" / "@stripe" / "link-cli"
    (pkg / "dist").mkdir(parents=True)
    (pkg / "dist" / "cli.js").write_text("", encoding="utf-8")
    (pkg / "package.json").write_text(json.dumps({"bin": {"link-cli": "./dist/cli.js"}}), encoding="utf-8")
    shim = str(npm / "link-cli.CMD")
    which = {"link-cli": shim, "node": r"C:\node\node.exe"}.get
    cmd = payments.find_link({}, which=which, windows=True)
    assert cmd[0] == r"C:\node\node.exe" and cmd[1].endswith("cli.js") and not cmd[1].lower().endswith(".cmd")
    (pkg / "dist" / "cli.js").unlink()
    assert payments.find_link({}, which=which, windows=True) is None  # never falls back to the shim
    assert payments.find_link({}, which={"link-cli": "/usr/bin/link-cli"}.get, windows=False) == ["/usr/bin/link-cli"]
    seen = []
    payments.Link(["node", "cli.js"], tmp_path, test=True,
                  run=lambda c, **kw: seen.append(c) or NS(returncode=0, stdout="{}", stderr="")).status("lsrq_1")
    assert seen[0][:4] == ["node", "cli.js", "spend-request", "retrieve"]


# --- reading the checkout page -------------------------------------------------------------------

def test_plan_refuses_two_pay_buttons_and_finds_month_and_year():
    two = SNAP + '\n- button "Pay now" [ref=e20]'
    assert "more than one pay button" in checkout.plan(two, CARD, 4250)[2]
    split = SNAP.replace('- textbox "Expiration date MM / YY" [ref=f1e3]',
                         '- combobox "Month" [ref=f1e5]\n  - combobox "Year" [ref=f1e6]')
    fields, button, why = checkout.plan(split, CARD, 4250)
    assert not why and ("Month", "f1e5", "04") in fields and ("Year", "f1e6", "2029") in fields
    assert "card number" in checkout.plan(SNAP.replace("Card number", "Gift note"), CARD, 4250)[2]


def test_reminds_twice_before_link_runs_out_then_expires_with_an_audit(tmp_path):
    link = FakeLink(["pending_approval"] * 5)
    root = requested(tmp_path, link)
    events = []
    audit = lambda event, entry, note: events.append(event)  # noqa: E731
    step = lambda minutes: payments.step(root, link, lambda: None, now=NOW + timedelta(minutes=minutes),  # noqa: E731
                                         audit=audit)
    assert step(5) == []
    first = step(11)
    assert len(first) == 1 and "step two is in the Link app" in first[0] and "19 minutes left" in first[0]
    assert step(12) == []  # once per reminder
    last = step(26)
    assert len(last) == 1 and last[0].startswith("Last call") and "4 minutes" in last[0]
    gone = step(36)
    assert "ran out before your passkey" in gone[0] and link.cancelled == ["lsrq_1"]
    assert events == ["payment_reminded", "payment_reminded", "payment_expired"]


def test_late_first_check_sends_only_the_last_call(tmp_path):
    link = FakeLink(["pending_approval"])
    root = requested(tmp_path, link)
    lines = payments.step(root, link, lambda: None, now=NOW + timedelta(minutes=27))
    assert len(lines) == 1 and lines[0].startswith("Last call")
