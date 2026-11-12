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


# --- 2. attachments ----------------------------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _gmail_get(sender: str):
    payload = {"headers": [{"name": "From", "value": f"Me <{sender}>"}], "mimeType": "multipart/mixed", "parts": [
        {"mimeType": "text/plain", "body": {"size": 5, "data": _b64(b"hello")}},
        {"mimeType": "application/octet-stream", "filename": "write-up.md", "body": {"attachmentId": "A1", "size": 9}},
        {"mimeType": "application/zip", "filename": "x.zip", "body": {"attachmentId": "A2", "size": 9}},
        {"mimeType": "image/png", "filename": "label.png", "body": {"attachmentId": "A3", "size": 4}}]}
    seen = []

    def get(url, token, params=None):
        seen.append(url)
        if url.endswith("/attachments/A1"):
            return {"data": _b64(b"# Write-up")}
        if url.endswith("/attachments/A3"):
            return {"data": _b64(b"\x89PNG")}
        return {"payload": payload}
    return get, seen


def test_gmail_attachments_saves_readable_files_from_known_senders(tmp_path):
    import gmail
    get, seen = _gmail_get("me@example.com")
    out = gmail.attachments("msg123456", token="t", get=get, root=tmp_path, label=lambda a: "michael")
    paths = [s["path"] for s in out["saved"]]
    assert paths == ["state/attachments/gmail-msg123456-0.md", "state/attachments/gmail-msg123456-1.png"]
    assert (tmp_path / paths[0]).read_text(encoding="utf-8") == "# Write-up"
    assert out["skipped"] == [{"type": "application/zip", "kb": 0}] and not any("A2" in u for u in seen)


def test_gmail_attachments_never_opens_unknown_or_contact_senders(tmp_path):
    import gmail
    for who in ("unknown", "contact"):
        get, seen = _gmail_get("stranger@example.org")
        out = gmail.attachments("msg123456", token="t", get=get, root=tmp_path, label=lambda a, w=who: w)
        assert out["saved"] == [] and "never opened" in out["refused"] and len(seen) == 1
    assert not (tmp_path / "state" / "attachments").exists()


def test_gmail_attachments_rejects_odd_ids():
    import gmail
    from google_read import GoogleError
    try:
        gmail.attachments("../../etc", token="t", get=lambda *a, **k: {})
    except GoogleError:
        return
    raise AssertionError("expected a refusal")


def test_pdf_attachment_gets_a_text_copy(tmp_path, monkeypatch):
    import gmail
    payload = {"headers": [{"name": "From", "value": "me@example.com"}], "parts": [
        {"mimeType": "application/pdf", "filename": "r.pdf", "body": {"attachmentId": "P1", "size": 4}}]}
    monkeypatch.setattr(gmail, "pdf_text", lambda path: "Order 12345")
    get = lambda url, token, params=None: {"data": _b64(b"%PDF")} if url.endswith("P1") else {"payload": payload}
    out = gmail.attachments("msg123456", token="t", get=get, root=tmp_path, label=lambda a: "known")
    assert (tmp_path / out["saved"][0]["text_path"]).read_text(encoding="utf-8") == "Order 12345"


def test_discord_markdown_file_is_saved_and_named_in_the_dm(tmp_path):
    import discord_transport as dt
    import slack_bridge
    ev = dt.message_event(message_id="1290000000000000001", channel_id="DM-1", author_id="U9", content="read this",
                          attachments=[{"id": 5, "content_type": "text/markdown; charset=utf-8", "size": 30,
                                        "url": "https://cdn.discordapp.com/a/5/write-up.md", "filename": "write-up.md"},
                                       {"id": 6, "content_type": "", "size": 30,
                                        "url": "https://cdn.discordapp.com/a/6/n.csv", "filename": "n.csv"},
                                       {"id": 7, "content_type": "application/zip", "size": 30,
                                        "url": "https://cdn.discordapp.com/a/7/x.zip", "filename": "x.zip"},
                                       {"id": 8, "content_type": "text/plain", "size": 30,
                                        "url": "https://cdn.discordapp.com/a/8/page.txt", "filename": "page.txt"}])
    pages = {"5": b"# Notes", "6": b"a,b", "8": b"<!DOCTYPE html><html>sign in"}
    saved = slack_bridge.save_files(ev, "", tmp_path, hosts=dt.FILE_HOSTS,
                                    fetch=lambda url: pages[url.split("/a/")[1].split("/")[0]])
    assert saved == {"5": "state/attachments/1290000000000000001-0.md",
                     "6": "state/attachments/1290000000000000001-1.csv"}
    text_ = slack_bridge.dm_text(ev, saved)
    assert "[He attached a file (write-up.md), saved at state/attachments/1290000000000000001-0.md." in text_
    assert "[He attached x.zip, which you can't open." in text_
    from v2.converse import ATTACHED
    assert ATTACHED.search(text_)


