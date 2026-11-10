"""tools/gmail.py, tools/gcal.py and gateway/approval_tokens.py, offline: Google is a fake that records calls."""
from __future__ import annotations

import base64
import email
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "gateway"))

import approval_policy  # noqa: E402
import approval_tokens  # noqa: E402
import gcal  # noqa: E402
import gmail  # noqa: E402
from google_read import BAD_INPUT, REFUSED, GoogleError  # noqa: E402


class Fake:
    def __init__(self, reads: dict | None = None, made: dict | None = None):
        self.reads, self.made, self.calls = {"/settings/sendAs": {"sendAs": []}, **(reads or {})}, made or {}, []

    def get(self, url, token, params=None):
        for key, value in self.reads.items():
            if url.endswith(key):
                return value
        raise AssertionError(f"unexpected read {url}")

    def call(self, method, url, token, body=None, params=None):
        self.calls.append((method, url, body, params))
        return self.made


def _decoded(raw: str) -> email.message.Message:
    return email.message_from_bytes(base64.urlsafe_b64decode(raw))


# --- gmail -----------------------------------------------------------------------------------------

def test_reply_draft_threads_and_logs(tmp_path):
    fake = Fake(reads={"/messages/m1": {"threadId": "t1", "payload": {"headers": [
        {"name": "Subject", "value": "Dinner Friday"}, {"name": "Message-ID", "value": "<abc@x>"},
        {"name": "References", "value": "<zzz@x>"}]}}},
        made={"id": "r-1", "message": {"id": "m2", "threadId": "t1"}})
    log = tmp_path / "drafts.jsonl"
    out = gmail.draft(["sam@example.com"], [], "", "Sounds good.\n", "m1", "family (Sam)", token="t",
                      call=fake.call, get=fake.get, log=log)
    assert out == {"draft_id": "r-1", "message_id": "m2", "thread_id": "t1", "link": gmail.link("m2")}
    method, url, body, _ = fake.calls[0]
    assert method == "POST" and url.endswith("/drafts") and body["message"]["threadId"] == "t1"
    msg = _decoded(body["message"]["raw"])
    assert msg["Subject"] == "Re: Dinner Friday" and msg["In-Reply-To"] == "<abc@x>"
    assert msg["References"] == "<zzz@x> <abc@x>" and msg["To"] == "sam@example.com"
    line = json.loads(log.read_text(encoding="utf-8"))
    assert line["draft_id"] == "r-1" and line["context"] == "family (Sam)" and line["draft_text"] == "Sounds good."


def test_draft_carries_his_gmail_signature():
    sig = '<div>Michael<br>Atlanta &amp; around</div>'
    fake = Fake(reads={"/settings/sendAs": {"sendAs": [{"isDefault": False, "signature": "work"},
                                                       {"isDefault": True, "signature": sig}]}},
                made={"id": "r-3", "message": {"id": "m4", "threadId": "t4"}})
    gmail.draft(["a@b.com"], [], "Hi", "Line one\nLine two\n", token="t", call=fake.call, get=fake.get)
    msg = _decoded(fake.calls[0][2]["message"]["raw"])
    plain, rich = [part.get_payload(decode=True).decode() for part in msg.walk() if not part.is_multipart()]
    assert plain.startswith("Line one\nLine two\n\nMichael\nAtlanta & around")
    assert "Line one<br>" in rich and 'class="gmail_signature">' + sig in rich and "work" not in rich


def test_no_signature_flag_keeps_plain_text():
    fake = Fake(reads={"/settings/sendAs": {"sendAs": [{"isDefault": True, "signature": "<b>M</b>"}]}},
                made={"id": "r-4", "message": {"id": "m5"}})
    gmail.draft(["a@b.com"], [], "Hi", "Body\n", token="t", call=fake.call, get=fake.get, with_signature=False)
    msg = _decoded(fake.calls[0][2]["message"]["raw"])
    assert not msg.is_multipart() and "M" not in msg.get_payload()


def test_draft_without_context_writes_no_log(tmp_path):
    fake = Fake(made={"id": "r-2", "message": {"id": "m3", "threadId": "t3"}})
    gmail.draft(["a@b.com"], [], "Hi", "Body\n", token="t", call=fake.call, get=fake.get, log=tmp_path / "d.jsonl")
    assert not (tmp_path / "d.jsonl").exists()


@pytest.mark.parametrize("to", [[], ["not-an-address"], ["a@b.com, c@d.com"], ["x@y.com"] * 11])
def test_draft_refuses_bad_recipients(to):
    with pytest.raises(GoogleError) as err:
        gmail.draft(to, [], "Hi", "Body\n", token="t", call=Fake().call, get=Fake().get)
    assert err.value.code == BAD_INPUT


