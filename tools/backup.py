"""Encrypted backups of the personal layer that git doesn't hold, and a restore drill (docs/v2 brief P0, item 1).

What goes in: me/, people/, observed/, learnings/, state/, data/, domains/, logs/, docs/private/, and the Claude session
transcripts for this folder. No .env files. One archive, encrypted with gpg (AES-256, passphrase from 1Password as
Agent-Secrets/Backup-Juno/passphrase, or JUNO_BACKUP_PASSPHRASE for a test), written to the folder in
me/backup.yaml (`to:`, for example a OneDrive folder, which syncs it off this PC; `keep:` how many to keep, default 14).

  python tools/backup.py run [--to DIR]           make one backup; prints {"file", "bytes", "files"}
  python tools/backup.py restore --file F --into DIR   decrypt and unpack into an empty scratch folder
  python tools/backup.py drill [--into DIR]       restore the newest backup into a scratch folder and compare it file
                                                  by file with what it saved; prints {"ok", "files", "missing", "changed"}

Never restores into this folder. Exit codes: 0 ok, 3 no passphrase or no target yet, 4 gpg failed, 5 bad input,
6 the drill found differences.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

LAYER = ("me", "people", "observed", "learnings", "state", "data", "domains", "logs", "docs/private")
TRANSCRIPTS = Path.home() / ".claude" / "projects" / "C--Users-Michael-Claude-Personal-personal-coordinator"
REF = "op://Agent-Secrets/Backup-Juno/passphrase"
MANIFEST = "MANIFEST.json"
OK, NO_SETUP, GPG_FAILED, BAD_INPUT, DIFFERS = 0, 3, 4, 5, 6
SKIP_NAMES = (".env",)


class BackupError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def find_gpg() -> str:
    for c in (os.environ.get("GPG_BIN"), shutil.which("gpg"), r"C:\Program Files\Git\usr\bin\gpg.exe",
              r"C:\Program Files (x86)\GnuPG\bin\gpg.exe", r"C:\Program Files\GnuPG\bin\gpg.exe"):
        if c and Path(c).exists():
            return c
    raise BackupError(GPG_FAILED, "gpg not found (it comes with Git for Windows)")


def passphrase() -> str:
    if os.environ.get("JUNO_BACKUP_PASSPHRASE"):
        return os.environ["JUNO_BACKUP_PASSPHRASE"]
    import google_read
    token_store = google_read._token_store()
    try:
        value = token_store.read_ref(token_store.find_op(), REF, google_read._sa_key(token_store))
    except Exception as exc:  # no item yet, or 1Password unreachable
        raise BackupError(NO_SETUP, f"no backup passphrase yet (fill Agent-Secrets/Backup-Juno/passphrase): {exc}")
    if not value or value == "FILL-ME":
        raise BackupError(NO_SETUP, "the Backup-Juno item in 1Password is still empty")
    return value


def settings(root: Path = ROOT) -> dict:
    path = root / "me" / "backup.yaml"
    if not path.exists():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def sources(root: Path = ROOT, transcripts: Path = TRANSCRIPTS) -> list[tuple[Path, str]]:
    """(file on disk, name in the archive) for everything that goes in."""
    out = []
    for top in LAYER:
        base = root / top
        if base.exists():
            out += [(p, p.relative_to(root).as_posix()) for p in sorted(base.rglob("*"))
                    if p.is_file() and not p.name.startswith(SKIP_NAMES)]
    if transcripts.exists():
        out += [(p, "transcripts/" + p.relative_to(transcripts).as_posix()) for p in sorted(transcripts.rglob("*"))
                if p.is_file()]
    return out


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gpg_path(path: str, gpg: str) -> str:
    """Git for Windows' gpg is an MSYS program: it wants /c/Users/... rather than a drive-letter path."""
    if os.name != "nt" or "usr" not in Path(gpg).parts or len(path) < 3 or path[1] != ":":
        return path
    return "/" + path[0].lower() + path[2:].replace("\\", "/")


