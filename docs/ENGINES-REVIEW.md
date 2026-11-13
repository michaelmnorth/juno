# Juno's two engines: a brief for a second opinion

Written 2026-11-12 for a fresh reviewer, which can be another Claude session or a person. The repo is public;
nothing personal is in this file.

## The question

Juno has two engines that produce replies, called "v1" and "v2". The owner wants **one** engine, one source of
truth in GitHub, and no more v1/v2 wording. He also wants it to run on his **Claude Max subscription rather than
API credits** where possible.

Review the reasoning below and say:

1. Should Juno collapse to one engine, and if so, which one?
2. What would be lost, and what has to be ported first?
3. Are the cost and billing facts below right as of today?

## What each engine is

Both live in this repo and share everything else: the Discord/Slack bridge (`gateway/slack_bridge.py`), the
approval cards and taps, the scripts in `tools/`, the timers, `state/`, and the tests.

| | v1 | v2 |
|---|---|---|
| What it is | The Claude Code CLI (`claude -p`), started per run by `gateway/claude_runner.py`, resuming a session per chat | A small Python control plane (`v2/`): router → context assembler → model with typed tools → policy engine. Calls the Messages API directly |
| Billing | The owner's Max sign-in, sharing his subscription limits | API key from the Console (pay as you go) |
| Prompt | `CLAUDE.md` plus the skills and agents in `.claude/` | `v2/prompts/constitution.md` plus playbooks in `v2/playbooks/` |
| Tools | Built-in tools (Read, Bash, WebSearch, …), Gmail/Drive connectors, subagents, `tools/*.py` | 17 typed tools in `v2/tools.py` over the same scripts (`v2/backend.py`) |
| Runs today | Timers (sweeps, morning brief, evening check-in, coach sheet, weekly reflection, watch digest), health, money, YouTube, the browser agent, and every DM v2 hands off | Every DM first (`v2/config.py` `DEFAULT_ENGINE = "v2"`); calendar, mail, reminders, notes, people, research |
| Speed per DM | Slower (tens of seconds; about a 41K-token harness prefix, and resumed context reaching about 117K tokens at the median) | Faster (a few seconds; target ≤ 8K tokens assembled per turn) |
| Safety model | Rules in `CLAUDE.md` plus a settings allow/deny list. Shell and file tools are present in the same run that reads mail | Enforced in code: a tiered policy engine, taint tracking, a no-tool "reader" that turns email into typed fields, drafts only when the owner asked, a repeat-call guard, approvals bound to the exact payload |
| Cost seen | Mean about $0.37 and median about $0.20 per DM on Opus when it was the DM engine (DV1), now inside Max limits | About $0.01–0.02 per DM, estimated at $8–15 a month at 30 DMs a day (ledger in `state/v2.db`) |

## Why v2 was built

From `docs/v2/01-DECISIONS.md` (D1, D11, D14) and `docs/v2/DEVIATIONS.md` (DV1, DV13):

- **Safety.** v1 runs DMs through a general-purpose coding harness, with file, shell and web tools in the same run
  as mail text and private memory. The Claude Code sandbox doesn't exist on native Windows. v2 gives the model only
  typed tools, gated by code.
- **Bounded context and budgets.** v1's budget flags can't stop a single expensive call, and its resumed
  transcript keeps growing. v2 assembles each turn from its parts and records every call in a ledger.
- **Cost.** This was the original driver, but the early figure was overstated about 7× by a logging bug (DV1), so
  cost is now a secondary reason.
- **Billing independence.** D11 rejected building a headless server on a subscription login, because it ties
  Juno's uptime to the owner's own usage and to a policy that changed several times in 2026.
- **Migrate, don't rewrite** (D14). v2 was put in front of v1, and v1 kept everything v2 hadn't ported.

## What has gone wrong with having two

