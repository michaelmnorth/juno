# gateway/ : the Slack bridge

A small Socket Mode bot in Michael's free Slack workspace. It is the only way Juno reaches his phone and the only way
he talks to Juno outside the Code tab. It is outbound-only, answers one allowlisted user, and runs the real
`claude -p` on the subscription inside the coordinator folder, so every rule in `CLAUDE.md`, `.claude/settings.json`
and the hooks applies to every run.

## One-time setup (Phase 1, tasks 1-3)

1. **Slack app.** api.slack.com/apps → Create New App → From a manifest → your workspace → paste
   `slack-app-manifest.yaml` → Create → Install to Workspace. Copy the **Bot User OAuth Token** (`xoxb-...`).
   Basic Information → App-Level Tokens → Generate, scope `connections:write`. Copy it (`xapp-...`).
2. **Your user id.** Slack → your profile → three dots → Copy member ID (`U...`). Put it in
   `me/notify-allowlist.json` under `"slack"`.
3. **Secrets.** 1Password: vault `Agent-Secrets`, item `Slack-Juno`, fields `bot_token`, `app_token`. Then
   `copy gateway\slack.env.example gateway\slack.env`. The `.env` holds only `op://` references.
4. **Python deps.** `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r gateway/requirements.txt`.
5. **Prove the Claude round trip first**, no Slack involved:
   ```
   .venv\Scripts\python gateway/slack_bridge.py --once "What can you do?" --dry-run
   .venv\Scripts\python gateway/slack_bridge.py --once "What can you do?"
   ```
   The second one runs `claude -p` in this folder. If `claude` is not on PATH, set `CLAUDE_BIN` in `slack.env`.
6. **Start the bridge:**
   ```
   op run --env-file=gateway/slack.env -- .venv\Scripts\python gateway/slack_bridge.py
   ```
   DM the Juno app in Slack. `/new` (typed as a message) starts a fresh Claude session; otherwise the DM keeps one
   session for 12 hours of use.
7. **Run at logon.** Task Scheduler → Create Task → trigger "At log on" → action: program `op`, arguments
   `run --env-file=gateway/slack.env -- .venv\Scripts\python gateway/slack_bridge.py`, start in this folder. Leave "Run whether user
   is logged on or not" unchecked (`claude` needs your session). Settings → "If the task fails, restart every 1 minute".

## Always on, with no 1Password prompts

Steps 3, 6 and 7 above were the first setup. The bridge now uses a 1Password service account limited to the
`Agent-Secrets` vault, read and write since 2026-11-08 so it can make empty items for the fill-in card. Its key is in Windows Credential Manager, and the bridge fetches the Slack tokens at startup.

1. `.venv\Scripts\python gateway\token_store.py --store-op-token` saves the key. The prompt hides what you paste.
2. `.venv\Scripts\python gateway\token_store.py --check` confirms it works, printing only pass or fail.
3. `powershell -ExecutionPolicy Bypass -File gateway\install_task.ps1` registers the hidden logon task, which also
   checks every 5 minutes and restarts the bridge if it stopped.

The log is `logs/bridge.log`. New secrets go in the `Agent-Secrets` vault in 1Password, never in chat or a file.

## What runs on timers

`me/proactivity.yaml` anchors become cron jobs: morning brief, evening check-in, the sweep (every N minutes inside the
window, silent when the coordinator answers `NOTHING_TO_REPORT` or during quiet hours), weekly reflection. Each runs
`claude -p` with `COORDINATOR_UNATTENDED=1` (so the memory-write hook blocks `me/` and `learnings/` writes) and
auto-memory disabled.

The coach sheet has no Hevy webhook to lean on (Hevy's API has none), so `hevy_watcher` stands in: every
`hevy_check_every_minutes` inside `hevy_check_window` it pulls Hevy without the model, and only when a saved workout
isn't on the coach's sheet yet (`tools/sheets.py plan` says so) runs the `coach-sheet` job. `coach_sheet_nightly` runs the
same check once more whether or not Hevy changed. A lock keeps the two from overlapping.

## Approvals

When the coordinator needs a T3 action it appends `{"summary", "action", "session_id", "status": "new"}` to
`state/pending-approvals.json` (the `Approvals.add()` helper or the JSON shape in `state_store.py`). The bridge posts a
card with Approve / Deny; the tap resumes that session with the decision. Text fallback: there is none on purpose;
a typed "yes" is not an approval, a tap is.

## Known limits (Phase 1)

- The PC must be on and awake, with Michael signed in to Windows. `state/last-run.json` is the heartbeat for the desktop scheduled task.
- Whether `claude -p` sees the Gmail/Calendar connectors is unverified; if it does not, Phase 2 adds `tools/gmail.py`
  and `tools/gcal.py`.
- Hook `defer` is not wired yet (Phase 3); gating today is deny rules plus the approvals file.
- Tested offline only (`python -m pytest tests/ -q`). The first live run is Michael's.
