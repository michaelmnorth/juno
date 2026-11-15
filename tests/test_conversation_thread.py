"""The two Discord bugs of 2026-11-13, offline.

1. Losing the thread: a sweep ping asked "did you set them up?", Michael answered "I did", and the reply went back to
   what the DM had been about before. Timer messages never reached either engine's view of the conversation.
2. The working line ("On it. 🫡") went up on every DM, even mid-conversation, and never said what it was about.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import slack_bridge  # noqa: E402
from state_store import Approvals, SessionMap  # noqa: E402
from test_v2 import FakeBackend, FakeClient, final, route_resp  # noqa: E402
from v2 import converse  # noqa: E402
from v2.converse import Engine  # noqa: E402
from v2.store import Store  # noqa: E402

PING = ("Two sign-in notices from Example Bank name no app; the other two look like your own setup. "
        "Did you set them up?")


def engine(tmp_path, script):
    client = FakeClient(script)
    e = Engine(tmp_path, FakeBackend(), store=Store(tmp_path / "state" / "v2.db"), client_factory=lambda: client)
    return e, client


# --- 1. timer messages are part of the conversation ---------------------------------------------------------

def test_short_answer_after_a_ping_sees_the_ping(tmp_path):
    e, client = engine(tmp_path, [route_resp("general", needs_tools=False), final("Good, then nothing to do.")])
    e.store.add_turn("C1", "user", "pin the start here channel", "r-1")
    e.store.add_turn("C1", "assistant", "Done, start here is pinned.", "r-1")
    e.note_outbound("C1", PING, "sweep")
    e.handle("C1", "I did", "C1:1")
    router_req, converse_req = client.requests
    assert "Did you set them up?" in router_req["messages"][0]["content"]  # the router knows what he's answering
    body = converse_req["messages"][0]["content"]
    assert body.index("Did you set them up?") > body.index("start here is pinned")  # newest last, after the old topic
    assert "Michael's message:\nI did" in body


def test_ping_taints_the_run_but_not_the_thread(tmp_path):
    e, _ = engine(tmp_path, [route_resp("general", needs_tools=False), final("Noted.")])
    e.note_outbound("C1", PING, "sweep")
    e.handle("C1", "I did", "C1:1")
    assert not e.store.thread("C1")["tainted"]  # the next sweep would otherwise keep every DM tainted all day


def test_long_outbound_keeps_its_last_line():
    brief = "Morning. " + "x" * 3000 + " Want me to move the 4pm?"
    clipped = converse.clip_outbound(brief)
    assert len(clipped) <= converse.OUTBOUND_MAX + 5 and clipped.endswith("Want me to move the 4pm?")


def test_unanswered_lines_stop_at_his_last_message(tmp_path):
    e, _ = engine(tmp_path, [])
    e.note_outbound("C1", "Old ping he already answered", "sweep")
    e.store.add_turn("C1", "user", "thanks", "")
    e.note_outbound("C1", "[react:wink] " + PING, "sweep")
    lines = e.unanswered_lines("C1")
    assert "Did you set them up?" in lines and "Old ping" not in lines and "[react" not in lines
    assert "You, in a scheduled message" in e.recent_lines("C1")


def test_post_to_michael_records_the_message(tmp_path):
    seen = []

    class Client:
        def conversations_open(self, users):
            return {"channel": {"id": "D1"}}

        def chat_postMessage(self, channel, text, blocks=None, thread_ts=None):
            return {"ts": "9.0"}

    bridge = NS(allowlist={"U1"}, note_outbound=lambda c, t, s: seen.append((c, t, s)))
    slack_bridge.post_job(Client(), bridge, "sweep", PING)
    assert seen == [("D1", PING, "sweep")]
    assert slack_bridge.mid_conversation("D1")  # his answer to it gets no "On it" line


def test_v1_prompt_carries_the_unanswered_ping(tmp_path, monkeypatch):
    class OnlyV1:  # a chat pinned to v1: the old session never saw the timer's message
        def __init__(self):
            self.store = Store(tmp_path / "state" / "v2.db")
            self.store.set_engine("D1", "v1")

        def unanswered_lines(self, channel):
            return "- (17:01 UTC) " + PING

    calls = []
    monkeypatch.setattr(slack_bridge, "load_allowlist", lambda root, channel=None: {"U1"})
    monkeypatch.setattr(slack_bridge, "heartbeat", lambda *a, **k: None)
    b = slack_bridge.Bridge(root=tmp_path, sessions=SessionMap(tmp_path / "s.json"),
                            approvals=Approvals(tmp_path / "a.json"), v2_engine=OnlyV1(),
                            runner=lambda p, **k: calls.append(p) or NS(text="ok", session_id="s", is_error=False,
                                                                        raw={}))
    b.handle_dm("D1", "U1", "I did")
    assert "Did you set them up?" in calls[0] and "don't change the subject" in calls[0]
    assert calls[0].index("Did you set them up?") < calls[0].index("DM from Michael]\nI did")


# --- 2. the working line --------------------------------------------------------------------------------------

class Slack:
    def __init__(self):
        self.posts, self.typing_in, self.reactions = [], [], []

    def chat_postMessage(self, channel, text):
        self.posts.append(text)
        return {"ts": f"w{len(self.posts)}"}

    def chat_delete(self, channel, ts):
        pass

    def reactions_add(self, channel, timestamp, name):
        self.reactions.append(name)

    def typing(self, channel):
        self.typing_in.append(channel)


def test_first_message_gets_a_working_line_named_for_its_topic():
    s = Slack()
    slack_bridge.acknowledge(s, "D1", "1.0", text="can you look at my grocery list")
    assert "grocery" in s.posts[0].lower() and s.reactions == ["eyes"]
    slack_bridge._working_for.pop("D1", None)


def test_mid_conversation_gets_typing_not_a_line():
    s = Slack()
    slack_bridge.note_exchange("D1")
    slack_bridge.acknowledge(s, "D1", "2.0", text="ok and tomorrow?")
    assert s.posts == [] and s.typing_in == ["D1"] and s.reactions == ["eyes"]
    slack_bridge._working_for.pop("D1", None)


def test_after_a_quiet_gap_the_line_comes_back():
    s = Slack()
    slack_bridge.note_exchange("D1", datetime.now(timezone.utc) - timedelta(minutes=30))
    slack_bridge.acknowledge(s, "D1", "3.0", text="hey")
    assert len(s.posts) == 1 and s.posts[0].strip("_") in slack_bridge.WORKING_LINES
    slack_bridge._working_for.pop("D1", None)


def test_mid_conversation_reply_posts_only_the_answer(tmp_path, monkeypatch):
    s = Slack()
    slack_bridge.note_exchange("D2")
    slack_bridge.acknowledge(s, "D2", "4.0", text="yes do it")
    bridge = NS(allowed=lambda u: True, handle_dm=lambda *a, **k: "Done. 🫡", root=tmp_path)
    monkeypatch.setattr(slack_bridge, "post_people", lambda *a, **k: None)
    slack_bridge.answer_batch(s, bridge, "D2", [{"ts": "4.0", "user": "U1", "text": "yes do it"}])
    assert s.posts == ["Done. 🫡"]


def test_topic_lines_never_name_juno():
    lines = [l for _, ls in slack_bridge.TOPIC_LINES for l in ls]
    assert lines and not any("juno" in l.lower() for l in lines)


def test_discord_typing_hits_the_typing_endpoint():
    from discord_transport import DiscordClient, Registry
    calls = []
    c = DiscordClient(lambda m, p, b=None: calls.append((m, p)) or {}, Registry.__new__(Registry))
    c.typing(channel="123")
    assert calls == [("POST", "/channels/123/typing")]


def test_cli_runs_never_inherit_an_api_key(monkeypatch):
    """With an API key in its environment, Claude Code silently bills the API instead of the Max plan login."""
    import claude_runner
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-test")
    monkeypatch.setenv("JUNO_V2_API_KEY", "sk-test")
    env = claude_runner.child_env()
    assert not {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "JUNO_V2_API_KEY"} & set(env)
