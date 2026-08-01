# 02 — The world feature, reviewed as a corpus for adaptation

The PO asked for this review directly: *we built the world feature to join books together — this is the
moment to look at that architecture again, because we are about to add a new book plus several others
(including reference games and their glossaries/KGs), and then ask how to exploit that mixture.*

Everything in §1 is verified against code, not against the design docs that describe it.

---

## 1. What a world already is

| piece | where | what it is |
|---|---|---|
| `worlds` | book-service `migrate.go:382` | `id · owner_user_id · name · description`. That is all. A world is a **container with an owner**, nothing more. |
| membership | `books.world_id` (`migrate.go:392`, `ON DELETE SET NULL`) | a book belongs to at most one world; removing the world orphans rather than deletes |
| the **bible book** | `books.is_bible` (`migrate.go:400`) + a chapter at `sort_order 0` | auto-provisioned, **hidden**, prose-less. It exists so the chapter-keyed lore machinery — glossary, knowledge, composition outline — has something to key on when the lore is about the *world* rather than a book. |
| KG partitions | `knowledge_projects.world_id`, `world_rollup.py` | a world's readable partitions = the world-level (bible) project **plus each owned member book's** project. Deduped, order-stable, world-level first. |
| cross-book query | `kg_world_query` (knowledge-service MCP) | read-only rollup over that partition set |
| maps | `world_map_*` + MinIO | world-scoped, additive (a map is world-spanning by nature) |
| spoiler cutoff | `spoiler_window.resolve_before_order`, `before_chapter_id` | fail-closed: unknown reading position ⇒ nothing passes |

**The governing constraint (G1 additivity).** Lore stays `book_id`/`chapter_id`-keyed and *rolls up*
to a world through its books. There is deliberately **no `world_id` on glossary/knowledge rows.**
World-native authoring resolves `world_id → bible_book_id → bible_chapter_id` and writes book-keyed.

> **`BTG-A3`.** The world container is a **membership set with one privileged member** — the bible
> book, whose only purpose is to give world-level lore a chapter to hang from. That is a smaller
> primitive than "world" suggests, and it is the right size: everything world-level is a *rollup over
> members*, computed, never stored twice. A game concept that stored its own copy of the world's facts
> would be the first thing to break that.

## 2. What the world would have to hold for adaptation

The PO's shape: *a new book, plus several other books including the original game and their
glossaries/KGs.* Concretely a world becomes heterogeneous, and the heterogeneity is the point:

| member | role in adaptation | what it can and cannot answer |
|---|---|---|
| **source book(s)** — the novel | canon. The thing being adapted. | says what happened; almost never says what a *rule* is |
| **lore book(s)** — reference wikis | context, character, cosmology | encyclopaedic: covers everything a word ever meant, including what belongs to other traditions (measured — §[`01`](01_the_missing_tier.md)) |
| **reference game(s)** — an existing game's text | *systems* vocabulary: what a grade is, what a tier costs, how a ladder is normally shaped | says what a game of this kind usually does; says nothing about *this* world |
| **glossary** (authored SSOT) | the human's own naming decisions | already the human's, already scoped per book, already carries entity kinds |
| **KG** (derived) | relations across the corpus — who wields what, what follows what | derived and fuzzy; anchored to glossary by `glossary_entity_id` |
| **the game concept** ← NEW | the output. World-level, so it hangs off the **bible book**. | |

> **`BTG-A4`.** The reference game is the member that makes this tier tractable, and it is the one the
> current setup does not have. A novel constrains *what is true*; a reference game supplies *what a
> rule looks like*. The gap the game tier keeps hitting — the novel states no grades, no realm count,
> no costs — is not closed by reading the novel harder. It is closed by knowing the **shape** an answer
> of that kind takes, which is what a second game's text carries. This is `ENR-A5`'s "genre pack",
> except it need not be authored from nothing: it can be a book in the world.

## 3. How the mixture is exploited

Three retrieval modes over one world, and they must not be collapsed into one similarity search — §[`01`](01_the_missing_tier.md) measured what happens when they are.

```
             ┌── source books ──────► WHAT IS TRUE HERE        cited · spoiler-cut · verbatim-verifiable
 a question ─┼── reference games ───► WHAT SHAPE AN ANSWER TAKES   pattern, never fact
             └── glossary + KG ─────► WHAT WE ALREADY DECIDED      the human's prior answers
```

* **Source retrieval must be citable.** Anchor → `locate()` → sentence, as
  `lore-enrichment-service` already does: a claim that cannot be pointed at cannot be stored.
* **Reference-game retrieval must be un-citable *as fact*.** Whatever it returns is a **pattern**, and
  a pattern imported as a fact is the failure mode `MEM-A6` already caught in the game tier — a model
  handed western rarity tiers (`Common`…`Mythic`) into a Ming-dynasty setting. The provenance for
  anything sourced this way is `PROJECTED`, never `CITED`.
* **Glossary/KG retrieval is the cheapest and is currently unused.** The glossary is the human's own
  authored SSOT and it is *already* in the contract's conceptual vocabulary — which is precisely what
  the failed slot-id queries were not. Any query strategy should hit the glossary first and the raw
  text last.

> **`BTG-A5`.** Retrieval over a heterogeneous world is **not one index**. Each member answers a
> different question and carries a different maximum provenance, and mixing them into one similarity
> ranking is what produced the measured result where a 《狐狸缘全传》 crossover reference out-scored the
> passage that actually described the campaign. The router is per-member-role, and the role decides the
> ceiling on what a retrieved span may be used to claim.

## 4. Where the game concept lives — the open decision

Three candidate homes, and the review changes what they cost:

| option | what it inherits | what it fights |
|---|---|---|
| **glossary-service / wiki** (`wiki_*`, authored SSOT) | the authored-lore home, entity+attribute structure, per-book scoping, kinds, the correction spine | wiki pages are prose; closed-set structure would be new |
| **a book in book-service** | PlanForge, chapters, revisions, the whole authoring stack, the existing bible-book mechanic | a book is linear prose; a game concept is entities with attributes |
| **a new game-tier artifact** | total freedom of schema | inherits nothing — a second authoring stack to build and maintain |

The review's finding: **this is less of a fork than it looks.** The world's *bible book* already exists
to be the chapter-key for world-level lore, and glossary/knowledge already write **book-keyed against
it**. A game concept authored as glossary entities + wiki pages on the bible book is simultaneously
option 1 and option 2 — it hangs off a book, and it is stored as authored lore. G1 additivity is
satisfied without a migration and without a `world_id` on anything new.

**This is a recommendation, not a decision, and it is the first thing §[`05`](05_poc_plan.md) tries to
falsify.** The thing that would break it: a closed set is not a wiki page, and if expressing *"these
are all six equip slots and there are no others"* needs a structure the glossary cannot hold, the
option collapses back to a new artifact.

## 5. What the review says the world feature is missing

1. **No notion of member ROLE.** `books.world_id` says a book is in the world; nothing says whether it
   is canon, reference, or output. §3 needs that distinction and it does not exist — today it would
   have to be inferred from a title.
2. **No world-level freeze.** The game tier freezes its pool to a digest so a generator can pin what it
   consumed. A world's contents drift constantly (chapters are added, glossary edited) and nothing
   content-addresses "the world as it was when this concept was authored".
3. **`is_bible` is a hiding flag, not a role.** It marks the container hidden from counts. It does not
   say what the bible book is *for*, and a second world-level book — say the game concept — would need
   either a second flag or a real role column.
