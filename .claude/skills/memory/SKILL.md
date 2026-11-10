---
name: memory
description: Show or delete what Juno remembers. Use when Michael asks "what do you remember about X", "what do you know about me", "what have you picked up", "forget X", "stop remembering X", or "delete that".
---

# Memory: show and forget

Juno's memory is files, so showing it is reading them and forgetting is deleting lines. Nothing is hidden elsewhere.

**Where it lives**
- Confirmed with Michael: `me/*.md` and `me/*.yaml`, `people/*.md`, `learnings/*.md`, `domains/*/CONTEXT.md`.
- Picked up silently: `observed/voice.md`, `observed/preferences.md`, `observed/procedures.md`, `observed/people.md`,
  with every change in `observed/changelog.md`.
- Not memory, but records: `logs/`, `state/` (approvals, pings, drafts), `data/` (YouTube cache, finance ledger).

## Show ("what do you remember about watches")
1. Search all memory files above for the topic (Grep, case-insensitive, including obvious synonyms).
2. Reply grouped by layer: "Confirmed" and "Picked up", each line in plain words with its date and how often it was
   seen. Mention the file names in one line at the end so he can open them.
3. "What do you know about me" with no topic: the 10 most useful lines across both layers, newest first.
4. "What have you picked up lately": the `observed/changelog.md` lines from the last 7 days.

## Forget ("forget that I like watches")
1. Find every matching line in `observed/` and in the confirmed files. Also matching cached data if he asks (for
   example a YouTube transcript in `data/youtube/`).
2. Delete them for real: remove the lines, do not mark them. For confirmed files this is a DM with Michael present,
   so it is allowed; an unattended run never deletes from confirmed files.
3. Add one `observed/changelog.md` line: `removed | <what> | Michael asked`. Do not record the deleted content itself.
4. Confirm with exactly what was removed and from where, as a short list. If nothing matched, say so and show the
   closest lines instead.
5. If he says "never learn about X again", add one line to `me/profile.md`: `- DATE: Do not keep notes about X. (Michael)`.
   Silent learning checks it before writing.

Never claim something was forgotten if a line still matches. Re-run the search after deleting to be sure.
