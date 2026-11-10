# 08 · Roadmap

A migration in phases. v1 keeps running until each gate passes. One phase per branch, one brief per phase (`briefs/`).

## Ordering logic

1. **Measure before changing** (P0). The kit was written from the System Map, not the code.
2. **Fix the path the owner uses most** (P1). Every DM turn carries a 41K-token harness prefix and a replayed transcript, in a run that can read files, fetch the web and hold mail text (audit, 2026-11-10). The earlier reason given here, "91% of spend", came from a logging bug; see `09-AUDIT-CORRECTIONS.md`.
3. **Get off the daily PC** as soon as the runtime no longer needs a subscription login (P3). In v1's plan, Phase 3's own gate could not pass until Phase 5 existed; here always-on comes early.
4. **Give memory a lifecycle** (P2), then **close the learning loop** on top of it (P4).
5. **Split the engine from the person** (P5) once the engine has settled, so the split is done once.
6. **Add surface last:** a second channel (P6), the work twin (P7).

P2 and P3 can overlap. Nothing else should.

## Phases and gates

| Phase | Delivers | Gate ("done when") | Brief |
|---|---|---|---|
| **P0 Stabilise and measure** | Audit of v1 against this kit; token ledger; quick safety fixes; backup; freeze | Top three token sinks named with numbers; backup restored; kill-switch and approval-binding tests pass; CI green | `P0` |
| **P1 Context engine** | Event queue, router, assembler, direct model calls with typed tools; DMs on the new path behind a flag | 7 days of real DMs at p50 ≤ $0.03 and p95 ≤ $0.20; ≥ 90% of follow-up dialogues pass; no general-purpose tool reachable | `P1` |
| **Quick packs** | Launch tracker, weekly goals pulse, wind-down nudge, dated reminders, all L0 or one L1 call | Each appears in the brief or check-in and costs under a cent a day | none; small tasks |
| **P3 Isolation and always-on** | Container on a dedicated host; pollers; scheduled jobs on the new lanes; run classes and taint enforced; red-team suite; runbook | 14 days unattended with the old PC off; brief on time ≥ 13 of 14; red-team 100%; restore drill done | `P3` |
| **P2 Memory** | Store, importer, budgeted retrieval, nightly consolidation, forget | Recall at budget ≥ 90% on ≥ 40 probes; forget and poisoning tests pass; 7 clean nights | `P2` |
| **P4 Learning loop** | Signals, golden sets, eval gate, rules, examples, lesson lifecycle, scorecard, graduation | 3 scorecards with no manual step; one task graduated or a finding why not; no active item without an eval | `P4` |
| **P5 Profiles and onboarding** | Core, packs and instance split; profile loader; onboarding and shadow mode; offboarding | Empty directory to first brief in ≤ 60 minutes; nothing personal in the repo | `P5` |
| **P6 Second channel** | One more channel adapter | Approvals work end to end on it; channel failover tested | `P6` |
| **P7 Work twin** | Gate record; skills-only twin; full instance only if justified | Gate recorded; each playbook used three times and rated | `P7` |

## Suggested calendar

A suggestion, built around the cohort launch on Dec 15. The owner sets the dates. **Changed 2026-11-10:** P1 moved after the launch (decision O6). It was placed before the launch because DMs looked like $500 a month with no conversation; the audit showed neither is true.

| When | What |
|---|---|
| Nov 10–17 | P0, including the items added after the audit. Backups first. Also set the two dated reminders the map lists as not yet set |
| Nov 18–Dec 5 | Quick packs on v1, launch tracker first. P1 may be built on its branch, with no real DMs moved. Buy or provision the host for P3 |
| Dec 6–15 | **Freeze.** Fixes only. Launch |
| After Dec 15 | P1 and its 7-day run on real DMs, then P3 (its 14-day gate runs while P2 is built), then P4, P5 |
| When the gate clears | P7. P6 any time after P3 |

Quick packs were written as L0 code or one L1 call. On v1, build them the way the coach-sheet job already runs: code first, then a single lean call with no tools.

## What happens to the map's existing phases

| Map phase | Disposition |
|---|---|
| 0 Foundations, 1 Slack, 2 Personal assistant | Kept. Their open gates (7 days of briefs, two weeks of drafts) keep running during P0 and P1 |
| 3 Hardened runtime | Folded into P0 (quick fixes) and P3 |
| 4a Health | Continue as a pack after P1. Apple Health export is an L0 importer; the Monday report is one L1 call |
| 4b Finance | After P3 only. Read-only aggregator; reports computed in code; finance is a restricted data class |
| 5 Always on | Becomes P3, moved early. "Roster as a plugin" becomes P5 and D12 |
| Juno as a person | Paused (O3). Revisit in P6 |

## What happens to the map's proposed loops

| Loop | Verdict | How |
|---|---|---|
| Weekly scorecard | Keep | P4. A ledger-only version can ship in P0 |
| Your edits become tests | Keep | Capture pairs from P0; evals in P4 |
| Launch tracker for Dec 15 | Keep, soon | Quick pack on v1, before the freeze: a checklist file, counted in code, one line in the brief |
| Weekly goals pulse | Keep | Quick pack: stored goals, checked in code against calendar and workouts |
| Wind-down nudge | Keep | L0, fixed text, before quiet hours |
| Event scan | Keep, reshape | A `research` run that receives the stated criteria and free evenings only; results return through `reader` |
| Cost guard | Superseded | P1's router and budgets replace it. Apply the model default change in P0 as a stopgap |
| Gap detector | Reshape | Count intents that had no playbook; propose a playbook. New tools remain a build-plane change |
| Errors become tickets | Reshape | Tickets from structured error codes only; the owner triages before any coding agent sees them |
| Overnight build queue | Defer and reshape | After P3. Isolated cloud sandbox, code repo only, items the owner marked "go", pull request, never merges |

## Stop doing

- Adding agents, skills or loops before P1 exits.
- Measuring progress by commits, lessons saved or agents built.
- Running anything new on the daily PC.
- Building the phone-and-WhatsApp track before P6.

## Risks to the plan

| Risk | Sign | Response |
|---|---|---|
| The audit finds v1 differs from the map in ways that change P1 | Many "differs" rows in `AUDIT.md` | Update the kit's specs with the owner before P1; do not adapt silently |
| Answer quality drops with small assembled context | Dialogue set below 90%; more corrections | Raise one block's budget with ledger evidence; add a retrieval slot; do not fall back to "load everything" |
| The rebuild crowds the launch | P0 still open on Nov 21 | Finish backups, the kill switch and the web-tool restriction; park the rest until after Dec 15 |
| v2 conversation is worse than v1's resumed session | v2 scores below v1 on the dialogue set | Do not move real DMs. Widen the thread block with ledger evidence, or keep v1's path for that intent |
| A cheaper model disappoints on voice | Compose edit distance rises | Stay on the higher rung for that task; the ladder moves both ways |
| The owner tires of taps | Approvals expiring unanswered | Bundle proposals; consider earned autonomy for reversible shapes only |
| Platform rules change again | A doc or price differs from the kit | The kit is dated; verify with the `claude-api` skill at the start of each phase |
