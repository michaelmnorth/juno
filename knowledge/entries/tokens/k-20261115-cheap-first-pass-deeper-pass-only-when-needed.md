---
id: k-20261115-cheap-first-pass-deeper-pass-only-when-needed
title: Cheap first pass, deeper pass only when needed
status: confirmed
topic: tokens
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_usage.py::test_optimizer_deep_dive_only_when_flagged
---
The token optimizer runs Haiku first and calls Sonnet only when Haiku flags a job for a closer look.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
