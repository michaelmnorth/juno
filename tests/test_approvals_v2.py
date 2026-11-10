"""Approval cards v2 and the outward gate: only what Michael approved can go out, and only in that run."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

import approval_policy  # noqa: E402
import claude_runner  # noqa: E402
import slack_bridge  # noqa: E402
from state_store import Approvals, SessionMap  # noqa: E402

SEND = "mcp__claude_ai_Gmail__send_message"
CREATE = "mcp__claude_ai_Google_Calendar__create_event"
PERMS = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]


def gate(tool, tool_input, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("COORDINATOR_")}
    clean.update(env or {})
    proc = subprocess.run([sys.executable, str(ROOT / ".claude" / "hooks" / "gate_outward.py")],
                          input=json.dumps({"tool_name": tool, "tool_input": tool_input}), text=True,
                          capture_output=True, env=clean, timeout=30)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return out["hookSpecificOutput"]["permissionDecision"] if out else "allow"


# --- settings: grantable, never generally allowed --------------------------------------------------

def test_grantable_tools_are_not_in_the_allow_list():
    for tools in approval_policy.EXECUTABLE.values():
        for tool in tools:
            assert tool not in PERMS["allow"]


def test_other_outward_tools_stay_denied():
    for tool in ("Gmail__forward", "Gmail__reply", "Gmail__trash_thread", "Google_Calendar__delete_event",
                 "Slack__slack_send_message", "Google_Drive__share_file"):
        assert f"mcp__claude_ai_{tool}" in PERMS["deny"]


# --- gate_outward ----------------------------------------------------------------------------------

def test_send_without_approval_denied():
    assert gate(SEND, {"draftId": "d1"}) == "deny"


def test_send_of_approved_draft_allowed():
    assert gate(SEND, {"draftId": "d1"}, {"COORDINATOR_APPROVED_CLASS": "email.send", "COORDINATOR_APPROVED_DRAFT": "d1"}) == "allow"


def test_send_of_other_draft_denied():
    assert gate(SEND, {"draftId": "d2"}, {"COORDINATOR_APPROVED_CLASS": "email.send", "COORDINATOR_APPROVED_DRAFT": "d1"}) == "deny"


def test_send_with_extra_recipients_denied():
    env = {"COORDINATOR_APPROVED_CLASS": "email.send", "COORDINATOR_APPROVED_DRAFT": "d1"}
    assert gate(SEND, {"draftId": "d1", "bcc": ["x@evil.example"]}, env) == "deny"


def test_draft_cannot_change_during_approved_send():
    env = {"COORDINATOR_APPROVED_CLASS": "email.send", "COORDINATOR_APPROVED_DRAFT": "d1"}
    assert gate("mcp__claude_ai_Gmail__update_draft", {"draftId": "d1", "body": "new"}, env) == "deny"
    assert gate("mcp__claude_ai_Gmail__update_draft", {"draftId": "d1", "body": "new"}) == "allow"


def test_hold_with_attendees_denied():
    env = {"COORDINATOR_APPROVED_CLASS": "calendar.hold"}
    assert gate(CREATE, {"summary": "Prep", "startTime": "t", "endTime": "t"}, env) == "allow"
    assert gate(CREATE, {"summary": "Prep", "attendees": [{"email": "a@b.com"}]}, env) == "deny"
    assert gate(CREATE, {"summary": "Prep", "addGoogleMeetUrl": True}, env) == "deny"
    assert gate(CREATE, {"summary": "Prep", "calendarId": "family@group.calendar.google.com"}, env) == "deny"


def test_event_invites_only_approved_people():
    env = {"COORDINATOR_APPROVED_CLASS": "calendar.event.create", "COORDINATOR_APPROVED_RECIPIENTS": "coach@x.com"}
    assert gate(CREATE, {"summary": "S", "attendees": [{"email": "Coach@x.com"}]}, env) == "allow"
    assert gate(CREATE, {"summary": "S", "attendees": [{"email": "other@x.com"}]}, env) == "deny"
    assert gate(CREATE, {"summary": "S"}) == "deny"


# --- policy ----------------------------------------------------------------------------------------

def entry(**kw):
    base = {"id": "a-1", "summary": "Reply to Tim", "action": "send draft", "status": "new",
            "created": datetime.now(timezone.utc).isoformat()}
    base.update(kw)
    return base


def test_timer_cards_expire_after_30_minutes():
    old = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
    assert approval_policy.expired(entry(from_timer=True, created=old))
    assert not approval_policy.expired(entry(created=old))


def test_always_rule_is_per_class_and_recipients(tmp_path):
    e = entry(action_class="email.send", to=["Tim@x.com"])
    assert approval_policy.auto_ok(e, tmp_path, {}) is None
    approval_policy.add_always_rule(tmp_path, e)
    assert approval_policy.auto_ok(entry(action_class="email.send", to=["tim@x.com"]), tmp_path, {}) == "always allowed"
    assert approval_policy.auto_ok(entry(action_class="email.send", to=["mom@x.com"]), tmp_path, {}) is None


def test_hold_auto_from_automation_yaml_but_never_installs(tmp_path):
    auto = {"actions": {"calendar.hold": {"mode": "auto_notify"}, "subagent.install": {"mode": "auto"}}}
    assert approval_policy.auto_ok(entry(action_class="calendar.hold"), tmp_path, auto)
    assert approval_policy.auto_ok(entry(action_class="subagent.install"), tmp_path, auto) is None


def card_buttons(blocks):
    """(button labels, overflow option labels) of a card's actions block."""
    els = next(b for b in blocks if b["type"] == "actions")["elements"]
    labels = [e["text"]["text"] for e in els if e["type"] == "button"]
    more = [o["text"]["text"] for e in els if e["type"] == "overflow" for o in e["options"]]
    return labels, more


