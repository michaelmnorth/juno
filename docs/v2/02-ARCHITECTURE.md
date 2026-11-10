# 02 · Architecture

Target design for Juno v2. Written 2026-11-09 from the Juno System Map, without access to the v1 repo. Statements about v1 marked **ASSUMED** come from the map and must be confirmed by the Phase 0 audit. The first audit list arrived on 2026-11-10; what it changed is in `09-AUDIT-CORRECTIONS.md`.

## The shape in one paragraph

A small always-on service, the **control plane**, owns everything that needs no judgment: channels, timers, change detection, policy, approvals, budgets, memory storage and context assembly. Models are called as stateless functions through **lanes** of increasing cost. Every model invocation is a **run** with a fixed **class** that determines what it can see and do. State lives in a per-instance store, so nothing depends on a transcript surviving. The engine (**core**) contains no personal data. A **profile** describes one person-context (personal, work). An **instance** is one profile plus its data on one host.

## Principles

Ranked. When two conflict, the higher one wins.

1. **Code decides, models advise.** A model never executes a side effect. It proposes typed actions; the policy engine executes them or asks the owner.
2. **Capability absent beats capability denied.** The runtime has no shell, no file tools and no generic HTTP tool. If a run should not do something, that tool is not in its registry. Deny lists are a last resort.
3. **Every run has a class.** The class fixes tools, memory namespaces, model, budget, and whether untrusted text may enter. Classes are defined in code and config, never by a prompt.
4. **State lives in the store.** Each turn is assembled fresh from the store inside a token budget. Losing a process loses nothing.
5. **Use the smallest lane.** No model, then one structured call, then a bounded tool loop, then batch, then a sandbox. Escalate on evidence.
6. **Learned things are data.** Facts, lessons and examples carry a source and a trust level, load only where scoped, and can never widen permissions.
7. **Core knows no person.** Anything specific to the owner, a coach, Hevy or a workplace lives in a profile or a pack.

## Components

```
                 ┌──────────────── control plane (no model) ────────────────┐
 channels  ─────►│ gateway ─► event queue ─► dispatcher ──► policy engine ──┼─► tool executors ─► Gmail, Calendar, Hevy …
 timers,         │                              │   ▲            ▲   │      │
 pollers  ──────►│                              ▼   │            │   ▼      │
                 │   thread store ◄──► context assembler     approvals ─────┼─► owner (tap)
                 │   memory store ◄──────────┘   │               ▲          │
                 │   ledger · audit log          │               │          │
                 └───────────────────────────────┼───────────────┼──────────┘
                                                 ▼               │ proposed actions
                          lanes  L1 call · L2 loop · L3 batch · L4 sandbox
                                    (Claude API, stateless per run)
```

| Component | Owns | Never does |
|---|---|---|
| **Gateway** | Channel adapters, owner identity check, dedupe, fast ack | Calls a model |
| **Event queue** | Durable, ordered, idempotent events (SQLite) | Drops an event on restart |
| **Scheduler and pollers** | Timers; Gmail history polling, Calendar sync tokens, Hevy checks | Wakes a model when nothing changed |
| **Dispatcher** | Maps event → handler → lane and run class | Lets a run pick its own class |
| **Context assembler** | Builds each request from the store inside budgets; cache layout | Puts volatile text in the cached prefix |
| **Policy engine** | Tool registry per class, tiers, taint, quiet hours, ping caps, budgets, kill switch | Trusts a model's description of an action |
| **Approvals** | Stores exact payloads, renders cards, executes on tap | Lets a model see or handle a pass |
| **Memory store** | Facts, episodes, threads, lessons, signals (SQLite + curated markdown) | Stores secrets or raw third-party mail bodies |
| **Ledger and audit log** | Tokens and cost per block per run; every tool call and action | Logs secrets or full mail bodies |

## Event → run → action

1. Something happens: an inbound message, a timer, a poller delta, an approval tap. The gateway or scheduler writes an **event** with a dedupe key.
2. The dispatcher picks a handler. Many handlers finish in **L0** with no model (status, snooze, approvals, workout sync, rule-settled mail).
3. If judgment is needed the handler creates a **run**: class, lane, model and budget are fixed now and recorded.
4. The assembler builds the request. The lane executes it. Tool calls go through the policy engine one at a time.
5. Side effects are **actions**. T0–T2 execute. T3 becomes a stored **proposal** and an approval card. Nothing executes from model text.
6. The run's result, token ledger, signals and any new episodes are written to the store. The thread's working set and summary are updated by code.

