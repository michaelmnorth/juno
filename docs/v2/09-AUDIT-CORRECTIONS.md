# 09 · Corrections from the Phase 0 audit

Dated 2026-11-10. The kit was written on 2026-11-09 from the System Map, without the code. On 2026-11-10 the build session in the Juno repo sent back the first list from `docs/v2/AUDIT.md` (branch `v2-p0-audit`). This file records what that list changed. The affected kit files were edited the same day, so this file and the others agree.

**Standing of these facts.** They are the build session's report. The author of this kit has still not read the code. Figures marked "audit" are from that report; figures marked "estimate" are arithmetic on top of it.

## Two claims that were wrong

### 1. A DM does not cost $1.69

- **What the kit said.** $1.69 per DM, 91% of spend, $500 to $1,000 a month at 10 to 20 DMs a day.
- **What the audit found.** The cost log summed `total_cost_usd`, which for a resumed session is the session's running total. For 37 DMs on Nov 8–10 the log showed $97.79 and the real cost was about $13.75: mean $0.37, median $0.20, p90 $1.31, max $2.53. Those runs were on Opus 5.5, the account default, because DMs passed no model.
- **Corrected projection.** At the audited mean, DMs are about $111 a month at 10 a day and about $222 at 20 a day, on Opus. Timers add about $27 (those jobs start cold, so the bug should not touch them; the audit did not re-measure them).
- **After the P0 fix** (DMs on `claude-sonnet-5-5`, low effort): not yet measured. Sonnet lists at half of Opus per token, so about half if token counts hold (estimate): roughly $55 and $110 a month for DMs.
- **Caveat.** 37 DMs over three build-heavy days is a small, unusual sample. The P0 ledger replaces it.

### 2. Conversation does carry over

- **What the kit said.** Following the map's "chat history doesn't carry over", the kit treated DMs as cold starts and said there was no conversation.
- **What the audit found.** The bridge resumes one Claude Code session per Slack channel (`--resume`). The session closes after 12 quiet hours; a Haiku run writes a handoff note that opens the next one. Approval runs resume the session that asked.
- **What that means.** v1 has working follow-ups inside a 12-hour window. It pays for them by replay: a DM turn's first call carries a median of 117K tokens of transcript (max 227K) on top of a fixed prefix of 33K–49K (median about 41K), with about 3.5 model calls per turn. 96% of DM input is cache reads; the 1-hour cache writes of the growing transcript are the main dollar cost.

## What this does to the design

| Decision | Effect |
|---|---|
| **D1** Own the control plane | Stands. The cost case is smaller: v2's target is about 7 times cheaper than the audited median DM, not 50 times. The case now rests mainly on safety (no general-purpose tools in the path that reads mail), bounded context, and budgets that actually stop a run |
| **D3** Stateless turns | Stands, with a higher bar. v1's conversation works, so v2 must match it on the dialogue set before any real DM moves. `briefs/P1` now requires a v1 baseline on the same set |
| **D6** Payload-bound approvals | Confirmed as needed. The model wrote the proposal entry, and `email.send` was bound to a draft ID only. P0 has added a payload hash checked on the tap and a code-only send |
| **D7** Separate planes, dedicated host | Stronger. The code repo is also the instance directory, and build sessions share the transcript folder with Juno's runs |
| **D11** Design for API billing | Stands. One new fact: budget flags on `claude -p` do not stop a single expensive call (a handoff cost $1.75 against a $0.15 cap), and DMs had no cap |
| **O6** Timing against Dec 15 | Default changed. See below |
| **O8** Sonnet at low effort | Applied in P0 |

## Changed owner decisions

- **O6, new default: P0 before the launch, P1 after it.** P1 was scheduled before Dec 15 because DMs looked like $500 a month with no conversation. Neither is true. P1 is still the next structural step, and it can be built on its branch at any time, but moving real DMs before the launch now carries more risk than it removes.
- **O9, new: where the build rules live.** v1's `CLAUDE.md` is the runtime prompt, so merging `templates/CLAUDE.build.md` into it would add about 600 tokens to every Juno run. Default: keep the rules at `docs/v2/BUILD-RULES.md` and name that file in each build session's opening prompt. In v2 the runtime does not read `CLAUDE.md` at all, and the question goes away.

## Added to Phase 0

These come from the audit's "differs" list. They are in `briefs/P0-stabilize-and-measure.md` under "Added after the audit", which lists eight items: the six below, the build-rules file (O9), and two ledger measurements.

1. **Web tools out of runs that hold mail text or private memory.** The audit confirms WebFetch needs no tap in such runs. In v1 terms: web tools only in the research agent, which receives a question and nothing else.
2. **Remove unrestricted Bash from the YouTube agent's tool list.** The settings allow-list still limits commands, so this is defence in depth, and it is one line.
3. **Serialise runs that write state.** Nothing stops a timer and a DM from overlapping; JSONL appends have no locks and models write some state files directly. One run at a time per instance in the bridge is enough until P1's event queue.
4. **A per-run cost cap enforced by the bridge,** from the corrected per-run figure, since the CLI flag does not stop one expensive call.
5. **Delete or stub what agents point to and does not exist:** the scheduling engine (Tempo), `finance_query.py` (Ledger), the `health_*` and `withings_*` scripts (Rep), `notify.py` (Ping). An instruction that names a missing tool invites improvisation.
6. **Backups first.** The audit confirms there are none: the personal layer (about 40 MB) and the session transcripts exist only on the PC. Do this before any other quick fix.

Already done by the build session in P0: exact model IDs, DMs on Sonnet at low effort, per-run cost logging, payload hash on approvals, code-only email send, unfurling off, test discovery and CI.

## Things the audit confirmed

`claude -p --output-format json --permission-mode acceptEdits` in the repo folder, on the subscription login. Timer jobs start cold; sweeps have a wake gate in Python. 11 agents, 9 skills, 3 hooks, 76 deny rules (plus 26 allow, 4 ask). Calendar approvals use a one-time token: SHA-256 stored, 15-minute expiry, bound to class and recipients, spent after the write. Taps only from the allow-listed Slack user; a replayed tap is refused. Secrets through a 1Password service-account key in Windows Credential Manager, read inside fixed scripts.

## Worth testing in P1

The coach-sheet job already runs as a single lean call: `claude -p` with `--system-prompt`, `--tools ""`, `--strict-mcp-config` and one turn, at about a cent a run. That is lane L1 on the subscription login. If the owner prefers not to create an API key yet (O1), the router and other L1 calls could start on this invocation behind the same `Lane` interface. L2's typed tool loop still needs the Messages API. Not verified by this kit's author; the build session should measure the prefix of such a call before relying on it.

## Still unknown

Exact overlap paths between timers and DMs. What `bridge.log` records and whether secret-shaped strings reach it (there is no scrubber). Per-script dedupe on writes. How the fixed prefix splits between harness, tools, connectors and listings (count it with the token counting endpoint). Google OAuth holds `gmail.modify`, which can send; whether a narrower scope is workable.
