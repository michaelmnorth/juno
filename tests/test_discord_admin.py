"""tools/discord_admin.py: channels and categories only, nothing deleted, gated by me/automation.yaml."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

import discord_admin as da


class FakeRest:
    def __init__(self):
        self.calls = []
        self.chans = [{"id": "c1", "name": "Projects", "type": 4, "position": 0},
                      {"id": "t1", "name": "general", "type": 0, "parent_id": None, "position": 0, "topic": "hi"},
                      {"id": "t2", "name": "lifting", "type": 0, "parent_id": "c1", "position": 1}]

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/users/@me/guilds":
            return [{"id": "g1", "name": "Michael's server"}]
        if method == "GET":
            return self.chans
        if method == "POST":
            made = {"id": f"n{len(self.calls)}", **body}
            self.chans.append(made)
            return made
        return {}


def root_with(tmp_path, mode):
    (tmp_path / "me").mkdir()
    (tmp_path / "me" / "automation.yaml").write_text(
        f"actions:\n  discord.channel: {{mode: {mode}}}\n", encoding="utf-8")
    return tmp_path


def test_list_reads_without_any_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("JUNO_DISCORD_GUILD", raising=False)
    out = da.run(NS(cmd="list"), FakeRest(), tmp_path)
    assert {c["name"]: c["category"] for c in out["channels"]}["lifting"] == "Projects"


def test_writes_refuse_while_the_class_is_ask(tmp_path, monkeypatch):
    monkeypatch.delenv("JUNO_DISCORD_GUILD", raising=False)
    rest = FakeRest()
    with pytest.raises(da.AdminError) as exc:
        da.run(NS(cmd="create", name="x", kind="text", category=None, topic=None), rest, root_with(tmp_path, "ask"))
    assert exc.value.code == 4 and not [c for c in rest.calls if c[0] != "GET"]


def test_create_rename_topic_archive_and_audit(tmp_path, monkeypatch):
    monkeypatch.delenv("JUNO_DISCORD_GUILD", raising=False)
    root, rest = root_with(tmp_path, "auto_notify"), FakeRest()
    out = da.run(NS(cmd="create", name="Meal Prep", kind="text", category="Projects", topic="Sunday batch"), rest, root)
    assert out["name"] == "meal-prep" and rest.calls[-1][2] == {"name": "meal-prep", "type": 0, "parent_id": "c1",
                                                              "topic": "Sunday batch"}
    da.run(NS(cmd="rename", channel="#lifting", to="Powerlifting"), rest, root)
    assert rest.calls[-1] == ("PATCH", "/channels/t2", {"name": "powerlifting"})
    da.run(NS(cmd="topic", channel="general", text="Anything"), rest, root)
    assert rest.calls[-1] == ("PATCH", "/channels/t1", {"topic": "Anything"})
    da.run(NS(cmd="archive", channel="t1"), rest, root)
    made_archive = [c for c in rest.calls if c[0] == "POST" and c[2] == {"name": "Archive", "type": 4}]
    assert made_archive and rest.calls[-1][0] == "PATCH" and "parent_id" in rest.calls[-1][2]
    assert not [c for c in rest.calls if c[0] == "DELETE"]  # nothing is ever deleted
    lines = [json.loads(x) for x in (root / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["event"] for x in lines] == ["discord.create", "discord.rename", "discord.topic", "discord.archive"]


def test_bad_names_and_ambiguity_are_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("JUNO_DISCORD_GUILD", raising=False)
    root, rest = root_with(tmp_path, "auto"), FakeRest()
    with pytest.raises(da.AdminError):
        da.run(NS(cmd="create", name="@everyone", kind="text", category=None, topic=None), rest, root)
    rest.chans.append({"id": "t3", "name": "general", "type": 2, "position": 2})
    with pytest.raises(da.AdminError) as exc:
        da.run(NS(cmd="rename", channel="general", to="x"), rest, root)
    assert "use the id" in str(exc.value)
