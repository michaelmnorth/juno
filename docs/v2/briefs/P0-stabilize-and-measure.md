# Brief P0 · Stabilise and measure

**Hand this to a Claude Code session opened in the existing Juno repo.** Read `00-START-HERE.md` and `01-DECISIONS.md` first, then `03-CONTEXT-AND-COST.md` and `05-SECURITY.md`.

## Goal

Before anything is rebuilt: know exactly what v1 is and where its tokens go, close the cheap high-risk gaps, and stop adding surface. No refactors in this phase.

## Why first

The kit was written from the System Map without the code. Every later phase depends on facts this phase establishes. The measurements also decide how much of Phase 1 is necessary.

## Deliverables

1. **`docs/v2/AUDIT.md`.** For each item: confirmed, differs (say how), or unknown.
   - How the bridge invokes Claude: exact flags, model per job, cold start or resumed session, where transcripts live.
   - Size in tokens of everything loaded before the owner's words: system prompt and built-in tools, CLAUDE.md, profile and lesson files, skill and agent listings, MCP tools.
   - The 11 agents and 9 skills: what each loads, which tools it has, which model.
   - The 18 tool scripts: API scopes used, which write, which return other people's text.
   - Hooks and deny rules: what each enforces.
   - Approvals: is a pass bound to the exact payload, who executes, expiry, replay handling.
   - State files: who writes them, any locking, what happens when a timer and a DM overlap.
   - What is in git, what is ignored, what is backed up, where secrets could leak into logs.
   - Test layout and how tests run.
2. **A token ledger for v1.** Per run: model, input, output, cache write and read, per subagent, cost. Collect at least 50 owner DMs or 7 days. End with one page: the top three places the tokens go, with numbers.
3. **Quick fixes, each with a test.**
   - All bot messages sent with link and media unfurling off.
   - Approvals execute a stored payload bound by hash to what the card showed (implement if missing).
   - `pause` and `resume` handled in the bridge with no model, plus a flag file.
   - External heartbeat with a phone alert when the bridge stops.
   - Encrypted off-box backup of the personal files that are not in git; restore tested into a scratch folder.
   - A daily spend cap in the bridge.
   - Test discovery fixed from the repo root; CI runs the suite on every push.
   - The map's own loose ends: lesson saves from Slack queue and save on tap; retire Ping; pin or remove Tempo's missing engine.
4. **Interim cost relief** (config only): owner DMs default to Sonnet 5.5 at low effort; confirm which model each alias resolves to and pin exact IDs.
5. **Signal capture starts.** Record draft outcomes, approval outcomes and ping outcomes as rows now. Phase 4 needs the history.
6. **`docs/v2/THREAT-MODEL.md`** adapted from `05-SECURITY.md` to what the audit found, with source links confirmed.
7. **Freeze note** in the plan doc: no new agents, skills or loops until Phase 1 exits. Exceptions: fixed-text reminders for the owner's dated deadlines, and the quick packs in `08-ROADMAP.md`, built as code plus at most one lean call with no tools.

## Added after the audit (2026-11-10)

The first audit list changed the kit (`09-AUDIT-CORRECTIONS.md`). These items join the quick fixes, each with a test. Do the first one before anything else.

1. **Backups.** The audit found none. Encrypted, off-box, covering the personal layer and the session transcripts; restore tested into a scratch folder. The owner runs the step that touches real data.
2. **Web tools out of runs that hold mail text or private memory.** Web tools only in the research agent, which receives a question and nothing else.
3. **Remove unrestricted Bash from the YouTube agent's tool list.**
4. **One state-writing run at a time per instance,** enforced in the bridge, until Phase 1's event queue replaces it.
5. **A per-run cost cap in the bridge** from the corrected per-run figure. The CLI budget flag does not stop a single expensive call.
6. **Remove or stub references to scripts that do not exist** (scheduling engine, `finance_query.py`, `health_*`, `withings_*`, `notify.py`).
7. **Build rules** go to `docs/v2/BUILD-RULES.md`, not into `CLAUDE.md` (decision O9; the owner confirms).
8. **Ledger:** split the fixed prefix (about 41K tokens) into harness, tools, connectors and listings with the token counting endpoint, and re-measure DM cost on Sonnet at low effort.

## Done when

- `AUDIT.md` has no "unknown" on anything Phase 1 touches (invocation, tools used by DMs, approvals, state).
- The ledger covers ≥ 50 DM runs and names the top three token sinks.
- Tests for every quick fix pass; the backup restored; CI is green from the repo root.
- The owner has read the audit's "differs" list and the kit's affected sections are annotated.

## Guardrails

- Do not restructure code, rename things or change behaviour beyond the list above.
- Do not read or print personal files beyond what the audit needs; sizes and shapes, not contents.
- Where the repo contradicts the kit, stop and record it. Do not adapt silently.
- If the ledger shows DM cost is already low for a reason the kit missed, say so; Phase 1 may shrink.

## Report back

The audit's "differs" list, the three token sinks with numbers, which quick fixes were already in place, and any decision in `01-DECISIONS.md` the evidence argues against.
