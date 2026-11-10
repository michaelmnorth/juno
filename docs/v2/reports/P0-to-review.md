# Phase 0 closing note for the review chat (2026-11-10)

Paste this into the review chat. Code facts only; details are in `P0.md`, `P0-ledger.md`, `../AUDIT.md` and
`../DEVIATIONS.md`.

Phase 0 is finished and merged to master (2c158bd, pushed). The bridge was restarted on it and 344 tests pass.
The owner approved all eight of the review's additions.

## The eight additions

1. **Backups.** `tools/backup.py` encrypts the git-ignored personal layer plus the session transcripts with gpg
   AES-256. The passphrase comes from 1Password (`Agent-Secrets/Backup-Juno/passphrase`). Backups go to the folder
   in `me/backup.yaml`, and the last 14 are kept. Restore and the drill only go into an empty scratch folder.
   - Tested on synthetic folders: no plaintext names in the ciphertext, a wrong passphrase fails, and the drill
     checks each file's sha256 against a manifest inside the archive.
   - Nightly at 3:30 once `me/backup.yaml` exists. Not yet run on real data; that's the owner's step.
2. **Web tools only in the research agent.** A PreToolUse hook (`gate_web.py`) denies WebSearch and WebFetch in
   Juno's runs unless the hook input's `agent_type` is `researcher`.
   - Live check on Haiku: the coordinator's own search was refused, and the researcher fetched a page.
   - Code-tab sessions aren't gated.
3. **YouTube agent.** Its tools are now `Read` plus `Bash` and `PowerShell` limited to `python tools/youtube.py *`.
4. **One state-writing run at a time.** A reentrant `RUN_LOCK` in the bridge wraps every model run and the
   coach-sheet script. A test proves three concurrent runs never overlap.
5. **Per-run cost cap.** The CLI reference says `--max-budget-usd` counts only the current invocation, subagents
   included, even with `--resume`. It's checked between steps.
   - DMs now pass $1.50. Over that, the session resets and the owner gets a plain line.
   - No cap can stop one call midway (DV8), so P1 has to cap request size before the call.
6. **Missing scripts.**
   - Tempo has a new `tools/slots.py` for free slots, conflicts and exact times.
   - Rep uses `hevy_pull.py` and `sheets.py`, and says sleep, weight and macros aren't connected.
   - Ledger says money data isn't connected.
   - Ping is removed.
   - A test fails if an agent names a script that doesn't exist.
7. **Build rules.** They're in `docs/v2/BUILD-RULES.md`, not in CLAUDE.md (O9).
8. **Prefix split.** Measured with CLI toggles on Haiku 5.5 instead of the token counting endpoint, since there's
   no API key yet (O1). The whole measurement cost $0.036.

   | What was turned off | Tokens it removed |
   |---|---|
   | (full prefix) | 58,612 total |
   | Connectors (they load as deferred names) | 3,387 |
   | Skills listing | about 0 |
   | Agent tool and agent listing | 4,414 |
   | All built-in tool definitions | 36,507 |
   | Claude Code system prompt | 3,400 |
   | CLAUDE.md, imports and project memory | 11,465 |
   | (what's left) | 888 |

   - Juno's runs now load only the 12 built-in tools her runs actually use: 41,342 tokens.
   - `JUNO_TOOLS=all` rolls it back.
   - The full figure, 58.6K, comes from this environment; the bridge's own session files had a 41K median. The
     2026-11-17 ledger gives the bridge's post-trim number and the first Sonnet DM cost.

## The three unknowns, closed

- **Timer and DM overlap.** Five paths started model runs on their own threads with no shared lock:
  - DM batches (one lock per channel only)
  - APScheduler jobs (a 10-thread pool)
  - approval taps
  - the watchers
  - button taps that start a DM run

  `RUN_LOCK` now covers all of them.
- **What `bridge.log` records.** It rotates at 2 MB × 3, at INFO level. The 738 lines break down as:
  - 367 from APScheduler
  - 209 from the bridge itself
  - 162 from Slack Bolt's connection lines

  There are no tokens in it, and Juno's runs get none. Two paths can log model text: a failed handoff (its first
  200 characters) and a failed DM batch's trace. No message bodies are logged.
- **Per-script dedupe.**
  - Already deduped: `inbox.py`, `coach_sheet.py`, `people_queue.py`, `watch_history.py` and approvals.
  - `gmail.py draft` had none. A second draft in the same thread within 12 hours now returns the first.
  - `gcal.py hold` has none; it relies on the run lock (backlog).

## Also done

- Lesson Save and Skip are handled in code. The bridge writes exactly the card's line, never to tier or recipient
  config.
- Ping outcome signals are recorded: `ping.posted`, and `ping.answered` when the owner replies within the hour.

## A fact for the L1 idea

- A lean one-shot CLI call cost $0.49 when it kept Claude Code's default system prompt.
- With `--system-prompt` replaced, it costs about $0.007, and the base measured 888 tokens.

## New deviations

DV7 (the prefix is mostly built-in tools) and DV8 (no cap stops one call). DV2 is resolved and DV5 is fixed.

## Still open

These are the owner's steps or wait on time:
- the backup folder, passphrase and first drill
- the heartbeat monitor
- the 50-DM ledger gate on 2026-11-17

Next is planning the work twin (P7).
