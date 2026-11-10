# Bops vs Juno: compare, contrast, decide (2026-11-08)

Source: the Bops repo (github.com/OrgoAI/bops, v0.0.50), read in full by a helper agent; key claims spot-checked
against the code. Nothing was run. See docs/10-VIDEO-BOPS.md for the video.

## Should we fork Bops?
**No, borrow from it instead.** The reasons, in order:
1. **Platform.** It is a Mac (Apple silicon) Electron app. Juno runs on this Windows PC and lives in Slack on
   Michael's phone, which is how he actually uses it (voice-dictated messages from the car).
2. **Engine.** Bops runs on OpenAI (Responses, Agents, Codex) with six paid providers: Orgo, OpenAI, Honcho,
   Composio, AgentMail, AgentPhone, plus TypeSafe. Juno is Claude on his subscription plus a few fixed scripts.
3. **Size.** About 1,000 files; single files of 4,000 to 5,600 lines. Forking means owning all of it.
4. **License.** FSL-1.1 allows personal use, but a future business product built on it could count as competing.
   Borrowing ideas carries no such limit.
5. Juno is already ahead where it matters most for a personal assistant: it is built around his life, with code
   enforcing what the model may do.

## Side by side
| Area | Bops | Juno today | Verdict |
|---|---|---|---|
| Shape | Chief-of-staff bot plus a team chart; bots hand work down (`hand_off`, up to 4 parallel tasks) | Coordinator plus specialist subagents; everything flows through Juno | Same idea. Ours is simpler, which is right for one person. |
| Where you talk to it | Mac app; also Slack, Telegram, Discord, phone, email; routed by which bot owns the address | Slack DM | Bops is richer. Phone and email are the later "own identity" phase. |
| Memory | Honcho bank; facts saved without being asked, shown as "Remembered … Undo"; "this replaces an older fact?"; 8 categories (People, Tasks, Events, **Promises**, Companies, Projects, **Decisions**, Preferences); secrets kept to one bot; private lines kept out of prompts | `me/` (confirmed), `observed/` (silent, with confidence and aging), `people/` profiles | **Ours is stronger on honesty** (confidence, aging, trust). **Theirs is stronger on visibility** (Undo at the moment of learning). Borrow the Undo line and the Promises and Decisions categories. |
| Proactivity | Routines (daily, weekly, before an event, every N minutes in hours); `NOTHING` means silent; a "now / quiet / later" rating against what you are doing; a batched "While you were busy" digest; diff-based watches | Timers, sweep verdict JSON, quiet hours, daily cap, holding file batched into the brief | Close. **Borrow "now / quiet / later"** (ours is effectively notify or hold) and the "While you were busy" wording. |
| Approvals | Allow once / Always / Deny per bot per action; **the card's facts line is written by the system, never by the bot**; no Always for writes from tasks that read web pages; money always asks | Allow once / Always / Deny; one tool granted per approval; hooks check the call; trust labels hide Always for strangers | Both strong. **Borrow system-written card facts.** |
| Reply safety | A draft can only go to a thread the turn read, and only to addresses in real headers, never one written in the body | Only the approved draft and recipients can be sent (hook) | **Borrow "only addresses from headers"** for drafts Quill makes from mail. |
| Who counts as the owner | Email from the owner only if DMARC passes; texts only from his numbers; a pairing code per channel | Slack allowlist; mail from his address is still just mail | Ours is safer for now. Adopt DMARC when Juno gets its own inbox. |
| Skills | Skill-change proposals as diff cards with their source; versioned skills with rollback; "Save as skill" from a chat | `new-subagent` and installer with tests and rollback; lessons as cards | **Borrow diff cards** for skill changes (the Rewind and reflector ideas). |
| Asking questions | The bot ends with `Options: a / b / c`, shown as buttons | Free text; wrap-up buttons only in this app | **Borrow it:** an Options line becomes Slack buttons. Cheap and big for phone use. |
| Writing style | Mostly Simplified Technical English; 1 to 3 sentences; tests fail on em dashes | Plain words, no em dashes (Michael's preference), Juno's dry voice | Same instinct. Borrow the test that fails on dashes. |
| Cost | Spend-capped key; credit checked per turn | Per-job turn and dollar caps; cost log | Ours is finer-grained. |
| Computer use | 4 screens per VM, a screen ledger, hand-off to the human on sign-in, 2FA or captcha | None yet | Later, with the spare PC. Their blocker hand-off is the pattern to copy. |
| Weak spots | One outside yes/no service decides risk, memory and attention; "Just do it" sends without asking; the VM is fully trusted; no aging on memory | Fewer channels, no app UI, no computer use | |

## What to borrow (new proposals; Michael picks)
| # | Idea | Effort |
|---|---|---|
| 11 | **Options buttons:** when Juno needs an answer, it ends with `Options: a / b / c`; the bridge turns them into Slack buttons that reply for him | S |
| 12 | **System-written card facts:** the bridge writes the card's facts line itself (who it reaches, what it changes, trust label), never Juno's summary alone | S |
| 13 | **"Remembered … Undo":** when Juno saves a silent note during a chat, one quiet line with an Undo button; "replaces an older note?" when it conflicts | S |
| 14 | **now / quiet / later** for sweep items, with "While you were busy" as the batched digest after meetings (calendar-aware) | S |
| 15 | **Drafts only to header addresses:** Quill may reply only to addresses from real From, To and Cc headers of the thread it read | S |
| 16 | **Promises and Decisions** as observed/ categories: what Michael promised people and what was decided, fed into the handoff note and the brief | S |
| 17 | **Skill-change diff cards:** proposed changes to a skill or agent show as a diff with the source (video, lesson), Accept or Skip | M |
| 18 | **Juno home:** a Bops-style app view (people, threads, what is waiting, what Juno learned) as a Slack App Home tab first | M |
| later | Own email (AgentMail or a Gmail account with DMARC owner checks), phone (AgentPhone), computer (the spare PC, with the blocker hand-off) | L |

## The design restart
Do it, in Paper, starting from research, as Nick did:
1. **Research** (this file plus docs/10): what Bops gets right in the interface (an iMessage-calm chat, a bot row
   with mood, "Remembered … Undo", Options buttons, "While you were busy") and what Juno must keep (Slack on the
   phone, cards, trust labels).
2. **Design** the surfaces in docs/11-DESIGN-BRIEF.md, diverge then converge, now including 11 to 14 and 18.
3. **Build** what was chosen, one surface per commit, with tests.
The engine underneath (bridge, hooks, tiers, learning loop) stays; the redesign is the surfaces and the
conversation patterns. The same split applies to the work coordinator later (docs/09).
