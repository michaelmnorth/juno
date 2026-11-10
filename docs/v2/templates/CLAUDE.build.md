# Rules for build sessions (copy to docs/v2/BUILD-RULES.md)

These rules apply to any Claude Code session that changes Juno's code. They do not apply to the Juno runtime.

**Do not merge this into v1's `CLAUDE.md`.** The Phase 0 audit found that file is Juno's runtime prompt, so these rules would be loaded into every Juno run. Keep them at `docs/v2/BUILD-RULES.md` and name that file in each build session's opening prompt (decision O9). While the code repo is also the instance directory, the rule below about instance data means: do not open the personal folders inside the repo.

## Planes

- **Build plane:** this session. Works on the code repo with synthetic fixtures.
- **Runtime plane:** the running assistant and its instance directory (`$JUNO_HOME/<instance>/`).
- Do not open, copy, print or move anything in an instance directory. Do not use the instance's credentials. If a task seems to need real data, stop and ask the owner to run the step.

## How to work

1. One phase per branch. Read that phase's brief and the specs it names before writing code.
2. Write the acceptance tests from the brief's "Done when" first.
3. The specs in `docs/v2/` are the design. If the code or the evidence contradicts a spec, stop and record it in `docs/v2/DEVIATIONS.md` with the reason. Do not adapt silently, and do not edit a spec to match the code.
4. Verify every Claude API call, model ID, parameter and price against current documentation with the `claude-api` skill. Do not write SDK code from memory.
5. Never weaken a security control or raise a budget to make a test pass.
6. Keep v1 working until the phase's gate says it can be switched off. Use flags; every phase has a rollback.
7. No personal data in the repo: no names, addresses, document IDs, phone numbers, real mail. CI checks this.
8. Do not add agents, tools, packs or dependencies a brief does not call for. Record ideas in `docs/v2/BACKLOG.md`.
9. A phase is done when its "Done when" list is met, tests and evals are green, the runbook and specs are current, and the "Report back" items are written to `docs/v2/reports/<phase>.md`.

## Never

- Give a model a shell, file tool or generic HTTP tool in the runtime.
- Let a model execute a side effect directly, or see an approval pass.
- Put learned or retrieved text in an operator-authority position in a prompt.
- Put timestamps or per-run values in a cached prompt prefix.
- Install plugins, skills or MCP servers into the runtime at run time.
- Merge your own pull request.
