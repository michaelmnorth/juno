# Video breakdown: "The $1M+ Solo Grok Bot Business" (Greg Isenberg with Nick Vasilescu of Orgo)

https://www.youtube.com/watch?v=67BmkptgTms, published 2026-11-02, 49 min. Read 2026-11-08 from the full
transcript (YouTube's own transcript panel, because the transcript tool was IP-blocked) plus the description, the
Bops README and LICENSE, and Paper's docs. Summary in our words; timestamps point to the source.

## The idea in one paragraph
Nick built **Bops** ("business ops"), a team of AI bots in one Mac app, in a 36-hour weekend. Each bot has its own
email, phone number and cloud computer with four screens, and you can reach it by text, call, email, Slack or the
app. The business idea: take a personal-agent platform, specialize it for one industry with the agents pre-built,
and sell it to small businesses. The suggested price is $25k up front for a system they own, plus an optional
$3k-a-month retainer. The part that matters for Juno is how he built it, and the "one agent per platform" habit.

## How he builds (the part to copy)
| Step | What he does | When |
|---|---|---|
| 0. Where | One long thread in T3 Code (Theo's free, open-source coding UI on top of a Claude subscription) with Opus 5.5 on high effort. No GitHub, no branching; loops ran overnight. Claude Code works the same way. | 16:05 |
| 1. Research | His first message: research the products he is cloning (personal-agent apps like Meta's Muse) so the model knows exactly what "this" means before anything is built. He checks the sources it found. | 17:04 |
| 2. Design | With the Paper MCP installed, the agent designs every screen in Paper **before any code**. Plain-English back and forth. **Diverge, then converge:** ask for 3 or 4 variations, pick parts from each, merge. He landed on an iMessage or FaceTime-like look. | 17:49 |
| 3. Stack | Decide the components (computer, phone, email, connectors) and buy rather than build each one. For every feature: "read the docs and the API reference" for that service first. | 22:12 |
| 4. Iterate | Screenshot anything wrong or anything he likes (CleanShot on Mac) and paste it to the agent: "fix this", "make it more like that". Keep a **swipe file** of references. | 24:03 |
| 5. Host and ship | Host on Orgo, Fly or Vercel; ship fast; a two-minute demo video. | 26:43 |

## Tools mentioned
| Tool | What it is | In Bops | For Juno |
|---|---|---|---|
| **Paper** (paper.design) | A design canvas built on HTML/CSS. The desktop app (macOS and Windows) runs a local MCP server at `127.0.0.1:29979/mcp` while a file is open; Claude Code can read and write designs. Free and Pro tiers; exports React. The web version has no MCP. | All UI design | **Yes, try it** for redesigning Juno's Slack cards, brief layout or a future app. Michael installs the app and adds the MCP himself (our no-marketplace rule). |
| **T3 Code** | A free, simple chat UI for coding agents | Where Bops was built | Skip; Claude Code is already this. |
| **Orgo** (orgo.ai) | Cloud Linux desktops for agents, controlled by API, SDK or VNC; you bring the model (Claude computer use and others). Each step takes 1 to 3 seconds. | One computer per bot (4 cores, 16 GB, 4 screens on hosted plans) | Later: the "bot has its own computer" phase, or use the spare PC instead (below). |
| **AgentMail** | Email inboxes by API, priced by volume rather than per inbox, with send, receive, threads and labels | Bot email (`@bops.bot`) | Later: Juno's own address, so Juno writes as itself instead of drafting as Michael. |
| **AgentPhone** | Phone numbers by API: calls and texts through one webhook, with an MCP server and a Claude connector. YC Spring 2026; early. | Call or text a bot | Later: "call Juno from the car" is exactly his use case. |
| **Composio** | One API key gives many app connectors (Slack, Gmail, CRMs) with approval controls | All connectors | Skip for now: Juno uses Claude's own connectors plus fixed scripts. Re-check if we need many apps. |
| **Honcho** | Memory for agents | Bot memory | Compare with Juno's own `me/` + `observed/` design; we already have the learning loop. |
| OpenAI (Responses API, computer tool, Agents API, Codex CLI), TypeSafe (small yes/no checks), treg (business data), Tailscale | Bops' model and plumbing | | Juno stays on Claude. TypeSafe-style yes/no checks equal our cheap-model gates. |
| CleanShot | Mac screenshot tool | Feedback loop | Windows: Win+Shift+S works; paste into Claude Code. |

## Bops repo (github.com/OrgoAI/bops)
- **Needs:** an Apple-silicon Mac with Node 22+, an Orgo account, an OpenAI key, and a second OpenAI key with a
  spend limit. Self-hosting is `BOPS_SELF_HOSTED=1` with keys in `.env.local`. Commands: `npm run setup`, then
  `npm run app` (a local server on port 3210).
- **Electron + Next.js; OpenAI only.** Juno runs on Windows and Claude, so forking it does not fit this PC. Read
  it for patterns instead: per-bot computers, phone and email webhooks, the relay for public webhooks.
- **License:** FSL-1.1 (Apache 2.0 after two years). Personal and internal use is fine; a competing hosted
  product is not. Relevant only if the venture ever sells something like it.
- **Free tier vs the pitch:** the video says every bot has its own computer, email and phone. The README says
  Free and Pro share one computer, and only the main bot gets email and phone, on paid plans.

## Ideas worth taking for Juno
1. **Design first in Paper:** research, then 3 or 4 design variations, then merge, before any code. Worth
   redoing the Slack cards, the morning brief layout and any future Juno app this way. Michael is open to redoing
   the design phase.
2. **One agent per platform** (14:00): an agent that owns a platform, stays logged in and runs routines there.
   Juno already does this by domain (Sorter for Gmail, Tempo for Calendar, Rewind for YouTube). Platform owners
   for LinkedIn or X belong to the venture phase.
3. **Its own identity:** an email, a phone number, a computer (see below).
4. **Swipe file:** a `domains/admin/swipe/` folder of screenshots and references Michael likes, which design and
   draft runs can draw on.
5. **"Read the docs and the API reference" before every integration:** already our habit; make it a standing
   line in the new-subagent skill.
6. **Venture angle** (for `domains/business/`): sell a specialized agent team, priced as a system the client owns
   plus an optional retainer. Sweeten it with a website or lead-magnet tool built quickly. For the first niche,
   call 50 people you know, do one build free, and trade the case study for referrals (40:21).

## The second computer (Michael's question)
Yes, as a later phase, and the spare PC beats paying for cloud desktops. What it buys:
- **Isolation, not more power.** Juno logs into its own accounts on that machine: its own Gmail, an AgentPhone
  number, a browser profile. It gets **delegated** access to Michael's things (Gmail delegation, a shared
  calendar), never his passwords. If the bot machine is ever tricked, his own PC, 1Password and bank stay out of
  reach.
- **Always on,** so the bridge, webhooks for calls and texts, and computer use no longer depend on this PC being
  awake.
- **Rules that stay:** the same tiers and approval cards apply. "Full control of its own computer" must not mean
  sending, paying or signing as Michael. Juno writes as "Juno, Michael's assistant", which is honest to recipients
  and fine under Google's terms for a separate account.
- **Order:** finish Juno's phases here, then move the bridge to the spare PC, then add Juno's own email, then a
  phone number.

## Sources
- Video and description: https://www.youtube.com/watch?v=67BmkptgTms
- Bops README and LICENSE: https://github.com/OrgoAI/bops
- Paper: https://paper.design/llms.txt, https://paper.design/docs/mcp
- Composio on Bops: https://composio.dev/built-with/bops-by-orgo
- Orgo docs: https://docs.orgo.ai/introduction.md
- AgentMail: https://www.agentmail.to/docs/introduction ; AgentPhone: https://ycombinator.com/companies/agentphone
