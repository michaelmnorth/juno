"""Juno's browser agent ("Hands"): fill a web form, card, then submit only on Michael's tap (P2 brief step 7).

The coordinator queues a request with tools/browser_queue.py. The bridge runs this, never a model with a shell:

1. Fill run. A separate `claude -p` with only Playwright's tools (`--tools ""`, `--mcp-config` for this run,
   `--strict-mcp-config`, `--setting-sources user` so no CLAUDE.md, memory or connectors come along), headless
   Chromium in its own profile (state/browser/profile), the sites from the request only. The gate hook
   (.claude/hooks/gate_browser.py) is loaded through this run's own `--settings` file and stops any submit.
   The run ends with JSON: site, page, every field and value, and the button it would press.
2. Card. A `web.form.submit` approval with exactly that; never auto-approved, no Always button.
3. Submit run, after the tap: a one-time pass (state/browser/pass.json, 15 minutes) names the approval and its
   values. The run fills the same values and presses that button; success is claimed only when the page shows a
   confirmation. The bridge adds a follow-up for the answer.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import browser_queue  # noqa: E402

import ping_policy  # noqa: E402

TEMPLATE = ROOT / "gateway" / "mcp" / "browser.json"
PERSONA = ROOT / "gateway" / "agents" / "browser.md"
HOOK = ROOT / ".claude" / "hooks" / "gate_browser.py"
TOOLS = tuple(f"mcp__playwright__{t}" for t in sorted(browser_queue._gate().ALLOWED))
FILL_JSON = ('{"ok": true, "site": "<site name>", "url": "<form page url>", "form": "<form title>", '
             '"fields": [{"label": "<field label>", "value": "<what you put in>"}], '
             '"submit_label": "<exact text of the submit button>", "missing": ["<required field with no value>"], '
             '"needs_michael": "<what only he can do, or empty>", "notes": "<anything odd, or empty>"}')
SUBMIT_JSON = ('{"submitted": true, "confirmation": "<the confirmation text the page showed, word for word, '
               'short>", "reference": "<claim or case number, or empty>", "differs": "<what differed from the '
               'card, or empty>"}')


def browser_dir(root: Path) -> Path:
    return root / "state" / "browser"


def find_cli(env: dict | None = None) -> Path | None:
    """@playwright/mcp's cli.js from Michael's global install (npm install -g @playwright/mcp@0.0.85). Run with
    node directly: no shell, no npx download at run time."""
    import os
    env = env if env is not None else os.environ
    if env.get("JUNO_PLAYWRIGHT_MCP"):
        return Path(env["JUNO_PLAYWRIGHT_MCP"])
    found = shutil.which("playwright-mcp")
    if not found:
        return None
    p = Path(found).resolve()
    if p.suffix == ".js":
        return p
    cli = p.parent / "node_modules" / "@playwright" / "mcp" / "cli.js"
    return cli if cli.exists() else None


def write_configs(root: Path, origins: list[str], cli: Path) -> tuple[Path, Path]:
    """This run's Playwright config, the --mcp-config that starts it, and the --settings that loads the gate."""
    out = browser_dir(root)
    (out / "profile").mkdir(parents=True, exist_ok=True)
    (out / "out").mkdir(parents=True, exist_ok=True)
    cfg = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    cfg.pop("_comment", None)
    cfg["browser"]["userDataDir"] = str(out / "profile")
    cfg["outputDir"] = str(out / "out")
    pw = out / "playwright.json"
    pw.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    node = shutil.which("node") or "node"
    mcp = out / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"playwright": {"command": node,
                                                             "args": [str(cli), "--config", str(pw)]}}}, indent=2),
                   encoding="utf-8")
    settings = out / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "mcp__playwright__.*", "hooks": [
        {"type": "command", "command": sys.executable, "args": [str(HOOK)], "timeout": 15, "onFailure": "block"}]}]},
        "permissions": {"deny": ["Bash", "PowerShell", "Read", "Write", "Edit", "WebFetch", "WebSearch"]}},
        indent=2), encoding="utf-8")
    return mcp, settings


