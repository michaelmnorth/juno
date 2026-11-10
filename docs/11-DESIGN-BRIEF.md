# Design brief: Juno in Paper (2026-11-08)

Michael wants to redo Juno's design phase the way docs/10-VIDEO-BOPS.md describes: research, then design in Paper
before code, diverge then converge. This is the brief for that session.

## Setup (Michael, once)
1. Open Paper Desktop and create a file named "Juno".
2. In PowerShell (one line; `claude` is not on PATH here): `cd "$env:USERPROFILE\Claude-Personal\personal-coordinator"; & (Get-ChildItem "$env:APPDATA\Claude\claude-code\*\*\claude.exe" | Sort-Object LastWriteTime | Select-Object -Last 1).FullName mcp add --transport http paper http://127.0.0.1:29979/mcp`
3. Start a new Claude Code session here (MCP servers load at session start) and say "run the design brief".

## What exists today (the research step, already known)
- Juno lives in a Slack DM on Michael's phone. Everything he sees is Slack text plus Block Kit buttons.
- Surfaces: the 7:00 morning brief, the sweep pings, the Send / Always send / Edit / Skip draft cards, the Allow once
  / Deny cards, leave-by pings, the 20:30 check-in, the Sunday reflection card, the `status` reply, and the
  eyes / working / done reactions.
- Voice: dry warmth, short sentences, lead with what was done or what is needed (CLAUDE.md, "Your personality").
- Constraint: Slack Block Kit limits the layout (sections, context lines, buttons, dividers, small images). Any
  design must be buildable in Block Kit, or it is marked "needs a Juno app".

## Also read first
docs/12-BOPS-VS-JUNO.md: what Bops' interface gets right. Design these patterns in too: Options buttons (11),
system-written card facts (12), "Remembered ... Undo" (13), "While you were busy" (14), Juno home (18).

## Screens to design (diverge: 3 or 4 variations each, then converge)
1. **Morning brief** on a phone: today, people prep, held-back items, picked up, from your watching.
2. **Draft card** (email.send): known person vs stranger (trust label), the draft preview, buttons.
3. **Approval card** (Allow once / Deny) and the expired state.
4. **Status** reply and the **evening check-in**.
5. **Sunday reflection:** lessons to Save or Skip, cost and reliability, coming up for people.
6. Optional: a **Juno home** (a Slack App Home tab, or a later web app): what is waiting, what Juno learned, people
   coming up, costs. Inspiration from the video: an iMessage-like calm, one bot per row.

## Rules for the session
- Swipe file: Michael's screenshots go in `domains/admin/swipe/` (git-ignored if personal).
- Use real shapes with fake data only (no real names, emails or health or money figures in Paper files).
- Output: the chosen design per screen, plus a note mapping it to Block Kit; then build in `gateway/approval_policy.py`
  and the skills, with tests, one commit per screen.
