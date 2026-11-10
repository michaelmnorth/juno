---
name: evening-checkin
description: Evening check-in - tomorrow's prep, anything Michael left unanswered today, the day's batched low-priority mail (newsletters, receipts), and a one-question nudge (training done? note for tomorrow?). Use when the 20:30 timer fires or Michael says "evening check-in" or "wrap up the day".
---

# Evening check-in

1. **Tomorrow.** Events with prep lines; the first event's start time; anything that needs preparation tonight
   (documents, travel, a draft to finish).
2. **Open loops.** Approvals still pending, drafts not sent (Gmail drafts created by Quill still in Drafts), reminders
   due tomorrow morning.
3. **Batched mail.** Counts and one-line gists for today's `newsletter`, `receipt`, `subscription` items from the
   sweep logs. Never ping about these individually.
4. **Health nudge (Phase 4a+).** If the program had a session today and Hevy shows none, ask in one line. If a weigh-in
   is missing, mention it once a week at most.
4a. **Tidy the notes (silent).** `python tools/observed.py retire --apply`, then `python tools/observed.py check`.
   Merge each `duplicates` pair into one line (add the counts, keep the newer date), rewrite `unparsed` lines in
   the standard format, and if a file shows `over_warn`, merge or drop its oldest low-confidence lines. One
   changelog line per change. Nothing to do: skip it without a word.
5. **One question, optional.** "Anything for tomorrow?" only if nothing else needs an answer; never two questions.
5a. **Held back.** Lines in `state/holding.md` (things the sweeps batched, or held for quiet hours or the daily
   cap), grouped, at most 4 bullets. Then empty the file.
5b. **Picked up.** Lines in `observed/changelog.md` newer than `state/learned-cursor.txt`, as at most 3 short
   bullets in plain words ("You trimmed greetings on two business emails, so I will too"). Skip the section when
   there are none. Then move the cursor.
6. Log to `logs/YYYY-MM-DD_2030_evening-checkin.md`; append `checkin_sent` to `state/signals.jsonl`.
7. Deliver: your reply is the message; the bridge posts it. Respect quiet hours in `me/proactivity.yaml`; if the check-in itself is
   inside quiet hours, Michael set it that way, so send.

Under 12 lines.
