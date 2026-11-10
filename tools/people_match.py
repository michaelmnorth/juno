"""Match the people in an email or calendar event to people/ profiles, and spot the ones who should have one.

Match order: an attendee or sender email listed in a profile's `emails:` line, then the profile's full name or an
`also called:` alias (Mom, Dad) appearing as whole words in the text, then a first name (or a spelling in the
heading's brackets, like "Sam Rivera (Samuel)") as a best guess. He says "Sam" far more than "Sam Rivera" and has
few duplicates (Michael 2026-11-09). A first name two profiles share comes back on both, marked "ambiguous". An email with no profile that is in Google Contacts comes back as
`"by": "contacts", "file": null`: a person Michael knows who has no profile yet. `--starter` prints the first draft
of that profile from Contacts alone (no model, nothing invented); the coordinator queues it for Michael's yes.

  python tools/people_match.py --attendees "a@x.com,b@y.com" --title "Dinner with Mom"
  python tools/people_match.py --starter "a@x.com"        (or a full name)

Exit codes: 0 ok (possibly no matches), 4 not in Contacts (starter), 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "people"
CONTACTS = ROOT / "data" / "contacts" / "contacts.json"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TITLE_PREFIX = re.compile(r"^(dr|mr|mrs|ms|prof)\.?\s+", re.I)


def profiles(folder: Path = PEOPLE) -> list[dict]:
    out = []
    for path in sorted(folder.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        heading = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), path.stem)
        name = TITLE_PREFIX.sub("", re.sub(r"\s*\(.*?\)", "", heading)).strip()
        emails, aliases = set(), set()
        for line in text.splitlines():
            low = line.lower()
            if low.startswith("- emails:"):
                emails |= {e.lower() for e in EMAIL_RE.findall(line)}
            elif low.startswith("- also called:"):
                aliases |= {a.strip() for a in line.split(":", 1)[1].split(",") if a.strip()}
        firsts = {name.split()[0]} if name.split() else set()
        for part in re.findall(r"\((.*?)\)", heading)[:1]:
            for bit in part.split(";"):
                bit = re.sub(r"^also spelled\s+", "", bit.strip(), flags=re.I)
                if re.fullmatch(r"[A-Z][a-z]+", bit):
                    firsts.add(bit)
        out.append({"file": f"people/{path.name}", "name": name, "emails": emails, "aliases": aliases,
                    "firsts": firsts})
    return out


def _words_in(phrase: str, title: str) -> bool:
    return bool(phrase) and re.search(rf"(?<!\w){re.escape(phrase)}(?:'s)?(?!\w)", title, re.I) is not None


def contacts(store: Path = CONTACTS) -> list[dict]:
    if not store.exists():
        return []
    return json.loads(store.read_text(encoding="utf-8")).get("contacts", [])


def _first_in(first: str, text: str) -> bool:
    return re.search(rf"(?<![\w@.]){re.escape(first)}(?:'s)?(?!\w)", text) is not None


def match(attendees: list[str], title: str, folder: Path = PEOPLE, store: Path = CONTACTS) -> list[dict]:
    wanted = {a.strip().lower() for a in attendees if a.strip()}
    hits, known, rest = [], set(), []
    everyone = profiles(folder)
    for p in everyone:
        known |= p["emails"]
        if wanted & p["emails"]:
            hits.append({"file": p["file"], "name": p["name"], "by": "email"})
        elif _words_in(p["name"], title) or any(_words_in(a, title) for a in p["aliases"]):
            hits.append({"file": p["file"], "name": p["name"], "by": "title"})
        else:
            rest.append(p)
    for p in rest:  # best guess on a capitalized first name; case matters so "max effort" isn't Max
        said = sorted(f for f in p["firsts"] if _first_in(f, title))
        if said:
            shared = sum(1 for q in everyone if said[0] in q["firsts"]) > 1
            hits.append({"file": p["file"], "name": p["name"], "by": "first_name", **({"ambiguous": True} if shared else {})})
    left = wanted - known
    for c in contacts(store) if left else []:
        mine = {e["address"] for e in c["emails"]} & left
        if mine and c["name"]:
            hits.append({"file": None, "name": c["name"], "by": "contacts", "email": sorted(mine)[0]})
            left -= mine
    return hits


def slug(name: str) -> str:
    name = TITLE_PREFIX.sub("", re.sub(r"\s*\(.*?\)", "", name)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "person"


def starter(query: str, store: Path = CONTACTS) -> dict | None:
    """A first-draft profile from Contacts only, in the people/README.md shape. confirmed: no until Michael says."""
    q = query.strip().lower()
    everyone = contacts(store)
    hit = next((c for c in everyone if q in {e["address"] for e in c["emails"]}), None) or \
        next((c for c in everyone if c["name"].lower() == q), None)
    if not hit:
        return None
    lines = [f"# {hit['name']}",
             "- relationship: unknown (ask Michael)" + (f"; Contacts says \"{hit['title'] or hit['org']}\""
                                                        if hit["title"] or hit["org"] else ""),
             "- confirmed: no"]
    if hit["nickname"]:
        lines.append(f"- also called: {hit['nickname']}")
    lines.append("- emails: " + ("; ".join(e["address"] for e in hit["emails"]) or "none in Contacts"))
    if hit["phones"]:
        lines.append("- phone: in Google Contacts")
    for a in hit["addresses"][:1]:
        lines.append(f"- address: {a['text']} (Contacts{', ' + a['type'] if a['type'] else ''})")
    lines += ["", "## Dates", f"- birthday: {hit['birthday']} (Contacts)" if hit["birthday"] else "- birthday: unknown.",
              "", "## Interests and tastes (gift-useful)", "- Nothing known yet.", "", "## Open threads", "- None seen."]
    return {"file": f"people/{slug(hit['name'])}.md", "name": hit["name"], "text": "\n".join(lines) + "\n"}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--attendees", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--starter", default="")
    args = parser.parse_args(argv)
    if args.starter:
        if len(args.starter) > 200:
            print(json.dumps({"error": "input too long", "code": 5}))
            return 5
        found = starter(args.starter)
        print(json.dumps(found or {"error": "not in Google Contacts", "code": 4}, ensure_ascii=False, indent=1))
        return 0 if found else 4
    if len(args.title) > 300 or len(args.attendees) > 4000:
        print(json.dumps({"error": "input too long", "code": 5}))
        return 5
    print(json.dumps(match(args.attendees.split(","), args.title), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
