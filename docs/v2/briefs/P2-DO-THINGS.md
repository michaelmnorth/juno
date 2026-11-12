# P2 brief: "do things", parity with a one-shot assistant session

Written 2026-11-12. Execution happens in its own session; this file is that session's brief.

## Why

Michael's other assistant took one problem (a photo of an appliance label) from diagnosis to a submitted
manufacturer claim in four messages: it read the serial off the photo, researched the known fault, checked prices
on the product page itself, found the purchase date in his mail, filled in and submitted a web form, tracked the
shipment, and emailed itself a write-up. The full breakdown is a Markdown file Michael keeps outside the repo, in
his Downloads folder. Ask him for it; it holds personal details and never goes in the repo.

When he asked Juno to review that email, the run failed:

- The lighter engine (v2) took it as `mail.read`. Its reader returns typed fields only and cannot open
  attachments. It saw a one-line gist and asked him to paste the file instead of handing off.
- The reader flagged the email as `suspicious`, because the email describes tools and asks for a transcript. That
  is the injection guard working, but the run should still have handed off: Michael's own request was the
  instruction, not the email.
- Its reply said it "fired off a send request by mistake". No send tool call appears in the audit log, so either
  the model called a tool outside its playbook (which errors and is not audited) or it made the claim up. Find out
  which.
- Even v1 could not have done the job end to end. It has no browser, no attachment reader, no follow-up tracking,
  and cannot attach a file to an email.

## Capability map

| # | What the session did | Juno today | Gap and lean fix |
|---|---|---|---|
| 1 | Read a photo: model, serial, refrigerant line | v1 reads the saved photo. v2 sees only "[He attached a photo]" | v2 sends the image as an image block (DM photos only, size-capped), or hands off when a photo is attached. Start with the handoff, which needs no new code path. |
| 2 | Searched its memory before acting | `notes_search`, `people/` | New `domains/home/` (CONTEXT.md plus a private facts file: appliances, models, serials, purchase records), so "the washer" resolves next time. Facts are written before the reply. |
| 3 | Ran web searches in parallel and read the source pages | v1: WebSearch, WebFetch, and `researcher` | v2 has none. Add Anthropic's server-side `web_search` (about $10 per 1,000 searches, `max_uses` 3) and `web_fetch` (tokens only) to a new `research` playbook. The run is tainted after any result. |
| 4 | Found and checked a how-to video, chapters included | `youtube` agent, `tools/youtube.py` | Covered. Route "find a video" there from v2 by handoff. |
| 5 | Checked price and stock on the product page, never from a snippet | Nothing | New `shopping` skill: read the price on the product page itself, prefer the maker's own store, match the exact part number, and look for free, recall or warranty programs first. |
| 6 | Mail forensics: tried queries from narrow to broad, read the order confirmation in full | v1: Gmail connector. v2: typed fields only | Add `merchant`, `order_number`, `order_date`, `items` and `delivered_on` to the v2 reader schema. A "find when I bought X" playbook loops through queries. |
| 7 | Opened an emailed attachment (this .md) | Nothing in either engine | `tools/gmail.py attachments --message <id>` saves the text, PDF and image attachments of mail from `michael` or `known` senders to `state/attachments/` (git-ignored) and returns paths. Never for `unknown` senders (existing rule). PDFs become text with `pypdf`. |
| 8 | Read a file sent in chat | Discord: photos only. Other files are "can't open" | Save .md, .txt, .pdf and .csv from the Discord CDN (same host allowlist and size cap as photos) and pass their paths like photos. |
| 9 | Filled in and submitted a web form (a claim) with a browser agent | No browser | A new `browser` subagent, "Hands", with Microsoft's Playwright MCP server in its own persistent profile (`--user-data-dir` under Juno's folder, never his Chrome), loaded only for that agent's runs through `--mcp-config`. See Browser below. |
| 10 | Tracked a pending outcome (a shipment) | Reminders only | `tools/followups.py add/list/close` with an "expect by" date and what would close it. The sweep matches shipping and delivery mail against open follow-ups, and the morning brief lists overdue ones. |
| 11 | Emailed itself the write-up as an attachment | `send-self` has no attachments | `gmail.py draft --attach <path>` (paths inside the project only, under 10 MB). `send-self` stays self-only. |
| 12 | Sent an interim "found it, submitting now" message, and the result later | The bridge posts the final reply only | Long v1 runs post one progress line after about 60 seconds (the bridge already has the "delivery took" timing). Optional. |
| 13 | Said, in plain words, what it would do and did it | v2 asked him to paste the file | Router and constitution: "can't open it" or "needs the web or a form" means `hand_off`, never "paste it here". Add a dialogue eval for this exact case. |

