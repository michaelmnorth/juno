"""tools/people_queue.py: people notes wait for Michael's Save tap, then code writes exactly that line."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "gateway"))

import cards  # noqa: E402
import people_queue as pq  # noqa: E402

COACH = """# Chris Hale
- relationship: coach (stated)
- confirmed: yes
- last contact: 2026-10-01 (Michael)

## Dates
- birthday: unknown.

## Life now
- None seen.

## Open threads
- None seen.
"""


@pytest.fixture
def home(tmp_path):
    (tmp_path / "people").mkdir()
    (tmp_path / "people" / "chris-hale.md").write_text(COACH, encoding="utf-8")
    store = tmp_path / "contacts.json"
    store.write_text(json.dumps({"contacts": [
        {"name": "Alex Lee", "nickname": "", "emails": [{"address": "alex@x.com", "type": ""}], "phones": [],
         "birthday": "--04-02", "dates": [], "addresses": [], "org": "", "title": "friend", "related": [],
         "note": ""}]}), encoding="utf-8")
    return tmp_path, tmp_path / "state" / "people-queue.jsonl", store


def test_line_waits_then_save_writes_it_in_its_section(home):
    root, queue, store = home
    e = pq.add(file="people/chris-hale.md", line="- Moving his gym to Riverton in December", section="Life now",
               source="Michael 2026-11-09", queue=queue, folder=root / "people", store=store)
    again = pq.add(file="people/chris-hale.md", line="- Moving his gym to Riverton in December",
                   section="Life now", source="Michael 2026-11-09", queue=queue, folder=root / "people", store=store)
    assert again["id"] == e["id"] and len(pq.pending(queue)) == 1  # no duplicate card
    assert "Chris Hale" in (root / "people" / "chris-hale.md").read_text() and "Riverton" not in \
        (root / "people" / "chris-hale.md").read_text()  # nothing written before the tap
    pq.apply(e["id"], queue, root)
    text = (root / "people" / "chris-hale.md").read_text(encoding="utf-8")
    assert "## Life now\n- Moving his gym to Riverton in December (Michael 2026-11-09)\n" in text  # placeholder replaced
    assert pq.pending(queue) == []
    with pytest.raises(pq.QueueError):
        pq.apply(e["id"], queue, root)  # a second tap does nothing


def test_field_line_replaces_the_field(home):
    root, queue, store = home
    e = pq.add(file="people/chris-hale.md", line="- last contact: 2026-11-09 (calendar: Check-in with Chris)",
               source="calendar 2026-11-09", queue=queue, folder=root / "people", store=store)
    pq.apply(e["id"], queue, root)
    text = (root / "people" / "chris-hale.md").read_text(encoding="utf-8")
    assert text.count("- last contact:") == 1 and "- last contact: 2026-11-09 (calendar: Check-in with Chris)" in text


def test_new_profile_from_contacts_and_guards(home):
    root, queue, store = home
    e = pq.add(new="alex@x.com", source="mail 2026-11-09", queue=queue, folder=root / "people", store=store)
    assert e["kind"] == "new" and e["file"] == "people/alex-lee.md"
    assert pq.label(e) == "New profile: *Alex Lee* (friend), from your contacts"
    pq.apply(e["id"], queue, root)
    assert "- confirmed: no" in (root / "people" / "alex-lee.md").read_text(encoding="utf-8")
    assert "already exists" in pq.add(new="alex@x.com", source="mail", queue=queue, folder=root / "people",
                                      store=store)["note"]
    for bad in ({"file": "../me/profile.md", "line": "- x"}, {"file": "people/chris-hale.md", "line": "no dash"},
                {"file": "people/nobody.md", "line": "- x"}):
        with pytest.raises(pq.QueueError):
            pq.add(source="mail", queue=queue, folder=root / "people", store=store, **bad)
    with pytest.raises(pq.QueueError):
        pq.add(new="stranger@x.com", source="mail", queue=queue, folder=root / "people", store=store)


def test_card_has_save_and_skip_per_entry(home):
    root, queue, store = home
    e = pq.add(file="people/chris-hale.md", line="- Likes cold brew", section="Interests and tastes (gift-useful)",
               source="Michael 2026-11-09", queue=queue, folder=root / "people", store=store)
    msg = cards.people_card(pq.pending(queue), pq.label)
    acts = [b for b in msg.blocks if b["type"] == "actions"]
    assert [x["action_id"] for x in acts[0]["elements"]] == ["people_save", "people_skip"]
    assert acts[0]["elements"][0]["value"] == e["id"]
    assert "*Chris Hale:* Likes cold brew" in json.dumps(msg.blocks)
    assert cards.people_card([], pq.label) is None
