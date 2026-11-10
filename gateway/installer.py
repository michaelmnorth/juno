"""Install an approved subagent proposal deterministically, from Python, after Michael taps Allow once.

A `claude -p` run cannot write `.claude/agents/` without an interactive prompt (Rewind's install on 2026-11-08 got
half done that way), and an install is exactly the kind of change that should not depend on a model following
instructions. So the `new-subagent` skill writes `proposals/<name>/install.json` and the bridge runs this:

  {"files": {"agents/watch-digest.md": ".claude/agents/watch-digest.md", "tools/x.py": "tools/x.py"},
   "pip": ["somepkg==1.2.3"],
   "claude_md": {"roster": "| `x` | \"X\" | Live | ... |", "routing": "- \"...\" -> `x`."}}

Rules: sources must sit inside the proposal folder; targets only under ALLOWED_TARGETS and must not exist yet (a
proposal adds, it never overwrites); packages only as exact `name==version` pins; CLAUDE.md lines are single lines.
Then the full test suite runs. If anything fails, every copied file and the CLAUDE.md edit are rolled back.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_TARGETS = (".claude/agents/", ".claude/skills/", "tools/", "tests/", "learnings/")
PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}==[0-9][A-Za-z0-9.+-]{0,40}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
ROSTER_ANCHOR = "\nA subagent whose phase has not started"
ROUTING_ANCHOR = "## Routing rules\n\n"


class InstallError(Exception):
    pass


@dataclass
class Manifest:
    name: str
    files: dict[Path, Path]
    pip: list[str]
    roster: str = ""
    routing: str = ""


@dataclass
class Result:
    ok: bool
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def load_manifest(root: Path, name: str) -> Manifest:
    if not NAME_RE.match(name or ""):
        raise InstallError(f"Bad proposal name: {name!r}")
    proposal = root / "proposals" / name
    path = proposal / "install.json"
    if not path.is_file():
        raise InstallError(f"No proposals/{name}/install.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"install.json is not valid JSON: {exc}") from exc
    files = {}
    for src, dst in (data.get("files") or {}).items():
        s, d = proposal / src, root / dst
        if not _inside(s, proposal) or not s.is_file():
            raise InstallError(f"Source {src!r} is not a file inside the proposal")
        rel = d.resolve().relative_to(root.resolve()).as_posix() if _inside(d, root) else None
        if rel is None or ".." in Path(dst).parts or not rel.startswith(ALLOWED_TARGETS):
            raise InstallError(f"Target {dst!r} is not under {', '.join(ALLOWED_TARGETS)}")
        if d.exists():
            raise InstallError(f"Target {dst!r} already exists; a proposal may only add files")
        files[s] = d
    if not files:
        raise InstallError("install.json lists no files")
    pip = [str(p).strip() for p in data.get("pip") or []]
    for p in pip:
        if not PIN_RE.match(p):
            raise InstallError(f"Package {p!r} must be pinned exactly, like name==1.2.3")
    md = data.get("claude_md") or {}
    roster, routing = str(md.get("roster", "")).strip(), str(md.get("routing", "")).strip()
    for label, line in (("roster", roster), ("routing", routing)):
        if "\n" in line or len(line) > 400:
            raise InstallError(f"claude_md.{label} must be one line under 400 characters")
    if roster and not roster.startswith("|"):
        raise InstallError("claude_md.roster must be a table row starting with |")
    return Manifest(name=name, files=files, pip=pip, roster=roster, routing=routing)


def _edit_claude_md(text: str, m: Manifest) -> str:
    if m.roster:
        at = text.find("\n" + ROSTER_ANCHOR)  # the blank line after the last table row
        if at < 0:
            raise InstallError("Could not find the end of the roster table in CLAUDE.md")
        text = text[:at] + "\n" + m.roster + text[at:]
    if m.routing:
        if ROUTING_ANCHOR not in text:
            raise InstallError("Could not find '## Routing rules' in CLAUDE.md")
        text = text.replace(ROUTING_ANCHOR, ROUTING_ANCHOR + m.routing + "\n", 1)
    return text


def default_pip(root: Path, pins: list[str]) -> tuple[bool, str]:
    python = root / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", *pins],
                          cwd=str(root), capture_output=True, text=True, timeout=600)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-500:]


def default_tests(root: Path) -> tuple[bool, str]:
    python = root / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run([str(python), "-m", "pytest", "tests/", "-q"], cwd=str(root), capture_output=True,
                          text=True, timeout=900)
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    return proc.returncode == 0, lines[-1] if lines else ""


def install(root: Path, name: str, *, pip=default_pip, tests=default_tests) -> Result:
    try:
        m = load_manifest(root, name)
    except InstallError as exc:
        return Result(False, [f"Not installed: {exc}"])
    res = Result(True)
    if m.pip:
        ok, out = pip(root, m.pip)
        if not ok:
            return Result(False, [f"Not installed: pip failed for {', '.join(m.pip)}", out])
        res.lines.append(f"Installed packages: {', '.join(m.pip)}")
    claude_md = root / "CLAUDE.md"
    original = claude_md.read_text(encoding="utf-8")
    copied: list[Path] = []
    try:
        for src, dst in m.files.items():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(dst)
        if m.roster or m.routing:
            claude_md.write_text(_edit_claude_md(original, m), encoding="utf-8")
        ok, summary = tests(root)
        if not ok:
            raise InstallError(f"tests failed after copying: {summary}")
    except (InstallError, OSError) as exc:
        for path in copied:
            path.unlink(missing_ok=True)
        claude_md.write_text(original, encoding="utf-8")
        lines = [f"Not installed: {exc}. Rolled back {len(copied)} file(s) and CLAUDE.md."]
        if m.pip:
            lines.append(f"Packages stay installed in .venv: {', '.join(m.pip)} (uninstall by hand if unwanted).")
        return Result(False, lines)
    rels = [d.relative_to(root).as_posix() for d in m.files.values()]
    res.lines += [f"Installed {m.name}: " + ", ".join(rels), f"Tests: {summary}"]
    return res
