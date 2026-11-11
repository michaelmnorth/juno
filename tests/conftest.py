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