def test_update_draft_refused_inside_an_approved_send():
    with pytest.raises(GoogleError) as err:
        gmail.update_draft("r-1", "new\n", env={"COORDINATOR_APPROVED_CLASS": "email.send"}, token="t",
                           call=Fake().call, get=Fake().get)
    assert err.value.code == REFUSED


def test_update_draft_keeps_recipients_and_thread():
    fake = Fake(reads={"/drafts/r-1": {"message": {"threadId": "t1", "payload": {"headers": [
        {"name": "To", "value": "a@b.com"}, {"name": "Subject", "value": "Re: X"},
        {"name": "In-Reply-To", "value": "<1@x>"}, {"name": "References", "value": "<0@x> <1@x>"}]}}}},
        made={"id": "r-1", "message": {"id": "m9", "threadId": "t1"}})
    gmail.update_draft("r-1", "new text\n", env={}, token="t", call=fake.call, get=fake.get)
    method, url, body, _ = fake.calls[0]
    msg = _decoded(body["message"]["raw"])
    assert method == "PUT" and msg["To"] == "a@b.com" and msg["References"] == "<0@x> <1@x>"
    assert body["message"]["threadId"] == "t1" and "new text" in msg.get_payload()


@pytest.mark.parametrize("name", ["INBOX", "TRASH", "Bills", "juno/x", "Juno/", "Juno/a/b/c", "Juno/" + "x" * 41])
def test_labels_outside_juno_are_refused(name):
    with pytest.raises(GoogleError):
        gmail.label("m1", "message", [name], [], token="t", call=Fake().call, get=Fake().get)


def test_label_creates_missing_juno_label_then_applies():
    fake = Fake(reads={"/labels": {"labels": [{"name": "Juno/Bills", "id": "L1", "type": "user"},
                                              {"name": "INBOX", "id": "INBOX", "type": "system"}]}},
                made={"id": "L2"})
    out = gmail.label("t1", "thread", ["Juno/Waiting"], ["Juno/Bills"], token="t", call=fake.call, get=fake.get)
    assert fake.calls[0][0] == "POST" and fake.calls[0][2]["name"] == "Juno/Waiting"
    method, url, body, _ = fake.calls[1]
    assert url.endswith("/threads/t1/modify") and body == {"addLabelIds": ["L2"], "removeLabelIds": ["L1"]}
    assert out["added"] == ["Juno/Waiting"] and out["removed"] == ["Juno/Bills"]


def test_gmail_has_no_general_send_or_delete():
    names = set(dir(gmail))
    assert not names & {"send", "send_message", "trash", "delete", "archive"}


# --- approval tokens -------------------------------------------------------------------------------

def test_token_is_one_time_and_scoped(tmp_path):
    token = approval_tokens.issue(tmp_path, "a-1", "calendar.event.create", ["Jess@Example.com"])
    assert token not in (tmp_path / approval_tokens.FILE).read_text()
    rec, why = approval_tokens.check(tmp_path, token, ("calendar.event.create",), {"jess@example.com"})
    assert rec and not why
    assert approval_tokens.check(tmp_path, token, ("calendar.hold",), set())[0] is None
    assert "not approved to invite" in approval_tokens.check(tmp_path, token, ("calendar.event.create",),
                                                              {"x@y.com"})[1]
    approval_tokens.spend(tmp_path, token)
    assert "already used" in approval_tokens.check(tmp_path, token, ("calendar.event.create",), set())[1]


def test_token_expires(tmp_path):
    then = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    token = approval_tokens.issue(tmp_path, "a-1", "calendar.hold", [], now=then)
    later = then + approval_tokens.TTL + timedelta(seconds=1)
    assert "expired" in approval_tokens.check(tmp_path, token, ("calendar.hold",), set(), now=later)[1]
    assert "need an approval" in approval_tokens.check(tmp_path, "", ("calendar.hold",), set())[1]


def test_execution_issues_a_token_for_calendar_only(tmp_path):
    tools, env = approval_policy.execution({"id": "a-1", "action_class": "calendar.hold"}, tmp_path)
    assert tools == () and env["COORDINATOR_APPROVAL_TOKEN"]
    tools, env = approval_policy.execution({"id": "a-2", "action_class": "email.send", "draft_id": "r-1"}, tmp_path)
    assert "COORDINATOR_APPROVAL_TOKEN" not in env and env["COORDINATOR_APPROVED_DRAFT"] == "r-1"
    assert "gcal.py hold" in approval_policy.how_to({"action_class": "calendar.hold"})


