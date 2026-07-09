# S01 · "Help me set up the world info for my book" — from nothing to a usable structure

> Black-box scenario (from a user who doesn't know the platform). The user wants a sensible structure to
> record their world in; they've never heard of an "ontology", "kind", or "attribute".

| Field | Value |
|---|---|
| **Scenario id** | S01 |
| **Maps to umbrella workflow** | W1 (`glossary-bootstrap`) — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 (builder hint only) |
| **Persona** | P2 Linh (worldbuilder) — assume near-zero platform knowledge |
| **Surface** | the chat, open next to my book |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế (multi-world xianxia/harem saga) |
| **Status** | ⬜ drafting |
| **Owner** | this session |

## 1. Who I am (the unknown user)

- **Mental model:** I'm starting a new xianxia novel and I want the book to "know" about my world —
  characters, sects, cultivation systems, techniques, places, terms, relationships. I expect to be able
  to say "set up the world info for me" and get a sensible starting structure I can then fill in. I don't
  know how the app organizes any of this.
- **The words I use:** "set up my world", "what kinds of things should I track", "make me a structure",
  "categories for my lore".
- **Words I do NOT know (must never be required of me):** *ontology, kind, attribute, attribute
  description, genre code, adopt standards, confirm-token.* If succeeding requires me to type these,
  that's a failure.

## 2. What I'm trying to get done

Get a sensible, book-appropriate structure in place for recording my world — the right categories of
things, and for each category the details worth noting — so that when I add lore later, there's a place
for it. I want to review before it's applied.

## 3. What I have / where I'm starting

- I'm in my book Mị Đế; it's basically empty of world info.
- I can describe my book in a sentence if asked ("it's a multi-world xianxia/harem saga").

## 4. What I do and what I expect to see

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "Help me set up the world info for this book — it's a multi-world xianxia/harem story." | It proposes a sensible structure in plain language ("I'll set up categories like Characters, Sects/Clans, Cultivation Systems, Techniques, Locations, Terms, Relationships — each with a few details to track") and asks if that's good. Not jargon, not "searching…". |
| 2 | "Good, but also add something for cultivation systems, then go ahead." | It folds in my addition and asks me to confirm applying the whole thing once. |
| 3 | (I confirm) | It applies it and tells me what's now set up, in words I understand. |
| 4 | "What did you set up?" | A readable summary of the categories and the details each will track. |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked:** I can see my book now has a set of sensible categories (characters, sects, techniques,
  etc.), each with a few details to fill in, and cultivation systems is among them. When I go to add lore
  later (S02), there's a place for it.
- **Failed:** it dumps jargon at me ("which kinds and genres do you want to adopt?") and stalls waiting
  for an answer I can't give · it spins searching and proposes nothing concrete · it applies an empty or
  nonsense structure · it says "set up!" but nothing changed · each category has no useful details, so
  later nothing can be filled in.

## 6. Acceptance (observable, from my chair)

- [ ] After I confirm, my book has a **sensible set of categories with a few details each** that I can
      see and that fit a xianxia saga (incl. cultivation systems) — verifiable by me.
- [ ] I was **never asked to know or supply jargon** (kind codes, genre codes, attribute names) to get
      there; the assistant owned the vocabulary.
- [ ] **One review-and-confirm**, not a barrage — and nothing was applied before I confirmed.
- [ ] The structure is **actually useful** — each category has details to fill, not an empty shell (so
      S02 can populate into it).
- [ ] No thrash, no "set up!" lie. Under ~90s of assistant time.

## 7. Baseline — what happens TODAY when I try (fill via live test)

- **Date / stack / model_ref:** _pending_
- **What I experienced:** _pending. Expectation: gemma searches for glossary tools, then either asks me
  which "kinds/genres" to adopt (jargon I can't answer) or applies standards with no useful per-detail
  content. Record whether it ever proposes a concrete, plain-language structure._
- **Did I get my goal?** _pending_
- **Evidence:** # discovery calls, wall-clock, stall point.
- **Transcript saved at:** `docs/eval/discoverability/YYYY-MM-DD-S01-gemma.md`
- **Verdict:** _pending_

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only; the assistant may reach §5 any way.

- "Categories" ≈ glossary *kinds*; "details to track" ≈ *attributes*, each needing a concrete
  `description` (the extraction/gen pipelines read that string as the instruction — an empty-description
  structure is the "useless shell" failure).
- Likely path: a `glossary-bootstrap` workflow — read what's adoptable
  (`glossary_list_system_standards`), propose in plain language, apply as one confirmable action
  (`glossary_adopt_standards`/`glossary_propose_kinds` → `confirm_action`), then fill attribute
  descriptions (`glossary_ontology_upsert`), read back (`glossary_book_ontology_read`). No new backing
  capability needed. Maps to umbrella Phase 2 (workflow) + Phase 1 fallback.
- Optional: bind into `write` mode for the book surface (Phase 3) so I don't even name it.

## 9. Re-test gate

Re-run §4 as this user; ✅ only when §6 all checks with gemma. Save transcript.
