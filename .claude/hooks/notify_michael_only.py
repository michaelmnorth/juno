"""PreToolUse hook: outbound chat messages may only go to Michael.

Works for any messaging tool: it looks at the common recipient fields (chat_id, channel_id, channel, to, user_id,
recipient) and allows the call only when every recipient found is in me/notify-allowlist.json:
    {"slack": ["U0XXXXXXXXX"], "email": []}
Values are compared as strings. If no recipient field is present at all, the call is allowed (the channel plugin's
reply tool replies to the paired sender, who is already allowlisted by the channel itself).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RECIPIENT_KEYS = ("chat_id", "channel_id", "channel", "to", "user_id", "recipient", "recipients")


def load_allowlist(root: Path) -> set[str]:
    path = root / "me" / "notify-allowlist.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    allowed: set[str] = set()
    for values in data.values():
        if isinstance(values, list):
            allowed.update(str(v) for v in values)
    return allowed


def recipients(tool_input: dict) -> list[str]:
    found: list[str] = []
    for key in RECIPIENT_KEYS:
        if key in tool_input and tool_input[key] not in (None, ""):
            value = tool_input[key]
            if isinstance(value, list):
                found.extend(str(v) for v in value)
            else:
                found.append(str(value))
    return found


def decide(tool_input: dict, allowed: set[str]) -> str | None:
    targets = recipients(tool_input)
    if not targets:
        return None
    bad = [t for t in targets if t not in allowed]
    if bad:
        return f"Blocked: the coordinator may only message Michael. Not allowlisted: {', '.join(bad)}."
    return None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig") or "{}"
    data = json.loads(raw)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    reason = decide(data.get("tool_input") or {}, load_allowlist(root))
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