def test_draft_card_send_and_edit_up_front_rest_in_overflow():
    e = entry(action_class="email.send", to=["tim@x.com"], draft_id="d1", draft_text="Hey Tim!", draft_link="https://mail.google.com/x")
    assert card_buttons(approval_policy.blocks(e)) == (["Send", "Edit in Gmail"], ["Always send to tim", "Skip"])


def test_draft_card_shows_the_whole_draft_exactly():
    text = "Hey Tim!\n\n" + "\n".join(f"Line {i} " + "x" * 80 for i in range(80)) + "\n\nRegards,\nMichael"
    e = entry(action_class="email.send", to=["tim@x.com"], draft_id="d1", draft_text=text)
    quoted = [b["text"]["text"] for b in approval_policy.blocks(e) if b["type"] == "section" and "text" in b
              and b["text"]["text"].startswith("> ")]
    assert len(quoted) > 1 and all(len(q) <= 3000 for q in quoted)
    assert [line[2:] for line in "\n".join(quoted).splitlines()] == text.splitlines()


def test_draft_card_facts_grid_to_who_subject_why(tmp_path):
    e = entry(action_class="email.send", to=["tim@x.com"], subject="Re: Saturday", why="He asked if you're free")
    grid = next(b for b in approval_policy.blocks(e, None, known_world(tmp_path)) if "fields" in b)["fields"]
    assert [f["text"].split("\n")[0] for f in grid] == ["*To*", "*Who*", "*Subject*", "*Why*"]
    assert "Friend" in grid[1]["text"] and "Re: Saturday" in grid[2]["text"]


def test_install_card_has_no_always():
    labels, more = card_buttons(approval_policy.blocks(entry(action_class="subagent.install")))
    assert labels == ["Yes, install", "Not now"] and more == ["Show files"]


def test_button_names_come_from_the_class_not_the_summary():
    e = entry(action_class="calendar.event.create", attendees=["dana@x.com"], summary="Just a hold, no one invited?")
    assert card_buttons(approval_policy.blocks(e, "known"))[0][0] == "Yes, invite"
    e = entry(action_class="calendar.event.create", summary="Add the dentist?")
    assert card_buttons(approval_policy.blocks(e))[0][0] == "Yes, add it"
    assert card_buttons(approval_policy.blocks(entry(action_class="calendar.event.update")))[0][0] == "Yes, move it"
    assert card_buttons(approval_policy.blocks(entry(action_class="something.new")))[0] == ["Yes", "Not now"]


