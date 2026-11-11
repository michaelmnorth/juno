"""Discord as the channel (gateway/discord_transport.py, DV15): the Slack-shaped client, cards as components, taps
back into the same handlers. No network: a fake REST records every call."""
from __future__ import annotations

import json

import discord_transport as dt
import slack_bridge
from state_store import Approvals, SessionMap


class FakeRest:
    def __init__(self):
        self.calls = []
        self.n = 1000

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST" and path == "/users/@me/channels":
            return {"id": "DM-1"}
        if method == "POST":
            self.n += 1
            return {"id": str(self.n)}
        return {}


def client(tmp_path):
    return dt.DiscordClient(FakeRest(), dt.Registry(tmp_path / "state" / "discord-ui.json"))


CARD = [
    {"type": "header", "text": {"type": "plain_text", "text": "Reply to Jess"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "*Dinner Saturday?* <https://mail.example/d|Open draft>"}},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "known · draft unchanged"}]},
    {"type": "actions", "block_id": "ap:a-1", "elements": [
        {"type": "button", "action_id": "approve", "value": "a-1", "style": "primary",
         "text": {"type": "plain_text", "text": "Send"}},
        {"type": "button", "action_id": "edit_link", "url": "https://mail.example/d",
         "text": {"type": "plain_text", "text": "Edit in Gmail"}},
        {"type": "overflow", "action_id": "approval_more", "options": [
            {"text": {"type": "plain_text", "text": "Always send to her"}, "value": "always:a-1"},
            {"text": {"type": "plain_text", "text": "Skip"}, "value": "deny:a-1"}]}]},
]


def test_mrkdwn_becomes_discord_markdown():
    assert dt.to_markdown("*bold* and ~gone~ <https://x.io|link> <https://y.io>") == \
        "**bold** and ~~gone~~ [link](https://x.io) <https://y.io>"
    assert dt.to_markdown("`*code*` 2*3*4") == "`*code*` 2*3*4"
    assert dt.to_markdown("a &lt;b&gt; &amp; c") == "a <b> & c"


def test_reaction_names_become_unicode():
    assert dt.emoji_for("+1") == "👍" and dt.emoji_for("saluting_face") == "🫡"
    assert dt.emoji_for("no_such_emoji_name") == "👍"


def test_card_renders_as_components_inside_discords_limits(tmp_path):
    c = client(tmp_path)
    out = c.chat_postMessage(channel="DM-1", text="Reply to Jess", blocks=CARD)
    method, path, body = c.rest.calls[-1]
    assert (method, path) == ("POST", "/channels/DM-1/messages") and out["ts"] == "1001"
    assert body["flags"] == dt.IS_COMPONENTS_V2 and body["allowed_mentions"] == {"parse": []}
    comps = body["components"]
    assert dt._count(comps) <= dt.V2_MAX_COMPONENTS
    text = comps[0]["content"]
    assert "## Reply to Jess" in text and "**Dinner Saturday?**" in text and "-# known" in text
    rows = [x for x in comps if x["type"] == 1]
    buttons, menu = rows[0]["components"], rows[1]["components"][0]
    assert [b["label"] for b in buttons] == ["Send", "Edit in Gmail"]
    assert buttons[0]["style"] == 1 and buttons[1]["style"] == 5 and "custom_id" not in buttons[1]
    assert menu["type"] == 3 and [o["label"] for o in menu["options"]] == ["Always send to her", "Skip"]


def test_a_tap_comes_back_as_a_slack_body_after_a_restart(tmp_path):
    c = client(tmp_path)
    ts = c.chat_postMessage(channel="DM-1", text="Reply to Jess", blocks=CARD)["ts"]
    comps = c.rest.calls[-1][2]["components"]
    send_id = next(x for x in comps if x["type"] == 1)["components"][0]["custom_id"]
    menu_id = [x for x in comps if x["type"] == 1][1]["components"][0]["custom_id"]
    reg = dt.Registry(tmp_path / "state" / "discord-ui.json")  # a fresh process reads it back
    body = dt.action_body(custom_id=send_id, values=None, message_id=ts, channel_id="DM-1", user_id="U9", reg=reg)
    assert body["actions"][0] == {"action_id": "approve", "block_id": "ap:a-1", "value": "a-1"}
    assert body["message"]["blocks"] == CARD and body["user"]["id"] == "U9" and body["channel"]["id"] == "DM-1"
    pick = dt.action_body(custom_id=menu_id, values=["1"], message_id=ts, channel_id="DM-1", user_id="U9", reg=reg)
    assert pick["actions"][0]["selected_option"]["value"] == "deny:a-1"
    assert dt.action_body(custom_id="j:unknown", values=None, message_id=ts, channel_id="DM-1", user_id="U9",
                          reg=reg) is None


def test_plain_replies_split_at_2000_and_thread_replies_reference_the_card(tmp_path):
    c = client(tmp_path)
    c.chat_postMessage(channel="DM-1", text="x" * 4500, thread_ts="555")
    posts = [b for m, p, b in c.rest.calls if m == "POST"]
    assert len(posts) == 3 and all(len(b["content"]) <= 2000 for b in posts)
    assert all(b["message_reference"]["message_id"] == "555" for b in posts)
    assert all(b["flags"] == dt.SUPPRESS_EMBEDS for b in posts)  # no link previews


