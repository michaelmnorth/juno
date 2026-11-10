# tools/

Fixed Python scripts the agents are allowed to run (`python tools/<name>.py ...`). Each one:

- fetches its secrets with `op run --env-file=tools/<name>.env -- python tools/<name>.py`, where the `.env` holds only
  `op://Agent-Secrets/<item>/<field>` references (the `.env` files are git-ignored anyway);
- never prints a token, an account number or a raw credential; finance output carries last-4 only;
- writes to `data/*.sqlite` or prints compact JSON for the agent to read;
- exits non-zero with a one-line reason on failure, so the agent reports instead of guessing.

Live: `youtube.py` (Reel); `mail_index.py` (whole-mailbox header index from a Google Takeout mbox, for rules,
cleanup suggestions and people); `contacts.py` (Google Contacts, synced read-only or from a vCard: emails, phones, birthdays, addresses);
`occasions.py` (birthdays, anniversaries and milestone years from `people/occasions.yaml` and Contacts; all date
math). The last three serve Kin (`relationships`). Their data lives in `data/mail/` and `data/contacts/`.
`people_match.py` (who in a mail or invite has a profile, and who in Contacts doesn't yet; starter profiles).
`people_queue.py` (profile notes waiting for Michael's Save tap; the bridge writes them on Save).
`trust.py` (michael, known, contact or unknown for an address; the bridge labels approval cards with it).
`observed.py` (life cycle of Juno's silent notes: confidence, stale retirement, duplicates, size).
`google_read.py` (Google sign-in and the sweep wake gate). `inbox.py` (new inbox mail for the sweep and brief:
headers, trust labels and `domains/admin/inbox-sort.yaml` settle most of it in code; the rest goes to Sorter as a
packet of cleaned text in `state/inbox/`, so the coordinator never reads a body). `gmail.py` (Juno's own Gmail writer: drafts, replies in
thread, `Juno/` labels; no send, trash or archive). `gcal.py` (read events, holds on his own calendar, approved events
and updates; every write needs the one-time approval token the bridge issues, see `gateway/approval_tokens.py`).
All three read their Google secrets with the 1Password service account and rerun themselves in `.venv` when called
with the system Python.
`hevy_pull.py` (Hevy workouts into `data/health.sqlite`: `pull`, `summary`, `lift`; key from 1Password item
Hevy-Juno; read-only toward Hevy; also keeps each exercise's notes and the routine id).
`sheets.py` (the coach's block tab: `plan` what Hevy says belongs there, `write` Actual, LsRPE and "MN:" notes;
weeks by order done, never overwrites a filled cell or the coach's text; config in `domains/health/private/coach-sheet.yaml`).

Planned (see docs/04-PLAN.md): `health_import.py` (iCloud JSON drop → health.sqlite), `withings_pull.py`
(likely not needed: the scale writes to Apple Health), `finance_fetch.py` (Plaid/SimpleFIN → finance.sqlite,
sanitized), `video_split.py` (ffmpeg). The scheduling engine was never pinned; `slots.py` (free slots, conflict
checks, exact times from the calendar) does Tempo's time math instead.
