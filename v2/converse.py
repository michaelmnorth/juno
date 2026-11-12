"""One owner DM on the v2 path: event, route, assemble, run, record (02-ARCHITECTURE.md, Event -> run -> action).

The bridge calls Engine.handle() for every DM (v2 is the default engine, DV13). Every turn is a fresh request built
from the store: no transcript replay. Three cases hand the message to v1 instead (Reply.handoff): a request the
router sends to "other" (health, money, YouTube, research: not ported), no API key yet, or a failure before the run
did anything. A failure after the run acted is never handed off: the owner hears it with the run ID, so nothing
is done twice.
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



# Michael's own words that ask for an email to be written. Without one, no draft is saved, whatever a mail says.
DRAFT_WORDS = re.compile(r"\b(draft|reply|respond|write|email|e-mail|send|answer|tell|say|let \w+ know|rsvp)\b", re.I)

# The bridge's line for a photo or file he attached and it saved (gateway/slack_bridge.py dm_text). v2 can't see
# either, so the message goes straight to v1, which opens the saved file (P2 brief, #1 and #8). Code decides, no call.
ATTACHED = re.compile(r"^\[He attached [^\]\n]{1,160}?, saved at ", re.M)


@dataclass
class Reply:
    text: str
    run_id: str = ""
    cost: float = 0.0
    error: bool = False
    handoff: bool = False  # v1 answers this one (the bridge runs it and calls note_v1_reply)


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
            if ATTACHED.search(text):
                self.store.mark_event(event_id, "handed_off")
                self.policy.audit("v2_handoff", {"event": event_id, "why": "attachment"})
                return Reply("", handoff=True)
            client = self.client_factory()
            thread = self.store.thread(channel, self._now())
            mine = [t["text"] for t in self.store.turns(channel, config.RECENT_TURNS) if t["role"] == "user"]
            route, rres = router.route(client, text, thread["summary"], mine, thread.get("playbook", ""))
            if route.unsupported:
                self.store.mark_event(event_id, "handed_off")
                self.policy.audit("v2_handoff", {"event": event_id, "why": "unsupported", "intent": route.intent})
                return Reply("", cost=round(rres.cost, 6) if rres else 0.0, handoff=True)
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
            res = self._run_lane(client, lane, built, run, specs, wants_draft=bool(DRAFT_WORDS.search(text)))
            self.record(run, lane, route.intent, config.EFFORT["converse"], res, built.block_tokens)
            # Reads are safe to repeat, so a run that only looked things up can still hand off (r-674d36975d
            # searched and read mail, then could not hand off and asked him to paste the file instead).
            if (res.data or {}).get("hand_off") and not (run.proposals or run.done):
                self._log_cost(run)
                self.store.mark_event(event_id, "handed_off")
                self.policy.audit("v2_handoff", {"run_id": run.run_id, "why": "model", "intent": route.intent})
                return Reply("", run.run_id, round(run.cost, 6), handoff=True)
            reply = self._reply_text(res, run)
            self.store.set_playbook(channel, route.playbook)
            self._remember(channel, text, reply, run.run_id, thread, run.touched, run.tainted)
            self._log_cost(run)
            self.store.mark_event(event_id, "done")
            if built.overflow:
                self.policy.audit("v2_overflow", {"run_id": run.run_id, "blocks": built.overflow})
            return Reply(reply, run.run_id, round(run.cost, 6))
        except Exception as exc:
            ref = run.run_id if run else f"e{event_id}"
            acted = bool(run and (run.proposals or run.done))
            self.policy.audit("v2_failed", {"run_id": ref, "error": type(exc).__name__, "detail": str(exc)[:200],
                                            "handoff": not acted})
            if run:
                self._log_cost(run, error=True)
            if not acted:  # nothing happened yet, so v1 can safely take the whole message
                self.store.mark_event(event_id, "handed_off")
                return Reply("", ref, round(run.cost, 6) if run else 0.0, error=True, handoff=True)
            self.store.mark_event(event_id, "failed")
            done = "; ".join(run.done) or "part of it"
            return Reply(f"[react:warning] That stopped partway with an error (ref {ref}). Already done: {done}. "
                         "Check that before asking again, so nothing happens twice. 🙃", ref, error=True)

    def note_v1_reply(self, channel: str, text: str, reply: str) -> None:
        """v1 answered a handed-off message: keep both turns so the next v2 turn knows what was said. v1 may have
        read mail, web pages or transcripts, so the thread is tainted (a hold becomes a card until it goes quiet)."""
        thread = self.store.thread(channel, self._now())
        self._remember(channel, text, reply, "", thread, [], True)

    def recent_lines(self, channel: str, limit: int = 4) -> str:
        """The last few turns, as plain lines for a v1 handoff prompt: Michael's messages and v2's own replies.
        v1's earlier replies are left out (v1 has its own session for those), so a mistaken belief in one of them,
        like "that tool is blocked", is never fed back to v1 as fact (found 2026-11-11)."""
        rows = [t for t in self.store.turns(channel, limit * 2) if t["role"] == "user" or t.get("run_id")]
        return "\n".join(f"{'Michael' if t['role'] == 'user' else 'The lighter engine'}: {t['text'][:300]}"
                         for t in rows[-limit:])

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

    def _run_lane(self, client, lane: str, built, run, specs, wants_draft: bool = True) -> lanes.LaneResult:
        if lane == "l1":
            res = lanes.call(client, model=config.MODELS["converse"], effort=config.EFFORT["converse"],
                             system=built.system, messages=built.messages, schema=lanes.REPLY_SCHEMA,
                             max_tokens=config.MAX_OUTPUT["converse"])
            run.calls += 1
            run.cost += res.cost
            return res
        tctx = _ToolCtx(self, run, client)
        by_name = {s.name: s for s in specs}
        seen: dict[str, str] = {}

        def refuse(name: str, reason: str, message: str = "") -> tuple[str, bool]:
            """Every refused call lands in the audit log (P2: r-674d36975d made one that left no trace)."""
            known = name in tools.TOOLS
            self.policy.audit("v2_tool_refused", {"run_id": run.run_id, "tool": name if known else "unknown",
                                                  **({} if known else {"asked_for": re.sub(r"[^\w.-]", "", str(name))[:40]}),
                                                  "reason": reason[:120]})
            return json.dumps({"error": message or reason}), True

        def execute(name: str, args: dict) -> tuple[str, bool]:
            if name == "mail_draft" and not wants_draft:  # a draft only when his own words ask for one (DV16)
                return refuse(name, "no draft asked for",
                              "Michael didn't ask for a reply or a draft. Don't write one; answer him.")
            key = name + json.dumps(args, sort_keys=True)
            if key in seen and by_name.get(name) and by_name[name].tier == tools.Tier.T0:
                return json.dumps({"same_as_before": True, "note": "You already have this result. Don't call it "
                                   "again; use what you have."}), False
            spec = by_name.get(name)
            d = self.policy.decide(run, spec, args)
            if d.verdict == "deny":
                return refuse(name, d.reason)
            if d.verdict == "ask":
                if not spec.propose:
                    return refuse(name, "needs a tap and has no card", "needs Michael; ask him in your reply")
                try:
                    entry = self.policy.propose(run, spec, spec.propose(self.backend, args), d.reason)
                except Exception as exc:
                    return refuse(name, f"card not prepared: {type(exc).__name__}",
                                  f"couldn't prepare the card: {type(exc).__name__}. Nothing was sent or changed; "
                                  "don't describe this as something you did.")
                return json.dumps({"card_up": True, "summary": entry["summary"],
                                   "note": "Michael approves or skips with a tap; nothing has happened yet"}), False
            try:
                result = spec.handler(self.backend, args, tctx)
            except Exception as exc:
                result = tools.ToolResult({"error": f"{type(exc).__name__}: {str(exc)[:160]}"}, is_error=True)
            self.policy.on_result(run, spec, args, result)
            if not result.is_error and spec.tier in (tools.Tier.T1, tools.Tier.T3a):
                run.done.append(spec.name)
            out = tools.cap(result.content, spec.max_result_tokens)
            if not result.is_error:
                seen[key] = out
            return out, result.is_error

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
