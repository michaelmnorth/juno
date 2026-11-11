# Deviations: where the repo contradicts the kit

Recorded by the P0 build session, 2026-11-10. The specs were not edited; the owner decides each item.

## DV1 · v1's DM cost was overstated about 7× (affects 01 D1 and D11, 03 "What v1's numbers say", 08)

The cost log summed `total_cost_usd`, which for a resumed `claude -p` session is the session's running total.
Real DM cost over 37 DMs (Nov 8–10): ≈ $13.75, mean $0.37, p50 $0.20, p90 $1.31, against a logged $97.79
(System Map: $1.69 per DM, 91% of spend). The extrapolations of $500–1,000 a month are about $150–200 at the
same pace, during a heavy build weekend.

What still holds: every run carries a ≈ 41K-token harness prefix (target: ≤ 8K for a whole DM), and resumed DM
context reaches 117K at p50. D1's direction stands on safety, conversation and cost per turn; the urgency on cost
is lower. The brief anticipated this ("Phase 1 may shrink").

## DV2 · CLAUDE.md is the runtime's prompt, so the build rules were not merged into it (affects templates/CLAUDE.build.md, 00 step 1)

The template says "the Juno runtime never reads this file". In v1 every Juno run loads CLAUDE.md. Merging the build
rules would add ≈ 600 tokens to every run and hand the runtime build-plane instructions. They are kept in
`docs/v2/templates/CLAUDE.build.md`; build sessions are told to read it. Options for the owner: (a) keep it like
this until P1 moves the runtime off CLAUDE.md, (b) a `.claude/rules/` file only build sessions load, (c) merge anyway.

**Resolved 2026-11-10:** the kit's O9 chose `docs/v2/BUILD-RULES.md`, named in each build session's opening prompt.

## DV3 · Build plane and runtime plane are one folder (affects 00 step 6, 05 control 7, templates/CLAUDE.build.md)

The code repo is also the instance directory: the personal layer (`me/`, `people/`, `observed/`, `learnings/`,
`state/`, `data/`) sits git-ignored inside it, and Code-tab sessions with the owner run in the same project as the
bridge's Juno runs. Session transcripts of both share one folder. A build session cannot avoid the instance
directory until P3 (host) or P5 (core/instance split) separates them. P0 measured sizes and usage numbers only.

## DV4 · The proposal is written by the model, not by the control plane (affects 02 Approvals, 05 control 3 step 2)

The kit's protocol has the control plane canonicalise and store the proposal. In v1 the model appends the entry to
`state/pending-approvals.json`. P0 hashes the entry when its card is posted and checks the hash on the tap, which
closes the "changed after the card" gap; it does not make the model's entry trustworthy at creation. That needs
typed propose-action tools (P1).

## DV5 · Four agents point at scripts that don't exist (affects 02 v1 → v2 map)

`tools/scheduling-engine/` (Tempo), `tools/finance_query.py` (Ledger), `tools/health_*` and `withings_*` (Rep),
`tools/notify.py` (Ping). The map lists them as built. Rep's Hevy and sheet parts work; Ledger and Ping cannot run.

**Fixed in P0:** Tempo uses the new `tools/slots.py`; Rep uses `hevy_pull.py` and `sheets.py` and says sleep,
weight and macros aren't connected; Ledger says money data isn't connected; Ping is removed. A test checks that
every script an agent names exists.

## DV6 · `gmail.modify` scope (affects 05 control 6)

The one Google app holds `gmail.modify`, which can send. Handlers expose only drafts, `Juno/` labels, send-to-self
and the approved send; the scope itself is broader than the tools. Narrowing it means a second OAuth client.

## DV7 · The prefix is mostly built-in tool definitions, not connectors or listings (affects 03 "Still to measure")

Measured 2026-11-10 with CLI toggles on Haiku 5.5, one "Reply OK" call each (`reports/P0-ledger.md`). Of a 58.6K
prefix: built-in tool definitions 36.5K, the Agent tool and agent listing 4.4K, connectors 3.4K (they load as
deferred names), the Claude Code system prompt 3.4K, CLAUDE.md with its imports and memory 11.5K; the skills
listing ≈ 0. P0 cut the built-in set to the 12 tools Juno's runs use (58.6K to 41.3K). The kit's 8K target still
needs P1: the rest is the harness and Juno's own prompt.

