"""Morning brief as Block Kit (docs/13 section 1), plus the Markdown-to-Slack fix every plain reply goes through.

The morning-brief job ends its reply with one JSON object (schema in slack_bridge.JOB_PROMPTS). `render` turns it into
blocks in this order: headline, counts, Needs you (numbered lines, Gmail as an inline link), Today (events, prep as a
gray line, directions as a link), While you were busy, Picked up, From your watching. No buttons (Michael
2026-11-09); reply drafts follow as their own Send cards. A reply without valid JSON falls back to plain
text, so a model slip never loses the brief. Limits from docs/14: 50 blocks, 150-character header, 3,000-character
sections, short button labels.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MAX_BLOCKS = 50
MAX_NEEDS = 6
MAX_BUSY = 6
MAX_REMEMBERED = 3
HEADER_MAX = 150
SECTION_MAX = 3000
BUTTON_MAX = 30
VALUE_MAX = 1900

# Buttons that start a short Claude run in the thread (slack_bridge on_brief_tap). The brief has none since
# 2026-11-09; the evening check-in and briefs already in Slack still use them. "Show", "Directions" and
# "Open in Gmail" never reach Claude: Show posts the held-back list from the button's own value, the other two are
# links. Labels say where the answer lands: "Open" read as "open my inbox" and only replied in the thread
# (Michael 2026-11-09), so a button that answers in the thread never says Open.
TAP_KINDS = {"review", "remind", "ideas", "open", "prep", "workout", "undo", "draft_hi", "details"}
LABELS = {"review": "See draft", "remind": "Remind me", "ideas": "Gift ideas", "open": "Show again",
          "prep": "Prep me", "workout": "Today's lift", "undo": "Undo", "directions": "Directions",
          "draft_hi": "Draft hi", "details": "Tell me more", "gmail": "Open in Gmail"}
GMAIL = "https://mail.google.com/"
LINKS = {"directions": ("https://",), "gmail": (GMAIL,)}


@dataclass
class Message:
    text: str                       # notification and fallback text
    blocks: list[dict] | None       # None: post `text` as plain mrkdwn
    thread: list[str] = field(default_factory=list)  # lines posted as one reply in the thread (Needs you overflow)


# --- Markdown to Slack mrkdwn ---------------------------------------------------------------------

_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def to_mrkdwn(text: str) -> str:
    """Claude writes Markdown; Slack reads mrkdwn. Bold, strikethrough, links and headings are converted outside code
    spans, so `**x**` no longer shows its asterisks (found in the docs/14 test DM)."""
    parts = _CODE.split(text or "")
    for i in range(0, len(parts), 2):  # even indexes are outside code
        p = _HEADING.sub(r"*\1*", parts[i])
        p = _BOLD.sub(r"*\1*", p)
        p = _STRIKE.sub(r"~\1~", p)
        parts[i] = _LINK.sub(r"<\2|\1>", p)
    return "".join(parts)


# --- brief JSON -----------------------------------------------------------------------------------

def parse_brief(text: str) -> dict | None:
    """The last JSON object in the reply that has a "headline" key, or None."""
    for match in reversed(list(re.finditer(r"\{", text or ""))):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and str(data.get("headline") or "").strip():
            return data
    return None


def _rows(data: dict, key: str) -> list[dict]:
    return [r for r in data.get(key) or [] if isinstance(r, dict) and str(r.get("text") or "").strip()]


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _section(text: str, button: dict | None = None) -> dict:
    block = {"type": "section", "text": {"type": "mrkdwn", "text": _clip(to_mrkdwn(text), SECTION_MAX)}}
    if button:
        block["accessory"] = button
    return block


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": _clip(to_mrkdwn(text), SECTION_MAX)}]}


def _button(kind: str, row_text: str, *, primary: bool = False, url: str | None = None) -> dict | None:
    kind = (kind or "").lower()
    label = LABELS.get(kind)
    if not label:
        return None
    btn = {"type": "button", "text": {"type": "plain_text", "text": label}}
    if kind in LINKS:
        if not url or not url.startswith(LINKS[kind]):
            return None
        btn.update(action_id="brief_link", url=url)
    else:
        btn.update(action_id="brief_tap", value=json.dumps({"kind": kind, "text": _clip(row_text, VALUE_MAX)}))
    if primary:
        btn["style"] = "primary"
    return btn


def _link(url, label: str, prefix: str = "https://") -> str:
    """An inline mrkdwn link, or nothing when the url isn't the expected kind (a model slip never makes a bad link)."""
    url = str(url or "").strip()
    return f" <{url}|{label}>" if url.startswith(prefix) and not re.search(r"[\s<>|]", url) else ""


