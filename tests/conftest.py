"""Shared test guard: no test ever reaches the real Gmail sender."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ["JUNO_OWNER_EMAILS"] = "owner@example.com"  # tools/owner.py; the real address stays in me/
for sub in ("gateway", "tools"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))


@pytest.fixture(autouse=True)
def _no_real_gmail_send(monkeypatch):
    import slack_bridge

    def refuse(*a, **k):
        raise RuntimeError("tests never reach Gmail")

    monkeypatch.setattr(slack_bridge, "_gmail_send_approved", refuse)


@pytest.fixture(autouse=True)
def _no_real_state(monkeypatch, tmp_path):
    """Heartbeats and other default-path state writes land in a scratch folder, never the instance's state/."""
    import state_store

    scratch = tmp_path / "_state"
    scratch.mkdir(exist_ok=True)
    monkeypatch.setattr(state_store, "STATE", scratch)


@pytest.fixture(autouse=True)
def _no_real_model_key(monkeypatch):
    """No test spends real money: the v2 key is never in a test's environment, and nothing loads it from 1Password."""
    import token_store

    monkeypatch.delenv("JUNO_V2_API_KEY", raising=False)
    monkeypatch.setattr(token_store, "load_late_secrets", lambda: [])


@pytest.fixture(autouse=True)
def _fresh_conversation_clock():
    """The bridge remembers when it last talked in each DM (mid-conversation: no working line). Tests start cold."""
    import slack_bridge
    slack_bridge._last_exchange.clear()
    yield
    slack_bridge._last_exchange.clear()


@pytest.fixture(autouse=True)
def _no_real_cli_model_call(monkeypatch):
    """No test reaches the real Claude Code CLI through the engine: the Max-plan client refuses unless a test gives
    it a fake runner, and the backend defaults to the old API path (no key, so DMs hand off as they used to)."""
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    from v2 import config, max_lanes

    def refuse(*a, **k):
        raise RuntimeError("tests never reach the real Claude Code CLI")

    monkeypatch.setattr(config, "BACKEND", "api")
    monkeypatch.setattr(max_lanes, "_default_runner", lambda: refuse)
