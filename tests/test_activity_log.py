"""The daily conversation log the project's coordinator reads (Michael 2026-11-15): readable, and never a secret."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "gateway") not in sys.path:
    sys.path.insert(0, str(ROOT / "gateway"))

import activity_log  # noqa: E402
import approval_policy  # noqa: E402

NOW = datetime(2026, 11, 15, 3, 1, tzinfo=timezone.utc)  # 10:01 PM Eastern on the 14th


def test_lines_land_in_his_eastern_day(tmp_path):
    activity_log.write(tmp_path, "Michael", "test the payment", NOW)
    activity_log.write(tmp_path, "Juno", "Queued.\nA card is coming.", NOW)
    text = (tmp_path / "logs" / "conversations" / "2026-11-14.md").read_text(encoding="utf-8")
    assert text.startswith("# Juno conversation log, Saturday November 14, 2026")
    assert "- 22:01 **Michael:** test the payment" in text and "Queued.\n  A card is coming." in text


def test_secrets_never_reach_the_log(tmp_path):
    secrets = ["4000 0099 9000 1984", "4242424242424242", "sk_live_abcdefgh1234", "xoxb-1234-abcd-efgh",
               "op://Agent-Secrets/Slack-Juno/bot_token", "ghp_" + "a" * 30, "sk-ant-api03-abcdefghijk"]
    activity_log.write(tmp_path, "Juno", " ".join(secrets) + " cvc 321 password: hunter2", NOW)
    text = activity_log.path_for(tmp_path, NOW).read_text(encoding="utf-8")
    for s in secrets + ["321", "hunter2"]:
        assert s not in text
    assert "[number removed]" in text and "[removed]" in text


def test_audit_events_become_plain_lines(tmp_path):
    state = tmp_path / "state"
    entry = {"id": "a-1", "action_class": "payment.link", "summary": "Pay $28.80 to Stripe demo checkout?"}
    approval_policy.audit(state, "approved", entry)
    approval_policy.audit(state, "payment_expired", {**entry, "summary": "$28.80 to Stripe demo checkout"},
                          "no passkey approval in Link within 30 minutes")
    approval_policy.audit(state, "v2_handoff", entry)  # plumbing: not in the readable log
    text = activity_log.path_for(tmp_path).read_text(encoding="utf-8")
    assert "**[tapped yes]:** Pay $28.80 to Stripe demo checkout?" in text
    assert "**[payment expired]:** $28.80 to Stripe demo checkout — no passkey approval" in text
    assert "v2_handoff" not in text and text.count("\n- ") == 2


def test_a_broken_folder_never_breaks_a_reply(tmp_path):
    blocker = tmp_path / "logs"
    blocker.write_text("not a folder", encoding="utf-8")
    activity_log.write(tmp_path, "Juno", "hello", NOW)  # no exception
