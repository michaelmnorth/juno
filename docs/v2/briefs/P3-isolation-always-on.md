# Brief P3 · Isolation and always-on

**Hand this to a Claude Code session after Phase 1 has exited** (Phase 2 can run before or alongside). Read `05-SECURITY.md` in full and the run-class, taint and layout sections of `02-ARCHITECTURE.md`.

## Goal

Juno runs on a dedicated always-on host in a container with no inbound ports and an egress allow-list, off the owner's daily PC. Scheduled work moves to the new lanes. Detection becomes event-driven. The security controls are enforced and tested.

## Owner decisions needed before starting

- Which host: a small home machine or a small cloud VM (`01-DECISIONS.md` D7).
- Backup target and retention.
- The alert channel for the heartbeat monitor.

## Deliverables

1. **Code and data separated on disk:** the instance directory at `$JUNO_HOME/<instance>/`; the runtime refuses to start if personal data is found inside the code tree.
2. **Container image:** non-root, read-only filesystem, one data mount, pinned dependencies with hashes. One command to start, stop, upgrade and roll back.
3. **Network:** no inbound ports; egress limited to the named hosts in the profile; remote admin over a private overlay network.
4. **Pollers** replacing two-hour model sweeps for detection: Gmail history IDs every one to two minutes, Calendar sync tokens every few minutes, the existing workout check. A model runs only on a relevant change.
5. **Scheduled jobs on the new lanes:** brief, check-in, triage and drafts as L0 gathering plus one L1 call; `reader` for each item that needs reading; `compose` for drafts.
6. **Run classes and taint enforced for every lane,** including `research` through server-side web tools with caps and domain filters, and no private context.
7. **Approval protocol** verified against `05-SECURITY.md` §3, with the tainted-run marker on cards.
8. **Channel output rules:** unfurl off; inert links from tainted runs.
9. **Audit log,** heartbeat, daily "did without a tap" list in the check-in.
10. **Backups** from the new host and a restore drill onto a clean machine.
11. **Red-team suite** in CI and as a weekly job against the live configuration.
12. **Runbook:** start, stop, pause, upgrade, rotate each credential, restore, and what to do in an incident.
13. **Retire `claude -p` from the runtime.** The subscription login is no longer needed on the host.

## Done when

- **14 days unattended with the old PC off.** The brief arrived by 07:05 on at least 13 of them.
- Red-team suite passes 100%.
- Median time from an urgent email arriving to the owner being told is ≤ 5 minutes outside quiet hours.
- Restore drill completed on a clean machine, timed, and written into the runbook.
- No runtime path invokes `claude -p`, a shell, or a file tool. A test asserts it.
- The egress test shows a request to an unlisted host is dropped.

## Guardrails

- Never weaken a control to make a test pass. If a control blocks something the owner needs, record it and ask.
- The build session works on the code repo with synthetic fixtures. It does not copy the instance directory or its credentials anywhere. The owner performs the data move with the runbook.
- Do not add an overnight coding agent in this phase.
- Keep v1 able to run on the old PC until the 14-day gate passes, then switch it off.

## Report back

Uptime and brief-on-time numbers, detection latency, red-team results, restore time, the egress allow-list as shipped, and any control that could not be implemented as written.
