# Juno: where things stand

The one page to read first. Any Juno session updates it when something lands. The details live in `04-PLAN.md`
(phases and queue), `13-DESIGN-DECISIONS.md` (Slack screens), `14-STACK-SLACK.md` (stack) and
`private/15-RESEARCH-AGENT-PHONE.md` (Juno's own phone, kept on this PC only).

Last updated 2026-11-08.

## Where to talk to Claude about Juno

- **The "Juno" section in the Code sidebar.**
  - "Juno build" is the main session. Its folder is `personal-coordinator`.
  - "Original build (scheduling PR)" started the project. Its folder is `support-agent`, a different repo with its own
    PR (the scheduling engine proof of concept). It's kept for history.
- **Code backup.** Private GitHub repo `michaelmnorth/personal-coordinator`, branch `master`, first pushed
  2026-11-08.
  - The repo is the template. Personal files stay on this PC: real `me/` files, domain context, learnings, email
    rules, people, observed, state, logs, data, private and env files.
  - Blank `.example` templates stand in for them, and the history was scrubbed of them the same day.
  - The audit found no secrets anywhere in the history.
- **Rebuilding elsewhere** (the work computer): `16-REBUILD-PLAYBOOK.md`, step by step, with what changes for work.
- **New side jobs.** Start them from New in the `personal-coordinator` folder, and file them under Juno.
- **Status questions.** Any session can answer "where are we?" by reading this file.
- **Code changes.** Only one session at a time changes Juno's code.

## Plan in one line per phase

| Phase | What | Status |
|---|---|---|
| 0 Foundations | Folder, profile, 1Password, connectors | Done |
| 1 Slack | Juno in a Slack DM, cards with buttons, timers | Live. Screens 2 to 6 built. Home tab off (mobile). Photos readable |
| 2 Personal assistant | Inbox triage, drafts, calendar, reminders, reflection | Built and running in the sweep. Living with it |
| 3 Hardened runtime | Runs unattended, headless approvals, cost log | Mostly done: bridge on Task Scheduler, cost log, wake gate live 2026-11-08 |
| 4a Health | Hevy, Apple Health (sleep, weight, steps, macros), coach sheet | Started 2026-11-08: Hevy puller built, key requested |
| 4b Finance | Plaid, SimpleFIN, monthly report | Not started |
| 5 Always on | Runs while the PC sleeps (mini PC or VPS) | Not started |
| Juno as a person | Own phone number, WhatsApp, Gmail | Pixel 8 (refurbished) bought 2026-11-08, arrives 2026-11-09. Line: US Mobile texts only (about $6 a month), signed up on the Pixel 2026-11-09. Juno's Gmail and the scrcpy install can happen 2026-11-08, before the phone. Setup log in docs/15 |

## Decisions

- 2026-11-08: Paper dropped. The design phase is done, and Michael doesn't want to pay for another tool. The Slack
  screens in `13-DESIGN-DECISIONS.md` are the design of record. (Michael)

## Done 2026-11-08

- Google sign-in. The sweep now skips the AI run when nothing changed.
  - First read-only. Widened the same day (Michael: "full access") to gmail.modify (read, labels, drafts) and
    calendar.events.
  - Google has no drafts-only scope, so the grant could send. Sending and invites still need Michael's tap.
- The 1Password fill-in card: Juno asks for a login and never sees it. Tested end to end with Test-Juno.
- Read-write service account "Juno read-write", Agent-Secrets only. The bridge makes the empty items itself, and
  Google checks and sign-ins use it, so the desktop app no longer prompts for them.
- Phone research. Pick, re-checked live: a refurbished Pixel 8 from Best Buy ($218, updates to about 2030). Line changed later the same day to US Mobile texts only (see the phase table).

- Juno's own Gmail and Calendar scripts (`tools/gmail.py`, `tools/gcal.py`). Drafts and `Juno/` labels need no tap.
  Holds and events need an approval, proven by a one-time token the bridge gives only to the approved run. Sending
  still goes through the approved send of one exact draft. Calendar reads checked live; drafting covered by tests,
  first live draft pending.

- Juno points at the new scripts: `CLAUDE.md` (Gmail and Calendar, Asking for a login), the drafter and calendar
  agents, the sweep and the morning brief.
- Config edits: Code-tab sessions may now change `CLAUDE.md` and `.claude/` (Michael's hook edit). Juno's own Slack
  and timer runs still can't.

- First live test from Slack worked: a hold on his calendar and an email to himself, sent after his tap.
  Fixed from his feedback the same night:
  - Holds, and email only to his own address, now happen with no tap (`me/automation.yaml`: holds auto_notify,
    `email.send.self` auto). Anyone else still gets a card.
  - Replies are plain talk: no IDs, file or setting names. The card's Why line only shows Juno's own plain reason.
  - The "working" line is a random friendly one ("On it…", "Sure, one sec…") instead of "Juno is working on it".

- Personality pass, first round (Michael's picks): playful friend plus deadpan, Norm MacDonald style humor that
  ribs him a little; personality in every message; emoji in most; varied Slack reactions (seen, done, a reply to
  his message). Guide in `CLAUDE.md`, Your personality. Name stays Juno. Slack About page rewritten in her voice.
- Drafts carry his Gmail signature (HTML plus a plain-text copy).

## Done 2026-11-09

- Google Contacts connected (317), profiles that build themselves with a Save card, first-name matching.
- Sorter reads mail. `tools/inbox.py` sorts new mail in code (Gmail tabs, unsubscribe headers, receipts, his
  own labels and senders) and sends only people he knows, bills and account-security notices to Sorter, as
  cleaned text it alone reads. The 7:00 brief now reads overnight mail itself instead of "inbox not checked yet".

## Waiting on Michael

1. Revoke the old read-only "Juno" service account in 1Password (Developer, then Service accounts). "Juno read-write"
   replaced it on 2026-11-08.
2. Phone: Pixel 8 bought, arrives 2026-11-09. Get Juno's line: US Mobile custom, texts only (about $6 a month), picking a 404, 678 or 770 number. See docs/15, Setup log. Handled in the "Juno phone and Gmail
   setup" session.

## Next builds (in order)

1. Personality: live with round one for a few days, then tune from his reactions (`/lesson` for misses).
2. Phone setup: eSIM, WhatsApp on Juno's number, adb control from the PC.
3. Juno's own Gmail. Michael creates the account after the phone, since Google wants a number.
4. Health (Phase 4a).
5. Before 2026-12-15: a reminder for health insurance enrollment.
