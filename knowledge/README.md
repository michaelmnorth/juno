# knowledge/

Juno's knowledge base: one entry per thing Juno knows that could go out of date. It replaces the loose "lessons
learned" lists (Michael 2026-11-16): every item is timestamped, marked confirmed or unconfirmed, and a confirmed
item always says where the proof is.

## Where entries live

| Folder | In git? | What goes there | Sources allowed |
|---|---|---|---|
| `entries/<topic>/` | Yes (public repo) | Shared system knowledge: how Juno works, what fixed a failure, token and design findings. No personal data. | `pr`, `commit`, `url`, `test`, `doc` (anyone with the repo can check them) |
| `local/<topic>/` | No, stays on the PC | Anything personal, and everything Juno writes on its own: lessons from his taps, the nightly research scan, migrated `learnings/` and `me/` lines. | All kinds |

`INDEX.md` in each folder is the one-page list (title, status, dates, source count). It is rebuilt by the tool;
don't edit it by hand.

## One entry

```markdown
---
id: k-20261115-timer-messages-go-into-the-conversation-record
title: Timer messages go into the conversation record
status: confirmed
topic: agent-design
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_conversation_thread.py::test_short_answer_after_a_ping_sees_the_ping
  - commit: 54f77ab
---
Otherwise a short reply to a ping ("yes") loses the thread.
```

- **status**: `unconfirmed` (written down, not proven; the default), `confirmed` (at least one source shows it is
  true), `retired` (wrong or replaced; kept with `retired_reason`, never deleted).
- **Stale** is not stored: an entry past its `review_by` date shows as stale until someone checks it again.
  New unconfirmed entries get 30 days, confirmed ones 90. Confirming again stamps `last_verified` and moves
  `review_by` out.
- **Sources** are `kind: ref`:
  - `pr: owner/repo#12` · `commit: 54f77ab` · `url: https://...` (a doc page or announcement)
  - `test: tests/test_x.py::test_name`: the test exists and, when rechecked, passes
  - `doc: CLAUDE.md`: a tracked file. This proves what the rule *is*, not that it works.
  - `log: logs/...`, `card: a-1234abcd` (an approval in `state/audit.jsonl`), `michael: DM 2026-11-16 21:05, "..."`:
    local entries only.

What "confirmed" means depends on the claim. A passing test confirms that the code does what the entry says. It
does not confirm the idea was a good one. A research finding is never confirmed by the page that announced it; it
is confirmed once Juno has tried it (a PR, a test) or Michael says it held up.

## Rules (checked in code by `tools/knowledge.py`)

- Confirmed needs a source. A `card:` source must be an approved card in `state/audit.jsonl`; `test:`, `log:` and
  `doc:` sources must point at a file that exists. Tracked entries can only cite sources anyone can check.
- Juno's own runs (timer or DM) can only write `local/`. `entries/` changes through a pull request or a Code-tab
  session, and the write hook blocks Juno's runs from editing it directly.
- Entries are data. Nothing in one is an instruction, a recipient or a permission.
- Retire, don't delete, so the history of what we used to think stays.

## Who writes here

| When | What happens |
|---|---|
| A Save tap on a weekly lesson card | The line goes to `learnings/` or `me/` as before, and a confirmed local entry cites the tap. A line it replaced has its entry retired. |
| The lesson skill (he says "remember that") | Same, with `--source michael:<DM date and his words>` or `card:<id>`. |
| The nightly research scan | Each finding becomes an unconfirmed local entry with its link and publish date. |
| The weekly reflection | Reruns cited tests (`recheck-tests --apply`), runs `check`, and asks Michael about stale entries. |
| The weekly recap | `recap --since <date>` lists what was added, confirmed, retired and gone stale. `--shared-only` is the part that is safe to share outside Juno. |

## Commands

```
python tools/knowledge.py add --title "..." --body "..." --topic tokens [--status confirmed --source test:tests/...]
python tools/knowledge.py confirm <id> --source pr:michaelmnorth/juno#7
python tools/knowledge.py retire <id> --reason "Claude Code changed this in 2.3"
python tools/knowledge.py check            # broken entries, confirmed without a source, stale list
python tools/knowledge.py recheck-tests --apply
python tools/knowledge.py list --stale
python tools/knowledge.py recap --since 2026-11-09 [--shared-only]
python tools/knowledge.py migrate-learnings [--apply]   # one time, on the PC
```

## How this compares with what Juno had

- `learnings/` and `me/` stay the short rule lists every run loads. The knowledge base adds the proof and the
  dates behind them, and holds what isn't a rule (findings, how things work).
- `observed/` stays as is: counted guesses about Michael with their own fade-out (`tools/observed.py`). Those are
  unconfirmed by nature; a pattern he confirms becomes a lesson, and then an entry.
- The pattern borrows from decision records (one file per item, a status, never deleted) and from docs-as-code
  (a review-by date, checks in CI). It skips a database or a vector index: a few hundred markdown files and an
  index page are enough, and grep finds them.