def _gpg(args: list[str], data: bytes, secret: str) -> bytes:
    """Data in on stdin, result on stdout. The passphrase sits in a private temp folder that gpg reads once, never
    on the command line; that folder is also gpg's home, so nothing touches his own keyring."""
    gpg = find_gpg()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        pw = Path(tmp) / "pw"
        pw.write_text(secret, encoding="utf-8")
        home = _gpg_path(tmp, gpg)
        cmd = [gpg, "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback", "--passphrase-file",
               _gpg_path(str(pw), gpg), "--homedir", home, *args]
        try:
            done = subprocess.run(cmd, input=data, capture_output=True, timeout=600,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            pw.unlink(missing_ok=True)
            agent = Path(gpg).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")
            if agent.exists():  # gpg starts an agent for this home; stop it so the folder can go
                subprocess.run([str(agent), "--homedir", home, "--kill", "all"], capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise BackupError(GPG_FAILED, "gpg failed: " + done.stderr.decode("utf-8", "replace")[-300:])
    return done.stdout


def run(to: Path, root: Path = ROOT, transcripts: Path = TRANSCRIPTS, keep: int = 14, secret: str | None = None,
        now: datetime | None = None) -> dict:
    to = Path(to)
    if to.resolve() == root.resolve() or root.resolve() in to.resolve().parents:
        raise BackupError(BAD_INPUT, "backups go outside this folder (they would back themselves up)")
    files = sources(root, transcripts)
    manifest, buf = {}, io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, name in files:
            try:
                manifest[name] = _sha(path)
                tar.add(path, arcname=name, recursive=False)
            except OSError:  # a file in use or gone mid-run: the next night gets it
                manifest.pop(name, None)
        raw = json.dumps(manifest, indent=0).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
    sealed = _gpg(["--symmetric", "--cipher-algo", "AES256", "--output", "-"], buf.getvalue(),
                  secret or passphrase())
    to.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    out = to / f"juno-{stamp}.tar.gz.gpg"
    out.write_bytes(sealed)
    for old in sorted(to.glob("juno-*.tar.gz.gpg"))[:-max(1, keep)]:
        old.unlink()
    return {"file": str(out), "bytes": len(sealed), "files": len(manifest)}


def restore(file: Path, into: Path, root: Path = ROOT, secret: str | None = None) -> dict:
    into = Path(into)
    if into.resolve() == root.resolve() or root.resolve() in into.resolve().parents:
        raise BackupError(BAD_INPUT, "restore into a scratch folder, never into this one")
    if into.exists() and any(into.iterdir()):
        raise BackupError(BAD_INPUT, f"{into} is not empty")
    plain = _gpg(["--decrypt"], Path(file).read_bytes(), secret or passphrase())
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
        tar.extractall(into, filter="data")
    manifest = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    return {"into": str(into), "files": len(manifest)}


def drill(file: Path, into: Path, root: Path = ROOT, secret: str | None = None) -> dict:
    restore(file, into, root, secret)
    manifest = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    missing = [n for n in manifest if not (into / n).is_file()]
    changed = [n for n, sha in manifest.items() if n not in missing and _sha(into / n) != sha]
    return {"ok": not missing and not changed, "files": len(manifest), "missing": missing[:20],
            "changed": changed[:20], "into": str(into)}


def _target(arg: str | None, root: Path = ROOT) -> Path:
    to = arg or settings(root).get("to")
    if not to:
        raise BackupError(NO_SETUP, "no backup folder yet: set `to:` in me/backup.yaml")
    return Path(os.path.expandvars(os.path.expanduser(str(to))))


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--to")
    s = sub.add_parser("restore"); s.add_argument("--file", required=True); s.add_argument("--into", required=True)
    d = sub.add_parser("drill"); d.add_argument("--into")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return BAD_INPUT
    try:
        if args.cmd == "run":
            out = run(_target(args.to), keep=int(settings().get("keep", 14)))
        elif args.cmd == "restore":
            out = restore(Path(args.file), Path(args.into))
        else:
            newest = sorted(_target(None).glob("juno-*.tar.gz.gpg"))
            if not newest:
                raise BackupError(NO_SETUP, "no backup to drill yet; run one first")
            into = Path(args.into) if args.into else Path(tempfile.mkdtemp(prefix="juno-restore-"))
            out = drill(newest[-1], into)
        print(json.dumps(out))
        return DIFFERS if args.cmd == "drill" and not out["ok"] else OK
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
