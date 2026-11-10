"""Screens 4 to 6 of docs/13: status grid, evening check-in, Sunday reflection, and the Juno Home tab.

Same rules as the brief (brief_blocks.py): the job ends its reply with one JSON object, these builders draw the
blocks, and a reply without valid JSON still posts as text. Status and Home are built by the bridge from state/
files with no Claude run. Button words and who-is-reached facts come from code, never from Juno's text.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from brief_blocks import MAX_BLOCKS, Message, _button, _clip, _context, _rows, _section, to_mrkdwn

TZ = ZoneInfo("America/New_York")
# Persona names from the CLAUDE.md roster, for the reflection's "which agent this goes to" label.
PERSONAS = {"inbox-triage": "Sorter (triage)", "calendar": "Tempo (calendar)", "drafter": "Quill (drafts)",
            "health": "Rep (health)", "finance": "Ledger (finance)", "researcher": "Scout (research)",
            "notifier": "Ping (messages)", "reflector": "Mirror (reflection)", "relationships": "Kin (people)",
            "watch-digest": "Rewind (watching)", "youtube": "Reel (YouTube)", "coordinator": "Juno"}
ANSWERS_MAX = 3


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, json.JSONDecodeError):
        return default


def _jsonl(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _clock(at: datetime) -> str:
    return at.astimezone(TZ).strftime("%I:%M %p").lstrip("0")


def _field(label: str, value: str) -> dict:
    return {"type": "mrkdwn", "text": f"*{label}*\n{value or '-'}"[:1900]}


def _parse(text: str, key: str) -> dict | None:
    for match in reversed(list(re.finditer(r"\{", text or ""))):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and str(data.get(key) or "").strip():
            return data
    return None


# --- screen 4: status (no Claude run) -------------------------------------------------------------

def facts(root: Path, now: datetime | None = None) -> dict:
    """What the status grid and the Home tab's week grid read from state/."""
    now = now or datetime.now(timezone.utc)
    state = root / "state"
    runs = _read_json(state / "last-run.json", {})
    jobs = {k: v for k, v in runs.items() if not k.startswith("_") and isinstance(v, dict) and "at" in v}
    problems = sorted(k for k, v in jobs.items() if not v.get("ok"))
    pending = _read_json(state / "pending-approvals.json", {}).get("pending", [])
    waiting = [e for e in pending if e.get("status") in ("new", "posted")]
    local = now.astimezone(TZ)
    today, week_start = local.date(), local.date() - timedelta(days=local.weekday())
    costs = _jsonl(state / "costs.jsonl")

    def day(entry):
        try:
            return datetime.fromisoformat(entry["at"]).astimezone(TZ).date()
        except (KeyError, ValueError):
            return None

    spent_today = sum(float(c.get("cost_usd") or 0) for c in costs if day(c) == today)
    week = [c for c in costs if (d := day(c)) and d >= week_start]
    pinged = _read_json(state / "pinged.json", {}).get("days", {})
    sweep = jobs.get("sweep")
    ago = ""
    if sweep:
        mins = int((now - datetime.fromisoformat(sweep["at"])).total_seconds() // 60)
        ago = f"{mins // 60} h ago" if mins >= 60 else f"{mins} min ago"
    return {"problems": problems, "waiting": waiting, "spent_today": spent_today, "last_sweep": ago,
            "pings_today": int(pinged.get(today.isoformat(), 0)), "week_runs": len(week),
            "week_failed": sum(1 for c in week if c.get("is_error")), "week_spent": sum(float(c.get("cost_usd") or 0) for c in week)}


def next_anchor(cfg: dict, now: datetime | None = None) -> str:
    """The next scheduled touchpoint from me/proactivity.yaml, e.g. "Check-in 8:30 PM"."""
    local = (now or datetime.now(timezone.utc)).astimezone(TZ)
    anchors = (cfg or {}).get("anchors", {})
    times = []
    for key, label in (("morning_brief", "Brief"), ("evening_checkin", "Check-in")):
        if key in anchors:
            h, m = (int(x) for x in str(anchors[key]).split(":"))
            at = local.replace(hour=h, minute=m, second=0, microsecond=0)
            times.append((at if at > local else at + timedelta(days=1), label))
    if not times:
        return "-"
    at, label = min(times)
    return f"{label} {at.strftime('%I:%M %p').lstrip('0')}" + ("" if at.date() == local.date() else " tomorrow")


def status_blocks(root: Path, cfg: dict, now: datetime | None = None) -> Message:
    f = facts(root, now)
    cap = (cfg or {}).get("unprompted_pings_per_day", 5)
    head = "All running" if not f["problems"] else f"{len(f['problems'])} problem" + ("s" if len(f["problems"]) > 1 else "")
    grid = [_field("Last sweep", f["last_sweep"] or "Not yet"), _field("Next", next_anchor(cfg, now)),
            _field("Waiting on you", str(len(f["waiting"]))), _field("Pings today", f"{f['pings_today']} of {cap}"),
            _field("Spent today", f"${f['spent_today']:.2f}"), _field("Problems", ", ".join(f["problems"]) or "None")]
    blocks = [_section(f"*{head}*"), {"type": "section", "fields": grid}]
    elements = []
    if f["waiting"]:
        elements.append({"type": "button", "action_id": "status_show", "style": "primary", "value": "waiting",
                         "text": {"type": "plain_text", "text": f"Show the {len(f['waiting'])}"}})
    options = [("Sweep now", "sweep")] + [(f"Why is {p} failing?", f"why:{p}") for p in f["problems"][:3]]
    elements.append({"type": "overflow", "action_id": "status_more",
                     "options": [{"text": {"type": "plain_text", "text": _clip(t, 75)}, "value": v} for t, v in options]})
    blocks.append({"type": "actions", "elements": elements})
    return Message(head, blocks)


# --- screen 4: evening check-in -------------------------------------------------------------------

def checkin(text: str) -> Message:
    """Tomorrow rows, Still open rows, Remembered with Undo, and one question with answer buttons."""
    data = _parse(text, "headline")
    if data is None:
        return Message(to_mrkdwn(text), None)
    headline = _clip(data["headline"], 150)
    blocks = [_section(f"*{headline}*")]
    tomorrow = _rows(data, "tomorrow")
    if tomorrow:
        blocks.append(_section("*Tomorrow*"))
        for row in tomorrow:
            line = f"*{row['time']}* {row['text']}" if row.get("time") else row["text"]
            blocks.append(_section(line, _button(row.get("button", ""), line, url=row.get("url"))))
            if str(row.get("prep") or "").strip():
                blocks.append(_context(row["prep"]))
    still = _rows(data, "still_open")
    quiet = [str(i).strip() for i in data.get("quiet_mail") or [] if str(i).strip()]
    remembered = _rows(data, "remembered")[:3]
    if still or quiet or remembered:
        blocks += [{"type": "divider"}, _section("*Still open*")]
        for row in still:
            blocks.append(_section(row["text"], _button(row.get("button", "review"), row["text"])))
        if quiet:
            blocks.append(_section(f"Quiet mail: {len(quiet)}", {
                "type": "button", "action_id": "brief_show", "text": {"type": "plain_text", "text": f"Show {len(quiet)}"},
                "value": _clip("\n".join(f"• {i}" for i in quiet), 1900)}))
        for row in remembered:
            blocks.append(_section(f"*Remembered* {row['text']}", _button("undo", row["text"])))
            if str(row.get("seen") or "").strip():
                blocks.append(_context(row["seen"]))
    q = data.get("question") or {}
    answers = [str(a).strip() for a in q.get("answers") or [] if str(a).strip()][:ANSWERS_MAX]
    if str(q.get("text") or "").strip() and answers:
        blocks += [{"type": "divider"}, _section(q["text"]),
                   {"type": "actions", "elements": [
                       {"type": "button", "action_id": f"answer_{i}", "value": json.dumps({"q": q["text"][:300], "a": a}),
                        "text": {"type": "plain_text", "text": _clip(a, 30)}, **({"style": "primary"} if i == 0 else {})}
                       for i, a in enumerate(answers)]}]
    return Message(headline, blocks[:MAX_BLOCKS])


def answer_prompt(question: str, answer: str) -> str:
    return f"[Tapped an answer on the evening check-in]\nQuestion: {question}\nMy answer: {answer}"


# --- screen 5: Sunday reflection ------------------------------------------------------------------

def agent_label(target: str) -> str:
    """Which agent or file a proposed lesson goes to, in Michael's words."""
    path = Path(str(target or ""))
    if path.parts[:1] == ("learnings",):
        return PERSONAS.get(path.stem, path.stem)
    if path.parts[:1] == ("me",):
        return "You"
    if path.parts[:1] == ("people",):
        return path.stem.replace("-", " ").title()
    if path.parts[:1] == ("domains",) and len(path.parts) > 1:
        return f"{path.parts[1].title()} context"
    return str(target or "Juno")


def _change_text(change: dict) -> str:
    def bare(line) -> str:  # lesson lines are list items ("- 2026-11-08: ..."); the diff marker replaces the dash
        return re.sub(r"^[-*]\s+", "", str(line or "").strip())
    lines = []
    if bare(change.get("old_line")):
        lines.append(f"- {bare(change['old_line'])}")
    lines.append(f"+ {bare(change.get('new_line'))}")
    return "\n".join(lines)


def reflection(text: str) -> list[Message]:
    """Message 1: week summary, each proposed change with Save / Skip, watching ideas. Message 2: Coming up."""
    data = _parse(text, "title")
    if data is None:
        return [Message(to_mrkdwn(text), None)]
    s = data.get("summary") or {}
    changes = [c for c in data.get("changes") or [] if isinstance(c, dict) and str(c.get("new_line") or "").strip()]
    blocks = [_section(f"*{_clip(data['title'], 150)}*"),
              {"type": "section", "fields": [_field("Runs", str(s.get("runs", "-"))), _field("Blocked", str(s.get("blocked", "-"))),
                                             _field("Spent", str(s.get("spent", "-"))), _field("To review", str(len(changes)))]}]
    shown = 0
    for c in changes:
        if len(blocks) + 5 > MAX_BLOCKS - 4:  # leave room for the watching section
            break
        value = json.dumps({"id": str(c.get("id") or ""), "target": str(c.get("target") or ""),
                            "old": _clip(c.get("old_line") or "", 700), "new": _clip(c["new_line"], 700)})
        blocks += [{"type": "divider"}, _section(f"*{agent_label(c.get('target'))}*"),
                   {"type": "rich_text", "elements": [{"type": "rich_text_preformatted",
                                                       "elements": [{"type": "text", "text": _change_text(c)}]}]}]
        if str(c.get("evidence") or "").strip():
            blocks.append(_context(c["evidence"]))
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "action_id": "lesson_save", "style": "primary", "value": value,
             "text": {"type": "plain_text", "text": "Save"}},
            {"type": "button", "action_id": "lesson_skip", "value": value, "text": {"type": "plain_text", "text": "Skip"}},
            {"type": "overflow", "action_id": "lesson_more", "options": [  # the handler reads Save's value
                {"text": {"type": "plain_text", "text": "Change the wording"}, "value": "reword"}]}]})
        shown += 1
    if shown < len(changes):
        blocks.append(_context(f"{len(changes) - shown} more in the thread"))
    w = data.get("watching") or {}
    ideas = [i for i in w.get("ideas") or [] if str(i).strip()][:2]
    if str(w.get("themes") or "").strip() or ideas:
        blocks += [{"type": "divider"}, _section(f"*From your watching:* {w.get('themes', '')}".strip())]
        for idea in ideas:
            v = _clip(str(idea), 1900)
            blocks += [_section(str(idea)), {"type": "actions", "elements": [
                {"type": "button", "action_id": "idea_draft", "style": "primary", "value": v,
                 "text": {"type": "plain_text", "text": "Draft it"}},
                {"type": "button", "action_id": "idea_skip", "value": v, "text": {"type": "plain_text", "text": "Not now"}}]}]
    title = _clip(data["title"], 150)
    out = [Message(f"{title}: {len(changes)} change{'s' if len(changes) != 1 else ''} to review", blocks[:MAX_BLOCKS],
                   [f"{agent_label(c.get('target'))}: {_change_text(c)}" for c in changes[shown:]])]
    coming = _rows(data, "coming_up")[:3]
    if coming:
        more = [_section("*Coming up*")]
        for row in coming:
            more.append(_section(row["text"], _button(row.get("button", "ideas"), row["text"])))
            if str(row.get("note") or "").strip():
                more.append(_context(row["note"]))
        out.append(Message("Coming up", more))
    return out


