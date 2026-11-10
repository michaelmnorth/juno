# Research digest (2026-11-06)

Five research tracks ran in parallel against current docs and repos, plus one targeted read of the Claude Code
channels, scheduled-task, routines and Remote Control pages. Each section ends with "what it changes in the plan".
"UNVERIFIED" marks claims from a single or secondary source. Items marked **confirm before building** are the only
ones that need a hands-on test before the phase that depends on them.

---

## A. Open-source personal assistants: what to copy, what to avoid

| Repo | What it is | Activity | License | Take from it |
|---|---|---|---|---|
| [openclaw/openclaw](https://github.com/openclaw/openclaw) | The 394k-star "AI that does things" gateway (ex Clawdbot/Moltbot): channels + skills + SOUL/memory markdown + cron. Not on the Agent SDK. | pushed 2026-11-06 | MIT | The product shape. Not the code. |
| [nanocoai/nanoclaw](https://github.com/nanocoai/nanoclaw) | Small assistant on the Claude Agent SDK; each agent group has its own container, CLAUDE.md, memory and mounts; credential gateway; script-gated scheduled jobs. Slack/Telegram/Discord/WhatsApp. | 31k, pushed 2026-11-06 | MIT | **Closest match to our design.** Read `docs/memory.md`, `docs/isolation-model.md`, `docs/scheduled-tasks.md`, `docs/SECURITY.md`. Docker is awkward on Windows 11 Home. |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | Official Claude Code **Channels** (Telegram, Discord, iMessage): push chat into a running session; pairing code + sender allowlist; permission relay to the phone. | 46k, pushed 2026-11-06 | Apache-2.0 | Considered for Phase 1, not used because Slack has no channel plugin. Section C. |
| [overwirehq/claude-code-telegram](https://github.com/overwirehq/claude-code-telegram) | Python Telegram bot over the Agent SDK (CLI fallback), persistent cron store, HMAC-authenticated webhooks. | 2.8k, pushed 2026-10-01 | MIT (badge) | Most direct Python reference for chat → SDK session + cron, for the Phase 3 gateway. |
| [anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos) | email-agent (IMAP), research-agent (parallel subagents + synthesis), session API demo. | 2.8k | MIT | Subagent fan-out pattern. README says local dev only. |
| [HKUDS/nanobot](https://github.com/HKUDS/nanobot) | Python personal agent, cron, MCP, "Dream" memory consolidation. Not Claude-specific. | 50k, pushed 2026-11-06 | MIT | Memory consolidation + preference-file pattern (`docs/memory.md`). |
| [k-it-ai/cakeagent](https://github.com/k-it-ai/cakeagent) | ~5k lines, 3 deps, no open ports, dedicated OS user; a reaction to OpenClaw. | 2 stars | MIT | Readable minimal reference. Its "install integrations from chat" idea is the anti-pattern. |
| [khoj-ai/khoj](https://github.com/khoj-ai/khoj), [leon-ai/leon](https://github.com/leon-ai/leon), [chenhg5/cc-connect](https://github.com/chenhg5/cc-connect) | Second-brain / assistant / chat-bridge projects | large | AGPL / MIT / none | Ideas only. |

No mature repo combines the Agent SDK, a chat bridge and domain subagents for health and finance. We assemble; we do
not fork.

**OpenClaw's 2026 incidents, and the rule each gives us**

| Incident | Rule for us |
|---|---|
| ClawHavoc: hundreds of malicious ClawHub skills (counts conflict: 341 Koi Security, ~900 Bitdefender, 1,184 Antiy). Publishing needed only a week-old GitHub account. [SC World](https://www.scworld.com/news/openclaw-agents-targeted-with-341-malicious-clawhub-skills) | **No skill or MCP marketplace.** Every skill and server we run is written or read by us first. |
| CVE-2026-25253 (CVSS 8.8): the control UI trusted `gatewayUrl` from a query string and sent the stored token. | **Nothing listens on a port.** Slack Socket Mode is outbound only. |
| 21k-42k exposed instances; JFrog: 93% had auth bypass from implicit localhost trust behind a reverse proxy. | Same rule. No reverse proxy, no "localhost is safe". |
| Zenity zero-click injection: a Google Doc rewrote `SOUL.md`; a scheduled task re-injected it every 2 minutes. Upstream calls prompt injection out of scope. | **Agents that read untrusted content (email, web, docs, spreadsheets) cannot write persona or memory files or create schedules.** Memory writes are approval-gated. |
| Moltbook: Supabase key in client JS, 1.5M tokens exposed. | Secrets never in the repo or a readable file: 1Password. |

---

## B. Chat and push surface

| Option | Cost | Setup | Proactive push | Approval buttons | Works behind home NAT | Verdict |
|---|---|---|---|---|---|---|
| **Telegram bot** | $0 | Minutes (BotFather) | Yes | Yes (inline keyboards) | Yes (long polling) | Not chosen (Michael ruled it out 2026-11-06). Official Claude Code channel plugin. 20 MB down / 50 MB up via the cloud API, 2 GB with a local Bot API server. |
| **Slack free + custom app (Socket Mode)** | $0 | Medium (app, scopes, two tokens) | Yes (DM to his user ID) | Yes (Block Kit) | Yes (Socket Mode) | **Alternative** if Michael prefers to stay in Slack. 10-app cap; 90-day visible history; internal apps exempt from the 2025 history rate-limit cut. |
| Claude Tag (Claude in Slack) | Team/Enterprise only | High | Channels only, hourly, never DMs | n/a | hosted | **Out.** "Not available on individual plans (Free, Pro, Max, or Ultra)." Personal connectors do not apply to its routines. |
| Discord bot | $0 | Medium | Yes | Yes | Yes | Works; one more app for no gain. |
| ntfy.sh / Pushover | $0 / $4.99 once | Minutes | Yes | ntfy: HTTP action buttons | Yes | **Heartbeat fallback** for "the agent is down". |
| Twilio SMS | ~$1.15/mo + $0.0083/segment + 10DLC registration | High | Yes | No | No (webhook) | Out. |
| WhatsApp Business API | per message; templates; business verification; Meta barred general-purpose AI bots 2026-01-15 (press, enforcement UNVERIFIED) | Very high | Yes | Templates only | No | **Out, as Michael suspected.** |
| iMessage (BlueBubbles / official channel) | needs a Mac | High | Yes | No | proxy | Out on a Windows PC. |
| Signal (signal-cli) | $0 | High | Yes | No | Yes | Out: unofficial, breaks. |
| Claude app push via Remote Control | plan | Low | Only while a session runs; "Claude decides" | Approvals in the Claude app | Yes | **Bonus**, not the backbone. |

Sources: [Slack free limits](https://slack.com/help/articles/115002422943-Usage-limits-for-free-workspaces),
[Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode),
[chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage),
[Claude Tag availability](https://claude.com/docs/claude-tag/overview),
[Claude Tag proactivity](https://claude.com/docs/claude-tag/users/proactivity.md),
[Telegram bot FAQ](https://core.telegram.org/bots/faq), [Telegram features](https://core.telegram.org/bots/features),
[Twilio US SMS](https://www.twilio.com/en-us/sms/pricing/us), [WhatsApp pricing](https://developers.facebook.com/docs/whatsapp/pricing/),
[ntfy publish](https://docs.ntfy.sh/publish/), [Pushover](https://pushover.net/pricing).

**Decision (Michael, 2026-11-06): Slack, using his existing free workspace.** He has had bad experiences with Telegram.
One surface, carrying both chat and push over Socket Mode. The 90-day history limit is irrelevant because all memory is
files in this folder; the 10-app cap is fine for one bot.

What Slack changes versus Telegram: Claude Code Channels ship plugins for Telegram, Discord and iMessage only, and
only Anthropic-allowlisted plugins can register, so the zero-code inbound path does not exist for Slack. Two-way Slack
needs our own small Socket Mode bridge (`gateway/slack_bridge.py`), which moves from Phase 5 to Phase 1. It runs the
real `claude -p` binary on the subscription, which the docs describe as a supported use, so no API key is needed yet.
Outbound-only pings have a zero-code path: the claude.ai Slack connector can post (the work coordinator's settings
list `slack_send_message`, `slack_schedule_message` and `slack_send_message_draft` on it; **confirm the consumer
connector exposes the same** when connecting), so a desktop scheduled task can still reach Michael if the bridge is
down. Remote Control plus the Claude mobile app remains a free second surface for conversation and approvals. If
Michael is ever open to Discord, its official channel plugin is the zero-code alternative.

---

## C. How the agent runs and reaches Michael (Anthropic surfaces, read 2026-11-06)

| Surface | Runs where | PC must be on | Min interval | Connectors (Gmail/Calendar/Drive) | Loads project CLAUDE.md, agents, hooks | Push to phone | Cost |
|---|---|---|---|---|---|---|---|
| **Claude Code Channels** (research preview) | local `claude` session | Yes | event-driven | yes | Yes | Reply in Telegram; permission relay for approvals | subscription |
| **Session-scoped tasks** (`/loop`, `CronCreate`) | inside that session | Yes | 1 min; 50 per session; recurring expire after 7 days; restored only on `--resume`; missed fires run once | same session | Yes | via the channel (**confirm before building**: not stated that a cron fire can reply on a channel) | subscription |
| **Desktop scheduled tasks** | desktop app | Yes, app open and awake; one catch-up run on wake | 1 h in the form (1 min when Claude sets it) | connectors + local MCP | Yes (local folder per task) | desktop notification on catch-up only | subscription |
| **Cloud scheduled tasks / routines** (`/schedule`) | Anthropic cloud, fresh clone | **No** | 1 h; 100 runs/h per account; HTTP fire `POST /v1/claude_code/routines/<id>/fire` (30/h per task) | claude.ai connectors; no local MCP | CLAUDE.md from the repo; repo `.claude/agents` UNVERIFIED | none documented | subscription usage; runs start in auto mode |
| **Remote Control** (`claude --rc`) | local | Yes (reconnects after sleep) | n/a | yes | Yes | **Yes**: "Push when Claude decides" / "Push when actions required" | subscription; API keys not supported |
| **`claude -p` from Task Scheduler** | local | Yes | any | only with an interactive `/login` credential (**confirm**: whether `-p` loads them) | Yes unless `--bare` | build your own | subscription (documented as allowed, see below) |
| **Agent SDK daemon** (our gateway) | local or VPS | Yes | any | no claude.ai connectors; own MCP servers | Yes (`settingSources`) | via Telegram/Slack API | API key per token; Max includes $100/month API credits that cover the SDK |
| Managed Agents | Anthropic sandbox | No | cron, minute granularity | via vaults/MCP | agent-level skills/MCP, no local folder | webhooks | tokens + $0.08 per session-hour; not ZDR |

Channel setup, verbatim from https://code.claude.com/docs/en/channels: `/plugin marketplace add anthropics/claude-plugins-official`
→ `/plugin install telegram@claude-plugins-official` → `/telegram:configure <token>` (saved to `~/.claude/channels/telegram/.env`)
→ `claude --channels plugin:telegram@claude-plugins-official` → DM the bot, get a pairing code → `/telegram:access pair <code>`
→ `/telegram:access policy allowlist`. Requires Bun. "Events only arrive while the session is open, so for an always-on
setup you run Claude in a background process or persistent terminal." "Anyone who can reply through the channel can
approve or deny tool use in your session." "Pro, Max, and Ultra users without an organization skip these checks entirely."

**Subscription vs API for unattended runs** (https://code.claude.com/docs/en/authentication, https://code.claude.com/docs/en/legal-and-compliance,
https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan):
`claude setup-token` exists "for CI pipelines, scripts, or other environments where interactive browser login isn't
available" and "authenticates with your Claude subscription". The Agent SDK and `claude -p` "still draw from your
subscription limits" (policy update 2026-10-07; an earlier split was paused 2026-06-15, so this can change). OAuth is
"designed to support ordinary use of Claude Code and other native Anthropic applications"; advertised limits "assume
ordinary, individual usage". Reading: running the real `claude` binary on his own login from Task Scheduler is within
the documented use; a custom daemon reusing subscription OAuth outside the binary is a gray area; the Agent SDK on an
API key is unambiguous, and Max's $100/month API credits cover the Agent SDK (not Claude Code itself).

Other facts that shape the design (https://code.claude.com/docs/en/hooks, /permissions, /sandboxing, /memory, /sub-agents):
- PreToolUse decisions: `allow`, `deny`, `ask`, `defer`; precedence deny > defer > ask > allow. **`defer` works only in
  `-p` mode**, ends the turn with `stop_reason: "tool_deferred"`, and is ignored when several tool calls share a turn.
  Exit code 2 blocks regardless. Hook timeouts do not block unless `"onFailure": "block"`.
- **Sandbox is not supported on native Windows.** Deny rules and hooks are the gates. (WSL2 would add a sandbox.)
- Permission rules: deny → ask → allow, first match wins. MCP rules: `mcp__<server>__<tool>` or `mcp__<server>__*`.
- Auto memory writes to `~/.claude/projects/<project>/memory/`; `MEMORY.md` loads the first 200 lines / 25 KB. Docs:
  CLAUDE.md and memory are "context, not enforced configuration". Subagent `memory: project` stores in
  `.claude/agent-memory/<name>/`. Managed Agents memory docs warn: "a successful prompt injection could write
  malicious content into the store. Later sessions then read that content as trusted memory."
- `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` defaults to 3; set 1. Model order: per-call, frontmatter, env var, main model.
- Plugins package skills, agents, hooks and MCP servers; `--plugin-dir` loads locally; cloud sessions do not load local plugins.

---

## D. Finance: read-only aggregation, secrets, tax mechanics

| Option | Cost/yr | Setup (1-5) | Brokerage | Read-only | Notes |
|---|---|---|---|---|---|
| **Plaid Trial** (teams created after 2026-04-15) | $0 | 3 | Investments product included | Transfer not on this plan | **10 Items for life**; removing an Item does not free its slot; OAuth banks work on Trial; "Personal use" at signup (support article 403'd: UNVERIFIED). [billing](https://plaid.com/docs/account/billing/), [OAuth](https://plaid.com/docs/link/oauth/) |
| Plaid pay-as-you-go | price only on the Production form | 4 | yes | same | Needed past 10 Items. |
| **SimpleFIN Bridge** | $15 | 2 | partial (Fidelity seen; Schwab/Vanguard UNVERIFIED) | by protocol | 25 institutions, 90 days of history per account, ~daily refresh. [bridge](https://beta-bridge.simplefin.org/), [protocol](https://www.simplefin.org/protocol.html) |
| Teller | $0 dev (100 enrollments ever); prod KYB-gated | 4 | unknown | not stated | Company-oriented. |
| MX / Finicity / Yodlee / Akoya | sales-led | 5 | yes | n/a | No personal tier. |
| YNAB API | subscription | 2 | none | `scope=read-only` | Budget layer only. |
| Lunch Money / Monarch / Tiller / Actual Budget | $60-100 / none official / $79 / $0 + SimpleFIN | 2-3 | weak / unofficial / ? / via SimpleFIN | varies | Optional categorization layer later. Monarch is reverse-engineered: TOS risk. |
| Schwab Trader API (Individual) | $0 | 4 | Schwab only | **can place orders**: scope check required | ~month approval, 7-day refresh token (UNVERIFIED). |
| Coinbase API | $0 | 2 | crypto | view-only key possible | Never grant the transfer permission. |
| Statement PDFs via Gmail | $0 | 2 | all | yes | Monthly lag. Local PDF parse, rows only to the model. Fallback for Fidelity/Vanguard (no public APIs). |

**1Password runtime pattern** (no secret ever enters the model's context): service account with `read_items` on one
`Agent-Secrets` vault (Individual/Families appear in the rate-limit table; plan inclusion UNVERIFIED) → token in Windows
Credential Manager → a fixed tool script runs `op run --env-file=finance.env -- python fetch.py` where `finance.env`
holds only `op://` references → `fetch.py` writes sanitized JSON (last-4 only, no tokens) → the agent reads the JSON.
Permissions deny `op read`, `printenv`, `Read(**/.env*)`. `op` is **not installed** yet. Sources:
[service accounts](https://www.1password.dev/service-accounts/get-started), [rate limits](https://www.1password.dev/service-accounts/rate-limits),
[op run](https://www.1password.dev/cli/secrets-environment-variables).

**Tax mechanics the agent can compute or remind about** (IRS pages, 2026 tax year; a CPA confirms):
- Estimated payments: Apr 15, Jun 15, Sep 15 2026, Jan 15 2027 (Form 1040-ES; 2027 schedule UNVERIFIED until Pub 509 2027).
- Required if expecting to owe ≥ $1,000; safe harbor 90% current year / 100% prior year (110% above $150k AGI UNVERIFIED on the page fetched).
- SE tax 15.3%; 2026 Social Security wage base $184,500; +0.9% Medicare over $200k single; half of SE tax deductible.
- 2026 limits (IR-2025-111): 401(k) deferral $24,500; IRA $7,500; 415(c) total $72,000; comp cap $360,000 (secondary sources for the last two).
- SEP-IRA: lesser of 25% of compensation or $72,000. Solo 401(k): deferral + employer 25% within $72,000; Form 5500-EZ at $250k assets.
- QBI (199A) permanent under OBBBA; single threshold $201,750 phasing over $75,000 (sources conflict: **confirm with Rev. Proc. 2025-32**). Standard deduction single $16,100.
- Home office simplified: $5/sq ft to 300 sq ft (Pub 587).
- S-corp election: CPA territory. The "$40-80k net profit" rule of thumb is folklore, not sourced.
- Disclaimer the agent carries verbatim: "I am an AI assistant, not a licensed tax, financial or investment advisor. Figures are estimates from IRS publications dated [date]. Confirm with a CPA before filing or paying."

**Data handling.** API inputs/outputs deleted within 30 days; zero-data-retention is not offered to individuals;
consumer-plan retention settings were not retrieved (UNVERIFIED). Design mitigations: account numbers never reach
the model, aggregates before rows, finance runs on the API with commercial terms. Sources:
[retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data),
[ZDR](https://privacy.claude.com/en/articles/8956058-i-have-a-zero-data-retention-agreement-with-anthropic-what-products-does-it-apply-to).

---

## E. Health: getting the data out

| Source | Auth | Data | Push or pull | Cost | Effort (1-5) |
|---|---|---|---|---|---|
| **Apple Health** | none: no cloud API; HealthKit needs an iOS app | everything the phone has | n/a | | |
| **Health Auto Export** (iOS) | your own HTTP headers | metrics (`sleep_analysis` with core/deep/rem/awake/inBed, `step_count`, `dietary_energy`, weight, HRV...), workouts v2 (start/end/duration/energy/HR). Shapes for weight, HRV and strength sets **UNVERIFIED: test with a real export** | **push** to a URL on a cadence ("desired background cadence, not a guaranteed schedule"; phone unlocked, Background App Refresh on) | Premium $1.99/mo, $6.99/yr or **$24.99 lifetime** (REST automations are Premium) | 2 |
| **HealthExport** (iOS 26.2+) | none | daily JSON to **iCloud Drive** | push to a folder, no URL needed | free | 2 |
| Apple Health XML export | manual | full history | manual zip | free | 1 (one-off backfill) |
| **Withings API** | OAuth2 (access 3 h, refresh ~1 yr, each refresh rotates) | weight, fat %, muscle, hydration, bone, VO2 max (`getmeas`); **`sleep_score`** via `/v2/sleep getsummary` (device-dependent) | pull (≤ 1 per 10 min) or Notify webhooks (need a URL) | free | 3 |
| **Hevy API** (Pro) | `api-key` header from hevy.com/settings?developer | workouts (page size 10), routines, exercise templates, exercise history, body measurements; **create/update routines: yes**; no deletes; webhook on workout created | pull, optional webhook | Pro ~$2.99/mo, $23.99/yr, $74.99 lifetime | 2 |
| Apple Watch Sleep Score (watchOS 26) | | 0-100 score | | | Apple DTS 2025-09: "no API that allows the access to sleep scores". Stages only, via HAE. |
| Oura / Whoop | OAuth2 | `daily_sleep.score` / sleep performance | pull / webhooks | membership | 3 |
| Garmin | gated program | | | | 5 |
| Macro trackers (MacroFactor, Cronometer, MyFitnessPal, Lose It) | | none have a usable public API | CSV export, or write to Apple Health and read `dietary_energy`/protein/carbs/fat via HAE (fields per tracker UNVERIFIED) | | 2 |
| **Google Sheets** (coach program) | service account shared on the one sheet (UNVERIFIED in fetched docs; standard practice) or OAuth | read program tab, `values.append` to a Log tab; quotas 300 r/w per minute | pull/write | free | 2 |
| Video | Drive folder → PC | ffmpeg 9 is installed; scene detection is weak on a static gym camera: use motion energy or silence gaps; H.264 under 20 MB for Telegram or send Drive links | | | 4 |

Sources: [HAE REST](https://help.healthyapps.dev/en/health-auto-export/automations/rest-api), [HAE format](https://help.healthyapps.dev/en/health-auto-export/export-format),
[HealthExport](https://apps.apple.com/app/id6759782354), [Withings llms.md](https://developer.withings.com/llms.md),
[hevy-py](https://github.com/ewright3/hevy-py), [hevy-mcp](https://github.com/chrisdoc/hevy-mcp), [Apple DTS thread](https://developer.apple.com/forums/thread/800403),
[Oura auth](https://cloud.ouraring.com/docs/authentication), [Sheets quotas](https://developers.google.com/workspace/sheets/api/limits).

**Recommended minimum path, and why it differs from the research agent's.** The agent suggested HAE pushing to an
HTTPS endpoint on the PC. That needs an inbound URL (tunnel) and breaks our zero-inbound-ports rule. Preferred:
**file drop**. HealthExport (free) or HAE writing JSON into an iCloud Drive folder, iCloud for Windows syncs it to the
PC, a watcher loads it into SQLite. No ports, no tunnel. Fallback if the file route proves flaky: Cloudflare Tunnel or
Tailscale Funnel to a tiny receiver, which is outbound-initiated. Hevy and Withings are pulled on a schedule
(webhooks later, same tunnel). The coach sheet is read and appended with a service account. Everything lands in
`data/health.sqlite`; the health agent answers from SQL, never from raw JSON in context.

---

## F. Models and cost

API list prices, USD per million tokens (https://platform.claude.com/docs/en/about-claude/pricing, read 2026-11-06):

| Model | Input | Cache read | Output | Batch in/out |
|---|---|---|---|---|
| Fable 5.1 `claude-fable-5-1` | $10 | $0.25 | $50 | $5 / $25 |
| Opus 5.5 `claude-opus-5-5` | $4 | $0.20 | $20 | $2 / $10 |
| Sonnet 5.5 `claude-sonnet-5-5` | $2 | $0.10 | $10 | $1 / $5 |
| Haiku 5.5 `claude-haiku-5-5` (≤100k prompt) | $0.10 | $0.01 | $0.50 | $0.05 / $0.25 |

All four are available to Claude Code subscribers; Opus 5.5 is the default; Fable is opt-in (`/model fable`) and on
Max is "included, up to half your weekly limit". Models from 4.7 on tokenize ~30% heavier than earlier models.

**Back-of-envelope monthly API cost** for the routine workload (12 Haiku sweeps/day at 15k in / 1k out; 3 Sonnet
digests/day at 40k in / 3k out; 10 Opus coordinator runs/month at 100k in / 5k out; 70% cache hits; thinking tokens excluded):

| Workload | Haiku/Sonnet/Opus tiering | Same work on Fable 5.1 |
|---|---|---|
| Sweeps | $0.38 | $35.15 |
| Digests | $5.11 | $24.93 |
| Coordinator | $2.34 | $5.68 |
| **Total** | **≈ $7.83** (≈ $8.71 if the uncached 30% is billed as cache writes) | **≈ $65.75** |

Caveats: 70% cache hits is optimistic for 2-hourly sweeps on a 5-minute cache TTL; adaptive thinking bills as output.
Even at 3x the estimate, the API route sits inside Max's $100/month API credits.

**What it changes in the plan.** Fable is for design sessions with Michael only. The coordinator runs on Sonnet 5.5,
sweeps and the notifier on Haiku 5.5, the weekly reflection and anything touching money on Opus 5.5. Phase 1 costs
no API money at all because it runs inside the subscription.
