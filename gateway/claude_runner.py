"""Run the coordinator through the Claude Code CLI (`claude -p`) and return its reply.

Why the CLI and not the Agent SDK yet: `claude -p` draws on the subscription and is documented for scripts, so Phase 1
needs no API key. Phase 5 adds an SDK backend behind the same `run()` signature.

Every run happens in the coordinator folder so CLAUDE.md, .claude/agents, skills, hooks and settings all apply.
Unattended runs (timers) set COORDINATOR_UNATTENDED=1, which the memory-write hook enforces, and disable auto memory.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The bridge needs these to reach Slack, 1Password and Google. Claude runs and their tools never do.
# ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN too: with either set, Claude Code bills the API instead of the Max plan login.
SECRET_ENV_PREFIXES = ("SLACK_", "DISCORD_", "OP_", "GOOGLE_", "JUNO_V2_API_KEY", "ANTHROPIC_API_KEY",
                       "ANTHROPIC_AUTH_TOKEN")


def child_env() -> dict[str, str]:
    """Copy the environment for a Claude run, leaving out the bridge's secrets (case-insensitive for Windows)."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(SECRET_ENV_PREFIXES)}


@dataclass
class RunResult:
    text: str
    session_id: str | None
    is_error: bool
    cost_usd: float | None = None
    duration_ms: int | None = None
    raw: dict = field(default_factory=dict)
    command: list[str] = field(default_factory=list)


def find_claude(explicit: str | None = None) -> str:
    """Locate the claude CLI. Order: explicit arg, CLAUDE_BIN, PATH, common Windows install paths."""
    candidates: list[str | None] = [
        explicit,
        os.environ.get("CLAUDE_BIN"),
        shutil.which("claude"),
        shutil.which("claude.cmd"),
        os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\claude-code\claude.exe"),
        os.path.expanduser("~/.local/bin/claude"),
    ]
    # The Claude desktop app bundles the CLI under a version-pinned folder; take the newest version present.
    bundled = sorted(Path(os.path.expandvars(r"%APPDATA%\Claude\claude-code")).glob("*/*/claude.exe"),
                     key=lambda p: [int(x) if x.isdigit() else x for x in p.parts[-3].split(".")])
    candidates += [str(p) for p in reversed(bundled)]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("claude CLI not found. Set CLAUDE_BIN to its full path.")


def build_command(claude_bin: str, prompt: str, *, resume: str | None = None, permission_mode: str = "acceptEdits",
                  model: str | None = None, max_budget_usd: float | None = None, max_turns: int | None = None,
                  extra: tuple[str, ...] = (), effort: str | None = None) -> list[str]:
    cmd = [claude_bin, "-p", prompt, "--output-format", "json", "--permission-mode", permission_mode]
    if resume:
        cmd += ["--resume", resume]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", f"{max_budget_usd:g}"]
    if max_turns is not None:
        cmd += ["--max-turns", str(max_turns)]
    cmd += list(extra)
    return cmd


def parse_output(stdout: str) -> RunResult:
    """`claude -p --output-format json` prints one JSON object. Tolerate leading noise and a bare text fallback."""
    stdout = stdout.strip()
    data: dict | None = None
    if stdout:
        start = stdout.find("{")
        if start != -1:
            try:
                data = json.loads(stdout[start:])
            except json.JSONDecodeError:
                # Multiple objects or trailing noise: take the last complete JSON line
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue
    if not isinstance(data, dict):
        return RunResult(text=stdout or "(no output)", session_id=None, is_error=not stdout, raw={})
    text = data.get("result") or data.get("text") or data.get("content") or ""
    if isinstance(text, list):  # content blocks
        text = "\n".join(b.get("text", "") for b in text if isinstance(b, dict))
    subtype = str(data.get("subtype") or "")
    if subtype.startswith("error_max") and not str(text).strip():  # a turn or budget cap stopped the run
        text = f"Stopped early: hit the {subtype.removeprefix('error_max_').replace('_', ' ')} cap for this job."
        data["is_error"] = True
    return RunResult(
        text=str(text).strip() or "(empty reply)",
        session_id=data.get("session_id"),
        is_error=bool(data.get("is_error", False)),
        cost_usd=data.get("total_cost_usd"),
        duration_ms=data.get("duration_ms"),
        raw=data,
    )


ZONE = "America/New_York"


def now_line(now: datetime | None = None) -> str:
    """Every run starts with Michael's local time. Claude's own idea of "today" is UTC, so at 9:30 PM Eastern on a
    Sunday it thought it was Monday (Michael 2026-11-08)."""
    from zoneinfo import ZoneInfo
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(ZONE))
    stamp = f"{local:%A, %B} {local.day}, {local.year}, {local:%I:%M %p}".replace(", 0", ", ")
    return f"[Now for Michael: {stamp} Eastern. Use this for today, tomorrow and day names, never UTC.]"


# A words-only call (summarize, rephrase): no tools, no MCP servers, no skills, none of the project's CLAUDE.md or
# settings, and a one-line system prompt. About 900 tokens of overhead instead of about 11,000 (measured
# 2026-11-08). --bare would be leaner still but needs an API key, and Juno runs on Michael's Claude sign-in.
LEAN_FLAGS = ("--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "user",
              "--no-session-persistence")


