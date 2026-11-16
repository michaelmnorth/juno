---
id: k-20261115-the-research-scan-skips-what-it-already-read
title: The research scan skips what it already read
status: confirmed
topic: research
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_usage.py::test_research_scan_uses_only_web_tools_and_skips_what_it_saw
---
Keep a seen list so each night only reads new things; the scan has web tools only and changes nothing.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
