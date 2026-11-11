"""The v2 store: one SQLite file in the instance's state folder (state/v2.db, git-ignored).

- events: durable, idempotent inbound events (a DM keyed by its Slack timestamp). Never dropped on restart.
- threads: one per DM channel. Engine flag (v2 by default; "use v1" pins a chat to v1), rolling summary, working set, taint, last activity.
- turns: the thread's turns, kept so the summary and the last few turns can be rebuilt without a transcript.
- ledger: one row per model call, with token counts per assembled block (03-CONTEXT-AND-COST.md, Ledger).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

SCHEMA = """
create table if not exists events (
  id integer primary key, dedupe_key text unique not null, kind text not null, channel text,
  payload text not null, status text not null default 'new', created text not null, updated text);
create table if not exists threads (
  channel text primary key, engine text not null default 'v1', summary text not null default '',
  working_set text not null default '[]', tainted integer not null default 0, updated text);
create table if not exists turns (
  id integer primary key, channel text not null, role text not null, text text not null, run_id text, at text not null);
create table if not exists ledger (
  id integer primary key, run_id text, call_idx integer, ts text, lane text, run_class text, intent text,
  model text, effort text, tok_tools integer, tok_constitution integer, tok_core integer, tok_playbook integer,
  tok_operator integer, tok_snapshot integer, tok_memory integer, tok_thread integer, tok_message integer,
  tok_tool_results integer, input_tokens integer, cache_write_5m integer, cache_write_1h integer,
  cache_read integer, output_tokens integer, searches integer, cost_usd real, latency_ms integer,
  stop_reason text, tainted integer);
"""

LEDGER_COLS = ("run_id", "call_idx", "ts", "lane", "run_class", "intent", "model", "effort", "tok_tools",
               "tok_constitution", "tok_core", "tok_playbook", "tok_operator", "tok_snapshot", "tok_memory",
               "tok_thread", "tok_message", "tok_tool_results", "input_tokens", "cache_write_5m", "cache_write_1h",
               "cache_read", "output_tokens", "searches", "cost_usd", "latency_ms", "stop_reason", "tainted")
WORKING_SET_MAX = 12


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.executescript(SCHEMA)
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._con.execute(sql, args)
            self._con.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._con.execute(sql, args).fetchall()

    # --- events -------------------------------------------------------------------------------------------------
    def enqueue(self, dedupe_key: str, kind: str, payload: dict, channel: str = "") -> int | None:
        """Add an event once. Returns its id, or None when the same key was already queued (a Slack retry)."""
        try:
            cur = self._exec("insert into events (dedupe_key, kind, channel, payload, created) values (?,?,?,?,?)",
                             (dedupe_key, kind, channel, json.dumps(payload, ensure_ascii=False), now_iso()))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def mark_event(self, event_id: int, status: str) -> None:
        self._exec("update events set status=?, updated=? where id=?", (status, now_iso(), event_id))

    def unfinished(self) -> list[dict]:
        """Events a restart left behind: 'new' ones never started, 'running' ones cut off midway."""
        return [dict(r) for r in self._all("select * from events where status in ('new','running') order by id")]

    # --- threads ------------------------------------------------------------------------------------------------
    def thread(self, channel: str, now: datetime | None = None) -> dict:
        rows = self._all("select * from threads where channel=?", (channel,))
        if not rows:
            self._exec("insert into threads (channel, engine, updated) values (?,?,?)",
                       (channel, config.DEFAULT_ENGINE, now_iso()))
            rows = self._all("select * from threads where channel=?", (channel,))
        t = dict(rows[0])
        t["working_set"] = json.loads(t["working_set"] or "[]")
        t["tainted"] = bool(t["tainted"])
        now = now or datetime.now(timezone.utc)
        if t["tainted"] and t["updated"]:
            quiet = now - datetime.fromisoformat(t["updated"])
            if quiet > timedelta(hours=config.THREAD_IDLE_HOURS):  # the thread closed; taint goes with it
                t["tainted"] = False
                self._exec("update threads set tainted=0 where channel=?", (channel,))
        return t

    def set_engine(self, channel: str, engine: str) -> None:
        self.thread(channel)
        self._exec("update threads set engine=? where channel=?", (engine, channel))

    def engine(self, channel: str) -> str:
        return self.thread(channel)["engine"]

    def save_thread(self, channel: str, *, summary: str, working_set: list[dict], tainted: bool) -> None:
        self._exec("update threads set summary=?, working_set=?, tainted=?, updated=? where channel=?",
                   (summary, json.dumps(working_set[-WORKING_SET_MAX:], ensure_ascii=False), int(tainted),
                    now_iso(), channel))

    def clear_taint(self, channel: str) -> None:
        self._exec("update threads set tainted=0 where channel=?", (channel,))

    def add_turn(self, channel: str, role: str, text: str, run_id: str = "") -> None:
        self._exec("insert into turns (channel, role, text, run_id, at) values (?,?,?,?,?)",
                   (channel, role, text, run_id, now_iso()))

    def turns(self, channel: str, limit: int = 40) -> list[dict]:
        rows = self._all("select role, text, at from turns where channel=? order by id desc limit ?", (channel, limit))
        return [dict(r) for r in reversed(rows)]

    # --- ledger -------------------------------------------------------------------------------------------------
    def ledger(self, row: dict) -> None:
        cols = [c for c in LEDGER_COLS if c in row]
        self._exec(f"insert into ledger ({','.join(cols)}) values ({','.join('?' * len(cols))})",
                   tuple(row[c] for c in cols))

    def ledger_rows(self, run_id: str | None = None) -> list[dict]:
        if run_id:
            return [dict(r) for r in self._all("select * from ledger where run_id=? order by call_idx", (run_id,))]
        return [dict(r) for r in self._all("select * from ledger order by id")]
