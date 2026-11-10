# 07 · Profiles and onboarding

The same engine has to serve the owner's personal life, a work context, and people rebuilding it from the template. That only works if the engine knows no person. This spec defines the split, the profile file, the onboarding flow, and the rules for a work twin.

## Three things, kept apart

| Thing | Contains | Lives | Shared? |
|---|---|---|---|
| **Core + packs** | Engine code, tool packs, playbooks, synthetic eval fixtures | Code repo | Yes. Safe to publish or hand to a cohort |
| **Profile** | Who this instance serves and what it may do: channels, packs, policy, models, schedules | `profile.yaml`, `persona.md`, `core-card.md`, `rules.yaml` in the instance directory | Templates only |
| **Instance** | One profile plus its data: memory, golden evals, logs, credentials reference | One host, one directory, one vault | Never |

A CI check fails the build if the code repo contains owner strings (names, addresses, sheet IDs) or anything from an instance directory.

## One instance per context

Personal and work are **separate instances**, not one assistant with a work subagent.

- **Data rules.** Employer and client data may not sit in a personal memory store or pass through a personal API account.
- **Blast radius.** A hostile personal email must not be one hop from work systems.
- **Different policy.** Work needs stricter gates and its own retention.
- **Clean exit.** Changing jobs means deleting one directory and revoking one vault.

Nothing crosses between instances at the agent level. If the two need to avoid double-booking, share free/busy between the calendars with the calendar product's own feature.

## `profile.yaml`

Shape, not final schema. The loader validates it and refuses to start on unknown keys.

```yaml
profile:
  id: personal
  owner: { display_name: "<name>", timezone: "America/New_York", locale: "en-US" }
  persona: persona.md
  core_card: core-card.md

channels:
  - type: slack
    mode: socket
    owner_user_id: "<U…>"
    primary: true

packs:
  mail:        { provider: gmail,  capabilities: [read, label, draft, send_with_tap] }
  calendar:    { provider: google, capabilities: [read, hold, event_with_tap] }
  people:      {}
  reminders:   {}
  research:    { max_searches_per_run: 5 }
  health_hevy: { automations: [workout_to_coach_sheet] }

policy:
  quiet_hours: ["22:00", "06:00"]
  pings_per_day: 5
  budgets: { call_usd: 0.05, run_usd: 0.50, task_usd: 2.00, day_usd: 3.00, month_alert_usd: 40 }
  data_classes:
    finance: { allow_run_classes: [converse, reflect], tainted: deny }
    health:  { allow_run_classes: [converse, reflect], tainted: deny }
  autonomy: []                     # earned-autonomy shapes the owner has switched on

models:
  router: claude-haiku-5-5
  reader: claude-haiku-5-5
  converse: { model: claude-sonnet-5-5, effort: low }
  compose: claude-sonnet-5-5
  reflect_nightly: claude-sonnet-5-5
  reflect_weekly: claude-opus-5-5

schedules:
  - { id: morning_brief,    cron: "0 7 * * *",   playbook: morning-brief }
  - { id: evening_checkin,  cron: "30 20 * * *", playbook: evening-checkin }
  - { id: consolidate,      cron: "30 2 * * *",  lane: batch }
  - { id: weekly_review,    cron: "0 18 * * 0",  lane: batch }

secrets: { backend: 1password, vault: "<vault name>" }
backup:  { target: "<encrypted off-box location>", retain_days: 30 }
```

A **pack** is a folder with tools (`ToolSpec`s), playbooks, automations, rule templates and eval fixtures. A profile enables packs and narrows their capabilities; it cannot widen what a pack defines.

## Onboarding

One flow creates any instance. The owner's own personal instance is the first one built with it: if Juno cannot be rebuilt from an empty directory by following the prompts, onboarding is not done.

| Step | What happens | Output |
|---|---|---|
| **0 · Preflight** | Check host, vault access, API key, clock and timezone. Create the channel app from a manifest. Grant each connector with the narrowest scopes. Run one read-only smoke test per connector | A green checklist; nothing stored yet |
| **1 · Interview** | In the channel, about 12 questions in about 10 minutes: roles, current priorities, people who matter, hard rules, quiet hours, what "urgent" means, how the owner likes to be told things | Draft core card, persona and policy; owner edits and accepts |
| **2 · Bootstrap** | Read-only pass over the last 90 days: calendar (routines), sent mail (voice examples, from the owner's own text), contacts (entity seeds), top correspondents (VIP candidates) | A review screen. Nothing is saved until accepted item by item or in bulk |
| **3 · Shadow week** | Juno drafts and proposes but takes no automatic action. Pings are limited to the brief and check-in. Each day asks two calibration questions | Signals, first golden eval cases, a tuned `rules.yaml` |
| **4 · Graduation** | Scorecard review. Turn on automations per pack. Pick candidates for earned autonomy | Profile updated by the owner |
| **5 · Steady state** | Monthly profile review prompt; quarterly restore drill | — |

Design notes:

- The interview is a playbook plus a form schema, not free chat, so two people get comparable profiles.
- Bootstrap reads other people's mail only as metadata (who, when, how often). Voice examples come from the owner's sent mail.
- Shadow week is what makes a new instance trustworthy. Do not skip it for the work twin.
- Offboarding is part of onboarding: one command exports the owner's data, revokes tokens, and deletes the instance directory and backups.

## The work twin

### Gate first

Before any build: written confirmation from the employer of (a) which Claude deployment is approved for company and client data, (b) which systems an assistant may read and write, (c) retention and audit requirements. This is a decision for the owner and the employer, not for a coding session.

### Two ways to run it

| | **A · Skills-only twin** | **B · Full instance** |
|---|---|---|
| What | The work packs' playbooks shipped as a plugin inside the employer's Claude plan, using its admin-approved connectors and scheduled tasks | A second Juno instance on employer-approved infrastructure |
| Gets | Call prep, recaps, weekly notes, follow-up drafts, on demand or on a schedule | The same, plus code-enforced gates, proactive pings with caps, memory with provenance, the learning loop |
| Costs | Almost nothing to build; data stays where IT already approved it | A host, credentials, a security review, ongoing ownership |
| Choose when | The employer has Claude for Work and the need is drafting and summarising | The need is proactive, stateful help and IT signs off |

Default: **start with A.** Playbooks are written once in the Agent Skills format and run in both. Move to B when A's limits are the actual problem.

### What differs in a work profile

- **Packs.** Work mail and calendar, the team's chat workspace, the project system, documents, meeting notes.
- **Policy.** Everything visible to a client or colleague is a tap, with no earned autonomy. Research runs never receive client names or content.
- **Data classes.** `client_confidential` items never enter `research`, never leave the instance, and appear in logs only as pointers.
- **Models and billing.** The employer's account and, if required, its cloud provider. The core depends only on the Messages API so it runs wherever the model is offered. Keep any hosted-agent feature behind the L4 interface.
- **Memory.** Per-client entities and dossiers. Retention follows company policy. No personal facts about the owner are imported from the personal instance.
- **Exit.** The offboarding command is tested before the instance goes live.

## For the cohort

The same three-way split is the teaching structure: students clone core and packs, run onboarding to produce their own profile, and never see anyone else's instance. The personal profile in the owner's instance is the worked example; a scrubbed `profile.example.yaml` ships in the repo.
