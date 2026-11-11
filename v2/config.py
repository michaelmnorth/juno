"""Pinned models, budgets and prices. Verified with the claude-api skill on 2026-11-10 (cached model table dated
2026-11-03). The kit puts these in a per-instance profile.yaml; that split is P5, so P1 keeps them here and lets
`JUNO_V2_*` environment variables override the models for an experiment."""
from __future__ import annotations

import os
from dataclasses import dataclass

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"

MODELS = {
    "router": os.environ.get("JUNO_V2_ROUTER_MODEL", HAIKU),
    "reader": os.environ.get("JUNO_V2_READER_MODEL", HAIKU),
    "converse": os.environ.get("JUNO_V2_CONVERSE_MODEL", SONNET),
}
EFFORT = {"router": "low", "reader": "low", "converse": os.environ.get("JUNO_V2_CONVERSE_EFFORT", "low")}

# $ per million tokens: input, output, cache read. Cache writes are 1.25x input (5 minutes) or 2x (1 hour).
# Haiku 5.5 prices are for prompts up to 100K tokens, which every v2 request is by design.
PRICES = {
    HAIKU: (0.10, 0.50, 0.01),
    SONNET: (2.00, 10.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 0.20),  # the server-side refusal fallback for Sonnet 5.5
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}


@dataclass(frozen=True)
class Budget:
    dollars: float
    calls: int


# 03-CONTEXT-AND-COST.md "Budgets and breakers". The $3-a-day pause is not here: DV9 (Michael 2026-11-10) replaced
# it with spend notices at $5 and $10 that never stop a run (gateway/brakes.py).
BUDGETS = {
    "l1": Budget(0.05, 1),
    "l2": Budget(0.50, 8),
    "deep": Budget(2.00, 16),
    "router": Budget(0.01, 1),
    "reader": Budget(0.02, 1),
}

# Token budgets per assembled block (03-CONTEXT-AND-COST.md, the assembler table).
BLOCK_BUDGETS = {
    "tools": 1500, "constitution": 700, "core": 1200, "playbook": 900, "operator": 150,
    "snapshot": 300, "memory": 1200, "summary": 400, "working_set": 200, "turns": 1500,
}
FIRST_REQUEST_TARGET = 8000
TOOL_RESULT_TOKENS = 800
MAX_OUTPUT = {"router": 512, "reader": 1024, "converse": 4096}
THREAD_IDLE_HOURS = 24  # a quiet thread closes: its taint clears; summary and working set carry over
RECENT_TURNS = 6
