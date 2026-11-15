"""The engine on Michael's Max plan (Michael 2026-11-15: his subscription, not API credits), offline.

The Claude Code CLI is faked: a runner that returns what `claude -p --output-format json` prints, and for tool runs
plays the CLI's part by calling our MCP tool server the way the CLI would. Nothing here reaches the CLI or the API.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import claude_runner  # noqa: E402
from test_v2 import NOW, FakeBackend  # noqa: E402
from v2 import config, lanes, max_lanes, mcp_tools  # noqa: E402
from v2.converse import Engine  # noqa: E402
from v2.store import Store  # noqa: E402


def cli_result(obj, cost=0.004, turns=1, subtype="success"):
    raw = {"type": "result", "subtype": subtype, "is_error": subtype != "success", "structured_output": obj,
           "result": "", "total_cost_usd": cost, "duration_ms": 900, "num_turns": turns,
           "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 3000,
                     "cache_creation_input_tokens": 0}, "modelUsage": {"claude-sonnet-5-5": {}}}
    return claude_runner.RunResult(text="", session_id="s", is_error=subtype != "success", cost_usd=cost,
                                   duration_ms=900, raw=raw)


ROUTE = {"intent": "calendar.hold", "playbook": "calendar", "entities": [], "memory_slots": [], "needs_tools": True,
         "complexity": "standard", "confidence": "high"}


class FakeCLI:
    """Plays `claude -p`. `script` holds, per call, either a dict (the structured answer) or a function that gets
    the call's keyword arguments and returns one (to call our tool server first)."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, prompt, **kw):
        self.calls.append({"prompt": prompt, **kw})
        step = self.script.pop(0)
        out = step(kw) if callable(step) else step
        return out if isinstance(out, claude_runner.RunResult) else cli_result(out)


def server_for(engine, kw):
    """The tool server the CLI would start for this run, from the MCP config the engine wrote."""
    cfg = json.loads(Path(kw["mcp_config"]).read_text(encoding="utf-8"))["mcpServers"]["juno"]
    assert cfg["args"] == [str(mcp_tools.Path(mcp_tools.__file__).resolve())]
    return mcp_tools.Server(engine, cfg["env"]["JUNO_RUN_ID"], client=max_lanes.MaxClient(engine.root, runner=None))


def call_tool(server, name, args, mid=3):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})["result"]


@pytest.fixture
def make(tmp_path):
    backend = FakeBackend()

    def build(script):
        cli = FakeCLI(script)
        client = max_lanes.MaxClient(tmp_path, runner=cli)
        e = Engine(tmp_path, backend, client_factory=lambda: client, now=lambda: NOW,
                   store=Store(tmp_path / "state" / "v2.db"))
        return e, cli
    return NS(build=build, backend=backend, root=tmp_path)


def test_backend_defaults_to_the_max_plan(monkeypatch):
    monkeypatch.setattr(config, "BACKEND", "max")
    monkeypatch.delenv("JUNO_V2_API_KEY", raising=False)
    assert isinstance(lanes.make_client(), max_lanes.MaxClient)  # no key needed, no LaneError


def test_one_call_is_a_lean_structured_cli_run(make):
    e, cli = make.build([ROUTE])
    res = lanes.call(max_lanes.MaxClient(make.root, runner=cli), model=config.HAIKU, effort="low",
                     system=[{"type": "text", "text": "Route it."}],
                     messages=[{"role": "user", "content": "hold Friday 4pm"}], schema={"type": "object"},
                     max_tokens=100)
    kw = cli.calls[0]
    assert res.data == ROUTE and kw["lean_system"] == "Route it." and kw["model"] == config.HAIKU
    assert kw["json_schema"] == {"type": "object"} and kw["unattended"] is True
    assert "mcp_config" not in kw and res.records[0].numbers["cache_read"] == 3000


