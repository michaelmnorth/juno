"""tools/backup.py on synthetic folders: encrypt, restore into scratch, drill, and the refusals."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import backup  # noqa: E402

try:
    backup.find_gpg()
except backup.BackupError:
    pytest.skip("gpg not installed", allow_module_level=True)

SECRET = "correct horse battery staple"


@pytest.fixture
def layer(tmp_path):
    root = tmp_path / "coordinator"
    for rel, text in {"me/profile.md": "who", "people/a.md": "a", "state/x.json": "{}", "data/d.sqlite": "db",
                      "me/.env": "SECRET=1", "tools/code.py": "not backed up"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    talk = tmp_path / "transcripts"
    talk.mkdir()
    (talk / "s1.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    return root, talk, tmp_path / "offsite"


def test_backup_is_encrypted_and_restores_exactly(layer, tmp_path):
    root, talk, to = layer
    made = backup.run(to, root, talk, secret=SECRET)
    blob = Path(made["file"]).read_bytes()
    assert made["files"] == 5 and b"who" not in blob and b"profile.md" not in blob
    out = backup.drill(Path(made["file"]), tmp_path / "scratch", root, secret=SECRET)
    assert out["ok"] and out["files"] == 5
    assert (tmp_path / "scratch" / "transcripts" / "s1.jsonl").exists()
    assert not (tmp_path / "scratch" / "me" / ".env").exists() and not (tmp_path / "scratch" / "tools").exists()


def test_wrong_passphrase_fails(layer, tmp_path):
    root, talk, to = layer
    made = backup.run(to, root, talk, secret=SECRET)
    with pytest.raises(backup.BackupError) as err:
        backup.restore(Path(made["file"]), tmp_path / "scratch", root, secret="wrong")
    assert err.value.code == backup.GPG_FAILED


def test_never_restores_or_backs_up_into_the_coordinator(layer):
    root, talk, _ = layer
    with pytest.raises(backup.BackupError):
        backup.run(root / "backups", root, talk, secret=SECRET)
    with pytest.raises(backup.BackupError):
        backup.restore(Path("x.gpg"), root / "state", root, secret=SECRET)


def test_keeps_only_the_newest(layer):
    from datetime import datetime, timedelta, timezone
    root, talk, to = layer
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for n in range(4):
        backup.run(to, root, talk, keep=2, secret=SECRET, now=start + timedelta(days=n))
    assert [p.name[5:13] for p in sorted(to.glob("juno-*"))] == ["20261103", "20261104"]


def test_no_target_yet_says_so(tmp_path):
    with pytest.raises(backup.BackupError) as err:
        backup._target(None, tmp_path)
    assert err.value.code == backup.NO_SETUP
