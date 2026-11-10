"""P0 token ledger for v1, from Claude Code session files. Reads usage numbers only; prints no message text."""
import glob, json, os, statistics as st, sys
from collections import defaultdict
from datetime import datetime

PROJ = os.path.expanduser("~/.claude/projects/C--Users-Michael-Claude-Personal-personal-coordinator")
DM_TAG = "[Slack DM from Michael]"
JOBS = {"morning-brief skill": "morning-brief", "sweep skill": "sweep", "evening-checkin skill": "evening-checkin",
        "weekly-reflection skill": "weekly-reflection", "Session handoff:": "handoff", "[Approved": "approval",
        "[Tapped": "tap"}


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def tok(u):
    return {"in": u.get("input_tokens", 0), "cw": u.get("cache_creation_input_tokens", 0),
            "cr": u.get("cache_read_input_tokens", 0), "out": u.get("output_tokens", 0)}


def load(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


turns = []  # one per owner DM or job prompt
for f in glob.glob(os.path.join(PROJ, "*.jsonl")):
    recs = load(f)
    if not any(r.get("entrypoint") == "sdk-cli" for r in recs):
        continue
    sid = os.path.basename(f)[:-6]
    sub = []
    for sf in glob.glob(os.path.join(PROJ, sid, "subagents", "*.jsonl")):
        sub += [r for r in load(sf) if r.get("type") == "assistant"]
    cur, seen = None, set()
    for r in recs:
        if r.get("type") == "user" and not r.get("isSidechain"):
            t = text_of(r.get("message", {}))
            kind = "dm" if DM_TAG in t else next((v for k, v in JOBS.items() if k in t), None)
            if kind:
                cur = {"kind": kind, "session": sid, "start": r.get("timestamp"), "calls": [], "sub": []}
                turns.append(cur)
        elif r.get("type") == "assistant" and cur is not None:
            m = r.get("message", {})
            mid = m.get("id") or r.get("requestId")
            if mid in seen or not m.get("usage"):
                continue
            seen.add(mid)
            cur["calls"].append({"model": m.get("model"), **tok(m["usage"]), "side": bool(r.get("isSidechain"))})
    # subagent calls: attach to the turn whose window holds them
    for r in sub:
        m = r.get("message", {})
        if not m.get("usage"):
            continue
        ts = r.get("timestamp", "")
        owner = [t for t in turns if t["session"] == sid and t["start"] <= ts]
        if owner:
            owner[-1]["sub"].append({"model": m.get("model"), **tok(m["usage"])})


def total(c):
    return c["in"] + c["cw"] + c["cr"]


def summary(kind):
    ts = [t for t in turns if t["kind"] == kind and t["calls"]]
    if not ts:
        return None
    first = [total(t["calls"][0]) for t in ts]
    calls = [len(t["calls"]) for t in ts]
    subs = [len(t["sub"]) for t in ts]
    agg = defaultdict(int)
    for t in ts:
        for c in t["calls"] + t["sub"]:
            for k in ("in", "cw", "cr", "out"):
                agg[k] += c[k]
    main_in = sum(total(c) for t in ts for c in t["calls"])
    sub_in = sum(total(c) for t in ts for c in t["sub"])
    models = defaultdict(int)
    for t in ts:
        for c in t["calls"] + t["sub"]:
            models[c["model"]] += 1
    return {"turns": len(ts), "first_call_input_p50": st.median(first), "first_call_input_max": max(first),
            "first_call_input_min": min(first), "main_calls_p50": st.median(calls), "subagent_calls_p50": st.median(subs),
            "turns_with_subagents": sum(1 for s in subs if s), "input_main": main_in, "input_subagents": sub_in,
            "cache_write": agg["cw"], "cache_read": agg["cr"], "uncached_in": agg["in"], "output": agg["out"],
            "calls_by_model": dict(models)}


# fresh sessions: the first call's input is everything loaded before the owner's words, plus those words
fresh = []
for f in glob.glob(os.path.join(PROJ, "*.jsonl")):
    recs = load(f)
    if not any(r.get("entrypoint") == "sdk-cli" for r in recs):
        continue
    a = next((r for r in recs if r.get("type") == "assistant" and r.get("message", {}).get("usage")
              and not r.get("isSidechain")), None)
    u = next((r for r in recs if r.get("type") == "user" and not r.get("isSidechain")), None)
    if a and u:
        t = text_of(u.get("message", {}))
        kind = "dm" if DM_TAG in t else next((v for k, v in JOBS.items() if k in t), "other")
        fresh.append({"kind": kind, "model": a["message"].get("model"), "first_input": total(tok(a["message"]["usage"])),
                      "prompt_chars": len(t)})

out = {"kinds": {k: summary(k) for k in sorted({t["kind"] for t in turns})},
       "fresh_session_first_call": fresh,
       "window": [min(t["start"] for t in turns), max(t["start"] for t in turns)] if turns else None}
json.dump(out, sys.stdout, indent=1, default=str)