# The built-in tools Juno's runs use (counted from 45 bridge sessions, 2026-11-10) plus Scout's web tools. Every other
# built-in tool definition is ~17K tokens of prefix on every model call (docs/v2/reports/P0-ledger.md, prefix split).
# Connectors are not built-in tools and are unaffected. JUNO_TOOLS=all restores the full set (rollback).
JUNO_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "PowerShell", "Agent", "Skill", "ToolSearch",
              "WebSearch", "WebFetch")


def tool_flags() -> tuple[str, ...]:
    return () if os.environ.get("JUNO_TOOLS", "").lower() == "all" else ("--tools", ",".join(JUNO_TOOLS))


def run(prompt: str, *, cwd: Path = ROOT, resume: str | None = None, unattended: bool = False,
        permission_mode: str | None = None, model: str | None = None, max_budget_usd: float | None = None,
        max_turns: int | None = None, timeout: int = 900, dry_run: bool = False, claude_bin: str | None = None,
        allowed_tools: tuple[str, ...] = (), env_extra: dict | None = None, job: str = "other",
        lean_system: str | None = None, effort: str | None = None, mcp_config: Path | None = None,
        settings_file: Path | None = None) -> RunResult:
    """lean_system set: a lean words-only call with that system prompt (see LEAN_FLAGS).
    mcp_config set (with lean_system): an agent run whose only tools are that MCP server's `allowed_tools`, with
    no built-in tools, no other MCP server, no project CLAUDE.md or settings, and `settings_file` for its hooks
    (the browser agent, gateway/browser_agent.py)."""
    permission_mode = permission_mode or os.environ.get("CLAUDE_PERMISSION_MODE", "acceptEdits")
    model = model or os.environ.get("CLAUDE_MODEL") or None
    binary = claude_bin or ("claude" if dry_run else find_claude())
    # allowed_tools grants tools outside the settings allow list to this one run only (an approved action).
    prompt = f"{now_line()}\n{prompt}"
    extra = (("--allowedTools", ",".join(allowed_tools)) if allowed_tools else ()) + tool_flags()
    if lean_system is not None and mcp_config is not None:
        if not allowed_tools or settings_file is None:
            raise ValueError("an MCP agent run needs its allowed tools and its settings file (the gate hook)")
        extra = ("--system-prompt", lean_system, *LEAN_FLAGS, "--mcp-config", str(mcp_config), "--settings",
                 str(settings_file), "--allowedTools", ",".join(allowed_tools))
    elif lean_system is not None:
        extra = ("--system-prompt", lean_system, *LEAN_FLAGS)
        max_turns = max_turns or 1
    cmd = build_command(binary, prompt, resume=resume, permission_mode=permission_mode, model=model,
                        max_budget_usd=max_budget_usd, max_turns=max_turns, extra=extra, effort=effort)
    env = child_env()
    env["COORDINATOR_HOME"] = str(cwd)
    env["COORDINATOR_UNATTENDED"] = "1" if unattended else "0"
    env.update(env_extra or {})
    if unattended:
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    if dry_run:
        return RunResult(text=f"[dry run] would run: {' '.join(cmd[:3])} ... (cwd={cwd}, unattended={unattended})",
                         session_id=resume, is_error=False, command=cmd)
    try:
        # CREATE_NO_WINDOW keeps the hidden bridge from flashing a console on every run.
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        result = RunResult(text=f"Claude run timed out after {timeout}s.", session_id=resume, is_error=True, command=cmd)
        log_cost(cwd, job, model, result)
        return result
    result = parse_output(proc.stdout)
    result.command = cmd
    if proc.returncode != 0 and not result.is_error:
        result.is_error = True
        err = (proc.stderr or "").strip()
        if err and result.text in ("(no output)", "(empty reply)"):
            result.text = err[-1500:]
    log_cost(cwd, job, model, result)
    return result


USAGE_KEYS = {"input_tokens": "in", "cache_creation_input_tokens": "cache_write", "cache_read_input_tokens": "cache_read",
              "output_tokens": "out"}


def _session_total(path: Path, session_id: str | None) -> float:
    """The last running total logged for this session. `total_cost_usd` of a resumed `claude -p` run is the whole
    session's cost so far, not this run's (docs/v2/AUDIT.md section 2), so a run's own cost is the difference."""
    if not session_id or not path.exists():
        return 0.0
    last = 0.0
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("session_id") == session_id and row.get("session_total_usd") is not None:
                last = float(row["session_total_usd"])
    return last


def log_cost(cwd: Path, job: str, model: str | None, result: RunResult) -> None:
    """One line per real run in state/costs.jsonl, summed by the weekly reflection. Never breaks a run.
    `cost_usd` is this run's own cost; `session_total_usd` is what the CLI reported for the session so far."""
    try:
        raw = result.raw or {}
        used = raw.get("modelUsage") or {}
        path = Path(cwd) / "state" / "costs.jsonl"
        total = result.cost_usd
        own = None if total is None else round(max(0.0, total - _session_total(path, result.session_id)), 6)
        usage = raw.get("usage") or {}
        line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "job": job,
                "model": model or (",".join(sorted(used)) if used else None), "cost_usd": own,
                "session_total_usd": total, "session_id": result.session_id,
                "tokens": {short: usage[k] for k, short in USAGE_KEYS.items() if k in usage} or None,
                "models": sorted(used) or None,
                "duration_ms": result.duration_ms, "turns": raw.get("num_turns"), "is_error": result.is_error}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except Exception:  # cost logging is bookkeeping, not part of the job
        pass
