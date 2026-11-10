# 04 · Memory

Memory in v2 is a store with a lifecycle, not a folder that gets read. Three questions drive every choice here: **how does a memory get in, how does it get into a prompt, and how does it get out.**

## What v1 has (ASSUMED) and what is missing

v1 splits a folder by confirmation level: confirmed (`me/ learnings/ people/ domains/`, written only on a tap), observed (`observed/`, written silently, fades after 30 days), working state, data. Keep those ideas: the owner-gated layer, the decay of guesses, summaries instead of raw mail.

Missing, and the reason for this spec:

- **No selection.** Profile and lessons are read every run, so cost grows with what Juno knows.
- **No recall.** There is no searchable record of what was said or what happened.
- **No time.** A fact has no "since", "until" or "last confirmed". Facts change.
- **No provenance.** Nothing records where a fact came from or how far to trust it.
- **No lifecycle.** Only a weekly pass consolidates. Lessons accumulate as prose.
- **One write gate for everything.** The owner's own statement in a private DM needs the same tap as a guess from an email.
- **No backup** of the personal files that are kept out of git.
- **No test** that memory works.

## Layers

| Layer | What | Size | In the prompt |
|---|---|---|---|
| **Core card** | Who the owner is, current priorities, standing rules, key people, week skeleton | ≤ 1,200 tokens, curated | Always |
| **Thread state** | Rolling summary, working set of recent IDs, last turns | ≤ 2,100 tokens | Always for that thread |
| **Entity dossiers** | A compact generated card per person, project or place | ≤ 300 tokens each | When the entity is mentioned (top 3) |
| **Facts** | Typed, dated, sourced statements | unbounded | Selected by slot and search |
| **Episodes** | One row per thing that happened: a DM exchange, a triaged email, an event, a workout, an action taken | unbounded | Selected by search and recency |
| **Daily notes** | One short summary per day | ~300 tokens a day | For "what happened" questions |
| **Procedural** | Playbooks, scoped lessons, examples, rules | per playbook budget | Only with its playbook |
| **Archive** | Everything older | unbounded | Only through `memory.search` |

Curated text the owner may edit by hand stays in markdown in the instance directory (`core-card.md`, `persona.md`, playbooks). High-volume machine-written records live in SQLite.

## Schema

One SQLite database per instance, WAL mode, foreign keys on. Sketch; the build session finalises types and indexes.

```sql
entities(id, kind, name, aliases_json, external_ids_json, created_at, updated_at)
  -- kind: self | person | org | place | project | topic

facts(id, entity_id, predicate, value_text, value_json,
      kind,          -- preference | biographical | relationship | commitment | routine | state
      sensitivity,   -- normal | health | finance | intimate | work
      trust,         -- owner_stated | owner_confirmed | observed | third_party
      status,        -- candidate | active | superseded | retired | rejected
      confidence, tainted,
      valid_from, valid_to, observed_at, last_confirmed_at,
      last_used_at, use_count,
      source_kind, source_ref, source_run_id, supersedes_id)

episodes(id, ts, kind, thread_id, entity_ids_json, summary, pointer_ref, sensitivity, tainted)
  -- pointer_ref: Gmail message id, calendar event id, workout id … never the raw body

threads(id, channel, started_at, last_at, rolling_summary, working_set_json, open_loops_json, tainted)
messages(id, thread_id, ts, role, text, token_count)

daily_notes(date, summary, highlights_json)
dossiers(entity_id, text, token_count, built_at, built_from_json)

lessons(id, scope, kind, rule_text, status, evidence_json, eval_case_ids_json,
        created_at, promoted_at, last_validated_at)
examples(id, playbook, key, before_text, after_text, created_at)        -- few-shot pairs
signals(id, ts, kind, run_id, target_ref, value_json)

tombstones(id, selector_json, created_at)

-- FTS5 virtual tables over facts, episodes, messages, daily_notes
-- embeddings(item_kind, item_id, model, vector)   -- optional, added only if recall evals need it
```

## How a memory gets in

Trust and status come from **the source of the text**, decided in code:

| Source | Trust | Status | Tap? |
|---|---|---|---|
| Owner says it in the private channel ("remember…", "no, Chris is my coach"), run untainted | `owner_stated` | `active` | No |
| Same, but the run is tainted | `owner_stated`, `tainted` | `candidate` | Yes |
| Owner taps Confirm on a candidate | `owner_confirmed` | `active` | — |
| A run infers it from the owner's own behaviour (edits, choices, timings) | `observed` | `candidate` → `active` when seen in 2+ independent episodes | No, but listed weekly |
| It comes from someone else's text (an email says a meeting moved) | `third_party` | `candidate` | Yes, before it is treated as true |
| Imported from v1 confirmed files | `owner_confirmed` | `active` | — |
| Imported from v1 observed files | `observed` | `candidate` | — |

Rules:

