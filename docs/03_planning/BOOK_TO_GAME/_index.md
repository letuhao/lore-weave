# BOOK → GAME — the missing tier

**Status:** DESIGN. Nothing here is built — but the prerequisite is now being satisfied and
measured ([`09`](09_first_extraction.md)). **Date opened:** 2026-08-01.

---

## Why this folder exists, and why it is not inside the game folder

LoreWeave turns raw text into books, glossaries and knowledge graphs. The
[`LLM_MMO_RPG`](../LLM_MMO_RPG/_index.md) track turns a **game concept** into a running game —
contracts, generators, a deterministic engine.

Between them there is a step nobody has built and, until now, nobody had named: **turning a world into
a game concept.** The game tier has been reaching straight back into the novel for its material, and
this session measured what that costs (§ [`01`](01_the_missing_tier.md)).

The PO's framing, which this folder takes as its charter:

> *What we intend to build is the **authoring** piece — not the logic piece that says "the book doesn't
> have this, so we can't do that." A game concept is not a wiki. It has to **invent** the thing called
> a game concept, in order for there to be gameplay at all.*
>
> *And a game is created from an original story, but **how closely it can follow that story is a
> question that has to be answered** — the human should answer it. How can they?*

Neither question belongs to book-authoring, and neither belongs to the game engine. They are their own
tier, and it is the piece `lore-enrichment-service` alone cannot supply.

```
   LoreWeave                  ▸ THIS TIER ◂                   LLM MMO RPG
   ─────────                  ─────────────                   ───────────
   books · translation        world  →  game concept          generators structure it
   glossary · KG              AUTHORED · unstructured          into manifests
   PlanForge (novel spec)     invents what the book lacks      the deterministic runtime
```

The single most important line in this folder: **the game concept is not directly consumable by the
game.** It is unstructured by nature. Turning it into something an engine can run is the *generators'*
job, and that is a different job — see [`03_two_jobs.md`](03_two_jobs.md).

## The documents

| doc | settles |
|---|---|
| [`01_the_missing_tier.md`](01_the_missing_tier.md) | what is missing, with the measurement that shows it — and why `lore-enrichment-service` cannot close it alone |
| [`02_world_as_corpus.md`](02_world_as_corpus.md) | review of the world feature: what a world already holds, what it would have to hold, and how a heterogeneous world is exploited |
| [`03_two_jobs.md`](03_two_jobs.md) | **the load-bearing separation** — authoring invents, structuring is deterministic, and one agent cannot hold both. Read this before the rest. |
| [`04_fidelity.md`](04_fidelity.md) | how far from the source, on which axes, and how a human can actually decide — fidelity as **recorded distance, not permission** |
| [`05_planforge_reuse.md`](05_planforge_reuse.md) | evidence-based: what of PlanForge is reusable, what is not, and why |
| [`06_poc_plan.md`](06_poc_plan.md) | the smallest thing that could falsify this design |
| [`07_lore_bible.md`](07_lore_bible.md) | **the find-and-load answer** — the bible's spine is an exhaustive SWEEP over the glossary the book produced, not a search. The chapter is the wrong unit. |
| [`08_measuring_a_creative_result.md`](08_measuring_a_creative_result.md) | there is no right answer, so what IS proven — traceability, not truth — and the **census, not score**, that measures the rest |
| [`09_first_extraction.md`](09_first_extraction.md) | **the first real input** — a glossary extracted from classical Chinese, what it got right, and the systematic kind error a sweep cannot see |
| [`10_place_or_organization.md`](10_place_or_organization.md) | that error, diagnosed: it is a **missing-entity** error, not a classification one — five levers, ranked by evidence |
| [`11_prior_art.md`](11_prior_art.md) | **the industry solved most of this** — metonymy resolution, ACE's GPE, EDC, G-KMS. What to take, what to build, and the axiom of mine it makes *less* likely |

**`03`, `04`, `07` and `08` are corrections.** The first draft of this folder put authoring and structuring in one
place, treated fidelity as a gate that could forbid a mechanism, and argued the corpus-vs-derived
question from COST when the real reason is that a chapter is the wrong UNIT. All three were wrong, all
three were corrected by the PO — and `08` corrects a fourth: calling the residue *"correctness is not
provable"* was a category error, because an authored world has no truth to be correct about. The
superseded axioms are marked as replaced rather than deleted; the mistakes are more instructive than
the fixes.

## Working name

**GameForge** — chosen to signal the relationship the analysis actually found: this is PlanForge's
*machine* pointed at a different artifact, not a new invention. Rename freely; the name is not
load-bearing and appears nowhere in code yet.

## What this tier is NOT

* **Not a summariser.** A game concept is not a condensed novel. Most of its content is not in the
  source at all and has to be authored (`ENR-A4`'s enrichment ladder).
* **Not a wiki.** A wiki records what is known. This invents what is needed. Cultivation fiction is the
  easy case because it ships with a system; for a family saga or a detective novel there is nothing to
  extract and **everything** has to be authored — and that is the case the tier has to be good at.
* **Not a gate.** It never says *"the book lacks this, so the game cannot have it."* It says *"the book
  lacks this — here is what you would be inventing, and here is where it departs."*
* **Not structured output.** It produces prose and decisions for a human. Manifests are downstream and
  deterministic (`03_two_jobs.md`).
* **Not automatic.** The one decision it exists to support — how far from canon — is the human's, and
  the tier's job is to make that decision *informed*, not to make it.
