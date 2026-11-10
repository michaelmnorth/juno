# 03 · Context and cost

How Juno v2 spends tokens. The rule is simple: **code assembles a small, exact context before the model runs; the model does not go looking for it.**

Prices and API behaviour below were read from Anthropic's live pricing page and API reference on 2026-11-09. Re-verify before building (use the `claude-api` skill; do not code from memory).

## What v1's numbers say

**Corrected 2026-11-10 from the Phase 0 audit** (`09-AUDIT-CORRECTIONS.md`). The System Map's cost table showed $1.69 per DM and 91% of spend on DMs. That was a logging bug: the log summed a resumed session's running total. The audited figures, which are the build session's report:

| Measure (37 owner DMs, Nov 8–10, on Opus 5.5) | Value |
|---|---|
| Cost per DM | mean $0.37 · median $0.20 · p90 $1.31 · max $2.53 |
| Fixed prefix on every run | 33K–49K tokens, median about 41K. `CLAUDE.md` and its imports are about 7.3K of that |
| Resumed transcript on a turn's first call | median 117K tokens, max 227K |
| Model calls per turn | about 3.5 (median) |
| Share of DM input read from cache | 96% |
| Main dollar cost | 1-hour cache writes of the growing transcript |

Scheduled jobs, from the map's table: sweeps $0.03, morning brief $0.26, check-in $0.17, weekly reflection $1.38 per run. These jobs start cold, so the bug should not affect them; the audit did not re-measure them.

- The scheduled jobs alone extrapolate to about **$27 a month** (8 sweeps, a brief and a check-in a day, a weekly reflection), which is already above the $15 target.
- DMs at the audited mean are about **$111 a month at 10 a day and $222 at 20 a day**, on Opus. On Sonnet 5.5 at low effort (applied in P0, not yet measured) list prices suggest about half.
- The sample is small and came from three build-heavy days. The P0 ledger replaces it.

The sweep path is cheap because code does the work and a small model sees one item. The DM path costs more because every turn carries a 41K harness prefix and replays the day's transcript, with about 3.5 calls per turn. Caching hides most of the price and none of the latency or the growth. **v2 makes the DM path look like the sweep path.**

Still to measure in P0: how the fixed prefix splits between harness, tools, connectors and listings (use the token counting endpoint), and per-subagent cost.

## The assembler

One function builds every request. Order is most stable first.

| # | Block | Changes | Budget (tokens) | Cache |
|---|---|---|---|---|
| 1 | Tool definitions for the run class | on deploy | ≤ 1,500 | in prefix |
| 2 | Constitution: role, safety rules, output style | on deploy | ≤ 700 | in prefix |
| 3 | Persona + core card | every few days | ≤ 1,200 | **breakpoint A** |
| 4 | Playbook body + its scoped lessons and examples | per intent | ≤ 900 | **breakpoint B** (L2 only) |
| 5 | Operator facts: now, timezone, quiet-hours state, taint state, budget left | every run | ≤ 150 | never |
| 6 | Situational snapshot: next events, open loops, pending approvals | every run | ≤ 300 | never |
| 7 | Retrieved memory: dossiers, facts, episodes (labelled by trust) | every run | ≤ 1,200 | never |
| 8 | Thread: rolling summary, working set of recent IDs, last turns verbatim | every run | ≤ 400 + 200 + 1,500 | never |
| 9 | The current message | every run | as sent | never |

Target for the first request of a typical DM: **≤ 8,000 input tokens.** Tool results are capped per tool (default 800 tokens) and paginated.

Rules:

- **Stateless turns.** Do not replay API message history across DMs. Each turn is a fresh request: stable prefix, then one user message that contains blocks 6–9. Inside one run the loop appends tool calls and results as usual and passes thinking blocks back unchanged. This avoids transcript growth and the history-editing constraints on current models.
- **Working set.** After each run, code extracts the IDs the turn touched (events, messages, people) into the thread's working set, so "move that to 4" needs no search.
- **Authority.** Blocks 1–5 are operator text. Blocks 6–8 are data and are delimited and labelled as data. Retrieved or learned text never goes in an operator-authority position, because memory can be poisoned. Where the model supports mid-conversation system messages, use that channel only for block 5.
- **Nothing volatile above a breakpoint.** No timestamps, IDs or per-run text in blocks 1–4. Serialise tool schemas deterministically.
- **Every block is measured.** The assembler records token counts per block in the ledger using the token counting endpoint or the response usage, never a local tokenizer guess.
- **Over budget is a bug.** If a block exceeds its budget the assembler truncates by priority within the block and records the overflow. It does not silently grow the request.

### Caching

Current behaviour to design around (verify): up to 4 breakpoints; minimum cacheable prefix 512 tokens on Haiku 5.5, Sonnet 5.5 and Opus 5.5; writes cost 1.25× (5-minute) or 2× (1-hour); reads cost 0.05× on Sonnet 5.5 and Opus 5.5 and 0.1× on Haiku 5.5; caches are per model.

- Breakpoint A on the stable prefix always. Choose the TTL from the measured gap between runs that share it: under 5 minutes use the default; 5–60 minutes use 1 hour; longer, accept the miss. For a sparse personal assistant the prefix is small, so a miss costs fractions of a cent. Do not build keep-alives.
- In L2, add automatic caching for the growing tail so the second and later calls of a loop read the first call's prompt from cache.
- In L1 single calls with a unique tail, mark only the shared prefix. An automatic breakpoint after unique content is a pure surcharge.
- Check `cache_read_input_tokens` in the ledger. Zero across repeated runs means a silent invalidator.
- Switching model mid-thread discards the cache. Route per intent, not per call.

## Router

