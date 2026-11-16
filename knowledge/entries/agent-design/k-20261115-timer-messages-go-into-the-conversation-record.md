---
id: k-20261115-timer-messages-go-into-the-conversation-record
title: Timer messages go into the conversation record
status: confirmed
topic: agent-design
created: 2026-11-15
last_verified: 2026-11-16
review_by: 2027-02-14
sources:
  - test: tests/test_conversation_thread.py::test_short_answer_after_a_ping_sees_the_ping
  - commit: 54f77ab
---
Otherwise a short reply to a ping ("yes") loses the thread.

Migrated from the Nov 15 lessons write-up (recaps/for-minerva/2026-11-15-lessons.md).
