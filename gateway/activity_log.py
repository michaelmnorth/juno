"""A plain daily log of what happened in Michael's DM with Juno (Michael 2026-11-15).

He asked that the project's coordinator (Claude in the claude.ai project) know what he and Juno said and did without
him sending screenshots. Every DM he sends, every reply and ping Juno posts, every card and tap and every payment or
build outcome lands as one line in `logs/conversations/YYYY-MM-DD.md` (his Eastern day). `logs/` is git-ignored, so
this stays on his PC; the coordinator reads it through the folder he approved for the project.

Secrets never land here: card numbers, security codes, API keys and tokens, 1Password references and passkey or
one-time codes are replaced before anything is written. Writing never breaks a reply.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")
FOLDER = Path("logs") / "conversations"
ENTRY_MAX = 4000
_lock = threading.Lock()

# Order matters: the card-number rule runs before the long-token rule.
REDACTIONS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[number removed]"),  # card and account numbers
    (re.compile(r"(?i)\b(cvc|cvv|cid|security code|passcode|one-time code|verification code|otp|pin)\b"
                r"(\W{0,3})(\d{3,8})\b"), r"\1\2[removed]"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}"), "[key removed]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}"), "[token removed]"),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{8,}"), "[token removed]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), "[token removed]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"), "[key removed]"),
    (re.compile(r"\bops_[A-Za-z0-9_-]{20,}"), "[token removed]"),  # 1Password service account
    (re.compile(r"op://[^\s)>\]]+"), "[1Password reference removed]"),
    (re.compile(r"\b[MN][A-Za-z\d_-]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"), "[token removed]"),  # Discord bot
    (re.compile(r"(?i)\b(password|passwd|secret|api[_ -]?key|token)\b(\s*[:=]\s*)\S+"), r"\1\2[removed]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[token removed]"),  # JWT
)


def redact(text: str) -> str:
    text = str(text or "")
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def path_for(root: Path, now: datetime | None = None) -> Path:
    local = (now or datetime.now(timezone.utc)).astimezone(ZONE)
    return Path(root) / FOLDER / f"{local:%Y-%m-%d}.md"


def write(root: Path, who: str, text: str, now: datetime | None = None) -> None:
    """One entry. `who` is "Michael", "Juno", or a bracketed event like "[approved]". Never raises."""
    try:
        text = redact(text).strip()
        if not text:
            return
        if len(text) > ENTRY_MAX:
            text = text[:ENTRY_MAX - 1].rstrip() + "…"
        now = now or datetime.now(timezone.utc)
        path = path_for(root, now)
        local = now.astimezone(ZONE)
        body = text.replace("\r", "").replace("\n", "\n  ")  # continuation lines stay inside the entry
        line = f"- {local:%H:%M} **{who}:** {body}\n"
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            with path.open("a", encoding="utf-8") as fh:
                if new:
                    fh.write(f"# Juno conversation log, {local:%A %B} {local.day}, {local.year} (Eastern)\n\n")
                fh.write(line)
    except Exception:  # bookkeeping: never breaks a reply
        pass


# Audit events worth a line, with the word the log uses. The rest (v2 routing, overflow) is plumbing.
AUDIT_WORDS = {
    "posted": "card posted", "approved": "tapped yes", "denied": "tapped no", "auto_approved": "ran without a tap",
    "always_allow_added": "tapped always", "expired": "card expired", "executed": "done", "declined": "declined",
    "send_failed": "send failed", "draft_changed": "draft changed, not sent", "submit_failed": "form failed",
    "submit_stopped": "form stopped", "installed": "installed", "install_failed": "install failed",
    "payment_carded": "pay card", "payment_requested": "asked Link", "payment_failed": "payment failed",
    "payment_reminded": "payment reminder", "payment_expired": "payment expired", "payment_declined":
    "payment declined", "payment_paid": "paid", "payment_stopped": "payment stopped",
    "payload_changed": "card changed, refused", "dropped_after_expiry": "dropped",
    "build_carded": "build card", "build_started": "build started", "build_failed": "build failed",
    "build_skipped": "build skipped",
}


def audit_line(root: Path, event: str, summary: str, note: str = "", now: datetime | None = None) -> None:
    word = AUDIT_WORDS.get(event)
    if not word:
        return
    write(root, f"[{word}]", f"{summary}" + (f" — {note}" if note else ""), now)