L0 first: exact commands (`status`, `pause`, `resume`, `snooze`, approval taps, `forget …` confirmations) are matched in code.

Otherwise one L1 call on Haiku 5.5 with structured output:

```json
{ "intent": "calendar.change", "playbook": "calendar", "entities": ["Chris"],
  "memory_slots": ["routines", "person:Chris"], "needs_tools": true,
  "complexity": "standard", "data_classes": ["calendar"] }
```

- `intent` and `playbook` choose blocks 1 and 4. `entities` and `memory_slots` drive block 7. `needs_tools: false` sends the turn down L1 instead of L2.
- `complexity: deep` creates an asynchronous task: the owner gets "on it", the work runs with a larger budget, and the result arrives as a message.
- Low confidence falls back to a `general` playbook with the default tool set.
- The router sees only the owner's message and the thread summary. It never sees untrusted text.

### Model table

Lives in `profile.yaml`. Pin exact model IDs. A change must pass the eval suite.

| Role | Start with | Move down when |
|---|---|---|
| router, reader, extraction | `claude-haiku-5-5` | — |
| converse | `claude-sonnet-5-5`, effort `low` | An intent passes its evals on Haiku 5.5 (`06-LEARNING-LOOP.md`, graduation) |
| compose (owner's voice) | `claude-sonnet-5-5` | Per recipient class, on eval parity |
| reflect: nightly | `claude-sonnet-5-5` (batch) | Haiku 5.5 on eval parity |
| reflect: weekly review | `claude-opus-5-5` (batch) | Sonnet 5.5 on eval parity |

Start quality-first and demote with evidence. Before adding a second model to a path, measure the stronger model at lower effort: one model means one cache.

API notes that affect code on current models (verify): forced `tool_choice` is rejected on Sonnet 5.5 and Opus 5.5, so use structured outputs for JSON; thinking cannot be disabled on them, so control spend with `output_config.effort`; sampling parameters are rejected; handle `stop_reason: "refusal"`; pass thinking blocks back unchanged inside a loop.

## Budgets and breakers

Defaults in `profile.yaml`:

| Limit | Default | On breach |
|---|---|---|
| Per L1 call | $0.05 | Fail the run, record, tell the owner if it was owner-initiated |
| Per L2 run | $0.50, 8 model calls | Stop the loop, answer with what is known, say what was not done |
| Per deep task | $2.00 | Pause and ask to continue |
| Per day | $3.00 | Model lanes pause; L0 keeps running; one notice to the owner |
| Per month | alert at $40 | Notice in the weekly scorecard |

Caps are enforced by the control plane from its own ledger, computed from response usage and the current price table. They do not rely on the model pacing itself.

## Ledger

One row per model call:

```
run_id, call_idx, ts, lane, run_class, intent, model, effort,
tok_tools, tok_constitution, tok_core, tok_playbook, tok_operator, tok_snapshot,
tok_memory, tok_thread, tok_message, tok_tool_results,
input_tokens, cache_write_5m, cache_write_1h, cache_read, output_tokens,
searches, cost_usd, latency_ms, stop_reason, tainted
```

The numbers that matter weekly: cost per owner DM (p50, p95), cost per accepted outcome (a sent draft, an approved action, a brief that was read), cache read share, share of turns handled in L0 and L1, and tokens per block against budget.

## Expected cost

List prices per million tokens on 2026-11-09 ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)):

| Model | Input | Output | Cache read | Batch in / out |
|---|---|---|---|---|
| Haiku 5.5 (prompts ≤ 100K) | $0.10 | $0.50 | $0.01 | $0.05 / $0.25 |
| Sonnet 5.5 | $2 | $10 | $0.10 | $1 / $5 |
| Opus 5.5 | $4 | $20 | $0.20 | $2 / $10 |

Web search is $10 per 1,000 searches plus tokens. Web fetch has no extra charge.

Estimate at 20 DMs a day, Sonnet-first. These are design targets, to be replaced by ledger data after Phase 1:

| Item | Volume / month | Unit | Month |
|---|---|---|---|
| Router (Haiku) | 600 | $0.0002 | $0.12 |
| Converse turn (Sonnet, ~2 calls, ~8K in) | 600 | $0.03 | $18.00 |
| Reader per email (Haiku) | 750 | $0.0004 | $0.30 |
| Draft in owner's voice (Sonnet) | 240 | $0.014 | $3.36 |
| Brief and check-in (Sonnet, one call each) | 60 | $0.018 | $1.08 |
| Nightly consolidation (Sonnet, batch) | 30 | $0.055 | $1.65 |
| Weekly review (Opus, batch) | 4.3 | $0.36 | $1.55 |
| Research run (Sonnet, 5 searches) | 30 | $0.19 | $5.70 |
| Weekly evals (Sonnet, batch) | 4.3 | $0.90 | $3.87 |
| **Total** | | | **≈ $36** |

With simple turns graduated to Haiku 5.5 and research a few times a week, the same usage is about $15–25. v1 at the same volume, from the audited mean, is about $250 a month on Opus, and by list price about $140 on Sonnet at low effort (estimate, not measured).

Phase 1 exit targets: **p50 DM ≤ $0.03, p95 ≤ $0.20.**

## Things that silently burn tokens

- A timestamp, run ID or changing list inside the cached prefix.
- Adding or removing a tool mid-thread.
- Replaying the full conversation instead of summary plus last turns.
- Loading every lesson and every profile file "to be safe".
- Tool results that return raw API payloads.
- A coordinator model whose only job is to call another model.
- Retrying a failed run without changing anything.
- Running a model on a timer when a poller could tell that nothing changed.
- Using the batch discount for nothing: anything that can wait until night should.