def render(text: str) -> Message:
    """The job's reply as a Slack message. Plain text when the JSON is missing or broken. No buttons: Gmail and
    directions are inline links, and the only things to tap are the reply drafts, posted as their own cards right
    under the brief (slack_bridge.post_drafts). Michael 2026-11-09: a button that answers in the thread is a wait,
    not an action."""
    data = parse_brief(text)
    if data is None:
        return Message(to_mrkdwn(text), None)
    headline = _clip(data["headline"], HEADER_MAX)
    needs = _rows(data, "needs_you")
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": headline}}]
    if str(data.get("counts") or "").strip():
        blocks.append(_context(data["counts"]))

    thread: list[str] = []
    if needs:
        blocks += [{"type": "divider"}, _section("*Needs you*")]
        for n, row in enumerate(needs[:MAX_NEEDS], 1):
            blocks.append(_section(f"{n}. {row['text']}" + _link(row.get("url"), "Open in Gmail", GMAIL)))
        if len(needs) > MAX_NEEDS:
            rest = needs[MAX_NEEDS:]
            blocks.append(_context(f"and {len(rest)} more, in the thread"))
            thread = [f"{n}. {r['text']}" + _link(r.get("url"), "Open in Gmail", GMAIL)
                      for n, r in enumerate(rest, MAX_NEEDS + 1)]

    today = _rows(data, "today")
    if today:
        blocks += [{"type": "divider"}, _section("*Today*")]
        for row in today:
            line = f"*{row['time']}* {row['text']}" if row.get("time") else row["text"]
            blocks.append(_section(line + _link(row.get("url"), "Directions")))
            if str(row.get("prep") or "").strip():
                blocks.append(_context(row["prep"]))

    busy = [str(i).strip() for i in (data.get("busy") or []) if str(i).strip()]
    remembered = _rows(data, "remembered")[:MAX_REMEMBERED]
    watching = str(data.get("watching") or "").strip()
    if busy or remembered or watching:
        blocks.append({"type": "divider"})
    if busy:
        blocks.append(_section("*While you were busy*\n" + "\n".join(f"• {i}" for i in busy[:MAX_BUSY])))
    if remembered:
        blocks.append(_section("*Picked up*\n" + "\n".join(f"• {r['text']}" for r in remembered)))
    if watching:
        blocks.append(_context(f"From your watching: {watching}"))

    blocks = blocks[:MAX_BLOCKS]  # only a very long Today gets here; Slack rejects the whole message past 50
    fallback = headline + (f" {len(needs)} need you." if needs else "")
    return Message(fallback, blocks, thread)


def show_text(value: str) -> str:
    """What the Show N button posts in the thread: the held-back list it carries."""
    return value or "Nothing held back."


def tap_prompt(kind: str, row_text: str) -> str:
    """The DM-style prompt for a brief button. The reply goes in the brief's thread."""
    asks = {
        "review": "Show me the draft for this in full, with the who and why, so I can send or edit it.",
        "remind": "Ask me when to remind me about this, in one short line.",
        "ideas": "Ask Kin for three short gift or celebration ideas for this.",
        "open": "Show me this pending approval again.",
        "details": "Tell me more about this, right here: what it is, whether it needs me, and what you'd do. "
                   "Four lines at most.",
        "prep": "Prep me for this: who, last contact, one thing to ask, anything to bring. Five lines at most.",
        "workout": "Post today's session from the coach's program for this.",
        "undo": "Forget this from observed/ with the memory skill, and confirm in one line what was removed.",
        "draft_hi": "Have Quill draft a short hello in my voice as a Gmail draft and post its card. Don't send.",
    }
    return f"[Tapped {LABELS.get(kind, kind)} on a Juno message]\n{row_text}\n\n{asks.get(kind, 'Handle this.')}"
