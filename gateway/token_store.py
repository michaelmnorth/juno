"""Unattended access to 1Password: the service account key lives in Windows Credential Manager.

At startup the bridge reads that key, asks 1Password for the Slack tokens (and the optional Google ones), and keeps
them in its own process only.
The key is passed to the `op` call alone, never set in the bridge's environment, so Claude runs cannot inherit it.
1Password stays the single place secrets are kept. Nothing here prompts or prints a secret.

Store or replace the key (the prompt hides what you paste):
  .venv\\Scripts\\python gateway\\token_store.py --store-op-token
Check it can reach the Slack tokens, printing only pass or fail:
  .venv\\Scripts\\python gateway\\token_store.py --check
"""
from __future__ import annotations

import argparse
import getpass
import glob
import os
import shutil
import subprocess
import sys

SERVICE = "juno"
OP_KEY = "OP_SERVICE_ACCOUNT_TOKEN"
REFS = {
    "SLACK_BOT_TOKEN": ("op://Agent-Secrets/Slack-Juno/bot_token", "xoxb-"),
    "SLACK_APP_TOKEN": ("op://Agent-Secrets/Slack-Juno/app_token", "xapp-"),
}
# Discord (DV15): one bot token. Discord tokens have no fixed prefix; "" means any non-empty value.
DISCORD_REFS = {"DISCORD_BOT_TOKEN": ("op://Agent-Secrets/Discord-Juno/bot_token", "")}
# Read-only Gmail and Calendar for the sweep wake gate (tools/google_read.py). Optional: if any is missing the bridge
# still starts, and the gate fails open so every sweep runs.
OPTIONAL_REFS = {
    "GOOGLE_CLIENT_ID": "op://Agent-Secrets/Google-Juno/client_id",
    "GOOGLE_CLIENT_SECRET": "op://Agent-Secrets/Google-Juno/client_secret",
    "GOOGLE_REFRESH_TOKEN": "op://Agent-Secrets/Google-Juno/refresh_token",
}


# The external heartbeat's ping URL (healthchecks.io or similar; docs/v2 brief P0). Optional and read on its own:
# without it the bridge runs as before and nothing outside notices if it stops.
HEARTBEAT_REF = ("JUNO_HEARTBEAT_URL", "op://Agent-Secrets/Heartbeat-Juno/url")

# The v2 engine's own Claude API key (decision O1). Optional: without it, chats on v2 get a plain "no key yet" line.
# Kept under a name the Claude Code CLI never reads, so v1's runs stay on the subscription.
API_KEY_REF = ("JUNO_V2_API_KEY", "op://Agent-Secrets/Anthropic-Juno/api_key")


class TokenError(RuntimeError):
    """Holds a description safe to log. It never contains a secret."""


def find_op() -> str:
    found = shutil.which("op") or shutil.which("op.exe")
    if found:
        return found
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\AgileBits.1Password.CLI_*\op.exe")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    raise TokenError("1Password CLI (op) not found")


def op_env(key: str) -> dict[str, str]:
    """Environment for one `op` call: the service account key, and no fallback to a desktop-app prompt."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("OP_")}
    env[OP_KEY] = key
    env["OP_BIOMETRIC_UNLOCK_ENABLED"] = "false"
    return env


def read_ref(op: str, ref: str, key: str, timeout: int = 60) -> str:
    try:
        proc = subprocess.run([op, "read", "--no-newline", ref], env=op_env(key), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise TokenError(f"1Password timed out reading {ref}") from exc
    if proc.returncode != 0:
        raise TokenError(f"1Password could not read {ref} (exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def fetch_tokens(refs: dict | None = None) -> dict[str, str]:
    import keyring
    key = keyring.get_password(SERVICE, OP_KEY)
    if not key:
        raise TokenError("No 1Password service account key stored. Run gateway/token_store.py --store-op-token.")
    op = find_op()
    tokens = {}
    for name, (ref, prefix) in (refs or REFS).items():
        value = read_ref(op, ref, key)
        if not value or not value.startswith(prefix):
            raise TokenError(f"{ref} does not look like a bot token" + (f" (expected {prefix}...)" if prefix else ""))
        tokens[name] = value
    return tokens


def fetch_optional() -> dict[str, str]:
    """The optional secrets that 1Password has. Any one it can't read is left out, never an error."""
    import keyring
    key = keyring.get_password(SERVICE, OP_KEY)
    if not key:
        return {}
    op = find_op()
    found = {}
    for name, ref in OPTIONAL_REFS.items():
        try:
            value = read_ref(op, ref, key)
        except TokenError:
            continue
        if value:
            found[name] = value
    # All three or none: a partial Google set would only make the wake gate fail later.
    return found if len(found) == len(OPTIONAL_REFS) else {}


def load_into_env(channel: str = "slack") -> None:
    """Put the chat app's tokens (Slack's two, or Discord's one), and the optional ones 1Password has, in this
    process unless already set. Claude runs drop them (claude_runner.child_env)."""
    refs = DISCORD_REFS if channel == "discord" else REFS
    if not all(os.environ.get(name) for name in refs):
        os.environ.update(fetch_tokens(refs))
    if not all(os.environ.get(name) for name in OPTIONAL_REFS):
        os.environ.update(fetch_optional())
    load_late_secrets()


LATE_REFS = ((HEARTBEAT_REF, "https://"), (API_KEY_REF, "sk-ant-"))


def load_late_secrets() -> list[str]:
    """Load the heartbeat URL and the v2 API key if they are missing and 1Password has them now (they are often
    added after the bridge started). Returns the names newly loaded, never the values."""
    loaded = []
    for (name, ref), prefix in LATE_REFS:
        if os.environ.get(name):
            continue
        try:
            import keyring
            key = keyring.get_password(SERVICE, OP_KEY)
            value = read_ref(find_op(), ref, key) if key else ""
        except (TokenError, OSError, ImportError):
            value = ""
        if value.startswith(prefix):
            os.environ[name] = value
            loaded.append(name)
    return loaded


def store_op_token() -> int:
    import keyring
    value = getpass.getpass("Paste the service account token (hidden), then press Enter: ").strip()
    if not value.startswith("ops_"):
        print("That does not look like a service account token (expected ops_...). Nothing stored.", file=sys.stderr)
        return 2
    keyring.set_password(SERVICE, OP_KEY, value)
    print("Stored in Windows Credential Manager.")
    return 0


def check() -> int:
    try:
        tokens = fetch_tokens()
    except TokenError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"OK: read {len(tokens)} Slack tokens from 1Password with no prompt.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store-op-token", action="store_true", help="save the service account key")
    parser.add_argument("--check", action="store_true", help="test reading the Slack tokens")
    args = parser.parse_args()
    if args.store_op_token:
        raise SystemExit(store_op_token())
    if args.check:
        raise SystemExit(check())
    parser.print_help()
