# Brief P4 · Learning loop

**Hand this to a Claude Code session after Phases 1 and 2 have exited.** Read `06-LEARNING-LOOP.md` in full. Signal capture started in Phase 0, so there is history to build from.

## Goal

Juno improves on a measured loop: signals become rules, examples or scoped lessons; every change is proven against evals; tasks move down the cost ladder when the evidence allows; a weekly scorecard shows the trend.

## Deliverables

1. **Signals complete** for every row of the table in `06-LEARNING-LOOP.md`, with the tainted flag.
2. **Golden sets** built from captured traffic, at least 20 cases each: triage, compose, routing, dialogue. Stored in the instance directory. Synthetic equivalents in the repo so CI can run without personal data.
3. **Eval runner** in the batch lane with graders: exact match, edit distance plus rubric for compose, assertions for dialogue and safety. Use the `claude-api` skill's eval guidance for the health checklist.
4. **CI gate:** a change to a prompt, playbook, rule set, tool description or the model table runs the affected sets and blocks on regression.
5. **Rules engine:** `rules.yaml` evaluated in code before any model, with a dry-run mode that reports what a new rule would have done on last week's traffic.
6. **Examples store** and nearest-pair retrieval inside the compose playbook's budget.
7. **Lesson lifecycle:** candidate, shadow, active, retired, with the 7-per-scope limit, evidence links and an owner eval case for each.
8. **Reflect jobs:** nightly candidates; weekly review that proposes merges, retirements and graduations.
9. **Weekly scorecard** computed by code and delivered with the Sunday review.
10. **Graduation proposals** with shadow results attached.
11. **Earned autonomy** mechanism, switched off by default, with the eligibility rules and exclusions enforced in the policy engine.

## Done when

- Three weekly scorecards were produced with no manual step.
- At least one task moved down a rung with eval parity on ≥ 30 cases, or a written finding that none qualifies and why.
- No active rule, example or lesson exists without an eval case. A test enforces it.
- A deliberately bad prompt change is blocked by CI.
- Median draft edit distance is flat or falling across three weeks.
- A tainted signal cannot create an active item. A test enforces it.

## Guardrails

- Learning never touches the tool registry, tiers, recipient rules, budgets, quiet hours, the constitution block or another instance.
- Do not let lessons become the dumping ground. Prefer a rule, then an example.
- Keep graders cheap and stable. Pin the grader model. A grader change is itself a change that needs review.
- Every eval run that calls a model costs money. Show the owner the estimated cost before the first full run, and use the batch lane.
- Do not auto-enable any earned-autonomy shape.

## Report back

The first three scorecards, set sizes and pass rates, what graduated, what was retired, the cost of a full eval run, and the signals that turned out to be noise.
