# Build plan: phases, tasks, done-when

Each phase ends with a measurable "done when" and a decision point. Tasks are ordered so each one can be done in one
sitting. **[M]** marks the items only Michael can do (accounts, approvals, devices). Everything else a Claude Code
session in this folder can do, and most of it is scaffolded already.

## Queued 2026-11-07 (build in this order; research in `06-RESEARCH-PROACTIVITY-AND-YOUTUBE.md`)

Each item can be built and tested by a session in this folder without Michael. **[M]** marks the only stops for him.

0. **Silent learning (done 2026-11-07):** `observed/` layer, hook cap and tests, draft-vs-sent comparison in the
   sweep, `state/drafts.jsonl`, "Picked up" in the brief and check-in, reflector consolidation. Verify live: the
   first draft Michael edits and sends shows up in `observed/voice.md` and the next brief.
Items 2-5 done 2026-11-07 (`gateway/ping_policy.py`). Item 1 is a placeholder (`sweep_should_wake`) until item 1's
Gmail and Calendar reads exist in Python; sweeps run on Haiku meanwhile.

1. **Sweep wake gate** (Hermes `wakeAgent`): before running `claude -p`, the bridge checks in Python whether Gmail,
   today's calendar or `state/reminders.yaml` changed since `state/sweep-cursor.json`. Nothing changed: no model call,
   one log line. This is the biggest cost cut. Needs Gmail/Calendar read access from Python (Phase 2 tools) or a
   cheap Haiku pre-check until then.
   **2026-11-08:**
   - Built: `sweep_should_wake` and `tools/google_read.py`.
   - Google sign-in done: read-only access, refresh token in `Agent-Secrets/Google-Juno`.
   - `google_read.py changes` works by hand through `op run --env-file=tools/google.env`.
   - On in the bridge: `token_store.py` loads the three `GOOGLE_*` values as optional secrets, all three or none,
     and the bridge logs "Google read access for the wake gate: on". Michael lifted the `Read(**/*token*)` deny for
     this.
2. **Code-enforced pings:** the sweep returns JSON `{notify, urgency, items[]}` instead of a bare SILENT marker; the
   bridge enforces quiet hours, the 5-a-day cap and per-item de-duplication (`state/pinged.json`) in code.
3. **Hold, don't ping:** non-urgent findings go to `state/holding.md`; the 07:00 brief and 20:30 check-in empty it.
   Pings are only for leave-by times, approvals and real reply-needed mail.
4. **Continuity:** the sweep reads `state/sweep-last.md` with "do not repeat what was already reported; do not invent
   work". Failures always post once per failure streak, never hidden by silence (closes Phase 1 item 7).
5. **Model per job:** Haiku for sweeps, Sonnet for the brief and check-in, pinned in the bridge, never chosen by the model.
6. **Done 2026-11-07.** **YouTube subagent** (`youtube`, persona "Reel", Haiku; Sonnet for videos over an hour): `tools/youtube.py`
   with `transcript`, `info`, `search`, `playlist`; `youtube-transcript-api==1.2.5` then `yt-dlp==2026.10.26`;
   cache in `data/youtube/`; 1 request per 3 s, about 100 a day, 15 min back-off; transcripts wrapped as untrusted.
   Allowed tools: that script and its cache only. Whisper fallback off by default. Done when: summary with
   timestamps for 5 real videos Michael picks, one with no captions handled cleanly.
7. **Approval cards v2** (Grok Bot pattern): Allow once / Always allow / Deny, cards from timers expire after 30 min,
   an audit log in `state/audit.jsonl`. Then wire execution so approved sends and the `calendar.hold` auto_notify
   rule actually run (Phase 3 item 2).
8. **Drafts offered in Slack** (Muse pattern): each proactive draft posts with Send / Edit / Skip.
9. **Memory he can see:** "what do you remember about X" and "forget X" across `me/` and `observed/` (deletes for
   real, confirms with a diff).