- **The handoff seam.** v2 hands DMs it can't do to v1 (`Reply.handoff`, DV13, DV20). Failures cluster there. On
  2026-11-12 a request to review an emailed attachment stayed in v2, which couldn't open it, and the owner got a
  "paste it here" answer. That was fixed in P2, but the seam remains.
- **Two prompts, two tool sets, two sets of rules** to keep in sync, plus the v1/v2 vocabulary leaking into what
  the owner sees.
- **Two bills.** Max for v1, API credits for v2.

## Options

| Option | What it means | For | Against |
|---|---|---|---|
| A. v1 only | Set `DEFAULT_ENGINE = "v1"`, port v2's code-enforced guards into v1 (the reader for mail bodies, draft gate, repeat guard) as tools or hooks, then delete `v2/` | Everything on Max; one prompt; no seam | Slower DMs; the safety controls are weaker than code-enforced ones; heavy days count against Max weekly limits; D11's uptime-coupling concern |
| B. v2 only | Port the rest (timers, health, money, YouTube, browser) into v2, then delete the CLI path | One engine, code-enforced safety, fast, cheap | All on API billing; a large port; the browser agent and subagents need a new design |
| C. Keep both, hide it | Keep the split but remove the v1/v2 wording from everything the owner sees | Least work | The seam and duplication stay; not what the owner asked for |

The coordinator's recommendation to the owner was **A**, because he prefers his plan over API credits. Check it
against the facts below.

## Facts to verify (dated; check live docs)

- **Plan credits.** D11 says Max plans may include monthly API credits ($100 on Max) usable with a key from a
  linked Console organization. If that's true for his plan, v2's estimated bill is already covered, which would
  change the A-versus-B trade-off a lot. This hasn't been verified since 2026-11-09.
- **Subscription login and the CLI.** With a plan login, `claude -p` and the Agent SDK draw from the same limits
  the owner uses interactively. Check the current terms for unattended or headless use on a subscription.
- **API prices.** Web search is about $10 per 1,000 searches and web fetch costs tokens only.

## Where to read (on GitHub, main branch)

Repo: https://github.com/michaelmnorth/juno

- **Overview of v2 and the build kit:** https://github.com/michaelmnorth/juno/blob/main/docs/v2/00-START-HERE.md
- **The decisions and reasons (D1, D11, D14):** https://github.com/michaelmnorth/juno/blob/main/docs/v2/01-DECISIONS.md
- **v2 architecture, including the v1 → v2 map:** https://github.com/michaelmnorth/juno/blob/main/docs/v2/02-ARCHITECTURE.md
- **Context and cost model:** https://github.com/michaelmnorth/juno/blob/main/docs/v2/03-CONTEXT-AND-COST.md
- **Security controls:** https://github.com/michaelmnorth/juno/blob/main/docs/v2/05-SECURITY.md
- **What changed from the plan and why (DV1–DV22):** https://github.com/michaelmnorth/juno/blob/main/docs/v2/DEVIATIONS.md
- **Phase reports:**
  - https://github.com/michaelmnorth/juno/blob/main/docs/v2/reports/P0.md
  - https://github.com/michaelmnorth/juno/blob/main/docs/v2/reports/P1.md
  - https://github.com/michaelmnorth/juno/blob/main/docs/v2/reports/P2.md
- **v1's architecture:** https://github.com/michaelmnorth/juno/blob/main/docs/02-ARCHITECTURE.md
- **Overall status:** https://github.com/michaelmnorth/juno/blob/main/docs/00-STATUS.md
- **The code:**
  - v2: https://github.com/michaelmnorth/juno/tree/main/v2
  - v1 runner: https://github.com/michaelmnorth/juno/blob/main/gateway/claude_runner.py
  - Bridge: https://github.com/michaelmnorth/juno/blob/main/gateway/slack_bridge.py

The owner also has a private plan page, "Juno v2 Plan", with the full original reasoning. Ask him for the link if
you need it; a Claude session of his can read it with the Artifact tool.
