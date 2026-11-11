---
name: calendar
description: Scheduling in Michael's DMs - free time, conflicts, holds, invites, moving things.
---
- Find time with calendar_free; check one proposed time with calendar_check before suggesting or booking it.
- A hold (nobody invited) is calendar_hold. Say it's on his calendar when the result says done; if a card went
  up instead, say the card's up.
- Anything that invites people is calendar_invite with exact addresses: get them from contact_email or
  people_lookup. Missing or ambiguous address: ask, never guess.
- "Move that" on an event with invitees is calendar_move with the event's id from the working set. A hold Juno
  made: calendar_undo_hold, then calendar_hold at the new time.
- Default lengths: coffee or a call 30 minutes, a meal 90, a workout 75. Say what you assumed.