10. **Leave-by timers:** the morning brief sets one-shot timers in `state/timers.json` for today's events with a place,
    instead of waiting for the next 2-hour sweep.
11. **New-subagent routine:** a `new-subagent` skill. Michael describes a job in Slack; Juno drafts the agent file,
    tool script, permissions and tests, and posts them for approval. Nothing is installed or enabled without his tap,
    and only vetted, pinned packages (no marketplace skills or MCP servers).

Items 7-11 done 2026-11-07: approval cards v2 with execution (`gateway/approval_policy.py`,
`.claude/hooks/gate_outward.py`), drafts offered in Slack, the `memory` skill, leave-by timers
(`state/timers.json`), and the `new-subagent` skill. Learning also covers Juno's own runs and inbound mail as context.

**[M] Michael, when convenient:** which morning block moves (see `me/schedule.md`), the coach sheet link, the macro
tracker, and Plaid setup (Phase 4b item 1). Whether he connected anything to Muse for YouTube (curiosity, not a blocker).

## Phase 0: Foundations (this week)

Goal: the folder is a working Claude Code project that Michael can talk to in the Code tab, with guardrails in place
before any connector is attached.

1. **[M] Approve the folder plan**: `C:\Users\Michael\Claude-Personal\personal-coordinator\` as the coordinator;
   `Claude-Personal\projects\` for `support-agent`, `Claude Certified Architect`, `starter-app`, `The Roast Room`
   (moves happen one at a time, each on a yes). Decide who owns `Claude\Fin Lessons Learned` and
   `Claude\Scheduled\fin-lessons-harvest` (work content in the personal area).
2. Review the scaffold: `CLAUDE.md`, `.claude/settings.json`, `.claude/agents/*.md`, `.claude/hooks/*`, `me/*`.
   Rename the persona if Juno is wrong.
3. **[M] Fill `me/profile.md`, `me/schedule.md`, `me/voice.md`** (paste three real emails and three real texts),
   `me/proactivity.yaml` (quiet hours, max pings), `people/` (coach, CPA, family).
4. **[M] Install prerequisites**: 1Password CLI (`winget install AgileBits.1Password.CLI`), Bun (for channels), and
   `pip install -r tools/requirements.txt`. Create the `Agent-Secrets` vault and a read-only service account; store the
   token in Windows Credential Manager, never in a file.
5. Run the hook tests (`python -m pytest tests/`) and `claude plugin validate .claude/agents`. Every deny must deny.
6. **[M] Connect Gmail and Google Calendar connectors** in the desktop app for this project (Drive is already connected).
7. First conversation in the Code tab: "morning brief" and "what's on my calendar this week" working from connectors.
8. `git init`, first commit (logs, state, data are git-ignored).

**Done when:** the morning brief runs on demand from the Code tab, the deny tests pass, and no file in the repo
contains a secret.

## Phase 1: A ping away, in Slack (week 2)

Goal: Michael talks to the coordinator from Slack on his phone and gets two scheduled touchpoints a day.
Decision 2026-11-06: Slack free workspace, not Telegram. The bridge in `gateway/` is built and tested offline.

1. **[M] Create the Slack app** from `gateway/slack-app-manifest.yaml` (api.slack.com/apps → Create New App → From a
   manifest → your free workspace). Install it, copy the Bot token (`xoxb-`), create an App-level token (`xapp-`) with
   `connections:write`. Copy your member ID (profile → three dots → Copy member ID) into `me/notify-allowlist.json`.
2. **[M] Put both tokens in 1Password** (`Agent-Secrets` vault, item `Slack-Juno`) and run the bridge through
   `op run --env-file=gateway/slack.env -- python gateway/slack_bridge.py`. Plain environment variables work for the
   very first smoke test only.
3. `pip install -r gateway/requirements.txt`, then `python gateway/slack_bridge.py --once "hello"` to prove the
   `claude -p` round trip works before touching Slack, then start the bridge and DM the bot.
   **Confirm before relying on it:** a `claude -p` run started by the bridge sees the Gmail/Calendar connectors. If it
   does not, reads go through our own Gmail/Calendar scripts in `tools/` (Phase 2 builds them anyway for the sweep).
4. The bridge's scheduler runs the anchors from `me/proactivity.yaml` (morning brief 07:00, evening check-in 20:30,
   sweep every 2 h in the window, weekly reflection Sunday 18:00) as unattended runs and posts to Michael's DM.
5. Turn on Remote Control in the Code tab as a second surface (`/rc`), with push for actions required.
6. **[M] Live with it for a week.** Use `/lesson` for every correction. Tap buttons where offered.
7. Heartbeat: the bridge writes `state/last-run.json`; a desktop scheduled task checks it hourly and posts through the
   Slack connector if the bridge has been silent for 3 h (also the proof that the consumer Slack connector can post).
8. Run the bridge at logon: Task Scheduler → `op run --env-file=gateway/slack.env -- python gateway/slack_bridge.py`,
   working directory this folder, "run whether user is logged on or not" off (it needs your session for `claude`).

**Done when:** seven consecutive days of morning brief + evening check-in delivered to Slack, at least ten `/lesson`
lines saved, and Michael has answered at least one approval card from his phone.

## Phase 2: Personal assistant (weeks 3-4)

Goal: inbox and calendar handled the way the work coordinator does it, plus the proactive drafts Michael liked.

1. `inbox-triage` on Gmail (read-only), with `domains/admin/email-rules.md` seeded from a one-time review of the
   last 200 emails ("these senders are bills, these are family, these are noise").
2. `drafter`: Gmail drafts in his voice; proactive drafts for anything triage marks `reply-needed`. Send stays gated.
3. `calendar`: reuse the scheduling engine (pin it from the `scheduling-agent` branch as a submodule or versioned
   zip in `tools/scheduling-engine`), swap Outlook terms for Google Calendar, preferences from `me/schedule.md`.
   Event creation gated.
4. Reminders and notes as skills: "remind me", "note that", "what did I say about X" against `domains/admin/notes/`
   and `state/reminders.yaml`; due reminders surface in the sweep.
5. Pre-event prep in the evening check-in: who, last thread, open items, travel time.
6. Signals logging (`state/signals.jsonl`) and the weekly `reflector` with proposed-lesson cards.

**Done when:** two weeks in which every reply-needed email got a draft within one sweep, no duplicate drafts, and
Michael accepted at least three reflector proposals.

## Phase 3: Hardened runtime (week 5)

Goal: timers that survive session restarts and approvals that work headless.

1. Windows Task Scheduler job: `claude -p` runs the sweep skill every 2 hours with `--permission-mode` rules from
   `settings.json` and `--max-budget-usd`. **Confirm before building:** `-p` under the `/login` credential loads the
   Gmail/Calendar connectors; if not, the sweep reads mail through our own Gmail API tool (op-wrapped).
2. Headless approvals: hooks return `defer`; a tiny script posts the deferred call to the channel with Approve /
   Deny buttons and resumes with `claude -p --resume <session-id>` on Approve.
3. Cloud routine for the one job that must run when the PC is off: a daily "anything urgent?" sweep over connectors.
4. Cost log: tokens and model per run into `state/costs.jsonl`; a line in the weekly reflection.

**Done when:** two weeks unattended with the PC asleep overnight, no missed morning brief, one approval handled from
the phone with the Code tab closed.

## Phase 4a: Health (weeks 6-7)

1. **[M] Confirm devices and apps**: lifting app (Hevy?), Withings devices, macro tracker, watch, iOS version.
2. **[M] Install HealthExport (free, iOS 26.2+) or Health Auto Export Premium ($24.99 lifetime)**; export daily
   JSON to an iCloud Drive folder; install iCloud for Windows so the folder lands on the PC.
3. `tools/health_import.py`: watch the folder, load metrics into `data/health.sqlite` (sleep stages, weight, HRV,
   steps, dietary energy and macros, workouts). Test with a real export first; field shapes are unverified.
4. **[M] Hevy Pro + API key** into 1Password. `tools/hevy_pull.py` (workouts, exercise history, routines) on the
   2-hourly sweep.
5. **[M] Withings developer app** (free) → OAuth once → `tools/withings_pull.py` for weight, body comp, sleep score.
6. **[M] Share the coach's Google Sheet** with a service account (Editor). `tools/sheets.py` reads the program tab
   and appends to a Log tab only.
7. `health` agent: Monday report (sleep, weight trend, training volume, macro adherence vs targets), "build next
   week from the coach sheet" → Hevy routines (gated), and on-demand questions. All numbers from SQL.
8. Baselines and goals into `domains/health/`.

**Done when:** four consecutive Monday reports with correct numbers (spot-checked against the apps), and one week's
routines created in Hevy from the sheet with Michael's approval.

## Phase 4b: Finance (weeks 8-9)

1. **[M] Plaid: new team, "Personal use", Trial plan.** Link up to 10 Items (banks, cards, brokerage, retirement).
   Persist every access token in 1Password immediately; Trial slots are for life.
2. **[M] SimpleFIN Bridge ($15/yr)** for anything Plaid cannot link; Gmail label for statement PDFs (Fidelity,
   Vanguard) parsed locally.
3. `tools/finance_fetch.py` (op-wrapped): balances, transactions, holdings → `data/finance.sqlite`, with account
   numbers reduced to last-4 before anything is written.
4. `domains/finance/`: `accounts.yaml` (names, type, last-4, business vs personal), `tax-calendar.yaml` (2026/2027
   estimated dates, limits from §D of the research), categories.
5. `finance` agent: monthly report (cash flow, income vs run-rate, spend by category, net worth delta), quarterly
   estimated-tax reminder with the set-aside math and the fixed disclaimer, contribution-room check (SEP vs Solo
   401(k)), "what changed this week". Reports only; no external writes exist.
6. **[M] Share the first report with the CPA** and record their corrections as lessons.

**Done when:** three monthly reports Michael trusts, one estimated-tax payment reminded on time with a number the CPA
agreed with, and a written confirmation that no credential in the system can move money.

## Phase 5: Gateway and portability (weeks 10-12)

1. `gateway/`: add the `CLAUDE_BACKEND=sdk` path to the existing Slack bridge: `query()` from `claude-agent-sdk`
   with this folder as `cwd`, script-gated jobs (check for new data before waking the model), `max_budget_usd` per
   run, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`. API key from 1Password; Max's $100/month API credits cover the
   estimated $8/month.
2. Run it as a Windows service under a dedicated low-privilege user. Later: a mini PC or $5 VPS so the laptop can sleep.
3. Package the agents, skills and hooks as a plugin (`.claude-plugin/plugin.json`) so the same roster loads in Claude
   Code, Cowork and the gateway; the cohort offer in `The Roast Room` can reuse it as teaching material.
4. Retire the Phase 1 channel session once the gateway has run clean for two weeks.

**Done when:** laptop asleep overnight, morning brief still arrives; one month of cost under $15.

## Phase 6: Later and optional

- Video pipeline: Drive folder → `tools/video_split.py` (ffmpeg, motion/silence based) → compressed clips or links
  to the coach.
- `business` agent for the venture: pipeline, offer copy, cohort ops from `domains/business/`.
- Learning plan: the researcher runs a weekly "what changed in Claude tooling" digest tied to Michael's exam and the
  cohort material.
- Oura/Whoop if he wants a wearable sleep score; macro CSV import for nutrient detail.
- WSL2 for a real sandbox; Managed Agents if hosted sessions with vaults become worth $0.08/hour.

## Decision points along the way

| After | Decide |
|---|---|
| Phase 0 | Persona name; which loose folders move first (channel decided: Slack) |
| Phase 1 | Keep Remote Control push on or rely on the channel only; proactivity budget |
| Phase 2 | Which action classes graduate to auto (drafts never send; calendar holds likely first) |
| Phase 3 | Whether `-p` connectors work or we go to our own Gmail tool early |
| Phase 4a | Hevy routine writes to auto, or keep approving weekly |
| Phase 4b | Plaid pay-as-you-go worth it past 10 Items; CPA review cadence |
| Phase 5 | Stay on the PC or move to always-on hardware |

## Proposed 2026-11-08 (needs Michael's yes)

From the overnight research (`docs/07-RESEARCH-OVERNIGHT.md`, 20 web finds and 8 videos). Ranked by value for
effort. Nothing here is built until Michael says yes.

| # | Idea | Why it fits | Effort | Touches |
|---|---|---|---|---|
| 1 | **Quarantined triage.** Sorter reads mail and hands on only a small structured summary; the drafter and Juno never see raw email bodies. Strip hidden HTML first. | The strongest point every security source makes: prompt rules alone do not stop injection, structure does. | M | inbox-triage, sweep, drafter |
| 2 | **Trust label on every item** (Michael typed it, known person in `people/`, unknown sender) that limits what Juno may do with it. | Cheap, makes the approval rules sharper. | S | sweep, CLAUDE.md |
| 3 | **Learning lifecycle.** Each `observed/` note gets pending, promoted or retired and a confidence; the weekly reflection promotes or retires, stale guesses fade. | Matches the silent learning Michael wants, and keeps wrong guesses from hardening. | S | observed/, reflector |
| 4 | **Real wake gate** (already queue item 1): a cheap script decides if a sweep runs at all. | Biggest cost cut; every proactive-agent source agrees. Waits on the Google sign-in setup. | S once unblocked | bridge, sweep |
| 5 | **Kin: cold contacts and birthday drafts.** Weekly "haven't talked to X in a while" (family and close friends only), and a ready drafted note two days before a birthday. | Direct extension of what Michael asked Kin to do. | S | relationships, drafter |
| 6 | **Thin job briefs with turn caps.** Each timer prompt becomes three lines (task, guardrails, what done means) plus a per-job turn and budget cap, using the new cost log. | Runaway runs become visible and cheap to stop. | S | bridge, skills |
| 7 | **Session handoff note.** When a Slack session resets after 12 h quiet, write a short fixed-format handoff (open threads, promises, decisions) for the next session. | Keeps context small without forgetting what was in flight. | S | bridge, CLAUDE.md |
| 8 | **Debounce Slack bursts.** Several quick DMs in a row become one run. | Michael types in bursts from his phone; saves runs and gives better answers. | S | bridge |
| 9 | **Evals for the drafter and Sorter.** Fixture emails with expected labels and voice checks, run with `claude plugin eval` or pytest, so changes cannot quietly make them worse. | Turns "feels right" into a score before Michael sees a draft. | M | tests, drafter, inbox-triage |
| 10 | **Memory consolidation pass.** A cheap model merges duplicate `observed/` lines nightly so the 8,000-character cap is never hit mid-run. | Common upgrade in long-running personal agents. | S | evening check-in |

**Built 2026-11-08 (Michael: "All the small ones"):** 2 trust labels (cf3e859), 3 and 10 notes that age and
nightly tidy-up (4aa5515), 5 Kin cold contacts and birthday notes (a583ec8), 6 thin briefs with caps (6f19b6e),
7 session handoff (36b50e9), 8 debounced bursts (f49fcaa). 4 (wake gate): live 2026-11-08 (queue item 1);
1 built 2026-11-09 with the Sorter fix (`tools/inbox.py`); 9 is medium and not started.

**Later (Michael 2026-11-08):** once Juno's phases are done, translate the pattern to the work environment as a
Fin-implementation coordinator. Draft ideas in `docs/private/09-WORK-ASSISTANT-IDEAS.md` (kept on this PC) (architecture only, no client
data). Remind Michael.

## Proposed 2026-11-09 (from Michael's Muse comparison; needs his yes)

Michael ran Muse alongside Juno for a day (his export: a Sunday-evening proactive message, a 7:15 brief, a 9:15
nudge). What Muse did better, and the lean way Juno would do it. Lean first per `docs/17-BUILD-PATTERNS.md`.

| # | Idea | What Muse did | Lean version for Juno | Effort |
|---|---|---|---|---|
| 1 | **Event-triggered prep packets** | Saw his Amazon order confirmation, matched it to the phone he'd talked about, and built a 2-page setup checklist unasked, with the two decisions he still had to make. | The sweep already sees receipts. When a receipt or shipping mail matches an open goal or plan (`me/goals.md`, `state/handoff.md`, recent DMs), one Sonnet call writes a short checklist as a Google Doc or a Slack post the evening before it arrives. Decisions are listed, never taken. | M |
| 2 | **A brief with the whole week** | Today plus the next 7 days, a fresh event scan against his criteria, health numbers, money due dates, and "Today's top moves" (3 lines). | Keep the card for Needs you; add a "This week" section from the calendar and a 3-line "Top moves". Event scan waits on a researcher job with his criteria (in `me/private/`). Health and money lines wait on Phases 4a and 4b. | M |
| 3 | **Restraint** | Prepared two more messages and didn't send them because the brief had covered them; kept the nudge short. | `state/pinged.json` already dedupes pings; extend it so a reminder that fires after a brief that covered it shrinks to one line. | S |
| 4 | **Security catches** | Flagged the Google "Juno was granted access" alert. | Juno caught it too (Needs you, 2026-11-09). Keep it. | done |
| 5 | **Read the mail it flags** | Muse read Gmail; Juno's 7:01 brief said "inbox not checked yet" and "an account alert I couldn't read". | **Built 2026-11-09 (Michael: "Fix Sorter first").** `tools/inbox.py new` sorts by trust label, Gmail tab, unsubscribe header, subject words and `domains/admin/inbox-sort.yaml`; people he knows, bills and account-security notices go to Sorter as a packet of cleaned text (also proposal 1 of 2026-11-08, quarantined triage). The brief reads overnight mail itself. Live check on 75 emails: 55 settled in code, 20 to Sorter. | M |

## Proposed 2026-11-09: leave-by day planner (Michael: "after I leave my parents' house, schedule my day")

He asks "after Mom and Dad's, plan my day" and Juno answers: "Lunch ends about 2. The Big Walk is at 7 in Midtown,
45 to 60 minutes from home at 5:30 traffic. Leave by 5:50; you have 2 to 5 free." Holds for the drive go on his
calendar with no tap (holds are auto).

Lean design:
- **Addresses (built 2026-11-09):** Google Contacts sync (`tools/contacts.py sync`, read-only) brings in
  everyone's address; `people/` profiles add an `address` line only when it matters. Event locations come from the
  calendar. "Home" is his own contact card or `me/profile.md` once he confirms which home.
- **Travel time:** a small script, `tools/route.py <from> <to> --leave|--arrive <time>`, calls the Google Maps
  Routes API with traffic. One request per leg, free monthly tier covers a personal planner many times over. Needs
  a Maps API key in 1Password (a fill-in card). No model involved.
- **Planning:** the scheduling engine does the time math (gaps, buffers); one Sonnet call only writes the plan in
  Juno's voice. Holds for drive time via `tools/gcal.py hold`.
- **Proactive later:** the sweep sees two events with locations on the same day and a gap under the drive time,
  and pings a leave-by time (the `leave_by` ping kind already exists).
- **Repeatable:** addresses in Contacts, the key in the vault, the script and engine are generic; nothing personal
  is in code.
