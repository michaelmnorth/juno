"""Connector tools that act outward must stay denied; reads and drafts are the only connector allows."""
from __future__ import annotations

import json
from pathlib import Path

PERMS = json.loads((Path(__file__).resolve().parents[1] / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]


def test_outward_tools_are_denied():
    # send_message and create/update_event are not denied: an approved action may be granted them for one run
    # (gateway/approval_policy.py, checked by .claude/hooks/gate_outward.py). They are never in the allow list.
    for tool in ("Gmail__forward", "Gmail__reply", "Gmail__trash_thread",
                 "Google_Calendar__delete_event", "Slack__slack_send_message",
                 "Google_Sheets__append_values", "Google_Drive__share_file", "Google_Docs__update_doc"):
        assert f"mcp__claude_ai_{tool}" in PERMS["deny"]


def test_allow_and_deny_do_not_overlap():
    assert not set(PERMS["allow"]) & set(PERMS["deny"])


def test_connector_allows_are_reads_or_drafts():
    allowed = [t.split("__")[-1] for t in PERMS["allow"] if t.startswith("mcp__")]
    assert allowed and all(t.startswith(("search", "get", "list", "read", "suggest")) or t.endswith("_draft") for t in allowed)


def test_untrusted_connectors_are_not_allowed():
    assert not [t for t in PERMS["allow"] if "Wispr" in t or "Spotify" in t or "__slack_" in t]
