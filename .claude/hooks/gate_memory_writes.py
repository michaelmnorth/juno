"""PreToolUse hook for Write/Edit: protect identity, config and memory files.

Rules (checked against the target path, relative to the project root):
- CLAUDE.md and anything under .claude/  -> deny in Juno's own runs (the bridge sets COORDINATOR_UNATTENDED on every
      Slack and timer run), so mail or a web page can never talk Juno into rewriting its rules. Allowed in a Code-tab
      session with Michael, which has no COORDINATOR_UNATTENDED (Michael 2026-11-08), or with
      COORDINATOR_ALLOW_CONFIG_EDITS=1.
- me/, learnings/, people/, domains/**/CONTEXT.md (the preference and lesson memory)
      -> deny when COORDINATOR_UNATTENDED=1 (scheduled or headless runs). Interactive sessions may write them,
         because that is how `/lesson` works, with Michael present.
- state/proposed-lessons.md -> always allowed (the reflector's only output).
- observed/*.md (what Juno learns on its own, Michael 2026-11-07) -> allowed in any run, including unattended,
  as long as the file stays under OBSERVED_MAX_CHARS. The cap forces consolidation instead of endless growth.
- Everything else -> allow.

Reads the hook JSON on stdin. Prints a deny decision on stdout when blocking; exits 0 either way (exit 2 would also
block, but a JSON decision carries the reason to Claude).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTECTED_CONFIG = ("CLAUDE.md",)
PROTECTED_CONFIG_DIRS = (".claude",)
MEMORY_DIRS = ("me", "learnings", "people")
ALWAYS_ALLOWED = ("state/proposed-lessons.md",)
OBSERVED_DIR = "observed"
OBSERVED_MAX_CHARS = 8000


def _rel(path_str: str, root: Path) -> str:
    p = Path(path_str)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()  # outside the project: let permissions handle it


def _observed_size_check(rel: str, tool_input: dict, root: Path) -> str | None:
    """Size after the write: Write replaces the file, Edit swaps one string for another."""
    path = root / rel
    current = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if "content" in tool_input:
        size = len(tool_input.get("content") or "")
    else:
        old, new = tool_input.get("old_string") or "", tool_input.get("new_string") or ""
        times = current.count(old) if tool_input.get("replace_all") and old else 1
        size = len(current) + times * (len(new) - len(old))
    if size > OBSERVED_MAX_CHARS:
        return (f"Blocked: '{rel}' would be {size} characters (cap {OBSERVED_MAX_CHARS}). "
                "Consolidate: merge repeated observations and drop stale ones, then write.")
    return None


def decide(tool_input: dict, env: dict, root: Path) -> str | None:
    target = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path") or ""
    if not target:
        return None
    rel = _rel(target, root)
    if rel in ALWAYS_ALLOWED:
        return None
    if rel.startswith(OBSERVED_DIR + "/"):
        return _observed_size_check(rel, tool_input, root)
    first = rel.split("/", 1)[0]
    if rel in PROTECTED_CONFIG or first in PROTECTED_CONFIG_DIRS:
        if env.get("COORDINATOR_ALLOW_CONFIG_EDITS") == "1" or "COORDINATOR_UNATTENDED" not in env:
            return None
        return f"Blocked: '{rel}' is coordinator identity/config. Juno's own runs can't change it; ask Michael to make the change from the Code tab."
    is_memory = first in MEMORY_DIRS or (first == "domains" and rel.endswith("/CONTEXT.md"))
    if is_memory and env.get("COORDINATOR_UNATTENDED") == "1":
        return f"Blocked: unattended runs may not write memory ('{rel}'). Put the proposal in state/proposed-lessons.md and ask Michael."
    return None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig") or "{}"
    data = json.loads(raw)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    reason = decide(data.get("tool_input") or {}, os.environ, root)
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
