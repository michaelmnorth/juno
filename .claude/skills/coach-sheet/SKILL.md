---
name: coach-sheet
description: Log Michael's Hevy workouts onto the coach's program sheet (Actual, LsRPE, "MN:" notes) and hand him a copy-paste note for the coach per new session (W1D4 ...). Use when Michael says "update the sheet", "sync my workout", "log that to the coach's sheet", or "note for the coach". The bridge runs the same sync on its own after each saved workout.
---

# Coach sheet sync

This job is lean on purpose (docs/17-BUILD-PATTERNS.md): Python does every number and one words-only model call does
the MN lines and the coach note. Don't redo it by hand or hand it to a subagent.

1. Run `python tools/coach_sheet.py sync`. It pulls Hevy, plans the current block, writes the numbers, makes the
   one model call, writes the notes, and prints `{"ok", "message", "written"}`.
2. Relay `message` to Michael as it is: it already has the coach note in code blocks and anything left alone.
   `message` null: nothing new; say so in one line. `ok` false: the numbers are in and the notes will be retried on
   the next check; say that plainly.
3. A cell left alone, a workout in the wrong week, or "logged but not on the sheet" is never forced. Moves, clears
   and overwrites are his call from the Code tab (`tools/sheets.py write --repair` or `--fix <cell>`).

Rules for what goes where: `domains/health/CONTEXT.md`.