def test_no_always_for_invites_only_for_holds():
    assert "Always add holds" not in card_buttons(approval_policy.blocks(
        entry(action_class="calendar.event.create", attendees=["a@b.com"]), "known"))[1]
    assert "Always add holds" in card_buttons(approval_policy.blocks(entry(action_class="calendar.hold")))[1]


def test_timer_card_shows_expiry_and_expired_card_offers_ask_again():
    created = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc).isoformat()
    e = entry(action_class="calendar.hold", from_timer=True, created=created)
    grid = next(b for b in approval_policy.blocks(e) if "fields" in b)["fields"]
    assert grid[-1]["text"] == "*Expires*\n9:30 AM"
    gone = approval_policy.expired_blocks(e, now=datetime(2026, 11, 8, 14, 44, tzinfo=timezone.utc))
    assert gone[0]["text"]["text"].startswith("~") and "Expired 9:44 AM" in gone[2]["elements"][0]["text"]
    assert [x["action_id"] for x in gone[-1]["elements"]] == ["reask", "drop"]


def test_answered_card_swaps_buttons_for_a_line():
    e = entry(action_class="email.send", to=["tim@x.com"], draft_text="Hi")
    done = approval_policy.answered_blocks(approval_policy.blocks(e), "Skipped.")
    assert not any(b["type"] == "actions" for b in done) and done[-1]["elements"][0]["text"] == "Skipped."


def test_who_line_for_strangers_counts_emails(tmp_path):
    root = known_world(tmp_path)
    assert approval_policy.who_line("ann@y.com", root) == "In your contacts"
    assert approval_policy.who_line("eve@evil.com", root, history=lambda a: None) == "1st email from them"
    assert approval_policy.who_line("eve@evil.com", root, history=lambda a: (3, False)) == "3rd email, no reply yet"
    assert approval_policy.who_line("eve@evil.com", root, history=lambda a: (11, True)) == "11th email, you've replied before"


def test_reask_makes_a_new_id_with_a_fresh_clock(tmp_path):
    store = Approvals(tmp_path / "p.json")
    old = store.add("Okay to hold Saturday?", "hold")
    assert store.reask(old["id"]) is None  # only expired cards can be asked again
    store.mark(old["id"], "expired", slack_ts="1.0")
    new = store.reask(old["id"])
    assert new["id"] != old["id"] and new["status"] == "new" and "slack_ts" not in new
    assert store.get(old["id"])["status"] == "reasked"


# --- bridge flow -----------------------------------------------------------------------------------

class Runner:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return claude_runner.RunResult(text="done", session_id="s", is_error=False)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "notify-allowlist.json").write_text(json.dumps({"slack": ["U_M"]}), encoding="utf-8")
    monkeypatch.setattr(slack_bridge, "heartbeat", lambda *a, **k: None)
    runner = Runner()
    b = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                            approvals=Approvals(tmp_path / "a.json"), runner=runner)
    return b, runner, tmp_path


def test_approved_send_grants_only_send_and_the_draft(bridge):
    b, runner, _ = bridge
    e = b.approvals.add("Reply to Tim", "send draft d1")
    data = json.loads(b.approvals.path.read_text(encoding="utf-8"))
    data["pending"][0].update(action_class="email.send", draft_id="d1", to=["tim@x.com"])
    b.approvals.path.write_text(json.dumps(data), encoding="utf-8")
    sent = []
    b.send_email = lambda draft_id, to, text: sent.append((draft_id, to, text)) or {"sent": True}
    reply = b.handle_approval(e["id"], "approved", user_id="U_M")
    # Since docs/v2 P0 the bridge sends the approved draft in code: no model run, no granted tool.
    assert sent == [("d1", "tim@x.com", "")] and runner.calls == [] and reply.startswith("Sent to tim@x.com")


