# Brief P5 · Profiles and onboarding

**Hand this to a Claude Code session after Phase 3 has exited.** Read `07-PROFILES-AND-ONBOARDING.md` in full and the layout section of `02-ARCHITECTURE.md`.

## Goal

The engine knows no person. A new instance, for the owner, for a work context or for a student, is created by one onboarding flow from an empty directory.

## Deliverables

1. **Separation enforced.** Core and packs in the code repo; profile and data in the instance directory. A CI scan fails on owner strings (names, addresses, document IDs, phone numbers) or instance files in the repo.
2. **Profile loader and validator** for `profile.yaml`: strict schema, unknown keys refused, a readable error for each problem, a `--check` mode.
3. **Packs** as folders with tools, playbooks (`SKILL.md` format), automations, rule templates and synthetic eval fixtures. Owner-specific packs (the coach sheet) are separate from general ones (mail, calendar, people, reminders, research).
4. **Onboarding flow,** steps 0 to 5: preflight checks with connector smoke tests; the interview playbook with a fixed form schema; read-only bootstrap with a review screen; shadow mode enforced by the policy engine; graduation review.
5. **Shadow mode** as a policy setting: no automatic actions, pings limited to brief and check-in, two calibration questions a day.
6. **Offboarding command:** export, revoke, delete the instance directory and its backups, and verify.
7. **`profile.example.yaml`,** a scrubbed persona and core-card template, and a short operator guide.
8. **Rebuild test:** the owner's personal instance recreated from an empty directory on a fresh container, following only the onboarding prompts.

## Done when

- Empty directory to first morning brief in **≤ 60 minutes** of the owner's time, timed, without reading source code.
- The CI scan finds nothing personal in the repo.
- Two instances with different profiles run side by side on one host with no shared files, credentials or network identity, and a test proves a tool in one cannot read the other's directory.
- Offboarding leaves no data and no valid tokens.
- The owner's live instance runs unchanged on the new layout.

## Guardrails

- A profile can enable and narrow packs. It cannot grant a capability a pack does not define.
- The interview is a schema with questions, not open chat. Two people answering the same questions get comparable profiles.
- Bootstrap reads other people's mail as metadata only. Voice examples come from the owner's sent mail.
- Nothing from the bootstrap is saved before the owner accepts it.
- Do not build multi-user features. One human per instance.

## Report back

The timed rebuild with where the minutes went, the CI scan rules, what had to move out of core, and which onboarding questions produced unusable answers.
