"""P2 "do things" (docs/v2/briefs/P2-DO-THINGS.md), on synthetic data with fakes. Nothing here reaches the Claude
API, Gmail, Discord or a browser."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_v2 import FakeClient, config, env, final, route_resp, text, tool_call  # noqa: E402,F401
from v2 import tools  # noqa: E402


def audit(root: Path) -> list[dict]:
    path = root / "state" / "audit.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# --- 1. today's failure ------------------------------------------------------------------------------------------

def test_unknown_tool_call_is_refused_and_audited(env):
    e = env.make([route_resp("mail"), tool_call("send_email", {"to": "x@y.z"}), final("Here's what I found.")])
    e.handle("C1", "review my email", "C1:1")
    refused = [a for a in audit(env.root) if a["event"] == "v2_tool_refused"]
    assert refused and refused[0]["tool"] == "unknown" and refused[0]["asked_for"] == "send_email"


def test_card_that_cannot_be_built_is_audited_and_says_nothing_happened(env):
    def broken(draft_id):
        raise KeyError(draft_id)
    env.backend.draft_info = broken
    e = env.make([route_resp("mail"), tool_call("mail_send", {"draft_id": "made-up"}), final("Nothing sent.")])
    e.handle("C1", "send it", "C1:2")
    refused = [a for a in audit(env.root) if a["event"] == "v2_tool_refused"]
    assert refused[0]["tool"] == "mail_send" and "card not prepared" in refused[0]["reason"]
    sent = env.holder["client"].requests[-1]["messages"][-1]["content"][0]
    assert sent["is_error"] and "Nothing was sent" in sent["content"]


def test_refused_draft_and_denied_tool_are_audited(env):
    e = env.make([route_resp("mail"), tool_call("mail_draft", {"to": "a@b.c", "subject": "s", "body": "b"}),
                  tool_call("calendar_hold", {"title": "x", "start": "2026-11-13T09:00", "end": "2026-11-13T10:00",
                                              "note": ""}, tid="tu2"),
                  final("ok")])
    e.handle("C1", "what's new in my inbox", "C1:3")
    reasons = [a["reason"] for a in audit(env.root) if a["event"] == "v2_tool_refused"]
    assert reasons == ["no draft asked for", "that tool isn't available here"]


def test_hand_off_after_only_reading_goes_to_v1(env):
    reader = text({"category": "personal", "asks_for": "nothing", "due_date": "", "amount": "", "meeting_times": [],
                   "suspicious": True, "gist": "x"}, model=config.HAIKU)
    e = env.make([route_resp("mail"), tool_call("mail_search", {"query": "from:me", "limit": 3}),
                  tool_call("mail_read", {"message_id": "m1", "include_gist": False}, tid="tu2"), reader,
                  text({"reaction": "eyes", "reply": "", "hand_off": True})])
    reply = e.handle("C1", "review the attachment in my latest email", "C1:4")
    assert reply.handoff and reply.text == ""
    assert any(a["event"] == "v2_handoff" and a["why"] == "model" for a in audit(env.root))


def test_hand_off_after_a_write_is_not_allowed(env):
    e = env.make([route_resp("notes"), tool_call("reminder_add", {"text": "x", "due": "2026-11-13T09:00"}),
                  text({"reaction": "eyes", "reply": "Set it.", "hand_off": True})])
    reply = e.handle("C1", "remind me and also check my sleep", "C1:5")
    assert not reply.handoff and "Set it." in reply.text  # the reminder exists; v1 must not do it twice


def test_photo_or_file_goes_straight_to_v1_without_a_model_call(env):
    e = env.make([])
    msg = "What's wrong with my washer?\n[He attached a photo, saved at state/attachments/1-0.jpg. Read it to see it.]"
    reply = e.handle("C1", msg, "C1:6")
    assert reply.handoff and env.holder["client"].requests == []
    msg = "Look at this\n[He attached a file (notes.md), saved at state/attachments/2-0.md. Read it to see it.]"
    assert e.handle("C1", msg, "C1:7").handoff


def test_mail_read_lists_attachment_types_never_names(env):
    env.backend.mail_body = lambda mid: {"from": "me@example.com", "subject": "Write-up", "date": "x",
                                         "text": "See attached.", "attachments": [{"type": "text/markdown", "kb": 14,
                                                                                   "name": "secret plan.md"}]}
    reader = text({"category": "personal", "asks_for": "nothing", "due_date": "", "amount": "", "meeting_times": [],
                   "suspicious": False, "gist": "x"}, model=config.HAIKU)
    e = env.make([route_resp("mail"), tool_call("mail_read", {"message_id": "m1", "include_gist": False}), reader,
                  final("It has a file.")])
    e.handle("C1", "what's in my write-up email", "C1:9")
    sent = env.holder["client"].requests[-1]["messages"][-1]["content"][0]["content"]
    assert "text/markdown" in sent and "hand_off" in sent and "secret plan" not in sent


def test_gmail_attachment_parts_are_types_and_sizes():
    from v2.backend import attachment_parts
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "text/plain", "body": {"size": 10}},
        {"mimeType": "application/pdf", "filename": "x.pdf", "body": {"attachmentId": "A1", "size": 20480}}]}
    assert attachment_parts(payload) == [{"type": "application/pdf", "kb": 20}]


def test_dialogue_set_covers_attachments_and_photos():
    from evals.dialogues import DIALOGUES
    ids = {d["id"]: d for d in DIALOGUES}
    assert ids["review-attachment"]["turns"][0]["handoff"] and ids["photo-hands-off"]["turns"][0]["handoff"]


def test_constitution_forbids_asking_him_to_paste():
    text_ = (ROOT / "v2" / "prompts" / "constitution.md").read_text(encoding="utf-8")
    assert "Never ask him to paste" in text_ and "attachment" in text_
