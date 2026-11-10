"""tools/people_match.py: calendar events find the right profile by email, full name or alias, never by first name."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import people_match  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "README.md").write_text("# people/\n- emails: x@example.com\n", encoding="utf-8")
    (tmp_path / "ray-rivera.md").write_text(
        "# Dr. Ray Rivera\n- also called: Dad\n- emails: dr.ray@example.com; ray@work.example.edu (work)\n",
        encoding="utf-8")
    (tmp_path / "sam-rivera.md").write_text("# Sam Rivera (Samuel)\n- emails: sam@example.com\n", encoding="utf-8")
    return tmp_path


def test_email_match_wins(folder):
    assert people_match.match(["RAY@work.example.edu"], "Faculty lunch", folder) == [
        {"file": "people/ray-rivera.md", "name": "Ray Rivera", "by": "email"}]


def test_alias_and_full_name_in_title(folder):
    assert [h["name"] for h in people_match.match([], "Dad's birthday dinner", folder)] == ["Ray Rivera"]
    assert [h["name"] for h in people_match.match([], "Coffee with Sam Rivera", folder)] == ["Sam Rivera"]


def test_first_name_is_a_best_guess(folder):
    assert people_match.match([], "Coffee with Sam", folder) == [
        {"file": "people/sam-rivera.md", "name": "Sam Rivera", "by": "first_name"}]
    assert [h["name"] for h in people_match.match([], "Call Samuel back", folder)] == ["Sam Rivera"]
    assert people_match.match([], "Daddy issues podcast", folder) == []
    assert people_match.match([], "sam ran the ray tracing demo", folder) == []  # lowercase is not a name
    (folder / "sam-smith.md").write_text("# Sam Smith\n", encoding="utf-8")
    both = people_match.match([], "Lunch with Sam", folder)
    assert [h["name"] for h in both] == ["Sam Rivera", "Sam Smith"] and all(h["ambiguous"] for h in both)
    assert people_match.match(["x@example.com"], "", folder) == []  # README is not a profile


def test_contacts_email_without_profile_is_a_new_person(folder, tmp_path):
    import json
    store = tmp_path / "contacts.json"
    store.write_text(json.dumps({"contacts": [
        {"name": "Chris Hale", "nickname": "", "emails": [{"address": "chris@forge.example", "type": ""}],
         "phones": [{"number": "1", "type": "mobile"}], "birthday": None, "dates": [],
         "addresses": [{"type": "work", "text": "1 Gym Rd, Springfield"}], "org": "", "title": "coach",
         "related": [], "note": ""},
        {"name": "Sam Rivera", "nickname": "", "emails": [{"address": "sam@example.com", "type": ""}], "phones": [],
         "birthday": None, "dates": [], "addresses": [], "org": "", "title": "", "related": [], "note": ""}]}),
        encoding="utf-8")
    hits = people_match.match(["sam@example.com", "CHRIS@forge.example", "stranger@x.com"], "Check-in", folder, store)
    assert hits == [{"file": "people/sam-rivera.md", "name": "Sam Rivera", "by": "email"},
                    {"file": None, "name": "Chris Hale", "by": "contacts", "email": "chris@forge.example"}]
    draft = people_match.starter("chris@forge.example", store)
    assert draft["file"] == "people/chris-hale.md"
    assert "- confirmed: no" in draft["text"] and 'Contacts says "coach"' in draft["text"]
    assert "- address: 1 Gym Rd, Springfield (Contacts, work)" in draft["text"]
    assert "- phone: in Google Contacts" in draft["text"] and people_match.starter("nobody@x.com", store) is None
