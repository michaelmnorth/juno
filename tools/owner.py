"""The owner's own email addresses, so none is written into the repo.

Read from me/owner.json (git-ignored; start from me/owner.example.json): {"emails": ["you@example.com"]}.
JUNO_OWNER_EMAILS (comma-separated) overrides it, which is how the tests run. The first address is the one Gmail
drafts are sent from and the Google sign-in suggests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def emails(root: Path = ROOT) -> tuple[str, ...]:
    raw = os.environ.get("JUNO_OWNER_EMAILS")
    if raw is None:
        path = root / "me" / "owner.json"
        found = json.loads(path.read_text(encoding="utf-8-sig")).get("emails", []) if path.exists() else []
    else:
        found = raw.split(",")
    return tuple(e.strip().lower() for e in found if str(e).strip())


def primary(root: Path = ROOT) -> str:
    return next(iter(emails(root)), "")
