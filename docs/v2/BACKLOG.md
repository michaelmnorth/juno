# Backlog (ideas held by the freeze)

- **Work twin onboarding (owner, 2026-11-10).** A GitHub link plus a starter prompt for the work Claude Code, so a
  second instance starts from this one's prompts, configuration, persona and feedback loop without the personal
  data. Covered by kit P5 (core/profile/instance split) and P7 (work twin, with the employer gate first). Before
  that, a hand-picked list of what to carry (persona, preferences, build patterns) and what never to (mail,
  contacts, people, health, money).
- **Sleep, weight and macros for Rep** (Withings or Apple Health import) and **money data for Ledger** (kit
  Phase 4). Both agents now say "not connected" instead of pointing at scripts that never existed.
- **Hevy routine creation** (gated, T3). No tool yet; Rep returns routines as text.
- **Holds dedupe.** `gcal.py hold` has no idempotency key; the run lock covers concurrent runs, not a repeated ask.
- **Browser agent extras (P2).** A headed mode if Michael ever wants to watch; reusing the
  profile's sign-ins for sites he logs into himself; a gate that sees the page (Playwright's element role and name)
  instead of the model's description, so a fill run could click a widget safely.
- **Progress line for long v1 runs (P2 #12).** A short "on it, checking your mail" while a DM run takes over a
  minute, as the other assistant did with its reaction and interim reply.
