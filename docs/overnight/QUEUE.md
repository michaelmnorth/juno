# Overnight queue, 2026-11-08 (Michael asleep until about 10:00 ET)

Michael asked (2026-11-08, 00:50): work through the night, research what people have been building and saying in
the last few months, build what does not need him, commit, and have a summary ready when he wakes.

Each hourly run takes the **first unchecked item**, does it, ticks it with a one-line result, appends to `LOG.md`,
and commits. Items 1 and 2 may run in either order if one is blocked. If an item needs Michael, write the question
into `MORNING-SUMMARY.md` under "Needs you", tick it as `[~] blocked: <why>` and move on.

- [x] 1. (done: 20 finds in docs/07, section 1) **Research: what people built and say (Reddit, Hacker News, GitHub, blogs), Aug to Nov 2026.**
  Topics: personal AI assistants and "chief of staff" agents, Claude Code subagents and skills, orchestration
  patterns (dispatcher plus specialists, context hygiene, memory layers, proactive agents and heartbeats), relationship
  and CRM agents, learning-from-feedback loops, Slack or phone front ends. Use WebSearch and WebFetch. Note for each
  find: what it is, link, date, the idea worth stealing, and how it maps to Juno (agent, skill, routine, or "skip").
  Output: `docs/07-RESEARCH-OVERNIGHT.md`, section 1. Aim for 15 to 25 finds, ranked.
- [x] 2. (done: 8 videos in docs/07, section 2) **Research: video transcripts.** With `python tools/youtube.py search "<query>" --limit 5` and
  `python tools/youtube.py transcript <id>`, find 5 to 8 recent (2026) videos on Claude Code orchestration, subagents,
  personal agents, and agent memory. Respect the tool's limits: if it exits 3, stop this item and note it. Summarize
  lessons with timestamps in `docs/07-RESEARCH-OVERNIGHT.md`, section 2.
- [x] 3. (done: gateway/installer.py, 484f390) **Build: bridge-side installer for `subagent.install`.** Today an approved install fails because a `claude -p`
  run cannot write `.claude/agents/`. Make the install deterministic Python instead: the `new-subagent` skill writes
  `proposals/<name>/install.json` (`{"files": {"<proposal path>": "<final path>"}, "pip": ["pkg==x.y.z"],
  "claude_md": {"roster": "...", "routing": "..."}}`); on Allow once the bridge copies exactly those files (final
  paths only under `.claude/agents/`, `.claude/skills/`, `tools/`, `tests/`, `learnings/`), installs only pinned
  `pkg==version` lines from PyPI, appends the two CLAUDE.md lines, runs `pytest`, and rolls everything back on
  failure. Add tests (path escapes refused, unpinned packages refused, rollback works). Update the skill text and
  `gateway/approval_policy.py`. Commit.
- [x] 4. (done: fe14187) **Build: cost log (Phase 3 item 4).** `claude_runner.run` already parses `total_cost_usd` and
  `duration_ms`; append one line per run to `state/costs.jsonl` (`at`, `job`, `model`, `cost_usd`, `duration_ms`,
  `is_error`). Pass the job name from the bridge. The weekly reflection already sums it. Tests. Commit.
- [x] 5. (done: restarted 01:31, Bolt running, one copy) **Restart the bridge on the new code (only if items 3 or 4 changed `gateway/`).** Run the full test suite
  first; only if it passes: stop the two `pythonw.exe ... gateway\slack_bridge.py` processes, run the scheduled task
  "Juno Slack Bridge", wait 15 s, and confirm `logs/bridge.log` shows "Bolt app is running!" with one pair of
  processes. If it does not come up, `git revert` the gateway commit, restart again, and note it. Must finish before
  06:30 so the 07:00 morning brief is safe; after 06:30, skip and note it.
- [x] 5a. (done: 6a8e15f) **Build: cleanup and rules writers for the mail index.** `python tools/mail_index.py report` writes
  `domains/admin/cleanup-candidates.md` (from `cleanup`: sender, count, unread share, unsubscribe link present,
  suggested action; suggestions only) and a proposed rules block for `domains/admin/email-rules.md` (top senders by
  category) into `state/proposed-email-rules.md`, so the moment Michael's Takeout export lands it is one command.
  Offline tests with a synthetic mbox. Commit.
- [x] 5b. (done: 022148e) **Build: people prep in the morning brief.** For each calendar event today whose attendees or title match
  a `people/` file, add one prep line from the profile (last contact, open thread, one thing to ask about). Put the
  matching in a small tested helper (`tools/people_match.py`: event attendees and title words to profile files, by
  email first, then full name). Update the morning-brief skill text. Commit.
- [x] 5c. (done: 69e37df, live after the 01:31 restart) **Build: `status` in Slack.** When Michael DMs exactly "status", the bridge answers without running Claude:
  last run per job from `state/last-run.json`, pending approvals count, the latest line of `docs/overnight/LOG.md`
  if it is from today. Tests. Commit. (Bridge restart rule from item 5 applies; if past 06:30, leave for Michael.)
- [x] 6. (done: end of docs/04-PLAN.md) **Synthesis.** Read `docs/07-RESEARCH-OVERNIGHT.md`, `docs/04-PLAN.md` and the `CLAUDE.md` roster. Pick the
  10 best ideas, each with: what, why it fits Michael's goals, effort (S/M/L), and which agent it touches. Propose
  them as a new "Proposed 2026-11-08 (needs Michael's yes)" list at the end of `docs/04-PLAN.md`. Do not build them.
- [x] 7. (done: MORNING-SUMMARY.md) **Morning summary (last run, at or after 08:00).** Write `docs/overnight/MORNING-SUMMARY.md` for a phone:
  what got done (with commit hashes), what failed or was skipped, the top 5 ideas in one line each, and "Needs you"
  (what unblocks the next step). Under 40 lines, plain words, no em dashes.

If every item is ticked and there is time left: deepen item 1 on the two most promising threads, then stop.
