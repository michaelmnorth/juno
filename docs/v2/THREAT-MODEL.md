# Threat model · Juno v1 as audited (P0, 2026-11-10)

Adapted from `05-SECURITY.md` to what `AUDIT.md` found. Goal unchanged: hostile mail, pages, invites or
transcripts can waste Juno's time and can never make Juno act, leak or remember.

## Assets and where they are

| Asset | Where in v1 | Protection today |
|---|---|---|
| Mail, calendar, contacts, coach sheet | Google, one OAuth app (`gmail.modify`, `calendar.events`, `contacts.readonly`, `spreadsheets`) | Typed scripts in `tools/`; connector write tools denied; outward gate hook |
| Memory and preferences | `me/`, `people/`, `observed/`, `learnings/`, `domains/` inside the repo, git-ignored | Memory-write hook; **no backup** |
| State, approvals, ledger | `state/`, git-ignored | Atomic JSON writes for some files; **no backup** |
| Session transcripts (full DM history) | `~/.claude/projects/<repo>/` | None beyond the user account; **no backup** |
| Credentials | 1Password vault through a service-account key in Windows Credential Manager | Never in prompts or files; `op read` and env listings denied |
| The PC | Owner's daily Windows PC, runs as the owner | None specific to Juno |

## Adversaries, most likely first, and what v1 holds against each

1. **Honest model error** (wrong recipient, date, fact). Holds: every outward action needs a tap; the card is built in
   code from the entry; recipients come from code-checked trust labels. Gap: the model writes the entry (DV4).
2. **Untrusted text** (mail, web, invites, transcripts). Holds: Sorter has only Read and gets cleaned text; unknown
   senders get no profile notes; links and attachments from unknown senders are never opened (instruction, not
   code). Gaps: a DM run can read mail text, private memory and use WebFetch in the same run with no tap (the
   trifecta); Read/Glob/Grep reach any file the account can; "treat as data" is a prompt rule, not a boundary.
3. **Persistence.** Holds: `me/ learnings/ people/` need the owner present. Gap: `observed/` is written silently by
   any run, including ones that read mail, and is loaded into later runs.
4. **Supply chain.** Holds: plugin and MCP installs denied; new agents need a tap and install in code. Gap:
   dependencies not pinned with hashes; claude.ai connectors load in every run.
5. **Loss.** Gap: no backup of anything outside git.

## Controls: v1 state after P0

| # | Control (05) | v1 after P0 | Test |
|---|---|---|---|
| 1 | No general-purpose capability | **Not met.** Claude Code harness with shell (allow-listed to `python tools/*`), file read, web fetch | hooks tests |
| 2 | Run classes and taint | **Not met** (P1) | — |
| 3 | Approval protocol | **Partly.** Email: payload hash on post, checked on tap, sent in code only if the draft still matches, single-use, owner identity only. Calendar: one-time token bound to class and recipients. Proposals still model-written | `tests/test_approvals_v2.py` |
| 4 | Egress | **Partly.** Unfurling off on every bot message. No network allow-list; WebFetch from any run | `test_bot_messages_never_unfurl` |
| 5 | Memory integrity | **Partly.** Confirmed layer gated; `observed/` open | `tests/test_hooks.py` |
| 6 | Secrets | **Mostly.** Vault plus service account; no log scrubber; one broad Gmail scope | — |
| 7 | Host | **Not met** (P3): daily PC, owner's account, Windows | — |
| 8 | Stopping it | **Met in code.** `pause`/`resume` and `state/PAUSED` stop DMs, jobs and approvals with no model; $3/day cap; external heartbeat once its URL is stored | `tests/test_gateway.py` brakes tests |
| 9 | Audit | **Partly.** `state/audit.jsonl` for approvals; no per-tool-call log | — |
| 10 | Backups | **Not met.** Owner to choose target and tool | — |
| 11 | Data minimisation | **Partly.** Sorter packets are cleaned text; transcripts keep everything | — |
| 12 | Supply chain | **Partly** | — |
| 13 | Self-change | **Partly.** CLAUDE.md and `.claude/` denied in Juno's runs; the proposed self-modification loops are not built (keep it that way until P3) | `tests/test_hooks.py` |

## Red-team fixtures that exist today

Payload changed after the card (refused), replayed tap (refused), tap from another Slack user (ignored), draft
text or recipients changed in Gmail (not sent), bot message with an image URL (no unfurl), `pause` (nothing runs).
Still to write: injected email, link with a canary in the query, hidden-text page, invite asking to add an
attendee, transcript asking for an instruction change, secret-shaped string in a tool result. They need P1's run
classes to be meaningful.

## Sources

Carried from `05-SECURITY.md` (opened by the review session 2026-11-09; not re-opened in P0, so "confirmed" here
means confirmed against the code, not re-checked online):

- Simon Willison, [The lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (2025)
- Meta, [Agents Rule of Two](https://ai.meta.com/blog/practical-ai-agent-security/) (2025), and Willison's
  [caveat](https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/)
- Willison, [The dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/); Google DeepMind,
  [CaMeL](https://arxiv.org/abs/2503.18813) (2025)
- Anthropic, [How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude) (2026) and
  [prompt-injection defences](https://www.anthropic.com/research/prompt-injection-defenses) (2025)
- Meta, [How we built safety into Muse](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) (2026)
- Microsoft, [Running OpenClaw safely](https://microsoft.com/en-us/security/blog/2026/02/19/running-openclaw-safely-identity-isolation-runtime-risk) (2026)
- [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)