def test_updates_reactions_dm_and_permalinks(tmp_path):
    c = client(tmp_path)
    ts = c.chat_postMessage(channel="DM-1", text="card", blocks=CARD)["ts"]
    c.chat_update(channel="DM-1", ts=ts, text="Done")  # a components card stays one
    m, p, b = c.rest.calls[-1]
    assert (m, p) == ("PATCH", f"/channels/DM-1/messages/{ts}") and b["flags"] == dt.IS_COMPONENTS_V2
    c.reactions_add(channel="DM-1", timestamp=ts, name="eyes")
    assert c.rest.calls[-1][:2] == ("PUT", f"/channels/DM-1/messages/{ts}/reactions/%F0%9F%91%80/@me")
    c.chat_delete(channel="DM-1", ts=ts)
    assert c.rest.calls[-1][:2] == ("DELETE", f"/channels/DM-1/messages/{ts}")
    assert c.conversations_open(users=["U9"])["channel"]["id"] == "DM-1"
    c.conversations_open(users=["U9"])
    assert sum(1 for m, p, _ in c.rest.calls if p == "/users/@me/channels") == 1  # cached
    assert c.chat_getPermalink(channel="DM-1", message_ts=ts)["permalink"].endswith(f"/@me/DM-1/{ts}")


def test_big_cards_are_trimmed_to_forty_components(tmp_path):
    blocks = []
    for i in range(30):
        blocks += [{"type": "section", "block_id": f"pq:{i}", "text": {"type": "mrkdwn", "text": f"note {i}"}},
                   {"type": "actions", "block_id": f"pqa:{i}", "elements": [
                       {"type": "button", "action_id": "people_save", "value": str(i), "text": {"text": "Save"}}]},
                   {"type": "divider"}]
    comps = dt.render_blocks(blocks, dt.Registry(tmp_path / "r.json"))
    assert dt._count(comps) <= dt.V2_MAX_COMPONENTS


def test_dm_event_has_the_slack_shape_and_photos_download_from_discord_only(tmp_path):
    ev = dt.message_event(message_id="1290000000000000000", channel_id="DM-1", author_id="U9", content="look",
                          attachments=[{"id": 7, "content_type": "image/png", "url": "https://cdn.discordapp.com/a/7.png",
                                        "size": 10, "filename": "p.png"},
                                       {"id": 8, "content_type": "image/png", "url": "https://evil.example/8.png",
                                        "size": 10, "filename": "q.png"}])
    assert ev["channel_type"] == "im" and ev["subtype"] == "file_share" and ev["sent_at"] > 1.4e9
    saved = slack_bridge.save_images(ev, "", tmp_path, fetch=lambda url: b"\x89PNG", hosts=dt.FILE_HOSTS)
    assert list(saved) == ["7"] and (tmp_path / saved["7"]).exists()


def test_every_bridge_handler_runs_on_the_discord_app(tmp_path, monkeypatch):
    monkeypatch.setattr(slack_bridge, "load_allowlist", lambda root, channel=None: {"U9"})
    bridge = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                                 approvals=Approvals(tmp_path / "a.json"), runner=lambda *a, **k: None)
    c = client(tmp_path)
    app = slack_bridge.build_app(bridge, dt.App(c))
    for action in ("approve", "deny", "approval_more", "reask", "drop", "people_save", "lesson_save", "vault_check",
                   "vault_skip", "status_more", "answer_3", "brief_tap", "idea_draft"):
        assert app.handler_for(action), action
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "vault-requests.json").write_text(json.dumps({"requests": [
        {"id": "v-1", "item": "Discord-Juno", "fields": [{"name": "bot_token", "secret": True}], "why": "x",
         "status": "posted", "created": "2026-11-11T00:00:00+00:00"}]}), encoding="utf-8")
    card = [{"type": "section", "text": {"type": "mrkdwn", "text": "Fill it in"}},
            {"type": "actions", "block_id": "vault:v-1", "elements": [
                {"type": "button", "action_id": "vault_skip", "value": "v-1", "text": {"text": "Skip"}}]}]
    ts = c.chat_postMessage(channel="DM-1", text="Fill it in", blocks=card)["ts"]
    cid = next(x for x in c.rest.calls[-1][2]["components"] if x["type"] == 1)["components"][0]["custom_id"]
    body = dt.action_body(custom_id=cid, values=None, message_id=ts, channel_id="DM-1", user_id="U9", reg=c.registry)
    assert app.dispatch_action(body)
    assert json.loads((state / "vault-requests.json").read_text(encoding="utf-8"))["requests"][0]["status"] == "skipped"
    assert c.rest.calls[-1][:2] == ("PATCH", f"/channels/DM-1/messages/{ts}")


def test_channel_setting_and_allowlist_per_app(tmp_path):
    assert slack_bridge.load_channel(tmp_path) == "slack"
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "channel.yaml").write_text("channel: discord\n", encoding="utf-8")
    (tmp_path / "me" / "notify-allowlist.json").write_text(json.dumps({"slack": ["U1"], "discord": ["999"]}),
                                                          encoding="utf-8")
    assert slack_bridge.load_channel(tmp_path) == "discord"
    assert slack_bridge.load_allowlist(tmp_path) == {"999"}
    assert slack_bridge.load_allowlist(tmp_path, "slack") == {"U1"}
