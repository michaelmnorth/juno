# Brief P2 · Memory

**Hand this to a Claude Code session in the Juno repo after Phase 1 has exited.** Read `04-MEMORY.md` in full, plus the taint and trust sections of `02-ARCHITECTURE.md` and `05-SECURITY.md`.

## Goal

Replace "read the folder" with the memory store: typed, dated, sourced facts; searchable episodes; budgeted retrieval in the assembler; nightly consolidation; a real forget.

## Deliverables

1. **Schema and migrations** for the tables in `04-MEMORY.md`, with FTS5 indexes. No embeddings yet.
2. **Importer** from the v1 folders. Re-runnable, read-only on the source, with a report of what mapped where and what did not map. The core card draft goes to the owner for review before it is used.
3. **Write paths** with source-based trust: `memory.note` for the owner's explicit requests; `observations[]` returned by runs and validated by code; third-party claims stored as candidates.
4. **Retrieval in the assembler:** entity linking, slots, FTS search, recency digest, packing by priority inside the block budget, trust and age labels on every item.
5. **Model-facing tools:** `memory.search`, `memory.entity`, `memory.note`, `memory.forget` (which proposes; deletion needs a tap).
6. **Nightly consolidation** in the batch lane: the eight steps, each with a validated schema, and a counts report in the ledger.
7. **Confirm chips** in the morning brief, at most three, expiring.
8. **Forget** end to end, with tombstones.
9. **Tests:** recall at budget (≥ 40 probes, no model), forget, poisoning, budget drift over 30 simulated days, restore from backup.
10. **Backup** extended to the database, taken with a consistent snapshot.

## Done when

- Recall at budget ≥ 90%.
- Forget and poisoning tests pass.
- Consolidation has run seven nights with no manual repair, and its report shows facts being superseded and retired, not only added.
- The core card is ≤ 1,200 tokens and the owner has accepted it.
- Phase 1's cost targets still hold with the new memory block.
- The v1 memory files are no longer read by any v2 path. They stay on disk untouched until the owner removes them.

## Guardrails

- Models never write rows. They return structured observations; code decides trust, status and storage.
- Nothing from another person's text becomes an active fact without a tap.
- Do not store raw third-party mail bodies. Store a summary and a pointer.
- Do not add a vector index, a graph database or a hosted memory service. If recall is below target, report which probes fail and why first.
- Probes and golden cases contain personal data. They live in the instance directory, not in the repo. Fixtures in the repo are synthetic.

## Report back

Importer report, recall score with the failing probes, a week of consolidation counts, the token size of the memory block per DM, and anything in the schema that had to change.
