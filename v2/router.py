"""The router (03-CONTEXT-AND-COST.md, Router): one structured call on Haiku 5.5.

It sees only Michael's message and the thread summary, never untrusted text. Its answer picks the playbook (and so
the tool set), the memory to retrieve, and the lane. Low confidence falls back to `general`.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config, lanes

PLAYBOOKS = ("calendar", "mail", "people", "notes", "research", "general")

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "description": "short label like calendar.change or chat"},
        "playbook": {"type": "string", "enum": list(PLAYBOOKS) + ["other"]},
        "entities": {"type": "array", "items": {"type": "string"}, "description": "people or things named"},
        "memory_slots": {"type": "array", "items": {"type": "string",
                                                     "enum": ["routines", "goals", "preferences", "people"]}},
        "needs_tools": {"type": "boolean", "description": "false only for chat that needs no lookup or action"},
        "complexity": {"type": "string", "enum": ["simple", "standard", "deep"]},
        "confidence": {"type": "string", "enum": ["high", "low"]},
    },
    "required": ["intent", "playbook", "entities", "memory_slots", "needs_tools", "complexity", "confidence"],
    "additionalProperties": False,
}

SYSTEM = ("Route one direct message from Michael to his personal assistant. Playbooks: calendar (scheduling, holds, "
          "invites, free time), mail (find, read, draft, send email), people (someone in his life, birthdays, "
          "prep, addresses), notes (reminders, notes, what he said before), research (look into, research, what's new in, "
          "a fact to check on the web, a known fault or recall), general (chat, news, anything else the "
          "others don't cover), other (training, sleep, money accounts and taxes, YouTube, his Discord server and its channels, opening or reviewing an email attachment or a file, web pages and forms, shopping and prices). "
          "A bill, receipt or any question about an email is mail. A follow-up like 'move that to 4', 'remove it' "
          "or 'send it' keeps the previous playbook and needs tools.")


@dataclass(frozen=True)
class Route:
    intent: str
    playbook: str
    entities: tuple[str, ...]
    memory_slots: tuple[str, ...]
    needs_tools: bool
    complexity: str
    unsupported: bool = False


FALLBACK = Route("general", "general", (), (), True, "standard")


def route(client, message: str, summary: str, recent: list[str] | None = None,
          last_playbook: str = "") -> tuple[Route, lanes.LaneResult | None]:
    """`recent` is Michael's own last few messages (his words only, never a reply or tool text), and
    `last_playbook` the previous turn's, so a follow-up keeps its tools."""
    earlier = "\n".join(f"- {m[:200]}" for m in (recent or [])[-3:]) or "none"
    res = lanes.call(client, model=config.MODELS["router"], effort=config.EFFORT["router"],
                     system=[{"type": "text", "text": SYSTEM}],
                     messages=[{"role": "user", "content": (
                         f"Thread summary: {summary or 'none'}\nHis earlier messages:\n{earlier}\n"
                         f"Previous playbook: {last_playbook or 'none'}\n\nMessage: {message}")}],
                     schema=SCHEMA, max_tokens=config.MAX_OUTPUT["router"])
    d = res.data
    if not d or d.get("confidence") == "low":
        return FALLBACK, res
    playbook = d.get("playbook", "general")
    unsupported = playbook == "other"
    return Route(d.get("intent", "general")[:40], "general" if unsupported else playbook,
                 tuple(str(e)[:60] for e in d.get("entities", [])[:5]),
                 tuple(d.get("memory_slots", [])[:4]), bool(d.get("needs_tools", True)),
                 d.get("complexity", "standard"), unsupported), res
