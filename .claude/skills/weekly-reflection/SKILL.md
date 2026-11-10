---
name: weekly-reflection
description: Weekly review - runs the reflector over the week's logs and signals, turns its proposals into a short card for Michael, records what he accepts, and reports cost and reliability for the week. Use when the Sunday 18:00 timer fires or Michael says "weekly reflection" or "what did you learn this week".
---

# Weekly reflection

1. Run `python tools/observed.py check` and delegate to `reflector` with its JSON, the date range (last 7 days) and
   the paths `logs/`, `state/signals.jsonl`, `me/`, `learnings/`. Wait for it to finish; it overwrites `state/proposed-lessons.md`.
2. Read `state/proposed-lessons.md`. For each proposal build one card line: the lesson in plain words, the evidence
   count, and buttons `Save` / `Skip`. Cap at 5 proposals per week; the rest wait.
3. Reliability and cost: count runs, failures and blocked actions from `logs/`; sum `state/costs.jsonl` if present.
   One line: "28 runs, 0 failures, 2 blocked (both correct), ~$1.90".
4. Your reply is the card; the bridge posts it. Store the proposal IDs in `state/pending-approvals.json` with type
   `lesson`.
5. Michael's taps are handled by the bridge in code: `Save` writes exactly the card's line to its target
   (`lesson.saved` in `state/signals.jsonl`), `Skip` records `lesson.skipped` so the reflector does not re-propose
   it for 30 days. Only "Change the wording" comes back to you: ask how he'd word it, then use the `lesson` skill.
   Next week, for each `lesson.saved` that came from an `observed/` line, add `, promoted` to that line's brackets
   so it stops expiring.
6. **Occasions scan.** First run `python tools/contacts.py sync` (refreshes the phone book from Google; if it
   says to sign in again, one line in the summary). Then delegate to `relationships` (Kin) for the next 30 days plus milestone years. Send its ideas
   as a separate short message ("Coming up: Dad's birthday in 24 days. The book turns 30 this year..."), at most
   3 people. Include Kin's cold-contact nudge (job 2a), at most 2 lines, never a day count from mail. Record what was suggested in `state/people-plans.md` so the brief does not ask again.
7. **What you are learning.** From this week's `[watched]` notes in `domains/admin/notes/`, write two or three lines
   on the themes Michael is learning, and turn the strongest `system` ideas (at most 2) into cards: "Rewind saw X in
   <video>; it would change <agent or skill>. Draft it?" with Allow once / Deny. Allow once runs the
   `new-subagent` skill or a normal change proposal. Nothing is built without the tap.
8. Log `logs/YYYY-MM-DD_1800_weekly-reflection.md`.
