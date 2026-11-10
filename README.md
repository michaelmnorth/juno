# Personal coordinator (Juno)

Michael's personal coordinator: one agent he talks to from his phone, with narrowly scoped subagents for inbox and
calendar, health, finance, research and reminders. Built in the pattern of the work coordinator, with stricter gates
because it will act on its own.

Start here:
1. `docs/04-PLAN.md`: phases, tasks, done-when. Phase 0 is this week.
2. `docs/02-ARCHITECTURE.md`: shape, roster, automation tiers, memory, personality, what will not work.
3. `docs/03-RESEARCH.md`: what was verified against current docs (channels, Slack vs Telegram, Plaid, Hevy, Withings,
   Apple Health, 1Password, model pricing) and what it changed.
4. `docs/05-OPEN-QUESTIONS.md`: 28 questions, the blocking ones marked.
5. `docs/01-LESSONS-FROM-WORK.md`: what carried over from the work coordinator. (The machine inventory is in `docs/private/`, kept on this PC.)

Run the gate tests before trusting anything:

```
python -m pytest tests/ -q
```

Layout, roles and rules live in `CLAUDE.md`. Nothing here holds a secret; secrets live in 1Password and are fetched
by scripts in `tools/`.

**This repo is public, so nothing personal is in it.** Who Michael is, the people in his life, health, money, notes
and run history live in git-ignored folders (`me/`, `people/`, `observed/`, `learnings/`, `state/`, `data/`,
`domains/*/CONTEXT.md`, `**/private/`) on his PC, and in the encrypted nightly backup (`tools/backup.py`). The repo
keeps blank `*.example.*` templates instead. `tests/test_no_personal.py` fails if a name from a local profile, his
address or a word in `me/owner.json` `private_words` lands in a tracked file. To build your own from this, start
with `docs/16-REBUILD-PLAYBOOK.md` and `docs/v2/00-START-HERE.md`.
