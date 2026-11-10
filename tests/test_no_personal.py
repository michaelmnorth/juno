"""The repo is public: no name from a local people/ profile, no owner address and none of the owner's private words
(me/owner.json `private_words`, for example the employer's name) may sit in a tracked file.

Runs only where the personal layer exists (Michael's PC); a fresh clone has neither and skips. The names come from
profile file names only, so the test never reads a profile.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMON = {"see", "occasions", "mom", "dad", "max", "the", "and"}  # file-name parts that are ordinary words
PUBLIC_ON_PURPOSE = {"docs/index.html", "docs/privacy.html"}  # the Google sign-in home and privacy pages name him


def personal_markers() -> tuple[set[str], set[str]]:
    names = {part.capitalize() for f in (ROOT / "people").glob("*.md") if f.name != "README.md"
             for part in f.stem.split("-") if len(part) > 2 and part not in COMMON}
    path = ROOT / "me" / "owner.json"
    owner = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    names |= {w for w in owner.get("private_words", []) if w.strip()}
    return names, {e.lower() for e in owner.get("emails", [])}


def test_no_personal_names_or_addresses_in_tracked_files():
    names, emails = personal_markers()
    if not names and not emails:
        pytest.skip("no personal layer here")
    word = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\b") if names else None
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    hits = []
    for rel in filter(None, tracked):
        if rel in PUBLIC_ON_PURPOSE:
            continue
        try:
            text = (ROOT / rel).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if (word and word.search(line)) or any(e in line.lower() for e in emails):
                hits.append(f"{rel}:{n}")
    assert not hits, "Personal details in tracked files (move them to a git-ignored place): " + ", ".join(hits[:20])
