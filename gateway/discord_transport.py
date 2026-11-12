"""Discord as Juno's channel (docs/v2/DEVIATIONS.md DV15).

The bridge's logic speaks Slack's shapes: Block Kit cards, message ids called `ts`, action bodies with `value` and
`selected_option`. Rather than a second copy of every card and handler, this module gives the bridge a client with
the same methods it already calls (chat_postMessage, chat_update, chat_delete, reactions_add, conversations_open,
chat_getPermalink), backed by Discord's REST API, and turns Discord events back into the same shapes. The cards
render as Discord components (v2 layout: text, sections with a button, separators, button rows, select menus).

    gateway  -> discord.py, DMs and button taps only (the Gateway connection)
    sending  -> plain HTTPS to discord.com/api/v10 with the bot token (this module's Rest)

What a tap needs later (the card's blocks, the value behind a button) is kept in state/discord-ui.json, so buttons
keep working after a restart. Nothing here reads a secret except the bot token it is handed.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOG = logging.getLogger("juno.discord")

API = "https://discord.com/api/v10"
IS_COMPONENTS_V2 = 1 << 15
SUPPRESS_EMBEDS = 1 << 2
TEXT_MAX = 2000  # a plain message
V2_TEXT_MAX = 3900  # all text in one components message (Discord allows 4000)
V2_MAX_COMPONENTS = 40
FILE_HOSTS = ("https://cdn.discordapp.com/", "https://media.discordapp.net/")
NO_PINGS = {"parse": []}  # a reply can never @everyone or ping anyone
USER_AGENT = "DiscordBot (https://github.com/michaelmnorth/juno, 1.0)"


class DiscordError(RuntimeError):
    """Safe to log: never holds the token."""


# --- text ---------------------------------------------------------------------------------------------------------

_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
_SLACK_LINK = re.compile(r"<(https?://[^|>\s]+)\|([^>]+)>")
_SLACK_BARE = re.compile(r"<(https?://[^|>\s]+)>")
_BOLD = re.compile(r"(?<![\w*])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![\w*])")
_STRIKE = re.compile(r"(?<![\w~])~(?![\s~])([^~\n]+?)(?<![\s~])~(?![\w~])")


def to_markdown(text: str) -> str:
    """Slack mrkdwn (what the bridge produces) to Discord markdown, outside code spans."""
    parts = _CODE.split(text or "")
    for i in range(0, len(parts), 2):
        p = _SLACK_LINK.sub(r"[\2](\1)", parts[i])
        p = _SLACK_BARE.sub(r"<\1>", p)
        p = _BOLD.sub(r"**\1**", p)
        p = _STRIKE.sub(r"~~\1~~", p)
        parts[i] = p.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return "".join(parts)


def split_text(text: str, limit: int = TEXT_MAX) -> list[str]:
    text = (text or "").strip() or "(empty)"
    out = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    out.append(text)
    return out


def emoji_for(name: str) -> str:
    """A Slack reaction name (smile, +1, saluting_face) as the Unicode emoji Discord wants."""
    import emoji
    for lang in ("alias", "en"):
        got = emoji.emojize(f":{name}:", language=lang)
        if got != f":{name}:":
            return got
    return "👍"


def snowflake_time(message_id: str) -> float | None:
    try:
        return ((int(message_id) >> 22) + 1420070400000) / 1000
    except (TypeError, ValueError):
        return None


# --- what taps need later ---------------------------------------------------------------------------------------

class Registry:
    """state/discord-ui.json: the blocks behind each card Juno posted, and what each button or menu stands for."""
    MAX_MESSAGES, MAX_CONTROLS = 500, 5000

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.messages: dict = data.get("messages", {})
        self.controls: dict = data.get("controls", {})

    def _save(self) -> None:
        for d, cap in ((self.messages, self.MAX_MESSAGES), (self.controls, self.MAX_CONTROLS)):
            for k in list(d)[:-cap]:
                del d[k]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"messages": self.messages, "controls": self.controls}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)

    def control(self, action_id: str, block_id: str, value: str = "", options: list[str] | None = None) -> str:
        raw = json.dumps([action_id, block_id, value, options or []], ensure_ascii=False)
        key = "j:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        with self._lock:
            self.controls[key] = {"action_id": action_id, "block_id": block_id, "value": value,
                                  "options": options or []}
            self._save()
        return key

    def remember(self, message_id: str, text: str, blocks: list[dict] | None) -> None:
        with self._lock:
            self.messages.pop(message_id, None)
            self.messages[message_id] = {"text": text or "", "blocks": blocks or [], "v2": bool(blocks)}
            self._save()

    def message(self, message_id: str) -> dict:
        return self.messages.get(message_id, {"text": "", "blocks": [], "v2": False})


# --- Block Kit to Discord components ------------------------------------------------------------------------------

STYLES = {"primary": 1, "danger": 4}


def _text_of(obj) -> str:
    if isinstance(obj, dict):
        return obj.get("text", "")
    return str(obj or "")


def _button(el: dict, block_id: str, reg: Registry) -> dict:
    label = (_text_of(el.get("text")) or "Open")[:80]
    if el.get("url"):
        return {"type": 2, "style": 5, "label": label, "url": el["url"]}
    return {"type": 2, "style": STYLES.get(el.get("style", ""), 2), "label": label,
            "custom_id": reg.control(el.get("action_id", ""), block_id, el.get("value", ""))}


def _select(el: dict, block_id: str, reg: Registry) -> dict:
    opts = (el.get("options") or [])[:25]
    values = [o.get("value", "") for o in opts]
    return {"type": 3, "custom_id": reg.control(el.get("action_id", ""), block_id, "", values),
            "placeholder": (_text_of(el.get("placeholder")) or "More")[:150],
            "options": [{"label": (_text_of(o.get("text")) or "?")[:100], "value": str(i)}
                        for i, o in enumerate(opts)]}


def _rich_text(block: dict) -> str:
    lines = []
    for el in block.get("elements", []):
        inner = "".join(e.get("text", "") for e in el.get("elements", []) if isinstance(e, dict))
        lines.append(f"```\n{inner}\n```" if el.get("type") == "rich_text_preformatted" else inner)
    return "\n".join(lines)


def render_blocks(blocks: list[dict], reg: Registry) -> list[dict]:
    comps: list[dict] = []

    def text(t: str) -> None:
        t = to_markdown(t).strip()
        if not t:
            return
        if comps and comps[-1]["type"] == 10:  # neighbouring text joins one component (the limit is 40)
            comps[-1]["content"] += "\n" + t
        else:
            comps.append({"type": 10, "content": t})

    for b in blocks:
        kind, bid = b.get("type"), b.get("block_id", "")
        if kind == "header":
            text(f"## {_text_of(b.get('text'))}")
        elif kind == "section":
            body = _text_of(b.get("text"))
            fields = [_text_of(f) for f in b.get("fields") or []]
            body = "\n".join(x for x in [body, *fields] if x)
            acc = b.get("accessory") or {}
            if acc.get("type") == "button" and body:
                comps.append({"type": 9, "components": [{"type": 10, "content": to_markdown(body)}],
                              "accessory": _button(acc, bid, reg)})
            else:
                text(body)
                if acc.get("type") in ("overflow", "static_select"):
                    comps.append({"type": 1, "components": [_select(acc, bid, reg)]})
                elif acc.get("type") == "button":
                    comps.append({"type": 1, "components": [_button(acc, bid, reg)]})
        elif kind == "context":
            words = " · ".join(_text_of(e) for e in b.get("elements", []) if e.get("type") in ("mrkdwn", "plain_text"))
            if words:
                text("\n".join(f"-# {line}" for line in words.splitlines() if line.strip()))
        elif kind == "divider":
            comps.append({"type": 14, "divider": True, "spacing": 1})
        elif kind == "actions":
            row: list[dict] = []
            for el in b.get("elements", []):
                if el.get("type") == "button":
                    if len(row) == 5:
                        comps.append({"type": 1, "components": row})
                        row = []
                    row.append(_button(el, bid, reg))
                elif el.get("type") in ("overflow", "static_select"):
                    if row:
                        comps.append({"type": 1, "components": row})
                        row = []
                    comps.append({"type": 1, "components": [_select(el, bid, reg)]})
            if row:
                comps.append({"type": 1, "components": row})
        elif kind == "rich_text":
            text(_rich_text(b))
    while comps and comps[-1]["type"] == 14:
        comps.pop()
    return _fit(comps)


def _count(comps: list[dict]) -> int:
    n = 0
    for c in comps:
        n += 1 + len(c.get("components", [])) + (1 if c.get("accessory") else 0)
    return n


def _fit(comps: list[dict]) -> list[dict]:
    """Inside Discord's limits: 40 components and about 4000 characters of text per message."""
    while _count(comps) > V2_MAX_COMPONENTS and comps:
        drop = next((i for i in range(len(comps) - 1, -1, -1) if comps[i]["type"] == 14), len(comps) - 1)
        comps.pop(drop)
    budget = V2_TEXT_MAX
    for c in comps:
        for t in ([c] if c["type"] == 10 else c.get("components", []) if c["type"] == 9 else []):
            if t.get("type") == 10:
                t["content"] = t["content"][:max(1, budget)]
                budget -= len(t["content"])
    return comps


