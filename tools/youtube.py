"""YouTube transcripts, video info, search and playlists for the `youtube` subagent (Reel). Prints JSON or text.

Research and design: docs/06-RESEARCH-PROACTIVITY-AND-YOUTUBE.md section 3. Runs on Michael's home IP, which is why
it works where Claude's web fetch does not. Transcripts come from youtube-transcript-api first, then yt-dlp
subtitles. Everything fetched is cached in data/youtube/ (git-ignored) and rate-limited so YouTube does not block
this IP. Transcript and description text is untrusted and is printed inside <untrusted_*> tags.

  python tools/youtube.py transcript <url|id> [--lang en] [--format text|json]
  python tools/youtube.py info <url|id>
  python tools/youtube.py search "<query>" [--limit 10]
  python tools/youtube.py playlist <url> [--limit 50]

Exit codes: 0 ok, 2 no captions, 3 blocked or rate-limited, 4 unavailable (private, age-restricted, removed),
5 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CACHE = ROOT / "data" / "youtube"
RATE_FILE = CACHE / "_rate.json"
MIN_GAP_SECONDS = 3
DAILY_LIMIT = 100
COOLDOWN = timedelta(minutes=15)
INFO_TTL = timedelta(days=7)
OK, NO_CAPTIONS, BLOCKED, UNAVAILABLE, BAD_INPUT = 0, 2, 3, 4, 5

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TAGS = re.compile(r"<[^>]+>")


class ToolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# --- input ---------------------------------------------------------------------------------------

def video_id(value: str) -> str:
    """Accept an 11-character ID or a youtube.com / youtu.be URL. Anything else is refused."""
    value = value.strip()
    if ID_RE.match(value):
        return value
    from urllib.parse import parse_qs, urlparse
    url = urlparse(value if "://" in value else "https://" + value)
    if url.hostname not in HOSTS:
        raise ToolError(BAD_INPUT, "Only youtube.com and youtu.be links or 11-character video IDs are accepted.")
    if url.hostname == "youtu.be":
        candidate = url.path.lstrip("/").split("/")[0]
    elif url.path.startswith(("/shorts/", "/embed/", "/live/")):
        candidate = url.path.split("/")[2]
    else:
        candidate = (parse_qs(url.query).get("v") or [""])[0]
    if not ID_RE.match(candidate):
        raise ToolError(BAD_INPUT, "Could not find a video ID in that link.")
    return candidate


def playlist_url(value: str) -> str:
    from urllib.parse import urlparse
    url = urlparse(value.strip())
    if url.hostname not in HOSTS or "list=" not in url.query:
        raise ToolError(BAD_INPUT, "Give a youtube.com playlist link (one with list=...).")
    return value.strip()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub("", CONTROL.sub("", text or ""))).strip()


# --- rate limiting -------------------------------------------------------------------------------

def _rate() -> dict:
    try:
        return json.loads(RATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_rate(data: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    RATE_FILE.write_text(json.dumps(data), encoding="utf-8")


def throttle() -> None:
    """At most one request every 3 s and 100 a day; no requests at all during a cool-down after a block."""
    now = datetime.now(timezone.utc)
    data = _rate()
    until = data.get("cooldown_until")
    if until and now < datetime.fromisoformat(until):
        raise ToolError(BLOCKED, f"YouTube blocked a request recently. Cooling down until {until[11:16]} UTC; not retrying.")
    today = now.strftime("%Y-%m-%d")
    count = data.get("count", 0) if data.get("day") == today else 0
    if count >= DAILY_LIMIT:
        raise ToolError(BLOCKED, f"Daily limit of {DAILY_LIMIT} YouTube requests reached. Try again tomorrow.")
    wait = MIN_GAP_SECONDS - (time.time() - data.get("last", 0))
    if wait > 0:
        time.sleep(wait)
    _save_rate({**data, "day": today, "count": count + 1, "last": time.time()})


def blocked(reason: str) -> ToolError:
    until = (datetime.now(timezone.utc) + COOLDOWN).isoformat(timespec="seconds")
    _save_rate({**_rate(), "cooldown_until": until})
    return ToolError(BLOCKED, f"YouTube refused the request ({reason}). Cooling down 15 minutes; not retrying.")


# --- yt-dlp --------------------------------------------------------------------------------------

def ytdlp(*args: str, timeout: int = 120) -> str:
    """yt-dlp needs a JavaScript runtime for YouTube; Node is installed on this PC, Deno is not."""
    throttle()
    cmd = [sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "--no-warnings", "--sleep-requests", "1",
           "--sleep-subtitles", "2", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        err = proc.stderr.strip().splitlines()[-1:] or ["unknown error"]
        message = err[0]
        if re.search(r"429|Too Many Requests|Sign in to confirm|bot", message, re.I):
            raise blocked(message[:120])
        if re.search(r"Private|unavailable|removed|age|members", message, re.I):
            raise ToolError(UNAVAILABLE, f"Video unavailable: {message[:200]}")
        raise ToolError(BLOCKED, f"yt-dlp failed: {message[:200]}")
    return proc.stdout


def info(vid: str, *, refresh: bool = False) -> dict:
    path = CACHE / f"{vid}.info.json"
    if path.exists() and not refresh:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < INFO_TTL:
            return cached
    raw = json.loads(ytdlp("-J", "--skip-download", f"https://www.youtube.com/watch?v={vid}"))
    data = {
        "video_id": vid,
        "title": raw.get("title"),
        "channel": raw.get("channel") or raw.get("uploader"),
        "upload_date": raw.get("upload_date"),
        "duration": raw.get("duration"),
        "chapters": [{"start": c.get("start_time"), "title": c.get("title")} for c in raw.get("chapters") or []],
        "caption_languages": sorted(set(raw.get("subtitles") or {}) | {k for k in raw.get("automatic_captions") or {} if k.endswith("-orig")}),
        "description": clean(raw.get("description") or "")[:2000],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


# --- transcripts ---------------------------------------------------------------------------------

def _from_transcript_api(vid: str, lang: str) -> dict | None:
    import youtube_transcript_api as yta
    throttle()
    try:
        listing = yta.YouTubeTranscriptApi().list(vid)
        try:
            track = listing.find_manually_created_transcript([lang])
        except yta.NoTranscriptFound:
            track = listing.find_generated_transcript([lang])
        fetched = track.fetch()
    except (yta.NoTranscriptFound, yta.TranscriptsDisabled):
        return None
    except (yta.VideoUnavailable, yta.VideoUnplayable, yta.AgeRestricted, yta.InvalidVideoId) as exc:
        raise ToolError(UNAVAILABLE, f"Video unavailable: {type(exc).__name__}") from exc
    except (yta.RequestBlocked, yta.IpBlocked) as exc:
        raise blocked(type(exc).__name__) from exc
    except yta.YouTubeTranscriptApiException:
        return None  # PoTokenRequired and parsing changes: let yt-dlp try
    segments = [{"start": round(s.start, 2), "dur": round(s.duration, 2), "text": clean(s.text)} for s in fetched.snippets]
    return {"source": "auto" if fetched.is_generated else "manual", "lang": fetched.language_code, "segments": segments}


def _from_ytdlp(vid: str, lang: str) -> dict | None:
    # Ask for the original track only: "en.*" requests every translation and triggers 429s.
    with tempfile.TemporaryDirectory() as tmp:
        ytdlp("--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", f"{lang},{lang}-orig",
              "--sub-format", "json3", "-o", str(Path(tmp) / "%(id)s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}")
        files = sorted(Path(tmp).glob(f"{vid}.*.json3"), key=lambda p: (not p.name.endswith(f".{lang}.json3"), p.name))
        if not files:
            return None
        events = json.loads(files[0].read_text(encoding="utf-8")).get("events") or []
    segments = []
    for e in events:
        text = clean("".join(s.get("utf8", "") for s in e.get("segs") or []))
        if text:
            segments.append({"start": round(e.get("tStartMs", 0) / 1000, 2), "dur": round(e.get("dDurationMs", 0) / 1000, 2), "text": text})
    if not segments:
        return None
    return {"source": "auto" if "-orig" in files[0].name else "manual", "lang": lang, "segments": segments}


def transcript(vid: str, lang: str = "en") -> dict:
    path = CACHE / f"{vid}.{lang}.json"
    if path.exists():  # transcripts do not change, so the cache never expires
        return json.loads(path.read_text(encoding="utf-8"))
    meta = info(vid)
    found = _from_transcript_api(vid, lang) or _from_ytdlp(vid, lang)
    if not found:
        raise ToolError(NO_CAPTIONS, f"No {lang} captions for this video. Local transcription (Whisper) is not set up; ask Michael before adding it.")
    data = {**{k: meta[k] for k in ("video_id", "title", "channel", "duration")}, **found,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    data["text"] = " ".join(s["text"] for s in data["segments"])
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def as_text(data: dict, every: int = 30) -> str:
    """Plain text with a [mm:ss] marker about every 30 seconds so Reel can quote timestamps."""
    out, mark = [], -every
    for s in data["segments"]:
        if s["start"] - mark >= every:
            mark = s["start"]
            m, sec = divmod(int(s["start"]), 60)
            h, m = divmod(m, 60)
            out.append(f"\n[{h}:{m:02d}:{sec:02d}] " if h else f"\n[{m}:{sec:02d}] ")
        out.append(s["text"] + " ")
    header = f"{data['title']} | {data['channel']} | {data['duration']}s | captions: {data['source']} ({data['lang']})"
    return (f"{header}\n<untrusted_transcript video_id=\"{data['video_id']}\">"
            + "".join(out).strip() + "\n</untrusted_transcript>")


# --- search and playlists ------------------------------------------------------------------------

def _flat(target: str, limit: int) -> list[dict]:
    raw = json.loads(ytdlp("--flat-playlist", "-J", "--playlist-end", str(limit), target))
    return [{"video_id": e.get("id"), "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
             "duration": e.get("duration"), "url": f"https://www.youtube.com/watch?v={e.get('id')}"}
            for e in raw.get("entries") or [] if e.get("id")]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # captions carry characters the Windows console code page lacks
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcript"); t.add_argument("video"); t.add_argument("--lang", default="en")
    t.add_argument("--format", choices=("text", "json"), default="text")
    i = sub.add_parser("info"); i.add_argument("video")
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("playlist"); p.add_argument("url"); p.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "transcript":
            data = transcript(video_id(args.video), args.lang)
            print(as_text(data) if args.format == "text" else json.dumps(data, ensure_ascii=False))
        elif args.cmd == "info":
            data = info(video_id(args.video))
            data["description"] = f"<untrusted_description>{data['description']}</untrusted_description>"
            print(json.dumps(data, ensure_ascii=False, indent=1))
        elif args.cmd == "search":
            query = clean(args.query)[:200]
            if not query:
                raise ToolError(BAD_INPUT, "Empty search.")
            print(json.dumps(_flat(f"ytsearch{min(max(args.limit, 1), 25)}:{query}", 25), ensure_ascii=False, indent=1))
        else:
            print(json.dumps(_flat(playlist_url(args.url), min(max(args.limit, 1), 200)), ensure_ascii=False, indent=1))
    except ToolError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}))
        return exc.code
    return OK


if __name__ == "__main__":
    # Settings allow `python tools/*`, and plain `python` is the system install without these packages.
    if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise SystemExit(subprocess.run([str(VENV_PYTHON), __file__, *sys.argv[1:]]).returncode)
    raise SystemExit(main())
