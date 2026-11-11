"""Juno v2: the context engine (docs/v2/02-ARCHITECTURE.md, 03-CONTEXT-AND-COST.md, briefs/P1-context-engine.md).

Owner DMs run through code that assembles a small exact context, then one structured call (L1) or a bounded loop
over typed tools (L2) on the Messages API. The model proposes; code executes or asks for a tap.
"""
