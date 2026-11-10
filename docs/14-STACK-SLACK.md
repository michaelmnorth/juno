# Stack: Slack (step 3 of the playbook)

Nick's step 3 is "decide the components, then read each service's docs and API reference before building". Juno's
components were already decided (docs/02-ARCHITECTURE.md): Slack for the conversation, Gmail and Google Calendar
read through connectors and our scripts, Apple Health, Hevy, Withings and Plaid for data. So this step is about the
one that the six designs in docs/13 depend on: **Slack Block Kit**. Researched 2026-11-08 from Slack's developer
docs. Lines marked **unconfirmed** were not found in the docs and get tested with a real message before building.

## How Juno talks to Slack (unchanged)
- Socket Mode bridge, `gateway/slack_bridge.py`: no public URL, nothing to host for Slack itself.
- Cards are posted with `chat.postMessage`, changed in place with `chat.update` (approved, expired, asked again).
- Every message also sets a plain `text` fallback (docs/13 rule), which is what notifications and screen readers show.

## Limits the designs must fit

| Block or element | Limit | Where it bites |
|---|---|---|
| Message | 50 blocks | Sunday reflection (screen 5) is the only long one |
| Home tab (`views.publish`) | 100 blocks | Juno home (screen 6) |
| `section` text | 3,000 characters | The full draft on the draft card (screen 2). A long email needs splitting into two sections |
| `section` fields | up to 10 fields, 2,000 characters each | Facts grids: draft card, approval card, status (6 fields, fine) |
| `header` | 150 characters, plain text only (no bold, no links) | Card titles |
| `context` | 10 elements | Footer lines |
| `context` image | needs a public `image_url` or an uploaded `slack_file` | The gray dot on the expired card (see fixes) |
| `actions` | 25 elements | Never close; we use 2 or 3 plus ⋯ |
| `button` text | 75 characters, but long labels get cut off on phones (around 30) | Keep labels like "Yes, invite", "Edit in Gmail" |
| `overflow` (⋯) | 5 options at most | Draft card: "Always send to X" and "Skip" (2). Fine |
| `response_url` | 5 uses within 30 minutes | Don't rely on it for the expired edit; use `chat.update` |
| `chat.update` | no stated per-message limit (normal rate limits) | Card state changes |

## Behaviors worth knowing
- **Link buttons still send an interaction.** A button with a `url` (Edit in Gmail, Open in Calendar) opens the link
  and also sends an action to the bridge, which must acknowledge it or Slack shows an error. Needs a do-nothing handler.
- **Home tab:** turn it on under the app's App Home settings (Show Tabs > Home Tab), reinstall the app, then answer
  the `app_home_opened` event with `views.publish`. Socket Mode delivering that event: likely, **unconfirmed**.
- **Custom name and icon per message** (`chat:write.customize`): lets one app post as another persona with its own
  name and picture. That is the path for a "Gary" voice later without a second app. Such posts can't be removed with
  `chat.delete`, and they must go to the DM's channel id (D...).
- **App icon, name and color:** set by hand in the app settings (done 2026-11-08: the studio portrait on #1F3B73). No
  public API for it, as far as the docs show.

## Unconfirmed until a real test message
1. `~strikethrough~` inside `section` mrkdwn in a bot message (the expired card strikes its question).
2. `>` block quote rendering in a bot message (the "show changes" view on the Sunday reflection).
3. `rich_text_preformatted` posted by a bot (an alternative way to show the full draft).
4. The Home tab event arriving over Socket Mode.

Test: one throwaway DM from the bridge with all four, looked at on Michael's phone and desktop. That is the first
build task, before any card code.

### Results, 2026-11-08 (`python gateway/block_check.py`)
Slack accepted every block, and on desktop (Slack in Chrome) all of them render as designed. Screenshot:
`docs/private/design/block-check-desktop.jpg` (kept on this PC).

| Check | Result |
|---|---|
| 1. `~strikethrough~` in a bot `section` | Works |
| 2. `>` quote in a bot `section` | Works: gray bar, both lines |
| 3. `rich_text_preformatted` from a bot | Works: monospace box. The draft card can keep a plain `section` instead; both are fine |
| Fields grid (4 fields) | Works: two columns, bold labels |
| `context` with ⏱ instead of an image | Works |
| url button (`edit_link`, already acked by the bridge) | Renders. The no-op handler already exists for `edit_link`; new link buttons reuse that action_id or get their own ack |
| 4. Home tab event over Socket Mode | **Works** (2026-11-08): Home tab turned on, `app_home_opened` added under bot events; it needs no scope, so no reinstall. Socket Mode delivers the event and the bridge's `views.publish` shows on the next open. **Then turned off the same day:** on iPhone the app opens on its Home tab, an extra tap before every DM. Lesson: an app's Home tab costs a tap on mobile, so keep everything in the DM |
| Photos in a DM (2026-11-08) | Arrive as subtype `file_share`; need the `files:read` scope (added, app reinstalled, bot token unchanged) and a download of `url_private_download` with the bot token |
| Phone rendering (iPhone, Michael 2026-11-08) | Everything renders. One difference: **the fields grid stacks into one column on the phone** (Who, Why, What, Expires each on its own pair of lines), so a 4-fact grid gets tall. Keep grids to 4 facts or fewer, with short values; consider "*Who* Dana, a friend" on one line if it reads better on the phone |

**Found along the way:** Juno's ordinary replies show literal `**double asterisks**`. Claude writes Markdown bold,
but Slack's mrkdwn bolds with single `*`. The bridge should convert `**x**` to `*x*` (and `[text](url)` to
`<url|text>`) before posting. Small fix in `slack_bridge.chunk`'s callers; goes in with the first card build.

## Design changes this research causes (folded into docs/13)
- **Expired card:** replace the gray dot image with a text character (⏱ or ·) in the `context` line, so no image hosting.
- **Link buttons:** the bridge gets a no-op handler for url buttons (Edit in Gmail, Open in Calendar, Open in Drive).
- **Sunday reflection:** cap it by block count (stay under 50), not only by number of lessons. If it would go over,
  the rest moves to "Show all" in the thread.
- **Draft card:** if the draft passes 3,000 characters, split it across two `section` blocks; never cut it short
  (Michael wants the full draft before Send).

## Where this sits in the two plans
Michael follows Nick's playbook and Juno's own plan (docs/04-PLAN.md) together; they line up like this:

| Nick's step | Juno so far | Next |
|---|---|---|
| 1. Research | docs/03, 06, 07, 10, 12 | Done |
| 2. Design | docs/11, docs/13, six screens chosen; icon set | Copy screens 3 to 6 into Paper after its limit resets (~2026-11-13) |
| 3. Stack | This doc | The four-item test message |
| 4. Build and iterate | Phases 0 to 2 partly live (bridge, sweep, drafts, approvals) | Rebuild the cards to the chosen designs, one screen per commit with tests, morning brief first. Screenshot anything off and paste it back (Nick's swipe-file loop) |
| 5. Host and ship | Runs on Michael's PC (Phase 5 decides always-on hardware) | Later |
