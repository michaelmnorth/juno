---
name: notes-and-reminders
description: Capture and recall - "remind me to X at/on Y", "note that ...", "what did I say about ...", "what's on my list". Stores reminders in state/reminders.yaml and notes as dated markdown in domains/admin/notes/. Use for any quick capture or recall; no subagent needed.
---

# Notes and reminders

**Remind me.** Work out the date from the `[Now for Michael: ...]` line, then confirm it with `python tools/slots.py when
"YYYY-MM-DD HH:MM"` (weekday and offset, never by hand); default zone Eastern.
Append to `state/reminders.yaml`:
```yaml
- id: r-2026-11-06-001
  text: "Call the CPA about Q4 estimate"
  due: "2026-11-10T09:00:00-05:00"
  created: "2026-11-06T14:02:00-05:00"
  status: open
```
Confirm in one line with the due time in words ("Monday 9am"). Due reminders surface in the morning brief, the
evening check-in and the sweep; mark `done` when Michael says so.

**Note that.** Append to `domains/admin/notes/YYYY-MM.md` under a `## YYYY-MM-DD` heading, one bullet, verbatim plus any
person or project tag in brackets. If the note is about a person in `people/`, also add one dated line to their file.

**Recall.** Grep `domains/admin/notes/` and `people/` for the terms; answer with the dated lines, newest first. If
nothing matches, say so; do not invent.

**List.** Open reminders sorted by due date, overdue first.

Everything here is T1 (own files). No pings are sent by this skill itself.