def lesson_prompt(verb: str, change: dict) -> str:
    target, old, new = change.get("target", ""), change.get("old", ""), change.get("new", "")
    if verb == "save":
        return (f"[Tapped Save on weekly proposal {change.get('id', '')}]\nTarget: {target}\n"
                + (f"Replaces: {old}\n" if old else "") + f"Line: {new}\n"
                "Write exactly this line with the lesson skill (this tap is my yes), remove it from "
                "state/proposed-lessons.md, and confirm in one line.")
    if verb == "skip":
        return (f"[Tapped Skip on weekly proposal {change.get('id', '')}]\nTarget: {target}\nLine: {new}\n"
                "Do not write it. Record a skip signal so it is not proposed again for 30 days; confirm in one line.")
    return (f"[Tapped Change the wording on weekly proposal {change.get('id', '')}]\nTarget: {target}\nLine: {new}\n"
            "Ask me in one line how I'd word it. When I answer, write my wording with the lesson skill.")


# --- screen 6: Home tab ---------------------------------------------------------------------------

def _learned(root: Path, limit: int = 3) -> list[str]:
    path = root / "observed" / "changelog.md"
    if not path.exists():
        return []
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- 20")]
    out = []
    for line in reversed(lines[-limit:]):
        parts = [p.strip() for p in line[2:].split("|")]
        what = parts[3] if len(parts) >= 4 else line[2:]
        out.append(what[:1].upper() + what[1:])
    return out


