"""Juno's own Gmail writer: drafts and Juno/ labels, through the same OAuth app as google_read.py.

What it can't do, on purpose: send to anyone but Michael, trash, archive, touch system labels or labels outside
"Juno/". Sending to anyone else stays with the bridge's approval run (send_message locked to one draft id by
.claude/hooks/gate_outward.py).

  python tools/gmail.py draft --to a@b.com [--cc c@d.com] --subject "..." --body-file path|- [--reply-to MSG_ID]
                              [--context "friend (Sam)"]
      New draft, or a reply in the thread of MSG_ID (threading headers set, "Re:" added). With --context it also
      writes the state/drafts.jsonl line the sweep uses. Prints {"draft_id", "message_id", "thread_id", "link"}.
  python tools/gmail.py update-draft --id DRAFT_ID --body-file path|- [--subject "..."]
      Same recipients and thread, new text. Refused inside an approved send run.
  python tools/gmail.py send-self --id DRAFT_ID
      Sends a draft whose every recipient is Michael's own address, while me/automation.yaml has email.send.self as
      auto. Anyone else on To, Cc or Bcc and it refuses. Logged to state/audit.jsonl.
  python tools/gmail.py labels
      Juno/ labels with message counts.
  python tools/gmail.py attachments --message MSG_ID
      Saves the text, Markdown, CSV, PDF and photo attachments of mail from Michael or a known sender to
      state/attachments/ (a PDF also gets a .txt of its text) and prints their paths. Refuses other senders.
  python tools/gmail.py label (--message ID | --thread ID) [--add Juno/X ...] [--remove Juno/Y ...]
      Juno/ labels only; a missing one is created on --add.

Bodies are plain text, from a file or stdin (-). Every draft gets Michael's Gmail signature (his default send-as
address), as Gmail itself would add it: an HTML part with the signature and a plain-text copy. --no-signature skips it. Exit codes as google_read.py: 0 ok, 3 not signed in, 4 Google
refused, 5 bad input.
"""
from __future__ import annotations

import argparse
import base64
import email
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import approval_policy  # noqa: E402
import google_read  # noqa: E402
import trust  # noqa: E402
from google_read import BAD_INPUT, GMAIL, OK, GoogleError  # noqa: E402

ROOT = google_read.ROOT
DRAFTS_LOG = ROOT / "state" / "drafts.jsonl"
FROM = trust.ME[0] if trust.ME else ""
LABEL_PREFIX = "Juno/"
EMAIL_RE = re.compile(r"^[^@\s,<>]+@[^@\s,<>]+\.[^@\s,<>]+$")
LABEL_RE = re.compile(r"^Juno/[A-Za-z0-9 _&-]{1,40}(/[A-Za-z0-9 _&-]{1,40})?$")
MAX_RECIPIENTS = 10
MAX_BODY = 20_000


def _bad(message: str) -> GoogleError:
    return GoogleError(BAD_INPUT, message)


def check_recipients(addrs: list[str]) -> list[str]:
    out = [a.strip() for a in addrs if a and a.strip()]
    if not out:
        raise _bad("at least one --to address")
    if len(out) > MAX_RECIPIENTS:
        raise _bad(f"at most {MAX_RECIPIENTS} recipients")
    for a in out:
        if not EMAIL_RE.match(a):
            raise _bad(f"not an email address: {a!r}")
    return out


def check_label(name: str) -> str:
    if not LABEL_RE.match(name):
        raise _bad(f"labels must look like Juno/Name (letters, digits, spaces, _ & -): {name!r}")
    return name


def read_body(source: str, stdin=None) -> str:
    text = (stdin or sys.stdin).read() if source == "-" else Path(source).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").strip("\n")
    if not text.strip():
        raise _bad("the body is empty")
    if len(text) > MAX_BODY:
        raise _bad(f"the body is over {MAX_BODY} characters")
    return text + "\n"


def signature(token: str, get=None) -> str:
    """The HTML signature on his default send-as address, or "" (none set, or Gmail wouldn't say)."""
    get = get or google_read._get
    try:
        sends = get(f"{GMAIL}/settings/sendAs", token).get("sendAs", [])
    except GoogleError:
        return ""
    return next((x.get("signature", "") for x in sends if x.get("isDefault")), "")


