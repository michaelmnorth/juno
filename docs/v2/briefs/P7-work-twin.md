# Brief P7 · Work twin

**Do not start a build from this brief until the gate below is recorded.** Read `07-PROFILES-AND-ONBOARDING.md`, section "The work twin".

## Goal

The owner gets the same kind of help at work, inside the employer's rules, without work and personal data ever sharing an instance, an account or a memory.

## Gate (owner and employer, not a coding session)

Record in `docs/v2/WORK-GATE.md`, with who confirmed it and when:

1. Which Claude deployment is approved for company and client data (plan, account, cloud provider, retention terms).
2. Which systems an assistant may read, and which it may write.
3. Retention, audit and client-confidentiality requirements.
4. Whether a self-hosted service may hold company credentials at all.

If any answer is "not yet", build Path A only.

## Path A · Skills-only twin (default)

Runs inside the employer's Claude plan with its admin-approved connectors.

Deliverables:

1. The work playbooks (call prep, post-call recap, weekly client notes, follow-up drafts, task extraction) as `SKILL.md` folders in a work pack, written to the same format the Juno runtime loads.
2. A plugin that bundles those skills and names the connectors they expect.
3. Scheduled tasks for the recurring ones (weekly notes; prep before the first call of the day), using the plan's own scheduler.
4. A one-page operating note: what it reads, what it never sends without the owner, where its outputs go.
5. Synthetic eval fixtures for each playbook (no client data in the repo).

Done when: each playbook has been used on three real occasions and rated by the owner; nothing client-facing was sent without the owner sending it; IT has the operating note.

## Path B · Full instance

Only after the gate allows a self-hosted service, and after Phase 5.

Deliverables:

1. A work profile created through onboarding on employer-approved infrastructure, with its own vault, channel app and API account.
2. Work packs with tools behind `ToolSpec`: every write visible to a client or colleague is T3b with no earned autonomy.
3. The `client_confidential` data class enforced: never in `research`, never leaves the instance, pointers only in logs.
4. Model access through the employer's account. Keep any hosted-agent feature behind the L4 interface so the core runs wherever the Messages API is offered.
5. Two shadow weeks, then a graduation review with the owner's manager or IT if required.
6. Offboarding drill before going live.

Done when: the red-team suite passes on the work profile; the shadow-week scorecard was reviewed; the offboarding drill left no data and no valid tokens; a test proves the work instance cannot read the personal instance's directory, vault or channel.

## Guardrails

- No import from the personal instance: no facts, no lessons, no examples, no credentials.
- No agent-to-agent link between instances. Calendar free/busy sharing is the only bridge.
- Research runs never receive client names or content.
- The work instance's golden evals contain client data and stay on employer infrastructure.

## Report back

Which path, the gate record, what the first two weeks of use showed, and the list of things Path A could not do that would justify Path B.
