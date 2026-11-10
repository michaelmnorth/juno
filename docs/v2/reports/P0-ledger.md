# P0 · v1 token ledger (first cut, 2026-11-10)

**Method.** `docs/v2/reports/ledger_v1.py` reads the `usage` blocks of the bridge's Claude Code session files
(`~/.claude/projects/<repo>/*.jsonl`, entrypoint `sdk-cli`, plus `subagents/`). It prints only numbers and a
run kind (a DM is a user turn containing `[Slack DM from Michael]`; jobs are matched by their fixed prompt text).
It never prints message text. Dollars come from `state/costs.jsonl`, corrected for the running-total bug
(AUDIT section 2). Window: 2026-11-07 03:56 UTC to 2026-11-10 16:00 UTC.

**Coverage against the gate.** 44 DM turns, not yet the 50 DMs or 7 days the brief asks. From now on every run
logs its own cost, tokens and session ID, so the gate fills itself; rerun the script on 2026-11-17.

## Per kind

| Kind | Runs | First-call input p50 (max) | Model calls p50 | Subagent calls p50 | Input tokens (main + sub) | Cache read share | Output |
|---|---|---|---|---|---|---|---|
| DM | 44 | 116,622 (227,488) | 3.5 | 0 (6 turns used them) | 21.98M + 0.50M | 94% | 109,520 |
| Sweep | 27 | 40,682 (44,597) | 12 | 2 | 21.20M + 0.86M | 89% | 267,070 |
| Morning brief | 4 | 39,281 | 9 | 7.5 | 1.67M + 0.42M | 82% | 31,850 |
| Evening check-in | 3 | 40,900 | 6 | 0 | 0.87M | 87% | 6,982 |
| Weekly reflection | 1 | 40,771 | 13 | 69 | 0.65M + 1.89M | 84% | 97,642 |
| Handoff | 1 | 101,409 | 1 | 0 | 0.10M | 0% | 413 |

Fresh sessions, first call minus the prompt (everything loaded before the owner's words): 33K–49K, median ≈ 41K,
the same on Haiku, Sonnet and Opus.

## Dollars (corrected)

| Kind | Runs | Logged | Real (est.) | Per run |
|---|---|---|---|---|
| DM | 37 | $97.79 | ≈ $13.75 | mean $0.37, p50 $0.20, p90 $1.31, max $2.53 |
| Weekly reflection | 1 | $1.38 | $1.38 | |
| Morning brief | 3 | $0.78 | $0.78 | $0.26 |
| Sweep | 19 | $0.59 | $0.59 | $0.03 |
| Evening check-in | 2 | $0.36 | $0.36 | $0.18 |
| Approval, handoff | 5 | $2.53 | well under $0.50 (resumed: logged as running totals) | |

About $17 over 2.2 days of heavy use, ≈ $7.70 a day, against a $15-a-month target. These are API-equivalent
figures; the runs drew on the subscription.

## The top three token sinks

1. **The resumed DM transcript.** A DM call carries 117K tokens at p50 (41K of prefix + ≈ 76K of history), 3.5 calls
   a turn, on Opus until today. 1-hour cache writes of the growing transcript (1.31M tokens) are most of the DM bill;
   cache reads (21.2M) are most of the tokens.
2. **The ≈ 41K-token harness prefix on every run.** CLAUDE.md and its imports are ≈ 7.3K of it; the rest is the
   Claude Code system prompt, tool and connector definitions, and the agent and skill listings. The kit's target for a
   whole DM request is 8K.
3. **Tool loops on timers.** A sweep makes 12 model calls at p50, each carrying the prefix: 22M input tokens across 27
   sweeps (cheap on Haiku: $0.03 a sweep). The weekly reflection fanned out to 69 subagent calls (1.9M tokens).

## What it means for Phase 1

DM cost is about a seventh of what the map said, so the cost case for P1 is weaker than the kit states (DV1). The
token shape still argues for it: a stateless, assembled turn removes sink 1 and most of sink 2. The interim fixes
(Sonnet 5.5 at low effort for DMs, pinned IDs) should cut DM dollars by roughly half before P1 starts; the next
ledger run will show it.

## The prefix, split (2026-11-10, P0 added item 8)

Seven `claude -p "Reply with the single word OK."` calls on Haiku 5.5 from the repo, each turning one more thing
off, in the same environment as a DM run. Total input (fresh + cache write + cache read) of the one call. $0.036
for all seven. The kit asked for the token counting endpoint; that needs an API key (O1), so this uses the CLI.

| Configuration | Tokens | Removed |
|---|---|---|
| Full DM run: all built-in tools, connectors, skills, agents, CLAUDE.md | 58,612 | |
| minus connectors (`--strict-mcp-config`) | 55,225 | 3,387 |
| minus the skills listing (`--disable-slash-commands`) | 56,674 | ≈ 0 (noise) |
| minus the Agent tool and agent listing | 52,260 | 4,414 |
| minus every built-in tool (`--tools ""`) | 15,753 | **36,507** |
| minus the Claude Code system prompt (`--system-prompt`) | 12,353 | 3,400 |
| same, from an empty folder (no CLAUDE.md, imports or project memory) | 888 | 11,465 |
| **P0 setting: only the 12 built-in tools Juno uses** | **41,342** | 17,270 from the full run |
| (for scale) 8 tools, no shell or web | 35,213 | |

Notes:

- This run measured 58.6K where the session files showed a 41K median for fresh bridge sessions. The bridge's
  environment differs from a Code-tab child process (CLI version, feature flags); the split is the finding, not the
  absolute number. The 2026-11-17 ledger rerun shows the bridge's own prefix after the trim.
- Connectors are cheap because they load as deferred names behind ToolSearch.
- The 12 kept tools are the ones 45 bridge sessions used (Bash, Read, Edit, Write, PowerShell, Grep, Skill, Agent,
  Glob, ToolSearch) plus WebSearch and WebFetch for Scout. Live check after the change: Scout fetched a page, the
  Gmail connector was found. `JUNO_TOOLS=all` restores the full set.
