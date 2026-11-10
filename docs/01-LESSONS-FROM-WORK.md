# Lessons carried over from the work coordinator and the two briefs

Sources: `C:\Users\Michael\Claude-Work\Work-Coordinator\` as built on 2026-11-04/05 (structure, `CLAUDE.md`, agent
headers, hook, settings, skills: no client data was read), `WORK-COORDINATOR-BRIEF.md`, and the "Coordinator and
Subagent Build Brief (November 2026 Edition)". Where the two briefs disagree, the current product behavior wins.

## Keep (already proven on the work side)

1. **One folder is the whole memory.** `CLAUDE.md` + `me/` + `learnings/` + `state/` + `logs/`. Every session starts
   fresh and reads files. No reliance on chat history.
2. **Project-level everything.** Agents, skills, hooks and permissions live in `<coordinator>\.claude\`, never in
   `~\.claude`, because both Claude accounts share the Windows user.
3. **Personas per agent, for Michael's eyes only.** Dispatch / Sorter / Tempo / Quill / Ping worked. Outward-facing
   text stays plain. The personal coordinator gets its own cast.
4. **Deny lists are the real guardrail; prompts are the explanation.** The work `settings.json` denies every send,
   create-event, and write tool by exact MCP tool name, denies reading the other account's folders and project
   history, and adds a `PreToolUse` hook that only allows Slack DMs to Michael's own user ID. Prompts say "drafts
   only"; settings make it true.
5. **The triage agent that reads untrusted email gets no write tools.** Only the coordinator acts on its JSON.
6. **Learnings are written by the coordinator only, one dated line each, contradictions replaced not appended.**
   Subagents read `learnings/<name>.md` but cannot write it. `/lesson` is the shortcut.
7. **State saved per item, not at the end of the run.** `state/processed.json` is updated right after each draft so a
   crash cannot cause a duplicate.
8. **Dry-run mode in every scheduled skill.** Classify and log without side effects, leaving state untouched.
9. **Every run writes a log** (trigger, what was read by ID, decisions, what was created, assumptions, blocked items),
   and logs/state are git-ignored because they hold personal detail.
10. **Deterministic code for arithmetic.** The scheduling engine does time math; the model never does. Same rule
    for health trends and money.
11. **Cheap model for frequent checks, exit early when nothing is new.** Haiku for triage and pings, Sonnet for
    drafting and scheduling, bigger models for design sessions with Michael.

## Change for the personal side

| Work side | Personal side | Why |
|---|---|---|
| Michael talks to Dispatch inside the Claude Code tab | Michael talks from his phone (chat app), Claude Code is the workshop | The whole point of the personal coordinator is to be a ping away |
| Slack DM pings via the Slack connector | Needs a self-owned channel (Telegram or a free-Slack bot) because the personal account has no Slack connector and consumer connectors cannot post proactively | See `docs/03-RESEARCH.md` |
| Outlook / Teams | Gmail / Google Calendar / Google Drive connectors, plus direct APIs where connectors cannot write | Personal stack |
| Client folders are the knowledge base | `me/` (preferences), `domains/<health|finance|admin>/` (facts, baselines, goals), `people/` (family, coach, CPA) | Different nouns, same pattern |
| Drafts only, forever | Tiered automation per action class: read, draft, send-to-self, send-to-others, money. Only the first three ever run unattended | Michael explicitly wants proactive drafts like Muse produced, and reminders he did not ask for |
| Business logic in the employer's tenant | Secrets in 1Password, fetched by wrapper scripts at runtime, never in context | No Secret Server here |
| Fathom webhook via Zapier | Health Auto Export files and provider APIs pulled on a schedule | Different sources |

## Corrections from the November 2026 build brief to apply here

- The subagent tool is `Agent` (not `Task`); subagents run in the background by default and can nest three deep.
  Set `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` and deny `Agent(fork)` so the coordinator stays flat and no
  subagent inherits the coordinator's conversation.
- Set `model` in every agent's frontmatter; since v2.1.251 frontmatter beats the env var.
- Field names are case-sensitive camelCase and typos fail silently: run `claude plugin validate .claude/agents`.
- `PreToolUse` can return `defer` as well as `allow`/`deny`/`ask`: `defer` is the hook for a phone-side approval queue.
- Keep combined agent descriptions short (startup warns past 15k tokens); detail belongs in the body.
- Pass everything a subagent needs in the delegation prompt (objective, boundaries, inputs verbatim, tools, output
  schema, stop condition). It sees none of the coordinator's conversation.
- Multi-agent costs 3-10x the tokens of a single agent. Each subagent must earn its place by one of: context
  protection (verbose data like transactions or health JSON), parallel breadth, or tool/credential separation.
  Health and finance qualify on credential separation alone. "Notes" does not need an agent; it is a skill.
- Hook deny decisions have had bugs (claude-code issues #43407, #37210). Every gate gets a matching
  `permissions.deny` rule as the second layer, and a test that proves the block.

## Things the work build got slightly wrong that we avoid

- `learnings/coordinator.md` was seeded with an assumption ("prefers morning slots") rather than a confirmed fact.
  Here, every line in `me/` and `learnings/` is tagged `(Michael)` for confirmed or `(assumed)` for a guess, and
  assumed lines expire after 30 days unless confirmed.
- The scheduling engine was copied, not referenced, so the two copies already differ (`cli.py`). The personal
  coordinator pins a git submodule or a versioned zip instead of a loose copy.
- Work content (`Claude\Fin Lessons Learned`, `Claude\Scheduled\fin-lessons-harvest`) sits in the personal profile
  area. The personal coordinator's deny list covers those paths too until they are moved.