def test_denied_grants_nothing(bridge):
    b, runner, _ = bridge
    e = b.approvals.add("Reply to Tim", "send draft d1")
    b.handle_approval(e["id"], "denied", user_id="U_M")
    assert runner.calls[-1][1]["allowed_tools"] == () and "Do not perform it" in runner.calls[-1][0]


def test_stranger_tap_ignored_and_audit_written(bridge):
    b, runner, tmp = bridge
    e = b.approvals.add("Reply", "x")
    assert b.handle_approval(e["id"], "approved", user_id="U_X") == "" and not runner.calls
    b.handle_approval(e["id"], "approved", user_id="U_M")
    events = [json.loads(line)["event"] for line in (tmp / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events == ["approved", "executed"]


def test_install_runs_in_python_and_grants_no_tools(bridge, monkeypatch):
    b, runner, _ = bridge
    seen = []
    monkeypatch.setattr(slack_bridge.installer, "install",
                        lambda root, name: seen.append(name) or slack_bridge.installer.Result(True, ["Installed kin"]))
    e = b.approvals.add("Add Kin", "install proposals/kin")
    data = json.loads(b.approvals.path.read_text(encoding="utf-8"))
    data["pending"][0].update(action_class="subagent.install", proposal="kin")
    b.approvals.path.write_text(json.dumps(data), encoding="utf-8")
    b.handle_approval(e["id"], "approved", user_id="U_M")
    prompt, kw = runner.calls[-1]
    assert seen == ["kin"] and kw["allowed_tools"] == () and "Installed kin" in prompt
    assert "COORDINATOR_ALLOW_CONFIG_EDITS" not in kw["env_extra"]


# --- trust labels (docs/04 proposal 2) -------------------------------------------------------------

def known_world(root: Path) -> Path:
    (root / "people").mkdir(exist_ok=True)
    (root / "people" / "tim-ray.md").write_text("# Tim Ray\n- relationship: friend (stated)\n- emails: tim@x.com\n",
                                                encoding="utf-8")
    (root / "data" / "contacts").mkdir(parents=True, exist_ok=True)
    (root / "data" / "contacts" / "contacts.json").write_text(json.dumps(
        {"contacts": [{"name": "Ann", "emails": [{"address": "ann@y.com", "type": ""}]}]}), encoding="utf-8")
    return root


def test_trust_labels_come_from_files_not_the_entry(tmp_path):
    root = known_world(tmp_path)
    assert approval_policy.trust_of(entry(to=["Tim <TIM@x.com>"]), root) == "known"
    assert approval_policy.trust_of(entry(to=["ann@y.com"]), root) == "contact"
    assert approval_policy.trust_of(entry(to=["tim@x.com", "eve@evil.com"], trust="known"), root) == "unknown"
    assert approval_policy.trust_of(entry(to=["owner@example.com"]), root) == "michael"
    assert approval_policy.trust_of(entry(action_class="calendar.hold"), root) is None


def test_stranger_card_has_no_always_and_says_so():
    e = entry(action_class="email.send", to=["eve@evil.com"], draft_id="d1", draft_link="https://mail.google.com/x")
    assert card_buttons(approval_policy.blocks(e, "unknown")) == (["Send", "Edit in Gmail"], ["Skip"])


def test_always_tap_for_stranger_sends_once_without_a_rule(bridge):
    b, runner, tmp = bridge
    e = b.approvals.add("Reply to Eve", "send draft d1")
    data = json.loads(b.approvals.path.read_text(encoding="utf-8"))
    data["pending"][0].update(action_class="email.send", draft_id="d1", to=["eve@evil.com"])
    b.approvals.path.write_text(json.dumps(data), encoding="utf-8")
    sent = []
    b.send_email = lambda draft_id, to, text: sent.append(draft_id) or {"sent": True}
    b.handle_approval(e["id"], "always", user_id="U_M")
    assert not (tmp / "state" / "always-allow.json").exists()
    assert sent == ["d1"] and runner.calls == []


# --- payload binding (docs/v2/05-SECURITY.md control 3, brief P0) ------------------------------------

def _send_card(b, **fields):
    e = b.approvals.add("Reply to Tim", "send draft d1")
    data = json.loads(b.approvals.path.read_text(encoding="utf-8"))
    data["pending"][0].update(action_class="email.send", draft_id="d1", to="tim@x.com", draft_text="See you at 7.",
                              **fields)
    b.approvals.path.write_text(json.dumps(data), encoding="utf-8")
    b.approvals.mark(e["id"], "posted", slack_ts="1.0")
    return e["id"]


def test_posting_a_card_stores_the_payload_hash(bridge):
    b, _, _ = bridge
    aid = _send_card(b)
    entry = b.approvals.get(aid)
    import state_store
    assert entry["payload_sha256"] == state_store.payload_hash(entry)


def test_entry_edited_after_the_card_is_refused(bridge):
    b, runner, tmp = bridge
    aid = _send_card(b)
    data = json.loads(b.approvals.path.read_text(encoding="utf-8"))
    data["pending"][0]["to"] = "someone-else@x.com"
    b.approvals.path.write_text(json.dumps(data), encoding="utf-8")
    b.send_email = lambda *a: pytest.fail("must not send")
    reply = b.handle_approval(aid, "approved", user_id="U_M")
    assert "changed after you saw it" in reply and b.approvals.get(aid)["status"] == "refused" and runner.calls == []


def test_replayed_tap_is_refused(bridge):
    b, _, _ = bridge
    aid = _send_card(b)
    sent = []
    b.send_email = lambda *a: sent.append(a) or {"sent": True}
    b.handle_approval(aid, "approved", user_id="U_M")
    assert "Already approved" in b.handle_approval(aid, "approved", user_id="U_M") and len(sent) == 1


def test_tap_from_another_user_is_ignored(bridge):
    b, _, _ = bridge
    aid = _send_card(b)
    b.send_email = lambda *a: pytest.fail("must not send")
    assert b.handle_approval(aid, "approved", user_id="U_OTHER") == ""


def test_draft_changed_in_gmail_gets_a_fresh_card_not_a_send(bridge):
    b, _, tmp = bridge
    aid = _send_card(b)
    b.send_email = lambda *a: {"sent": False, "why": "text changed", "current_text": "See you at 8."}
    assert "fresh card" in b.handle_approval(aid, "approved", user_id="U_M")
    fresh = b.approvals.new_entries()
    assert len(fresh) == 1 and fresh[0]["draft_text"] == "See you at 8." and fresh[0]["refreshed_from"] == aid
    kinds = [json.loads(l)["type"] for l in (tmp / "state" / "signals.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds == ["approval.approved", "draft.edited"]


def test_gmail_send_approved_checks_recipients_and_text():
    import base64
    import gmail
    from email.message import EmailMessage

    def raw(to, body):
        m = EmailMessage()
        m["To"] = to
        m["Subject"] = "Re: Saturday"
        m.set_content(body)
        return base64.urlsafe_b64encode(m.as_bytes()).decode()

    def run(to, body):
        posts = []

        def get(url, token, params=None):
            if url.endswith("/settings/sendAs"):
                return {"sendAs": [{"isDefault": True, "signature": "<div>Michael</div>"}]}
            return {"message": {"raw": raw(to, body)}}

        out = gmail.send_approved("d1", "tim@x.com", "See you at 7.\n", token="t", get=get,
                                  call=lambda *a: posts.append(a) or {"id": "m1"})
        return out, posts

    out, posts = run("tim@x.com", "See you at 7.\n\nMichael\n")
    assert out["sent"] and posts[0][1].endswith("/drafts/send")
    out, posts = run("tim@x.com", "See you at 9.\n")
    assert not out["sent"] and out["why"] == "text changed" and posts == []
    out, posts = run("tim@x.com, eve@evil.com", "See you at 7.\n")
    assert not out["sent"] and out["why"] == "recipients changed" and posts == []
