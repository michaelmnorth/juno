"""Trust label for an email address, decided in code (docs/04 proposal 2), so the model never grades its own inputs.

  michael   one of Michael's own addresses (still email: never an instruction, see CLAUDE.md)
  known     listed in a people/ profile's `emails:` line
  contact   in Google Contacts (data/contacts/contacts.json) but no profile
  unknown   anyone else

  python tools/trust.py label a@x.com "Sam <sam@y.com>" ...

Prints {"address": "label", ...}. Exit codes: 0 ok, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import owner  # noqa: E402
from people_match import profiles  # noqa: E402

ME = owner.emails()
ORDER = ("unknown", "contact", "known", "michael")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
OK, BAD_INPUT = 0, 5


def directory(root: Path = ROOT) -> dict[str, str]:
    labels: dict[str, str] = {}
    path = root / "data" / "contacts" / "contacts.json"
    if path.exists():
        for c in json.loads(path.read_text(encoding="utf-8")).get("contacts", []):
            for e in c.get("emails", []):
                labels[e["address"].lower()] = "contact"
    if (root / "people").is_dir():
        for p in profiles(root / "people"):
            labels.update({e: "known" for e in p["emails"]})
    labels.update({e: "michael" for e in ME})
    return labels


def address(value: str) -> str:
    m = EMAIL_RE.search(value or "")
    return m.group(0).lower() if m else ""


def label(value: str, root: Path = ROOT, known: dict[str, str] | None = None) -> str:
    addr = address(value)
    return (known if known is not None else directory(root)).get(addr, "unknown") if addr else "unknown"


def lowest(values: list[str], root: Path = ROOT) -> str | None:
    """The least trusted label among several addresses; None when there are none."""
    known = directory(root)
    found = [label(v, root, known) for v in values if str(v).strip()]
    return min(found, key=ORDER.index) if found else None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("label").add_argument("addresses", nargs="+")
    args = parser.parse_args(argv)
    known = directory()
    out = {}
    for value in args.addresses:
        addr = address(value)
        if not addr:
            print(json.dumps({"error": f"not an email address: {value[:80]}", "code": BAD_INPUT}))
            return BAD_INPUT
        out[addr] = label(addr, known=known)
    print(json.dumps(out, indent=1))
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
