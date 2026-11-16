"""The knowledge base (tools/knowledge.py): timestamps, confirmed only with a source, stale after review-by, Juno's
own runs kept to knowledge/local/, and the three places that write into it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "gateway"))

import knowledge as k  # noqa: E402

CODE_TAB = {}  # no COORDINATOR_UNATTENDED: Michael in a Code-tab session
JUNO = {"COORDINATOR_UNATTENDED": "0"}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "audit.jsonl").write_text(
        json.dumps({"at": "2026-11-16T00:55:23+00:00", "event": "approved", "id": "a-8d7b4354", "class": "lesson"})
        + "\n" + json.dumps({"at": "2026-11-16T00:55:38+00:00", "event": "executed", "id": "a-8d7b4354",
                             "class": "lesson"}) + "\n", encoding="utf-8")
    return tmp_path


def test_new_entry_is_unconfirmed_and_timestamped(root):
    e = k.add(root, title="Gmail adds the signature on send", body="So drafts carry none.", today="2026-11-16",
              env=JUNO)
    assert e["status"] == "unconfirmed" and e["created"] == "2026-11-16" and e["last_verified"] == ""
    assert e["review_by"] == "2026-12-16" and e["path"].parent == root / "knowledge" / "local" / "general"
    back = k.parse(e["path"].read_text(encoding="utf-8"))
    assert back["title"] == "Gmail adds the signature on send" and back["body"] == "So drafts carry none."


def test_confirmed_needs_a_source(root):
    with pytest.raises(k.KnowledgeError, match="needs a source"):
        k.add(root, title="x", body="y", status="confirmed", env=JUNO)
    e = k.add(root, title="x", body="y", today="2026-11-01", env=JUNO)
    with pytest.raises(k.KnowledgeError):
        k.confirm(root, e["id"], [], env=JUNO)


@pytest.mark.parametrize("source", ["pr:not a pr", "url:http://plain.example", "card:a-00000000",
                                    "test:tests/test_missing.py", "test:tests/test_x.py::test_gone",
                                    "michael:said so", "rumor:somebody"])
def test_bad_or_unprovable_sources_are_refused(root, source):
    e = k.add(root, title="claim", body="", env=JUNO)
    with pytest.raises(k.KnowledgeError):
        k.confirm(root, e["id"], [source], env=JUNO)
    assert k.find(root, e["id"])["status"] == "unconfirmed"


def test_confirm_stamps_and_moves_review_by(root):
    e = k.add(root, title="claim", body="", today="2026-10-01", env=JUNO)
    done = k.confirm(root, e["id"], ["card:a-8d7b4354", "test:tests/test_x.py::test_ok"], today="2026-11-16",
                     env=JUNO)
    assert done["status"] == "confirmed" and done["last_verified"] == "2026-11-16"
    assert done["review_by"] == "2027-02-14" and [s["kind"] for s in done["sources"]] == ["card", "test"]
    assert k.problems(root) == []


def test_stale_after_review_by_and_listed_by_check(root):
    e = k.add(root, title="old claim", body="", today="2026-09-01", env=JUNO)
    assert k.is_stale(k.find(root, e["id"]), "2026-11-16")
    assert not k.is_stale(k.find(root, e["id"]), "2026-09-15")
    k.retire(root, e["id"], "turned out wrong", today="2026-11-16", env=JUNO)
    gone = k.find(root, e["id"])
    assert gone["status"] == "retired" and gone["retired_reason"].startswith("2026-11-16: turned out wrong")
    assert not k.is_stale(gone, "2027-01-01") and gone["path"].exists()


def test_same_title_or_url_is_not_a_second_entry(root):
    a = k.add(root, title="Claude Code adds X", body="", sources=["url:https://example.com/x"], env=JUNO)
    b = k.add(root, title="claude code adds x!", body="", env=JUNO)
    c = k.add(root, title="Another headline", body="", sources=["url:https://example.com/x"], env=JUNO)
    assert a["created_new"] and not b["created_new"] and not c["created_new"] and b["id"] == c["id"] == a["id"]


def test_juno_runs_never_write_the_shared_part(root):
    with pytest.raises(k.KnowledgeError, match="local"):
        k.add(root, title="x", body="", shared=True, env=JUNO)
    e = k.add(root, title="x", body="", shared=True, env=CODE_TAB)
    assert e["path"].parent.parent == root / "knowledge" / "entries"
    with pytest.raises(k.KnowledgeError):
        k.retire(root, e["id"], "no", env={"COORDINATOR_UNATTENDED": "1"})


def test_shared_entries_cite_only_public_sources(root):
    with pytest.raises(k.KnowledgeError, match="stay on the PC"):
        k.add(root, title="x", body="", shared=True, status="confirmed", sources=["card:a-8d7b4354"], env=CODE_TAB)


def test_check_flags_hand_edited_problems(root):
    folder = root / "knowledge" / "local" / "general"
    folder.mkdir(parents=True)
    (folder / "k-bad.md").write_text("---\nid: k-bad\ntitle: Bad\nstatus: confirmed\ntopic: general\n"
                                     "created: 2026-11-16\nlast_verified:\nreview_by: 2026-12-16\nsources:\n---\nx\n",
                                     encoding="utf-8")
    (folder / "k-broken.md").write_text("no header here", encoding="utf-8")
    found = " ".join(k.problems(root))
    assert "cites no source" in found and "no last_verified" in found and "missing the --- header" in found
    assert k.main(["check", "--root", str(root)]) == k.PROBLEMS


def test_recheck_reverifies_passing_tests(root):
    e = k.add(root, title="x passes", body="", status="confirmed", sources=["test:tests/test_x.py::test_ok"],
              today="2026-08-01", env=JUNO)
    assert k.is_stale(k.find(root, e["id"]), "2026-11-16")
    out = k.recheck_tests(root, today="2026-11-16", apply=True, env=JUNO)
    assert out["passed"] == [e["id"]] and not out["failed"]
    assert k.find(root, e["id"])["last_verified"] == "2026-11-16"


def test_index_and_recap(root):
    k.add(root, title="old", body="", today="2026-10-01", env=JUNO)
    k.add(root, title="new", body="", today="2026-11-14", env=JUNO)
    k.write_indexes(root, "2026-11-16")
    index = (root / "knowledge" / "local" / "INDEX.md").read_text(encoding="utf-8")
    assert "0 confirmed, 2 unconfirmed, 1 stale" in index and "**stale**" in index
    r = k.recap(root, "2026-11-09", "2026-11-16")
    assert [e["title"] for e in r["added"]] == ["new"] and [e["title"] for e in r["stale"]] == ["old"]
    assert k.recap(root, "2026-11-09", "2026-11-16", shared_only=True)["added"] == []


def test_record_lesson_confirms_and_retires_the_line_it_replaced(root):
    old = k.record_lesson(root, target="learnings/drafter.md", line="- 2026-11-01: Old rule. (Michael)",
                          source="michael: DM 2026-11-01 09:00, old rule", today="2026-11-01")
    new = k.record_lesson(root, target="learnings/drafter.md", line="- 2026-11-16: New rule. (Michael)",
                          old="- 2026-11-01: Old rule. (Michael)", source="card:a-8d7b4354", today="2026-11-16")
    assert new["status"] == "confirmed" and new["topic"] == "lesson-drafter"
    assert k.find(root, old["id"])["status"] == "retired"


def test_migration_confirms_only_card_saved_lines(root):
    (root / "learnings").mkdir()
    (root / "learnings" / "coordinator.md").write_text(
        "# coordinator learnings\n\n- 2026-11-08: Check the people file first. (Michael)\n"
        "- 2026-11-15: Use the Edit tool in timer runs. (Michael)\n- 2026-11-10: Probably likes mornings. (assumed)\n",
        encoding="utf-8")
    (root / "state" / "proposed-lessons.md").write_text(
        '- [p-1] target: learnings/coordinator.md\n  new_line: "- 2026-11-15: Use the Edit tool in timer runs. '
        '(Michael)"\n', encoding="utf-8")
    plan = k.migrate_learnings(root, apply=True, today="2026-11-16")
    status = {p["title"]: p["status"] for p in plan}
    assert status == {"Check the people file first": "unconfirmed", "Use the Edit tool in timer runs": "confirmed",
                      "Probably likes mornings": "unconfirmed"}
    assert next(p for p in plan if p["status"] == "confirmed")["sources"][0] == "card:a-8d7b4354"
    assert k.migrate_learnings(root, apply=True, today="2026-11-16")  # twice is safe
    assert len(k.load(root)) == 3 and k.problems(root) == []


def test_a_save_tap_also_records_the_lesson(root):
    import lessons
    (root / "learnings").mkdir()
    (root / "learnings" / "drafter.md").write_text("# drafter learnings\n", encoding="utf-8")
    out = lessons.apply({"id": "p-1", "target": "learnings/drafter.md", "new": "- Shorter sign-offs"}, root,
                        today="2026-11-16")
    e = k.find(root, out["knowledge_id"])
    assert e["status"] == "confirmed" and e["sources"][0]["kind"] == "michael" and "p-1" in e["sources"][0]["ref"]


def test_research_findings_land_unconfirmed(root):
    import daily_jobs
    daily_jobs._to_knowledge(root, [{"title": "Agent memory paper", "date": "2026-11-14", "what": "A paper.",
                                     "idea": "Try it.", "url": "https://example.com/paper"}], "2026-11-16")
    [e] = k.load(root)
    assert e["status"] == "unconfirmed" and e["topic"] == "research" and not e["shared"]
    assert e["sources"] == [{"kind": "url", "ref": "https://example.com/paper"}]


def test_the_repos_own_shared_entries_are_valid():
    shared = [e for e in k.load(ROOT) if e["shared"]]
    assert shared, "knowledge/entries/ should not be empty"
    found = [p for p in k.problems(ROOT, shared) if "card" not in p]
    assert found == []
