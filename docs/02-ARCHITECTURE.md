# Personal coordinator: architecture

One coordinator Michael talks to from his phone. It routes to a few narrowly scoped subagents, acts on its own on a
schedule, learns his preferences from his corrections, and never holds a credential that can move money or send on
his behalf without a gate he controls from the chat UI.

## 1. Shape

```
  Michael's phone (Slack)                         Timers
        │  messages, button taps, photos            │ morning brief, evening check-in,
        ▼                                           ▼ 2-hourly sweep, weekly reflection
┌──────────────────────────────────────────────────────────────┐
│ COORDINATOR  (persona: see §7; Sonnet 5.5 by default)        │
│ CLAUDE.md = identity + routing + guardrails                  │
│ reads: me/*, learnings/coordinator.md, state/*, domains/*    │
│ writes: logs/, state/, and (only after approval) me/, learnings/ │
└───────┬──────────┬──────────┬──────────┬──────────┬──────────┘
        │ Agent tool, depth 1, no forks, full inputs in the prompt
        ▼          ▼          ▼          ▼          ▼
   inbox-     calendar    drafter    health     finance   researcher   notifier   reflector
   triage     (Sonnet)   (Sonnet)   (Sonnet)   (Sonnet)   (Sonnet)    (Haiku)    (Opus, weekly)
   (Haiku)
   Gmail      GCal read  Gmail      SQLite +   sanitized  web, read-  one msg    logs + signals
   read only  + engine   drafts     Sheets +   JSON via   only        to Michael → proposed
   → JSON     → slots    only       Hevy tool  op-wrapped            only       lessons
                                    (writes    scripts                           (never applies)
                                    gated)     (never creds)
```

- Subagents cannot call each other. Everything flows through the coordinator.
- Every subagent gets only the tools its job needs, with reads separated from writes and the untrusted-input agents
  (inbox-triage, researcher) given no write tools at all.
- The coordinator passes each delegation the objective, boundaries, inputs verbatim, tools to use, output schema and
  stop condition. Subagents see none of the conversation.
- Deterministic code does arithmetic: the scheduling engine for time, SQL and Python for health trends and money.
  The model decides and writes; it never computes a buffer, a sum or a date in its head.

## 2. Runtime, in three stages

| Stage | How Michael talks to it | How it acts on a timer | Approvals | Cost | Why move on |
|---|---|---|---|---|---|
| **1. Slack bridge on the subscription** (Phase 1-2) | `gateway/slack_bridge.py`: a Socket Mode bot (outbound only) in his free Slack workspace. A DM from Michael runs `claude -p` in this folder with the conversation's saved session id; the reply is posted back. `/new` starts a fresh session. | APScheduler in the same process reads `me/proactivity.yaml` and runs the anchors (morning brief, evening check-in, sweep, weekly reflection) as unattended `claude -p` runs, posting results to his DM | The coordinator writes `state/pending-approvals.json`; the bridge posts a Block Kit card; Approve/Deny resumes the session with the answer. Remote Control push from the Claude app as a second surface | Subscription only (`claude -p` is documented for scripts) | Reads from Gmail/Calendar in `-p` must be confirmed; PC must stay on |
| **2. Hardened** (Phase 3) | Same bridge, run as a Windows service at logon | Same, plus a cloud routine for the one "PC may be off" daily sweep over connectors | Hooks return `defer` in `-p` mode for T3 tool calls, surfaced through the same card | Subscription | Still tied to the CLI surface |
| **3. Gateway on the Agent SDK** (Phase 5+) | Same bridge with `CLAUDE_BACKEND=sdk`: `query()` from `claude-agent-sdk` instead of the CLI | Script-gated jobs (a cheap check decides whether to wake the model at all) | PreToolUse hook `defer`, resumed by session id | API key; routine load ≈ $8/month, inside Max's $100 API credits | Independent of CLI changes; can move to a mini PC or VPS |

Michael chose Slack over Telegram (2026-11-06), which removes the zero-code channel plugin option (Claude Code
Channels cover Telegram, Discord and iMessage only). The bridge is therefore built in Phase 1, kept small, and tested
offline; it is the one piece of code that must exist before anything reaches his phone.

## 3. Folder layout

```
C:\Users\Michael\Claude-Personal\personal-coordinator\
├── CLAUDE.md                     identity, routing, guardrails, learning loop (imports learnings/coordinator.md)
├── .claude\
│   ├── settings.json             permissions allow/deny, hooks, env (spawn depth 1)
│   ├── agents\                   one .md per subagent (frontmatter: name, description, tools, model, memory...)
│   ├── skills\                   morning-brief, evening-checkin, sweep, lesson, weekly-reflection, onboard-source
│   └── hooks\                    notify_michael_only.py, gate_memory_writes.py, gate_external_writes.py
├── me\                           preferences: profile, voice, schedule, proactivity.yaml, automation.yaml, goals
├── learnings\                    one file per agent + coordinator; dated lines; coordinator-only writes
├── domains\
│   ├── health\                   baselines, coach, equipment, HEALTH-CONTEXT.md
│   ├── finance\                  accounts.yaml (names and last-4 only), tax-calendar.yaml, FINANCE-CONTEXT.md
│   ├── admin\                    email rules, calendar rules, recurring reminders
│   └── business\                 the venture (Roast Room): offer, pipeline, learning plan
├── people\                       family, coach, CPA, friends: name, relationship, time zone, how to address
├── tools\                        Python: health_fetch, finance_fetch, sheets, hevy, video_split; op-wrapped
├── data\                         health.sqlite, finance.sqlite, imports\ (git-ignored)
├── state\                        processed.json, pending-approvals.json, proposed-lessons.md, signals.jsonl
├── logs\                         one file per run (git-ignored)
└── docs\                         these documents
```

