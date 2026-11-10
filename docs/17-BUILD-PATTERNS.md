# Build patterns: lean, scalable, repeatable

How to build any new job for a coordinator like Juno, and the questions to ask while building it. Started
2026-11-08 from the Hevy-to-coach-sheet sync. This is the part that carries over to the work copy (docs/16) and to
other people's coordinators. The apps are personal; the mechanics aren't. Add to it every time a build teaches
something.

## The rule (Michael, 2026-11-08)

Every design starts with the lean version, then asks how it scales and how someone else would repeat it. Suggest
the lean version even when nobody asked.

- **Lean:** code does everything code can do. A model gets only the part that needs judgment or words, with only
  the data that part needs. No coordinator session and no subagent when one model call will do.
- **Scalable:** cost and load grow with real events (a new workout), not with clock ticks or how often we check.
- **Repeatable:** the app-specific parts (Hevy, the coach's sheet layout, exercise names) live in config and private
  files. The mechanics live in code and docs someone else can reuse.

## The four layers, cheapest first

| Layer | What | Cost | Use it for |
|---|---|---|---|
| 1. Trigger | A webhook if the app has one; otherwise a timed check in the bridge (Python) | 0 tokens | Knowing something changed |
| 2. Gate | Python diff: is there anything new to act on? | 0 tokens | Skipping almost every run |
| 3. Mechanics | Python: fetch, compare, write numbers, format | 0 tokens | Everything deterministic |
| 4. Words | One words-only model call (`claude_runner.run(..., lean_system=...)`) | about 2 to 3k tokens | Summaries, notes, a friendly line |

A full coordinator run (CLAUDE.md, profile, skills, tools) costs about 11k tokens of setup before it does anything.
Each subagent costs about the same again. Use that only when the job needs open-ended judgment, tools, or a
conversation.

## Worked example: Hevy to the coach's sheet

- **Trigger:** Hevy's API has no webhooks (checked 2026-11-08), so the bridge checks every 30 minutes, 6 AM to
  10 PM, plus a catch-all at 9:17 PM. One small request to Hevy's events feed per check.
- **Gate:** if Hevy changed, `tools/sheets.py plan` reads the sheet once and lists sessions not yet logged. Almost
  every check stops before this step.
- **Mechanics:** `tools/sheets.py write` fills Actual and LsRPE: weeks by order done, never overwriting a filled
  cell, bold and centered. Config: `domains/health/private/coach-sheet.yaml`.
- **Words:** `tools/coach_sheet.py` sends only the session's lifts and his raw notes to one Sonnet call: MN lines,
  the coach note, a one-line message. The model never sees or touches a number.
- **Cost:** checks 0 tokens. About $0.01 to $0.02 per logged workout (measured: 2.3k tokens, $0.013 to $0.019).
  The first version (coordinator plus health subagent, both Sonnet) was an estimated $0.15 to $0.40.
- **Safety:** writes run as unattended (setting must be auto); moving, clearing or overwriting a cell stays a
  Code-tab action with him present.

## Questions to ask when building a job

These are the questions Michael asked while we built the sync. They make a good onboarding checklist.

1. **What triggers it?** Does the app have a webhook? If not, how often do we really need to check? Ten minutes
   felt too often for a workout log; 30 is plenty.
2. **Does checking cost tokens?** It shouldn't. Checks are Python. Say so plainly, with the real per-day count.
3. **Who does the work: the core coordinator, a subagent, or a script?** Default to a script plus one lean model
   call. Name the model and why.
4. **How many tokens per run and per day?** Estimate before building, then measure on the first real run and log
   it (`state/costs.jsonl`).
5. **What exactly happens step by step?** Which calls, which reads, what is cached. No hand-waving.
6. **Where does the model still have to be involved?** Usually only words: summarizing his notes, writing to a
   person in his voice.
7. **What must never happen?** For example: overwriting the coach's text, adding a row, guessing a number.
8. **What is personal and what is the pattern?** Personal: config and private files. Pattern: here.
9. **How does a new person set it up?** Each new integration adds its setup steps to docs/16.
10. **Where does the data live as it grows?** (Michael 2026-11-09, about people.) Never in the agent's file: an
    agent definition holds instructions only, so it costs the same on run one and run one thousand. Bulk records
    (thousands of contacts) go in a local data file that scripts search. Rich notes go one small file per item, and
    the agent finds the few it needs with Grep instead of reading the folder. `people/README.md` is the example.
11. **Do the buttons say where the answer lands?** (Michael 2026-11-09.) "Open" read as "open Gmail" but replied in
    the thread. A button either links out (Open in Gmail, Directions) or names what it posts (See draft, Tell me more).

## Lean model call, the mechanics

`claude -p` with `--system-prompt <one line>`, `--tools ""`, `--strict-mcp-config`, `--disable-slash-commands`,
`--setting-sources user`, `--no-session-persistence`, `--max-turns 1` (`claude_runner.LEAN_FLAGS`). That skips the
project CLAUDE.md, settings, hooks, skills and MCP servers: about 900 tokens of overhead instead of about 11,000.
`--bare` is leaner still but needs an API key; the coordinator runs on the person's Claude sign-in. Ask for JSON
back, parse it in code, and clean it in code (the no-dash rule is enforced in Python, not trusted to the model).
