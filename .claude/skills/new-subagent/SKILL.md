---
name: new-subagent
description: Design and propose a new subagent when Michael describes a job Juno should be able to do ("I need something that can...", "add an agent for...", "can Juno learn to..."), or when the same kind of request keeps arriving that no agent covers. Drafts everything in proposals/ and asks for one tap before anything is installed.
---

# New subagent

Michael describes the job in plain words; you do the design. Nothing is installed, enabled or downloaded until he
taps **Allow once** on the install card.

## 1. Understand the job (in the same conversation)
- What should it do, how often, and what does "done" look like? Ask at most two questions, only if the answer
  changes the design. Otherwise assume, and list the assumptions on the card.
- Check `observed/procedures.md` and `docs/` for anything already learned about this kind of task, and the existing
  roster in `CLAUDE.md`: extend an existing agent instead when that is simpler.

## 2. Design it the way Reel (youtube) was built
First ask whether it needs an agent at all: read `docs/17-BUILD-PATTERNS.md`. If a script plus one lean model call
does the job (the coach-sheet sync), propose that instead, with its token cost per run and per day. Every proposal
gives the lean version, how it scales, and what another person would reuse. (Michael 2026-11-08)
Read `.claude/agents/youtube.md`, `tools/youtube.py` and `tests/test_youtube.py` as the reference.
- **One narrow agent file**: persona name, `description` that says when to use it, the cheapest model that can do
  it (haiku for fetch and extract, sonnet for judgement or writing), `tools` limited to what it needs, and
  `omitClaudeMd: true` with its own untrusted-content rule if it reads anything from outside.
- **A small script in `tools/`** for anything that touches the outside world, so the agent only runs that script.
  Validate inputs, cache results under `data/<name>/`, rate-limit, clear exit codes, wrap fetched text in
  `<untrusted_...>` tags. Secrets come only from 1Password through the service account, never from files or chat.
- **Packages**: only from PyPI, pinned to an exact version you checked exists (`pip index versions <pkg>`), and as
  few as possible. Never a marketplace skill, plugin or MCP server; if one seems needed, say so and stop.
- **Permissions**: say exactly which existing rule covers it (for example `Bash(python tools/*)`). If it needs a
  new connector or an outward tool, it cannot be self-installed: describe what Michael would have to add.
- **Tests**: offline tests for input checks, caching and failure handling, like `tests/test_youtube.py`.

## 3. Draft it in `proposals/<name>/`
Write the files at their final relative paths inside the proposal folder (for example
`proposals/<name>/.claude/agents/<name>.md`, `proposals/<name>/tools/<name>.py`, `proposals/<name>/tests/test_<name>.py`)
plus `proposals/<name>/install.json` (`{"files": {"<path in proposal>": "<final path>"}, "pip": ["pkg==x.y.z"],
"claude_md": {"roster": "<one table row>", "routing": "<one routing bullet>"}}`; final paths only under
`.claude/agents/`, `.claude/skills/`, `tools/`, `tests/`, `learnings/`, and never an existing file) and
`proposals/<name>/README.md`: what it does, an example request, model, tools, packages with versions, risks,
and how to remove it. Run its tests from the proposal folder if you can.

## 4. Ask for the tap
Add an approval entry (see "Asking for a tap" in `CLAUDE.md`) with `action_class: "subagent.install"`, `proposal: "<name>"`, a one-line
`summary` ("Add Scout-2, a watch price tracker"), and an `action` that lists exactly: the files to copy into place,
the `pip install` lines with pinned versions, the roster line for `CLAUDE.md`, and the routing line.

## 5. On Allow once
The bridge installs it, not you: `gateway/installer.py` checks `install.json`, installs only the pinned packages,
copies exactly the listed files, adds the two `CLAUDE.md` lines, runs the full test suite, and rolls everything back
if anything fails. Your resumed run only gets the result: report it, and on success note the new agent in
`observed/procedures.md` and the changelog. Never copy, install or edit config yourself.