# --- gcal ------------------------------------------------------------------------------------------

def test_hold_needs_a_token(tmp_path):
    fake = Fake(made={"id": "e1"})
    with pytest.raises(GoogleError) as err:
        gcal.hold("Prep", "2026-11-12T18:00", "2026-11-12T19:00", env={}, state=tmp_path, token="t", call=fake.call,
                  mode=lambda cls: "ask")
    assert err.value.code == REFUSED and not fake.calls


def test_hold_is_private_unnotified_and_spends_the_token(tmp_path):
    token = approval_tokens.issue(tmp_path, "a-1", "calendar.hold", [])
    fake = Fake(made={"id": "e1", "summary": "Prep", "start": {"dateTime": "x"}, "end": {"dateTime": "y"},
                      "extendedProperties": gcal.MARK})
    out = gcal.hold("Prep", "2026-11-12T18:00", "2026-11-12T19:00", env={"COORDINATOR_APPROVAL_TOKEN": token},
                    state=tmp_path, token="t", call=fake.call)
    method, url, body, params = fake.calls[0]
    assert params == {"sendUpdates": "none"} and "attendees" not in body and body["extendedProperties"] == gcal.MARK
    assert body["start"] == {"dateTime": "2026-11-12T18:00:00", "timeZone": "America/New_York"}
    assert out["juno_hold"]
    with pytest.raises(GoogleError):
        gcal.hold("Again", "2026-11-12T18:00", "2026-11-12T19:00", env={"COORDINATOR_APPROVAL_TOKEN": token},
                  state=tmp_path, token="t", call=fake.call, mode=lambda cls: "ask")


@pytest.mark.parametrize("start,end", [("2026-11-12T19:00", "2026-11-12T18:00"), ("tomorrow", "2026-11-12T18:00"),
                                       ("2026-11-12T06:00", "2026-11-12T19:00"),
                                       ("2026-11-12T18:00-05:00", "2026-11-12T19:00")])
def test_hold_rejects_bad_times(tmp_path, start, end):
    with pytest.raises(GoogleError) as err:
        gcal.hold("Prep", start, end, env={}, state=tmp_path, token="t", call=Fake().call, mode=lambda cls: "ask")
    assert err.value.code == BAD_INPUT


def test_event_invites_only_approved_people(tmp_path):
    token = approval_tokens.issue(tmp_path, "a-1", "calendar.event.create", ["jess@example.com"])
    env = {"COORDINATOR_APPROVAL_TOKEN": token}
    fake = Fake(made={"id": "e2"})
    with pytest.raises(GoogleError):
        gcal.event("Dinner", "2026-11-14T19:00", "2026-11-14T21:00", invite=["jess@example.com", "x@y.com"],
                   env=env, state=tmp_path, token="t", call=fake.call)
    assert not fake.calls
    gcal.event("Dinner", "2026-11-14T19:00", "2026-11-14T21:00", invite=["Jess@example.com"], env=env,
               state=tmp_path, token="t", call=fake.call)
    assert fake.calls[0][3] == {"sendUpdates": "all"} and fake.calls[0][2]["attendees"] == [{"email": "jess@example.com"}]


def test_update_checks_only_newly_invited(tmp_path):
    token = approval_tokens.issue(tmp_path, "a-1", "calendar.event.update", [])
    fake = Fake(reads={"/e3": {"id": "e3", "attendees": [{"email": "sam@example.com"}],
                               "start": {"dateTime": "2026-11-14T19:00:00-05:00"},
                               "end": {"dateTime": "2026-11-14T21:00:00-05:00"}}}, made={"id": "e3"})
    gcal.update("e3", end="2026-11-14T22:00:00-05:00", invite=["sam@example.com"],
                env={"COORDINATOR_APPROVAL_TOKEN": token}, state=tmp_path, token="t", call=fake.call, get=fake.get)
    method, url, body, _ = fake.calls[0]
    assert method == "PATCH" and body["attendees"] == [{"email": "sam@example.com"}]
    assert body["end"]["dateTime"] == "2026-11-14T22:00:00-05:00"


def test_undo_hold_only_for_junos_own(tmp_path):
    mine = Fake(reads={"/e1": {"id": "e1", "summary": "Prep", "extendedProperties": gcal.MARK}})
    assert gcal.undo_hold("e1", token="t", call=mine.call, get=mine.get)["removed"] == "e1"
    assert mine.calls[0][0] == "DELETE"
    theirs = Fake(reads={"/e2": {"id": "e2", "summary": "Dentist"}})
    with pytest.raises(GoogleError):
        gcal.undo_hold("e2", token="t", call=theirs.call, get=theirs.get)
    assert not theirs.calls


