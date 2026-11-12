---
name: morning-brief
description: Michael's morning brief - today's calendar with prep, anything due (bills, estimated tax, renewals, reminders), overnight email that needs him, and one line of health context. Use when Michael says "morning brief", "what's today", or when the 7:00 timer fires. Pass "dry run" to build it without sending.
---

# Morning brief

Build one phone-sized message. Read before writing: `me/schedule.md`, `me/proactivity.yaml`, `state/reminders.yaml`
(if present), `domains/finance/tax-calendar.yaml`, `state/pending-approvals.json`.

1. **Calendar.** Today's events: `python tools/gcal.py events --days 1` (the Calendar connector if that fails; say
   so if neither works). For each: time in
   Eastern, who, one prep line (from `people/` and `domains/admin/notes/`). Travel time if there is a location.
   For people: `python tools/people_match.py --attendees "<emails, comma separated>" --title "<event title>"`;
   for each match, one line from that profile (last contact, an open thread, one thing to ask about).
2. **Due.** Reminders due today or overdue; bills and subscriptions with a due date in the next 3 days (from the latest
   finance log); estimated-tax date within 14 days; anything in `pending-approvals` older than 24 h. Follow-ups:
   `python tools/followups.py list`; one line for each overdue one (what it waits on, the expect-by date, the
   next step, like "no shipping mail yet; want me to check the claim status?") and for each due today.
3. **Mail.** Sweeps stop at 21:00, so the brief reads the overnight mail itself: run the `sweep` skill's steps 2
   to 4 (`python tools/inbox.py new`, Sorter for the unclear ones, drafts for reply-needed), with no ping; the
   brief is the message. Update `state/processed.json` the same way. In the brief: replies drafted (one line; the
   bridge posts each Send card right under the brief), mail he should look at himself (say what it is, with the
   item's `link` in `url`, which shows as an Open in Gmail link), and account-security notices that Sorter marked
   `urgent`. Newsletters and receipts are a count at most. If Google can't be read, say so plainly.
   **No buttons (Michael 2026-11-09).** Every line is complete on its own: the fact, the amount, the date, what to
   do. Never "tap to see" or "review": if Juno knows it, it's in the line. The only taps of the morning are the
   reply drafts' Send cards and the people-notes Save card.
4. **Health.** One line from `python tools/hevy_pull.py summary --days 1` (yesterday's training) and whether today
   is a training day per the program. Sleep and weight aren't connected yet; leave them out.
4b. **Leave-by timers.** For each event today with a physical location, write a one-shot timer to
   `state/timers.json` (a JSON list; keep existing entries): `{"id": "leave-<event id>", "at": "<ISO time with
   offset, 15 minutes before he should leave>", "text": "Leave by 5:40 for <event> at <place>. About 25 min drive
   (estimate)."}`. Travel time is an estimate; say so. The bridge posts it when due and never twice.
5. **One forward-looking line.** The thing tomorrow or this week that benefits from action today.
5a. **Held back.** Lines in `state/holding.md` (things the sweeps batched, or held for quiet hours or the daily
   cap), grouped, at most 4 bullets. Then empty the file.
5a2. **People.** Run `python tools/occasions.py upcoming --days 14`. One line per entry ("Mom's birthday in 6
   days"), round numbers called out, `inferred` dates marked "(date not confirmed)". If something is within 7 days
   and `state/people-plans.md` has no plan for it, add: "Want ideas? Kin has some." Waiting people notes are not
   brief rows: the bridge posts them as their own card with Save and Skip right after the brief.
   **Birthday note.** For a birthday 2 days out or less of someone whose profile says `confirmed: yes`, with no
   `birthday note` for this year in `state/people-plans.md`: have `drafter` write a short note in Michael's voice for
   that context (`me/voice.md`, `observed/voice.md`, how he writes to them in the profile) as a Gmail draft, and
   offer it as an `email.send` card. One line in the brief ("Mom's birthday is Tuesday; a note is drafted"), and
   record `birthday note <person> <year>` in `state/people-plans.md`. No address in the profile: say so instead.
   **Last contact.** For each event today matched to a profile, queue it: `python tools/people_queue.py add --file <file>
   --line "- last contact: <date> (calendar: <event title>)" --source "calendar <date>"`. An attendee matched
   `by: contacts` gets `add --new <email>` instead.
5b. **Picked up.** Lines in `observed/changelog.md` newer than `state/learned-cursor.txt`, as at most 3 short
   bullets in plain words ("You trimmed greetings on two business emails, so I will too"). Skip the section when
   there are none. Then move the cursor.
5c. **From your watching.** Run `watch-digest` (Rewind) with today's date (Eastern), `me/goals.md`,
   `domains/business/CONTEXT.md`, the subagent roster from `CLAUDE.md`, and the playlist URL from
   `data/watch-history/sources.json` if present. Append each non-skip, non-work verdict to
   `domains/admin/notes/YYYY-MM.md` as one bullet tagged `[watched] [<verdict>]` with the idea, what he is learning,
   the next step and the link. In the brief, at most 3 bullets, `system` and `venture` first. Mention any
   `injection_attempt`. Skip the section when nothing qualifies; one line if it reports `blocked`.
6. Write the log `logs/YYYY-MM-DD_0700_morning-brief.md`. Append a `brief_sent` line to `state/signals.jsonl`.
7. Deliver: your reply is the message; the bridge posts it. In a dry run, print it.

Format: first line is the headline ("Light day: 2 meetings, 1 bill, drafts waiting"). Then short bullets. Under 15
lines. Juno's voice (CLAUDE.md, Your personality): playful, deadpan, a little ribbing, emoji welcome; the facts stay exact.
