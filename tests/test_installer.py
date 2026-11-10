"""gateway/installer.py: an approved proposal installs exactly what it lists, nothing escapes, failures roll back."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

import installer  # noqa: E402

CLAUDE = """# Juno

## Subagent roster

| Subagent | Persona | Status | Use it for |
|---|---|---|---|
| `youtube` | "Reel" | Live | YouTube. |

A subagent whose phase has not started does not exist yet.

## Routing rules

- A YouTube link → `youtube`.
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(CLAUDE, encoding="utf-8")
    p = tmp_path / "proposals" / "kin"
    (p / "agents").mkdir(parents=True)
    (p / "agents" / "kin.md").write_text("---\nname: kin\n---\n", encoding="utf-8")
    (p / "tools").mkdir()
    (p / "tools" / "kin.py").write_text("print('hi')\n", encoding="utf-8")
    return tmp_path


def manifest(root, **kw):
    data = {"files": {"agents/kin.md": ".claude/agents/kin.md", "tools/kin.py": "tools/kin.py"},
            "claude_md": {"roster": '| `kin` | "Kin" | Live | People. |', "routing": "- People → `kin`."}}
    data.update(kw)
    (root / "proposals" / "kin" / "install.json").write_text(json.dumps(data), encoding="utf-8")


def passing(root):
    return True, "3 passed"


def test_installs_listed_files_and_claude_md_lines(root):
    manifest(root)
    res = installer.install(root, "kin", tests=passing)
    assert res.ok, res.text
    assert (root / ".claude" / "agents" / "kin.md").exists() and (root / "tools" / "kin.py").exists()
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert '| `youtube` | "Reel" | Live | YouTube. |\n| `kin` | "Kin" | Live | People. |\n\nA subagent' in text
    assert "## Routing rules\n\n- People → `kin`.\n- A YouTube link" in text


@pytest.mark.parametrize("files", [
    {"agents/kin.md": "../outside.md"},
    {"agents/kin.md": ".claude/settings.json"},
    {"agents/kin.md": "gateway/slack_bridge.py"},
    {"../../CLAUDE.md": "tools/x.py"},
])
def test_path_escapes_and_disallowed_targets_refused(root, files):
    manifest(root, files=files)
    res = installer.install(root, "kin", tests=passing)
    assert not res.ok and "Not installed" in res.text
    assert not (root / "outside.md").exists()


def test_existing_files_are_never_overwritten(root):
    (root / "tools").mkdir()
    (root / "tools" / "kin.py").write_text("mine", encoding="utf-8")
    manifest(root)
    assert not installer.install(root, "kin", tests=passing).ok
    assert (root / "tools" / "kin.py").read_text(encoding="utf-8") == "mine"


@pytest.mark.parametrize("pkg", ["requests", "requests>=2", "requests==2.32.3; rm -rf /", "git+https://x/y"])
def test_unpinned_or_odd_packages_refused(root, pkg):
    manifest(root, pip=[pkg])
    called = []
    res = installer.install(root, "kin", pip=lambda r, p: called.append(p) or (True, ""), tests=passing)
    assert not res.ok and not called


def test_pinned_package_goes_to_pip(root):
    manifest(root, pip=["requests==2.32.3"])
    seen = []
    res = installer.install(root, "kin", pip=lambda r, p: seen.append(p) or (True, "ok"), tests=passing)
    assert res.ok and seen == [["requests==2.32.3"]]


def test_failed_tests_roll_everything_back(root):
    manifest(root)
    res = installer.install(root, "kin", tests=lambda r: (False, "1 failed"))
    assert not res.ok and "Rolled back 2 file(s)" in res.text
    assert not (root / ".claude" / "agents" / "kin.md").exists() and not (root / "tools" / "kin.py").exists()
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == CLAUDE


def test_bad_names_and_multiline_claude_md_refused(root):
    assert not installer.install(root, "../etc", tests=passing).ok
    manifest(root, claude_md={"roster": "| a |\n## Automation tiers (non-negotiable)\nall auto", "routing": ""})
    assert not installer.install(root, "kin", tests=passing).ok