def last_json(text: str) -> dict | None:
    """The last JSON object in a reply (the agent is told to end with only that)."""
    text, found, i = text or "", None, 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = json.JSONDecoder().raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict):
            found = obj
        i = end  # skip past it: an object inside this one is not the answer
    return found


def _values_block(values: list[dict]) -> str:
    return "\n".join(f"- {v['field']}: {v['value']}" for v in values)


def fill_prompt(req: dict) -> str:
    return (f"Task: {req['task']}\nForm page: {req['url']}\nSites you may use: {', '.join(req['origins'])}\n"
            f"Values to enter (use only these):\n{_values_block(req['values'])}\n\n"
            "Fill the form but do NOT submit it: the submit happens later, after Michael approves. Don't press "
            "Enter or the submit button. If the form has several pages, fill the first page and report its "
            "button (Next, Continue or Submit) as submit_label. Then reply with only:\n" + FILL_JSON)


def submit_prompt(entry: dict) -> str:
    values = "\n".join(f"- {f['label']}: {f['value']}" for f in entry.get("fields") or [])
    return (f"Michael approved this submission.\nForm page: {entry['url']}\n"
            f"Enter exactly these values (nothing else, nothing changed):\n{values}\n"
            f"Then press the button labeled \"{entry['submit_label']}\" once. If the form now differs (new required "
            "fields, other choices, a login, a payment or a CAPTCHA), don't submit; say what differs. Later pages "
            "that ask for nothing new (instructions, a review page) you may press through with their Next, Continue "
            "or Submit button; a later page that asks for new information or a choice stops the run (say what it "
            "asks). Wait for the final page and read what it says, and take one screenshot of it (no file name; it "
            "is kept for the log). Claim submitted only if the page confirms it. "
            "Reply with only:\n"
            + SUBMIT_JSON)


def _clean_fields(fields) -> list[dict]:
    out = []
    for f in fields or []:
        if isinstance(f, dict) and str(f.get("label") or "").strip():
            out.append({"label": str(f["label"]).strip()[:80], "value": str(f.get("value") or "").strip()[:300]})
    return out[:browser_queue.MAX_VALUES]


