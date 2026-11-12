"""Juno's hands on Michael's Discord server: channels and categories only (DV17).

  python tools/discord_admin.py list
      Every channel and category: id, name, kind, category, topic.
  python tools/discord_admin.py create --name NAME [--kind text|voice|category] [--category NAME] [--topic TEXT]
  python tools/discord_admin.py rename --channel NAME_OR_ID --to NAME
  python tools/discord_admin.py topic --channel NAME_OR_ID --text TEXT
  python tools/discord_admin.py move --channel NAME_OR_ID --category NAME
  python tools/discord_admin.py archive --channel NAME_OR_ID
      Moves the channel into an "Archive" category (made if missing). Nothing is ever deleted: there is no delete
      command, and the bot has no permission to manage roles, members, bans or messages.
  python tools/discord_admin.py server [--name NAME] [--icon FILE] [--banner FILE]
      The server's name, icon and banner (Manage Server). FILE is a PNG, JPG or GIF inside this project folder (a
      photo Michael sent lands in state/attachments/). A banner needs the server at Boost level 2; Discord says so
      if not.

Writes run while me/automation.yaml has discord.channel as auto or auto_notify (Juno then tells Michael in plain
words); on ask they refuse with exit 4 and the coordinator asks him first. Every write goes to state/audit.jsonl.
The bot must be in exactly one server, or JUNO_DISCORD_GUILD names it. Output is JSON. Exit codes: 0 ok, 3 no
token, 4 not allowed or Discord refused, 5 bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))

KINDS = {"text": 0, "voice": 2, "category": 4}
KIND_NAMES = {0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum"}
ARCHIVE = "Archive"
NAME_OK = re.compile(r"^[^@#:`]{1,100}$")


class AdminError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _mode(root: Path = ROOT) -> str:
    import yaml
    path = root / "me" / "automation.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return str(((data or {}).get("actions") or {}).get("discord.channel", {}).get("mode", "ask"))


def _rest():
    import discord_transport
    import token_store
    try:
        token = token_store.fetch_tokens(token_store.DISCORD_REFS)["DISCORD_BOT_TOKEN"]
    except token_store.TokenError as exc:
        raise AdminError(3, f"no Discord bot token: {exc}") from None
    return discord_transport.Rest(token)


def guild_id(rest) -> str:
    if os.environ.get("JUNO_DISCORD_GUILD"):
        return os.environ["JUNO_DISCORD_GUILD"]
    guilds = rest("GET", "/users/@me/guilds")
    if len(guilds) != 1:
        raise AdminError(5, f"the bot is in {len(guilds)} servers; set JUNO_DISCORD_GUILD to pick one")
    return guilds[0]["id"]


def channels(rest, gid: str) -> list[dict]:
    raw = rest("GET", f"/guilds/{gid}/channels")
    cats = {c["id"]: c["name"] for c in raw if c.get("type") == 4}
    return sorted(({"id": c["id"], "name": c["name"], "kind": KIND_NAMES.get(c.get("type"), str(c.get("type"))),
                    "category": cats.get(c.get("parent_id") or "", ""), "topic": c.get("topic") or "",
                    "position": c.get("position", 0)} for c in raw),
                  key=lambda c: (c["category"], c["kind"] != "category", c["position"]))


def find(chans: list[dict], ref: str, kind: str | None = None) -> dict:
    ref = ref.strip().lstrip("#")
    hits = [c for c in chans if (c["id"] == ref or c["name"].lower() == ref.lower())
            and (kind is None or c["kind"] == kind)]
    if not hits:
        raise AdminError(5, f"no {kind or 'channel'} named '{ref}'")
    if len(hits) > 1:
        raise AdminError(5, f"{len(hits)} match '{ref}'; use the id: {', '.join(h['id'] for h in hits)}")
    return hits[0]


def _name(name: str, kind: str) -> str:
    name = name.strip()
    if not NAME_OK.match(name):
        raise AdminError(5, "a name is 1 to 100 characters with no @, #, : or `")
    return re.sub(r"\s+", "-", name.lower()) if kind == "text" else name


def _audit(root: Path, action: str, detail: dict) -> None:
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": f"discord.{action}",
            "class": "discord.channel", **detail}
    with (state / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def _category(rest, gid: str, chans: list[dict], name: str, make: bool = False) -> str:
    try:
        return find(chans, name, "category")["id"]
    except AdminError:
        if not make:
            raise
    made = rest("POST", f"/guilds/{gid}/channels", {"name": name, "type": 4})
    return made["id"]


IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}
IMAGE_MAX = 8 * 1024 * 1024


def _image(path: str, root: Path) -> str:
    """A local image as the data URI Discord wants. Only files inside the project folder."""
    import base64
    f = Path(path) if Path(path).is_absolute() else root / path
    f = f.resolve()
    if root.resolve() not in f.parents or not f.is_file():
        raise AdminError(5, "the image must be a file inside the project folder")
    mime = IMAGE_MIME.get(f.suffix.lower())
    if not mime or f.stat().st_size > IMAGE_MAX:
        raise AdminError(5, "the image must be a PNG, JPG or GIF under 8 MB")
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode("ascii")


def run(args, rest=None, root: Path = ROOT) -> dict:
    rest = rest or _rest()
    gid = guild_id(rest)
    if args.cmd == "list":
        g = rest("GET", f"/guilds/{gid}")
        return {"server": {"name": g.get("name"), "boost_level": g.get("premium_tier", 0),
                           "has_icon": bool(g.get("icon")), "has_banner": bool(g.get("banner"))},
                "channels": channels(rest, gid)}
    chans = channels(rest, gid) if args.cmd != "server" else []
    mode = _mode(root)
    if mode not in ("auto", "auto_notify"):
        raise AdminError(4, f"discord.channel is '{mode}': ask Michael first")
    if args.cmd == "server":
        body = {}
        if args.name:
            if not NAME_OK.match(args.name.strip()) or len(args.name.strip()) < 2:
                raise AdminError(5, "a server name is 2 to 100 characters with no @, #, : or `")
            body["name"] = args.name.strip()
        if args.icon:
            body["icon"] = _image(args.icon, root)
        if args.banner:
            body["banner"] = _image(args.banner, root)
        if not body:
            raise AdminError(5, "say what to change: --name, --icon or --banner")
        was = rest("GET", f"/guilds/{gid}").get("name", "")
        got = rest("PATCH", f"/guilds/{gid}", body)
        out = {"done": "server updated", "id": gid, "name": got.get("name", body.get("name", was)), "was": was,
               "changed": sorted(body)}
        _audit(root, "server", {k: v for k, v in out.items() if k != "done"})
        return out
    if args.cmd == "create":
        body = {"name": _name(args.name, args.kind), "type": KINDS[args.kind]}
        if args.category and args.kind != "category":
            body["parent_id"] = _category(rest, gid, chans, args.category)
        if args.topic and args.kind == "text":
            body["topic"] = args.topic[:1024]
        made = rest("POST", f"/guilds/{gid}/channels", body)
        out = {"done": "created", "id": made["id"], "name": made["name"], "kind": args.kind}
    else:
        ch = find(chans, args.channel)
        if args.cmd == "rename":
            body = {"name": _name(args.to, ch["kind"])}
        elif args.cmd == "topic":
            if ch["kind"] != "text":
                raise AdminError(5, "only text channels have a topic")
            body = {"topic": args.text[:1024]}
        elif args.cmd == "move":
            body = {"parent_id": _category(rest, gid, chans, args.category)}
        else:  # archive
            if ch["kind"] == "category":
                raise AdminError(5, "archive a channel, not a category")
            body = {"parent_id": _category(rest, gid, chans, ARCHIVE, make=True)}
        rest("PATCH", f"/channels/{ch['id']}", body)
        out = {"done": {"rename": "renamed", "topic": "topic set", "move": "moved", "archive": "archived"}[args.cmd],
               "id": ch["id"], "name": body.get("name", ch["name"]), "was": ch["name"]}
    _audit(root, args.cmd, {k: v for k, v in out.items() if k != "done"})
    return out


VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _in_project_python(argv: list[str]) -> int | None:
    """Juno's runs call the system Python, which lacks keyring and discord's libraries. Rerun this script in the
    project's own .venv when that happens; None means we're already where we need to be."""
    try:
        import keyring  # noqa: F401
        return None
    except ImportError:
        pass
    if not VENV_PYTHON.exists() or Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return None
    import subprocess
    return subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *argv]).returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rerun = _in_project_python(argv)
    if rerun is not None:
        return rerun
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--kind", choices=sorted(KINDS), default="text")
    c.add_argument("--category")
    c.add_argument("--topic")
    for cmd, extra in (("rename", ("--to",)), ("topic", ("--text",)), ("move", ("--category",)), ("archive", ())):
        s = sub.add_parser(cmd)
        s.add_argument("--channel", required=True)
        for flag in extra:
            s.add_argument(flag, required=True)
    sv = sub.add_parser("server")
    sv.add_argument("--name")
    sv.add_argument("--icon")
    sv.add_argument("--banner")
    args = p.parse_args(argv)
    try:
        out = run(args)
    except AdminError as exc:
        print(json.dumps({"error": str(exc)}))
        return exc.code
    except Exception as exc:  # Discord refused (DiscordError) or the network failed
        print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:200]}"}))
        return 4
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
