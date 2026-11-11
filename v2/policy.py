"""The policy engine, minimal (P1 deliverable 3): tools per run, tiers, budgets, kill switch, taint.

Taint is checked when a tool call is evaluated, not by changing the tool list, so the cached prefix never moves.
Model text never executes anything: a T3 call becomes an approval card built by code from the typed input, and the
bridge's existing cards and executor take it from there.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .tools import Tier, ToolSpec, validate

AUTO_MODES = ("auto", "auto_notify")


@dataclass
class RunState:
    run_id: str
    run_class: str
    intent: str
    tools: tuple[str, ...]
    budget: config.Budget
    tainted: bool = False
    cost: float = 0.0
    calls: int = 0
    proposals: list[dict] = field(default_factory=list)
    touched: list[dict] = field(default_factory=list)
    done: list[str] = field(default_factory=list)  # plain lines for the reply's record: what code carried out

    def over_budget(self) -> str | None:
        if self.calls >= self.budget.calls:
            return "calls"
        if self.cost >= self.budget.dollars:
            return "dollars"
        return None


@dataclass(frozen=True)
class Decision:
    verdict: str          # allow | ask | deny
    reason: str = ""


def new_run(run_class: str, intent: str, tools: list[ToolSpec], budget: config.Budget, tainted: bool) -> RunState:
    return RunState(f"r-{uuid.uuid4().hex[:10]}", run_class, intent, tuple(t.name for t in tools), budget,
                    tainted=tainted)


class Policy:
    def __init__(self, root: Path, automation_mode=None, paused=None):
        self.root = Path(root)
        self.state = self.root / "state"
        self._mode = automation_mode or (lambda cls: "ask")
        self._paused = paused or (lambda: (self.state / "PAUSED").exists())

    def decide(self, run: RunState, spec: ToolSpec | None, args: dict) -> Decision:
        if spec is None or spec.name not in run.tools:
            return Decision("deny", "that tool isn't available here")
        why = validate(spec, args)
        if why:
            return Decision("deny", why)
        if spec.tier is not Tier.T0 and self._paused():
            return Decision("deny", "Juno is paused; nothing that changes anything runs")
        if spec.tier in (Tier.T0, Tier.T1):
            return Decision("allow")
        if spec.tier is Tier.T3a:
            if spec.propose is None:  # undo of Juno's own hold: allowed only before outside text came in
                return Decision("deny", "outside text came into this conversation; ask Michael to say it again") \
                    if run.tainted else Decision("allow")
            if run.tainted:
                return Decision("ask", "outside text came into this conversation")
            return Decision("allow") if self._mode(spec.action_class) in AUTO_MODES else Decision("ask")
        return Decision("ask")  # T3b, and anything unknown

    def on_result(self, run: RunState, spec: ToolSpec, args: dict, result) -> None:
        if spec.returns_untrusted and getattr(result, "untrusted_text", False):
            run.tainted = True
        run.touched.extend(getattr(result, "touched", []) or [])
        self.audit("v2_tool", {"run_id": run.run_id, "tool": spec.name, "tier": spec.tier.value,
                               "tainted": run.tainted, "error": bool(getattr(result, "is_error", False))})

    # --- approvals: the existing card machinery ---------------------------------------------------------------
    def propose(self, run: RunState, spec: ToolSpec, fields: dict, reason: str = "") -> dict:
        """Write an approval entry for the bridge to post. Every field on the card comes from code."""
        entry = {"id": f"a-{uuid.uuid4().hex[:8]}", "kind": "action", "status": "new",
                 "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "session_id": None,
                 "from_timer": False, "run_id": run.run_id, "engine": "v2", "tainted": run.tainted,
                 "why": ("Asked in your DM. This conversation read outside text (mail or invites), so I'm checking."
                         if run.tainted else "Asked in your DM."),
                 **fields}
        path = self.state / "pending-approvals.json"
        data = _read(path, {"pending": []})
        data.setdefault("pending", []).append(entry)
        _write(path, data)
        run.proposals.append(entry)
        self.audit("v2_proposed", {"run_id": run.run_id, "id": entry["id"], "action_class": entry.get("action_class"),
                                   "reason": reason})
        return entry

    def audit(self, event: str, data: dict) -> None:
        try:
            self.state.mkdir(parents=True, exist_ok=True)
            with (self.state / "audit.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event,
                                     **data}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
