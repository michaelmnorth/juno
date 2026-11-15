"""A yes in his DM starts a Claude Code cloud session (Michael 2026-11-15), offline: the CLI is a fake."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "gateway", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import approval_policy  # noqa: E402
import build_queue  # noqa: E402
import builds  # noqa: E402

URL = "https://claude.ai/code/session_01AbcDEF234"


def queue(tmp_path, named=False, **kw):
    path = tmp_path / "state" / "build-requests.json"
    return build_queue.add("Remind before Link runs out", "Nudge him at 10 and 25 minutes.", "He said yes",
                           named=named, path=path, env={}, **kw), path


class Launch:
    def __init__(self, url=URL, note="started"):
        self.prompts, self.url, self.note = [], url, note

    def __call__(self, prompt, cwd):
        self.prompts.append(prompt)
        return self.url, self.note


def test_named_yes_starts_the_cloud_session_at_once(tmp_path):
    req, path = queue(tmp_path, named=True)
    launch, cards, events = Launch(), [], []
    lines = builds.process(tmp_path, cards.append, audit=lambda e, entry, note: events.append(e), path=path,
                           launcher=launch)
    assert cards == [] and URL in lines[0] and "draft pull request" in lines[0] and "merging stays with you" in lines[0]
    assert events == ["build_started"] and build_queue.load(path)[0]["status"] == "started"
    prompt = launch.prompts[0]
    assert "DRAFT pull request" in prompt and "Never merge" in prompt and "Never set payments to live" in prompt
    assert "Nudge him at 10 and 25 minutes." in prompt
    assert builds.process(tmp_path, cards.append, path=path, launcher=launch) == []  # never twice


def test_unnamed_request_gets_a_card_and_only_the_tap_starts_it(tmp_path):
    req, path = queue(tmp_path)
    launch, cards = Launch(), []
    assert builds.process(tmp_path, cards.append, path=path, launcher=launch) == []
    entry = cards[0]
    assert entry["action_class"] == "build.start" and not launch.prompts
    assert approval_policy.auto_ok(entry, tmp_path / "state", {"actions": {"build.start": {"mode": "auto"}}}) is None
    blocks = json.dumps(approval_policy.blocks(entry, root=tmp_path))
    assert "Start build" in blocks and "nothing merges without you" in blocks and "Always" not in blocks
    line = builds.tapped(tmp_path, entry, True, path=path, launcher=launch)
    assert URL in line and len(launch.prompts) == 1
    assert builds.tapped(tmp_path, entry, True, path=path, launcher=launch).startswith("That build isn't waiting")


def test_not_now_skips(tmp_path):
    req, path = queue(tmp_path)
    cards = []
    builds.process(tmp_path, cards.append, path=path, launcher=Launch())
    assert builds.tapped(tmp_path, cards[0], False, path=path, launcher=Launch()).startswith("Skipped")
    assert build_queue.load(path)[0]["status"] == "skipped"


def test_failed_start_says_so_plainly(tmp_path):
    req, path = queue(tmp_path, named=True)
    lines = builds.process(tmp_path, [].append, path=path, launcher=Launch(None, "no session link (exit 1): nope"))
    assert lines[0].startswith("I couldn't start") and "Nothing changed" in lines[0]
    assert build_queue.load(path)[0]["status"] == "failed"


def test_queue_refuses_merges_live_money_secrets_and_timer_named(tmp_path):
    path = tmp_path / "q.json"
    for task in ("Build it and merge the PR", "Flip payments to live mode", "Set live: true in payments",
                 "Use key sk_live_abcdefghijkl", "Card 4242 4242 4242 4242"):
        with pytest.raises(build_queue.Bad):
            build_queue.add("Change", task, path=path, env={})
    with pytest.raises(build_queue.Bad):
        build_queue.add("Change", "Wire up a reminder", named=True, path=path, env={"COORDINATOR_UNATTENDED": "1"})
    assert build_queue.add("Change", "Wire up a reminder and merge two helper functions", path=path, env={})


def test_launch_reads_the_link_even_when_the_cli_is_slow(tmp_path):
    def slow(cmd, **kw):
        assert cmd[1] == "--cloud" and "ANTHROPIC_API_KEY" not in kw["env"]
        raise subprocess.TimeoutExpired(cmd, 1, output=f"Creating cloud session...\nView: {URL}?from=cli\n")
    assert builds.launch("brief", tmp_path, run=slow, claude="claude") == (URL, "started")
    done = lambda cmd, **kw: NS(returncode=1, stdout="", stderr="Unable to get organization UUID")  # noqa: E731
    url, note = builds.launch("brief", tmp_path, run=done, claude="claude")
    assert url is None and "organization UUID" in note
