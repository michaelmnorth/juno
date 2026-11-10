"""A Save tap on a lesson card writes exactly that line, in code (gateway/lessons.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import lessons  # noqa: E402
import slack_bridge  # noqa: E402


@pytest.fixture
def root(tmp_path):
    (tmp_path / "learnings").mkdir()
    (tmp_path / "learnings" / "drafter.md").write_text("# drafter learnings\n\n- 2026-11-01: Old rule. (Michael)\n",
                                                       encoding="utf-8")
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "automation.yaml").write_text("calendar.hold: auto\n", encoding="utf-8")
    return tmp_path


def test_save_appends_a_dated_line(root):
    out = lessons.apply({"target": "learnings/drafter.md", "new": "- Cut the greeting on business mail"}, root,
                        today="2026-11-10")
    text = (root / "learnings" / "drafter.md").read_text(encoding="utf-8")
    assert text.endswith("- 2026-11-10: Cut the greeting on business mail (Michael)\n") and not out["replaced"]


def test_save_replaces_the_old_line(root):
    lessons.apply({"target": "learnings/drafter.md", "old": "2026-11-01: Old rule. (Michael)",
                   "new": "- 2026-11-10: New rule. (Michael)"}, root)
    text = (root / "learnings" / "drafter.md").read_text(encoding="utf-8")
    assert "Old rule" not in text and text.count("New rule") == 1


def test_save_twice_is_a_no_op(root):
    change = {"target": "learnings/drafter.md", "new": "- 2026-11-10: Once. (Michael)"}
    lessons.apply(change, root)
    assert lessons.apply(change, root)["already"]
    assert (root / "learnings" / "drafter.md").read_text(encoding="utf-8").count("Once.") == 1


@pytest.mark.parametrize("target", ["me/automation.yaml", "CLAUDE.md", ".claude/settings.json",
                                    "learnings/../CLAUDE.md", "state/x.md", "me/private/values.md"])
def test_save_refuses_config_and_odd_targets(root, target):
    with pytest.raises(lessons.LessonError):
        lessons.apply({"target": target, "new": "- anything"}, root)
    assert (root / "me" / "automation.yaml").read_text(encoding="utf-8") == "calendar.hold: auto\n"


def test_tap_records_signals_and_never_runs_a_model(root):
    assert slack_bridge.lesson_tap(root, "save", {"id": "p-1", "target": "learnings/drafter.md",
                                                  "new": "- Shorter sign-offs"}) == "✅ Saved."
    assert slack_bridge.lesson_tap(root, "skip", {"id": "p-2", "target": "learnings/drafter.md", "new": "- x"})
    rows = [json.loads(l) for l in (root / "state" / "signals.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["lesson.saved", "lesson.skipped"]
    assert rows[0]["target"] == "learnings/drafter.md" and rows[0]["line"].endswith("Shorter sign-offs (Michael)")