## 4. Subagent roster

| Agent | Model | Job | Tools (least privilege) | Can write? |
|---|---|---|---|---|
| `inbox-triage` | Haiku | Classify new Gmail: who, intent (schedule, reply-needed, bill, receipt, subscription, newsletter, family, noise), urgency, suggested action. JSON only. | Gmail read, `people/`, `domains/admin/email-rules.md` | **No** |
| `calendar` | Sonnet | Find slots, detect conflicts, prep for upcoming events, propose holds. Uses the scheduling engine for all time math. | GCal read, engine CLI, `me/schedule.md`, `people/` | GCal event create is **gated** |
| `drafter` | Sonnet | Replies and new emails in Michael's voice, saved as Gmail drafts. Proactive drafts allowed (the Muse behavior Michael liked). | Gmail draft create, `me/voice.md`, `people/` | Drafts only; send is **gated** |
| `health` | Sonnet | Weekly report and on-demand answers from `data/health.sqlite`; builds next week's workouts from the coach sheet; pushes routines to Hevy. | `tools/health_*` (op-wrapped), SQLite read, Sheets read, Hevy routine write | Sheet append and Hevy routine create are **gated** until 10 clean approvals |
| `finance` | Opus for analysis, Haiku for the pull | Cash flow, spend by category, income vs estimate, tax set-aside, retirement contribution room, "what changed". Reads sanitized JSON only. | `tools/finance_fetch` (op-wrapped), `data/finance.sqlite`, `domains/finance/*` | **No external writes exist.** Reports only. |
| `researcher` | Sonnet | Web research for the business venture and for Michael's learning plan; summaries with sources. | WebSearch, WebFetch, Read | **No** |
| `notifier` | Haiku | One short message to Michael with links and buttons. | Slack send, restricted by hook to Michael's user id | Only to Michael |
| `reflector` | Opus, weekly | Reads logs, signals, corrections; proposes dated lessons and preference changes into `state/proposed-lessons.md`. | Read, Write to `state/proposed-lessons.md` only | Never touches `me/` or `learnings/` |
| later: `video-cutter` | none/Haiku | ffmpeg split of lifting videos from a Drive folder, compress, return links. | `tools/video_split`, Drive | writes to Drive folder only |
| later: `business` | Sonnet | Pipeline, offer copy, cohort ops for the venture. | `domains/business/`, Drive | drafts only |

Why each earns its place (the 3-10x token tax): triage and finance protect context from verbose data; health and
finance need separate credentials; researcher and notifier isolate dangerous tool classes (web, send). Notes and
reminders are **skills**, not agents.

## 5. Automation tiers and the approval gate

| Tier | Examples | Unattended? |
|---|---|---|
| T0 read | read mail, calendar, health DB, finance JSON | Yes |
| T1 write own files | logs, state, drafts, SQLite, proposed lessons | Yes |
| T2 message Michael | pings, briefs, approval cards | Yes, inside `me/proactivity.yaml` limits (quiet hours, max unprompted pings per day) |
| T3 act outward | send an email, create a calendar event, append the coach sheet, create a Hevy routine, write to `me/` or `learnings/` | **Approval button**, per action. An action class moves to auto only after N clean approvals recorded in `me/automation.yaml` by Michael, and only for recipients in `people/`. |
| T4 money | move, pay, trade | **Does not exist.** No credential with that power is ever created. |

Enforcement is layered: prompts explain the rule, `settings.json` denies the tool by name, a PreToolUse hook checks
the arguments (recipient, path, amount), and in headless mode the hook returns `defer` so the call pauses until a tap.
Every gate ships with a test that proves it blocks, because hook deny decisions have had bugs.

## 6. Memory and the learning loop

Three kinds of memory, three different write rules:

| Memory | Where | Who writes | How it changes |
|---|---|---|---|
| **Identity and rules** | `CLAUDE.md`, `.claude/**` | Michael and a Claude session Michael is in | Never by an unattended run. Denied by settings for all agents. |
| **Preferences and lessons** | `me/*.md`, `learnings/*.md`, `people/`, `domains/*/CONTEXT.md` | Coordinator only, after Michael's `/lesson`, a correction, or an approved proposal | One dated line each, `(Michael)` for confirmed, `(assumed)` for a guess; assumed lines expire after 30 days unless confirmed; contradictions replace, never append. |
| **Facts and history** | `data/*.sqlite`, `state/`, `logs/` | Tools and the coordinator | Append-only, machine-generated. |

