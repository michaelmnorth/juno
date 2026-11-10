"""Offline tests for the morning brief card and the Markdown-to-mrkdwn fix (docs/13 section 1, docs/14)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

import brief_blocks  # noqa: E402
import slack_bridge  # noqa: E402

BRIEF = {
    "headline": "Tuesday. Light day.",
    "counts": "3 need you · 2 events · slept 7h 05m",
    "needs_you": [
        {"text": "Dana asked about Saturday. Reply drafted.", "button": "review"},
        {"text": "Electric bill due Thursday, $84.", "button": "remind"},
        {"text": "Mom's birthday in 6 days.", "button": "ideas"},
        {"text": "Gym membership renews Friday.", "button": "remind"},
        {"text": "Approval from yesterday still waiting.", "button": "open"},
    ],
    "today": [
        {"time": "12:30", "text": "Lunch with Dana, Juniper Cafe", "prep": "Leave by 12:05. Ask about the move.",
         "button": "directions", "url": "https://maps.google.com/?q=Juniper+Cafe"},
        {"time": "17:30", "text": "Squat day", "prep": "", "button": "workout"},
    ],
    "busy": ["2 newsletters", "1 receipt from Hevy"],
    "remembered": [{"text": "You cut greetings on business drafts.", "seen": "Seen 2 times · from your sent drafts"}],
    "watching": "Two videos on agent memory; one idea for Juno saved to notes.",
}


def reply(data=BRIEF, before="Here is today.\n\n") -> str:
    return before + json.dumps(data)


def actions(blocks):
    return [b["accessory"] for b in blocks if "accessory" in b]


# --- to_mrkdwn ------------------------------------------------------------------------------------

def test_mrkdwn_bold_strike_link_heading():
    out = brief_blocks.to_mrkdwn("# Today\n**Groupon x2**: ~~old~~ see [the draft](https://mail.google.com/x)")
    assert out == "*Today*\n*Groupon x2*: ~old~ see <https://mail.google.com/x|the draft>"


def test_mrkdwn_leaves_code_alone():
    text = "Run `**not bold**` then\n```\n**still code**\n```\n**bold**"
    out = brief_blocks.to_mrkdwn(text)
    assert "`**not bold**`" in out and "**still code**" in out and out.endswith("*bold*")


def test_mrkdwn_single_asterisks_untouched():
    assert brief_blocks.to_mrkdwn("*already slack* and 2 * 3") == "*already slack* and 2 * 3"


# --- parse and render -----------------------------------------------------------------------------

def test_parse_takes_last_object_with_headline():
    text = 'Note {"x": 1} then ' + json.dumps({"headline": "Hi"})
    assert brief_blocks.parse_brief(text) == {"headline": "Hi"}
    assert brief_blocks.parse_brief("no json here") is None
    assert brief_blocks.parse_brief('{"headline": ""}') is None


def test_broken_json_falls_back_to_text():
    msg = brief_blocks.render("Light day.\n**2 bills**\n{\"headline\": ")
    assert msg.blocks is None and "*2 bills*" in msg.text


def test_order_and_shape():
    msg = brief_blocks.render(reply())
    types = [b["type"] for b in msg.blocks]
    assert types[0] == "header" and msg.blocks[0]["text"]["text"] == "Tuesday. Light day."
    assert types[1] == "context"
    texts = [b.get("text", {}).get("text", "") for b in msg.blocks if b["type"] == "section"]
    assert texts.index("*Needs you*") < texts.index("*Today*") < next(i for i, t in enumerate(texts) if "busy" in t)
    assert msg.text == "Tuesday. Light day. 5 need you."
    assert len(msg.blocks) <= brief_blocks.MAX_BLOCKS


def test_brief_has_no_buttons():
    msg = brief_blocks.render(reply())
    assert actions(msg.blocks) == [] and not any(b["type"] == "actions" for b in msg.blocks)


def test_needs_capped_rest_in_thread():
    data = dict(BRIEF, needs_you=[{"text": f"Item {i}"} for i in range(1, 9)])
    msg = brief_blocks.render(reply(data))
    rows = [b for b in msg.blocks if b["type"] == "section" and b["text"]["text"][:5].startswith(tuple(f"{i}." for i in range(1, 9)))]
    assert len(rows) == brief_blocks.MAX_NEEDS == 6
    assert any(b["type"] == "context" and "and 2 more" in b["elements"][0]["text"] for b in msg.blocks)
    assert msg.thread == ["7. Item 7", "8. Item 8"]


def test_gmail_and_directions_are_inline_links():
    data = dict(BRIEF, needs_you=[{"text": "Wells Fargo alert at 6:25.", "url": "https://mail.google.com/mail/u/0/#all/abc"}])
    texts = [b["text"]["text"] for b in brief_blocks.render(reply(data)).blocks if b["type"] == "section"]
    assert "1. Wells Fargo alert at 6:25. <https://mail.google.com/mail/u/0/#all/abc|Open in Gmail>" in texts
    assert any(t.endswith("<https://maps.google.com/?q=Juniper+Cafe|Directions>") for t in texts)


def test_bad_urls_make_no_link():
    data = dict(BRIEF, needs_you=[{"text": "Odd one", "url": "https://evil.example/x"}],
                today=[{"time": "9:00", "text": "Dentist", "url": "javascript:x"},
                       {"time": "10:00", "text": "Gym", "url": "https://maps.google.com/?q=a|b"}])
    texts = [b["text"]["text"] for b in brief_blocks.render(reply(data)).blocks if b["type"] == "section"]
    assert "1. Odd one" in texts and "*9:00* Dentist" in texts and "*10:00* Gym" in texts


def test_unknown_button_kind_is_ignored():
    data = {"headline": "Day.", "needs_you": [{"text": "Something", "button": "send_money"}]}
    blocks = brief_blocks.render(reply(data)).blocks
    assert actions(blocks) == [] and "send_money" not in json.dumps(blocks)


def test_busy_and_picked_up_are_listed():
    texts = [b["text"]["text"] for b in brief_blocks.render(reply()).blocks if b["type"] == "section"]
    assert "*While you were busy*\n• 2 newsletters\n• 1 receipt from Hevy" in texts
    assert "*Picked up*\n• You cut greetings on business drafts." in texts


def test_limits_header_and_block_count():
    data = dict(BRIEF, headline="x" * 400, today=[{"time": f"{h}:00", "text": "Event", "prep": "p"} for h in range(40)])
    msg = brief_blocks.render(reply(data))
    assert len(msg.blocks[0]["text"]["text"]) <= brief_blocks.HEADER_MAX
    assert len(msg.blocks) <= brief_blocks.MAX_BLOCKS


def test_empty_sections_are_left_out():
    msg = brief_blocks.render(reply({"headline": "Quiet day."}))
    assert [b["type"] for b in msg.blocks] == ["header"] and msg.thread == []


def test_tap_prompt_names_the_row():
    p = brief_blocks.tap_prompt("prep", "*12:30* Lunch with Dana")
    assert p.startswith("[Tapped Prep me on a Juno message]") and "Lunch with Dana" in p


# --- bridge wiring --------------------------------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.posts = []

    def conversations_open(self, users):
        return {"channel": {"id": "D1"}}

    def chat_postMessage(self, **kw):
        self.posts.append(kw)
        return {"ts": f"{len(self.posts)}.0"}


class FakeBridge:
    allowlist = {"U1"}


def test_post_job_brief_posts_card_then_thread():
    client = FakeClient()
    data = dict(BRIEF, needs_you=[{"text": f"Item {i}"} for i in range(1, 8)])
    slack_bridge.post_job(client, FakeBridge(), "morning-brief", reply(data))
    assert client.posts[0]["blocks"][0]["type"] == "header"
    assert client.posts[1]["thread_ts"] == "1.0" and client.posts[1]["text"].startswith("7. ")


def test_post_drafts_moves_waiting_reply_cards_under_the_brief(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import state_store
    now = datetime.now(timezone.utc)
    store = state_store.Approvals(tmp_path / "pending-approvals.json")
    entries = [
        {"id": "a-00000001", "action_class": "email.send", "status": "posted", "slack_ts": "9.0",
         "summary": "Reply to Sam", "created": now.isoformat()},
        {"id": "a-00000002", "action_class": "email.send", "status": "posted", "slack_ts": "8.0",
         "summary": "Old reply", "created": (now - timedelta(days=9)).isoformat()},
        {"id": "a-00000003", "action_class": "calendar.event.create", "status": "posted", "slack_ts": "7.0",
         "summary": "Invite", "created": now.isoformat()},
    ]
    (tmp_path / "pending-approvals.json").write_text(json.dumps({"pending": entries}), encoding="utf-8")
    monkeypatch.setattr(slack_bridge, "approval_blocks", lambda entry, root=None: [{"type": "section"}])
    monkeypatch.setattr(slack_bridge.approval_policy, "card_text", lambda entry: entry["summary"])

    class Client(FakeClient):
        def __init__(self):
            super().__init__()
            self.updates = []

        def chat_update(self, **kw):
            self.updates.append(kw)

    class B(FakeBridge):
        approvals = store
        root = tmp_path

    client = Client()
    assert slack_bridge.post_drafts(client, B()) == 1
    assert [p["text"] for p in client.posts] == ["Reply to Sam"]
    assert client.updates[0]["ts"] == "9.0" and "Moved under" in client.updates[0]["text"]
    assert store.get("a-00000001")["slack_ts"] == "1.0"


def test_bot_messages_never_unfurl():
    class Client:
        def chat_postMessage(self, **kw):
            return kw

    slack_bridge.no_unfurl(Client)
    slack_bridge.no_unfurl(Client)  # patching twice changes nothing
    sent = Client().chat_postMessage(channel="D1", text="<https://evil.example/x.png|look>")
    assert sent["unfurl_links"] is False and sent["unfurl_media"] is False and sent["channel"] == "D1"


def test_post_job_other_jobs_stay_text_with_mrkdwn():
    client = FakeClient()
    slack_bridge.post_job(client, FakeBridge(), "evening-checkin", "**Tomorrow** is light.")
    assert client.posts == [{"channel": "D1", "text": "*Tomorrow* is light."}]


def test_brief_prompt_asks_for_json():
    prompt = slack_bridge.JOB_PROMPTS["morning-brief"]
    assert '"headline"' in prompt and '"needs_you"' in prompt and "nothing after it" in prompt
    assert '"button"' not in prompt and "no buttons" in prompt
