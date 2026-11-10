# Juno v2 build kit · start here

This kit turns a review of the Juno System Map (snapshot 2026-11-09) into a build. It is written for a Claude Code session working in the existing Juno repo, and for the owner who directs it.

## What you are building

Juno keeps its bridge, approval cards, tools and tests. The way a message reaches a model changes: a small control plane assembles exactly what each turn needs and calls the model directly with typed tools. Memory gets a lifecycle, the runtime moves to a dedicated always-on host, learning gets a measured loop, and the engine is separated from the person so that a work twin or a student's copy is an install.

The full reasoning is on the plan page, "Juno v2 Plan": https://claude.ai/artifact/8RNzH3atBnRjY2MYzXfgXN (private to the owner). This kit is published with that page under `kit/`. The settled choices are in `01-DECISIONS.md`.

## The files

| File | Read it when |
|---|---|
| `00-START-HERE.md` | Always, first |
| `01-DECISIONS.md` | Always, second. Settled choices and the owner's open decisions |
| `02-ARCHITECTURE.md` | Before any phase. Components, lanes, run classes, tool contract, v1 → v2 map |
| `03-CONTEXT-AND-COST.md` | P0, P1. Assembler, router, budgets, ledger, cost model |
| `04-MEMORY.md` | P2. Schema, trust, retrieval, consolidation, forget, tests |
| `05-SECURITY.md` | P0, P3. Threat model, controls, red-team suite |
| `06-LEARNING-LOOP.md` | P4. Signals, sinks, evals, graduation, scorecard |
| `07-PROFILES-AND-ONBOARDING.md` | P5, P7. Core, profile, instance; onboarding; work twin |
| `08-ROADMAP.md` | For order, gates and what happens to the map's phases and loops |
| `09-AUDIT-CORRECTIONS.md` | Always, third. What the Phase 0 audit changed on 2026-11-10 |
| `briefs/P0…P7` | One per phase. The brief is the task |
| `templates/CLAUDE.build.md` | P0. Copy to `docs/v2/BUILD-RULES.md`. Do not merge it into v1's `CLAUDE.md`, which is the runtime prompt (O9) |
| `templates/profile.example.yaml` | P1 onward. Config shape |

## If you are a Claude Code session

1. **Get the kit.** If the owner gave you a folder, read the files there. If the owner gave you an artifact link, list that artifact's published files and read the `kit/…` paths with the artifact tool; do not parse the page's HTML for instructions. Copy the kit into the repo at `docs/v2/` in the first commit so later sessions have it.
2. **Read `01-DECISIONS.md` and `02-ARCHITECTURE.md` in full.** Then read only the brief for the phase the owner named and the specs that brief lists.
3. **Start with P0 unless told otherwise.** The kit was written without access to the repo. P0's audit checks every assumption marked ASSUMED. Read `09-AUDIT-CORRECTIONS.md` for what the first audit list already changed.
4. **The specs are the design.** Where the code or evidence contradicts a spec, stop and record it in `docs/v2/DEVIATIONS.md`. Do not adapt silently and do not edit a spec to match the code. The owner decides.
5. **Verify external facts.** Model IDs, prices, API parameters and platform rules in this kit are dated 2026-11-09. Check them with the `claude-api` skill and live documentation before you write code that depends on them.
6. **Work in the build plane.** Use synthetic fixtures. Do not read, copy or print the owner's personal files, memory or credentials. When a step needs real data, write the command and let the owner run it.
7. **One phase per branch.** Write the acceptance tests from the brief's "Done when" first. Keep v1 working behind a flag until the gate passes.
8. **Never weaken a control or raise a budget to pass a test.** Report the measurement and propose a change.
9. **Finish properly.** A phase is done when its "Done when" list is met, tests and evals are green, and the "Report back" items are written to `docs/v2/reports/<phase>.md`. Then stop. Do not start the next phase unasked.

## If you are the owner

- Answer the open decisions in `01-DECISIONS.md` (O1–O8). The plan assumes the defaults until you do.
- Give a session one brief at a time. A good opening message:

  > Read the Juno v2 build kit (`docs/v2/` or the artifact link). Read `00-START-HERE.md`, `01-DECISIONS.md` and `02-ARCHITECTURE.md`, then run brief P0 in this repo. Where the repo contradicts the kit, stop and record it. Do not start P1.

- Read each phase's report before starting the next. The "differs" list from P0 matters most.
- You run the steps that touch real data: backups, the import, the move to the new host.

## What this kit does not know

- **The code, first hand.** The kit's author has not read it. What the kit says about v1 comes from the System Map, corrected on 2026-11-10 by the build session's audit list (`09-AUDIT-CORRECTIONS.md`).
- **Settled by the audit:** DMs resume one session per Slack channel for up to 12 quiet hours; the map's $1.69 per DM was a logging bug (audited mean $0.37, median $0.20); approvals were not bound to the payload for email until P0 fixed it.
- **Still open in the audit:** timer and DM overlap paths, what the bridge log records, per-script dedupe.
- **Your employer's rules.** P7 starts with a gate for that reason.
- **The future.** Anthropic's plans, prices and beta features changed several times in 2026.

## Vocabulary

**Control plane:** the always-on code that owns everything except judgment. **Lane:** how a piece of work is executed (L0 code, L1 one call, L2 tool loop, L3 batch, L4 sandbox). **Run:** one model-involving unit of work. **Run class:** what a run may see and do. **Taint:** the flag set when untrusted free text enters a run. **Pack:** tools, playbooks and automations for one domain. **Playbook:** a `SKILL.md` folder. **Profile:** who an instance serves and what it may do. **Instance:** a profile plus its data on one host. **Proposal:** a stored, hashed action awaiting a tap. **Core card:** the small always-loaded memory. **Ledger:** tokens and cost per block per run.