def html_to_text(markup: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</(div|p|li|tr)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def build_raw(to: list[str], cc: list[str], subject: str, body: str, in_reply_to: str = "",
              references: str = "", sig: str = "") -> str:
    msg = EmailMessage()
    if FROM:
        msg["From"] = FROM
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip()
    if sig:
        msg.set_content(body.rstrip("\n") + "\n\n" + html_to_text(sig) + "\n")
        markup = html.escape(body.rstrip("\n")).replace("\n", "<br>\n")
        msg.add_alternative(f'<div dir="ltr">{markup}<br><br><div dir="ltr" class="gmail_signature">{sig}</div></div>',
                            subtype="html")
    else:
        msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def reply_subject(subject: str) -> str:
    return subject if re.match(r"(?i)^re:", subject.strip()) else f"Re: {subject.strip()}"


def _headers(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def link(message_id: str) -> str:
    return f"https://mail.google.com/mail/u/0/#drafts?compose={message_id}"


REPEAT_WINDOW = timedelta(hours=12)


def recent_draft(thread_id: str, log: Path = DRAFTS_LOG, now: datetime | None = None) -> dict | None:
    """A draft Juno already made in this thread in the last 12 hours, from state/drafts.jsonl. Two runs answering
    the same mail (a sweep and a DM) would otherwise leave two drafts and two Send cards."""
    if not thread_id or not log.exists():
        return None
    now = now or datetime.now(timezone.utc)
    found = None
    for raw in log.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
            made = datetime.fromisoformat(str(row.get("created", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if row.get("thread_id") == thread_id and now - made <= REPEAT_WINDOW:
            found = row
    return found


def draft(to: list[str], cc: list[str], subject: str, body: str, reply_to: str = "", context: str = "",
          token: str | None = None, call=None, get=None, log: Path = DRAFTS_LOG, with_signature: bool = True,
          again: bool = False) -> dict:
    call, get = call or google_read.call, get or google_read._get
    to, cc = check_recipients(to), (check_recipients(cc) if cc else [])
    token = token or google_read.access_token()
    thread_id, in_reply_to, references = "", "", ""
    if reply_to:
        orig = get(f"{GMAIL}/messages/{reply_to}", token,
                   {"format": "metadata", "metadataHeaders": ["Subject", "Message-ID", "References"]})
        h = _headers(orig.get("payload", {}))
        thread_id, in_reply_to, references = orig.get("threadId", ""), h.get("message-id", ""), h.get("references", "")
        subject = subject or reply_subject(h.get("subject", ""))
        earlier = None if again else recent_draft(thread_id, log)
        if earlier:
            return {"draft_id": earlier.get("draft_id", ""), "thread_id": thread_id, "existing": True,
                    "note": "a draft for this thread was made in the last 12 hours; update it with update-draft, "
                            "or pass --again for a second one"}
    if not subject.strip():
        raise _bad("a --subject (or --reply-to to take the thread's)")
    sig = signature(token, get) if with_signature else ""
    message = {"raw": build_raw(to, cc, subject, body, in_reply_to, references, sig)}
    if thread_id:
        message["threadId"] = thread_id
    made = call("POST", f"{GMAIL}/drafts", token, {"message": message})
    msg = made.get("message", {})
    out = {"draft_id": made.get("id", ""), "message_id": msg.get("id", ""),
           "thread_id": msg.get("threadId", thread_id), "link": link(msg.get("id", ""))}
    if context:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"draft_id": out["draft_id"], "thread_id": out["thread_id"], "to": ", ".join(to),
                                 "context": context[:200], "created": _now(), "draft_text": body.strip()},
                                ensure_ascii=False) + "\n")
    return out


def update_draft(draft_id: str, body: str, subject: str = "", env=None, token: str | None = None, call=None,
                 get=None, with_signature: bool = True) -> dict:
    env = os.environ if env is None else env
    if env.get("COORDINATOR_APPROVED_CLASS") == "email.send":
        raise GoogleError(google_read.REFUSED, "the draft can't change after Michael approved sending it")
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    old = get(f"{GMAIL}/drafts/{draft_id}", token, {"format": "metadata"})
    msg = old.get("message", {})
    h = _headers(msg.get("payload", {}))
    to = [a.strip() for a in h.get("to", "").split(",") if a.strip()]
    cc = [a.strip() for a in h.get("cc", "").split(",") if a.strip()]
    message = {"raw": build_raw(to, cc, subject or h.get("subject", ""), body, h.get("in-reply-to", ""),
                                h.get("references", "").replace(h.get("in-reply-to", ""), "").strip(),
                                signature(token, get) if with_signature else "")}
    if msg.get("threadId"):
        message["threadId"] = msg["threadId"]
    made = call("PUT", f"{GMAIL}/drafts/{draft_id}", token, {"id": draft_id, "message": message})
    new = made.get("message", {})
    return {"draft_id": made.get("id", draft_id), "message_id": new.get("id", ""),
            "thread_id": new.get("threadId", ""), "link": link(new.get("id", ""))}


def send_self(draft_id: str, token: str | None = None, call=None, get=None, mode=None,
              state: Path = ROOT / "state") -> dict:
    mode = mode or google_read.automation_mode
    if mode("email.send.self") != "auto":
        raise GoogleError(google_read.REFUSED, "email to Michael himself needs a tap (me/automation.yaml)")
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    raw = get(f"{GMAIL}/drafts/{draft_id}", token, {"format": "raw"}).get("message", {}).get("raw", "")
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    people = {addr.lower() for _, addr in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])
                                                         + msg.get_all("Bcc", [])) if addr}
    if not people or people - set(trust.ME):
        raise GoogleError(google_read.REFUSED, "not only to Michael: this one needs a tap")
    sent = call("POST", f"{GMAIL}/drafts/send", token, {"id": draft_id})
    approval_policy.audit(state, "auto_sent_self", {"id": draft_id, "action_class": "email.send.self",
                                                    "summary": str(msg.get("Subject", ""))}, "me/automation.yaml")
    return {"sent": True, "message_id": sent.get("id", ""), "thread_id": sent.get("threadId", "")}


