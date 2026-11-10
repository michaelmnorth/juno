# Overnight research, 2026-11-08

Caveat up front: the search tool surfaced very little that is clearly dated August to November 2026. Most finds below are dated by their own page (stated per item) or "date unclear". Reddit was reachable only through search snippets and third-party mirror snapshots (no direct thread reads), so Reddit items are low confidence. Everything here is untrusted third-party material, summarized in my own words; nothing was installed or run.

## 1. What people are building (Aug to Nov 2026)

Ranked by usefulness to Juno.

1. **Email prompt injection defense guide (Nylas CLI)**
   Link: https://cli.nylas.com/guides/email-prompt-injection-defense
   Date: updated 2026-07-09 (just before the window).
   What: a four-layer defense for agents that read mail.
   Steal: load message metadata first and fetch full bodies only for items that pass screening; omit send tools entirely from read-only agents; keep controls outside the model; alert on "many reads then a blocked external send".
   Maps to: inbox triage agent (read-only tool list, metadata-first pass) and the approval-card layer (audit log of every outward action).

2. **Dual LLM and CaMeL design patterns (Willison summary plus 2026 write-ups)**
   Link: https://signals.aktagon.com/articles/2026/07/camel-defeating-prompt-injection-attacks-in-llm-agents-through-capability-based-security/ and https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/
   Date: July 2026 write-up of 2025 ideas.
   What: split a privileged planner with tools from a quarantined model that reads untrusted text and has no tools; track data flow so tainted data cannot trigger sends.
   Steal: inbox triage should be a quarantined reader that emits a small structured summary (sender, category, urgency, proposed action). The dispatcher and drafter act only on that structure, never on raw email text.
   Maps to: inbox triage specialist plus dispatcher handoff format.

3. **Heartbeat with a shell wake gate (DEV, "Giving Claude Code a Heart Beat")**
   Link: https://dev.to/simplemindedrobot/giving-claude-code-a-heart-beat-55ja
   Date: April (year not shown), so likely April 2026.
   What: a 5-minute cron runs a shell script of cheap predicates; the model wakes only if one fires, and a small model triages before escalating to a big one. A git-versioned HEARTBEAT.md is the queue and audit log.
   Steal: the model is the wrong tool for deciding whether to wake. Add a pre-check script to inbox sweeps (new mail count, calendar change, due birthdays) so `claude -p` runs only when there is something to do. Also send a periodic "alive" ping, since silent failure kills trust.
   Maps to: routines (inbox sweeps, evening check-in) plus a new `gate.ps1` helper.

4. **Claude Reflect (BayramAnnakov), learning from corrections**
   Link: https://github.com/BayramAnnakov/claude-reflect
   Date: date unclear (requires Claude Code 2.1.286 or newer, so recent).
   What: hooks detect correction phrases and explicit "remember:" markers, queue them with a confidence score (0.60 to 0.95) and decay, then a review step promotes approved items to rules files.
   Steal: two-stage learning. Silent capture into the observed/ layer with a confidence score and decay, promotion to durable rules only after review, reported in the next brief. Matches Juno's silent-learning rule.
   Maps to: observed/ layer and the drafter (voice corrections); promotion step surfaced in the morning brief.

5. **Anthropic Managed Agents engineering post**
   Link: https://www.anthropic.com/engineering/managed-agents
   Date: 2026-04-08.
   What: the session is an append-only event log stored outside the context window; the "brain" is separated from disposable "hands"; credentials stay out of the sandbox and tool calls go through a vault proxy.
   Steal: keep an append-only daily log that any fresh `claude -p` run can reread in slices, instead of dragging history through context. Keep tokens out of anything the model can read or echo.
   Maps to: dispatcher memory layer (daily event log file) and Slack/Gmail credential handling.

