---
id: k-20261115-pin-each-helper-s-and-job-s-model-haiku-to-sort
title: Pin each helper's and job's model: Haiku to sort, Sonnet to write, Opus for hard judgment
status: confirmed
topic: tokens
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_ping_policy.py::test_models_are_pinned_per_job
  - doc: .claude/agents/inbox-triage.md
---
Every timer job has a pinned model (test) and every subagent file names its model (doc).

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