Learning without Michael saying it: every run appends **signals** to `state/signals.jsonl`: which button he pressed,
how long before he reacted, whether a draft was sent as-is or edited (diff size), which pings he ignored, what he asked
for that no agent covered. The weekly `reflector` turns signals plus corrections into proposed lessons. The coordinator
sends them as a short card ("I think you prefer X. Save it?"). Only a tap writes the line. Claude Code's own auto
memory stays **off** for unattended runs (`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`), because an injected email must not be
able to teach the system anything.

## 7. Personality

Michael's two words: **personality** and **forward-thinking**. Translation into rules the coordinator can follow:

- Has a name and a consistent voice (working name: **Juno**; alternatives: Atlas, Sol, Marlow). Dry warmth, short
  sentences, one light line per message at most, never when something went wrong.
- Leads with what it did or what it needs, not what it was asked.
- Forward-thinking means anticipating: pre-event prep the evening before, "you have a flight at 6, checked in?",
  "three subscriptions renew this week", "your coach's sheet changed", "estimated tax due in 9 days". The morning
  brief and evening check-in are the anchors; unprompted pings live inside the daily budget in `me/proactivity.yaml`.
- Proposes drafts unasked (the behavior Michael liked in Muse): "two emails look like they want a reply; drafts are
  in Gmail, want me to tweak either?" Never sends them.
- Admits uncertainty in one clause and makes the call anyway; questions are for irreversible things.
- The personas of the subagents (Sorter-style names) show up only in what Michael sees, never in anything outward.

## 8. Security posture (the lessons from OpenClaw, Muse and Grok Bot applied)

1. **No inbound ports.** Slack Socket Mode, Drive/iCloud file drops, outbound-initiated tunnels only.
2. **Secrets in 1Password**, fetched by fixed wrapper scripts with `op run`; the model never sees a token. Denied:
   `op read`, `printenv`, `Read(**/.env*)`.
3. **Untrusted content is data.** Email, web pages, spreadsheets and PDFs can never instruct an agent; agents that read
   them have no write tools and cannot touch memory or schedules.
4. **Out-of-band approval**: the tap in Slack, not text in the chat, is what authorizes a T3 action. (Muse: approvals
   in the client UI. Grok Bot: hand the computer back for credentials.)
5. **Separate credentials per domain**; nothing with money-moving scope exists.
6. **No marketplace skills or servers.** Every skill and MCP server here is ours or read line by line first.
7. **Work and personal never meet.** Denies on `~/Claude-Work/**`, the work project history, `~/.claude-second/**`, and
   the stray work content under `~/Claude/`.
8. **Every run logs** what it read (by id), decided, created, assumed and was blocked from.
9. **Windows has no sandbox** for Claude Code, so deny rules and hooks are the whole gate until the gateway runs under
   a dedicated low-privilege Windows user (Phase 5).

## 9. What will not work, or not the way Michael pictured it

- **Chatting with it from Slack requires the bridge process running on the PC.** The PC-off case is cloud routines
  (hourly, connectors only, no phone push documented) until the bridge moves to a machine that stays on.
- **No zero-code Slack path exists.** Anthropic's channel plugins are Telegram, Discord and iMessage only; Claude Tag
  is Team/Enterprise only. The bridge is small but it is code Michael owns.
- **It cannot read Apple Health directly.** Data leaves the phone only through an iOS app you install (HealthExport or
  Health Auto Export). Apple exposes no Sleep Score API; stages come through, the score does not. Withings has its own
  score via API if the device supports it.
- **Bank access is read-only aggregation, not "connect my bank."** Plaid Trial gives 10 Items for life; brokerages
  without APIs (Fidelity, Vanguard) come in through monthly statement PDFs.
- **The agent will not give financial or tax advice.** It computes, reminds, and prepares questions for a CPA, with a
  fixed disclaimer. Investment decisions stay with Michael.
- **Learning is silent, but bounded (Michael's decision, 2026-11-07).** Juno writes what it notices to `observed/`
  without asking: his edits to its drafts, his sent mail, how he talks in Slack, interests he mentions. Because
  silent memory writes are how OpenClaw was compromised, four limits apply: only Michael's own words and actions
  are sources, plus Juno's own runs for faster procedures (inbound mail feeds a separate context-only file,
  `observed/people.md`; web pages and transcripts never feed memory); entries are descriptions, never rules, and
  cannot change permissions or recipients; each file is capped at 8,000 characters by the hook; and every change
  is listed in the next brief or check-in, with "forget X" deleting for real. `me/` stays the confirmed layer.
- **Fable stays out of the loop.** Routine runs on Fable would cost roughly eight times the tiered estimate for no
  gain in a triage or a brief. Fable is for sessions like this one.
- **Slack free plan can work but hides history after 90 days**, so the coordinator keeps its own record either way.
- **WhatsApp is out**; Meta's Business API now bars general-purpose AI assistants and needs a public webhook.
