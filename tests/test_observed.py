"""Offline tests for tools/observed.py: confidence, stale retirement, promote candidates, duplicates, size."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import observed  # noqa: E402

TODAY = date(2026, 11, 8)


def notes(tmp_path: Path, lines: list[str], name: str = "preferences.md") -> Path:
    (tmp_path / name).write_text("# Observed\n\n## Interests\n" + "\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "changelog.md").write_text("# What Juno picked up\n\n", encoding="utf-8")
    return tmp_path


def test_parse_line_and_confidence():
    n = observed.parse_line("- [interests] Into watches lately (seen 2, last 2026-11-07)")
    assert n == {"context": "interests", "text": "Into watches lately", "seen": 2, "last": "2026-11-07",
                 "confidence": "medium", "status": "pending"}
    assert observed.parse_line("- [juno] Short replies (seen 4, last 2026-01-01, promoted)")["status"] == "promoted"
    assert observed.parse_line("- free text with no meta") is None


def test_stale_by_confidence_and_promoted_never_expire(tmp_path):
    folder = notes(tmp_path, [
        "- [a] low and old (seen 1, last 2026-09-01)",       # 68 days, low -> stale
        "- [b] medium and recent-ish (seen 2, last 2026-09-20)",  # 49 days, medium -> keep
        "- [c] high but ancient (seen 5, last 2026-05-01)",   # 191 days, high -> stale
        "- [d] promoted and ancient (seen 5, last 2025-01-01, promoted)",
        "- [e] high and fresh (seen 3, last 2026-11-01)",
    ])
    out = observed.scan(folder, TODAY)
    assert [n["context"] for n in out["stale"]] == ["a", "c"]
    assert [n["context"] for n in out["promote"]] == ["e"]


def test_duplicates_only_within_same_context(tmp_path):
    folder = notes(tmp_path, [
        "- [interests] Into mechanical watches lately (seen 1, last 2026-11-07)",
        "- [interests] Into watches lately, mechanical ones (seen 1, last 2026-11-08)",
        "- [evenings] Into watches lately (seen 1, last 2026-11-08)",
    ])
    dups = observed.scan(folder, TODAY)["duplicates"]
    assert len(dups) == 1 and dups[0]["lines"] == [4, 5]


def test_size_warning_and_unparsed(tmp_path):
    folder = notes(tmp_path, ["- [x] " + "y" * 6500 + " (seen 1, last 2026-11-08)", "- loose line"])
    out = observed.scan(folder, TODAY)
    assert out["files"][0]["over_warn"] is True
    assert out["unparsed"][0]["text"] == "- loose line"


def test_retire_dry_run_then_apply(tmp_path):
    folder = notes(tmp_path, ["- [a] old guess (seen 1, last 2026-08-01)",
                              "- [b] keeps (seen 1, last 2026-11-01)"])
    assert len(observed.retire(folder, TODAY, apply=False)) == 1
    assert "old guess" in (folder / "preferences.md").read_text(encoding="utf-8")
    observed.retire(folder, TODAY, apply=True)
    kept = (folder / "preferences.md").read_text(encoding="utf-8")
    assert "old guess" not in kept and "keeps" in kept and kept.startswith("# Observed")
    assert "[a] old guess" in (folder / "retired.md").read_text(encoding="utf-8")
    assert "| preferences.md | retired | dropped an old guess: old guess" in (
        folder / "changelog.md").read_text(encoding="utf-8")
    assert observed.retire(folder, TODAY, apply=True) == []
