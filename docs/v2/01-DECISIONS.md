# 01 · Decisions

The structural choices for Juno v2, each with the reason and what was rejected. External facts were checked on 2026-11-09; links are in the plan page's source list. A build session should treat these as settled unless Phase 0 evidence contradicts one, in which case it stops and reports.

## Settled

### D1 · Own the control plane; call models through the Messages API

The runtime is a Python service that owns channels, timers, policy, approvals, memory and context assembly, and calls Claude through the Messages API (structured outputs, a bounded tool loop, batches).

- **Why.** v1 runs every DM through a general-purpose coding harness: a fixed prefix of about 41K tokens, a replayed transcript (median 117K tokens per turn), file and web tools in the same run as mail text and private memory, and budget flags that do not stop a single expensive call (audit, 2026-11-10). Typed tools and assembled context fix these at the root. The Messages API is offered wherever Claude is, which matters for a work twin.
- **Corrected 2026-11-10.** The cost case is smaller than first written. The map's $1.69 per DM was a logging bug; the audited figures are a mean of $0.37 and a median of $0.20 on Opus. v1 also does carry conversation, by resuming a session. The decision now rests mainly on safety, bounded context and enforceable budgets. See `09-AUDIT-CORRECTIONS.md`.
- **Rejected: keep `claude -p`.** Per-run harness overhead; shell and file tools must be denied one by one; Claude Code's sandbox covers shell commands only, is off by default and does not exist on native Windows.
- **Rejected: the Agent SDK as the core.** It is the same coding harness as a library. Useful for a sandboxed worker, not for a runtime that should have no shell.
- **Rejected: Managed Agents as the core.** Hosted loop, schedules, memory stores and a credential vault are real and attractive. But it is beta; context is explored by the agent rather than assembled by code; memory is a model-written file mount; custom tools still need a host or public MCP servers; personal memory would sit in a hosted store; and it is not offered on Bedrock, Vertex AI or Foundry. It stays a candidate for lane L4.
- **Rejected: adopt OpenClaw or Hermes Agent.** They bring channels, scheduling and memory for free, and a large general-purpose agent with a poor 2026 security record that the owner would then have to re-gate.
- **Rejected: Claude apps only.** Connectors plus scheduled tasks cover briefs and Q&A with no code. No code-enforced gates, tap cards, ping caps, custom automations or controllable learning loop. Right for the work twin's first version.

### D2 · Lanes

L0 code, L1 single structured call, L2 bounded tool loop, L3 batch, L4 sandbox. Use the smallest that does the job. Proactive flows are L0 plus one L1 call.

### D3 · Stateless turns; state in the store

Each owner turn is a fresh request assembled from the thread store and memory inside fixed token budgets. No transcript replay across turns.

