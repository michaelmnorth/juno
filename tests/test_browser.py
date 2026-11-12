"""P2 step 7: the browser agent fills, a card shows everything, and only a tap submits (docs/v2/briefs/P2-DO-THINGS.md)."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))
sys.path.insert(0, str(ROOT / "tools"))

import approval_policy  # noqa: E402
import browser_agent  # noqa: E402
import browser_queue  # noqa: E402
import claude_runner  # noqa: E402
import slack_bridge  # noqa: E402
import state_store  # noqa: E402
from state_store import Approvals, SessionMap  # noqa: E402

from test_hooks import decision, run_hook  # noqa: E402

_spec = importlib.util.spec_from_file_location("gate_browser", ROOT / ".claude" / "hooks" / "gate_browser.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SITE = "https://www.example.com"
FILL = {"JUNO_BROWSER_RUN": "fill", "JUNO_BROWSER_ORIGINS": SITE}
T = "mcp__playwright__"


def d(tool, data, env, root, session="s1"):
    return "deny" if gate.decide(T + tool, data, env, root, session) else "allow"


# --- the gate hook -------------------------------------------------------------------------------

def test_hook_denies_playwright_outside_a_browser_run():
    assert decision(run_hook("gate_browser.py", T + "browser_snapshot", {})) == "deny"
    assert decision(run_hook("gate_browser.py", T + "browser_snapshot", {}, FILL)) == "allow"
    assert decision(run_hook("gate_browser.py", "Read", {"file_path": "x"})) == "allow"  # not its business


@pytest.mark.parametrize("tool", ["browser_evaluate", "browser_run_code_unsafe", "browser_file_upload",
                                  "browser_route", "browser_cookie_set", "browser_tabs", "browser_install"])
def test_risky_tools_never(tool, tmp_path):
    assert d(tool, {}, FILL, tmp_path) == "deny"


def test_navigate_stays_on_the_site(tmp_path):
    assert d("browser_navigate", {"url": SITE + "/claim"}, FILL, tmp_path) == "allow"
    assert d("browser_navigate", {"url": "http://www.example.com/claim"}, FILL, tmp_path) == "deny"
    assert d("browser_navigate", {"url": "https://evil.example.net/"}, FILL, tmp_path) == "deny"
    assert d("browser_navigate", {"url": "https://www.example.com.evil.net/"}, FILL, tmp_path) == "deny"


@pytest.mark.parametrize("field,value", [("Card", "4111 1111 1111 1111"), ("Notes", "ssn 123-45-6789"),
                                         ("Password", "hunter2"), ("Account number", "12"),
                                         ("Verification code", "123456")])
def test_secrets_never_typed(field, value, tmp_path):
    assert d("browser_type", {"element": field, "text": value}, FILL, tmp_path) == "deny"
    assert d("browser_fill_form", {"fields": [{"name": field, "value": value}]}, FILL, tmp_path) == "deny"


def test_ordinary_values_and_numbers_are_fine(tmp_path):
    assert d("browser_fill_form", {"fields": [{"name": "Spin speed", "value": "High"},
                                              {"name": "Passenger count", "value": "2"},
                                              {"name": "Shipping address 2", "value": ""},
                                              {"name": "Footprint", "value": "27 in"}]}, FILL, tmp_path) == "allow"
    assert d("browser_fill_form", {"fields": [{"name": "Serial number", "value": "512KWYY4B123"},
                                              {"name": "Phone", "value": "404-555-0100"},
                                              {"name": "Model", "value": "WM1234HWA"}]}, FILL, tmp_path) == "allow"


@pytest.mark.parametrize("label", ["Place order", "Pay now", "Sign up", "Create an account", "Checkout",
                                   "Add to cart", "Log in"])
def test_never_buys_or_signs_up(label, tmp_path):
    for mode in ("fill", "submit"):
        assert d("browser_click", {"element": f"{label} button"}, {**FILL, "JUNO_BROWSER_RUN": mode},
                 tmp_path) == "deny"


def test_fill_run_never_submits(tmp_path):
    assert d("browser_click", {"element": "Warranty claim link"}, FILL, tmp_path) == "allow"  # before any value
    assert d("browser_press_key", {"key": "Enter"}, FILL, tmp_path) == "deny"
    assert d("browser_type", {"element": "Name", "text": "Sam", "submit": True}, FILL, tmp_path) == "deny"
    assert d("browser_type", {"element": "Name", "text": "Sam"}, FILL, tmp_path) == "allow"
    assert d("browser_click", {"element": "Submit claim button"}, FILL, tmp_path) == "deny"  # a value is in now
    assert d("browser_click", {"element": "the blue button"}, FILL, tmp_path) == "deny"
    assert d("browser_click", {"element": "Submit"}, FILL, tmp_path, session="other") == "allow"  # another run


def _pass(root: Path, approval_id="a-1", values=("Sam", "WM1234"), age=0):
    p = root / "state" / "browser" / "pass.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    made = datetime.now(timezone.utc) - timedelta(seconds=age)
    p.write_text(json.dumps({"approval_id": approval_id, "values": list(values), "created": made.isoformat()}),
                 encoding="utf-8")


def test_submit_needs_the_pass_and_only_its_values(tmp_path):
    env = {**FILL, "JUNO_BROWSER_RUN": "submit", "JUNO_BROWSER_PASS": "a-1"}
    assert d("browser_click", {"element": "Submit claim"}, env, tmp_path) == "deny"  # no pass yet
    _pass(tmp_path)
    assert d("browser_click", {"element": "Submit claim"}, env, tmp_path) == "allow"
    assert d("browser_type", {"element": "Name", "text": " sam "}, env, tmp_path) == "allow"
    assert d("browser_type", {"element": "Name", "text": "Alex"}, env, tmp_path) == "deny"
    assert d("browser_click", {"element": "Submit"}, {**env, "JUNO_BROWSER_PASS": "a-2"}, tmp_path) == "deny"
    _pass(tmp_path, age=gate.PASS_MAX_AGE + 5)
    assert d("browser_click", {"element": "Submit claim"}, env, tmp_path) == "deny"


# --- the queue the coordinator writes ------------------------------------------------------------

def test_queue_checks_before_anything_runs(tmp_path):
    path = tmp_path / "q.json"
    vals = browser_queue.parse_values(["First name=Sam", "Model=WM1234"])
    with pytest.raises(browser_queue.Bad):
        browser_queue.add("http://www.example.com/x", "claim", vals, path=path)
    with pytest.raises(browser_queue.Bad):
        browser_queue.add(SITE, "claim", vals + [{"field": "Card", "value": "4111111111111111"}], path=path)
    with pytest.raises(browser_queue.Bad):
        browser_queue.parse_values(["no equals sign"])
    req = browser_queue.add(SITE + "/claim", "File the claim", vals, ["https://forms.example.org"], path=path)
    assert req["origins"] == [SITE, "https://forms.example.org"] and browser_queue.load(path)[0]["status"] == "new"


# --- fill, card, submit --------------------------------------------------------------------------

class Runner:
    def __init__(self, text):
        self.text, self.calls = text, []

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return claude_runner.RunResult(text=self.text, session_id="s", is_error=False)


FILLED = json.dumps({"ok": True, "site": "Example", "url": SITE + "/claim", "form": "warranty claim",
                     "fields": [{"label": "First name", "value": "Sam"}, {"label": "Model", "value": "WM1234"}],
                     "submit_label": "Submit claim", "missing": [], "needs_michael": "", "notes": ""})


@pytest.fixture
def cli(tmp_path, monkeypatch):
    fake = tmp_path / "cli.js"
    fake.write_text("// fake", encoding="utf-8")
    monkeypatch.setattr(browser_agent, "find_cli", lambda env=None: fake)
    return fake


def _req(tmp_path):
    return browser_queue.add(SITE + "/claim", "File the free part claim",
                             browser_queue.parse_values(["First name=Sam", "Model=WM1234"]), why="Free pump program",
                             session_id="sess", path=tmp_path / "state" / "browser-requests.json")


def test_fill_run_is_its_own_lean_browser_run(tmp_path, cli):
    run = Runner("Done.\n" + FILLED)
    entry, line = browser_agent.fill(run, tmp_path, _req(tmp_path))
    prompt, kw = run.calls[0]
    assert line == "" and entry["action_class"] == "web.form.submit" and entry["submit_label"] == "Submit claim"
    assert entry["fields"][1] == {"label": "Model", "value": "WM1234"} and entry["session_id"] == "sess"
    assert all(t.startswith("mcp__playwright__") for t in kw["allowed_tools"])
    assert "mcp__playwright__browser_evaluate" not in kw["allowed_tools"]
    assert kw["env_extra"]["JUNO_BROWSER_RUN"] == "fill" and kw["env_extra"]["JUNO_BROWSER_ORIGINS"] == SITE
    assert "do NOT submit" in prompt and "Model: WM1234" in prompt
    mcp = json.loads(Path(kw["mcp_config"]).read_text(encoding="utf-8"))
    args = mcp["mcpServers"]["playwright"]["args"]
    pw = json.loads(Path(args[args.index("--config") + 1]).read_text(encoding="utf-8"))
    assert pw["browser"]["launchOptions"]["headless"] is True and pw["browser"]["browserName"] == "chromium"
    assert pw["webmcp"] is False and "network" not in pw  # the hook checks navigation; see the template
    assert Path(pw["browser"]["userDataDir"]) == tmp_path / "state" / "browser" / "profile"
    hooks = json.loads(Path(kw["settings_file"]).read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]
    assert hooks["matcher"] == "mcp__playwright__.*" and hooks["hooks"][0]["args"][0].endswith("gate_browser.py")


def test_fill_stops_without_a_card_when_he_is_needed(tmp_path, cli):
    run = Runner(json.dumps({**json.loads(FILLED), "needs_michael": "a login"}))
    entry, line = browser_agent.fill(run, tmp_path, _req(tmp_path))
    assert entry is None and "a login" in line and "Nothing was submitted" in line


def test_not_installed_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_agent, "find_cli", lambda env=None: None)
    entry, line = browser_agent.fill(Runner(FILLED), tmp_path, _req(tmp_path))
    assert entry is None and line == browser_agent.NOT_INSTALLED


def test_process_turns_requests_into_cards(tmp_path, cli):
    _req(tmp_path)
    cards = []
    lines = browser_agent.process(Runner(FILLED), tmp_path, cards.append)
    req = browser_queue.load(tmp_path / "state" / "browser-requests.json")[0]
    assert lines == [] and len(cards) == 1 and req["status"] == "carded" and req["approval_id"] == cards[0]["id"]
    assert browser_agent.process(Runner(FILLED), tmp_path, cards.append) == [] and len(cards) == 1  # once only


def test_submit_claims_only_a_confirmed_submission(tmp_path, cli):
    entry, _ = browser_agent.fill(Runner(FILLED), tmp_path, _req(tmp_path))
    seen, follow = {}, []

    class Check(Runner):
        def __call__(self, prompt, **kw):
            seen["pass"] = json.loads((tmp_path / "state" / "browser" / "pass.json").read_text(encoding="utf-8"))
            return super().__call__(prompt, **kw)

    ok, line = browser_agent.submit(Check(json.dumps({"submitted": True, "confirmation": "Thanks, claim received.",
                                                      "reference": "C-123"})), tmp_path, entry,
                                    add_followup=lambda **kw: follow.append(kw))
    assert ok and "claim received" in line and "C-123" in line
    assert seen["pass"]["approval_id"] == entry["id"] and seen["pass"]["values"] == ["Sam", "WM1234"]
    assert not (tmp_path / "state" / "browser" / "pass.json").exists()
    assert follow and follow[0]["match"] == "example,C-123"
    ok, line = browser_agent.submit(Runner(json.dumps({"submitted": True, "confirmation": ""})), tmp_path, entry)
    assert not ok and "not sent" in line
    ok, line = browser_agent.submit(Runner(json.dumps({"submitted": False, "differs": "a new required field"})),
                                    tmp_path, entry)
    assert not ok and "a new required field" in line


# --- the card --------------------------------------------------------------------------------------

def _entry(**over):
    return {"id": "a-1", "action_class": "web.form.submit", "summary": "Submit the warranty claim on www.example.com?",
            "action": "Submit it", "site": "www.example.com", "url": SITE + "/claim", "submit_label": "Submit claim",
            "fields": [{"label": "First name", "value": "Sam"}, {"label": "Note", "value": "<https://x.io|tap>"}],
            "status": "new", "created": "2026-11-12T12:00:00+00:00", **over}


def test_card_shows_site_values_and_button_and_is_never_automatic(tmp_path):
    entry = _entry()
    text = json.dumps(approval_policy.blocks(entry, root=tmp_path))
    assert "www.example.com" in text and "First name: Sam" in text and "Submit claim" in text
    assert "Yes, submit" in text and "always" not in text.lower().replace("always add", "")
    assert "<https://x.io|tap>" not in text and "&lt;https://x.io|tap&gt;" in text
    assert approval_policy.auto_ok(entry, tmp_path, {"actions": {"web.form.submit": {"mode": "auto"}}}) is None
    assert "web.form.submit" not in approval_policy.ALWAYS_ALLOWABLE


def test_tap_binds_the_values(tmp_path):
    entry = _entry()
    before = state_store.payload_hash(entry)
    entry["fields"][0]["value"] = "Alex"
    assert state_store.payload_hash(entry) != before
    old = {"action_class": "email.send", "summary": "s", "action": "a"}  # cards from before stay valid
    keyed = {k: old.get(k) for k in state_store.PAYLOAD_KEYS}
    canon = json.dumps(keyed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    import hashlib
    assert state_store.payload_hash(old) == hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_tapped_card_submits_in_the_bridge_not_a_resumed_session(tmp_path, monkeypatch):
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "notify-allowlist.json").write_text(json.dumps({"slack": ["U_M"]}), encoding="utf-8")
    monkeypatch.setattr(slack_bridge, "heartbeat", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(browser_agent, "submit", lambda run, root, entry, add_followup=None:
                        calls.append(entry["id"]) or (True, "Submitted on www.example.com."))
    runner = Runner("unused")
    b = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                            approvals=Approvals(tmp_path / "a.json"), runner=runner)
    b.approvals.append(_entry())
    b.approvals.mark("a-1", "posted")
    assert b.handle_approval("a-1", "approved", user_id="U_M") == "Submitted on www.example.com."
    assert calls == ["a-1"] and runner.calls == []
    b.approvals.append(_entry(id="a-2"))
    b.approvals.mark("a-2", "posted")
    assert b.handle_approval("a-2", "approved", user_id="U_STRANGER") == "" and calls == ["a-1"]


# --- the runner flags ------------------------------------------------------------------------------

def test_runner_mcp_agent_run_flags(tmp_path):
    out = claude_runner.run("x", dry_run=True, lean_system="persona", mcp_config=tmp_path / "m.json",
                            settings_file=tmp_path / "s.json", allowed_tools=("mcp__playwright__browser_snapshot",))
    cmd = out.command
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == str(tmp_path / "m.json")
    assert cmd[cmd.index("--settings") + 1] == str(tmp_path / "s.json")
    assert cmd[cmd.index("--setting-sources") + 1] == "user" and "--max-turns" not in cmd
    with pytest.raises(ValueError):
        claude_runner.run("x", dry_run=True, lean_system="p", mcp_config=tmp_path / "m.json")


def test_project_never_loads_playwright_for_the_coordinator():
    perms = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]
    assert "mcp__playwright" in perms["deny"]
