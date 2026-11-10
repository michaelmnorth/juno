# Brief P1 · Context engine and conversation

**Hand this to a Claude Code session in the Juno repo after Phase 0 has exited.** Read `01-DECISIONS.md`, `02-ARCHITECTURE.md`, `03-CONTEXT-AND-COST.md` and `docs/v2/AUDIT.md`.

## Goal

Owner DMs run through a new path: event queue → router → context assembler → L1 or L2 on the Messages API with typed tools. The v1 path stays available behind a flag. Scheduled jobs are not touched in this phase.

## Why now

Corrected 2026-11-10 (`09-AUDIT-CORRECTIONS.md`). The audit found that v1's DMs resume one Claude Code session per Slack channel, so follow-ups work today, at an audited mean of $0.37 and median of $0.20 per DM on Opus. Each turn carries a fixed prefix of about 41K tokens and a replayed transcript (median 117K), in a run that can read files, fetch the web and hold mail text.

This phase removes the general-purpose harness from the path the owner uses most, bounds what each turn carries, and makes budgets enforceable. The cost gain is real and smaller than first written. Because v1's conversation works, this phase must not make it worse. By decision O6, real DMs do not move to v2 before the Dec 15 launch.

## Deliverables

1. **Event queue and thread store** in SQLite: durable events with dedupe keys; threads with rolling summary, working set and recent turns.
2. **Tool registry** with `ToolSpec` wrappers around the existing scripts that DMs actually use (take the list from the Phase 0 logs, not from the full inventory). Typed inputs, compact capped results, tier, data classes, `returns_untrusted`.
3. **Policy engine, minimal:** registry per run class, tiers, budgets, kill switch, taint flag with enforcement at tool-call time. Reuse the existing approval cards and executor.
4. **Router:** L0 command table, then one structured-output call on Haiku 5.5.
5. **Assembler** exactly as specified: block order, per-block budgets, cache marks, per-block token counts written to the ledger. Until Phase 2, block 7 is filled by a thin adapter over the existing memory files with the same budget.
6. **Lanes L1 and L2.** Structured outputs for L1. A bounded tool loop for L2 with the run budget enforced by the control plane.
7. **`reader` class** for any DM that needs the content of a message or page: a no-tool structured call whose typed fields can enter `converse` without taint.
8. **Flag** to switch a DM thread between v1 and v2, and a clear error to the owner (with run ID) when v2 fails. No silent fallback.
9. **Dialogue test set:** at least 20 scripted multi-turn exchanges with a fake tool backend, covering follow-ups ("move that to 4", "yes, send it", "the other Sam"), corrections, and an action that needs a tap. Run the same set against v1's resumed-session path first and record the score as the baseline.

## Done when

- Seven consecutive days of real DMs on v2 with **p50 ≤ $0.03 and p95 ≤ $0.20** from the ledger.
- First request of a DM is ≤ 8,000 input tokens at p90, with every block inside its budget.
- Dialogue set ≥ 90% passing, and no lower than v1's resumed-session path scores on the same set; approval tests unchanged and green.
- A follow-up that arrives more than 12 hours after the last turn still resolves "that" and "it" from the thread store. v1 cannot do this, and it is the visible gain.
- A test asserts that no shell, file or generic HTTP tool is reachable from any v2 run.
- A tainted-run test: after untrusted free text enters, web tools are refused and a reversible action falls back to a tap.

## Guardrails

- Use the `claude-api` skill for every SDK call, model ID and parameter. Current models reject several older request shapes; do not code from memory.
- Pin exact model IDs and effort in config.
- Port only the tools DMs need. Everything else waits.
- Do not move memory, scheduled jobs or hosting in this phase.
- No new owner-facing features. The owner should notice that replies are faster, follow-ups work, and the cost line dropped.
- If a budget in `03-CONTEXT-AND-COST.md` cannot be met without hurting answers, report the measurement and propose a number. Do not quietly raise it.

## Report back

Ledger summary before and after (per DM, per block), cache read share, the dialogue failures that remain, the tools ported and not ported, and any decision the build argues against.