- Models never write facts directly. Runs return `observations[]` in a fixed schema with an evidence pointer. Code validates, dedupes and stores them.
- The model-facing write tool is `memory.note(text, about?)`. It exists for the owner's explicit requests. Its trust level follows the table above.
- Third-party and tainted items are rendered as claims ("an email from X says…"), never as facts or instructions.
- Sensitivity is assigned by rule from the pack and predicate (health, finance, intimate, work). It controls which run classes can receive the item.
- Secrets are rejected by pattern at write time.

## How a memory gets into a prompt

Selection is deterministic and happens in the assembler before the model runs.

1. **Entity linking.** Match names and aliases in the message and working set against `entities`. Ambiguity (two Sarahs) is resolved by recency, then by asking.
2. **Slots.** The router's `memory_slots` name what the intent needs (`routines`, `person:Chris`, `voice:client`, `training_block`). Each slot is a stored query with a token cap.
3. **Search.** For recall questions, FTS over episodes, daily notes and messages, ranked by match, recency and trust. Embeddings are an optional later addition, justified only by failed recall evals.
4. **Recency.** A short digest of the last 24 hours.
5. **Budget.** Items are packed by priority until the block budget is reached. Active owner-stated and confirmed facts first, then observed, then third-party claims.
6. **Labels.** Each item is rendered with its trust and age: `[confirmed, Oct 2026]`, `[observed, unconfirmed]`, `[claimed by sender]`.

The model can still call `memory.search(query, kinds?, since?)` and `memory.entity(name)` in L2 when the assembled context is not enough. Each retrieval updates `last_used_at` and `use_count`.

The core card is the only memory that is always present. It has a hard size limit. Changes arrive as a proposed diff the owner taps to accept. A monthly prompt asks whether priorities changed.

## Consolidation

A nightly `reflect` job in the batch lane. Each step has a fixed output schema that code validates; nothing here is free-form.

1. **Summarise** each thread touched today into its rolling summary. Write the daily note.
2. **Extract** candidate facts from the day's owner messages and episodes, each with evidence.
3. **Reconcile** with existing facts for the same entity and predicate. Same value: raise confidence, set `last_confirmed_at`. Different value: if the existing fact is owner-stated or confirmed, queue a one-tap question for the brief; otherwise supersede it and set `valid_to`.
4. **Promote** observed candidates seen in two or more independent episodes.
5. **Rebuild** dossiers for touched entities inside their budget.
6. **Decay** by kind. Observed `state` facts expire in weeks, `routine` and `preference` in months, `biographical` never. Unused, low-confidence items retire.
7. **Compact.** Old messages leave the hot table once their thread summary and daily note exist.
8. **Report** counts to the ledger: added, promoted, superseded, retired, questions queued.

The morning brief carries at most three "confirm?" chips. Unanswered questions expire.

## How a memory gets out

`forget <thing>`:

1. Show the matching facts, episodes, examples and dossier lines.
2. On tap, hard-delete the rows and their FTS (and embedding) entries, rebuild affected dossiers and summaries, and write a tombstone so consolidation does not relearn it from older records.
3. Report what was removed. State the backup retention window honestly: copies age out of encrypted backups within that window.

`what do you remember about X` renders the dossier plus sources. Every fact can answer "why do you think that?" from its evidence pointer.

## Other people

People profiles hold facts about third parties who did not ask to be profiled. Keep them proportionate: what helps the owner be a good friend, client or colleague. No raw message history, no inferred sensitive traits. The work instance follows the employer's rules instead.

## Importing v1

Write an importer; do not migrate by hand. It must be re-runnable and must not touch the v1 files.

- `me/` → core card draft (owner reviews) + `self` facts.
- `people/` → entities + facts (`owner_confirmed`).
- `learnings/` → lessons, each mapped to a scope, or to a rule where it is deterministic.
- `observed/` → candidate facts with their original dates.
- `state/` → reminders, pending approvals, handled IDs into their tables.
- `data/` → left in place; tools read it.

## Tests

- **Recall at budget (no model).** About 40 probes ("who is Chris", "when is the Q4 estimated tax due", "what time do I want to be in bed"). For each, assert the needed fact is in the assembled context within budget. Target ≥ 90%.
- **Answer check (weekly, batch).** The same probes answered by the converse model and graded against the expected fact.
- **Forget.** After `forget`, the item is absent from rows, FTS, dossiers, summaries and the next consolidation.
- **Poisoning.** A synthetic email asserting a false fact about the owner must end as a `third_party` candidate and never appear as a fact in any prompt.
- **Budget.** The core card and every dossier stay inside their limits after 30 simulated days of consolidation.
- **Restore.** A backup restores to a working instance on a clean host.

## Options considered

- **The memory tool (`memory_20250818`) or Managed Agents memory stores.** Both give the model a directory it reads and writes with file tools. Simple, and useful for a sandboxed worker's scratch notes. Not used for the core because writes are model-driven and untyped, which loses provenance and trust levels, and reads cost tool round trips.
- **A hosted memory product or a graph database.** Not justified at one-person scale before the recall tests say plain SQLite with FTS is failing.
