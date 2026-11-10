"""Offline tests for the Slack bridge: no network, no claude binary, no Slack SDK import."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

import claude_runner  # noqa: E402
import slack_bridge  # noqa: E402
from state_store import Approvals, SessionMap  # noqa: E402


# --- claude_runner ---------------------------------------------------------------------------------

def test_build_command_basic():
    cmd = claude_runner.build_command("claude", "hi", permission_mode="acceptEdits")
    assert cmd[:3] == ["claude", "-p", "hi"]
    assert "--output-format" in cmd and "json" in cmd
    assert "--resume" not in cmd


def test_build_command_resume_model_budget():
    cmd = claude_runner.build_command("claude", "hi", resume="sess-1", model="sonnet", max_budget_usd=0.5)
    assert cmd[cmd.index("--resume") + 1] == "sess-1"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.5"


def test_parse_output_json():
    out = json.dumps({"type": "result", "result": "Hello Michael", "session_id": "abc", "is_error": False,
                      "total_cost_usd": 0.0123, "duration_ms": 1200})
    r = claude_runner.parse_output("some warning line\n" + out)
    assert r.text == "Hello Michael" and r.session_id == "abc" and not r.is_error and r.cost_usd == 0.0123


def test_parse_output_plain_text_fallback():
    r = claude_runner.parse_output("not json at all")
    assert r.text == "not json at all" and r.session_id is None


def test_parse_output_empty_is_error():
    r = claude_runner.parse_output("")
    assert r.is_error


def test_run_dry_run_sets_unattended_env(tmp_path):
    r = claude_runner.run("x", cwd=tmp_path, unattended=True, dry_run=True)
    assert r.command[0] == "claude" and "[dry run]" in r.text and not r.is_error


def test_run_keeps_secrets_out_of_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    monkeypatch.setenv("SLACK_APP_TOKEN", "x")
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "x")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "x")
    monkeypatch.setenv("KEEP_ME", "1")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw["env"])
        return claude_runner.subprocess.CompletedProcess(cmd, 0, stdout='{"result": "ok"}', stderr="")

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    claude_runner.run("hi", cwd=tmp_path, claude_bin="claude")
    upper = {k.upper() for k in seen}
    assert "KEEP_ME" in upper and not {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "OP_SERVICE_ACCOUNT_TOKEN", "GOOGLE_REFRESH_TOKEN"} & upper


def fake_keyring(monkeypatch, stored):
    import types
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(
        get_password=lambda service, name: stored.get(name),
        set_password=lambda service, name, value: stored.update({name: value})))


def test_token_store_key_goes_only_to_op(monkeypatch):
    import token_store
    fake_keyring(monkeypatch, {token_store.OP_KEY: "ops_fake"})
    monkeypatch.setattr(token_store, "find_op", lambda: "op")
    monkeypatch.delenv(token_store.OP_KEY, raising=False)
    seen = []

    def fake_run(cmd, **kw):
        seen.append(kw["env"][token_store.OP_KEY])
        value = "xoxb-fake" if cmd[-1].endswith("bot_token") else "xapp-fake"
        return token_store.subprocess.CompletedProcess(cmd, 0, stdout=value, stderr="")

    monkeypatch.setattr(token_store.subprocess, "run", fake_run)
    assert token_store.fetch_tokens() == {"SLACK_BOT_TOKEN": "xoxb-fake", "SLACK_APP_TOKEN": "xapp-fake"}
    assert seen == ["ops_fake", "ops_fake"] and token_store.OP_KEY not in token_store.os.environ


def test_token_store_google_is_all_or_nothing(monkeypatch):
    import token_store
    fake_keyring(monkeypatch, {token_store.OP_KEY: "ops_fake"})
    monkeypatch.setattr(token_store, "find_op", lambda: "op")
    missing = {"op://Agent-Secrets/Google-Juno/refresh_token"}

    def fake_read(op, ref, key):
        if ref in missing:
            raise token_store.TokenError("not found")
        return "value"

    monkeypatch.setattr(token_store, "read_ref", fake_read)
    assert token_store.fetch_optional() == {}
    missing.clear()
    assert set(token_store.fetch_optional()) == set(token_store.OPTIONAL_REFS)


def test_token_store_starts_without_google(monkeypatch):
    import token_store
    for name in token_store.REFS:
        monkeypatch.setenv(name, "x")
    for name in token_store.OPTIONAL_REFS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(token_store, "fetch_optional", lambda: {})
    token_store.load_into_env()
    assert not any(token_store.os.environ.get(n) for n in token_store.OPTIONAL_REFS)


def test_token_store_without_key_fails_cleanly(monkeypatch):
    import token_store
    fake_keyring(monkeypatch, {})
    with pytest.raises(token_store.TokenError):
        token_store.fetch_tokens()


def test_token_store_rejects_wrong_token_shape(monkeypatch):
    import token_store
    stored = {}
    fake_keyring(monkeypatch, stored)
    monkeypatch.setattr(token_store.getpass, "getpass", lambda prompt: "not-a-token")
    assert token_store.store_op_token() == 2 and stored == {}


def test_token_retry_recovers_after_network_failure(monkeypatch):
    import token_store
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise token_store.TokenError("offline")

    monkeypatch.setattr(token_store, "load_into_env", flaky)
    assert slack_bridge.load_tokens_with_retry(attempts=5, wait_seconds=0) and len(calls) == 3


# --- state_store ------------------------------------------------------------------------------------

def test_session_map_roundtrip_and_idle_reset(tmp_path):
    sm = SessionMap(tmp_path / "s.json", idle_reset=timedelta(hours=1))
    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    assert sm.get("D1", now=now) is None
    sm.set("D1", "sess-1", now=now)
    assert sm.get("D1", now=now + timedelta(minutes=30)) == "sess-1"
    assert sm.get("D1", now=now + timedelta(hours=2)) is None
    sm.reset("D1")
    assert sm.get("D1", now=now) is None


def test_approvals_lifecycle(tmp_path):
    ap = Approvals(tmp_path / "a.json")
    e = ap.add("Send the CPA the Q4 summary", "email.send to cpa@example.com", session_id="sess-9")
    assert e["status"] == "new" and ap.new_entries()[0]["id"] == e["id"]
    ap.mark(e["id"], "posted", slack_ts="1.2")
    assert ap.new_entries() == [] and ap.get(e["id"])["slack_ts"] == "1.2"
    ap.mark(e["id"], "approved")
    assert ap.get(e["id"])["status"] == "approved"


# --- bridge behaviors -------------------------------------------------------------------------------

class FakeRunner:
    def __init__(self, text="ok", session_id="sess-new", is_error=False):
        self.calls = []
        self.text, self.session_id, self.is_error = text, session_id, is_error

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return claude_runner.RunResult(text=self.text, session_id=self.session_id, is_error=self.is_error)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "notify-allowlist.json").write_text(json.dumps({"slack": ["U_MICHAEL"]}), encoding="utf-8")
    (tmp_path / "me" / "proactivity.yaml").write_text(
        "timezone: America/New_York\nquiet_hours: {start: '22:00', end: '07:00'}\n"
        "anchors: {morning_brief: '07:00', evening_checkin: '20:30', sweep_every_minutes: 120, "
        "sweep_window: ['07:00','21:00'], weekly_reflection: 'Sun 18:00', coach_sheet_nightly: '21:17'}\n",
        encoding="utf-8")
    monkeypatch.delenv("SLACK_ALLOWED_USERS", raising=False)
    runner = FakeRunner()
    b = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                            approvals=Approvals(tmp_path / "a.json"), runner=runner)
    monkeypatch.setattr(slack_bridge, "heartbeat", lambda *a, **k: None)
    return b, runner


def test_dm_from_stranger_is_ignored(bridge):
    b, runner = bridge
    assert b.handle_dm("D1", "U_STRANGER", "hi") == ""
    assert runner.calls == []


def test_dm_runs_claude_and_keeps_session(bridge):
    b, runner = bridge
    assert b.handle_dm("D1", "U_MICHAEL", "what's today?") == "ok"
    prompt, kw = runner.calls[0]
    assert "[Slack DM from Michael]" in prompt and kw["resume"] is None and kw["unattended"] is False
    b.handle_dm("D1", "U_MICHAEL", "and tomorrow?")
    assert runner.calls[1][1]["resume"] == "sess-new"


def test_new_resets_session(bridge):
    b, runner = bridge
    b.handle_dm("D1", "U_MICHAEL", "hello")
    assert "Fresh session" in b.handle_dm("D1", "U_MICHAEL", "/new")
    b.handle_dm("D1", "U_MICHAEL", "again")
    assert runner.calls[-1][1]["resume"] is None


def test_job_runs_unattended(bridge):
    b, runner = bridge
    assert b.run_job("morning-brief") == "ok"
    assert runner.calls[0][1]["unattended"] is True


def test_sweep_silent_marker(bridge):
    b, runner = bridge
    runner.text = "NOTHING_TO_REPORT"
    assert b.run_job("sweep") is None


def test_job_error_reported(bridge):
    b, runner = bridge
    runner.is_error, runner.text = True, "boom"
    assert b.run_job("evening-checkin").startswith("evening-checkin failed")


def test_approval_tap_resumes_recorded_session(bridge):
    b, runner = bridge
    e = b.approvals.add("Create hold Tue 7pm", "calendar.hold", session_id="sess-7")
    text = b.handle_approval(e["id"], "approved", user_id="U_MICHAEL")
    assert text == "ok"
    prompt, kw = runner.calls[0]
    assert "approved by Michael" in prompt and kw["resume"] == "sess-7"
    assert b.approvals.get(e["id"])["status"] == "approved"
    assert "Already approved" in b.handle_approval(e["id"], "denied", user_id="U_MICHAEL")


def test_approval_from_stranger_ignored(bridge):
    b, runner = bridge
    e = b.approvals.add("x", "y")
    assert b.handle_approval(e["id"], "approved", user_id="U_STRANGER") == ""
    assert b.approvals.get(e["id"])["status"] == "new" and runner.calls == []


# --- schedule and helpers ---------------------------------------------------------------------------

def test_anchor_schedule(bridge):
    b, _ = bridge
    jobs = {j["job"]: j["trigger"] for j in slack_bridge.anchor_schedule(slack_bridge.load_proactivity(b.root))}
    assert jobs["morning-brief"] == {"hour": 7, "minute": 0, "timezone": "America/New_York"}
    assert jobs["evening-checkin"]["hour"] == 20 and jobs["evening-checkin"]["minute"] == 30
    assert jobs["sweep"]["hour"] == "7,9,11,13,15,17,19,21" and jobs["sweep"]["minute"] == "0"
    assert jobs["weekly-reflection"]["day_of_week"] == "sun" and jobs["weekly-reflection"]["hour"] == 18
    assert jobs["coach-sheet"] == {"hour": 21, "minute": 17, "timezone": "America/New_York"}


class _Proc:
    def __init__(self, out, code=0):
        self.stdout, self.stderr, self.returncode = json.dumps(out), "", code


def _runner(pulled, planned):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[1])
        return _Proc(pulled) if cmd[1].endswith("hevy_pull.py") else _Proc(planned)
    return run, calls


def test_coach_sheet_waits_for_a_new_hevy_workout(tmp_path):
    (tmp_path / "state").mkdir()
    run, calls = _runner({"added": 0, "updated": 0, "deleted": 0}, {"new_sessions": []})
    assert not slack_bridge.coach_sheet_due(tmp_path, run=run)
    assert calls == ["tools/hevy_pull.py"]  # nothing new in Hevy: the sheet isn't even read

    run, calls = _runner({"added": 1, "updated": 0}, {"new_sessions": ["W2D1"]})
    assert slack_bridge.coach_sheet_due(tmp_path, run=run)
    assert json.loads((tmp_path / "state" / "coach-sheet.json").read_text())["pending"]

    run, calls = _runner({"added": 0, "updated": 0}, {"new_sessions": ["W2D1"]})
    assert slack_bridge.coach_sheet_due(tmp_path, run=run)  # still waiting from before: checked again
    assert calls[-1] == "tools/sheets.py"


def test_coach_sheet_nightly_checks_anyway_and_fails_closed(tmp_path):
    (tmp_path / "state").mkdir()
    run, calls = _runner({"added": 0, "updated": 0}, {"new_sessions": []})
    assert not slack_bridge.coach_sheet_due(tmp_path, force=True, run=run)
    assert calls == ["tools/hevy_pull.py", "tools/sheets.py"]
    broken = lambda cmd, **kw: _Proc({}, code=4)  # noqa: E731
    assert not slack_bridge.coach_sheet_due(tmp_path, force=True, run=broken)


def test_coach_sheet_job_is_lean_and_retries_on_failure(bridge, monkeypatch):
    b, _ = bridge
    monkeypatch.setattr(slack_bridge, "coach_sheet_due", lambda root, force=False: True)
    flag = b.root / "state" / "coach-sheet.json"
    flag.parent.mkdir(exist_ok=True)
    flag.write_text(json.dumps({"pending": True}), encoding="utf-8")
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[1:3])
        return type("P", (), {"returncode": 0, "stderr": "", "stdout": json.dumps({"ok": False, "message": "later"})})
    assert b._coach_sheet(False, run=run) == "later"
    assert calls == [["tools/coach_sheet.py", "sync"]]  # no coordinator run at all
    assert json.loads(flag.read_text())["pending"]  # not ok: the next check tries again

    ok = lambda cmd, **kw: type("P", (), {"returncode": 0, "stderr": "",  # noqa: E731
                                          "stdout": json.dumps({"ok": True, "message": "W2D1 logged"})})
    assert b._coach_sheet(False, run=ok) == "W2D1 logged"
    assert not json.loads(flag.read_text())["pending"]


def test_quiet_hours():
    cfg = {"timezone": "America/New_York", "quiet_hours": {"start": "22:00", "end": "07:00"}}
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/New_York")
    assert slack_bridge.in_quiet_hours(cfg, datetime(2026, 11, 6, 23, 30, tzinfo=tz))
    assert slack_bridge.in_quiet_hours(cfg, datetime(2026, 11, 6, 6, 59, tzinfo=tz))
    assert not slack_bridge.in_quiet_hours(cfg, datetime(2026, 11, 6, 12, 0, tzinfo=tz))


def test_chunk_splits_on_newlines():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    parts = slack_bridge.chunk(text, limit=1000)
    assert all(len(p) <= 1000 for p in parts) and "".join(p.replace("\n", "") for p in parts).count("line") == 200


def test_approval_blocks_shape():
    blocks = slack_bridge.approval_blocks({"id": "a-1", "summary": "S", "action": "A"})
    els = next(b for b in blocks if b["type"] == "actions")["elements"]
    assert [el["action_id"] for el in els] == ["approve", "deny"] and els[0]["value"] == "a-1"


def test_sweep_verdict_posts_items(bridge):
    b, runner = bridge
    runner.text = 'done {"notify": true, "items": [{"id": "e1", "kind": "leave_by", "text": "Leave at 6:10 for dinner"}]}'
    assert b.run_job("sweep") in (None, "• Leave at 6:10 for dinner")  # None only inside quiet hours
    assert runner.calls[-1][1]["model"] == "claude-haiku-5-5" and runner.calls[-1][1]["unattended"] is True


def test_sweep_verdict_false_is_silent(bridge):
    b, runner = bridge
    runner.text = '{"notify": false, "items": [], "hold": []}'
    assert b.run_job("sweep") is None


def test_brief_uses_pinned_model(bridge):
    b, runner = bridge
    b.run_job("morning-brief")
    assert runner.calls[-1][1]["model"] == "claude-sonnet-5-5"


def test_cost_log_appends_one_line_per_run(tmp_path, monkeypatch):
    import claude_runner as cr

    class Proc:
        returncode = 0
        stdout = '{"type":"result","result":"hi","session_id":"s1","is_error":false,"total_cost_usd":0.012,"duration_ms":900,"modelUsage":{"claude-haiku-5-5":{}}}'
        stderr = ""

    monkeypatch.setattr(cr.subprocess, "run", lambda *a, **k: Proc())
    cr.run("x", cwd=tmp_path, job="sweep", claude_bin="claude")
    cr.run("y", cwd=tmp_path, job="dm", model="sonnet", claude_bin="claude")
    lines = [json.loads(l) for l in (tmp_path / "state" / "costs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["job"] for l in lines] == ["sweep", "dm"]
    assert lines[0]["model"] == "claude-haiku-5-5" and lines[0]["cost_usd"] == 0.012 and lines[1]["model"] == "sonnet"


def test_cost_log_records_each_runs_own_cost_and_tokens(tmp_path, monkeypatch):
    """A resumed session reports its running total; the log keeps the difference (docs/v2/AUDIT.md section 2)."""
    import claude_runner as cr
    totals = iter([0.30, 0.42, 0.05])
    sessions = iter(["s1", "s1", "s2"])

    class Proc:
        returncode = 0
        stderr = ""

        @property
        def stdout(self):
            return json.dumps({"result": "ok", "session_id": next(sessions), "total_cost_usd": next(totals),
                               "usage": {"input_tokens": 3, "cache_read_input_tokens": 40000,
                                         "cache_creation_input_tokens": 900, "output_tokens": 120}})

    monkeypatch.setattr(cr.subprocess, "run", lambda *a, **k: Proc())
    for _ in range(3):
        cr.run("x", cwd=tmp_path, job="dm", claude_bin="claude")
    lines = [json.loads(l) for l in (tmp_path / "state" / "costs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["cost_usd"] for l in lines] == [0.30, 0.12, 0.05]
    assert [l["session_total_usd"] for l in lines] == [0.30, 0.42, 0.05]
    assert lines[0]["tokens"] == {"in": 3, "cache_write": 900, "cache_read": 40000, "out": 120}


def test_dry_run_logs_no_cost(tmp_path):
    import claude_runner as cr
    cr.run("x", cwd=tmp_path, dry_run=True, job="dm")
    assert not (tmp_path / "state" / "costs.jsonl").exists()


def test_status_answers_without_running_claude(tmp_path, monkeypatch):
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "notify-allowlist.json").write_text(json.dumps({"slack": ["U_M"]}), encoding="utf-8")
    (tmp_path / "state").mkdir()
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    (tmp_path / "state" / "last-run.json").write_text(json.dumps({
        "sweep": {"at": "2026-11-08T10:00:00+00:00", "ok": True},
        "morning-brief": {"at": "2026-11-08T11:30:00+00:00", "ok": False},
        "_last": {"job": "sweep", "at": "2026-11-08T10:00:00+00:00"}}), encoding="utf-8")
    calls = []
    b = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                            approvals=Approvals(tmp_path / "a.json"), runner=lambda *a, **k: calls.append(1))
    b.approvals.add("Reply to Tim", "send draft")
    out = b.status_text(now=now)
    assert "✅ sweep: 2 h ago" in out and "⚠️ morning-brief: 30 min ago" in out
    assert "Waiting on you: 1 card(s), oldest: Reply to Tim" in out
    assert b.handle_dm("D1", "U_M", "status").startswith("*Status*") and not calls


# --- thin briefs and per-job caps (docs/04 proposal 6) ---------------------------------------------

def test_build_command_max_turns():
    cmd = claude_runner.build_command("claude", "hi", max_turns=12)
    assert cmd[cmd.index("--max-turns") + 1] == "12"
    assert "--max-turns" not in claude_runner.build_command("claude", "hi")


def test_cap_hit_is_an_error_with_a_plain_reason():
    r = claude_runner.parse_output(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": False,
                                               "session_id": "s", "num_turns": 31}))
    assert r.is_error and r.text == "Stopped early: hit the turns cap for this job."


def test_timer_jobs_get_caps_and_thin_briefs(bridge):
    b, runner = bridge
    for job in slack_bridge.JOB_PROMPTS:
        prompt = slack_bridge.JOB_PROMPTS[job]
        assert prompt.startswith("Timer job.\nTask: run the ") and "\nGuardrails: " in prompt and "\nDone: " in prompt
    b.run_job("morning-brief")
    kw = runner.calls[-1][1]
    assert (kw["max_turns"], kw["max_budget_usd"]) == slack_bridge.ping_policy.JOB_LIMITS["morning-brief"]
    b.handle_dm("D1", "U_MICHAEL", "hi")
    kw = runner.calls[-1][1]  # Michael is there: no turn cap, but one message has a dollar cap
    assert kw["max_turns"] is None and kw["max_budget_usd"] == slack_bridge.ping_policy.JOB_LIMITS["dm"][1]


def test_dm_over_its_cap_says_so_and_starts_fresh(bridge):
    b, runner = bridge
    b.sessions.set("D1", "sess-long")

    def capped(prompt, **kw):
        runner.calls.append((prompt, kw))
        return claude_runner.RunResult(text="Stopped early", session_id="sess-long", is_error=True,
                                       raw={"subtype": "error_max_budget_usd"})
    b.runner = capped
    reply = b.handle_dm("D1", "U_MICHAEL", "research everything")
    assert "per-message cap" in reply and "fresh session" in reply
    assert b.sessions.get("D1") is None


def test_runs_never_overlap(bridge):
    import threading
    import time as _time
    b, runner = bridge
    live, most = [0], [0]

    def slow(prompt, **kw):
        live[0] += 1
        most[0] = max(most[0], live[0])
        _time.sleep(0.05)
        live[0] -= 1
        return claude_runner.RunResult(text="ok", session_id="s", is_error=False)
    b.runner = slow
    threads = [threading.Thread(target=b.handle_dm, args=("D1", "U_MICHAEL", "hi")),
               threading.Thread(target=b.run_job, args=("evening-checkin",)),
               threading.Thread(target=b.handle_dm, args=("D2", "U_MICHAEL", "yo"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert most[0] == 1


def test_ping_answered_inside_the_hour_is_a_signal(tmp_path):
    slack_bridge.ping_posted(tmp_path, "evening-checkin", "9.0")
    slack_bridge.ping_answered(tmp_path)
    slack_bridge.ping_answered(tmp_path)  # once per ping
    rows = [json.loads(l) for l in (tmp_path / "state" / "signals.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["ping.posted", "ping.answered"]
    assert rows[1]["job"] == "evening-checkin" and rows[1]["seconds"] >= 0


def test_ping_answered_late_is_not_a_signal(tmp_path):
    slack_bridge.ping_posted(tmp_path, "sweep", "9.0")
    slack_bridge.ping_answered(tmp_path, now=datetime.now(timezone.utc) + timedelta(hours=2))
    rows = (tmp_path / "state" / "signals.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1


# --- session handoff (docs/04 proposal 7) ----------------------------------------------------------

def test_quiet_session_writes_handoff_and_next_session_starts_from_it(bridge, tmp_path):
    b, runner = bridge
    old = datetime.now(timezone.utc) - timedelta(hours=13)
    b.sessions.set("D1", "sess-old", now=old)
    runner.text = "Open threads: Acme reply\nPromised Michael: none\nDecided: Rewind on haiku"
    b.handle_dm("D1", "U_MICHAEL", "morning")
    (hp, hkw), (dp, dkw) = runner.calls
    assert hp == slack_bridge.HANDOFF_PROMPT and hkw["resume"] == "sess-old" and hkw["allowed_tools"] == ()
    assert hkw["model"] == "claude-haiku-5-5" and hkw["job"] == "handoff"
    assert dkw["resume"] is None and dp.startswith("[Where the last session left off]\nOpen threads: Acme")
    assert "Decided: Rewind on haiku" in (tmp_path / "state" / "handoff.md").read_text(encoding="utf-8")
    b.handle_dm("D1", "U_MICHAEL", "again")  # the new session is fresh: no second handoff
    assert len(runner.calls) == 3 and runner.calls[-1][1]["resume"] == "sess-new"


def test_no_handoff_for_live_or_unknown_sessions(bridge):
    b, runner = bridge
    b.handle_dm("D1", "U_MICHAEL", "first")
    b.handle_dm("D1", "U_MICHAEL", "second")
    assert all(c[1].get("job") == "dm" for c in runner.calls)


def test_failed_handoff_still_answers(bridge, tmp_path):
    b, runner = bridge
    b.sessions.set("D1", "sess-old", now=datetime.now(timezone.utc) - timedelta(hours=13))
    runner.is_error = True
    b.handle_dm("D1", "U_MICHAEL", "hi")
    assert not runner.calls[-1][0].startswith("[Where") and not (tmp_path / "state" / "handoff.md").exists()
    assert b.sessions.stale("D1") is None


# --- debounced Slack bursts (docs/04 proposal 8) ---------------------------------------------------

def test_burst_of_dms_becomes_one_batch():
    import threading
    import time
    got, done = [], threading.Event()
    d = slack_bridge.Debouncer(lambda ch, items: (got.append((ch, [i["text"] for i in items])), done.set()), wait=0.05)
    for text in ("one", "two", "three"):
        d.submit("D1", {"ts": text, "user": "U", "text": text})
    assert done.wait(2)
    time.sleep(0.1)
    assert got == [("D1", ["one", "two", "three"])]


def test_message_during_a_run_waits_for_the_next_batch():
    import threading
    import time
    got, release = [], threading.Event()

    def slow(ch, items):
        got.append([i["text"] for i in items])
        if len(got) == 1:
            release.wait(2)

    d = slack_bridge.Debouncer(slow, wait=0.03)
    d.submit("D1", {"ts": "1", "user": "U", "text": "first"})
    time.sleep(0.1)  # first batch is running
    d.submit("D1", {"ts": "2", "user": "U", "text": "second"})
    d.submit("D1", {"ts": "3", "user": "U", "text": "third"})
    time.sleep(0.1)
    assert got == [["first"]]  # not run alongside the first
    release.set()
    time.sleep(0.2)
    assert got == [["first"], ["second", "third"]]


class FakeSlack:
    def __init__(self):
        self.posts, self.deleted, self.reactions = [], [], []

    def chat_postMessage(self, channel, text):
        self.posts.append(text)
        return {"ts": f"w{len(self.posts)}"}

    def chat_delete(self, channel, ts):
        self.deleted.append(ts)

    def reactions_add(self, channel, timestamp, name):
        self.reactions.append(("+", timestamp, name))

    def reactions_remove(self, channel, timestamp, name):
        self.reactions.append(("-", timestamp, name))


def test_answer_batch_one_run_one_reply(bridge):
    b, runner = bridge
    runner.text = "[react:smile] Got both."
    slack = FakeSlack()
    items = [{"ts": "1.0", "user": "U_MICHAEL", "text": "book dinner"}, {"ts": "2.0", "user": "U_MICHAEL", "text": "for 4"}]
    slack_bridge.answer_batch(slack, b, "D1", items)
    assert len(runner.calls) == 1 and "book dinner\n\nfor 4" in runner.calls[0][0]
    assert slack.posts[0].strip("_") in slack_bridge.WORKING_LINES and slack.posts[1:] == ["Got both."]
    assert slack.deleted == ["w1"]
    assert ("-", "1.0", "eyes") in slack.reactions and ("-", "2.0", "eyes") in slack.reactions
    assert slack.reactions[-1] == ("+", "2.0", "smile")


def test_eyes_then_working_line_at_once_one_per_burst(bridge):
    b, runner = bridge
    runner.text = "Done."
    slack, order = FakeSlack(), []
    slack.reactions_add = lambda channel, timestamp, name: order.append(("eyes", timestamp))
    post = slack.chat_postMessage
    slack.chat_postMessage = lambda channel, text: (order.append(("post", text)), post(channel, text))[1]
    slack_bridge.acknowledge(slack, "D9", "1.0", 0.4)
    slack_bridge.acknowledge(slack, "D9", "2.0", 0.3)  # same burst: no second working line
    assert order[0] == ("eyes", "1.0") and order[1][0] == "post" and order[2] == ("eyes", "2.0") and len(order) == 3
    slack_bridge.answer_batch(slack, b, "D9", [{"ts": "1.0", "user": "U_MICHAEL", "text": "hi"},
                                               {"ts": "2.0", "user": "U_MICHAEL", "text": "there"}])
    assert slack.deleted == ["w1"] and slack.posts[1:] == ["Done."]  # the early working line, reused, then gone
    assert "D9" not in slack_bridge._working_for


def test_seen_reaction_is_the_eyes():
    assert slack_bridge.seen_reaction("9.0") == "eyes" and slack_bridge._seen_on.pop("9.0") == "eyes"
    assert slack_bridge.done_reaction() in slack_bridge.DONE_REACTIONS


def test_working_lines_vary_and_never_name_juno():
    seen = [slack_bridge.working_text() for _ in range(60)]
    n = slack_bridge.RECENT
    assert all(seen[i] not in seen[max(0, i - n):i] for i in range(len(seen)))
    assert not any("juno" in line.lower() for line in slack_bridge.WORKING_LINES)


# --- brakes: pause, resume, spend notices (docs/v2 brief P0; no cap, Michael 2026-11-10) --------------------------------------

def test_pause_stops_dms_jobs_and_approvals_without_a_model(bridge):
    b, runner = bridge
    assert "Paused" in b.handle_dm("D1", "U_MICHAEL", "pause")
    assert (b.root / "state" / "PAUSED").exists()
    assert "paused" in b.handle_dm("D1", "U_MICHAEL", "what's on today?").lower()
    assert b.run_job("morning-brief") is None
    assert "Paused" in b.handle_approval("a-00000001", "approved", user_id="U_MICHAEL")
    assert runner.calls == []
    assert "Back on" in b.handle_dm("D1", "U_MICHAEL", "resume")
    b.handle_dm("D1", "U_MICHAEL", "what's on today?")
    assert len(runner.calls) == 1


def test_flag_file_alone_pauses(bridge):
    b, runner = bridge
    (b.root / "state").mkdir(exist_ok=True)
    (b.root / "state" / "PAUSED").write_text("by hand", encoding="utf-8")
    b.handle_dm("D1", "U_MICHAEL", "hi")
    assert runner.calls == []


def test_spend_never_pauses_and_notices_once_at_5_and_10(bridge):
    import brakes
    b, runner = bridge
    NL = chr(10)
    state = b.root / "state"
    state.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tok = {"in": 1000, "cache_write": 0, "cache_read": 500_000, "out": 2000}
    rows = [{"at": now, "job": "dm", "cost_usd": 40.0},  # an old running-total row: ignored
            {"at": now, "job": "dm", "cost_usd": 3.0, "session_total_usd": 3.0, "tokens": tok},
            {"at": now, "job": "dm", "cost_usd": 2.5, "session_total_usd": 5.5, "tokens": tok}]
    (state / "costs.jsonl").write_text(NL.join(json.dumps(r) for r in rows), encoding="utf-8")
    assert brakes.today_totals(b.root) == (5.5, 1_006_000) and brakes.blocked(b.root) is None
    first = b.handle_dm("D1", "U_MICHAEL", "hi")
    assert len(runner.calls) == 1 and "$5.50 (1.0M tokens)" in first and "Nothing's paused" in first
    assert "Heads up" not in b.handle_dm("D1", "U_MICHAEL", "hi again")  # once per amount
    with (state / "costs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(NL + json.dumps({"at": now, "job": "sweep", "cost_usd": 5.0, "session_total_usd": 5.0}))
    assert "$10.50" in (b.run_job("evening-checkin") or "")
    assert len(runner.calls) == 3


def test_dm_runs_on_pinned_sonnet_at_low_effort(bridge):
    b, runner = bridge
    b.handle_dm("D1", "U_MICHAEL", "hi")
    kw = runner.calls[-1][1]
    assert kw["model"] == "claude-sonnet-5-5" and kw["effort"] == "low"
    cmd = claude_runner.build_command("claude", "hi", model=kw["model"], effort=kw["effort"])
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert all(m.startswith("claude-") for m in slack_bridge.ping_policy.JOB_MODELS.values())


def test_external_heartbeat_pings_only_a_configured_https_url():
    seen = []

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout):
        seen.append((url, timeout))
        return Resp()

    assert slack_bridge.external_heartbeat("", opener=opener) is False
    assert slack_bridge.external_heartbeat("http://plain.example/x", opener=opener) is False
    assert slack_bridge.external_heartbeat("https://hc-ping.example/abc", opener=opener) is True
    assert seen == [("https://hc-ping.example/abc", 10)]

    def broken(url, timeout):
        raise OSError("offline")

    assert slack_bridge.external_heartbeat("https://hc-ping.example/abc", opener=broken) is False


def test_nightly_backup_only_when_set_up_and_quiet_on_success(bridge):
    import types
    b, _ = bridge
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout='{"file": "x"}', stderr="")
    assert slack_bridge.nightly_backup(None, b, run=fake) is False and calls == []
    (b.root / "me" / "backup.yaml").write_text("to: D:/offsite\n", encoding="utf-8")
    assert slack_bridge.nightly_backup(None, b, run=fake) is True
    assert calls[0][1:] == ["tools/backup.py", "run"]


def test_runs_carry_only_junos_built_in_tools(tmp_path, monkeypatch):
    monkeypatch.delenv("JUNO_TOOLS", raising=False)
    cmd = claude_runner.run("x", cwd=tmp_path, dry_run=True).command
    tools = cmd[cmd.index("--tools") + 1].split(",")
    assert {"Read", "Agent", "Skill", "ToolSearch", "WebSearch"} <= set(tools) and "NotebookEdit" not in tools
    lean = claude_runner.run("x", cwd=tmp_path, dry_run=True, lean_system="Words only.").command
    assert lean[lean.index("--tools") + 1] == ""  # a words-only call still has no tools at all
    monkeypatch.setenv("JUNO_TOOLS", "all")
    assert "--tools" not in claude_runner.run("x", cwd=tmp_path, dry_run=True).command
