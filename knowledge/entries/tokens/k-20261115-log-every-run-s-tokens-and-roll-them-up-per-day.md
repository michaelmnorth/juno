---
id: k-20261115-log-every-run-s-tokens-and-roll-them-up-per-day
title: Log every run's tokens and roll them up per day
status: confirmed
topic: tokens
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_usage.py::test_rollup_counts_each_run_once_and_says_what_was_done
  - test: tests/test_usage.py::test_optimizer_never_offers_api_credits
---
Each run logs what it was for and its tokens; a daily rollup feeds the optimizer, which never suggests API credits (Juno runs on the Max plan).

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