def _norm(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").replace("\r", "").strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def _plain_body(msg) -> str:
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "text/html":
            return html_to_text(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace"))
    return ""


def send_approved(draft_id: str, to: str, draft_text: str, token: str | None = None, call=None, get=None) -> dict:
    """Send the draft Michael approved, in code, only if it still is what his card showed: the same recipients and
    the same text (plus his signature). Anything else changed it after the card, so nothing is sent and the caller
    shows him the current version instead (docs/v2/05-SECURITY.md control 3). Returns {"sent": True, ...} or
    {"sent": False, "why", "current_text"}."""
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    raw = get(f"{GMAIL}/drafts/{draft_id}", token, {"format": "raw"}).get("message", {}).get("raw", "")
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    people = {addr.lower() for _, addr in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])
                                                         + msg.get_all("Bcc", [])) if addr}
    approved = {addr.lower() for _, addr in getaddresses([to or ""]) if addr}
    body = _norm(_plain_body(msg))
    if not approved or people != approved:
        return {"sent": False, "why": "recipients changed", "current_text": body}
    expected = _norm(draft_text)
    if body != expected and body != _norm(draft_text.rstrip("\n") + "\n\n" + html_to_text(signature(token, get))):
        return {"sent": False, "why": "text changed", "current_text": body}
    sent = call("POST", f"{GMAIL}/drafts/send", token, {"id": draft_id})
    return {"sent": True, "message_id": sent.get("id", ""), "thread_id": sent.get("threadId", "")}


def juno_labels(token: str, get=None) -> dict[str, str]:
    get = get or google_read._get
    return {lab["name"]: lab["id"] for lab in get(f"{GMAIL}/labels", token).get("labels", [])
            if lab.get("type") == "user" and lab.get("name", "").startswith(LABEL_PREFIX)}


def list_labels(token: str | None = None, get=None) -> list[dict]:
    get = get or google_read._get
    token = token or google_read.access_token()
    out = []
    for name, lid in sorted(juno_labels(token, get).items()):
        info = get(f"{GMAIL}/labels/{lid}", token)
        out.append({"name": name, "messages": info.get("messagesTotal", 0), "unread": info.get("messagesUnread", 0)})
    return out


def label(target: str, kind: str, add: list[str], remove: list[str], token: str | None = None, call=None,
          get=None) -> dict:
    if not add and not remove:
        raise _bad("nothing to do: give --add or --remove")
    add, remove = [check_label(n) for n in add], [check_label(n) for n in remove]
    call, get = call or google_read.call, get or google_read._get
    token = token or google_read.access_token()
    have = juno_labels(token, get)
    for name in add:
        if name not in have:
            have[name] = call("POST", f"{GMAIL}/labels", token, {
                "name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"})["id"]
    body = {"addLabelIds": [have[n] for n in add], "removeLabelIds": [have[n] for n in remove if n in have]}
    call("POST", f"{GMAIL}/{'threads' if kind == 'thread' else 'messages'}/{target}/modify", token, body)
    return {kind: target, "added": add, "removed": [n for n in remove if n in have]}


# --- attachments (P2 brief, #7) ------------------------------------------------------------------------------------
ATTACH_DIR = ROOT / "state" / "attachments"
ATTACH_MAX = 10 * 1024 * 1024
ATTACH_TYPES = {"text/plain": "txt", "text/markdown": "md", "text/x-markdown": "md", "text/csv": "csv",
                "application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
                "image/webp": "webp"}
ATTACH_EXTS = {"txt": "txt", "md": "md", "markdown": "md", "csv": "csv", "pdf": "pdf", "jpg": "jpg", "jpeg": "jpg",
               "png": "png", "gif": "gif", "webp": "webp"}
ATTACH_FROM = ("michael", "known")  # never for contact or unknown senders (CLAUDE.md, Trust labels)


def _attach_ext(part: dict) -> str:
    mime = (part.get("mimeType") or "").split(";")[0].lower()
    if mime in ATTACH_TYPES:
        return ATTACH_TYPES[mime]
    name = part.get("filename") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ATTACH_EXTS.get(ext, "") if mime in ("", "application/octet-stream") or mime.startswith("text/") else ""


