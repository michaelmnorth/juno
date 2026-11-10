# people/

One file per person Juno should know: family, partner, close friends, the coach, the CPA, anyone Michael engages
with repeatedly. Kin (the `relationships` agent) drafts and refreshes them from Google Contacts, the calendar and
what Michael says; the coordinator saves them. Everything here except this README stays on this PC (git-ignored).

## Where people data lives (three layers, so nothing grows unbounded)

| Layer | What | Size | Who reads it |
|---|---|---|---|
| `data/contacts/contacts.json` | The phone book: everyone in Google Contacts, with emails, phones, addresses, birthdays. Synced by `tools/contacts.py sync`. | Thousands is fine | Scripts only (`find`, `email-for`, `occasions.py`). A model never reads the whole file. |
| `people/<slug>.md` | Profiles for the people who matter: what Michael has said, tastes, life now, open threads. | Dozens, one short file each | Kin reads only the files for the people in the task, found with Grep. |
| `.claude/agents/relationships.md` | Kin's instructions. No people data, ever. | Fixed, about 60 lines | Loaded each time Kin runs. |

A profile repeats only what the phone book doesn't know. Its `address` line is for when it matters (the day planner,
gifts by mail) and comes from Contacts or Michael; Contacts stays the source of truth for numbers and addresses.

Shape (`people/<first>-<last>.md`):

```
# Sam Rivera
- relationship: coach (stated)
- confirmed: yes            # Michael has looked at this file; only then may the drafter address them unprompted
- check in every: 30 days   # opt-in: Kin's weekly "haven't talked to X in a while" (occasions.py cold)
- last contact: 2026-11-07 (dinner, Michael)   # in person, texts he mentions, calendar; mail never counts
- address: 12 Oak St, Springfield (Contacts)   # home; for travel times and mailed gifts
- also called: Coach        # aliases the calendar matcher looks for in event titles
- emails: sam@example.com
- how Michael addresses them: "Hey Sam,"   how they sign off: "Cheers, Sam"
- time zone: America/Chicago

## Dates
- birthday: --03-14 (Contacts)          # also listed in occasions.yaml, which is what the tools read

## Interests and tastes (gift-useful)
- Trail running; bought new shoes in May (mail 2026-05-10)

## Life now
- 2026-11-06: Prefers videos as Drive links, not attachments. (Michael)

## Open threads
- Waiting on the program for December (mail 2026-11-02)
```

Rules:
- Every line has a source and date. `stated` vs `likely`/`inferred` is kept honest.
- No health details, money amounts or account matters; at most a one-line pointer if it changes how to approach them.
- Only the coordinator writes here, with Michael present. Slack and timer runs queue each change with
  `tools/people_queue.py add`; the bridge posts it with Save and Skip, and a Save writes exactly that line (code,
  not a model). New people come from mail, invites and his DMs, matched by `tools/people_match.py`; anyone in
  Contacts without a profile gets a starter (`add --new`), `confirmed: no` until he says otherwise.
- The drafter may address only people whose file says `confirmed: yes` without being told explicitly.
- `occasions.yaml` holds every date worth remembering (birthdays, anniversaries, milestone years). Run
  `python tools/occasions.py check` after editing it.
