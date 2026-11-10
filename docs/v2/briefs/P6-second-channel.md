# Brief P6 · Second channel

**Optional. Hand this to a Claude Code session after Phase 3 has exited.** Read the channel adapter section of `02-ARCHITECTURE.md` and D8 in `01-DECISIONS.md`.

## Goal

One more way to talk to Juno from a phone, added as an adapter, with approvals working end to end. Slack stays primary.

## Platform rules as of 2026-11-09

Verify before building; these changed during 2025 and 2026.

| Channel | Status for a single-owner assistant | Notes |
|---|---|---|
| **Telegram Bot API** | Allowed. Official and free | `getUpdates` long polling needs no inbound port. Inline keyboards for approvals. Voice notes in. About one message a second per chat. Bot chats are cloud chats, not end-to-end encrypted. Anyone can find a bot by username, so the bot must check the sender's numeric ID |
| **WhatsApp Business Platform** | Closed in the US | Meta's terms §4.7 bar AI providers, including general-purpose assistants, from the platform when the assistant is the primary function, "as determined by Meta in its sole discretion". WhatsApp's platform terms require business use, "not for personal use". Exemptions exist only where regulators required them (EEA countries, Brazil, Türkiye). Even where allowed: free-form messages only within 24 hours of the owner's last message, templates otherwise, per-message fees, a public webhook |
| **WhatsApp consumer account, automated** | Not allowed | The Terms of Service bar "bulk messaging, auto-messaging, auto-dialing, and the like" and allow termination "anytime for any reason". 2026 reports describe new dedicated numbers restricted within hours. Do not build this |
| **SMS** | Allowed, heavy | Carrier registration applies even to individuals; no buttons |
| **iMessage, Signal** | No official personal bot API | Do not build on unofficial clients |

**Default: Telegram.** If the owner wants WhatsApp, the answer is to re-read Meta's terms then, not to work around them.

## Deliverables

1. **Adapter interface finished.** Anything Slack-specific that leaked into core moves behind `ChannelAdapter`. Capability flags (buttons, threads, edits, files, voice) drive rendering.
2. **Telegram adapter:** long polling; an allow-list of exactly the owner's numeric user ID, with every other sender dropped, logged and never answered; approvals as inline keyboards whose callback data carries only the proposal ID; cards edited in place when resolved; files and photos in; link previews disabled on every message; send rate limited.
3. **Approval fallback** for channels without buttons: numbered text replies bound to the proposal ID and expiry.
4. **Routing rules in the profile:** which channel receives pings, failover when a send fails, and no duplicate pings across channels.
5. **Per-channel data rules:** a profile setting that keeps chosen data classes off a channel. Default for Telegram: no finance and no health detail, because bot chats are not end-to-end encrypted.
6. **Forwarded content is untrusted.** A message the owner forwards, or a file the owner attaches, contains other people's text. It enters as untrusted free text and taints the run. Text the owner types is the owner's.
7. **Voice notes** (optional; ask the owner): transcription in a `reader`-class call, with the transcript treated as the owner's words.
8. **Tests:** a stranger's message; a tap from a stranger; a replayed callback; failover; the data-class rule; a forwarded injection.

## Done when

- A proposal created from either channel can be approved on either channel exactly once.
- Messages and taps from any other account are ignored and logged.
- A week of real use with no duplicate or lost pings.
- The red-team suite passes with the new adapter enabled.

## Guardrails

- Official APIs only. No unofficial clients, no automation of a consumer account, no phone farm.
- The bot token lives in the vault. It never appears in a prompt or a log.
- Do not move approvals for sensitive actions to a channel with weaker identity guarantees without the owner's decision.
- If platform terms have changed since this brief was written, record the change in `01-DECISIONS.md` before building.

## Report back

What moved out of core, which Slack features have no equivalent, the per-channel data rules as configured, and a week of delivery statistics.