def test_oversized_file_is_not_downloaded(tmp_path):
    import slack_bridge
    ev = {"ts": "1.2", "files": [{"id": "F1", "mimetype": "application/pdf", "size": 11 * 1024 * 1024,
                                  "url_private": "https://files.slack.com/big.pdf"}]}
    assert slack_bridge.save_files(ev, "t", tmp_path, fetch=lambda u: (_ for _ in ()).throw(AssertionError())) == {}


# --- 3. reader schema ----------------------------------------------------------------------------------------------

def test_reader_returns_order_fields_cleaned_and_they_taint(env):
    reader = text({"category": "receipt", "asks_for": "nothing", "due_date": "", "amount": "1299.00 USD",
                   "meeting_times": [], "merchant": "Big Box <script>", "order_number": "BB-1234 5678",
                   "order_date": "2024-03-02", "items": ["WashCombo WM6998HBA", "", "x" * 200],
                   "delivered_on": "soon", "suspicious": False, "gist": "Order confirmation."}, model=config.HAIKU)
    e = env.make([route_resp("mail"), tool_call("mail_read", {"message_id": "m1", "include_gist": False}), reader,
                  final("Bought 2024-03-02.")])
    e.handle("C1", "when did I buy my washer", "C1:30")
    sent = json.loads(env.holder["client"].requests[-1]["messages"][-1]["content"][0]["content"])
    assert sent["merchant"] == "Big Box script" and sent["order_number"] == "BB-12345678"
    assert sent["order_date"] == "2024-03-02" and "delivered_on" not in sent
    assert sent["items"][0] == "WashCombo WM6998HBA" and len(sent["items"]) == 2 and len(sent["items"][1]) == 80
    assert e.store.thread("C1")["tainted"]  # merchant and item names are the sender's words


def test_reader_schema_has_the_order_fields_and_a_narrow_suspicious():
    from v2 import lanes
    props = lanes.READER_SCHEMA["properties"]
    assert {"merchant", "order_number", "order_date", "items", "delivered_on"} <= set(props)
    assert set(lanes.READER_SCHEMA["required"]) == set(props)
    assert "not" in props["suspicious"]["description"]


# --- 4. home domain and follow-ups ----------------------------------------------------------------------------------

def test_followups_add_list_match_close(tmp_path):
    from datetime import date
    import followups as fu
    path = tmp_path / "f.json"
    today = date(2026, 11, 12)
    a = fu.add("Replacement drain pump ships", "2026-11-20", "shipping mail from the maker", "LG, drain pump",
               "claim 2026-11-12", path=path, today=today)
    fu.add("Refund lands", "2026-11-14", "refund mail", "refund,acme", path=path, today=today)
    assert a["id"].startswith("f-") and a["match"] == ["lg", "drain pump"]
    rows = fu.listing(path, today=date(2026, 11, 16))
    assert [r["what"] for r in rows] == ["Refund lands", "Replacement drain pump ships"]
    assert [r["what"] for r in fu.listing(path, overdue=True, today=date(2026, 11, 16))] == ["Refund lands"]
    inbox = {"sorted": [{"id": "m1", "from": "LG Parts <parts@lg.example>", "subject": "Your order has shipped"},
                        {"id": "m2", "from": "news@glgx.example", "subject": "Weekly deals"}],
             "unclear": [{"id": "m3", "from": "x@y.example", "subject": "About your drain pump"}]}
    hits = fu.match(fu._mail_items(json.dumps(inbox)), path)
    assert [h["message_id"] for h in hits] == ["m1", "m3"]  # "lg" is a whole word only, so glgx is no match
    done = fu.close(a["id"], "Shipped 2026-11-15, delivered 2026-11-18", path)
    assert done["how"].startswith("Shipped") and not [r for r in fu.listing(path) if r["id"] == a["id"]]
    assert fu.listing(path, every=True, today=today)[-1]["id"] == a["id"]


