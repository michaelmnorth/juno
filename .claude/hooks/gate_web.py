"""PreToolUse hook for WebSearch and WebFetch: in Juno's own runs, only Scout (the researcher subagent) goes online.

The coordinator's run holds mail text and private memory, so it never searches or fetches itself: it hands Scout a
question, and Scout gets nothing else (docs/v2 brief P0, added item 2; 05-SECURITY.md, Rule of Two). The hook input
names the subagent making the call in `agent_type`; the main conversation has none.

A Code-tab session with Michael (no COORDINATOR_UNATTENDED) is not gated.
"""
from __future__ import annotations

import json
import os
import sys

WEB_TOOLS = ("WebSearch", "WebFetch")
ONLINE_AGENTS = ("researcher",)


def decide(tool_name: str, data: dict, env: dict) -> str | None:
    if tool_name not in WEB_TOOLS or "COORDINATOR_UNATTENDED" not in env:
        return None
    if data.get("agent_type") in ONLINE_AGENTS:
        return None
    return ("Blocked: only the researcher subagent goes online. Give it the question (and nothing from mail or "
            "memory) and use its findings.")


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig") or "{}"
    data = json.loads(raw)
    reason = decide(data.get("tool_name") or "", data, os.environ)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