- **Why.** Bounded cost per turn, no dependence on a session surviving, no history-editing problems with thinking blocks.
- **Rejected:** resuming one long session, which is what v1 does (audit, 2026-11-10: a median of 117K transcript tokens on a turn's first call, a hard break after 12 quiet hours); cold runs with no thread state (no conversation).
- **The bar.** v1's follow-ups work today. v2 must match v1 on the same dialogue set before real DMs move (`briefs/P1`).

### D4 · Memory is SQLite plus a small curated core

Typed, dated, sourced facts; searchable episodes; a core card capped at 1,200 tokens; nightly consolidation; a real forget. Trust comes from the source of the text, decided in code.

- **Rejected for now:** vector or graph databases, hosted memory services, and a model-writable memory directory. Add embeddings only if recall tests fail on FTS.

### D5 · Run classes and taint

Five classes (`converse`, `reader`, `compose`, `research`, `reflect`). At most two of: reads untrusted text, sees private memory, can change the outside world. Untrusted free text entering `converse` taints the run and removes web access, auto-execution and memory promotion.

- **Why.** "Treat mail as data" is an instruction to a model. This is a boundary in code.

### D6 · Approvals bind to the exact payload

Proposal stored and hashed; card rendered from the stored proposal; tap from the owner's identity only; executor runs the stored payload once. Models never see passes.

### D7 · A dedicated always-on host, outbound connections only

A Linux container on a small dedicated machine, non-root, read-only image, one data mount, egress allow-list, no inbound ports. Runtime plane and build plane are separate.

- **Default host:** a small machine at home. Personal data stays in the house; Socket Mode and polling need no public address. A small cloud VM is acceptable with disk encryption and the same egress rules.
- **Rejected:** the daily PC (sleeps, runs everything else, runs as the owner).

### D8 · Channels sit behind an adapter; Slack stays primary

Slack DM remains the main channel: it works, it has rich approval cards, and Socket Mode needs no inbound port. A second channel is an adapter, added in Phase 6.

- **Second channel default: a Telegram bot.** Official, free, buttons for approvals, long polling with no inbound port. Bot chats are not end-to-end encrypted, so sensitive data classes can be kept off it by policy.
- **WhatsApp is closed for this use in the US, both ways.** Meta's Business Platform terms (§4.7, modified 2026-09-23) bar general-purpose AI assistants as the primary function, and WhatsApp's platform terms require business use, "not for personal use". Automating a consumer account breaks the Terms of Service ("auto-messaging") and risks the number. Muse is on WhatsApp because Meta owns it. Details and sources: `briefs/P6-second-channel.md`.

### D9 · One instance per context

Personal and work are separate instances with separate hosts or containers, vaults, channels, accounts and memory. No agent-level link between them.

### D10 · Learning has three sinks and a ladder

Rules in code, examples for voice, scoped lessons last. Every active item has an eval. Tasks move down `opus → sonnet → haiku → rule` on eval parity. Learning can never change tools, tiers, budgets or the constitution.

### D11 · Design for API billing

Budgets are enforced in dollars by the control plane from its own ledger.

- **Facts.** With a plan login, `claude -p` and the Agent SDK draw from the same subscription limits the owner uses interactively. Anthropic's help centre says Max, Ultra and Team plans include monthly API credits (Max: $100) usable with a key from a linked Console organization; they do not roll over. If the owner's plan has them, v2's estimated bill fits inside them.
- **Rejected:** building on subscription login for a headless server. It couples Juno's uptime to the owner's own usage and to a policy that changed more than once in 2026.

### D12 · Playbooks use the Agent Skills format

One `SKILL.md` folder per playbook. The Juno assembler loads the body when the router selects it; Claude Code and the Claude apps load the same folders natively. This is what makes a skills-only work twin and a cohort plugin cheap.

### D13 · L4 is an interface, not a build

Deep, sandboxed work is defined as an interface with no private memory and no secrets. Implement it only when a real task needs it; candidates are a Managed Agents session or an Agent SDK worker in its own container.

### D14 · Migrate, do not rewrite

Keep the bridge, approval cards, tool scripts and tests. Replace the invocation path first (Phase 1), behind a flag, with v1 available until each gate passes.

## Open, for the owner

Each has a default the plan assumes until the owner says otherwise.

| # | Decision | Default |
|---|---|---|
| O1 | Create an API key for the runtime and claim the plan's API credits if available | Yes; monthly alert at $40 |
| O2 | Host for Phase 3: home machine or cloud VM | Home machine, outbound-only |
| O3 | The "Juno as a person" track (own phone number, WhatsApp, own Gmail) | Pause; revisit in Phase 6 with the platform rules in hand |
| O4 | Work twin path | A (skills-only inside the employer's Claude plan) after the gate |
| O5 | Overnight coding agent | Not before Phase 3; cloud sandbox on the code repo only |
| O6 | Rebuild timing against the Dec 15 launch | **Changed 2026-11-10:** Phase 0 before; freeze launch week; Phase 1 and the rest after. Phase 1 may be built on its branch earlier, but real DMs do not move before the launch |
| O7 | What the cohort builds | v1's shape as the first agent; v2 as the "living with it" module |
| O8 | Conversational default model | Sonnet 5.5 at low effort; demote per intent on evals. Applied to v1 in Phase 0 |
| O9 | Where the build rules live (added 2026-11-10) | `docs/v2/BUILD-RULES.md`, named in each build session's opening prompt. Not merged into v1's `CLAUDE.md`, which is the runtime prompt |
