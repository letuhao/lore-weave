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

## 7. Baseline — captured 2026-07-10 (gemma, HEAD `63369b2ab`, chat-service rebuilt)

- **Verdict: ❌** — `book_kinds = 0` after BOTH a cold and a warm pass. The user said "go ahead" twice
  and nothing exists. Full findings:
  [`docs/eval/discoverability/2026-07-10-S01-gemma.md`](../../../eval/discoverability/2026-07-10-S01-gemma.md).
- **What I experienced:** it does NOT search-thrash (0 discovery, 0 empty-intent — the `find_tools` loop is
  dead). It proposes a decent-sounding structure in prose. Then it **proposes ENTITIES into a book with no
  categories** — every item returns `unknown kind: character` — and **retries the identical call 4 more
  times**. It never calls the adopt-categories tool at all.
- **Three defects:** (1) wrong tool / wrong order — entities before kinds; (2) **silent success** —
  `glossary_propose_entities` returns envelope `ok:true` while all items errored, so the agent gets no
  failure signal and loops; (3) cold-pass only — the confirm suspends on the approval card and the agent
  then re-emits its proposal verbatim and says *"I cannot set up until you approve"* to a user who just
  approved twice.
- **Jargon:** it volunteers *"we need an **ontology**…"* and presents an *"Ontology Plan"* — a §1 word.
- **Evidence:** discovery 0 · empty-intent 0 · silent-success 1 (cold) / **5** (warm) · unresolved 1 (cold)
  · max consecutive identical call 4 · `book_kinds` 0/0 · ~116s.
- **Two-pass note:** cold = approval card fires (headless driver can't answer it → not a product verdict
  past the first suspend); warm = `user_tool_approvals` pre-seeded (what "always allow" writes). **Both
  failed for the same primary reason**, so the verdict is robust to the permission axis.

### 7c. WS-5 rail landed 2026-07-11 — S01 flips ❌ → ~75% ✅

The `glossary-bootstrap` System workflow + a steering directive make gemma call `workflow_load` and
follow the rail (`list → adopt → confirm → read-back`) instead of the entities-first loop. Result:
`book_kinds` 0 → **10–13** (character, location, **power_system**, …); ~3 of 4 fresh runs persist the
world; jargon-free. Remaining ~25%: gemma stalls before the confirm (model reliability), plus a latent
token-threading product question. Full write-up:
[`docs/eval/discoverability/2026-07-11-ws5-glossary-bootstrap-workflow.md`](../../../eval/discoverability/2026-07-11-ws5-glossary-bootstrap-workflow.md).

### 7b. Partial fix landed 2026-07-11 — silent success (P0) fixed; scenario still ❌ (needs the rail)

One of S01's two enablers is fixed: `glossary_propose_entities` no longer returns `ok:true` when every
item fails — it now returns `isError` with "adopt kinds first" guidance (root cause + live verify:
[`docs/eval/discoverability/2026-07-11-fix-silent-success-propose-entities.md`](../../../eval/discoverability/2026-07-11-fix-silent-success-propose-entities.md);
harness `silent_success_calls` 9→0). **But the scenario still fails:** mid-tier gemma reads the honest
error and *still* retries entities instead of calling `glossary_adopt_standards`, so `book_kinds=0`. A
mid-tier model needs the adopt→propose→confirm sequence **enforced by a rail (WS-5)**, not merely suggested
by an error. The fix is a prerequisite (makes the loop detectable), not the cure.

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
