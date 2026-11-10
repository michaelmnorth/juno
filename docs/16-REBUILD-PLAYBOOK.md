# Rebuild playbook: set up a coordinator on a new machine

Use this to stand up a copy of Juno from this repo on another computer, starting with Michael's work computer. Each
step says what is the same and what changes. The work copy uses its own account, its own folder and its own secrets,
and never shares anything with this personal one. Written 2026-11-08 from the personal build. Update it when a
step changes.

**How to use it:** open a Claude Code session in the new folder and say "Follow docs/16-REBUILD-PLAYBOOK.md with me,
one step at a time". [M] marks steps only the person can do: accounts, approvals, devices, pasting secrets.

## What the repo has and doesn't have

- **In the repo (the template):**
  - `CLAUDE.md`, agents (`.claude/agents/`), skills (`.claude/skills/`), hooks (`.claude/hooks/`), settings.
  - The Slack bridge (`gateway/`), tools (`tools/`), tests, docs.
  - Blank templates: `me/*.example.md`, `domains/*/CONTEXT.example.md`, `learnings/_template.md`.
- **Never in the repo (stays on each machine):**
  - Real `me/` files, `people/`, `observed/`, `state/`, `logs/`, `data/`, every `private/` folder, `.env` files.
- **Never in any file:** secrets. They live in a secrets manager and are read inside fixed scripts.

## Steps

| # | Step | Personal (done 2026-11) | Work: what changes |
|---|---|---|---|
| 1 | **Folder and clone.** Clone the repo into its own folder. Make a Python venv and install `gateway/requirements.txt`. | `C:\Users\Michael\Claude-Personal\personal-coordinator` | A separate work folder under the work account. Don't reuse the personal clone. |
| 2 | **[M] Name and persona.** Pick the coordinator's name and personality in `me/profile.md`. | Juno | Its own name (Dispatch already exists for work; decide whether this replaces or upgrades it). |
| 3 | **[M] Onboarding interview.** Copy each `.example` file to its real name. Claude asks the questions in each template; answers go in as dated lines: `me/profile.md`, `goals.md`, `schedule.md`, `voice.md` (ten real sent messages), `domains/*/CONTEXT.md`, `learnings/<agent>.md` per agent. | Done from an "everything about me" export plus Q&A | Work context only: role, clients, team, working hours, writing samples from work mail. Leave the domains that don't apply (health, finance) out. |
| 4 | **Guardrails first.** Review `CLAUDE.md` tiers (T0 to T4), `.claude/settings.json` deny rules and the three hooks before any connector. Run `python -m pytest -q tests`. | Done | Adjust the deny list to the work machine's paths. Keep the tiers. Keep work and personal blocked from each other. |
| 5 | **[M] Secrets manager.** One vault for the coordinator only, and a service account limited to it with read and write. Store the key with `gateway/token_store.py --store-op-token` (Windows Credential Manager). Check with `--check`. | 1Password vault `Agent-Secrets`, service account "Juno read-write" | The work secrets manager. The swap is in one place: `gateway/token_store.py` (`find_op`, `read_ref`, `REFS`) and the `op://` references in `tools/*.env.example`. Ask IT which manager and whether a service identity is allowed. |
| 6 | **[M] Chat channel.** Create the app from `gateway/slack-app-manifest.yaml`. Put its two tokens in the vault and your member ID in `me/notify-allowlist.json`. | Slack free workspace, bot "Juno", DM only, Home tab off | Teams or the company Slack, whatever IT allows. A Teams bot means a new bridge; the cards in `gateway/cards.py` are Slack Block Kit. |
| 7 | **Bridge.** Prove `python gateway/slack_bridge.py --once "hello"`, then register the logon task (`gateway/install_task.ps1`). Check `logs/bridge.log` for "Bolt app is running". | Running at logon on this PC | Same, if the work machine allows a logon task and `claude -p`. |
| 8 | **[M] Mail and calendar.** Own OAuth app, desktop client, loopback sign-in (`tools/google_read.py signin`), refresh token saved to the vault. Wake gate reads changes in Python. | Google Cloud project "Juno", gmail.modify + calendar.events, public privacy page for the consent screen | Outlook and Microsoft 365. Use the Outlook MCP the company already connected for reads. For the wake gate, an Azure app registration with Microsoft Graph `Mail.Read` / `Calendars.Read`, if IT allows; otherwise the gate stays off and sweeps always run. |
| 9 | **[M] Approvals.** Sending mail, creating events and anything outward wait for a tap (`state/pending-approvals.json`, cards). `me/automation.yaml` lists what may run without one. | Holds on own calendar are automatic; everything else asks | Same rule. Expect stricter company policy. Start with everything on ask. |
| 10 | **Timers.** `me/proactivity.yaml`: morning brief, evening check-in, sweep window, weekly reflection, quiet hours, ping budget. | 07:00, 20:30, every 2 h | Working hours only. |
| 11 | **Fill-in card for new logins.** Agents ask through `state/vault-requests.json`; the bridge makes the empty vault item and posts a card. | Live | Works once step 5's service account can write. |
| 12 | **Backup.** Private repo for the template only. Audit before the first push: no secrets in history, personal paths ignored. | `michaelmnorth/personal-coordinator`, private | The company's own git host, under company rules. Never push work content to a personal account. |
| 13 | **Live with it.** Use `/lesson` for every correction for a week. The weekly reflection turns them into proposals. | Ongoing | Same. |

Each new integration after these steps (a fitness app, a coach's sheet, a bank) follows `docs/17-BUILD-PATTERNS.md`:
lean first, its own config file, and its setup steps added here.

## Things that cost time the first time (do them in this order next time)

- **Secrets before anything else.** Every desktop-app prompt during the build came from not having the read-write
  service account yet. Create it in step 5, not later.
- **OAuth client before the vault item.** Create the client in the provider console first, then the vault item with
  exact field names (`client_id`, `client_secret`, `refresh_token`), then sign in.
- **Consent screen in production** needs a home page and a privacy page on a domain you control. GitHub Pages works.
  In Testing mode, refresh tokens expire after 7 days.
- **Mobile first for chat UI.** The Slack Home tab looked good on desktop and cost a tap on the phone. Check every
  screen on a phone before building more of it.
- **Settings that guard the coordinator** (`.claude/settings.json`, `CLAUDE.md`) can only be edited by the person.
  That's intended. Plan for one or two manual edits.

## Not part of the template

- Juno's own phone, number and Gmail (`docs/15`). Personal only. A work coordinator uses company accounts.
- Health and finance (Phases 4a and 4b). Personal only.
