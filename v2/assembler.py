"""The context assembler (03-CONTEXT-AND-COST.md, The assembler). One function builds every converse request.

Order is most stable first. Blocks 1-4 are operator text and carry no timestamp or per-run value; block 5 (operator
facts) goes in a mid-conversation system message; blocks 6-9 are data, delimited and labelled, in one user message.
Each block has a budget; over budget is truncated by priority and recorded, never silently grown.

Token counts here are estimates (characters / 4) used to enforce the budgets before the call; the ledger also keeps
the real totals from response usage. See docs/v2/DEVIATIONS.md DV10.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from .tools import ToolSpec, api_tools

HERE = Path(__file__).resolve().parent
ZONE = ZoneInfo("America/New_York")


def est(text: str) -> int:
    return math.ceil(len(text) / 4)


def fit(text: str, budget: int) -> tuple[str, bool]:
    """Cut text to a token budget at a line boundary. Returns (text, cut)."""
    if est(text) <= budget:
        return text, False
    out, used = [], 0
    for line in text.splitlines():
        cost = est(line + "\n")
        if used + cost > budget:
            break
        out.append(line)
        used += cost
    return "\n".join(out), True


def fit_items(items: list[str], budget: int) -> tuple[list[str], bool]:
    """Keep whole items in priority order until the budget is spent."""
    out, used = [], 0
    for item in items:
        cost = est(item) + 1
        if used + cost > budget:
            return out, True
        out.append(item)
        used += cost
    return out, False


def read_prompt(name: str) -> str:
    return (HERE / "prompts" / name).read_text(encoding="utf-8").strip()


def playbook_body(name: str) -> str:
    text = (HERE / "playbooks" / name / "SKILL.md").read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text.strip()


@dataclass
class Context:
    """What code gathered for this turn. Built by v2/converse.py from the store and the backend."""
    message: str
    now: datetime
    playbook: str
    core_card: str = ""            # block 3, from the instance (me/profile.md)
    voice: str = ""                # appended to the mail playbook (me/voice.md)
    snapshot: list[str] = field(default_factory=list)       # block 6 lines, highest priority first
    memory: list[dict] = field(default_factory=list)        # block 7: {"source","trust","text"}
    summary: str = ""
    working_set: list[dict] = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)         # {"role","text"}
    tainted: bool = False
    quiet_hours: bool = False
    budget_left: float = 0.0


@dataclass
class Assembled:
    system: list[dict]
    messages: list[dict]
    tools: list[dict]
    block_tokens: dict
    overflow: list[str]

    @property
    def estimate(self) -> int:
        return sum(self.block_tokens.values())


def build(ctx: Context, specs: list[ToolSpec], *, lane: str) -> Assembled:
    B = config.BLOCK_BUDGETS
    overflow: list[str] = []
    tok: dict[str, int] = {}

    tools = api_tools(specs)
    tok["tools"] = est(json.dumps(tools, sort_keys=True, separators=(",", ":")))
    if tok["tools"] > B["tools"]:
        overflow.append("tools")  # a deploy-time bug: the playbook's tool set is too big

    constitution = read_prompt("constitution.md")
    tok["constitution"] = est(constitution)
    core, cut = fit(read_prompt("persona.md") + ("\n\nAbout Michael:\n" + ctx.core_card if ctx.core_card else ""),
                    B["core"])
    tok["core"] = est(core)
    overflow += ["core"] if cut else []

    play = playbook_body(ctx.playbook)
    if ctx.playbook == "mail" and ctx.voice:
        play += "\n\nMichael's voice:\n" + ctx.voice
    play, cut = fit(play, B["playbook"])
    tok["playbook"] = est(play)
    overflow += ["playbook"] if cut else []

    # Breakpoint A after the stable prefix (tools + constitution + persona/core); B after the playbook in L2 only.
    system = [{"type": "text", "text": constitution},
              {"type": "text", "text": core, "cache_control": {"type": "ephemeral"}},
              {"type": "text", "text": "Playbook for this request:\n" + play,
               **({"cache_control": {"type": "ephemeral"}} if lane == "l2" else {})}]

    local = ctx.now.astimezone(ZONE)
    operator = (f"Now: {local:%A %Y-%m-%d %H:%M} Eastern. Quiet hours: {'yes' if ctx.quiet_hours else 'no'}. "
                f"Outside text in this conversation: {'yes, so holds go to a card' if ctx.tainted else 'no'}. "
                f"Budget left this turn: ${max(0.0, ctx.budget_left):.2f}.")
    operator, _ = fit(operator, B["operator"])
    tok["operator"] = est(operator)

    snap, cut = fit_items(ctx.snapshot, B["snapshot"])
    tok["snapshot"] = est("\n".join(snap))
    overflow += ["snapshot"] if cut else []

    mem_items = [f"[{m['trust']}: {m['source']}] {m['text']}" for m in ctx.memory]
    mem, cut = fit_items(mem_items, B["memory"])
    tok["memory"] = est("\n".join(mem))
    overflow += ["memory"] if cut else []

    summary, cut = fit(ctx.summary, B["summary"])
    overflow += ["summary"] if cut else []
    ws_lines = [f"- {w.get('kind')}: {w.get('label', '')} (id {w.get('id', '')})" for w in reversed(ctx.working_set)]
    ws, cut = fit_items(ws_lines, B["working_set"])
    overflow += ["working_set"] if cut else []
    turn_lines = [f"{'Michael' if t['role'] == 'user' else 'You'}: {t['text']}" for t in ctx.turns]
    kept, cut = fit_items(list(reversed(turn_lines)), B["turns"])  # newest turns win
    overflow += ["turns"] if cut else []
    turns = list(reversed(kept))
    tok["thread"] = est(summary) + est("\n".join(ws)) + est("\n".join(turns))

    tok["message"] = est(ctx.message)

    data = ("<data name=\"snapshot\">\n" + ("\n".join(snap) or "nothing coming up") + "\n</data>\n"
            "<data name=\"memory\">\n" + ("\n".join(mem) or "nothing retrieved") + "\n</data>\n"
            "<data name=\"thread\">\nEarlier: " + (summary or "nothing earlier") + "\nWorking set (newest first):\n"
            + ("\n".join(ws) or "- empty") + "\nLast turns:\n" + ("\n".join(turns) or "none") + "\n</data>\n")
    messages = [{"role": "user", "content": data + "\nMichael's message:\n" + ctx.message},
                {"role": "system", "content": operator}]
    return Assembled(system, messages, tools, tok, overflow)