## Browser: why Playwright MCP, and how it's gated

- **Options weighed:**
  - **Claude in Chrome (`--chrome`):** acts in his real Chrome with his sign-ins, which he ruled out. It is also
    unclear whether it works under `-p`.
  - **The built-in browser pane:** a desktop app feature only, which headless bridge runs can't reach.
  - **The computer-use API:** heavy and costly.
  - **Microsoft's `@playwright/mcp`:** runs its own Chromium, `--headless` for unattended runs,
    `--user-data-dir` for a separate Juno profile, and accessibility snapshots instead of screenshots (cheap in
    tokens). This one is recommended.
- **Install:** Michael adds it himself (guardrail: no MCP installs by Juno, and `claude mcp add` is denied).
  The session writes `gateway/mcp/browser.json` and the agent file, then gives him the one command to run.
- **Scope:** only the `browser` agent's run gets `--mcp-config gateway/mcp/browser.json`. Every other run keeps
  `--strict-mcp-config` lean, so no extra tool prefix tokens elsewhere.
- **Tiering:**
  - Reading a page is T0.
  - Filling fields without submitting is T1.
  - Submitting a form, creating an account, or entering his name, address, phone or email is T3. A new
    action class, `web.form.submit`, requires a card that shows the site, the fields and the values, unless his
    own DM explicitly asked for that submission on that site ("submit that LG form for me"). That message is the
    explicit yes, as the automation tiers already allow.
  - Never passwords, card numbers or IDs. No purchases: a checkout page ends the run with a link for him (T4
    spirit).
  - Only sites his DM named, or ones Juno found and he approved on the card.
- **Proof:** the agent returns the confirmation screen's text (a ticket number), and success is claimed only on
  that. One screenshot goes to `state/browser/` for the log.

## Order of work (one session, small commits, tests first)

1. **Diagnose today's failure.**
   - Confirm whether the "send request" was a call to an out-of-playbook tool.
   - Audit every refused or unknown v2 tool call (`v2_tool_refused`).
   - Add the dialogue eval "review the attachment in my email" and expect `hand_off`.
2. **Attachments** (#7, #8), including the Discord file save. Tests use fake Gmail and Discord payloads.
3. **v2 hand-off fixes** (#1, #13): an attached photo or file means hand off. Add the reader schema fields
   (#6).
4. **Home domain and follow-ups** (#2, #10), including the morning brief and sweep hooks.
5. **v2 research playbook** with server-side web search and fetch (#3). Cost goes in the ledger (`searches`
   already exists).
6. **Shopping skill** (#5) and `--attach` (#11).
7. **Browser agent** (#9): the agent file, MCP config, `web.form.submit` class in policy and cards, and
   `me/automation.yaml` default `ask`. Michael runs the install command. Do a dry run on a harmless public form
   first, then a real one with him watching.
8. **Replay:** in a DM, Michael sends the same photo and the first message, and Juno should get to a
   submitted-claim card in four messages or fewer. Record the result in `docs/v2/reports/P2.md` and new
   decisions in `DEVIATIONS.md`. The mechanics go into `docs/17-BUILD-PATTERNS.md`.

## Done looks like

- The full pytest suite passes, including the new tests.
- The dialogue evals include the attachment and browser cases.
- The replay above works end to end.
- No personal data is in tracked files (`test_no_personal`).
- The bridge has been restarted and the log shows the browser agent available.

## Open questions for Michael (ask at the start of that session)

- **Form submission:** for a form his DM explicitly asked for, should it submit straight away (like Muse did), or
  always show a card with the values first? The recommendation is to submit straight away when he named the form,
  and show a card otherwise.
- **Headed or headless:** should the browser run visibly on his PC when he's at it, or always headless?
