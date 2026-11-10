"""Prove every gate blocks. Run: python -m pytest tests/ -q"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def run_hook(script: str, tool_name: str, tool_input: dict, env_extra: dict | None = None) -> dict | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COORDINATOR_")}
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    env.update(env_extra or {})
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input, "cwd": str(ROOT)})
    proc = subprocess.run([sys.executable, str(HOOKS / script)], input=payload, text=True,
                          capture_output=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def decision(out: dict | None) -> str:
    return out["hookSpecificOutput"]["permissionDecision"] if out else "allow"


# --- gate_memory_writes -------------------------------------------------------------------------

# Juno's own runs (the bridge sets COORDINATOR_UNATTENDED to 0 or 1 on every one) may never edit config; a Code-tab
# session with Michael (no COORDINATOR_UNATTENDED at all) may, since 2026-11-08.
def test_claude_md_denied_in_junos_runs():
    for unattended in ("0", "1"):
        out = run_hook("gate_memory_writes.py", "Edit", {"file_path": str(ROOT / "CLAUDE.md")},
                       {"COORDINATOR_UNATTENDED": unattended})
        assert decision(out) == "deny"


def test_claude_md_allowed_in_code_tab_session():
    out = run_hook("gate_memory_writes.py", "Edit", {"file_path": str(ROOT / "CLAUDE.md")})
    assert decision(out) == "allow"


def test_claude_md_allowed_with_flag():
    out = run_hook("gate_memory_writes.py", "Edit", {"file_path": str(ROOT / "CLAUDE.md")},
                   {"COORDINATOR_ALLOW_CONFIG_EDITS": "1", "COORDINATOR_UNATTENDED": "0"})
    assert decision(out) == "allow"


def test_settings_denied_in_junos_runs():
    out = run_hook("gate_memory_writes.py", "Write", {"file_path": ".claude/settings.json"},
                   {"COORDINATOR_UNATTENDED": "0"})
    assert decision(out) == "deny"


def test_memory_allowed_interactive():
    out = run_hook("gate_memory_writes.py", "Edit", {"file_path": "learnings/coordinator.md"})
    assert decision(out) == "allow"


def test_memory_denied_unattended():
    for p in ("me/voice.md", "learnings/health.md", "people/coach.md", "domains/health/CONTEXT.md"):
        out = run_hook("gate_memory_writes.py", "Edit", {"file_path": p}, {"COORDINATOR_UNATTENDED": "1"})
        assert decision(out) == "deny", p


def test_domain_non_context_allowed_unattended():
    out = run_hook("gate_memory_writes.py", "Write", {"file_path": "domains/health/baselines.csv"},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "allow"


def test_proposed_lessons_always_allowed():
    out = run_hook("gate_memory_writes.py", "Write", {"file_path": "state/proposed-lessons.md"},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "allow"


def test_logs_allowed_unattended():
    out = run_hook("gate_memory_writes.py", "Write", {"file_path": "logs/2026-11-06_0700_morning-brief.md"},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "allow"


# --- notify_michael_only ------------------------------------------------------------------------

def test_notify_allowlisted_ok():
    import importlib.util
    spec = importlib.util.spec_from_file_location("notify_hook", ROOT / ".claude" / "hooks" / "notify_michael_only.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert hook.decide({"chat_id": "U1", "text": "hi"}, {"U1"}) is None  # CI has no personal files
    path = ROOT / "me" / "notify-allowlist.json"
    if not path.exists():
        return
    allow = json.loads(path.read_text(encoding="utf-8"))
    some = next((v[0] for v in allow.values() if v), None)
    if some is None:
        return  # allowlist not filled yet; other tests still prove the block
    out = run_hook("notify_michael_only.py", "mcp__telegram__send_message", {"chat_id": some, "text": "hi"})
    assert decision(out) == "allow"


def test_notify_other_recipient_denied():
    out = run_hook("notify_michael_only.py", "mcp__slack__slack_send_message", {"channel_id": "C0GENERAL", "text": "hi"})
    assert decision(out) == "deny"


def test_notify_email_recipient_denied():
    out = run_hook("notify_michael_only.py", "mcp__gmail__send_mail", {"to": ["coach@example.com"], "body": "x"})
    assert decision(out) == "deny"


def test_notify_no_recipient_field_allowed():
    out = run_hook("notify_michael_only.py", "mcp__telegram__reply", {"text": "reply to paired sender"})
    assert decision(out) == "allow"


# --- observed/ (silent learning) -----------------------------------------------------------------

def test_observed_writable_unattended():
    out = run_hook("gate_memory_writes.py", "Write",
                   {"file_path": str(ROOT / "observed" / "voice.md"), "content": "x" * 100},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "allow"


def test_observed_over_cap_denied():
    out = run_hook("gate_memory_writes.py", "Write",
                   {"file_path": str(ROOT / "observed" / "voice.md"), "content": "x" * 9000},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "deny"


def test_observed_does_not_open_me_dir():
    out = run_hook("gate_memory_writes.py", "Write",
                   {"file_path": str(ROOT / "me" / "voice.md"), "content": "x"},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "deny"


def test_observed_path_trick_denied():
    out = run_hook("gate_memory_writes.py", "Write",
                   {"file_path": str(ROOT / "observed" / ".." / "me" / "voice.md"), "content": "x"},
                   {"COORDINATOR_UNATTENDED": "1"})
    assert decision(out) == "deny"


# --- gate_web: only the researcher goes online in Juno's runs -------------------------------------

def run_web_hook(tool: str, agent_type: str | None, env_extra: dict | None) -> dict | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COORDINATOR_")}
    env.update(env_extra or {})
    data = {"tool_name": tool, "tool_input": {"query": "x"}, "cwd": str(ROOT)}
    if agent_type:
        data["agent_type"] = agent_type
    proc = subprocess.run([sys.executable, str(HOOKS / "gate_web.py")], input=json.dumps(data), text=True,
                          capture_output=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def test_web_denied_to_the_coordinator_in_junos_runs():
    for tool in ("WebSearch", "WebFetch"):
        assert decision(run_web_hook(tool, None, {"COORDINATOR_UNATTENDED": "0"})) == "deny"
        assert decision(run_web_hook(tool, "youtube", {"COORDINATOR_UNATTENDED": "1"})) == "deny"


def test_web_allowed_to_the_researcher():
    assert decision(run_web_hook("WebSearch", "researcher", {"COORDINATOR_UNATTENDED": "0"})) == "allow"


def test_web_allowed_in_code_tab():
    assert decision(run_web_hook("WebFetch", None, None)) == "allow"


def test_youtube_agent_has_no_open_shell():
    head = (ROOT / ".claude" / "agents" / "youtube.md").read_text(encoding="utf-8").split("---")[1]
    tools = next(l for l in head.splitlines() if l.startswith("tools:"))
    assert all(t.strip() == "Read" or "(python tools/youtube.py " in t for t in tools[6:].split(","))


def test_every_agent_tool_points_at_a_script_that_exists():
    import re
    for agent in (ROOT / ".claude" / "agents").glob("*.md"):
        head = agent.read_text(encoding="utf-8").split("---")[1]
        tools = next(l for l in head.splitlines() if l.startswith("tools:"))
        for script in re.findall(r"python (tools/[\w./-]+?)[ *)]", tools):
            assert (ROOT / script).exists() or list(ROOT.glob(script + "*")), f"{agent.name}: {script}"
