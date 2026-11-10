# Design decisions: Juno's surfaces (2026-11-08)

The output of the design brief (docs/11-DESIGN-BRIEF.md), run in Paper (file "Juno", one page per screen). Each
screen had 3 or 4 variations side by side; Michael picked the parts he liked and they were merged into one chosen
design (the green "CHOSEN" artboard on each page). Fake data only in Paper.

Paper's free weekly MCP limit ran out after screen 2. Michael chose to finish screens 3 to 6 as HTML mockups in
the same look (`docs/design/`, one HTML file per screen plus a PNG per variation and the chosen one; the PNGs are kept on this PC in `docs/private/design/`). Copy the chosen
ones into the Paper file after the limit resets. Screens 1 and 2's variations are exported there too
(`paper-*.png`); their chosen designs are the green artboards in Paper.

Rules that apply to every screen:
- Slack draws the cards, so the design is structure and words, not color: no boxes, no colored text, no custom fonts.
  Bold, gray context lines, dividers and buttons are what we have.
- Every message sets a plain `text` fallback (what the lock screen and notifications show).
- Buttons that open more detail post it as a thread reply, so the main message stays short.
- Plain words, no em dashes.
- **Most used buttons up front, the rest in ⋯** (Michael, from the draft card). At most two or three buttons, the
  main one green; rarely used ones go in an `overflow` menu. The same goes for every card, not only email.
- **A facts grid for any card that acts for him** (Michael, from the draft card): `section` fields in two columns
  for the who, what and why, then the content itself in full. Health and money cards later use the same layout.
- **Fit Slack's limits** (docs/14, 2026-11-08): under 50 blocks a message and 100 on the Home tab; a `section` holds
  3,000 characters, so a longer draft splits across two sections and is never cut; no images in cards (a `context`
  image needs public hosting); every url button gets a no-op handler in the bridge, because Slack still sends it as
  an action.

## Decisions

| # | Screen | Chosen | Block Kit mapping |
|---|---|---|---|
| 1 | Morning brief | B + C: "Needs you" rows on top, then the day's timeline, While you were busy, Remembered with Undo | See section 1 |
| 2 | Draft card (email.send) | D + C: facts grid, full draft, Send and Edit in Gmail up front, the rest in ⋯ | See section 2 |
| 3 | Approval card (Allow once / Deny) and expired | B + C: a plain question, the facts grid, answer buttons named for the action; expired keeps the facts and asks "Still want it?" | See section 3 |
| 4 | Status reply and evening check-in | B for both: status as a facts grid; check-in as rows with a button each, Remembered with Undo, answer buttons for the one question | See section 4 |
| 5 | Sunday reflection | B + D: B's week summary grid, then D's changes (agent, the exact line, where it came from, Save or Skip); people in a second message | See section 5 |
| 6 | Juno home | A + C: the Slack App Home tab now, in the Today page's order and voice; the Today page look is the target for a Juno app later | See section 6 |

## 1. Morning brief

**Changed 2026-11-09 (Michael, after the first live briefs):** the buttons go. Tapping one and waiting for an answer
in the thread wasn't helpful, so the brief is now close to option A: Needs you as up to 6 numbered lines that each
say the whole thing, Gmail and directions as inline links, While you were busy and Picked up as short lists, no
Show, Undo or Prep buttons. The only taps are the reply drafts: each waiting draft's Send card (Send / Edit in Gmail /
Skip) is posted right under the brief, and its older copy is edited to point there. The people-notes Save card
still follows. The rest of this section is the original pick, kept for history. The evening check-in (section 4)
keeps its buttons for now.

**Chosen:** B (timeline with buttons) + C (three things). Not chosen: A (full text, nothing to tap), D (two-line
parent with a thread).

Order, top to bottom:
1. Headline and one gray line of counts.
2. **Needs you:** at most 3 numbered rows, each with one button. The first is the primary (green) button. More than 3:
   a context line "and 2 more" with the rest in the thread.
3. **Today:** each event on its own row, a prep button on the right, a gray line under it (leave-by, one thing to
   ask, a coach change).
4. **While you were busy:** the held-back items as one line, with a "Show N" button.
5. **Remembered ... Undo:** what Juno picked up since the last brief (idea 13), one row each, at most 3.
6. **From your watching:** one gray line.