def _people(root: Path, today) -> list[dict]:
    """Upcoming occasions in the next 30 days (tools/occasions.py reads people/occasions.yaml)."""
    try:
        import sys
        sys.path.insert(0, str(root / "tools"))
        import occasions
        return occasions.upcoming(occasions.load_entries()[0], today, 30)["upcoming"]
    except Exception:
        return []


def home_view(root: Path, cfg: dict, waiting_links: dict[str, str] | None = None,
              now: datetime | None = None) -> dict:
    """The Home tab (docs/13 screen 6), in the Today page's order and voice. Rebuilt on every open."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(TZ)
    f = facts(root, now)
    n = len(f["waiting"])
    part = "morning" if local.hour < 12 else "afternoon" if local.hour < 17 else "evening"
    mood = "Quiet" if n == 0 else "Busy" if n > 3 else "Easy"
    blocks = [_context(f"{local.strftime('%A, %B')} {local.day} · updated {_clock(now)}"),
              {"type": "header", "text": {"type": "plain_text",
                                          "text": f"{mood} {part}. " + (f"{n} for you." if n else "Nothing for you.")}}]
    if n:
        blocks += [{"type": "divider"}, _section("*What waits*")]
        for i, e in enumerate(f["waiting"][:5]):
            link = (waiting_links or {}).get(e["id"])
            btn = ({"type": "button", "action_id": "home_open", "url": link, "text": {"type": "plain_text", "text": "Open"},
                    **({"style": "primary"} if i == 0 else {})} if link else None)
            blocks.append(_section(e.get("summary", ""), btn))
    learned = _learned(root)
    if learned:
        blocks += [{"type": "divider"}, _section("*Learned*")]
        for line in learned:
            blocks.append(_section(line, _button("undo", line)))
    people = _people(root, local.date())
    if people:
        first, rest = people[0], people[1:3]
        when = "today" if first["days"] == 0 else f"in {first['days']} day{'s' if first['days'] != 1 else ''}"
        blocks += [{"type": "divider"}, _section("*People*"),
                   _section(f"{first['person']}: {first['what']} {when}", _button("ideas", f"{first['person']}: {first['what']}"))]
        if rest:
            blocks.append(_context(" · ".join(f"{p['person']}: {p['what']} in {p['days']} days" for p in rest)))
    blocks += [{"type": "divider"}, _section("*This week*"),
               {"type": "section", "fields": [_field("Runs", f"{f['week_runs']}" + (f" ({f['week_failed']} failed)" if f["week_failed"] else "")),
                                              _field("Spent", f"${f['week_spent']:.2f}"),
                                              _field("Waiting on you", str(n)),
                                              _field("Problems", ", ".join(f["problems"]) or "None")]}]
    return {"type": "home", "blocks": blocks[:100]}


# --- people: what Juno learned, waiting for a Save tap (tools/people_queue.py) --------------------

MAX_PEOPLE = 3


def people_card(entries: list[dict], label) -> Message | None:
    """Up to three waiting people notes, each with Save and Skip. Save writes exactly the line shown."""
    if not entries:
        return None
    blocks: list[dict] = [_section("*Learned about people* (Save puts it in their profile)")]
    for e in entries[:MAX_PEOPLE]:
        blocks.append({"type": "section", "block_id": f"pq:{e['id']}",
                       "text": {"type": "mrkdwn", "text": _clip(to_mrkdwn(label(e)), 2900)}})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"From {e['source']}"}]})
        blocks.append({"type": "actions", "block_id": f"pqa:{e['id']}", "elements": [
            {"type": "button", "action_id": "people_save", "style": "primary", "value": e["id"],
             "text": {"type": "plain_text", "text": "Save"}},
            {"type": "button", "action_id": "people_skip", "value": e["id"],
             "text": {"type": "plain_text", "text": "Skip"}}]})
    if len(entries) > MAX_PEOPLE:
        blocks.append(_context(f"{len(entries) - MAX_PEOPLE} more next time"))
    return Message(f"{len(entries)} people notes waiting", blocks[:MAX_BLOCKS])

