"""tools/youtube.py offline behavior: input checks, timestamps, untrusted wrapping, rate limits."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import youtube  # noqa: E402


@pytest.mark.parametrize("value", [
    "dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
    "https://youtu.be/dQw4w9WgXcQ?si=abc",
    "youtube.com/shorts/dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_video_id_accepts_youtube_forms(value):
    assert youtube.video_id(value) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("value", [
    "https://evil.example.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
    "file:///C:/Windows/win.ini",
    "dQw4w9WgXc; rm -rf /",
])
def test_video_id_refuses_everything_else(value):
    with pytest.raises(youtube.ToolError) as exc:
        youtube.video_id(value)
    assert exc.value.code == youtube.BAD_INPUT


def test_clean_strips_markup_and_control_characters():
    assert youtube.clean("<b>Hi</b>\x07  there\n") == "Hi there"


def test_text_output_has_timestamps_and_untrusted_tags():
    data = {"video_id": "dQw4w9WgXcQ", "title": "T", "channel": "C", "duration": 100, "source": "manual", "lang": "en",
            "segments": [{"start": 0, "dur": 5, "text": "intro"}, {"start": 31, "dur": 5, "text": "point"},
                         {"start": 3700, "dur": 5, "text": "late"}]}
    out = youtube.as_text(data)
    assert '<untrusted_transcript video_id="dQw4w9WgXcQ">' in out and out.endswith("</untrusted_transcript>")
    assert "[0:00] intro" in out and "[0:31] point" in out and "[1:01:40] late" in out


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "CACHE", tmp_path)
    monkeypatch.setattr(youtube, "RATE_FILE", tmp_path / "_rate.json")
    monkeypatch.setattr(youtube, "MIN_GAP_SECONDS", 0)
    return tmp_path


def test_cooldown_blocks_without_calling_youtube(cache):
    youtube.blocked("429")
    with pytest.raises(youtube.ToolError) as exc:
        youtube.throttle()
    assert exc.value.code == youtube.BLOCKED


def test_daily_limit(cache):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (cache / "_rate.json").write_text(json.dumps({"day": today, "count": youtube.DAILY_LIMIT}), encoding="utf-8")
    with pytest.raises(youtube.ToolError):
        youtube.throttle()


def test_cached_transcript_needs_no_network(cache, monkeypatch):
    monkeypatch.setattr(youtube, "throttle", lambda: pytest.fail("network used"))
    (cache / "dQw4w9WgXcQ.en.json").write_text(json.dumps({"video_id": "dQw4w9WgXcQ", "text": "hi"}), encoding="utf-8")
    assert youtube.transcript("dQw4w9WgXcQ")["text"] == "hi"


def test_stale_info_is_refetched(cache, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    (cache / "dQw4w9WgXcQ.info.json").write_text(json.dumps({"fetched_at": old}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(youtube, "ytdlp", lambda *a, **k: calls.append(a) or json.dumps({"title": "New"}))
    assert youtube.info("dQw4w9WgXcQ")["title"] == "New" and calls