def test_followups_refuse_bad_input(tmp_path):
    from datetime import date
    import followups as fu
    path = tmp_path / "f.json"
    for args in [("x", "2026-13-01", "y", "abc"), ("x", "2026-11-01", "y", "abc"), ("x", "2026-11-20", "y", "a,b"),
                 ("", "2026-11-20", "y", "abc")]:
        try:
            fu.add(*args, path=path, today=date(2026, 11, 12))
        except fu.Bad:
            continue
        raise AssertionError(f"accepted {args}")
    assert fu.main(["close", "--id", "f-nope", "--how", "x"]) == fu.BAD_INPUT


def test_sweep_and_brief_use_followups_and_home_domain_is_routed():
    sweep = (ROOT / ".claude" / "skills" / "sweep" / "SKILL.md").read_text(encoding="utf-8")
    brief = (ROOT / ".claude" / "skills" / "morning-brief" / "SKILL.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "followups.py match" in sweep and "followups.py close" in sweep
    assert "followups.py list" in brief
    assert "domains/home/private/appliances.md" in claude and "followups.py add" in claude
    example = (ROOT / "domains" / "home" / "CONTEXT.example.md").read_text(encoding="utf-8")
    assert "private/appliances.md" in example


# --- 5. research playbook with server-side web tools ---------------------------------------------------------------

def _research_answer(text_="The E6 code is usually the drain pump.", url="https://www.lg.example/support/e6",
                     searches=2):
    from types import SimpleNamespace as NS
    from test_v2 import usage
    u = usage()
    u.server_tool_use = NS(web_search_requests=searches, web_fetch_requests=1)
    return NS(content=[NS(type="server_tool_use", id="srv1", name="web_search", input={"query": "e6"}),
                       NS(type="web_search_tool_result", tool_use_id="srv1", content=[]),
                       NS(type="text", text=text_, citations=[NS(type="web_search_result_location", url=url,
                                                                  title="t", cited_text="x")])],
              stop_reason="end_turn", usage=u, model=config.SONNET)


def test_research_runs_with_server_tools_and_no_json_format(env):
    e = env.make([route_resp("research"), _research_answer()])
    reply = e.handle("C1", "look into what an E6 error on my washer means", "C1:40")
    req = env.holder["client"].requests[-1]
    types_ = [t.get("type") for t in req["tools"]]
    assert "web_search_20260318" in types_ and "web_fetch_20260318" in types_
    search = next(t for t in req["tools"] if t.get("name") == "web_search")
    assert search["max_uses"] == 3
    assert "format" not in req["output_config"]  # citations and structured outputs don't mix
    assert "drain pump" in reply.text and "Sources: https://www.lg.example/support/e6" in reply.text
    assert e.store.thread("C1")["tainted"]  # a web result is outside text


def test_research_search_cost_is_counted_in_the_ledger(env):
    e = env.make([route_resp("research"), _research_answer(searches=3)])
    reply = e.handle("C1", "research E6", "C1:41")
    rows = e.store.ledger_rows(reply.run_id)
    converse = [r for r in rows if r["run_class"] == "converse"]
    assert converse[0]["searches"] == 3
    assert reply.cost >= 0.03  # three searches at $0.01 plus tokens


def test_research_can_hand_off_and_other_playbooks_keep_json(env):
    e = env.make([route_resp("research"), _research_answer(text_="HAND_OFF")])
    assert e.handle("C1", "research and fill in the claim form", "C1:42").handoff
    e2 = env.make([route_resp("notes"), final("ok")])
    e2.handle("C1", "what's on my list", "C1:43")
    req = env.holder["client"].requests[-1]
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert not any(str(t.get("type", "")).startswith("web_") for t in req.get("tools", []))


def test_citation_links_come_from_code_and_only_https(env):
    from v2 import lanes
    resp = _research_answer(url="javascript:alert(1)")
    assert "Sources" not in lanes.plain_reply(resp)["reply"]


def test_router_knows_research():
    from v2 import router
    assert "research" in router.PLAYBOOKS and "research (look into" in router.SYSTEM
    assert (ROOT / "v2" / "playbooks" / "research" / "SKILL.md").exists()


# --- 6. shopping skill and attachments on drafts -------------------------------------------------------------------

def _raw_of(call_log):
    import base64
    import email as em
    raw = call_log[-1][3]["message"]["raw"]
    return em.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_draft_attaches_project_files_and_logs_them(tmp_path):
    import gmail
    (tmp_path / "state" / "outbox").mkdir(parents=True)
    (tmp_path / "state" / "outbox" / "write-up.md").write_text("# Notes", encoding="utf-8")
    calls = []
    call = lambda m, u, t, body=None, params=None: calls.append((m, u, t, body)) or {"id": "D1", "message": {
        "id": "M1", "threadId": "T1"}}
    out = gmail.draft(["me@example.com"], [], "Write-up", "Attached.\n", token="t", call=call,
                      get=lambda *a, **k: {}, log=tmp_path / "drafts.jsonl", with_signature=False,
                      attach=["state/outbox/write-up.md"], root=tmp_path, context="self (Michael)")
    assert out["attachments"] == ["write-up.md"]
    msg = _raw_of(calls)
    assert gmail.attachment_names(msg) == ["write-up.md"]
    assert json.loads((tmp_path / "drafts.jsonl").read_text(encoding="utf-8"))["attachments"] == ["write-up.md"]


def test_attach_refuses_outside_hidden_secret_and_big_files(tmp_path):
    import gmail
    from google_read import GoogleError
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "x.md").write_text("x", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "google.env").write_text("x", encoding="utf-8")
    (tmp_path / "token_store.txt").write_text("x", encoding="utf-8")
    big = tmp_path / "big.pdf"
    big.write_bytes(b"0" * (10 * 1024 * 1024 + 1))
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    for bad in [str(outside), "../outside.txt", ".claude/x.md", "tools/google.env", "token_store.txt", "big.pdf",
                "missing.md"]:
        try:
            gmail.check_attachments([bad], tmp_path)
        except GoogleError:
            continue
        raise AssertionError(f"attached {bad}")