def payload(text: str, blocks: list[dict] | None, reg: Registry) -> dict:
    if blocks:
        comps = render_blocks(blocks, reg) or [{"type": 10, "content": to_markdown(text)[:V2_TEXT_MAX] or "…"}]
        return {"components": comps, "flags": IS_COMPONENTS_V2, "allowed_mentions": NO_PINGS}
    return {"content": to_markdown(text)[:TEXT_MAX], "flags": SUPPRESS_EMBEDS, "allowed_mentions": NO_PINGS}


# --- REST -------------------------------------------------------------------------------------------------------

class Rest:
    def __init__(self, token: str, opener=None):
        self._token = token
        self._open = opener or urllib.request.urlopen

    def __call__(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(4):
            req = urllib.request.Request(API + path, data=data, method=method, headers={
                "Authorization": f"Bot {self._token}", "User-Agent": USER_AGENT,
                **({"Content-Type": "application/json"} if data is not None else {})})
            try:
                with self._open(req, timeout=20) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:  # rate limited: wait what Discord says, then retry
                    try:
                        wait = float(json.loads(exc.read() or b"{}").get("retry_after", 1))
                    except ValueError:
                        wait = 1.0
                    time.sleep(min(wait, 10))
                    continue
                detail = exc.read()[:300].decode("utf-8", "replace") if exc.fp else ""
                raise DiscordError(f"{method} {path.split('?')[0]} -> {exc.code} {detail}") from None
            except urllib.error.URLError as exc:
                raise DiscordError(f"{method} {path.split('?')[0]} failed: {exc.reason}") from None
        raise DiscordError(f"{method} {path.split('?')[0]} kept hitting the rate limit")


class DiscordClient:
    """The Slack WebClient methods the bridge calls, on Discord. Message ids stand in for Slack's ts."""
    token = ""  # attachments on Discord's CDN need no auth header
    file_hosts = FILE_HOSTS

    def __init__(self, rest, registry: Registry):
        self.rest, self.registry = rest, registry
        self._dm: dict[str, str] = {}

    def chat_postMessage(self, *, channel: str, text: str = "", blocks: list[dict] | None = None,
                         thread_ts: str | None = None, **_) -> dict:
        pieces = [payload(text, blocks, self.registry)] if blocks else [
            payload(p, None, self.registry) for p in split_text(to_markdown(text))]
        msg = {}
        for p in pieces:
            if thread_ts:  # Slack's thread reply becomes a Discord reply to that message
                p["message_reference"] = {"message_id": thread_ts, "fail_if_not_exists": False}
            msg = self.rest("POST", f"/channels/{channel}/messages", p)
        self.registry.remember(msg.get("id", ""), text, blocks)
        return {"ok": True, "ts": msg.get("id", ""), "channel": channel}

    def chat_update(self, *, channel: str, ts: str, text: str = "", blocks: list[dict] | None = None, **_) -> dict:
        was_v2 = self.registry.message(ts).get("v2")
        if was_v2 and not blocks:  # a components message stays one
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text or "…"}}]
        p = payload(text, blocks, self.registry)
        self.rest("PATCH", f"/channels/{channel}/messages/{ts}", p)
        self.registry.remember(ts, text, blocks)
        return {"ok": True, "ts": ts}

    def chat_delete(self, *, channel: str, ts: str, **_) -> dict:
        self.rest("DELETE", f"/channels/{channel}/messages/{ts}")
        return {"ok": True}

    def _reaction_path(self, channel: str, ts: str, name: str) -> str:
        return f"/channels/{channel}/messages/{ts}/reactions/{urllib.parse.quote(emoji_for(name))}/@me"

    def reactions_add(self, *, channel: str, timestamp: str, name: str, **_) -> dict:
        self.rest("PUT", self._reaction_path(channel, timestamp, name))
        return {"ok": True}

    def reactions_remove(self, *, channel: str, timestamp: str, name: str, **_) -> dict:
        self.rest("DELETE", self._reaction_path(channel, timestamp, name))
        return {"ok": True}

    def conversations_open(self, *, users: list[str], **_) -> dict:
        uid = str(users[0])
        if uid not in self._dm:
            self._dm[uid] = self.rest("POST", "/users/@me/channels", {"recipient_id": uid})["id"]
        return {"ok": True, "channel": {"id": self._dm[uid]}}

    def chat_getPermalink(self, *, channel: str, message_ts: str, **_) -> dict:
        return {"ok": True, "permalink": f"https://discord.com/channels/@me/{channel}/{message_ts}"}


