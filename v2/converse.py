"""One owner DM on the v2 path: event, route, assemble, run, record (02-ARCHITECTURE.md, Event -> run -> action).

The bridge calls Engine.handle() for a DM thread whose engine flag is v2. Every turn is a fresh request built from
the store: no transcript replay. When something fails the owner hears it with the run ID; there is no silent
fallback to v1.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import assembler, config, lanes, router, tools
from .policy import Policy, new_run
from .store import Store

UNSUPPORTED_REPLY = ("[react:hourglass] That one (training, sleep, money, YouTube or web research) isn't on the new "
                     "engine yet. Say \"use v1\" and ask again, and the old one handles it. 🙃")


@dataclass
class Reply:
    text: str
    run_id: str = ""
    cost: float = 0.0
    error: bool = False


class _ToolCtx:
    def __init__(self, engine: "Engine", run, client):
        self.engine, self.run, self.client = engine, run, client

    @property
    def tainted(self) -> bool:
        return self.run.tainted

    def reader(self, message: dict) -> dict:
        fields, res = lanes.read(self.client, message)
        self.run.cost += res.cost  # the reader's spend counts against this turn
        self.engine.record(self.run, "l1", "reader", config.EFFORT["reader"], res, {"message": 0}, run_class="reader")
        return fields


class Engine:
    def __init__(self, root: Path, backend, *, store: Store | None = None, client_factory=None, policy=None,
                 now=None):
        self.root = Path(root)
        self.backend = backend
        self.store = store or Store(self.root / "state" / "v2.db")
        self.client_factory = client_factory or lanes.make_client
        self.policy = policy or Policy(self.root, automation_mode=getattr(backend, "automation_mode", None))
        self._now = now or (lambda: datetime.now(timezone.utc))

    # --- the turn ---------------------------------------------------------------------------------------------
    def handle(self, channel: str, text: str, dedupe_key: str) -> Reply | None:
        event_id = self.store.enqueue(dedupe_key, "dm", {"text": text}, channel)
        if event_id is None:
            return None  # a retry of a DM already handled
        self.store.mark_event(event_id, "running")
        run = None
        try:
            client = self.client_factory()
            thread = self.store.thread(channel, self._now())
            route, rres = router.route(client, text, thread["summary"])
            if route.unsupported:
                self.store.mark_event(event_id, "done")
                self._remember(channel, text, UNSUPPORTED_REPLY, "", thread, [], thread["tainted"])
                return Reply(UNSUPPORTED_REPLY)
            lane = "l2" if route.needs_tools else "l1"
            budget = config.BUDGETS["deep" if route.complexity == "deep" else lane]
            specs = tools.for_playbook(route.playbook) if lane == "l2" else []
            run = new_run("converse", route.intent, specs, budget, thread["tainted"])
            if rres:
                run.cost += rres.cost
                self.record(run, "l1", route.intent, config.EFFORT["router"], rres, {"message": assembler.est(text)},
                            run_class="router")
            ctx = self._context(text, route, thread, run)
            built = assembler.build(ctx, specs, lane=lane)
            res = self._run_lane(client, lane, built, run, specs)
            self.record(run, lane, route.intent, config.EFFORT["converse"], res, built.block_tokens)
            reply = self._reply_text(res, run)
            self._remember(channel, text, reply, run.run_id, thread, run.touched, run.tainted)
            self._log_cost(run)
            self.store.mark_event(event_id, "done")
            if built.overflow:
                self.policy.audit("v2_overflow", {"run_id": run.run_id, "blocks": built.overflow})
            return Reply(reply, run.run_id, round(run.cost, 6))
        except Exception as exc:  # the owner hears it; nothing falls back silently
            self.store.mark_event(event_id, "failed")
            ref = run.run_id if run else f"e{event_id}"
            self.policy.audit("v2_failed", {"run_id": ref, "error": type(exc).__name__, "detail": str(exc)[:200]})
            if run:
                self._log_cost(run, error=True)
            why = "I don't have the key for it yet" if isinstance(exc, lanes.LaneError) else "it hit an error"
            return Reply(f"[react:warning] The new engine couldn't answer that ({why}; ref {ref}). Nothing was "
                         "changed. Say \"use v1\" to switch back, or try again. 🙃", ref, error=True)

    def reset(self, channel: str) -> None:
        self.store.save_thread(channel, summary="", working_set=[], tainted=False)
        self.store._exec("delete from turns where channel=?", (channel,))

    # --- pieces -----------------------------------------------------------------------------------------------
    def _context(self, text: str, route, thread: dict, run) -> assembler.Context:
        b = self.backend
        recent = self.store.turns(thread["channel"], config.RECENT_TURNS)
        return assembler.Context(
            message=text, now=self._now(), playbook=route.playbook,
            core_card=b.core_card(), voice=b.voice() if route.playbook == "mail" else "",
            snapshot=b.snapshot(self._now()), memory=b.memory(list(route.entities), list(route.memory_slots)),
            summary=thread["summary"], working_set=thread["working_set"], turns=recent, tainted=run.tainted,
            quiet_hours=b.quiet_hours(), budget_left=run.budget.dollars - run.cost)

    def _run_lane(self, client, lane: str, built, run, specs) -> lanes.LaneResult:
        if lane == "l1":
            res = lanes.call(client, model=config.MODELS["converse"], effort=config.EFFORT["converse"],
                             system=built.system, messages=built.messages, schema=lanes.REPLY_SCHEMA,
                             max_tokens=config.MAX_OUTPUT["converse"])
            run.calls += 1
            run.cost += res.cost
            return res
        tctx = _ToolCtx(self, run, client)
        by_name = {s.name: s for s in specs}

        def execute(name: str, args: dict) -> tuple[str, bool]:
            spec = by_name.get(name)
            d = self.policy.decide(run, spec, args)
            if d.verdict == "deny":
                return json.dumps({"error": d.reason}), True
            if d.verdict == "ask":
                if not spec.propose:
                    return json.dumps({"error": "needs Michael; ask him in your reply"}), True
                try:
                    entry = self.policy.propose(run, spec, spec.propose(self.backend, args), d.reason)
                except Exception as exc:
                    return json.dumps({"error": f"couldn't prepare the card: {type(exc).__name__}"}), True
                return json.dumps({"card_up": True, "summary": entry["summary"],
                                   "note": "Michael approves or skips with a tap; nothing has happened yet"}), False
            try:
                result = spec.handler(self.backend, args, tctx)
            except Exception as exc:
                result = tools.ToolResult({"error": f"{type(exc).__name__}: {str(exc)[:160]}"}, is_error=True)
            self.policy.on_result(run, spec, args, result)
            if not result.is_error and spec.tier in (tools.Tier.T1, tools.Tier.T3a):
                run.done.append(spec.name)
            return tools.cap(result.content, spec.max_result_tokens), result.is_error

        return lanes.loop(client, model=config.MODELS["converse"], effort=config.EFFORT["converse"],
                          system=built.system, messages=built.messages, tools=built.tools, run=run, execute=execute,
                          max_tokens=config.MAX_OUTPUT["converse"])

    def _reply_text(self, res: lanes.LaneResult, run) -> str:
        cards = [p["summary"] for p in run.proposals]
        tail = ("\n\nCard's up: " + "; ".join(cards)) if cards else ""
        if res.stopped in ("calls", "dollars"):
            done = f" Done so far: {', '.join(_plain(d) for d in run.done)}." if run.done else " Nothing changed."
            return (f"[react:hourglass] I stopped partway: that was taking more steps than it should.{done} "
                    f"Ask for the rest in a smaller piece. 🙃{tail}")
        if res.stopped == "refusal":
            return "[react:thinking_face] I can't help with that one. Nothing was changed."
        if res.stopped == "max_tokens" or not res.data:
            return f"[react:warning] My answer came out garbled, so I dropped it. Nothing was changed. Try again?{tail}"
        reaction = re.sub(r"[^a-z0-9_+\-]", "", str(res.data.get("reaction", "")).lower())[:40]
        body = str(res.data.get("reply", "")).strip()
        if cards and "card" not in body.lower():
            body += tail
        return (f"[react:{reaction}] " if reaction else "") + body

    def _remember(self, channel: str, text: str, reply: str, run_id: str, thread: dict, touched: list[dict],
                  tainted: bool) -> None:
        self.store.add_turn(channel, "user", text, run_id)
        self.store.add_turn(channel, "assistant", re.sub(r"^\[react:[^\]]*\]\s*", "", reply), run_id)
        ws = [w for w in thread["working_set"] if w.get("id") not in {t.get("id") for t in touched}] + touched
        older = self.store.turns(channel, 40)[:-config.RECENT_TURNS]
        summary = "; ".join(f"{'he asked' if t['role'] == 'user' else 'you said'}: {t['text'][:90]}"
                            for t in older[-12:])
        self.store.save_thread(channel, summary=summary, working_set=ws, tainted=tainted)

    def record(self, run, lane: str, intent: str, effort: str, res: lanes.LaneResult, block_tokens: dict, *,
               run_class: str | None = None) -> None:
        rows = lanes.ledger_rows(run, lane, intent, effort, res, block_tokens)
        for row in rows:
            if run_class:
                row["run_class"] = run_class
            self.store.ledger(row)

    def _log_cost(self, run, error: bool = False) -> None:
        """One row in state/costs.jsonl, the file the spend notices read (gateway/brakes.py)."""
        rows = self.store.ledger_rows(run.run_id)
        tokens = {"in": sum(r["input_tokens"] or 0 for r in rows), "out": sum(r["output_tokens"] or 0 for r in rows),
                  "cache_read": sum(r["cache_read"] or 0 for r in rows),
                  "cache_write": sum((r["cache_write_5m"] or 0) + (r["cache_write_1h"] or 0) for r in rows)}
        line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "job": "dm-v2",
                "model": config.MODELS["converse"], "cost_usd": round(run.cost, 6),
                "session_total_usd": round(run.cost, 6), "session_id": run.run_id, "tokens": tokens,
                "turns": run.calls, "is_error": error}
        try:
            path = self.root / "state" / "costs.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
        except OSError:
            pass


def _plain(tool_name: str) -> str:
    return {"calendar_hold": "the hold", "calendar_undo_hold": "removed the hold", "mail_draft": "the draft",
            "reminder_add": "the reminder", "note_add": "the note"}.get(tool_name, tool_name.replace("_", " "))