def pdf_text(path: Path) -> str:
    """The text of a PDF, or "" when pypdf is missing or the file has none (a scan)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        return "\n\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages[:50]).strip()
    except Exception:
        return ""


def attachments(message_id: str, token: str | None = None, get=None, root: Path | None = None,
                label=None) -> dict:
    """Save the readable attachments of one message (text, Markdown, CSV, PDF, photos) to state/attachments/ and
    return their paths. Only for mail from Michael himself or someone with a people/ file. Files are named by the
    message id, never by the sender's file name. A PDF also gets a .txt copy of its text."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", message_id or ""):
        raise _bad("not a Gmail message id")
    get = get or google_read._get
    token = token or google_read.access_token()
    folder = (root / "state" / "attachments") if root else ATTACH_DIR
    msg = get(f"{GMAIL}/messages/{message_id}", token, {"format": "full"})
    payload = msg.get("payload", {})
    sender = next((a for _, a in getaddresses([_headers(payload).get("from", "")]) if a), "")
    who = (label or trust.label)(sender)
    if who not in ATTACH_FROM:
        return {"saved": [], "refused": f"attachments from a {who} sender are never opened"}
    saved, skipped, stack, n = [], [], [payload], 0
    while stack:
        part = stack.pop(0)
        stack.extend(part.get("parts") or [])
        body = part.get("body") or {}
        if not (part.get("filename") and body.get("attachmentId")):
            continue
        ext = _attach_ext(part)
        size = int(body.get("size") or 0)
        if not ext or size > ATTACH_MAX or n >= 10:
            skipped.append({"type": part.get("mimeType", ""), "kb": round(size / 1024)})
            continue
        got = get(f"{GMAIL}/messages/{message_id}/attachments/{body['attachmentId']}", token)
        raw = got.get("data", "")
        data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(data) > ATTACH_MAX:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"gmail-{message_id}-{n}.{ext}"
        path.write_bytes(data)
        item = {"path": path.relative_to(folder.parents[1]).as_posix(), "type": part.get("mimeType", ""),
                "kb": round(len(data) / 1024), "name": re.sub(r"[^\w .()-]", "", part["filename"])[:60]}
        if ext == "pdf":
            txt = pdf_text(path)
            if txt:
                path.with_suffix(".txt").write_text(txt, encoding="utf-8")
                item["text_path"] = path.with_suffix(".txt").relative_to(folder.parents[1]).as_posix()
        saved.append(item)
        n += 1
    return {"saved": saved, "skipped": skipped, "from": who}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gmail.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--to", action="append", default=[])
    d.add_argument("--cc", action="append", default=[])
    d.add_argument("--subject", default="")
    d.add_argument("--body-file", required=True)
    d.add_argument("--reply-to", default="")
    d.add_argument("--context", default="")
    d.add_argument("--no-signature", action="store_true")
    d.add_argument("--again", action="store_true")
    u = sub.add_parser("update-draft")
    u.add_argument("--id", required=True)
    u.add_argument("--body-file", required=True)
    u.add_argument("--subject", default="")
    u.add_argument("--no-signature", action="store_true")
    ss = sub.add_parser("send-self")
    ss.add_argument("--id", required=True)
    sub.add_parser("labels")
    att = sub.add_parser("attachments")
    att.add_argument("--message", required=True)
    lab = sub.add_parser("label")
    where = lab.add_mutually_exclusive_group(required=True)
    where.add_argument("--message")
    where.add_argument("--thread")
    lab.add_argument("--add", action="append", default=[])
    lab.add_argument("--remove", action="append", default=[])
    return p


def _split(values: list[str]) -> list[str]:
    return [v.strip() for value in values for v in value.split(",") if v.strip()]


def main(argv: list[str]) -> int:
    relaunched = google_read.ensure_venv([__file__, *argv])
    if relaunched is not None:
        return relaunched
    try:
        args = parser().parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        google_read.load_secrets()
        if args.cmd == "draft":
            out = draft(_split(args.to), _split(args.cc), args.subject, read_body(args.body_file), args.reply_to,
                        args.context, with_signature=not args.no_signature, again=args.again)
        elif args.cmd == "update-draft":
            out = update_draft(args.id, read_body(args.body_file), args.subject,
                               with_signature=not args.no_signature)
        elif args.cmd == "send-self":
            out = send_self(args.id)
        elif args.cmd == "labels":
            out = list_labels()
        elif args.cmd == "attachments":
            out = attachments(args.message)
        else:
            out = label(args.message or args.thread, "message" if args.message else "thread", args.add, args.remove)
        print(json.dumps(out))  # ASCII-safe: the Windows console chokes on emoji in titles
        return OK
    except (GoogleError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", BAD_INPUT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
