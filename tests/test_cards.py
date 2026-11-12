"""Screens 4 to 6 (gateway/cards.py): status, evening check-in, Sunday reflection, Home tab."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

import cards  # noqa: E402
import slack_bridge  # noqa: E402

NOW = datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc)  # 2 PM Eastern, a Sunday
CFG = {"anchors": {"morning_brief": "07:00", "evening_checkin": "20:30"}, "unprompted_pings_per_day": 5}


def world(tmp_path: Path, *, failed: bool = False, waiting: int = 1) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    runs = {"sweep": {"at": "2026-11-08T18:20:00+00:00", "ok": True},
            "morning-brief": {"at": "2026-11-08T12:00:00+00:00", "ok": not failed}}
    (state / "last-run.json").write_text(json.dumps(runs), encoding="utf-8")
    pending = [{"id": f"a-0000000{i}", "summary": f"sample-{i} waiting", "status": "posted", "slack_ts": f"{i}.5"}
               for i in range(waiting)] + [{"id": "a-done0000", "summary": "old", "status": "approved"}]
    (state / "pending-approvals.json").write_text(json.dumps({"pending": pending}), encoding="utf-8")
    costs = [{"at": "2026-11-08T13:00:00+00:00", "cost_usd": 0.25}, {"at": "2026-11-03T13:00:00+00:00", "cost_usd": 1.0,
                                                                    "is_error": True}]
    (state / "costs.jsonl").write_text("\n".join(json.dumps(c) for c in costs), encoding="utf-8")
    (state / "pinged.json").write_text(json.dumps({"days": {"2026-11-08": 2}}), encoding="utf-8")
    return tmp_path


def texts(blocks: list[dict]) -> str:
    return json.dumps(blocks)


# --- status ---------------------------------------------------------------------------------------

def test_status_grid_reads_state(tmp_path):
    msg = cards.status_blocks(world(tmp_path), CFG, NOW)
    assert msg.text == "All running"
    grid = texts(msg.blocks)
    assert "40 min ago" in grid and "Check-in 8:30 PM" in grid and "2 of 5" in grid and "$0.25" in grid
    actions = msg.blocks[-1]["elements"]
    assert actions[0]["action_id"] == "status_show" and actions[0]["text"]["text"] == "Show the 1"
    assert [o["value"] for o in actions[1]["options"]] == ["sweep"]


def test_status_names_problems_and_offers_why(tmp_path):
    msg = cards.status_blocks(world(tmp_path, failed=True, waiting=0), CFG, NOW)
    assert msg.text == "1 problem"
    actions = msg.blocks[-1]["elements"]
    assert actions[0]["type"] == "overflow"  # nothing waiting: no Show button
    assert [o["value"] for o in actions[0]["options"]] == ["sweep", "why:morning-brief"]


def test_next_anchor_rolls_to_tomorrow():
    late = datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc)  # 9 PM Eastern
    assert cards.next_anchor(CFG, late) == "Brief 7:00 AM tomorrow"


# --- evening check-in -----------------------------------------------------------------------------

CHECKIN = "Here it is.\n" + json.dumps({
    "headline": "Tomorrow starts at 9:30",
    "tomorrow": [{"time": "9:30", "text": "sample-dentist", "prep": "Bring the card", "button": "prep"}],
    "still_open": [{"text": "sample-draft to sample-friend", "button": "review"}],
    "quiet_mail": ["sample newsletter", "sample receipt"],
    "remembered": [{"text": "sample habit", "seen": "Seen 3 times"}],
    "question": {"text": "Trained today?", "answers": ["Trained", "Rest day", "Skipped", "Fourth"]}})


def test_checkin_rows_and_answers():
    msg = cards.checkin(CHECKIN)
    assert msg.text == "Tomorrow starts at 9:30"
    body = texts(msg.blocks)
    assert "Quiet mail: 2" in body and "Show 2" in body and "Bring the card" in body
    answers = msg.blocks[-1]["elements"]
    assert [b["action_id"] for b in answers] == ["answer_0", "answer_1", "answer_2"]  # capped at 3
    assert json.loads(answers[1]["value"]) == {"q": "Trained today?", "a": "Rest day"}
    assert answers[0]["style"] == "primary" and "style" not in answers[1]


def test_checkin_without_json_is_text():
    msg = cards.checkin("**Quiet** night.")
    assert msg.blocks is None and msg.text == "*Quiet* night."


def test_answer_prompt():
    assert cards.answer_prompt("Trained today?", "Rest day").endswith("Question: Trained today?\nMy answer: Rest day")


# --- reflection -----------------------------------------------------------------------------------

def change(i: int, target: str = "learnings/drafter.md") -> dict:
    return {"id": f"p-{i}", "target": target, "old_line": "old" if i == 0 else "", "new_line": f"- sample lesson {i}",
            "evidence": "You edited 3 drafts"}


def reflection_reply(n: int = 2) -> str:
    return json.dumps({"title": "Your week, Nov 2 to 8", "summary": {"runs": "41 (2 failed)", "blocked": 3, "spent": "$4.10"},
                       "changes": [change(i) for i in range(n)],
                       "watching": {"themes": "agents", "ideas": ["sample idea"]},
                       "coming_up": [{"text": "sample birthday in 6 days", "note": "gray", "button": "ideas"}]})


def test_reflection_changes_have_save_skip_reword():
    first, coming = cards.reflection(reflection_reply())
    assert first.text == "Your week, Nov 2 to 8: 2 changes to review"
    acts = [b for b in first.blocks if b["type"] == "actions" and b["elements"][0]["action_id"] == "lesson_save"]
    assert len(acts) == 2
    save = json.loads(acts[0]["elements"][0]["value"])
    assert save == {"id": "p-0", "target": "learnings/drafter.md", "old": "old", "new": "- sample lesson 0"}
    assert acts[0]["elements"][2]["options"][0]["value"] == "reword"
    assert "Quill (drafts)" in texts(first.blocks) and "idea_draft" in texts(first.blocks)
    diff = next(b for b in first.blocks if b["type"] == "rich_text")["elements"][0]["elements"][0]["text"]
    assert diff == "- old\n+ sample lesson 0"  # no "+ - " double marker
    assert coming.text == "Coming up" and coming.blocks[1]["accessory"]["text"]["text"] == "Gift ideas"


def test_reflection_stays_under_50_blocks_and_threads_the_rest():
    first, _ = cards.reflection(reflection_reply(20))
    assert len(first.blocks) <= 50
    shown = sum(1 for b in first.blocks if b["type"] == "actions" and b["elements"][0]["action_id"] == "lesson_save")
    assert shown < 20 and len(first.thread) == 20 - shown
    assert f"{20 - shown} more in the thread" in texts(first.blocks)


def test_agent_label():
    assert cards.agent_label("learnings/relationships.md") == "Kin (people)"
    assert cards.agent_label("me/voice.md") == "You"
    assert cards.agent_label("people/linda-rivera.md") == "Linda Rivera"
    assert cards.agent_label("domains/health/CONTEXT.md") == "Health context"


def test_lesson_prompts_say_what_the_tap_means():
    c = {"id": "p-1", "target": "learnings/drafter.md", "old": "", "new": "- x"}
    assert "this tap is my yes" in cards.lesson_prompt("save", c)
    assert "Do not write it" in cards.lesson_prompt("skip", c)
    assert "how I'd word it" in cards.lesson_prompt("reword", c)


# --- Home tab -------------------------------------------------------------------------------------

def test_home_view(tmp_path):
    root = world(tmp_path, waiting=2)
    (root / "observed").mkdir()
    (root / "observed" / "changelog.md").write_text(
        "# log\n- 2026-11-07 | preferences.md | add | sample preference | Slack\n", encoding="utf-8")
    view = cards.home_view(root, CFG, {"a-00000000": "https://slack.example/p1"}, NOW)
    assert view["type"] == "home" and len(view["blocks"]) <= 100
    body = texts(view["blocks"])
    assert "Easy afternoon. 2 for you." in body and "Sample preference" in body and "Sunday, November 8" in body
    opens = [b["accessory"] for b in view["blocks"] if b.get("accessory", {}).get("action_id") == "home_open"]
    assert len(opens) == 1 and opens[0]["url"] == "https://slack.example/p1"  # no link, no button


class HomeClient:
    def __init__(self):
        self.views = []

    def conversations_open(self, users):
        return {"channel": {"id": "D1"}}

    def chat_getPermalink(self, channel, message_ts):
        return {"permalink": f"https://slack.example/{channel}/{message_ts}"}

    def views_publish(self, user_id, view):
        self.views.append((user_id, view))


def test_photo_message_reaches_juno():
    # 2026-11-08: a DM with a photo arrives as subtype file_share and was dropped, so the shadow box went unanswered
    assert "file_share" in slack_bridge.DM_SUBTYPES and None in slack_bridge.DM_SUBTYPES
    assert "message_changed" not in slack_bridge.DM_SUBTYPES
    event = {"ts": "1794164938.236029", "text": "Made him a shadow box", "files": [
        {"id": "F1", "name": "IMG_0313.jpg", "mimetype": "image/jpeg", "size": 1600,
         "url_private_download": "https://files.slack.com/files-pri/T/F1/download/img_0313.jpg"},
        {"id": "F2", "name": "notes.pdf", "mimetype": "application/pdf", "url_private": "https://files.slack.com/x"}]}
    text = slack_bridge.dm_text(event, {"F1": "state/attachments/1794164938-236029-0.jpg"})
    assert text == ("Made him a shadow box\n[He attached a photo, saved at state/attachments/1794164938-236029-0.jpg. "
                    "Read it to see it.]\n[He attached notes.pdf, which you can't open. Mention that in one clause only "
                    "if it matters.]")
    assert slack_bridge.dm_text({"text": "hi"}) == "hi"


def test_save_files_keeps_photos_and_readable_files(tmp_path):
    event = {"ts": "17.5", "files": [
        {"id": "F1", "mimetype": "image/jpeg", "url_private_download": "https://files.slack.com/a.jpg"},
        {"id": "F2", "mimetype": "application/pdf", "url_private_download": "https://files.slack.com/b.pdf"},
        {"id": "F3", "mimetype": "image/png", "url_private_download": "https://evil.example/c.png"},
        {"id": "F4", "mimetype": "image/png", "url_private_download": "https://files.slack.com/login.png"}]}
    fetched = []

    def fetch(url):
        fetched.append(url)
        return b"<html>sign in</html>" if "login" in url else b"\xff\xd8jpeg"
    saved = slack_bridge.save_images(event, "t", tmp_path, fetch=fetch)
    # PDFs are readable since P2; still no foreign host and no HTML sign-in page
    assert saved == {"F1": "state/attachments/17-5-0.jpg", "F2": "state/attachments/17-5-1.pdf"}
    assert (tmp_path / saved["F1"]).read_bytes() == b"\xff\xd8jpeg"
    assert fetched == ["https://files.slack.com/a.jpg", "https://files.slack.com/b.pdf",
                       "https://files.slack.com/login.png"]


class DMClient(HomeClient):
    def __init__(self):
        super().__init__()
        self.posts, self.reactions = [], []

    def chat_postMessage(self, **kw):
        self.posts.append(kw)
        return {"ts": "9.0"}

    def reactions_add(self, **kw):
        self.reactions.append(kw)


def test_home_word_posts_home_view_without_claude(tmp_path):
    from state_store import Approvals
    root = world(tmp_path, waiting=1)

    class B:
        def allowed(self, user):
            return user == "U1"

        def handle_dm(self, *a):
            raise AssertionError("no Claude run for 'home'")
    bridge = B()
    bridge.root, bridge.approvals = root, Approvals(root / "state" / "pending-approvals.json")
    client = DMClient()
    slack_bridge.answer_batch(client, bridge, "D1", [{"ts": "1.0", "user": "U1", "text": "Home"}])
    post = client.posts[0]
    assert post["text"].endswith("1 for you.") and "https://slack.example/D1/0.5" in texts(post["blocks"])


def test_home_tab_is_off():
    manifest = (ROOT / "gateway" / "slack-app-manifest.yaml").read_text(encoding="utf-8")
    assert "home_tab_enabled: false" in manifest and "app_home_opened" not in manifest
    assert "files:read" in manifest and not hasattr(slack_bridge, "publish_home")