| Part | Block | Notes |
|---|---|---|
| Headline | `header` (plain_text) | "Tuesday. Light day." Max 150 characters. |
| Counts | `context` (mrkdwn) | "3 need you · 2 events · slept 7h 05m". Health part only when the DB has data. |
| Breaks | `divider` | Between Needs you, Today, and the rest. |
| Section labels | `section` mrkdwn `*Needs you*`, `*Today*` | |
| Needs-you row | `section` mrkdwn `1. Dana asked about Saturday. Reply drafted.` + `accessory` button | Buttons by kind: draft → Review (opens the draft card in the thread), bill → Remind (asks when), occasion → Ideas (runs Kin, posts in thread), stale approval → Open. First row `style: primary`. |
| Event row | `section` mrkdwn `*12:30* Lunch with Dana, Juniper Cafe` + `accessory` button, then `context` for the prep line | Prep (posts people prep in thread), Workout (posts today's session), Directions (a `url` button) when there is a place. |
| While you were busy | `section` + `accessory` button "Show 5" | Tap posts the list in the thread. Replaces the "Held back" wording (idea 14). |
| Remembered | `section` mrkdwn `*Remembered* ...` + `accessory` button "Undo", then `context` "Seen 2 times · from your sent drafts" | Undo deletes the `observed/` line and logs it in `observed/changelog.md` (idea 13). |
| From your watching | `context` | One line; the full note stays in `domains/admin/notes/`. |
| Fallback text | message `text` | "Tuesday. Light day. 3 need you." |

Where it changes code: `.claude/skills/morning-brief/SKILL.md` (order and caps above), and a brief builder in the
bridge that turns the skill's JSON into these blocks, with action handlers for Review, Remind, Ideas, Prep, Workout,
Show N and Undo. Check accessory buttons on the phone; Slack mobile may wrap long rows.

## 2. Draft card (email.send)

**Chosen:** D (facts grid) + C (the ⋯ menu). Not chosen: A (today's card), B (one facts line). From Michael:
always show the full draft, never a preview, because he will not tap Send on text he has not seen. Send and Edit
in Gmail are the buttons he will use; the rest go in ⋯.

Top to bottom:
1. One bold line from Juno: "Reply to Dana is ready".
2. **Facts grid**, two columns: To, Who, Subject, Why.
3. **The full draft**, quoted.
4. Buttons: Send (green), Edit in Gmail, ⋯.

**Who** says how he knows them, not "known" or "unknown":
- In `people/`: the `relationship:` line from the profile (Friend, Family, Client) and when they last wrote.
- In Google Contacts only: "In your contacts".
- Unknown: how many times they have written, and whether he has answered: "1st email from him", "3rd email, no
  reply yet". They may be someone he deals with but has not answered yet, so the count matters more than the label.

**Who writes what.** To and Who come from the bridge, in code (`tools/trust.py`, the profile, the mail index), never
from Juno's summary, so a stranger cannot be made to look like a friend (idea 12). Juno writes only the bold line
and Why.

| Part | Block | Notes |
|---|---|---|
| Summary | `section` mrkdwn `*Reply to Dana is ready*` | Juno's words. |
| Facts | `section` with 4 `fields` (mrkdwn): `*To*\nDana\ndana@example.com`, `*Who*\nFriend\nLast wrote 2 weeks ago`, `*Subject*\nRe: Saturday plans`, `*Why*\nShe asked if you're free` | Slack shows fields in two columns. To and Who built by the bridge. |
| Draft | `section` mrkdwn, every line prefixed `> ` | The whole draft. A section holds 3,000 characters; split longer drafts into more sections, never cut them. |
| Buttons | `actions`: `button` Send (`style: primary`, action_id `approve`), `button` Edit in Gmail (`url` = draft link), `overflow` | Overflow options: "Always send to Dana" (`always`) and "Skip" (`deny`). For an unknown recipient: Skip only. |
| After a tap | `chat.update` | Buttons replaced by a context line: "Sent 9:20 AM" or "Skipped". |
| Fallback text | message `text` | "Reply to Dana is ready". |

Where it changes code: `gateway/approval_policy.py` (`card_text` and `blocks` for `email.send`: fields instead of
the italic To and Subject line, the full draft instead of the 700-character cut, Always and Skip moved to an
overflow), the bridge's action handler (overflow sends `block_actions` with `selected_option.value`), and a small
helper that builds the Who field from the profile or the mail index. Tests: no Always option for an unknown
recipient, and the draft text in the card matches the approved draft exactly.

## 3. Approval card (Allow once / Deny) and the expired state

**Chosen:** B (facts grid, Ask again) + C (one question with answer buttons). Not chosen: A (today's card),
D (several OKs grouped in one card).

Waiting, top to bottom:
1. Juno's question in bold, one sentence: "Okay to invite Dana to the market, Saturday 10 to 12?"
2. **Facts grid:** What, Invites (or Reaches), Changes, Expires.
3. Buttons: the yes (green, named for the action), Not now, ⋯.

Expired (30 minutes after a timer card, `approval_policy.expired`): the same message, edited in place.
1. The question struck through.
2. What and Invites only.
3. A gray line from the bridge: "Expired 9:44 AM. Nothing changed, no invite sent."
4. "Still want it?" with Yes, ask again (green) and No, drop it.

**Button names come from the action class, in code,** not from Juno's text, so a card cannot dress up what it does:

| action_class | Yes button | ⋯ holds | Always? |
|---|---|---|---|
| `calendar.event.create` | Yes, invite (Yes, add it when no one is invited) | Other time | Never: events that invite people always ask |
| `calendar.event.update` | Yes, move it | Other time | Never |
| `calendar.hold` | Yes, add it | Always add holds, Other time | Yes (`ALWAYS_ALLOWABLE`) |
| `subagent.install` | Yes, install | Show files | Never |
| anything else | Yes | (empty, no ⋯) | Never |

| Part | Block | Notes |
|---|---|---|
| Question | `section` mrkdwn `*Okay to invite Dana to the market, Saturday 10 to 12?*` | Juno's `summary`, phrased as a question. |
| Facts | `section` with `fields`: `*What*`, `*Invites*` (or `*Reaches*`), `*Changes*`, `*Expires*` | Built by the bridge: What from `action`, Invites from `recipients()` with the Who wording from screen 2, Changes from the class, Expires from `created` + 30 min. Expires only on timer cards. |
| Buttons | `actions`: `button` yes (`style: primary`, `approve`), `button` Not now (`deny`), `overflow` | Overflow options per the table. Other time replies "What time instead?" and keeps the card open. |
| Expired | `chat.update` with: struck question (`~...~`), `section` fields What and Invites, `context` with a ⏱ character and the expiry line (not an image; docs/14), `section` "Still want it?", `actions` Yes, ask again (`reask`, primary) and No, drop it (`drop`) | Ask again writes a new pending entry with a fresh `created` and posts a new card; the old one says "Asked again 10:02 AM". |
| Fallback text | message `text` | The question. |

Where it changes code: `gateway/approval_policy.py` (`card_text` and `blocks` for non-draft classes, a table of
button names per class, an `expired_blocks(entry)` builder), the bridge's expiry job (it now edits the card instead of
only marking it), and two new action ids (`reask`, `drop`). Tests: no Always for invite classes, button names come
from the class even if the summary says otherwise, and Ask again creates a new id.

## 4. Status reply and evening check-in

**Chosen:** B for both (grid and rows). Not chosen: A (plain bullets), C (one line, one question, the rest in the
thread). Added after the pick: a Remembered row with Undo in the check-in, the same as the brief.

### Status (answered by the bridge, no Claude run: `slack_bridge.status_text`)
1. One bold line: "All running", or "1 problem" when a job failed or is blocked.
2. **Facts grid:** Last sweep, Next, Waiting on you, Pings today, Spent today, Problems.
3. Buttons: Show the N (green, posts the waiting cards again in the thread), ⋯.

| Part | Block | Source |
|---|---|---|
| Headline | `section` mrkdwn `*All running*` | `state/last-run.json`: any job not `ok` makes it "N problems". |
| Grid | `section` with 6 `fields` | Last sweep: `last-run.json` + the sweep log's count. Next: `state/timers.json` and the schedule. Waiting on you: `pending-approvals.json` (new or posted). Pings today: `state/signals.jsonl` against `me/proactivity.yaml`'s budget. Spent today: `state/costs.jsonl` against the daily cap. Problems: failed or blocked jobs, or "None". |
| Buttons | `actions`: `button` Show the N (`primary`), `overflow` | Overflow: Sweep now, Pause pings 2 hours, Why is X blocked (only when there is a problem). |
| Reactions | `reactions.add` on his message | 👀 when read, ✅ when answered (unchanged). |

### Evening check-in (`.claude/skills/evening-checkin`)
1. Bold headline: "Tomorrow starts at 9:30" (the first event), or "Nothing on tomorrow".
2. **Tomorrow:** a row per event, a button on the right (Prep, Ideas, Directions), a gray prep line.
3. Divider. **Still open:** a row per unsent draft or stale card (Review), quiet mail as one row (Show N), and
   Remembered rows (Undo), at most 3.
4. Divider. **One question** with answer buttons. Training: Trained / Rest day / Skipped. Otherwise "Anything for
   tomorrow?" with Add a note / No. Never two questions.

| Part | Block | Notes |
|---|---|---|
| Headline | `section` mrkdwn bold | Fallback `text` is the same line. |
| Event row | `section` + `accessory` button, then `context` | Same as the brief's Today rows. |
| Open item row | `section` + `accessory` button, then `context` | Review opens the draft card in the thread; Show N posts the list in the thread. |
| Remembered | `section` + `accessory` Undo, then `context` "Seen 3 times · from your calendar" | Same handler as the brief (idea 13). |
| Question | `section` + `actions` with up to 3 buttons, first `primary` | The answer goes back to Juno as his reply (idea 11). Trained / Rest day / Skipped writes a `signals.jsonl` line and, for Trained, nothing else; Skipped asks nothing more. |

Where it changes code: `slack_bridge.status_text` becomes `status_blocks` (keep the text version as the fallback),
the evening check-in skill outputs rows as JSON for a block builder shared with the brief, and an "answer button"
handler that posts the button's label back to the session as Michael's reply.

## 5. Sunday reflection

**Chosen:** B's short summary + D's "show the change" (Michael: "I absolutely love" both). Not chosen: A (one card
of plain lessons), C (checklist). Assumed: one message with every change, not B's one-lesson-per-tap flow, because
Michael named B's summary, not its flow. If the list grows past 5 (the skill's cap), switch to one per tap. Also cap
it by blocks: if the message would pass 50 blocks, the rest goes to "Show all" in the thread (docs/14).

Message 1, top to bottom:
1. Bold "Your week, Nov 2 to 8".
2. **Summary grid:** Runs, Blocked, Spent, To review.
3. Per proposed lesson, after a divider: the **agent it goes to** in bold ("Quill (drafts)"), the **exact line** in a
   code block (`+` for a new line; `-` then `+` when it replaces one), a gray line with **where it came from** and
   what it replaces, then Save (green), Skip, ⋯ (Change the wording).
4. **From your watching:** the themes in one line and at most 2 ideas for Juno, each with Draft it / Not now.

Message 2: **Coming up**, at most 3 rows from Kin (birthdays, round numbers, gone quiet), each with a button (Ideas,
Draft hi). Cold contacts at most 2.

| Part | Block | Notes |
|---|---|---|
| Title | `section` mrkdwn bold | Fallback `text`: "Your week: 2 changes to review". |
| Summary | `section` with 4 `fields` | Runs and failures from `logs/`, Blocked from the audit log, Spent from `state/costs.jsonl`, To review from `state/proposed-lessons.md`. |
| Agent label | `section` mrkdwn `*Quill (drafts)*` | From the proposal's target file: `learnings/drafter.md` → Quill (drafts); `learnings/coordinator.md` → Juno; `me/*.md` → You; `people/x.md` → the person's name. |
| The change | `rich_text` with `rich_text_preformatted` | `+ new line`, or `- old line` and `+ new line`. One color; Slack cannot color code. The line shown is exactly the line the lesson skill will write. |
| Evidence | `context` | The reflector's evidence in plain words and the date of the line it replaces. Never quotes mail. |
| Buttons | `actions`: Save (`primary`), Skip, `overflow` (Change the wording) | Save runs the `lesson` skill with that target and line (T3, so the tap is the yes). Skip writes the 30-day no-repeat signal. After a tap, `chat.update` swaps the buttons for "Saved" or "Skipped". |
| Watching idea | `section` + `actions` Draft it / Not now | Draft it runs `new-subagent` or a change proposal; nothing is built without that tap. |
| Coming up | `section` + `accessory` button, then `context`, per person | Ideas runs Kin and posts in the thread; Draft hi asks Quill for a short note and posts the draft card. |

Where it changes code: `.claude/skills/weekly-reflection/SKILL.md` (the card shape above; the reflector's proposals
need `target`, `old_line`, `new_line` and `evidence` fields), a reflection block builder in the bridge, and Save /
Skip handlers that resume the session with the proposal id.

## 6. Juno home

**Chosen:** A (Slack Home tab) + C (Today page). Not chosen: B (one bot per row, messages-app style). Built now as the
Home tab of Juno's Slack app, so it needs no new app. It uses C's order and voice, so the same data ports to a Juno
app later with C's look (bone and moss, rounded cards, big headline): that part is marked **needs a Juno app**.

Top to bottom:
1. Gray line: date and "updated 6:12 PM".
2. **Headline** in C's voice: "Quiet evening. 2 for you." (time of day plus how many things wait).
3. **What waits:** a row per item with a button (first one green). Same items as the brief's Needs you.
4. **Learned:** at most 3 recent `observed/` lines with Undo (idea 13).
5. **People:** the nearest occasion as a row with Ideas; the next two as one gray line.
6. **This week:** a grid with runs, spent, pings answered, and problems.

| Part | Block | Notes |
|---|---|---|
| Tab | `views.publish` with `type: home` on `app_home_opened` | Rebuilt each time he opens it, and after any card is answered. Needs the `app_home_opened` event and the Home tab turned on in the Slack app settings (Michael does that once). |
| Date line | `context` | |
| Headline | `header` (plain_text) | Built from the count of waiting items: "2 for you", or "Nothing for you" when empty. |
| What waits | `section` + `accessory` button, then `context` | Review opens the card in the DM (a `url` button to the message permalink). |
| Learned | `section` + `accessory` Undo, then `context` "Seen 3 times" | Same Undo handler as the brief. |
| People | `section` + `accessory` Ideas for the nearest; `context` for the next two | From `tools/occasions.py upcoming --days 30`. |
| This week | `section` with 4 `fields` | Same sources as the status grid (section 4). |

Where it changes code: a `home_view()` builder in the bridge that reuses the brief, status and reflection builders,
an `app_home_opened` handler, and the Slack app manifest (Home tab on, the event subscribed). Michael turns on the
Home tab in the Slack app settings; nothing else outward changes.

## What is left
- Copy the chosen designs for screens 3 to 6 into the Paper file "Juno" after the free MCP limit resets (about
  2026-11-13), so the file holds all six.
- Done 2026-11-08: the test DM (docs/14). Screen 1, the morning brief, is built: `gateway/brief_blocks.py` draws the
  card from the job's JSON, `tests/test_brief_blocks.py` covers it, `docs/private/design/1-brief-built-desktop.jpg` (on this PC) shows it.
  Every plain reply now converts Markdown bold, links and headings to Slack's format.
- Done 2026-11-08: screens 2 and 3 (`gateway/approval_policy.py`: draft card, approval card, expired state) and
  screens 4 to 6 (`gateway/cards.py`: status grid on "status" with no Claude run, evening check-in with answer
  buttons, Sunday reflection with Save / Skip / Change the wording per lesson, and the Home tab). Home tab turned on
  and `app_home_opened` subscribed in the Slack app settings (no new scope, no reinstall); the bridge rebuilds the tab
  on every open, confirmed in Slack web. Samples: `python gateway/block_check.py --checkin | --reflection | --status |
  --home`. Tests: `tests/test_cards.py`.
- Not yet tried live: the taps that start a Claude run (brief buttons, check-in answers, Save / Skip). The first real
  7:00 brief, 8:30 check-in and Sunday reflection will exercise them. Draft-card Send was deliberately not tapped.
- Not built: Home refresh "after any card is answered" (it rebuilds on open only, which covers it in practice).
- Changed 2026-11-08 (Michael, from his phone): **the Slack Home tab is off.** On iPhone, tapping Juno opened the
  Home tab first, so every conversation cost an extra tap. Screen 6 now posts in the DM when he types "home" (or
  "today"); same blocks, same Open links. The tab and its `app_home_opened` event are removed from the app settings
  and the manifest. A Home view comes back only in a Juno app of its own (C's look).
- Changed 2026-11-08: DMs with a photo were dropped (Slack sends them as `file_share`). They now reach Juno, and the
  bot has `files:read`: photos are saved to `state/attachments/` and the DM run reads them.
