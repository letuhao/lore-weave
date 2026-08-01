# BOOK → GAME — the missing tier

**Status:** DESIGN. Nothing here is built. **Date opened:** 2026-08-01.

---

## Why this folder exists, and why it is not inside the game folder

LoreWeave turns raw text into books, glossaries and knowledge graphs. The
[`LLM_MMO_RPG`](../LLM_MMO_RPG/_index.md) track turns a **game concept** into a running game —
contracts, generators, a deterministic engine.

Between them there is a step nobody has built and, until now, nobody had named: **turning a world into
a game concept.** The game tier has been reaching straight back into the novel for its material, and
this session measured what that costs (§ [`01`](01_the_missing_tier.md)).

The PO's framing, which this folder takes as its charter:

> *A game is created from an original story, but **how closely it can follow that story is a question
> that has to be answered** — and the human should be the one to answer it. How can they?*

That question does not belong to book-authoring and it does not belong to the game engine. It is its
own tier, and it is the piece `lore-enrichment-service` alone cannot supply.

```
   LoreWeave                  ▸ THIS TIER ◂                   LLM MMO RPG
   ─────────                  ─────────────                   ───────────
   books · translation        world  →  game concept          contract generator
   glossary · KG                                              generators · engine
   PlanForge (novel spec)     the fidelity decision           the deterministic runtime
```

## The documents

| doc | settles |
|---|---|
| [`01_the_missing_tier.md`](01_the_missing_tier.md) | what is missing, with the measurement that shows it — and why `lore-enrichment-service` cannot close it alone |
| [`02_world_as_corpus.md`](02_world_as_corpus.md) | review of the world feature: what a world already holds, what it would have to hold, and how a heterogeneous world is exploited |
| [`03_fidelity.md`](03_fidelity.md) | **the central question** — how closely may the game follow the source, on which axes, and how a human can actually decide |
| [`04_planforge_reuse.md`](04_planforge_reuse.md) | evidence-based: what of PlanForge is reusable, what is not, and why |
| [`05_poc_plan.md`](05_poc_plan.md) | the smallest thing that could falsify this design |

## Working name

**GameForge** — chosen to signal the relationship the analysis actually found: this is PlanForge's
*machine* pointed at a different artifact, not a new invention. Rename freely; the name is not
load-bearing and appears nowhere in code yet.

## What this tier is NOT

* **Not a summariser.** A game concept is not a condensed novel. Most of its content is not in the
  source at all and has to be authored (`ENR-A4`'s enrichment ladder).
* **Not part of the game.** It produces the input the contract generator consumes. It stops at the
  freeze, exactly as the game tier's own layers stop at each other (`PPB-A6`).
* **Not automatic.** The one decision it exists to support — how far from canon — is the human's, and
  the tier's job is to make that decision *informed*, not to make it.