def test_events_are_compact():
    fake = Fake(reads={"/events": {"items": [
        {"id": "e1", "summary": "Lift", "start": {"dateTime": "2026-11-09T06:00:00-05:00"},
         "end": {"dateTime": "2026-11-09T07:30:00-05:00"}, "attendees": [{}, {}]},
        {"id": "e2", "status": "cancelled"}]}})
    out = gcal.events("2026-11-09", 1, token="t", get=fake.get)
    assert out == [{"id": "e1", "start": "2026-11-09T06:00:00-05:00", "end": "2026-11-09T07:30:00-05:00",
                    "title": "Lift", "location": "", "attendees": 2, "busy": True, "juno_hold": False, "link": ""}]


def test_hold_runs_directly_when_automation_allows(tmp_path):
    fake = Fake(made={"id": "e5", "summary": "Prep", "extendedProperties": gcal.MARK})
    out = gcal.hold("Prep", "2026-11-12T18:00", "2026-11-12T19:00", env={}, state=tmp_path, token="t",
                    call=fake.call, mode=lambda cls: "auto_notify")
    assert out["id"] == "e5" and fake.calls[0][3] == {"sendUpdates": "none"}
    assert json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))["event"] == "auto_hold"


def _raw(headers: str) -> str:
    return base64.urlsafe_b64encode((headers + "\r\n\r\ntest 123\r\n").encode()).decode().rstrip("=")


def test_send_self_sends_only_to_michael(tmp_path):
    fake = Fake(reads={"/drafts/r-1": {"message": {"raw": _raw("To: Michael <owner@example.com>\r\n"
                                                                  "Subject: test 123")}}},
                made={"id": "m1", "threadId": "t1"})
    out = gmail.send_self("r-1", token="t", call=fake.call, get=fake.get, mode=lambda c: "auto", state=tmp_path)
    assert out["sent"] and fake.calls == [("POST", gmail.GMAIL + "/drafts/send", {"id": "r-1"}, None)]


@pytest.mark.parametrize("headers", ["To: owner@example.com\r\nCc: jess@example.com",
                                     "To: owner@example.com\r\nBcc: x@y.com",
                                     "To: someone@example.com", "Subject: nobody"])
def test_send_self_refuses_anyone_else(tmp_path, headers):
    fake = Fake(reads={"/drafts/r-1": {"message": {"raw": _raw(headers)}}})
    with pytest.raises(GoogleError):
        gmail.send_self("r-1", token="t", call=fake.call, get=fake.get, mode=lambda c: "auto", state=tmp_path)
    assert not fake.calls


def test_send_self_needs_the_setting(tmp_path):
    with pytest.raises(GoogleError):
        gmail.send_self("r-1", token="t", call=Fake().call, get=Fake().get, mode=lambda c: "ask", state=tmp_path)


def test_card_path_auto_sends_to_michael_only(tmp_path):
    auto = {"actions": {"email.send.self": {"mode": "auto"}}}
    assert approval_policy.auto_ok({"action_class": "email.send", "to": ["owner@example.com"]}, tmp_path, auto)
    assert not approval_policy.auto_ok({"action_class": "email.send",
                                        "to": ["owner@example.com", "jess@example.com"]}, tmp_path, auto)


def test_second_reply_draft_in_a_thread_returns_the_first(tmp_path):
    fake = Fake(reads={"/messages/m1": {"threadId": "t1", "payload": {"headers": [
        {"name": "Subject", "value": "Dinner"}, {"name": "Message-ID", "value": "<a@x>"}]}}},
        made={"id": "r-1", "message": {"id": "m2", "threadId": "t1"}})
    log = tmp_path / "drafts.jsonl"
    gmail.draft(["sam@example.com"], [], "", "Yes.\n", "m1", "family (Sam)", token="t", call=fake.call,
                get=fake.get, log=log)
    again = gmail.draft(["sam@example.com"], [], "", "Yes!\n", "m1", "family (Sam)", token="t", call=fake.call,
                        get=fake.get, log=log)
    assert again["existing"] and again["draft_id"] == "r-1" and len(fake.calls) == 1
    gmail.draft(["sam@example.com"], [], "", "Also.\n", "m1", "family (Sam)", token="t", call=fake.call,
                get=fake.get, log=log, again=True)
    assert len(fake.calls) == 2
