# home context

Template. Copy to the same name without `.example` (onboarding does this). The home domain is the house and what is
in it: appliances, models and serials, where and when each was bought, warranties, service history, recurring
upkeep. It exists so "the washer" or "the fridge" resolves to one known thing next time (P2 brief, #2).

One dated line per fact: `- YYYY-MM-DD: fact. (Michael)` for confirmed, `(assumed)` for guesses that expire after
30 days, `(source: mail YYYY-MM-DD)` when it came from his own order mail.

## Where facts go
- This file: the home itself and how Michael wants it handled (preferred brands, who to call, budget habits).
- `domains/home/private/appliances.md` (git-ignored): one section per appliance with brand, model, serial,
  bought (date, store, order number), warranty end, faults and claims. Serial and order numbers stay there only.

## Rules for Juno
- Before researching an appliance problem, read `private/appliances.md`: the model and serial may already be known.
- Write a new fact (a model read off a label photo, a purchase date from an order email) before the reply, so it
  survives the session. A model or serial read from a photo is `(assumed)` until he confirms it.
- A pending outcome (a part shipping, a claim decision, a refund) becomes a follow-up:
  `python tools/followups.py add --what ... --expect-by ... --closes ... --match ...`.
- Free, recall and warranty programs come before buying anything (the `shopping` skill).
