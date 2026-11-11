# Juno: where things stand

The one page to read first. Any Juno session updates it when something lands. The plan of record is `docs/v2/`
(`08-ROADMAP.md` for phases and gates, `reports/P0.md` for the latest phase report, `BACKLOG.md` for parked ideas).
The v1 docs (`01` to `16`) are history.

Last updated 2026-11-10.

## Where things live

- **Code:** public GitHub repo `michaelmnorth/juno`, branch `main`. It holds no personal data; `tests/test_no_personal.py`
  fails if a name, address or private word from the local personal layer reaches a tracked file.
- **Personal layer:** on this PC only, git-ignored (`me/`, `people/`, `observed/`, `learnings/`, `state/`, `data/`,
  `logs/`, `domains/*/CONTEXT.md`, every `private/` folder). The encrypted backup (`tools/backup.py`) copies it off the
  box.
- **The Google sign-in home and privacy pages** are served by GitHub Pages from `docs/` (`index.html`, `privacy.html`).
- **Work twin:** Minerva, built on the work laptop from `docs/v2/MINERVA-START.md`. A separate instance with no link
  back to this one.
- **Code changes:** one session at a time. Build sessions read `docs/v2/BUILD-RULES.md` first.

## Running now (v1)

| Area | State |
|---|---|
| Slack | DMs, approval cards, timers, reactions, photos. Home tab off |
| Inbox | Sweep every 2 hours; code sorts most mail, Sorter the rest; reply drafts unasked; never sends without a tap |
| Calendar | Reads, free slots in code, holds with no tap; invites need a tap |
| Briefs | Morning brief and evening check-in; dated reminders and one-shot pings |
| People | Contacts connected; profiles build themselves through Save/Skip cards |
| Health | Hevy puller and the coach-sheet sync. Sleep, weight and macros not connected |
| Finance | No data connected |
| YouTube | Transcripts, search, daily watch digest |
| Learning | Silent notes in `observed/`, lessons in code from Slack, weekly reflection |
| Safety (P0) | Pause and resume, spend notices at $5 and $10 that never stop runs, per-DM cap, web tools for the researcher only, run lock, email sends bound to the stored draft, backup code, CI |

## The plan (v2)

There is no Dec 15 launch, so nothing waits on one (owner, 2026-11-10).

| When | Phase | Done when |
|---|---|---|
| By Nov 17 | **P0 close-out** | Ledger rerun at 50 DMs or 7 days; real backup restored; heartbeat monitor live |
| From Nov 18 | **P1 Context engine**: DMs on a lean, typed path | 7 days of real DMs at p50 ≤ $0.03, p95 ≤ $0.20; dialogue set ≥ 90% |
| After P1 | **Quick packs**: weekly goals pulse, wind-down nudge | Each in the brief or check-in, under a cent a day |
| Then | **P3 Always on** (dedicated host), with **P2 Memory** alongside | 14 days unattended with the PC off; recall ≥ 90% |
| Then | **P4 Learning loop**, **P5 Profiles and onboarding** | Scorecards with no manual step; empty folder to first brief in 60 minutes |
| After P3 | **P6 Second channel** | Approvals work end to end on it |
| Done elsewhere | **P7 Work twin** | Taken over by Minerva |

The freeze (`docs/v2/FREEZE.md`) holds new agents, skills and loops until P1 exits.

## Waiting on Michael

1. Fill the backup passphrase in 1Password; then the first real backup and a restore drill run.
2. Create the external heartbeat monitor and store its URL in 1Password.
3. Revoke the old read-only service account in 1Password, if still there.
4. Open decisions: an API key for the runtime with a $40 monthly alert (needed for P1); P3 host, home machine or
   cloud VM (default home).

## Parked (`docs/v2/BACKLOG.md`)

- Sleep, weight and macros for Rep; money data for Ledger.
- Hevy routine creation (gated).
- Holds dedupe.
- Juno's own phone and WhatsApp: paused until P6 (O3).
