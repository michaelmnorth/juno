# 06 · Learning loop

"Learns from me" has to mean something measurable: **over time Juno needs fewer corrections, costs less per useful result, and asks for fewer taps, and a weekly number shows it.** This spec defines the signals, where learning is stored, how a change is proven, and what learning is never allowed to change.

## What v1 has (ASSUMED) and what is missing

v1: a weekly reflector (Mirror) proposes lessons from logs, reactions and corrections; the owner approves each; draft edits are compared and feed later drafts; five lessons saved. Proposed and not built: edits become tests, a weekly scorecard, a gap detector.

Missing:

- **A measure.** The phase gate counts lessons saved, not whether behaviour improved.
- **Structure.** Lessons are prose in the prompt. At fifty they conflict, cost tokens on every run, and nobody can say which one helped.
- **Signals.** Much of what the owner does in response to Juno is not recorded as data.
- **Evals.** Nothing stops a prompt change or a model update from quietly making drafts worse.
- **A link to cost.** Learning never makes Juno cheaper.

## Signals

Captured by the control plane, in code, at zero tokens. One row in `signals` each.

| Signal | Captured when | Used for |
|---|---|---|
| `draft.sent_asis` / `draft.edited` (with diff and edit distance) / `draft.discarded` / `draft.ignored` | The owner acts on a draft, or 24 hours pass | Voice examples, compose evals |
| `approval.approved` / `denied` / `expired`, time to decision | Card resolved | Earned autonomy, proposal quality |
| `ping.acted` / `ping.dismissed` / `ping.ignored`, "not useful" tap | After a proactive message | Ping rules, brief content |
| `feedback.up` / `feedback.down`, reaction emoji | Reaction on a Juno message | General quality |
| `correction.fact` / `correction.behaviour` | Router intent `feedback` ("no, …", "stop doing …", "always …") | Facts, rules, lessons |
| `repeat.question` | Same question within 7 days | Memory and retrieval misses |
| `override` | Owner undid or redid something Juno did or proposed | Planning quality |
| `run.error`, `run.over_budget`, `run.slow` | From the ledger | Reliability |

Signals that originate in tainted runs are flagged and cannot create rules or lessons without a tap.

## Where learning is stored

Three sinks. Use the first one that fits.

1. **A rule.** Deterministic preferences become entries in `rules.yaml`, evaluated by code: sender or domain → label and never ping; no pings during a calendar block; batch receipts into the evening check-in. A rule costs no tokens forever.
2. **An example.** For writing in the owner's voice, store accepted before/after pairs keyed by recipient class and message type. The compose prompt gets the two or three nearest pairs. Examples teach voice better than descriptions of voice.
3. **A scoped lesson.** One or two sentences attached to a playbook, an entity or a channel. Loaded only with that scope. At most 7 active lessons per scope; the eighth forces a merge or a retirement.

Facts about the world go to memory (`04-MEMORY.md`), not here.

## Lifecycle

```
signal(s) ──► candidate ──► shadow ──► active ──► retired
               (reflect)   (eval run)   (in use)   (stale, contradicted, or regressed)
```

- **Candidate.** The nightly or weekly `reflect` job proposes a rule, example or lesson with its evidence (signal IDs) and at least one eval case built from that evidence.
- **Shadow.** The eval suite runs with and without the candidate in the batch lane. It must fix its own case and must not break others.
- **Active.** Low-risk classes activate automatically and appear in the weekly digest with a one-tap undo: formatting and tone, noise filters, ping suppression, brief ordering. Everything that changes what is sent to other people, what is treated as urgent, or how money, health or legal items are handled needs a tap.
- **Retired.** No supporting signal for 90 days, a contradicting correction, or a failed eval.

Every active item has an owner eval case. An item without one is a bug.

## Evals

Built from real traffic, stored in the instance directory (they contain personal data), plus synthetic fixtures in the code repo.

| Set | Case | Grader |
|---|---|---|
| **Triage** | A real email's features → the label and ping decision the owner's behaviour implied | Exact match |
| **Compose** | Thread + owner's final sent text | Edit distance to the owner's version, plus a rubric grade (facts right, ask answered, length, tone) |
| **Routing** | Owner message → intent, lane, playbook | Exact match |
| **Recall** | Probe → fact present in assembled context | No model (`04-MEMORY.md`) |
| **Safety** | Red-team fixtures | Assertions (`05-SECURITY.md`) |
| **Dialogue** | Scripted multi-turn exchanges with follow-ups | Assertions on tool calls and final state |

When to run:

- On every change to a prompt, playbook, rule set, tool description or the model table. A failing suite blocks the change.
- Weekly, in the batch lane, against the live configuration.
- Before any model upgrade or demotion.

Start small. Twenty good cases per set beat two hundred weak ones. Grow the sets from signals: every edited draft and every correction is a candidate case.

## The graduation ladder

Each intent and task sits on a rung:

```
opus ──► sonnet ──► haiku ──► rule
```

- `reflect` proposes moving a task **down** a rung when the cheaper rung matches the current one on at least 30 recent cases in shadow.
- A regression in the weekly evals moves it back **up** and opens a note in the scorecard.
- When behaviour on a task is fully predictable from features (this sender, this label, always this action), `reflect` proposes a rule and the model leaves the path.

This is the link between learning and cost: what Juno has learned well gets cheaper.

## Earned autonomy

Taps are a cost too. For a **narrow, reversible** action shape (accept invites from family; file receipts under a label; hold gym blocks), when the last 20 proposals of that shape were approved without edits, Juno proposes auto mode for it.

- The owner opts in per shape. The setting is written to the profile, not learned silently.
- Auto actions are listed in the evening check-in with undo.
- One denial or undo drops the shape back to tap.
- Never eligible: money, first contact with a new person, anything on behalf of an employer or client, deletions, anything in a tainted run.

## Weekly scorecard

Computed by code from signals and the ledger. One model sentence at most.

- Drafts: sent as-is %, median edit distance, trend over 4 weeks.
- Proposals: approved %, denied %, median time to decision.
- Pings: acted %, dismissed %, ignored %.
- Memory: repeat-question count, corrections, facts added / superseded / retired.
- Cost: per owner DM (p50, p95), per accepted outcome, total; share of work in L0 and L1.
- Reliability: brief on time, failed runs, over-budget runs, uptime.
- Changes: items activated, retired, graduated; evals passed and failed.

A phase gate that says "N lessons saved" is replaced by "edit distance flat or falling for three weeks" and "no active item without an eval".

## What learning may never change

- The tool registry, tiers, recipient rules, budgets, quiet hours, or the kill switch.
- The constitution block of the prompt.
- Anything in another instance.

Those are profile and code changes, made by the owner through the build plane.
