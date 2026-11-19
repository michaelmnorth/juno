"""Usage log per request, the daily rollup, and the two daily lean jobs (Michael 2026-11-15). Offline: the model is
a fake runner that returns what `claude -p --output-format json --json-schema` prints."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "gateway", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import claude_runner  # noqa: E402
import daily_jobs  # noqa: E402
import ping_policy  # noqa: E402
import slack_bridge  # noqa: E402
import usage_report  # noqa: E402

NOW = datetime(2026, 11, 15, 11, 40, tzinfo=timezone.utc)  # 06:40 Eastern; yesterday is 2026-11-14
DAY = "2026-11-14"


def row(job, cost, at="2026-11-14T15:00:00+00:00", model="claude-sonnet-5-5", tokens=None, turns=3, what="",
        **extra):
    return {"at": at, "job": job, "model": model, "cost_usd": cost, "session_total_usd": cost,
            "tokens": tokens or {"in": 1000, "out": 200, "cache_read": 4000, "cache_write": 0}, "turns": turns,
            "is_error": False, "what": what, **extra}


def write_rows(root: Path, rows):
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "costs.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def result(obj, error=False):
    return claude_runner.RunResult(text="", session_id="s", is_error=error, cost_usd=0.01, duration_ms=10,
                                   raw={"structured_output": obj, "subtype": "success"})


class FakeRun:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, prompt, **kw):
        self.calls.append({"prompt": prompt, **kw})
        return result(self.answers.pop(0))


# --- the per-request line ------------------------------------------------------------------------

def test_cli_run_logs_what_it_was_for(tmp_path):
    res = claude_runner.RunResult(text="ok", session_id="s1", is_error=False, cost_usd=0.02, duration_ms=5,
                                  raw={"usage": {"input_tokens": 10, "output_tokens": 2}, "num_turns": 2})
    claude_runner.log_cost(tmp_path, "dm-converse", "m", res, what="calendar.hold " + "x" * 300)
    line = json.loads((tmp_path / "state" / "costs.jsonl").read_text(encoding="utf-8"))
    assert line["what"].startswith("calendar.hold") and len(line["what"]) <= claude_runner.WHAT_MAX
    claude_runner.log_cost(tmp_path, "sweep", "m", res)
    last = json.loads((tmp_path / "state" / "costs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert last["what"] == "sweep"  # no description: the job name stands in


def test_lean_run_grants_its_web_tools():
    res = claude_runner.run("hi", dry_run=True, lean_system="S", builtin_tools=("WebSearch",),
                            allowed_tools=("WebSearch",), max_turns=8)
    cmd = res.command
    assert cmd[cmd.index("--allowedTools") + 1] == "WebSearch"
    assert cmd[cmd.index("--max-turns") + 1] == "8"


# --- the rollup ----------------------------------------------------------------------------------

def test_rollup_counts_each_run_once_and_says_what_was_done():
    rows = [row("dm-router", 0.001, model="claude-haiku-5-5", what="dm-router"),
            row("dm-converse", 0.05, what="calendar.hold"),
            {**row("dm-v2", 0.0, what="calendar.hold: Held Gym Friday 4pm", tokens={}), "summary": True,
             "parts_usd": 0.051},
            row("sweep", 0.40, model="claude-opus-5-5", turns=45),
            {"at": "2026-11-14T16:00:00+00:00", "job": "old", "cost_usd": 9.0},  # legacy running total: no cost
            row("sweep", 1.0, at="2026-11-15T15:00:00+00:00")]  # another day
    r = usage_report.rollup(rows, DAY)
    assert r["runs"] == 4 and r["requests"] == 1 and r["api_price_usd"] == 0.451
    assert r["tokens"]["in"] == 3000 and r["by_job"][0]["job"] == "sweep"
    assert r["done"] == [{"at": rows[2]["at"], "what": "calendar.hold: Held Gym Friday 4pm"}]
    assert any("sweep ran on Opus" in h for h in r["hints"]) and any("40+ turns" in h for h in r["hints"])
    assert "Max plan" in r["billing"]


def test_rollup_flags_low_cache_reuse():
    cold = {"in": 9000, "out": 100, "cache_read": 1000, "cache_write": 0}
    r = usage_report.rollup([row("dm", 0.1, tokens=cold) for _ in range(3)], DAY)
    assert any("from cache" in h for h in r["hints"])


def test_eastern_days_and_week(tmp_path):
    write_rows(tmp_path, [row("sweep", 0.1, at="2026-11-15T03:00:00+00:00"),  # 22:00 Nov 14 in New York
                          row("sweep", 0.2, at="2026-11-13T15:00:00+00:00")])
    rows = usage_report.load(tmp_path)
    assert usage_report.rollup(rows, DAY)["runs"] == 1
    week = usage_report.week(rows, DAY)
    assert [d["date"] for d in week][-1] == DAY and len(week) == 7
    assert [d["runs"] for d in week][-2:] == [1, 1]


def test_cli_writes_the_day(tmp_path, capsys):
    write_rows(tmp_path, [row("sweep", 0.1)])
    assert usage_report.main(["day", "--date", DAY, "--write"], root=tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["runs"] == 1
    assert (tmp_path / "state" / "usage" / f"{DAY}.json").exists()


def test_v2_summary_line_on_max_is_not_counted_twice(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    from v2 import config
    from v2.converse import Engine
    monkeypatch.setattr(config, "BACKEND", "max")
    eng = NS(root=tmp_path, store=NS(ledger_rows=lambda run_id: []))
    run = NS(run_id="r-1", cost=0.05, calls=2, intent="calendar.hold", done=["Held Gym Friday 4pm"])
    Engine._log_cost(eng, run)
    line = json.loads((tmp_path / "state" / "costs.jsonl").read_text(encoding="utf-8"))
    assert line["cost_usd"] == 0.0 and line["parts_usd"] == 0.05 and line["summary"] is True
    assert line["what"] == "calendar.hold: Held Gym Friday 4pm"


# --- token optimizer -----------------------------------------------------------------------------

SUGGEST = {"job": "sweep", "change": "Run the sweep on Haiku", "why": "Opus on a sorting job", "saves": "~60%"}


def test_optimizer_is_quiet_with_no_runs(tmp_path):
    run = FakeRun()
    assert daily_jobs.token_optimizer(run, tmp_path, NOW) is None and run.calls == []
    assert (tmp_path / "state" / "usage" / f"{DAY}.json").exists()


def test_optimizer_haiku_first_and_posts_when_worth_it(tmp_path):
    write_rows(tmp_path, [row("sweep", 0.4, model="claude-opus-5-5")])
    run = FakeRun({"suggestions": [SUGGEST], "deep_dive": "", "notify": True})
    text = daily_jobs.token_optimizer(run, tmp_path, NOW)
    kw = run.calls[0]
    assert len(run.calls) == 1 and kw["model"] == ping_policy.HAIKU and kw["builtin_tools"] == ()
    assert kw["job"] == "token-optimizer" and kw["json_schema"] == daily_jobs.OPTIMIZER_SCHEMA
    packet = json.loads(kw["prompt"])
    assert packet["day"]["date"] == DAY and "recent_suggestions" in packet
    assert "Run the sweep on Haiku" in text and "Max plan" in text and "API credits" not in text
    log = (tmp_path / "state" / "usage" / "suggestions.jsonl").read_text(encoding="utf-8")
    assert json.loads(log)["change"] == "Run the sweep on Haiku"


def test_optimizer_deep_dive_only_when_flagged(tmp_path):
    write_rows(tmp_path, [row("research", 0.9, what="scan"), row("sweep", 0.1)])
    run = FakeRun({"suggestions": [], "deep_dive": "research", "notify": False},
                  {"suggestions": [SUGGEST], "deep_dive": "", "notify": False})
    assert daily_jobs.token_optimizer(run, tmp_path, NOW) is None  # not worth a message
    second = run.calls[1]
    assert second["model"] == ping_policy.SONNET and second["lean_system"] == daily_jobs.DEEP_SYSTEM
    rows = json.loads(second["prompt"])["rows"]
    assert rows and all(r["what"] == "scan" for r in rows)
    assert (tmp_path / "state" / "usage" / "suggestions.jsonl").exists()  # still kept for the weekly look


def test_optimizer_never_offers_api_credits():
    assert "Never suggest API credits" in daily_jobs.OPTIMIZER_SYSTEM


# --- research scan -------------------------------------------------------------------------------

ITEM = {"title": "Agent wallets", "date": "2026-11-14", "what": "one-time cards", "idea": "pay with a tap",
        "url": "https://example.com/a"}


def test_research_scan_uses_only_web_tools_and_skips_what_it_saw(tmp_path):
    run = FakeRun({"items": [ITEM, {**ITEM, "url": "javascript:alert(1)"}], "notify": True},
                  {"items": [ITEM], "notify": True})
    text = daily_jobs.research_scan(run, tmp_path, NOW)
    kw = run.calls[0]
    assert kw["builtin_tools"] == ("WebSearch", "WebFetch") and kw["allowed_tools"] == ("WebSearch", "WebFetch")
    assert "mcp_config" not in kw and kw["model"] == ping_policy.SONNET
    assert "Agent wallets" in text and "javascript" not in text
    assert (tmp_path / "state" / "research" / "2026-11-15.md").exists()
    assert daily_jobs.research_scan(run, tmp_path, NOW) is None  # the same link again is not news
    assert "https://example.com/a" in json.loads(run.calls[1]["prompt"])["already_seen"]


def test_research_scan_quiet_on_a_failed_run(tmp_path):
    run = lambda prompt, **kw: result(None, error=True)  # noqa: E731
    assert daily_jobs.research_scan(run, tmp_path, NOW) is None


def test_lift_video_scan_appends_to_its_living_file(tmp_path):
    item = {**ITEM, "title": "Auto trim with pose", "url": "https://example.com/trim"}
    run = FakeRun({"items": [item], "notify": True}, {"items": [{**item, "url": "https://example.com/more"}],
                                                     "notify": False})
    text = daily_jobs.run_job("lift-video-scan", run, tmp_path, NOW)
    kw = run.calls[0]
    assert kw["job"] == "lift-video-scan" and kw["allowed_tools"] == ("WebSearch", "WebFetch")
    assert kw["lean_system"] == daily_jobs.LIFT_VIDEO_SYSTEM and "lift clips" in text
    folder = tmp_path / "state" / "research" / "lift-video"
    assert daily_jobs.run_job("lift-video-scan", run, tmp_path, NOW) is None  # nothing that changes the plan
    living = (folder / "LIVING.md").read_text(encoding="utf-8")
    assert living.count("# Lift video clips") == 1 and "example.com/trim" in living and "example.com/more" in living
    assert not (tmp_path / "state" / "research" / "seen.json").exists()  # its own seen list, apart from the main scan


# --- schedule ------------------------------------------------------------------------------------

def test_daily_jobs_are_scheduled_and_lean():
    jobs = {j["job"]: j["trigger"] for j in slack_bridge.anchor_schedule(slack_bridge.load_proactivity(ROOT))}
    assert jobs["token-optimizer"]["hour"] == 6 and jobs["research-scan"]["hour"] == 12
    assert jobs["lift-video-scan"]["hour"] == 12 and jobs["lift-video-scan"]["minute"] == 40
    assert set(daily_jobs.JOBS) <= set(slack_bridge.LEAN_JOBS)
    for job in daily_jobs.JOBS:
        assert job in ping_policy.JOB_MODELS and job in ping_policy.JOB_LIMITS
