---
id: k-20261115-only-a-yes-on-a-lesson-card-writes-a-lesson-and
title: Only a yes on a lesson card writes a lesson, and never into config
status: confirmed
topic: learning-loop
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_lessons.py::test_save_appends_a_dated_line
  - test: tests/test_lessons.py::test_save_refuses_config_and_odd_targets
---
The weekly review proposes; a Save tap writes exactly that line, dated. A card can never target me/automation.yaml, CLAUDE.md or settings.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