# --- the app: Bolt's decorators, Discord's events ---------------------------------------------------------------

class App:
    """Enough of slack_bolt.App for gateway/slack_bridge.py build_app(): .client, @event, @action."""

    def __init__(self, client: DiscordClient):
        self.client = client
        self._events: dict[str, list] = {}
        self._actions: list[tuple] = []

    def event(self, name: str):
        def deco(fn):
            self._events.setdefault(name, []).append(fn)
            return fn
        return deco

    def action(self, matcher):
        def deco(fn):
            self._actions.append((matcher, fn))
            return fn
        return deco

    @staticmethod
    def _call(fn, **available):
        params = inspect.signature(fn).parameters
        return fn(**{k: v for k, v in available.items() if k in params})

    def dispatch_event(self, name: str, event: dict) -> None:
        for fn in self._events.get(name, []):
            try:
                self._call(fn, event=event, client=self.client, logger=LOG, body={"event": event})
            except Exception:
                LOG.exception("%s handler failed", name)

    def handler_for(self, action_id: str):
        for matcher, fn in self._actions:
            if (matcher == action_id) if isinstance(matcher, str) else matcher.match(action_id):
                return fn
        return None

    def dispatch_action(self, body: dict) -> bool:
        fn = self.handler_for(body["actions"][0]["action_id"])
        if not fn:
            return False
        try:
            self._call(fn, ack=lambda *a, **k: None, body=body, client=self.client, logger=LOG,
                       action=body["actions"][0])
        except Exception:
            LOG.exception("action %s failed", body["actions"][0]["action_id"])
        return True