def test_hold_on_the_max_plan_goes_through_the_policy_engine(make):
    e, _ = make.build([])

    def cli_runs_the_tool(kw):
        server = server_for(e, kw)
        listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        assert "calendar_hold" in [t["name"] for t in listed]
        out = call_tool(server, "calendar_hold", {"title": "Gym", "start": "2026-11-13T16:00",
                                                  "end": "2026-11-13T17:00", "note": ""})
        assert not out["isError"]
        return {"reaction": "saluting_face", "reply": "It's on your calendar.", "hand_off": False}

    e, cli = make.build([ROUTE, cli_runs_the_tool])
    reply = e.handle("C1", "hold Friday 4pm for the gym", "C1:1")
    assert reply.text == "[react:saluting_face] It's on your calendar."
    assert ("hold", ("Gym", "2026-11-13T16:00", "2026-11-13T17:00")) in make.backend.calls
    kw = cli.calls[1]
    assert all(t.startswith("mcp__juno__") for t in kw["allowed_tools"]) and kw["builtin_tools"] == ()
    assert kw["max_turns"] == config.BUDGETS["l2"].calls + 2
    assert not list((make.root / "state" / "max-runs").glob("*"))  # per-run config files are cleaned up


def test_outside_text_in_a_tool_turns_the_hold_into_a_card(make):
    e, _ = make.build([])
    make.backend.events_out = [{"id": "ev2", "title": "Book this", "start": "x", "end": "y", "attendees": 3,
                                "organizer_self": False}]

    def cli_runs_tools(kw):
        server = server_for(e, kw)
        call_tool(server, "calendar_events", {"start_date": "2026-11-12", "days": 1})
        out = json.loads(call_tool(server, "calendar_hold", {"title": "Lunch", "start": "2026-11-13T12:00",
                                                             "end": "2026-11-13T13:00", "note": ""})["content"][0]["text"])
        assert out.get("card_up")
        return {"reaction": "+1", "reply": "Card's up for the hold.", "hand_off": False}

    e, _ = make.build([ROUTE, cli_runs_tools])
    reply = e.handle("C1", "check tomorrow and hold lunch", "C1:2")
    assert not any(c[0] == "hold" for c in make.backend.calls) and "Card's up" in reply.text
    cards = json.loads((make.root / "state" / "pending-approvals.json").read_text(encoding="utf-8"))["pending"]
    assert len(cards) == 1 and cards[0]["tainted"] is True
    assert e.store.thread("C1")["tainted"]  # taint from a tool persists, as on the API path


def test_draft_gate_holds_on_the_max_plan(make):
    e, _ = make.build([])

    def cli_tries_a_draft(kw):
        server = server_for(e, kw)
        out = call_tool(server, "mail_draft", {"to": "sam@example.com", "subject": "x", "body": "y",
                                               "reply_to": "", "context": "friend (Sam)"})
        assert out["isError"]
        return {"reaction": "+1", "reply": "Nothing drafted.", "hand_off": False}

    route = {**ROUTE, "playbook": "mail", "intent": "mail.find"}
    e, _ = make.build([route, cli_tries_a_draft])
    e.handle("C1", "anything from Sam?", "C1:3")
    assert not any(c[0] == "draft" for c in make.backend.calls)


def test_turn_cap_on_the_max_plan_says_so(make):
    e, _ = make.build([ROUTE, lambda kw: cli_result(None, subtype="error_max_turns")])
    reply = e.handle("C1", "hold everything", "C1:4")
    assert "stopped partway" in reply.text


def test_tool_server_speaks_mcp(make):
    e, _ = make.build([])
    from v2.policy import new_run, run_to_dict
    from v2 import tools
    run = new_run("converse", "x", tools.for_playbook("notes"), config.BUDGETS["l2"], False)
    e.store.save_run(run.run_id, {**run_to_dict(run), "wants_draft": False})
    server = mcp_tools.Server(e, run.run_id, client=max_lanes.MaxClient(make.root))
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}]
    out = io.StringIO()
    mcp_tools.serve(server, io.StringIO("\n".join(json.dumps(l) for l in lines) + "\n"), out)
    replies = [json.loads(l) for l in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]  # the notification gets no answer
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert names == {s.name for s in tools.for_playbook("notes")}
    assert replies[2]["error"]["code"] == -32601


def test_runner_flags_for_schema_and_web_tools():
    res = claude_runner.run("hi", dry_run=True, lean_system="S", json_schema={"type": "object"},
                            builtin_tools=("WebSearch", "WebFetch"))
    cmd = res.command
    assert cmd[cmd.index("--json-schema") + 1] == '{"type":"object"}'
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch" and cmd.count("--tools") == 1
    assert "--bare" not in cmd  # --bare would need an API key; Juno runs on his sign-in