def card_entry(req: dict, result: dict) -> dict:
    fields = _clean_fields(result.get("fields"))
    site = re.sub(r"^https://", "", req["origins"][0])
    form = str(result.get("form") or "form").strip()[:80]
    url = str(result.get("url") or req["url"])
    if browser_queue._gate()._origin(url) not in req["origins"]:
        url = req["url"]
    return {"id": f"a-{uuid.uuid4().hex[:8]}", "kind": "action", "action_class": "web.form.submit",
            "summary": f"Submit the {form} on {site}?",
            "action": f"Submit the {form} on {site} with the values below, pressing \"{result['submit_label']}\".",
            "why": req.get("why") or req["task"], "site": site, "url": url, "fields": fields,
            "submit_label": str(result["submit_label"]).strip()[:60], "origins": req["origins"],
            "request_id": req["id"], "session_id": req.get("session_id"), "status": "new",
            "from_timer": False, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _cleanup(root: Path) -> None:
    for f in browser_dir(root).glob("gate-*.json"):
        f.unlink(missing_ok=True)


def _run(run, root: Path, prompt: str, mode: str, origins: list[str], extra_env: dict | None = None):
    cli = find_cli()
    if cli is None:
        return None
    mcp, settings = write_configs(root, origins, cli)
    turns, dollars = ping_policy.JOB_LIMITS["browser"]
    env = {"JUNO_BROWSER_RUN": mode, "JUNO_BROWSER_ORIGINS": ",".join(origins), **(extra_env or {})}
    try:
        return run(prompt, cwd=root, unattended=True, allowed_tools=TOOLS, env_extra=env, max_turns=turns,
                   max_budget_usd=dollars, job="browser", model=ping_policy.DM_MODEL, effort=ping_policy.DM_EFFORT,
                   lean_system=PERSONA.read_text(encoding="utf-8"),
                   mcp_config=mcp, settings_file=settings)
    finally:
        _cleanup(root)


NOT_INSTALLED = ("The browser isn't set up on this PC yet, so I couldn't open that form. Michael installs it once "
                 "(see docs/v2/reports/P2.md); nothing was filled or sent. 🙃")


def fill(run, root: Path, req: dict) -> tuple[dict | None, str]:
    """Returns (approval entry, "") or (None, a line for Michael)."""
    result = _run(run, root, fill_prompt(req), "fill", req["origins"])
    if result is None:
        return None, NOT_INSTALLED
    out = last_json(result.text) or {}
    if result.is_error or not out:
        return None, "The form run didn't finish, so nothing was filled in for a card. Nothing was submitted. 🙃"
    if out.get("needs_michael") or out.get("missing") or not out.get("ok") or not out.get("submit_label"):
        need = str(out.get("needs_michael") or "").strip()
        missing = ", ".join(str(m) for m in out.get("missing") or [])[:200]
        why = need or (f"it still needs: {missing}" if missing else "the form didn't come out right")
        return None, f"I filled what I could on {req['origins'][0].replace('https://', '')}, but {why}. Nothing was submitted. 👀"
    return card_entry(req, out), ""


def write_pass(root: Path, entry: dict) -> Path:
    path = browser_dir(root) / "pass.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"approval_id": entry["id"], "values": [f["value"] for f in entry.get("fields") or []],
                                "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                    encoding="utf-8")
    return path


def submit(run, root: Path, entry: dict, add_followup=None, today: date | None = None) -> tuple[bool, str]:
    """Carry out an approved web.form.submit. Returns (submitted, a line for Michael)."""
    path = write_pass(root, entry)
    try:
        result = _run(run, root, submit_prompt(entry), "submit", entry.get("origins") or [f"https://{entry['site']}"],
                      {"JUNO_BROWSER_PASS": entry["id"]})
    finally:
        path.unlink(missing_ok=True)
    if result is None:
        return False, NOT_INSTALLED
    out = last_json(result.text) or {}
    confirmation = re.sub(r"\s+", " ", str(out.get("confirmation") or "")).strip()[:200]
    if result.is_error or not out.get("submitted") or not confirmation:
        differs = str(out.get("differs") or "").strip()[:200]
        return False, (f"Didn't submit on {entry['site']}: {differs}. Nothing went in. 🙃" if differs else
                       f"I couldn't confirm the form on {entry['site']} went through, so treat it as not sent. "
                       "I'll check if you want to try again. 🙃")
    ref = re.sub(r"[^A-Za-z0-9 #-]", "", str(out.get("reference") or ""))[:40].strip()
    if add_followup is not None:
        due = (today or date.today()) + timedelta(days=14)
        brand = entry["site"].split(".")[-2] if "." in entry["site"] else entry["site"]  # www.lg.com -> lg
        add_followup(what=f"Answer on the {entry['site']} form" + (f" ({ref})" if ref else ""),
                     expect_by=due.isoformat(), closes="reply mail from them",
                     match=",".join(x for x in (brand, ref) if x), source=f"approval {entry['id']}")
    return True, (f"Submitted on {entry['site']}. The page said: \"{confirmation}\""
                  + (f" Reference {ref}." if ref else "") + " I'll watch for their answer. 🫡")


def process(run, root: Path, approvals_add, path: Path | None = None) -> list[str]:
    """New requests → fill runs → cards. Returns lines to post to Michael for requests that couldn't reach a card."""
    path = path or root / "state" / "browser-requests.json"
    lines = []
    for req in [r for r in browser_queue.load(path) if r.get("status") == "new"]:
        browser_queue.update(req["id"], path, status="filling")
        entry, line = fill(run, root, req)
        if entry:
            approvals_add(entry)
            browser_queue.update(req["id"], path, status="carded", approval_id=entry["id"])
        else:
            browser_queue.update(req["id"], path, status="stopped", note=line[:200])
            lines.append(line)
    return lines