## DV8 · No cap can stop one expensive call (affects 03 "Budgets and breakers", P0 added item 5)

`--max-budget-usd` counts only the current invocation, subagents included, even on `--resume` (CLI reference), and
is checked between steps against a client-side estimate. A bridge watching `stream-json` and killing the process
would check at the same points, since a call's input is billed when it starts. P0 uses the flag (DMs: $1.50 a
message; over it, the session resets so the next turn doesn't carry the long transcript). P1's per-call budget has
to work the same way: cap the request size before the call (assembler budgets), not the spend after.

## DV9 · No daily spend stop; notices at $5 and $10 (affects 03 "Budgets and breakers", 05 control 8)

The owner chose this on 2026-11-10, after the $3.00 daily cap paused his timers and answers on a normal day. Spend
never pauses anything now. The first time a day's runs pass $5.00, and again at $10.00, the bridge adds one line
with the dollars and tokens so far (`gateway/brakes.py` `NOTICE_AT_USD`). "pause" in the DM and the `state/PAUSED`
flag still stop everything, and the per-run turn and dollar caps (DV8) still end a runaway run. A work instance should
decide its own budget rule; this one is the owner's personal choice.

## DV10 · Per-block token counts are estimates (affects 03 "The assembler", Every block is measured)

The spec asks for per-block counts from the token counting endpoint or response usage, never a local guess.
Response usage gives only totals, and counting each block through the endpoint would add an API round trip per
block per turn. P1's assembler enforces block budgets on a characters ÷ 4 estimate before the call, writes those
estimates to the ledger's `tok_*` columns, and writes the real totals (input, cache writes, cache reads, output)
from response usage. When the gate run starts, calibrate the estimate once against `count_tokens` on a sample of
real requests and record the ratio here.

## DV11 · Tool sets per playbook, not per run class (affects 03 block 1)

Block 1 is "tool definitions for the run class". Every converse tool together is about 2,000 tokens against a
1,500 budget, so the router's playbook picks the set (calendar, mail, people, notes, general; `v2/tools.py`
`PLAYBOOK_TOOLS`), as the router section already implies ("intent and playbook choose blocks 1 and 4"). A test keeps
every set inside the budget. The cache is per set; a thread that moves between playbooks pays one prefix write.

## DV12 · The v1 baseline on the dialogue set is not automatic (affects the P1 brief, Done when 3)

The brief asks for the dialogue set to run on v1's resumed-session path first. The set runs against a synthetic
world through v2's typed tools (`evals/world.py`); v1 calls the real Gmail and Calendar scripts and has no seam for
a fake backend. Options: score v1 by hand on the same 22 scripts in a scratch Slack DM (about 50 messages), or
accept v2's absolute score with the 90% gate. Owner to choose before real DMs move.

## DV13 · v2 is the default engine and hands off to v1 (affects the P1 brief, deliverable 8; owner 2026-11-11)

The brief puts v2 behind a per-chat flag and says a failure answers with a ref and never falls back. The owner
asked to be fully on v2 with no engine switching. Now every DM goes to v2 first (`v2/config.py` `DEFAULT_ENGINE`).
v2 hands the message to v1 (`Reply.handoff`) in three cases only: the router sends it to "other" (health and the
coach sheet, money, YouTube, research: not ported); there is no API key yet; or the run failed before it touched,
proposed or did anything. A failure after the run acted is never handed off, so nothing happens twice; the owner
hears what was already done and the ref. v1's answer is kept as a turn in the v2 thread, which taints it (v1 may
have read mail, pages or transcripts), and v1's prompt carries the last few v2 turns. "use v1" still pins one chat
to v1 as a rollback. Until the key exists, every DM lands on v1 at no extra cost (no model call is made).

Effect on the gate: handed-off turns cost a router call plus v1 and are not v2 turns; the 7-day p50 and p95 are read
from the ledger rows of v2 runs only. The dialogue set grades the "unsupported" dialogue as a handoff.

## DV14 · DV12 resolved: v2's absolute score with the 90% gate (owner 2026-11-11)

The owner chose to be fully on v2 without a side-by-side v1 run, so the v1 baseline is skipped. The gate is the
dialogue set at 90% or better plus the 7-day cost targets.
