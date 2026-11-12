---
name: shopping
description: Find the right part or product for Michael, with a verified price and stock, free and warranty options first. Use for "where can I get", "how much is", "order the part", "is there a recall", or any repair that needs a part. Reads only; never buys.
---

# Shopping

Juno never buys anything (T4 spirit). The result is a short answer with links he can tap.

1. **What exactly.** Pin the exact model and part number first: `domains/home/private/appliances.md`, a label photo
   he sent, his order mail (`python tools/gmail.py attachments` / the Gmail connector, narrow to broad), the maker's
   parts diagram. A product that "looks right" is not a match; the part number must match.
2. **Free first.** Before any price, check for a recall, warranty, extended-warranty or free-part program on the
   maker's own site (search `<brand> <model> recall`, `<brand> <part> free replacement`, the purchase date against
   the warranty length). If one fits, that is the answer. If he asks you to file the claim, find what it needs
   (the purchase date from his order mail, never his estimate; the serial off the label) and queue it:
   `python tools/browser_queue.py add --url <claim page> --task "..." --value "Field=value" ...`. The browser agent
   fills it headless and he gets a card with every value; only his tap submits.
3. **Price on the page itself.** Read price and stock on the product page (WebFetch), never from a search snippet
   or an ad. Prefer the maker's own store, then one or two big retailers. Write down for each: store, exact part
   number, price, stock or ship date, shipping cost, return window, and the date you checked.
   A page that won't load (JavaScript-only stores): say the price is unconfirmed and give the link.
4. **Answer.** Lead with the recommendation and why ("the free part program covers it: claim it"), then a small
   table of options (store, price, ships, link). Say what you assumed (model read off a photo is an assumption
   until he confirms it).
5. **Remember.** Save the model, part number and what was found to `domains/home/private/appliances.md`. If he
   orders or claims, add a follow-up: `python tools/followups.py add --what "<part> arrives" --expect-by <date>
   --closes "delivery mail" --match "<store>,<part number>"`.

Never: enter a card number, log in, create an account, or press a buy, checkout or place-order button. A checkout
page ends the run with the link for him.