Events are processed at-least-once with idempotency keys on every tool that writes, so a crash mid-run cannot double-send.

## Lanes

| Lane | What | Use for | Typical model |
|---|---|---|---|
| **L0 code** | Deterministic handler | Commands, approvals, syncs, rule-settled triage, nudges with fixed text | none |
| **L1 call** | One request, structured output | Routing, triage of one item, extraction, composing a brief or draft from gathered inputs | Haiku 5.5; Sonnet 5.5 for prose in the owner's voice |
| **L2 loop** | Bounded tool loop over typed tools | Conversational turns that need lookups or actions | Sonnet 5.5 at low effort (Haiku 5.5 where evals allow) |
| **L3 batch** | Message Batches, half price, no latency promise | Nightly consolidation, evals, weekly review | Sonnet 5.5 or Opus 5.5 |
| **L4 sandbox** | Isolated long task with no secrets and no private memory | Multi-source research, document building, code | Pluggable. Not built until a real need appears (see `01-DECISIONS.md` D13) |

Proactive flows (brief, check-in, sweeps) are L0 gathering followed by one L1 call. They do not need a loop.

## Run classes

This is the Rule of Two in code: a run may combine at most two of *reads untrusted text*, *sees private memory*, *can change the outside world*.

| Class | Private memory | Untrusted text | Outside effects | Tools | Examples |
|---|---|---|---|---|---|
| `converse` | yes | typed fields only until tainted (below) | proposes; T3 needs a tap | pack read tools, propose-action tools, `memory.*` | Owner DMs |
| `reader` | no | yes | none | none; structured output only | Triage one email, digest a page or transcript |
| `compose` | scoped (voice, recipient facts) | yes, as quoted data | none; output is a draft | none | Reply drafts |
| `research` | no; receives only the question | yes (web) | none | server-side web search and fetch with caps and domain filters | Event scans, lookups |
| `reflect` | yes | no raw untrusted text; logs and signals only | none; writes candidates | none (batch) | Consolidation, weekly review |

### Taint

- A tool marked `returns_untrusted` returns text an outsider could have written: mail bodies, web content, event descriptions from others, shared docs, transcripts. **Free text taints; typed fields do not.** A reader result's `label`, `due_date`, `amount`, `sender_id` are typed. Its `gist` is free text.
- When untrusted free text enters a `converse` run, the policy engine sets `run.tainted = true`. It stays set for the rest of the run and for the thread until the thread closes.
- A tainted run loses: web tools; auto-execution of reversible actions (they fall back to a tap); promotion of memory writes (they are stored as tainted candidates); live links in outgoing messages. It keeps: reading, answering, proposing actions with the full payload shown.
- Taint is enforced when a tool call is evaluated, not by changing the tool list, so the prompt cache prefix is unaffected.
- Approval cards created by a tainted run carry a visible marker.

## Tool contract

Tools are typed functions registered by packs. The model sees name, description and schema. The policy engine sees the rest.

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str                      # "calendar.create_hold"
    description: str               # written for the model; one or two sentences
    input_schema: dict             # JSON Schema, additionalProperties: false, strict
    tier: Tier                     # T0 read · T1 private write · T2 notify owner
                                   # T3a reversible, owner-only · T3b visible to others · T4 never
    data_classes: frozenset[str]   # {"mail"}, {"finance"}, {"health"} …
    returns_untrusted: bool
    idempotency: Literal["safe", "keyed", "none"]
    max_result_tokens: int         # results are compact and paginated
    handler: Callable[..., ToolResult]
```

Rules:

- Tiers gate **model-proposed** actions. Deterministic automations (workout → coach sheet) are declared in the profile and reviewed like code.
- T3a executes without a tap only in an untainted run. T3b always needs a tap unless the owner has enabled an earned-autonomy class for that exact action shape (`06-LEARNING-LOOP.md`).
- T4 tools do not exist. There is nothing to deny.
- Secrets are fetched inside the handler at call time. They never appear in a prompt, a result or a log.
- Results return what the next decision needs, not what the API returned. Lists are capped and paginated. IDs are stable handles the model can pass back.

## Interfaces

Signatures only. Names are suggestions; keep v1 names where v1 already has the concept.

```python
class ChannelAdapter(Protocol):
    name: str
    caps: ChannelCaps                      # buttons, threads, edits, files, voice_in
    async def start(self, on_event) -> None: ...
    async def send(self, msg: OutboundMessage) -> SentRef: ...
    async def update(self, ref: SentRef, msg: OutboundMessage) -> None: ...
    def render_approval(self, proposal: Proposal) -> OutboundMessage: ...   # falls back to numbered text replies

