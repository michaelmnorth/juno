"""PreToolUse hook for the few outward tools an approved action may use (sending a draft, calendar events).

These tools are not in the settings allow list, so an ordinary run cannot use them at all. The bridge grants one of
them only to the run that carries out an approval Michael tapped (or an always-allow rule he set), and passes what
was approved in the environment. This hook checks the call matches exactly that:

- Gmail send_message: only with COORDINATOR_APPROVED_CLASS=email.send, and only `draftId` equal to
  COORDINATOR_APPROVED_DRAFT. No free-form to/cc/bcc/body, so what goes out is the draft Michael saw.
- Gmail create_draft / update_draft during an approved send: denied, so the draft cannot change after approval.
- Calendar create_event / update_event: only with an approved calendar class. calendar.hold means Michael's own
  primary calendar, no attendees, no Meet link. Other classes may invite only COORDINATOR_APPROVED_RECIPIENTS.
"""
from __future__ import annotations

import json
import os
import sys


def _emails(value) -> set[str]:
    out: set[str] = set()
    for item in value or []:
        email = item.get("email") if isinstance(item, dict) else item
        if email:
            out.add(str(email).strip().lower())
    return out


def decide(tool_name: str, tool_input: dict, env: dict) -> str | None:
    cls = env.get("COORDINATOR_APPROVED_CLASS", "")
    name = tool_name.rsplit("__", 1)[-1]

    if name == "send_message":
        if cls != "email.send":
            return "Blocked: sending email needs Michael's tap on that exact draft."
        draft = env.get("COORDINATOR_APPROVED_DRAFT", "")
        if not draft or tool_input.get("draftId") != draft:
            return f"Blocked: only the approved draft ({draft or 'none'}) may be sent."
        extra = [k for k in ("to", "cc", "bcc", "subject", "body", "htmlBody", "attachments") if tool_input.get(k)]
        if extra:
            return f"Blocked: send the approved draft as is; do not pass {', '.join(extra)}."
        return None

    if name in ("create_draft", "update_draft"):
        if cls == "email.send":
            return "Blocked: the draft cannot change after Michael approved it."
        return None

    if name in ("create_event", "update_event"):
        if not cls.startswith("calendar."):
            return "Blocked: calendar changes need an approval or an auto rule in me/automation.yaml."
        invited = _emails(tool_input.get("attendees")) | _emails(tool_input.get("attendeeEmails"))
        if cls == "calendar.hold":
            if invited or tool_input.get("addGoogleMeetUrl") or tool_input.get("googleMeetUrl"):
                return "Blocked: a hold is for Michael only: no attendees, no Meet link."
            if tool_input.get("calendarId") not in (None, "", "primary"):
                return "Blocked: holds go on Michael's primary calendar only."
            return None
        approved = {e.strip().lower() for e in env.get("COORDINATOR_APPROVED_RECIPIENTS", "").split(",") if e.strip()}
        if invited - approved:
            return f"Blocked: not approved to invite {', '.join(sorted(invited - approved))}."
        return None

    return None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig") or "{}"
    data = json.loads(raw)
    reason = decide(data.get("tool_name") or "", data.get("tool_input") or {}, os.environ)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
