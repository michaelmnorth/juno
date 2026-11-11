"""Run the dialogue set on the v2 engine against the synthetic world and grade it in code.

    .venv\\Scripts\\python evals\\run_dialogues.py            # all dialogues, real models (spends real money)
    .venv\\Scripts\\python evals\\run_dialogues.py hold-then-move invite-needs-tap

Needs JUNO_V2_API_KEY in the environment (the bridge's 1Password item). Each run gets its own temp folder: no
instance data is read or written. Prints one line per dialogue and the score; writes evals/last-run.json.
About $0.02 to $0.05 a dialogue at list prices.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.dialogues import DIALOGUES  # noqa: E402
from evals.world import World  # noqa: E402
from v2.converse import Engine  # noqa: E402
from v2.store import Store  # noqa: E402

START = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)  # Thursday 9 AM Eastern


def grade_turn(turn: dict, calls: list[str], cards: list[str], reply: str, handoff: bool = False) -> list[str]:
    misses = []
    if turn.get("handoff") != handoff and (turn.get("handoff") or handoff):
        misses.append("expected a handoff to v1" if turn.get("handoff") else "handed off to v1 unexpectedly")
    for c in turn.get("calls", []):
        if c not in calls:
            misses.append(f"expected {c}")
    for c in turn.get("not_calls", []):
        if c in calls:
            misses.append(f"should not call {c}")
    for c in turn.get("cards", []):
        if c not in cards:
            misses.append(f"expected a {c} card")
    if turn.get("no_cards") and cards:
        misses.append(f"unexpected cards {cards}")
    says = turn.get("says")
    if says and not any(s.lower() in reply.lower() for s in says):
        misses.append(f"reply lacks any of {says}")
    return misses


def run_one(d: dict, client_factory=None) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        world = World()
        store = Store(root / "state" / "v2.db")
        now = START
        out = {"id": d["id"], "turns": [], "cost": 0.0}
        for i, turn in enumerate(d["turns"]):
            now = now + timedelta(hours=turn.get("after_hours", 0), minutes=2)
            engine = Engine(root, world, store=store, now=lambda now=now: now,
                            **({"client_factory": client_factory} if client_factory else {}))
            seen = len(world.calls)
            cards_before = _cards(root)
            reply = engine.handle("D-eval", turn["say"], f"{d['id']}:{i}")
            calls = [c[0] for c in world.calls[seen:]]
            cards = [c["action_class"] for c in _cards(root)[len(cards_before):]]
            text = reply.text if reply else ""
            misses = grade_turn(turn, calls, cards, text, bool(reply and reply.handoff))
            out["turns"].append({"say": turn["say"], "calls": calls, "cards": cards, "reply": text[:400],
                                 "misses": misses, "cost": reply.cost if reply else 0})
            out["cost"] += reply.cost if reply else 0
        out["passed"] = all(not t["misses"] for t in out["turns"])
        store.close()
        return out


def _cards(root: Path) -> list[dict]:
    path = root / "state" / "pending-approvals.json"
    return json.loads(path.read_text(encoding="utf-8"))["pending"] if path.exists() else []


def main(argv: list[str]) -> int:
    chosen = [d for d in DIALOGUES if not argv or d["id"] in argv]
    results = []
    for d in chosen:
        r = run_one(d)
        results.append(r)
        mark = "PASS" if r["passed"] else "FAIL"
        why = "; ".join(m for t in r["turns"] for m in t["misses"])
        print(f"{mark} {r['id']:<26} ${r['cost']:.4f} {why}")
    passed = sum(r["passed"] for r in results)
    total_cost = sum(r["cost"] for r in results)
    print(f"\n{passed}/{len(results)} passed ({passed / max(1, len(results)):.0%}), ${total_cost:.3f}")
    (ROOT / "evals" / "last-run.json").write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "passed": passed, "total": len(results),
         "cost": round(total_cost, 4), "results": results}, indent=2), encoding="utf-8")
    return 0 if passed / max(1, len(results)) >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