class Assembler(Protocol):
    def build(self, run: RunSpec) -> AssembledRequest: ...   # blocks, budgets, cache marks, token counts per block

class Lane(Protocol):
    def execute(self, req: AssembledRequest, budget: Budget) -> RunResult: ...

class PolicyEngine(Protocol):
    def tools_for(self, run_class: RunClass) -> list[ToolSpec]: ...
    def decide(self, run: RunState, call: ToolCall) -> Decision: ...        # allow | ask | deny(reason)
    def on_result(self, run: RunState, call: ToolCall, result: ToolResult) -> None: ...   # taint, ledger, audit

class MemoryStore(Protocol):
    def retrieve(self, slots: list[SlotRequest], budget_tokens: int) -> list[MemoryItem]: ...
    def note(self, item: NewItem, source: Source) -> ItemRef: ...            # trust and status derived from source
    def forget(self, selector: Selector) -> ForgetReport: ...
```

## Where things live

Code and data are separated on disk. The code repo can be shared. The instance directory never leaves the host except as an encrypted backup.

```
juno/                              # code repo — zero personal data, CI-checked
  core/
    gateway/  scheduler/  dispatch/  policy/  context/  lanes/
    memory/   learning/   obs/       tools/           # tools/ = the tool SDK and registry
  packs/                           # capability packs: tools + playbooks + evals + automations
    mail/ calendar/ people/ reminders/ research/ media/ health_hevy/ finance/ …
  evals/                           # runner, graders, shared fixtures (synthetic only)
  ops/                             # container, compose, backup, healthcheck, onboarding CLI
  docs/

$JUNO_HOME/<instance>/             # instance directory — all personal data, zero code
  profile.yaml  persona.md  core-card.md  rules.yaml
  memory.db                        # SQLite: events, threads, facts, episodes, lessons, signals, ledger
  golden/                          # eval cases built from the owner's real traffic
  logs/  backups/
```

**Playbooks** are the unit of procedural knowledge. Each is a folder with a `SKILL.md` (name, description, body) in the Agent Skills format, so the same folder loads in the Juno runtime, in Claude Code and in the Claude apps. The Juno assembler loads a playbook body only when the router selects it.

## v1 → v2 map

| v1 (ASSUMED) | v2 | Note |
|---|---|---|
| `gateway/slack_bridge.py`, timers, wake gate, ping rules, approval cards | Gateway, scheduler, policy engine, approvals | Keep. This is the best part of v1. Refactor behind the interfaces above |
| `claude -p` per job with CLAUDE.md, model pin, caps. Timer jobs start cold; DMs resume one session per Slack channel for up to 12 quiet hours (audit, 2026-11-10) | Dispatcher + assembler + lanes on the Messages API; thread store in place of the resumed session | Replace. Main safety and context change. v2 must match v1's follow-ups on the dialogue set first |
| Juno coordinator on Opus | Router (L1, Haiku) + `converse` run (L2) | Replace |
| 11 subagents | 5 run classes; domain behaviour moves to pack playbooks | Sorter → `reader` + rules. Quill → `compose`. Scout, Reel, Rewind → `research`/`reader` playbooks. Mirror → `reflect`. Tempo, Kin, Rep → pack tools + playbooks in `converse`. Ledger → finance pack (later). Ping → gone |
| 9 skills | Playbooks | Port as `SKILL.md` folders |
| 18 Python tools | Pack tools behind `ToolSpec` | Keep the code; wrap, type and tier it |
| 3 hooks, 76 deny rules | Policy engine; no general-purpose tools to deny | Hooks' checks become policy tests |
| `me/ learnings/ people/ domains/ observed/ state/ data/` | Instance directory + `memory.db` | Import, do not hand-migrate (`04-MEMORY.md`) |
| Cost log | Ledger with per-block token counts | Extend |

## Non-goals

Voice calls. More than one human per instance. Moving money. Unattended purchases. A general shell or file system for the assistant. An agent that edits its own prompts, tools or permissions at runtime.