def message_event(*, message_id: str, channel_id: str, author_id: str, content: str,
                  attachments: list[dict], mention: bool = False) -> dict:
    """A Discord DM (or an @mention of Juno in a server channel) in the shape the bridge's Slack handler reads."""
    return {"type": "message", "channel_type": "mention" if mention else "im", "channel": channel_id, "user": author_id, "ts": message_id,
            "sent_at": snowflake_time(message_id), "text": content,
            **({"subtype": "file_share", "files": [
                {"id": str(a.get("id")), "mimetype": (a.get("content_type") or "").split(";")[0],
                 "url_private": a.get("url", ""), "size": a.get("size") or 0, "name": a.get("filename", "")}
                for a in attachments]} if attachments else {})}


def action_body(*, custom_id: str, values: list[str] | None, message_id: str, channel_id: str, user_id: str,
                reg: Registry) -> dict | None:
    """A Discord button or menu tap in the shape of a Slack block_actions body. None for a control we never made."""
    ctl = reg.controls.get(custom_id)
    if not ctl:
        return None
    action = {"action_id": ctl["action_id"], "block_id": ctl["block_id"], "value": ctl["value"]}
    if ctl.get("options"):
        try:
            action["selected_option"] = {"value": ctl["options"][int((values or ["0"])[0])]}
        except (ValueError, IndexError):
            return None
    stored = reg.message(message_id)
    return {"type": "block_actions", "user": {"id": user_id}, "channel": {"id": channel_id},
            "message": {"ts": message_id, "blocks": stored["blocks"], "text": stored["text"]}, "actions": [action]}


def run_gateway(token: str, app: App, allowed: set[str], executor=None) -> None:
    """Connect to Discord and hand DMs and taps to the app on worker threads. Blocks until the process ends."""
    import asyncio
    import discord
    from concurrent.futures import ThreadPoolExecutor

    pool = executor or ThreadPoolExecutor(max_workers=8, thread_name_prefix="juno-discord")
    intents = discord.Intents.none()
    intents.dm_messages = True  # DMs carry their text without the privileged message-content intent
    intents.guild_messages = True  # server messages; only ones that @mention Juno carry their text (DV18)
    intents.guilds = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        LOG.info("Discord gateway up as %s", client.user)

    @client.event
    async def on_message(m):
        if m.author.bot or str(m.author.id) not in allowed:
            return  # only Michael; other members and bots are never read
        mention = m.guild is not None
        if mention and client.user not in m.mentions:
            return  # in a server, only messages that @mention Juno
        content = m.content or ""
        if mention:
            content = re.sub(rf"<@!?{client.user.id}>", "", content).strip() or "(he just @mentioned you)"
        event = message_event(message_id=str(m.id), channel_id=str(m.channel.id), author_id=str(m.author.id),
                              content=content, mention=mention, attachments=[
                                  {"id": a.id, "content_type": a.content_type, "url": a.url, "size": a.size,
                                   "filename": a.filename} for a in m.attachments])
        asyncio.get_running_loop().run_in_executor(pool, app.dispatch_event, "message", event)

    @client.event
    async def on_interaction(i):
        if i.type != discord.InteractionType.component or i.message is None:
            return
        data = i.data or {}
        body = action_body(custom_id=data.get("custom_id", ""), values=data.get("values"),
                           message_id=str(i.message.id), channel_id=str(i.channel_id), user_id=str(i.user.id),
                           reg=app.client.registry)
        try:
            await i.response.defer()  # within Discord's 3 seconds; the handler edits the card afterwards
        except Exception as exc:
            LOG.info("tap ack failed: %s", type(exc).__name__)
        if body is None or str(i.user.id) not in allowed:
            return
        asyncio.get_running_loop().run_in_executor(pool, app.dispatch_action, body)

    client.run(token, log_handler=None)
