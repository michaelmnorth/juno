"""The engine's typed tools as a local MCP server, for a Max-plan run (v2/max_lanes.py).

Started by `claude -p` over stdio for exactly one run. It lists only that run's tools (its playbook's), and runs each
call through Engine.executor: the same policy engine, tiers, taint, draft gate, repeat guard and approval cards as on
the old API path. Nothing else is reachable from here: no shell, no files, no web.

Run state comes from the store (keyed by JUNO_RUN_ID) and goes back after every call, so the engine sees what
happened once the CLI returns. Protocol: newline-delimited JSON-RPC 2.0 (MCP stdio transport).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("JUNO_ROOT") or Path(__file__).resolve().parents[1])
for p in (ROOT, ROOT / "gateway", ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from v2 import tools  # noqa: E402
from v2.policy import run_from_dict, run_to_dict  # noqa: E402

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self, engine, run_id: str, client=None):
        self.engine, self.run_id = engine, run_id
        state = engine.store.load_run(run_id)
        if not state:
            raise RuntimeError(f"no run state for {run_id}")
        self.wants_draft = bool(state.get("wants_draft", True))
        self.run = run_from_dict(state)
        self.specs = [tools.TOOLS[n] for n in self.run.tools if n in tools.TOOLS]
        if client is None:
            from v2.max_lanes import MaxClient
            client = MaxClient(engine.root)
        self.execute = engine.executor(client, self.run, self.specs, self.wants_draft)

    def _save(self) -> None:
        self.engine.store.save_run(self.run_id, {**run_to_dict(self.run), "wants_draft": self.wants_draft})

    def handle(self, msg: dict) -> dict | None:
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # a notification (initialized, cancelled): no answer
            return None
        if method == "initialize":
            asked = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
            result = {"protocolVersion": asked, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "juno", "version": "1"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [{"name": s.name, "description": s.description,
                                 "inputSchema": tools.api_schema(s.input_schema)} for s in self.specs]}
        elif method == "tools/call":
            params = msg.get("params") or {}
            name, args = str(params.get("name") or ""), params.get("arguments") or {}
            bad = tools.validate(tools.TOOLS[name], args) if name in tools.TOOLS else None
            if bad:
                text, is_error = json.dumps({"error": bad}), True
            else:
                text, is_error = self.execute(name, args)
            self._save()
            result = {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(server: Server, stdin=None, stdout=None) -> None:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            out = server.handle(msg)
        except Exception as exc:  # one bad call never kills the run
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": type(exc).__name__}}
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            stdout.flush()


def main() -> int:
    from v2.backend import RealBackend
    from v2.converse import Engine
    engine = Engine(ROOT, RealBackend(ROOT))
    serve(Server(engine, os.environ["JUNO_RUN_ID"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
