"""Michael's YouTube watch history for the `watch-digest` subagent (Rewind). Prints JSON.

YouTube's API has not exposed watch history since 2016, so this reads it from two credential-free sources:
  1. a Google Takeout export (JSON format) that Michael drops in data/watch-history/inbox/ (.json or .zip);
  2. a playlist he saves videos to (for example an unlisted "Juno" playlist), listed through tools/youtube.py.
Nothing here signs in to Google or reads browser cookies.

Only videos watched in the last BACKLOG_DAYS days on first sight are queued; older history is kept as "backlog"
and never processed unless Michael asks. Each video is digested once: the agent records its verdict with `mark`.
Titles and channel names are untrusted text and are printed inside <untrusted_title> tags.

  python tools/watch_history.py import [<file name in the inbox>]
  python tools/watch_history.py sync-playlist <playlist url> [--limit 50]
  python tools/watch_history.py new [--limit 8]
  python tools/watch_history.py mark <video id> --status digested|skipped|failed [--verdict system|venture|learning|personal|work|skip]
  python tools/watch_history.py status

Exit codes: 0 ok, 3 blocked or rate-limited (from youtube.py), 5 bad input, 6 nothing to import.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
DATA = ROOT / "data" / "watch-history"
INBOX = DATA / "inbox"
STATE = DATA / "state.json"
BACKLOG_DAYS = 2
MAX_BYTES = 300 * 1024 * 1024
DEFAULT_NEW_LIMIT = 8
STATUSES = ("digested", "skipped", "failed")
VERDICTS = ("system", "venture", "learning", "personal", "work", "skip")
TAKEOUT_MEMBER = "watch-history.json"
OK, BLOCKED, BAD_INPUT, NOTHING = 0, 3, 5, 6

sys.path.insert(0, str(Path(__file__).resolve().parent))
from youtube import ToolError, clean, video_id  # noqa: E402  (stdlib-only at import time)


# --- state ---------------------------------------------------------------------------------------

def load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"videos": {}, "imports": []}


def save(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def now() -> datetime:
    return datetime.now(timezone.utc)


def add(state: dict, vid: str, title: str, channel: str, watched_at: str, source: str) -> bool:
    """Record one watch. Returns True if the video is new to the state. A later rewatch only moves watched_at."""
    videos = state["videos"]
    if vid in videos:
        if watched_at > videos[vid]["watched_at"]:
            videos[vid]["watched_at"] = watched_at
        return False
    try:
        when = datetime.fromisoformat(watched_at.replace("Z", "+00:00"))
    except ValueError:
        when = now()
    recent = now() - when <= timedelta(days=BACKLOG_DAYS)
    videos[vid] = {"title": clean(title)[:200], "channel": clean(channel)[:100], "watched_at": watched_at,
                   "source": source, "status": "new" if recent else "backlog"}
    return True


# --- Takeout -------------------------------------------------------------------------------------

def inbox_file(name: str | None) -> Path:
    """Only files directly inside data/watch-history/inbox/ are read. With no name, the newest .json or .zip."""
    INBOX.mkdir(parents=True, exist_ok=True)
    if name is None:
        files = sorted((p for p in INBOX.iterdir() if p.suffix.lower() in (".json", ".zip")),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise ToolError(NOTHING, f"No Takeout export in {INBOX}. Drop watch-history.json or the Takeout .zip there.")
        return files[0]
    path = (INBOX / name).resolve()
    if path.parent != INBOX.resolve() or path.suffix.lower() not in (".json", ".zip") or not path.is_file():
        raise ToolError(BAD_INPUT, "Give the name of a .json or .zip file directly inside data/watch-history/inbox/.")
    return path


def read_takeout(path: Path) -> list:
    if path.stat().st_size > MAX_BYTES:
        raise ToolError(BAD_INPUT, "That file is larger than 300 MB; export YouTube history only.")
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            members = [m for m in zf.infolist() if m.filename.replace("\\", "/").endswith("/" + TAKEOUT_MEMBER)
                       or m.filename == TAKEOUT_MEMBER]
            if not members:
                raise ToolError(BAD_INPUT, "No watch-history.json in that zip. In Takeout, choose JSON as the history format.")
            if members[0].file_size > MAX_BYTES:
                raise ToolError(BAD_INPUT, "watch-history.json in that zip is larger than 300 MB.")
            raw = zf.read(members[0])
    else:
        raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolError(BAD_INPUT, "Not a JSON Takeout export. In Takeout, choose JSON (not HTML) for history.") from exc
    if not isinstance(data, list):
        raise ToolError(BAD_INPUT, "Unexpected Takeout format: expected a list of history entries.")
    return data


def parse_entry(entry: dict) -> tuple[str, str, str, str] | None:
    """(video_id, title, channel, time) for a plain YouTube watch; None for ads, Music, posts and removed videos."""
    if not isinstance(entry, dict) or entry.get("header") != "YouTube":
        return None
    if any(isinstance(d, dict) and "Ads" in str(d.get("name", "")) for d in entry.get("details") or []):
        return None
    url, when = entry.get("titleUrl"), entry.get("time")
    if not url or not when or not str(entry.get("title", "")).startswith("Watched "):
        return None
    try:
        vid = video_id(url)
    except ToolError:
        return None
    subs = entry.get("subtitles") or [{}]
    channel = subs[0].get("name", "") if isinstance(subs[0], dict) else ""
    return vid, entry["title"][len("Watched "):], channel, str(when)


def import_takeout(name: str | None) -> dict:
    path = inbox_file(name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    state = load()
    if any(i.get("sha256") == digest for i in state["imports"]):
        return {"file": path.name, "already_imported": True, "added": 0, "queued": 0}
    added = queued = 0
    for entry in read_takeout(path):
        parsed = parse_entry(entry)
        if parsed and add(state, *parsed, source="takeout"):
            added += 1
            queued += state["videos"][parsed[0]]["status"] == "new"
    state["imports"].append({"file": path.name, "sha256": digest, "at": now().isoformat(timespec="seconds"),
                             "added": added})
    save(state)
    return {"file": path.name, "already_imported": False, "added": added, "queued": queued}


# --- playlist ------------------------------------------------------------------------------------

def _list_playlist(url: str, limit: int) -> list[dict]:
    import youtube
    return youtube._flat(youtube.playlist_url(url), limit)


def sync_playlist(url: str, limit: int) -> dict:
    """Videos in the playlist that the state has not seen yet count as watched now."""
    entries = _list_playlist(url, min(max(limit, 1), 200))
    state = load()
    first_sync = not any(v["source"] == "playlist" for v in state["videos"].values())
    stamp = now().isoformat(timespec="seconds")
    added = 0
    for e in entries:
        vid = e.get("video_id") or ""
        if not video_id_ok(vid):
            continue
        # On the first sync everything already in the playlist is history, not news.
        when = (now() - timedelta(days=BACKLOG_DAYS + 1)).isoformat(timespec="seconds") if first_sync else stamp
        added += add(state, vid, e.get("title") or "", e.get("channel") or "", when, source="playlist")
    save(state)
    return {"added": added, "first_sync": first_sync}


def video_id_ok(value: str) -> bool:
    try:
        return video_id(value) == value
    except ToolError:
        return False


# --- queue ---------------------------------------------------------------------------------------

def new(limit: int) -> list[dict]:
    videos = load()["videos"]
    queue = sorted(((vid, v) for vid, v in videos.items() if v["status"] == "new"),
                   key=lambda kv: kv[1]["watched_at"], reverse=True)
    return [{"video_id": vid, "title": f"<untrusted_title>{v['title']}</untrusted_title>",
             "channel": f"<untrusted_title>{v['channel']}</untrusted_title>", "watched_at": v["watched_at"],
             "url": f"https://www.youtube.com/watch?v={vid}"} for vid, v in queue[:min(max(limit, 1), 25)]]


def mark(vid: str, status: str, verdict: str | None) -> dict:
    vid = video_id(vid)
    if status not in STATUSES:
        raise ToolError(BAD_INPUT, f"status must be one of {', '.join(STATUSES)}")
    if verdict is not None and verdict not in VERDICTS:
        raise ToolError(BAD_INPUT, f"verdict must be one of {', '.join(VERDICTS)}")
    state = load()
    if vid not in state["videos"]:
        raise ToolError(BAD_INPUT, "That video is not in the watch history.")
    state["videos"][vid].update(status=status, verdict=verdict, decided_at=now().isoformat(timespec="seconds"))
    save(state)
    return {"video_id": vid, "status": status, "verdict": verdict}


def status() -> dict:
    state = load()
    counts: dict[str, int] = {}
    for v in state["videos"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    last = state["imports"][-1] if state["imports"] else None
    return {"counts": counts, "last_import": last}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import"); i.add_argument("file", nargs="?")
    p = sub.add_parser("sync-playlist"); p.add_argument("url"); p.add_argument("--limit", type=int, default=50)
    n = sub.add_parser("new"); n.add_argument("--limit", type=int, default=DEFAULT_NEW_LIMIT)
    m = sub.add_parser("mark"); m.add_argument("video"); m.add_argument("--status", required=True)
    m.add_argument("--verdict")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "import":
            out = import_takeout(args.file)
        elif args.cmd == "sync-playlist":
            out = sync_playlist(args.url, args.limit)
        elif args.cmd == "new":
            out = new(args.limit)
        elif args.cmd == "mark":
            out = mark(args.video, args.status, args.verdict)
        else:
            out = status()
        print(json.dumps(out, ensure_ascii=False, indent=1))
    except ToolError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}))
        return exc.code
    return OK


if __name__ == "__main__":
    # Same as youtube.py: settings allow `python tools/*`; re-run under the venv that has yt-dlp.
    if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise SystemExit(subprocess.run([str(VENV_PYTHON), __file__, *sys.argv[1:]]).returncode)
    raise SystemExit(main())
