# P0 audit · Juno v1 as built (2026-11-10)

Code facts from the repo at `db0629c` (master) plus branch `v2-p0-audit`. Personal files were measured (sizes,
counts, token usage numbers), never read for content. Each item is **confirmed** (the kit's ASSUMED statement holds),
**differs** (how), or **unknown**.

## 1. How the bridge invokes Claude

| Item | Status | Finding |
|---|---|---|
| Invocation | confirmed | `gateway/claude_runner.py` runs `claude -p <prompt> --output-format json --permission-mode acceptEdits` in the repo folder, so CLAUDE.md, `.claude/agents`, skills, hooks and settings all load. Subscription login, no API key. |
| DMs: cold or resumed | **differs** (kit: unknown) | DMs **resume one Claude Code session per Slack channel** (`--resume`, `state/slack-sessions.json`). A session is closed after 12 h of quiet; the old session is resumed once on Haiku to write `state/handoff.md`, which opens the next session. Timer jobs are cold (`resume=None`). Approval runs resume the session that asked. |
| Where transcripts live | confirmed | `~/.claude/projects/<repo-path>/<session>.jsonl`, plus `<session>/subagents/*.jsonl`. Outside the repo; not backed up. The Code tab's own sessions live in the same folder (entrypoint `claude-desktop` vs `sdk-cli`). |
| Model per job | **differs** | DMs and approval runs passed **no model**: they ran on the account default (Opus 5.5). Jobs used aliases (`haiku`, `sonnet`, `opus`), not pinned IDs. Subagents set their own alias in frontmatter. P0 change: exact IDs everywhere, DMs and approval runs on `claude-sonnet-5-5` at `--effort low` (`gateway/ping_policy.py`). |
| Caps | **differs** | Jobs pass `--max-turns` and `--max-budget-usd` (`ping_policy.JOB_LIMITS`). DMs have none. The budget flag does not stop a single expensive call: the handoff ran $1.75 against a $0.15 cap. |
| Lean lane | confirmed (partial) | One job already runs as an L1-style call: `coach-sheet` uses `--system-prompt` with `--tools "" --strict-mcp-config --setting-sources user --no-session-persistence --max-turns 1` (≈ $0.01 per run). |
| Wake gate | confirmed | Sweeps check Gmail/Calendar change cursors in Python first and skip the model when nothing changed. |

## 2. Tokens loaded before the owner's words, and the cost log

Measured from usage numbers in the session files (`docs/v2/reports/P0-ledger.md` has the method and the table).

| Item | Status | Finding |
|---|---|---|
| Fixed prefix per run | measured | First call of a fresh session, minus the prompt: **33K–49K tokens, median ≈ 41K**, on every model and every job. |
| CLAUDE.md + imports | measured (estimate) | CLAUDE.md 21.4K chars + `learnings/coordinator.md` 0.8K + `me/profile.md` 7.1K ≈ **7.3K tokens** (chars ÷ 4). The other ≈ 34K is the harness system prompt, built-in tool definitions, claude.ai connector tool definitions, and the agent and skill listings; usage numbers can't split these. P1 should measure them with the token counting endpoint. |
| DM context per call | measured | First call of a DM turn: **p50 117K, max 227K tokens**, because the resumed transcript rides along. 3.5 model calls per turn (p50); 6 of 44 turns spawned subagents. 96% of DM input was cache reads. |
| Cost log | **differs (major)** | `state/costs.jsonl` logged `total_cost_usd`, which for a resumed session is the **session's running total**, not the run's. The logged DM costs climb within a session ($0.31 → $8.61), and summing them overstates DM spend about 7×: logged $97.79 for 37 DMs, real ≈ **$13.75** (mean $0.37, p50 $0.20, p90 $1.31, max $2.53). The approval and handoff rows are inflated the same way. The System Map's "$1.69 per DM, 91% of spend" and the kit's $500–1,000 a month extrapolation come from this bug. P0 change: the log keeps each run's own cost, the running total, the session ID and token counts. |
| Status card spend | **differs** | `gateway/cards.py` "spent today" summed the same running totals. Rows from 2026-11-10 on are per-run. |

## 3. Agents and skills

11 agent files, 9 skills, all in `.claude/`. Agents load their own `.md` plus whatever the coordinator passes.

| Agent | Model | Tools | Status |
|---|---|---|---|
| calendar (Tempo) | sonnet | Read, `python tools/scheduling-engine/*`, `python tools/gcal.py events*` | **differs**: `tools/scheduling-engine` does not exist |
| drafter (Quill) | sonnet | Read | confirmed |
| finance (Ledger) | opus | Read, `python tools/finance_query.py *`, Write, Edit | **differs**: `finance_query.py` does not exist |
| health (Rep) | sonnet | Read, `python tools/health_*`, `hevy_*`, `withings_*`, `sheets.py`, Write, Edit | **differs**: no `health_*` or `withings_*` script exists; `hevy_pull.py` and `sheets.py` do |
| inbox-triage (Sorter) | haiku | Read | confirmed; gets a packet of cleaned text from `tools/inbox.py` |
| notifier (Ping) | haiku | Read, `python tools/notify.py *` | **differs**: `tools/notify.py` does not exist; the bridge posts every job reply itself, so Ping is dead |
| reflector (Mirror) | opus | Read, Grep, Glob, Write | confirmed; the one weekly run made 69 subagent calls |
| relationships (Kin) | sonnet | Read, Grep, Glob, `mail_index`, `contacts`, `occasions`, Gmail search/get | confirmed |
| researcher (Scout) | sonnet | Read, WebSearch, WebFetch | confirmed |
| watch-digest (Rewind) | haiku | Read, `watch_history.py`, `youtube.py transcript/info` | confirmed |
| youtube (Reel) | haiku | **Bash** (unrestricted in the tool list), Read | differs: the tool list grants all of Bash; the settings allow list still limits commands to `python tools/*` |

Skills: coach-sheet, evening-checkin, lesson, memory, morning-brief, new-subagent, notes-and-reminders, sweep,
weekly-reflection (1.3K–6.8K chars each). Morning brief and sweep call Sorter; the brief also calls Rewind and,
for birthdays, Quill. Step 7 of the brief still says "call notifier"; the bridge does the posting.

## 4. Tool scripts

18 Python files in `tools/` (16 scripts + 2 helpers), all on the allow list as `python tools/*`.

| Area | Finding |
|---|---|
| OAuth scopes | One Google app: `gmail.modify`, `calendar.events`, `contacts.readonly`, `spreadsheets`. `gmail.modify` is broader than any tool needs (it allows send); scripts expose only drafts, `Juno/` labels, send-to-self and (P0) the bridge's approved send. |
| Writes | `gmail.py` (drafts, Juno/ labels, send-self), `gcal.py` (holds; events and updates only with a one-time token), `sheets.py` / `coach_sheet.py` (fixed cells on the coach sheet), `people_queue.py`, `observed.py`, `watch_history.py`, `inbox.py` (packets, processed state), local `state/` files. |
| Other people's text | `inbox.py` (subjects, senders; the packet for Sorter holds cleaned bodies), `mail_index.py`, `youtube.py` and `watch_history.py` (transcripts), `gcal.py events` (titles and descriptions from others), `contacts.py`. |
| Secrets | `token_store.py` keeps a 1Password service-account key in Windows Credential Manager; tools read Google and Hevy secrets through it inside the process. No secret on a command line. |
| Missing scripts | `scheduling-engine/`, `health_query.py`, `finance_query.py`, `withings_*`, `notify.py` are referenced and absent. |

The detailed per-script table (subcommands, dedupe on writes) is in `docs/v2/reports/P0-tools.md` when the
read-only tool sweep finishes.

## 5. Hooks and deny rules

| Item | Status | Finding |
|---|---|---|
| Hooks | confirmed (3) | `gate_memory_writes.py` (Write/Edit: CLAUDE.md and `.claude/` denied in Juno's runs; `me/ learnings/ people/ CONTEXT.md` denied unattended; `observed/` open), `notify_michael_only.py` (any send/post/reply MCP tool: recipients must be on the allowlist), `gate_outward.py` (Gmail send only for the approved draft ID; no draft edits during an approved send; calendar writes only for approved classes and recipients). All fail closed. |
| Deny rules | confirmed (76) | 3 Read, 1 Edit, 1 Write, 12 Bash/PowerShell (`op read`, `op item`, `printenv`, env listings, plugin and MCP installs), 59 connector write tools (Gmail, Calendar, Slack, Sheets, Docs, Drive, Claude Docs, Spotify). |
| Allow | 26 | `python tools/*`, `python -m pytest*`, WebSearch, WebFetch, 20 read or draft connector tools. Ask: 4 (CLAUDE.md, `.claude/**`). |
| Gap | **differs** | Read, Glob and Grep are not limited beyond the 3 Read denies, so any run can read any file the owner's account can. WebFetch needs no tap, in a run that may already hold mail text and private memory (the trifecta the kit names). |

## 6. Approvals

| Item | Status | Finding |
|---|---|---|
| Who writes the proposal | **differs** | The model appends the entry to `state/pending-approvals.json` itself; the card shows that entry's fields (built in code by `approval_policy.card_text`, not from model prose). |
| Calendar pass | confirmed (partial) | One-time token, SHA-256 stored, 15-minute TTL, bound to class and recipients, spent after the write. Not bound to time or title. |
| Email send | **differs** | Was bound to the draft ID only, and executed by a resumed model run granted the Gmail send tool. A draft edited after the card (by a later run) would have sent the new text. **P0 fix:** the bridge sends in code (`gmail.send_approved`) only when recipients and text still match the card; changed text gets a fresh card. |
| Payload hash | **differs** | None for email. **P0 fix:** `payload_sha256` stored when a card is posted, checked on the tap; a changed entry is refused. |
| Identity | confirmed | Taps and DMs accepted only from the allowlisted Slack user ID. |
| Expiry, replay | confirmed | Cards expire at 30 minutes (email.send never); handled entries reply "Already …". Calendar tokens single-use. |
| Executor | **differs** | A model run executes calendar and other approved actions; only installs (and now email) run in code. |

## 7. State files and concurrency

| Item | Status | Finding |
|---|---|---|
| Writes | confirmed (partial) | `state_store.py` writes JSON atomically (temp file + replace). Several JSONL files (`costs`, `signals`, `audit`, `drafts`) are appended without locks; models also write `pending-approvals.json`, `processed.json`, `timers.json` and `holding.md` directly through the Write tool. |
| Timer vs DM overlap | confirmed, **fixed** | Before P0, five paths started model runs on their own threads with no shared lock: DM batches (`Debouncer`, one lock per channel), timer jobs (APScheduler's 10-thread pool, so two jobs could also overlap), approval taps (Slack handler threads), the approvals and timers watchers, and button taps that start a DM run (status, answers, lessons). Only the coach sheet had a lock. **P0:** `RUN_LOCK` (reentrant) wraps every model run and the coach-sheet script; a DM can wait behind a sweep. |
| Coach sheet | confirmed | A process lock keeps the watcher and the nightly pass apart. |
| Per-script dedupe | confirmed | `inbox.py` skips IDs in `state/processed.json` and Michael's own sent mail; `coach_sheet.py` never overwrites a filled cell; `people_queue.py` ignores a repeat of a waiting entry; `watch_history.py` imports each file once; approvals answer "Already ..." to a second tap and calendar tokens are single-use. `gmail.py draft` and `gcal.py hold` had none. **P0:** a second reply draft in one thread within 12 hours returns the first (`--again` overrides). Holds rely on the run lock. |

## 8. Git, backups, secrets in logs

| Item | Status | Finding |
|---|---|---|
| In git | confirmed | Code, docs, tests, CLAUDE.md, `.claude/`, examples. Private repo on GitHub. |
| Ignored | confirmed | All of `me/` (except examples, `automation.yaml`, `proactivity.yaml`), `people/`, `observed/`, `learnings/`, `state/` (except `proposed-lessons.md`), `data/`, `logs/`, `domains/*/CONTEXT.md`, `**/private/`, every `.env`. |
| Backups | **differs** | **None** before P0. The personal layer (≈ 40 MB across `me/`, `people/`, `observed/`, `learnings/`, `state/`, `data/`, `domains/`) and the session transcripts (≈ 130 MB) exist only on this PC. **P0:** `tools/backup.py` (gpg AES-256, passphrase in 1Password, restore drill into a scratch folder), nightly at 3:30 once the owner names the folder. |
| Secrets in logs | confirmed | `logs/bridge.log` rotates at 2 MB × 3, INFO level. Of 738 lines: APScheduler job lines (367), the bridge's own (209: DM timing, skips, card and vault IDs, the allowlisted user ID), Slack Bolt connection lines (162). No tokens: the bridge reads them from 1Password into its own environment and runs get none. Two lines can hold model text: a failed handoff logs its first 200 characters, and the trace of a failed DM batch. No message bodies are logged. `--verbose` (DEBUG) would log Slack payloads; the logon task doesn't use it. |

## 9. Tests

| Item | Status | Finding |
|---|---|---|
| Layout | confirmed | `tests/` holds 21 files, run with `python -m pytest tests`. |
| Root discovery | **differs** | `python -m pytest` from the root failed: `proposals/watch-digest/tests/test_watch_history.py` collides with `tests/test_watch_history.py`. **P0 fix:** `pytest.ini` (`testpaths = tests`, skip `proposals/`). |
| CI | **differs** | None. **P0 fix:** `.github/workflows/tests.yml` on every push (Windows runner, Python 3.14). |
| Count | | 296 before P0, 344 after. |

## 10. Quick-fix checklist (brief P0, deliverable 3)

| Fix | State |
|---|---|
| Unfurling off on every bot message | done, tested (`slack_bridge.no_unfurl`) |
| Approvals bound by hash, stored payload executed | done for email (code send, hash, fresh card on change), tested; calendar keeps its token |
| `pause` / `resume` and a flag file, no model | done, tested (`gateway/brakes.py`, `state/PAUSED`) |
| External heartbeat with a phone alert | code done, tested; needs the owner to create a free monitor and store its ping URL in 1Password (`Heartbeat-Juno/url`) |
| Encrypted off-box backup, restore tested | code done, tested on synthetic folders (`tools/backup.py`); the owner names the folder, fills the passphrase, and runs the first backup and drill on real data |
| Daily spend cap | replaced 2026-11-10 by notices at $5 and $10 that never pause (DV9) |
| Test discovery from the root; CI | done |
| Lesson saves from Slack, retire Ping, Tempo's engine | done: Save and Skip written in code (`gateway/lessons.py`); notifier removed; `tools/slots.py` |
| Interim cost relief | done: pinned IDs; DMs on Sonnet 5.5 low effort |
| Signal capture | done: approval, approved-send, lesson and ping outcomes (`ping.posted`, `ping.answered` within the hour) written by the bridge |
| Added after the audit: web tools only in Scout | done, live-checked (`.claude/hooks/gate_web.py`) |
| Added: Reel without open Bash | done |
| Added: one state-writing run at a time | done (`RUN_LOCK`) |
| Added: per-run cost cap | done for DMs ($1.50 via `--max-budget-usd`, which counts only the current invocation); jobs already had theirs. Neither stops one call midway (DV8) |
| Added: missing scripts | done: removed or replaced; a test fails if an agent names a script that doesn't exist |
| Added: build rules | done: `docs/v2/BUILD-RULES.md` (O9) |
| Added: prefix split, DM cost on Sonnet | split done (`reports/P0-ledger.md`, DV7); DM cost on Sonnet waits for real DMs after the merge |
