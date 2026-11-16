---
id: k-20261115-guesses-that-are-not-seen-again-fade-on-their-ow
title: Guesses that are not seen again fade on their own
status: confirmed
topic: learning-loop
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_observed.py::test_stale_by_confidence_and_promoted_never_expire
---
A pending observation retires after 30 days (low), 60 (medium) or 120 (high) without being seen again, so a wrong guess never hardens. Promoted lines never expire.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
