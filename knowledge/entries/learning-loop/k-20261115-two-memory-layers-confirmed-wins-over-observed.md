---
id: k-20261115-two-memory-layers-confirmed-wins-over-observed
title: Two memory layers: confirmed wins over observed
status: confirmed
topic: learning-loop
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_hooks.py::test_memory_denied_unattended
  - test: tests/test_hooks.py::test_observed_writable_unattended
---
Juno keeps a confirmed layer (me/, learnings/, people/, written only with Michael's yes) and an observed layer (observed/, written silently). Juno's own runs can write observed/ but are blocked from the confirmed layer.

Confirmed means: the write hook really blocks unattended writes to the confirmed layer and allows observed/ (tests below). It does not prove the split makes Juno better; that is still a judgment call.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