6. **OpenPaw (Show HN, flat-file memory)**
   Link: https://news.ycombinator.com/item?id=47220057
   Date: about eight months before the snapshot, date unclear (likely early 2026).
   What: a toolkit that generates config Claude Code already reads (CLAUDE.md, permissions, hooks) and then exits; memory is plain MEMORY.md and SOUL.md. Commenters debated flat files versus vector search; the author defended readable, editable files.
   Steal: no daemon, no vector DB; a human-readable SOUL-style identity file separate from facts. Validates Juno's current approach.
   Maps to: memory layers (identity file vs facts file); skip the toolkit itself because Juno already has its own structure.

7. **claude-world/claude-agent**
   Link: https://github.com/claude-world/claude-agent
   Date: date unclear (a search snippet said about 17 days old, unverified).
   What: persistent Claude Code assistant with a background Haiku pass every 5 turns that extracts memories into four types (user, feedback, project, reference), periodic consolidation, and a 9-section handoff summary at 50 turns.
   Steal: typed memories (feedback vs reference) and a cheap-model consolidation job; a fixed-section handoff summary when a session rolls over. No approval step is documented, so do not copy its safety posture.
   Maps to: evening check-in (memory consolidation pass) and dispatcher session handoff template.

8. **LettaBot (archived 2026-05-26)**
   Link: https://github.com/letta-ai/lettabot
   Date: archived May 2026; useful as a design reference.
   What: one agent and one shared memory across Telegram, Slack, Discord, WhatsApp, Signal. Heartbeats always run in "silent mode": the agent's text goes nowhere unless it explicitly calls a message command. Read-only tools by default; unknown users need a pairing code.
   Steal: silent-by-default proactive runs where speaking is an explicit tool call, which prevents chatter. Pairing-code allowlist for any new front end.
   Maps to: all timed routines (quiet unless something clears the bar) and the Slack front end (allowlist only Michael's user ID).

9. **Personal CRM agent tutorial (DEV, itsjoaki)**
   Link: https://dev.to/itsjoaki/how-to-build-a-personal-crm-with-an-ai-agent-never-forget-a-follow-up-again-2iim
   Date: posted April 28, edited July 7 (year not shown).
   What: agent builds a relationship map from Gmail, scores contacts by recency and importance, flags cold relationships, and sends birthday reminders two days ahead with a drafted message.
   Steal: "cold relationship" weekly list, birthday nudge at T-2 days with a ready draft. Pull birthdays from signatures and conversation context, but confirm before storing.
   Maps to: Kin (birthdays, cold-contact list), drafter (birthday message in Michael's voice), routine in the weekly brief.

10. **claude-chief-of-staff (mimurchison)**
    Link: https://github.com/mimurchison/claude-chief-of-staff
    Date: date unclear (small repo, 4 commits).
    What: CLAUDE.md as the operating file, goals.yaml as priority source of truth, contact files enriched over time, slash commands for morning brief, tiered triage with draft replies, and an enrich command.
    Steal: a single goals file that triage tiers are scored against; a contact "enrich" command run on demand rather than automatically. No safety rules documented.
    Maps to: inbox triage (priority tiers from a goals file) and Kin (on-demand enrichment).

11. **Kirie (Claude Agent SDK assistant)**
    Link: https://github.com/khaterdev/kirie
    Date: date unclear.
    What: three memory layers (always-loaded key facts, searchable store, permanent chat archive); SQLite-backed background task queue with cost tracking and a turn cap per task.
    Steal: a per-task cost and turn cap logged for every routine run, so a runaway timer job is visible in the morning brief.
    Maps to: dispatcher run wrapper and the brief's "cost and health" line.

12. **Approval gates as a hard rule (r/AI_Agents threads, via mirror snapshots)**
    Link: https://reddit.sentinel-team.org/ (mirror of r/AI_Agents, thread ids vary; direct Reddit not read)
    Date: snapshots Feb to May 2026, so before the window; low confidence.
    What: posters converge on "observe, summarize, recommend, prepare freely; anything irreversible needs explicit approval", approval treated as a checked state change, and logging to a database before acting.
    Steal: make the approval card a recorded state that the send step verifies, not just a message the model reads. Log intent before the action.
    Maps to: approval-card layer (card id plus status file checked by the sending script).

13. **Telegram bridge with per-chat sessions (AgentField)**
    Link: https://agentfield.ai/blog/build-your-own-personal-assistant
    Date: 2026-07-02.
    What: a thin ~70-line bridge using long-polling, one session id per chat, last 12 messages kept in session memory in SQLite, advance the update offset after each message.
    Steal: long-polling needs no public URL; advance the offset after processing so a crash does not replay messages; a rolling window plus durable store.
    Maps to: Slack front end (use Socket Mode or polling, ack after handling, dedupe by message timestamp).

14. **Claude Code release notes: background subagents, plugin eval, agent teams**
    Link: https://code.claude.com/docs/en/changelog
    Date: third-party archive lists v2.1.198 (2026-07-01, subagents background by default) and v2.1.269 (2026-09-11, `claude plugin eval`); verify on the official page.
    What: platform changes that affect orchestration (background subagents, implicit teams under an experimental flag, skills reloaded after compaction, plugin validation).
    Steal: re-test specialist handoffs now that subagents may run in the background by default; use plugin eval to score skills like the drafter's voice.
    Maps to: dispatcher (confirm it waits for specialist results) and skill testing for drafter and Reel.

15. **Claude for Slack (Anthropic) and a DIY Telegram counterpart**
    Link: https://dev.to/lamingsrb/anthropic-shipped-claude-for-slack-my-team-runs-on-341h
    Date: 2026-07-09.
    What: Slack tagging works asynchronously from thread context; the author runs a cheap DIY version with debouncing, a daily mention cap and silent failure.
    Steal: debounce rapid messages into one task, cap daily triggers, and still surface errors somewhere (silent failure on the user side is fine only if the brief reports it).
    Maps to: Slack front end rate limits; skip Anthropic's own Slack app because it is team-oriented and Juno needs local file access.

16. **Subagent field notes from r/ClaudeCode (mirror snapshots)**
    Link: https://reddit.sentinel-team.org/posts/1r6cn6t/snapshots/2026-02-17T01%3A15%3A03.108844Z
    Date: Feb to Mar 2026, before the window; low confidence.
    What: complaints that subagents cannot nest so every result passes through the orchestrator, advice to run each phase in a clean session, short commands with depth in skills, and minimal-instruction agents beating persona-heavy ones.
    Steal: have specialists return compact structured results (not transcripts) and write long output to files the dispatcher only references. Keep agent prompts plain.
    Maps to: dispatcher context hygiene; trim specialist prompts.

17. **didntwatch (YouTube transcript skill)**
    Link: https://github.com/ewro/didntwatch
    Date: date unclear.
    What: Claude Code skill whose script only fetches subtitles (prefers author-uploaded over auto captions, caches locally, has a throttled batch mode) while Claude does the summarizing. Notes YouTube's tightening against scraping.
    Steal: separate "fetch and cache" from "think"; cache transcripts so follow-up questions are free; batch with throttling.
    Maps to: Reel (transcript cache) and Rewind (daily batch of watch-history videos). Note: none of the YouTube skills found cover watch history itself; Takeout export or the Data API would be the likely route (unverified).

18. **Splitting agents to contain prompt injection (C1)**
    Link: https://www.c1.ai/engineering/splitting-ai-agents-to-contain-prompt-injection
    Date: 2025-06-05 (outside window, but concrete).
    What: privileged agents act but never see raw user input; quarantined agents summarize untrusted content with no action tools; inputs labeled high or low trust; all actions logged.
    Steal: a trust label on every item in the brief (Michael-typed, known contact, unknown sender) that controls what the dispatcher may do with it.
    Maps to: inbox triage output schema and the dispatcher routing rules.

19. **Generic email-injection hardening list (tianpan.co)**
    Link: https://tianpan.co/blog/2026-04-18-prompt-injection-agentic-pipelines-defense
    Date: 2026-04-18.
    What: strip hidden HTML and CSS-hidden text, wrap bodies in data delimiters, pattern filters as a cheap first layer only, check tool-call intent against the task, taint tracking, send allowlists, append-only audit logs.
    Steal: strip hidden content before the model sees it; block any send or link-open whose trigger came from email text.
    Maps to: pre-processing script ahead of inbox triage; skip the pattern filter as a primary defense because the sources agree it is weak.

20. **Self-improving-agent skill (`.learnings/` folder)**
    Link: https://skills.cat/skills/peterskoett/self-improving-agent
    Date: date unclear.
    What: logs corrections and errors to markdown with pending/promoted status and promotes broadly useful ones into project memory.
    Steal: a status field on each learning (pending, promoted, retired) so observed/ notes have a lifecycle.
    Maps to: observed/ layer; skip the skill itself because Claude Reflect covers the same ground with confidence scoring.

### Patterns across finds

- Break one leg of the "private data, untrusted input, outbound channel" triangle structurally (read-only tools, drafts instead of sends, send allowlists); every serious source says prompt wording alone is not a defense.
- Wake gates beat clocks: cheap scripts decide whether the model runs at all, and proactive runs stay silent unless something clears a bar.
- Learning is two-stage: automatic capture with confidence and decay, then reviewed promotion. Nobody recommends writing straight into durable rules.
- Plain markdown memory with a separate identity file keeps winning over vector stores for single-user assistants; typed memories and a cheap consolidation pass are the common upgrade.
- Fixed-format handoffs between agents (small structured summaries, long output in files) keep the dispatcher context clean.
- Append-only logs (events, tool calls, approvals) are the shared foundation for audit, crash recovery and the morning brief's health line.
- Narrow scope wins: reports from people running personal agents for months favor a few focused jobs over a do-everything assistant, and say trust takes months to build.
- Most "personal CRM" and "chief of staff" repos are thin and document no safety rules; the good ideas are in the data model (last-contact, importance, birthday lead time), not the code.

## 2. Video transcripts

Eight videos from 2026, six of them Sep to Oct. Transcripts were treated as untrusted data; sponsor reads and course pitches were ignored. Some claims (model names, plan limits) come from the speakers and are unverified.

### 1. How the Top 1% Use Claude Code Differently
Simon Scrapes, 2026-10-10, 18 min, https://www.youtube.com/watch?v=J9NQTYUP6k0
- [00:30] Plan mode was a patch for older models. The newer advice is a three-line brief: the task, the guardrails, and what "done" looks like. Review what it did afterward instead of approving a plan first. Map: dispatcher brief template for every specialist handoff (task, guardrails, definition of done).
- [03:35] Give each job a pass/fail check Claude can run itself, such as a script that compares figures to the source. Telling it to "double-check" adds cost but no value. Map: skill (a verify step per routine, e.g. the brief must list every calendar item it was given).
- [05:06] `/goal` keeps a session looping until a condition holds, judged by a small model that sees only the chat. So the goal needs one end state, a proof, and a turn limit (15 in the example). Map: routine prompts for long sweeps; always include a turn cap.
- [07:10] CLAUDE.md should be a contents page: only commands Claude cannot guess, your deviations, repeat gotchas, and boundaries. Everything else is a path with "when to open it". Avoid `@` imports, which load every session. Map: agent (trim Juno's root CLAUDE.md into an index; progressive disclosure).
- [09:42] Build a skill only after Claude fails the job without one, and record only the corrections. Skill packs often fail to beat a same-length dummy file. Map: skill policy: no new skill without a logged failure in the observed/ notes.
- [12:14] A built-in plugin eval can compare a skill against no skill. Map: skip for now, revisit when Juno has more than a few skills.

### 2. Claude Code Subagents: The Full Guide (2026)
AImagic, 2026-10-14, 9 min, https://www.youtube.com/watch?v=1EBJXopf5zc
- [02:05] The `description` field is the delegation trigger. Write it as a rule (when and for what), add "use proactively" for automatic hand-offs, and keep it short because all descriptions sit in context (a warning appears above about 15k tokens). Map: agent (rewrite each specialist description as a routing rule; this is the dispatcher's routing table).
- [02:36] Per-agent controls: tool allowlist, model, permission mode, max turns, effort. Example: a read-only reviewer on Sonnet with a 20-turn cap. Map: agent (inbox-triage gets read and label tools only; no send tool).
- [03:39] Subagents can preload named skills and can skip project memory files. Map: agent (finance and health specialists load only their own skill).
- [05:15] A subagent can carry its own pre-tool hook that blocks disallowed commands with exit code 2. Map: hook (hard-block Slack posts or sends outside an approved channel, enforced per specialist).
- [07:51] The pattern: noisy work runs elsewhere and only a summary returns. Cheap routine jobs go on Haiku with low effort; background runs keep the main chat free. Map: routine (inbox sweep on a cheap model returning a short digest).
- [06:17] Agent teams cost roughly seven times the tokens and are experimental. Map: skip.

### 3. Context Engineering for AI Agents: 4 Failure Modes to Avoid
IBM Technology, 2026-10-15, 10 min, https://www.youtube.com/watch?v=BwXremQ-i6I
- [04:31] Poisoning: an agent's own wrong note gets treated as fact. Fix by validating before writing. Map: learning notes (observed/ entries need a source line and a confidence flag; verify before promoting).
- [05:12] Distraction: a long history of past actions pulls the agent to repeat itself. Fix by compacting and moving detail into files read on demand. Map: routine (each scheduled run starts fresh from files, not a long thread).
- [06:16] Confusion: too many tools degrade choices (one benchmark failed at 46 tools, passed at 19). Map: agent (give each specialist only its handful of tools).
- [06:47] Clash: old and new facts both sit in the window. Fix by pruning superseded notes. Map: skill (a weekly memory-tidy pass that deletes or merges contradicted notes).
- [00:33] Larger windows still get less reliable, so lean context beats big context. Map: principle for the dispatcher design.

### 4. How AI Agents Manage Their Memory: Context Engineering Explained
Ysology, 2026-09-30, 12 min, https://www.youtube.com/watch?v=Yt8eH-hsRQc
- [03:06] Four operations: write, select, compress, isolate. Useful as a checklist for Juno's whole memory design. Map: design review of the memory layer.
- [03:38] Write: keep a per-task scratchpad separate from long-term memory that persists across sessions. Map: agent (run-scoped scratch file vs the durable observed/ layer).
- [05:10] Select: keep lightweight references and fetch just in time, rather than preloading. Map: routine (briefs read only today's relevant files).
- [07:14] Compress by summarizing outcomes ("migration done, tests pass") or trimming stale tool output. Map: skill (end-of-day summarizer that writes one short state note).
- [08:46] Isolate: split research across subagents with separate contexts and return only conclusions. Map: agent (research specialist returns a half page, never raw pages).

### 5. Build a proactive agent workflow with Claude Code
Claude (Anthropic workshop), 2026-05-20, 22 min, https://www.youtube.com/watch?v=eSP7PLTXNy8
- [03:27] Running proactive agents yourself means building hosting, triggers, and visibility. Routines remove that by running sessions on managed infrastructure. Map: routine (decide per job: local scheduled task vs cloud routine, based on whether the PC is on).
- [08:40] Three decisions per routine: trigger, context, and how you steer it. Context is the ceiling on success. Map: routine template with those three fields filled in.
- [09:41] Triggers can be time-based, GitHub events, or a webhook POST carrying a payload. Map: routine (future: webhook-triggered Slack "capture" intake).
- [11:47] Generator and critic: one routine produces, a second reviews before a human sees it. Map: agent (a reviewer pass on outbound drafts before they reach Michael).
- [12:49] Every routine run is a normal session you can open, steer, and resume. Map: routine (store the session link in the brief so Michael can follow up).
- [19:29] Prompts must work with no one to ask, so connectors and permissions are set up beforehand. Map: routine checklist.

### 6. Claude Routines: The Hidden Costs Nobody Talks About
Better Stack, 2026-04-17, 10 min, https://www.youtube.com/watch?v=yVnsU-xqng4
- [00:31] Three levels of repeat: in-session loops, schedules (local or remote), and routines (adds GitHub and API triggers). Map: routine (pick the lightest level for each job).
- [04:40] Routines count against subscription usage plus a daily run cap (five on Pro per the speaker; test runs did not count). Check Michael's tier before planning many. Map: routine (budget the daily briefs and sweeps against the cap).
- [02:34] Cloud runs block bash network access by default; web fetch works, or add allowed domains in a custom environment. Map: routine (research jobs use web fetch).
- [06:46] Cloud sessions lack local skills, settings and hooks. They must live in a repo the routine clones. Map: skill (any skill used by a cloud routine must be committed to a repo).
- [02:34] Edit the auto-generated routine: remove unneeded repos, and fix formatting that Slack rejects. Map: routine (review generated config once).

### 7. I Made Claude My Personal Assistant (Full Build)
Systems Made Better, 2026-09-25, 29 min, https://www.youtube.com/watch?v=3ZT0upsICHk
- [15:43] The scheduled task is only a pointer: "read the run book in the folder". Instructions, memory, templates and boundaries live in files, so the setup is portable. Map: routine (thin prompts that read Juno's files).
- [13:05] Email briefing split into "for me specifically" and "unread but may matter", excluding known noise. Map: skill (inbox sweep with an explicit ignore list).
- [13:38] An approval loop: the brief lists tasks the AI could do, Michael tags which to approve, and a separate task executes only approved items. Map: routine (brief proposes, a second weekday run executes approved items only).
- [19:53] Replies to the brief are logged into a dated "captain's log" folder, which also updates the task list. Map: learning notes (daily log feeding observed/).
- [18:20] Iterate on the brief's tone and structure; start with a short reasoned focus paragraph and label where each waiting item came from. Map: skill (brief format).
- [14:41] Running commentary logs give ongoing memory with no special tooling. Map: agent (log-keeper).

### 8. How I Turned Claude Into My Personal Assistant (for 2027)
Albert Olgaard, 2026-10-17, 12 min, https://www.youtube.com/watch?v=g3e0m8nrQa4
- [01:32] Local sessions stop when the laptop closes; cloud sessions keep running. Pick the environment up front. Map: routine (default to cloud for brief and sweep if the data can be reached from there).
- [05:39] Routines turn Claude from a chat tool into a proactive one: a morning, noon and end-of-day email routine is the example. Map: routine (three daily touchpoints).
- [06:40] Create routines by describing them to Claude and explicitly saying "in the cloud", then ask for a test run and iterate. Map: routine (author-then-test workflow).
- [09:15] The mobile app can start sessions and create routines on the go. Map: skill (Slack and phone capture as the main intake).
- [10:18] Warning against chasing every new agent tool; stay with a few. Map: skip, but supports keeping Juno small.

### Patterns across videos
- Thin triggers, fat files: the schedule or routine prompt only says "read the run book"; behavior, memory and boundaries live in version-controlled files (videos 1, 5, 7).
- Less in context is better: index-style CLAUDE.md, just-in-time file reads, few tools per agent, prune stale notes, and a fresh start per run (videos 1, 3, 4).
- Subagent descriptions are the routing table, and permissions are enforced by allowlists, models and hooks per specialist, not by prompt wording (video 2).
- Proactive work needs an approval loop and a verifier: propose, let Michael approve by tag or reply, execute only approved items, and give every job a pass/fail check with a turn limit (videos 1, 5, 7).
- Agent-written notes are the main memory risk. Require a source, validate before saving, and prune on conflict (videos 3, 4).
- Know the platform limits before designing the schedule: daily routine caps, cloud runs missing local skills and hooks, and blocked network access (videos 5, 6, 8).