def test_send_refuses_when_attachments_differ_from_the_card(tmp_path):
    import base64
    import gmail
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    raw = gmail.build_raw(["sam@example.com"], [], "Hi", "Here it is.\n", files=[tmp_path / "a.md"])
    get = lambda url, token, params=None: {"message": {"raw": raw}}
    sent = []
    call = lambda *a, **k: sent.append(a) or {"id": "S1"}
    out = gmail.send_approved("D1", "sam@example.com", "Here it is.", token="t", call=call, get=get)
    assert out == {"sent": False, "why": "attachments changed", "current_text": "Here it is."} and not sent
    out = gmail.send_approved("D1", "sam@example.com", "Here it is.", token="t", call=call, get=get,
                              attachments=["a.md"])
    assert out["sent"] and sent


def test_send_card_lists_attachments():
    from approval_policy import blocks
    entry = {"id": "a-1", "action_class": "email.send", "summary": "Send the write-up", "to": "me@example.com",
             "subject": "x", "draft_text": "hi", "attachments": ["write-up.md"]}
    text_ = json.dumps(blocks(entry, "michael"))
    assert "Attached" in text_ and "write-up.md" in text_


def test_shopping_skill_reads_prices_on_the_page_and_never_buys():
    skill = (ROOT / ".claude" / "skills" / "shopping" / "SKILL.md").read_text(encoding="utf-8")
    assert "Free first" in skill and "product page" in skill and "never buys" in skill.lower()
