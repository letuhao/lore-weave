# Book-layer architecture — reliable lifecycle, story-time versioning, and a read/write pipeline

**Reconciles:** **Reading/writing entity or KG knowledge** · **Two-layer glossary↔knowledge** · **Module/service boundaries** — the pipeline proposal sits INSIDE those rows: it routes lore through the two-layer split rather than proposing a third layer.

**Status:** 🔒 **SEALED 2026-08-09** — the *reasoning* is closed and must not be re-litigated from memory; re-read it. **All 30 opened questions are closed.** No code has changed. Decision register: [ARCHITECTURE-OVERVIEW §9](2026-08-09-ARCHITECTURE-OVERVIEW.md#9--sealed--decision-register). **Opened:** 2026-08-09
**Branch:** `refactor/entity-lifecycle` · **Verified against:** `df18e9049`
**Scope:** the **book layer only** (book + lore bible). Manifest / reality / engine are out of scope by
the PO's boundary rule (§2) — and the lore bible is not designed yet, so this targets **book**.

> **Revision note.** A first draft of this file proposed an architecture spanning book → bible →
> manifest → reality. That was over-scoped and crossed a boundary the PO has since made explicit
> (§2). This version replaces it. The manifest and reality legs are recorded in §2 only as the
> boundary they are, not as work.

---

## 1 · The two failure cases this must fix

Stated by the PO, and both reproduce from the contracts rather than from bad luck:

> **AC1 — liveness.** *"When I make a new chapter, the agent cannot know whether a character is dead,
> because we don't have a reliable lifecycle."*
>
> **AC2 — story-time version.** *"When the story advances, the agent gets confused about the
> protagonist — what was his situation in the previous chapter? The agent reads the glossary from
> chapter 1 to now, and confuses age / appearance / relationships, because those change every chapter."*

Both are **structurally guaranteed today**, verified at `df18e9049`:

| evidence | |
|---|---|
| `composition-service` occurrences of `as_of` | **0** — the authoring agent never asks for a story position |
| KAL `roster` (the planner's cast source) parameters | `book_id`, `fields`, `cursor`, `limit` — **no time dimension**, and `fields` is projection-restricted to `id,name` |
| KAL `as_of` on the KG branch | returns **`temporal_unsupported`** until foundation F3 |
| `glossary_entities.alive` | **7290 true · 0 false** — never once set |
| `:EntityStatus` (the correct liveness model) | **21 rows · 0 reachable** by the guard's FK |
| `canon_at_chapter_handler.go:124` — the *"canon at chapter"* read | bounds chapter links by chapter, then filters `e.alive = true` and joins the **current** name and kind |

So the agent asks for "the cast" and receives *the union of every entity that ever existed, by current
name, with no liveness and no story position*. AC1 and AC2 are that sentence.

---

## 2 · The layer boundary (PO-stated — this proposal obeys it, it does not design it)

```
┌────────────────────────────────────────────────────────────────┐
│ BOOK LAYER          book  ·  lore bible (another kind of book) │
│                                                                │
│   the ONLY writers of lore, and they write THROUGH the KAL     │
│                          │                                     │
│                    ┌─────▼─────┐                               │
│                    │    KAL    │   read path  ✅ 18 routes     │
│                    │           │   write path ❌  ← THE GAP    │
│                    └─────┬─────┘                               │
│                 glossary  ·  KG  ·  wiki                       │
└──────────────────────────┼─────────────────────────────────────┘
                           │  the lore bible BUILDS the manifest,
                           │  reading knowledge ONLY through the KAL
                           ▼
                    ┌─────────────┐
                    │  MANIFEST   │  structured · compact · NO natural language
                    └──────┬──────┘
   ══════════════ HARD BOUNDARY — nothing below reads back up ══════════════
                           ▼
        reality database  →  game engine  →  world simulation (RAM)
```

**The rule and its reason, as stated by the PO:** the reality database must **not** reach the KAL —
latency, and more fundamentally *the knowledge layer is not fit for the game*: it is natural language
and large context, and nothing in the game engine or the in-game LLM agent is designed to read that.

**The consequence this proposal accepts:** the manifest is a **compiler output**, not a cache. Anything
the game needs must be *compiled into* it in game-readable form. That means the book layer's job is to
be able to produce a **complete, coherent, single-valued state** — which is the same capability AC1 and
AC2 demand. **Fixing the book layer is therefore a prerequisite for the manifest, not a detour from it.**

Out of scope here: the manifest schema, the bible design, `canon.entry.*` emission (`Q-L5A-1`), and
anything below the boundary.

---

## 3 · The finding that changes the cost

> **The book layer already stores story-time truth, and never reads it.**

Verified:

| mechanism | state |
|---|---|
| `entity_facts` — append-only **bi-temporal SSOT**: story time (`valid_from_ordinal` / `valid_to_ordinal`, `valid_to_eff` generated) **and** belief time (`created_at` / `invalidated_at` / `coverage_xid`) | ✅ built |
| `episodes` — anchors `chapter_ordinal` + `content_hash` + provenance | ✅ built |
| `emitChapterFacts` — writes **every extracted attribute** at the chapter's ordinal, with `source_episode_id` and an evidence quote | ✅ built |
| `maintain_chain` — supersession: a later fact closes the earlier one's interval; **pin-aware**, so an authored close is not overwritten | ✅ built |
| as-of read predicate — `valid_from_ordinal <= N AND (valid_to_ordinal IS NULL OR N < valid_to_ordinal)`, half-open, index-served | ✅ built and correct |
| `canonical_snapshot` + `folds_since_reground` — **anchor + delta**, the architecture [AeonG (VLDB'24)](https://www.vldb.org/pvldb/vol17/p1515-lu.pdf) recommends | ✅ built |
| **any authoring read that passes `as_of`** | ❌ **zero** |

The protagonist's age at chapter 25 **is already stored, timed, evidenced and superseded correctly.**
Nothing asks for it.

This is the repo's own **stored-but-never-read** class (`docs/standards/settings-and-config.md`), which
`ONT-F4` diagnoses across the social layer — here applied to the entire temporal substrate. It means
this refactor is mostly **routing reads through machinery that exists**, not building versioning.

---

## 4 · Proposed design

### D0 · ⛔ **The axis is wrong, not just the column** — *(PO, 2026-08-09)*

> **The PO's objection, which is correct and deeper than a vocabulary question:**
> *"A dead character can be mentioned everywhere — we cannot remove it because it is dead. For some
> novels the protagonist is already dead, and the story is third-person people telling his story after
> his death."*

**Two errors, and the second is structural.**

**(a) Liveness was being modelled as a load filter. It is not one.** Death is not absence. A dead
character is *more* referenced, not less — eulogised, avenged, quoted, misremembered. `alive` measured
**7290 true / 0 false** and `:EntityStatus` measured **0-of-21 reachable** not only because they were
unwired, but because **neither was actionable**: nothing sensible follows from *"this character is
dead"* on its own. **What loads into a plan is decided by salience and scene need — never by liveness.**

**(b) Liveness cannot be expressed on the axis the fact store has.** `entity_facts` carries exactly
one axis, `valid_from_ordinal` / `valid_to_ordinal`, sourced from `episodes.chapter_ordinal` — that is
**reading position**. Liveness is an **in-world** property. The KG already solved this for events and
nobody carried it across:

| | reading axis | in-world axis |
|---|---|---|
| `:Event` (KG) | `event_order` ✅ | `chronological_order` ✅ |
| `entity_facts` (SSOT) | `valid_from_ordinal` ✅ | ❌ **absent** |

In-world time exists only as *attribute data* — `date_in_story` (614 facts), `era` (201) — never as a
queryable axis.

**So the posthumous-narration novel is not merely unmodelled; it is unrepresentable.** Every fact about
the dead protagonist is asserted at reading positions 1..N while being true in-world long before
chapter 1. A flashback at chapter 50 depicting in-world year −20 gets `valid_from_ordinal = 50`, which
is *correct on the reveal axis and wrong on every question anyone wants to ask*. And *"is he alive at
position P?"* has no axis to be asked on.

**Naming the defect precisely:** `valid_from_ordinal` is used as **reveal time** but named as **valid
time**, and true valid time — world time — does not exist. For linear novels reveal-order ≈
world-order, so it works by luck. It breaks on flashback, prequel, non-linear structure, unreliable
narration and posthumous framing — all common in the web-novel corpus this platform serves.

**Proposed correction.** Three axes, explicitly named:

| axis | question it answers | today |
|---|---|---|
| **world time** | when is this true *in the story world*? | ❌ missing — **add it** |
| **reveal time** | when does the reader/agent learn it? | ✅ exists (mis-named `valid_*`) |
| **belief time** | when did the system record/retract it? | ✅ exists (`created_at`/`invalidated_at`) |

And **agency replaces liveness**: instead of a status flag, an entity carries **intervals of agency on
the world axis** — *can act in present scene time*. Death closes an interval; resurrection opens
another; multiple intervals are natural rather than exceptional. Reference availability is orthogonal
and effectively always true once introduced.

> **This subsumes Q1.** The question was *"what is the `life_status` vocabulary?"* The answer is that a
> status vocabulary was the wrong shape: **agency is an interval on an axis that does not exist yet.**
> Add the axis, and AC1 becomes a normal as-of read rather than a special case.

### D0.1 · World order is a **partial order over event entities**, not a time column — *(PO, 2026-08-09)*

> **The PO's correction:** *"Almost always the book has no real time order. The chapter time order is
> chaos and the book doesn't mention time. So time should be considered as an **entity (event
> timeline)**, and we should use the **chapter as the time unit** instead of real time."*

**Measured, and it settles both halves.**

| | |
|---|---|
| `event`-kind entities already in the glossary | **939** — second only to `character` (1,782) |
| event attributes already extracted | `participants` 691 · `outcome` 685 · `location` 632 · `date_in_story` 614 · `significance` 585 · `era` 201 |
| `:Event` nodes with **`event_order`** (reading) | **1,003 of 1,059 — 95 %** ✅ |
| `:Event` nodes with **`chronological_order`** (world) | **62 of 1,059 — 5.9 %** ⚠️ |
| of those 62, how many **diverge** from reading order | **62 — 100 %** 🔴 |
| ordering **edges** (`HAPPENS_BEFORE` / `CAUSES` / `PRECEDES`) | **0** |

**Two conclusions, and the first kills a shortcut I proposed above.**

**(1) ⛔ "Backfill world time = reveal time for linear books" is WRONG.** Every single event whose
chronological order was computed **disagrees with its reading order**. Reading order is not an
approximation of story order in this corpus — it is a *different thing that happens to look similar
when nobody checks*. Backfilling the identity would be wrong precisely where it matters, and silently
right everywhere it doesn't. **Withdrawn.**

**(2) `chronological_order` is 94 % empty because a scalar cannot express what the extractor knows.**
An integer demands a **total order** — a global position for every event. From prose you can usually
tell *"the betrayal came before the exile"* while having no idea where either sits globally, or whether
two events are simultaneous. So the extractor can only fill the scalar when it is confident about
everything, which is almost never. **`HAPPENS_BEFORE` was designed for exactly this and has zero
instances.**

> ### The model: time is an entity, chapter is the unit
>
> - **Events are the world-time substrate** — they already are entities (939 of them, with
>   participants, outcome, location).
> - **World order = a partial order (DAG) over event entities**, expressed as `HAPPENS_BEFORE` edges.
>   Partial, so *"A before B"* is recordable without knowing either one's global index, and
>   simultaneity and uncertainty are representable instead of forced.
> - **Chapter is the reveal unit** — `episodes.chapter_ordinal`, already 95 % populated and already
>   correct.
> - **A fact's world position is the event it is anchored to**, not the chapter it was extracted in.
> - **Agency becomes a graph question:** *"is X alive at story point P?"* → is there a death-event `E`
>   for `X` with `E HAPPENS_BEFORE P`'s anchoring event? Unknown ordering yields **unknown**, which is
>   the honest answer and one a scalar axis cannot give.
>
> **Nothing new is invented.** Event entities exist, chapter ordinals exist, `HAPPENS_BEFORE` is
> already a defined edge type. The work is to **populate the partial order and anchor facts to events**.

**Cost, stated honestly:** smaller than the absolute-axis version this replaces — no new time column on
`entity_facts`, no fold rewrite. The work is (a) `HAPPENS_BEFORE` extraction and curation, (b) a fact →
event anchor, (c) reachability queries over a DAG that is small per book. The risk moves from *schema*
to *extraction quality*: the partial order is only as good as the edges, and today there are none.

### D1 · Liveness becomes a fact, not a column *(superseded in part by D0 — the fact rides the world axis)*

`fact_kind = 'status'`, `attr_or_predicate = 'life_status'`, over a small closed vocabulary.

Then *"is X alive as of N"* is **the same query as every other as-of read** — no new store, no new
mechanism — and it inherits evidence, supersession, invalidation, and the episode citation for free.

Why not a column: the column form has already been tried and measured. `alive` is **7290 true / 0
false with 2 readers**, and `:EntityStatus` — which *is* modelled correctly, as a transition at a
reading position — sits on the wrong side of the identity seam at **0-of-21 reachable**. Death is a
story event at a position; that is precisely what a bitemporal fact is.

Requires widening `entity_facts_kind_chk` (today `attribute|relation|event|name|alias`). The
vocabulary should **seed the `ONT` existence ladder** rather than invent a parallel enum.

### D2 · The as-of read becomes required, not optional — the core reliability move

A parameter that is optional is a parameter every caller forgets; `composition-service`'s zero
occurrences of `as_of` is the proof. So the authoring path gets a **new KAL read whose story position
is required**:

```
GET /v1/kal/books/{book_id}/state?as_of={ordinal}     → one row per entity, single-valued:
     { entity_id, name@N, kind@N, life_status@N, attributes@N{...}, temporal_capability }
```

- **Required, not defaulted.** A default returns a silently wrong answer; a required parameter is a
  loud one. Same instinct as this repo's *spend-causing setting fails closed* rule.
- **Single-valued by construction.** One value per attribute per entity — which is exactly AC2.
- The planner/packer stop calling `roster` for cast state. `roster` survives as what it honestly is:
  an untimed catalogue enumeration.

### D3 · Identity becomes opaque; name and kind become facts

Adopt what the game tier already sealed rather than re-deriving it — **DL-A8** (*"the actor keeps its
`EntityId`… the entity does not change what it **is**, only who decides for it"*) and **ONT-A2**
(*"the self is not the decider… it carries what has happened to it"*).

`cached_name` and `kind_id` remain as **current-value caches** — the pattern this repo has already
proven three times (`entity_kind_votes`→`kind_id`, name-EAV→`cached_name`, `entity_facts`→
`canonical_snapshot`) — but the as-of read never consults them.

This retires `e.id = hash(user, project, name, kind)`, which is the only way a time-varying name and
kind can be coherent, and it kills the stale-`e.id` class permanently (the class the 2026-08-02 kind
backfill fired 77 times).

### D4 · The KAL grows a write path — and it is the only one

Extend **INV-KAL**'s scope from the bi-temporal reads to the **authored catalog and its writes**. Every
lore mutation becomes a named command that carries **story position + episode/evidence + actor**, and
writes its store and its outbox row **in one transaction**.

The gate already exists (`knowledge-access-gate.py` + `knowledge-http-surface-gate.py`, CI-enforced,
zero allowlist) — its scope simply stops at the authored catalog today. The new gate assertion:
**no bare `UPDATE glossary_entities` outside a command.** `softDeleteEntityCore` is the canonical
violation, and it is why deletion never propagates.

### D5 · Physical lifecycle — the second axis, wall-clock

The survey's axis: a lifecycle ledger with `deleted_at` / `status` demoted to derived caches, emitting
on **delete, restore and purge** (all three are silent today), and finally calling the already-built
`archive_entity(reason='glossary_deleted')` — designed, correct, honoured at 38 sites, **only test
callers**.

Kept deliberately separate from D1: physical status is *wall-clock and authored*; story status is
*story-ordinal and narrated*. One column could never have held both, which is the root of the five
private notions of "gone."

### D6 · Scale and HA

| | proposal | reason |
|---|---|---|
| `entity_facts` growth | **partition by `book_id`** | it is the growth table — one row per entity per attribute per chapter — and *every* query is already book-scoped, so the partition key is clean and needs no query changes |
| Postgres HA | **Patroni** (already in `infra/patroni`) | already the platform answer |
| graph HA | **none — make it rebuildable** | `SR06` already classifies the Neo4j derived layer **P2, "does not block active play."** DR becomes rebuild-from-Postgres |
| the two in-process caches | **key on a coverage digest, not a TTL** | `anchors.py::_CACHE` (300 s) and `GlossaryAnchorCache` (*"per-process, never cleared"*) cannot be invalidated by any event; keyed on a digest they become correct by construction |
| graph datastore choice | **defer, keep behind the KAL** | no lore-tier ceiling has been measured; see §6 |

---

## 5 · Acceptance tests — red before green

Each is written so it **fails today**, per the repo's bite discipline.

**AC1 · liveness is temporal, not a delete**
> A character dies in chapter 40. Read state `as_of=41`: `life_status = dead`, and a draft referencing
> them as acting must fail a check. Read state `as_of=39`: **present and alive.**
>
> The second half is what makes it a real test — it proves the mechanism is temporal rather than a
> deletion. A `deleted_at` implementation passes the first half and fails the second.

**AC2 · one value per attribute, not a union**
> The protagonist's age, appearance and a relationship each change at chapters 10, 25 and 60. Read
> state `as_of=30`: exactly the **chapter-25** values — one value per attribute.
>
> Today this returns either belief-latest or a smear across all three. This is AC2 verbatim.

**AC3 · the write path is the only path**
> A bare `UPDATE glossary_entities SET deleted_at = …` outside a command **fails the gate**; the
> command form emits, and a conformance test per consumer asserts the entity is absent from that
> consumer's output.

---

## 6 · Open questions — what must be decided or measured

| # | question | why it blocks |
|---|---|---|
| ~~**Q1**~~ | ⛔ **DISSOLVED 2026-08-09 (PO) — the question presupposed the wrong shape. See D0.** A status vocabulary cannot express liveness because **liveness is an in-world property and the fact store has only a reading-position axis**. Replaced by: **add a world-time axis, and model agency as intervals on it.** The load decision is salience, never liveness — *a dead character is referenced more, not less* | ✅ → **D0** |
| ~~**Q7**~~ | ✅ **RESOLVED 2026-08-09 (PO + measurement) — see D0.1.** No absolute time axis. **World order is a partial order over event entities** (`HAPPENS_BEFORE`), **chapter is the reveal unit**. The measurement that decided it: of the 62 events with a computed `chronological_order`, **62 diverge from reading order — 100 %** — so the "backfill world = reveal" shortcut is withdrawn | ✅ → **D0.1** |
| ~~**Q9**~~ | ✅ **RESOLVED 2026-08-09 — the machinery exists at three layers. See §6.2** | ✅ → **D8** |
| ~~**Q10**~~ | ✅ **DECIDED 2026-08-09 — BESIDE, not replacing.** They are different axes: `source_episode_id` records *where it was extracted* (**reveal provenance**); the event anchor records *when it is true* (**world position**). Collapsing them loses *"extracted in ch.40, true since ch.1"* — which is exactly the posthumous-narration case D0 exists for. *(orig)* **Does the fact→event anchor replace `source_episode_id`, or sit beside it?** `source_episode_id` records *where it was extracted* (reveal); the event anchor records *when it is true* (world). They are different axes and probably both needed — but that is a schema decision, not an obvious one | D0.1 schema |
| ~~**Q8**~~ | ✅ **SEALED 2026-08-09 — YES.** The author-curation opt-out and the reader spoiler window stop being query flags and become **"read at reveal position P"**. One concept instead of two, and it removes a fail-open class the register already records (author-curation views failing closed to EMPTY). **Cost accepted:** re-cuts a surface with shipped behaviour and tests. **Consequence for D0:** the reveal axis is no longer merely a rename of `valid_from_ordinal` — it becomes a **first-class read parameter** that the spoiler surfaces migrate onto | ✅ decided |
| ~~**Q8-orig**~~ | *(superseded)* **Does the reveal axis subsume the spoiler window?** If reveal time is first-class, the author-curation opt-out and the reader spoiler window stop being query flags and become *"read at reveal position P"*. Cheaper and more honest — but it re-cuts a surface that already has behaviour and tests | D0 scope |
| ~~**Q2**~~ | ✅ **SEALED 2026-08-09 — a ROLE is a relation fact with a story interval.** *"Lâm Trạch is the one who sets the trap, from ch.1"* becomes an `entity_facts` row: `fact_kind='relation'`, story interval, evidence. It inherits supersession, as-of reads and invalidation from machinery that already works — no new store, no new mechanism. **Two consequences that widen scope: (a)** the closed `entity_facts_kind_chk` set must widen; **(b)** roles are **plan-authored, not extracted**, so **composition-service becomes a KAL command producer** — the plan→lore write path is now explicitly in D4's scope, and the command vocabulary is wider than entity CRUD. **This closes `D-CANON-CHECK-BLIND-TO-ROLE`**, the refactor's stated acceptance case | ✅ decided → new slice **S-role** | <!-- doc-language-gate: ok -- the entity names are the cited corpus span from the dogfood acceptance case (Mi De book); quoting them in English would erase the identity the case turns on -->
| ~~**Q3**~~ | ✅ **RESOLVED 2026-08-09 by measurement — see §6.1.** Volatility varies **~50×** across attributes, and **11.7 % of single-valued fact rows already carry no new information** — a fraction that *grows with chapter count* | ✅ → adds **D7** (write-time dedupe) |
| ~~**Q4**~~ | ✅ **MEASURED 2026-08-09 — see §6.3.** `state@as_of` is **~8.7 ms and flat across the whole story range** on a 26,192-fact book. **Not invalidated.** But it falls back to `idx_entity_facts_book` (**128 lifetime scans**) and sorts — a shape that grows linearly with book length and spills `work_mem` before 4,000 chapters. → **D9** (covering index) + a synthetic-scale ceiling run stays a gate | ✅ → **D9** |
| ~~**Q5**~~ | ✅ **RESOLVED 2026-08-09 by D0.1 — and F3 is the wrong shape too.** Foundation F3 is described as *"unifying the KG **ordinal** axis"* — another **scalar total order**, the same error that leaves `chronological_order` 94 % empty. Under D0.1 the KG's temporal job is not to carry an ordinal but to hold the **`HAPPENS_BEFORE` / `CAUSES` partial order over event entities** — which is a *graph* question and the one thing a graph is unambiguously better at than Postgres. So: **the KG keeps as-of duty for event ordering, and gives it up for entity attribute state** (which is `TruthStore`'s). `temporal_unsupported` on the KG branch stays correct for attributes and becomes *wrong* for event ordering once D8 lands | ✅ → sharpens §4 D6 |
| ~~**Q6**~~ | ✅ **SEALED 2026-08-09 — INVALIDATE ON THE BELIEF AXIS.** A chapter edit already mints a new `episodes` row (`uq_episode_chapter_hash`); facts sourced from the superseded episode get `invalidated_at` + `invalidated_reason='episode_superseded'`, **reusing the exact mechanism already live for `superseded_same_ordinal`**. Story-time intervals are untouched — only the system's *belief* changes, which is what the belief axis is for. **Latent today:** 99 episodes / 99 chapters / **0 revisions** — the path has never fired, so this is red-before-green by construction | ✅ decided |
| ~~**Q6-orig**~~ | *(superseded)* **Do revisions invalidate a story position?** Authoring and translation mutate upstream text continuously. If chapter 3 is rewritten, every fact citing its episode is suspect. `episodes.content_hash` exists — is that the invalidation trigger? | decides whether belief-time alone is enough or revisions need their own axis |

---

## 6.1 · Q3 measured — attribute volatility, and the write-time dedupe it implies

Measured on the live dev glossary, 2026-08-09. Chains = `(entity, attribute)` with more than one
single-valued fact.

| attribute | facts / chain | distinct values | **% pure re-assertion** |
|---|---:|---:|---:|
| **gender** | 6.44 | **1.07** | **93.2 %** |
| owner | 4.44 | 1.57 | 49.3 % |
| affiliation | 6.17 | 2.42 | 28.2 % |
| type | 4.81 | 2.47 | 25.1 % |
| occupation | 5.93 | 3.15 | 22.5 % |
| social_class | 5.97 | 3.14 | 16.9 % |
| appearance | 5.34 | 3.92 | 12.5 % |
| role | 5.94 | 3.65 | 10.5 % |
| relationships | 5.85 | 5.11 | 5.4 % |
| personality | 5.49 | 4.96 | 3.8 % |
| **description** | 5.44 | 5.16 | **1.7 %** |

**Two findings.**

**(1) The bitemporal model already separates story change from extractor disagreement — and it works.**
Of superseded single facts, **42,264 close at a *later* chapter** (genuine story-time change) while
**4,360 collide at the *same* ordinal** and are handled on the belief axis instead, via
`invalidated_at` with `invalidated_reason='superseded_same_ordinal'`. That is the correct design and
it is live. **No change needed.**

**(2) But re-assertion is not deduped, and it compounds with book length.** `gender` writes **6.44
facts per entity and the value changes in 6.8 % of cases** — six rows for one bit of information.
Overall **11.7 % of single-valued rows (5,192 of 44,234) are pure re-assertion**, measured at only
~21 processed chapters. At 4,000 chapters an attribute re-asserted on every appearance produces
hundreds of identical rows, so this fraction **grows with the thing we are scaling for**.

> ### D7 · Dedupe re-assertion at write time
>
> In `emitChapterFacts`: if the incoming `value_hash` equals the currently-open fact's `value_hash`
> for the same `(entity, fact_kind, attr_or_predicate)`, **attach the new evidence to the existing
> fact instead of opening a new interval.** The fact's interval simply stays open.
>
> Wins three ways: fewer rows (the D6 partition arithmetic improves), **cheaper as-of reads** (fewer
> rows to scan on the hot path D2 makes mandatory), and a **truer story** — an unchanged attribute
> should read as *continuously true*, not as six consecutive assertions.
>
> **Bite:** re-run extraction over an already-extracted chapter — fact count must not grow, and
> evidence count must.

**No per-attribute volatility declaration is needed.** The data supplies it: dedupe by value, and
`gender` collapses to ~1 row while `description` keeps all 5.16. Volatility becomes an *observed*
property rather than an authored one — the same "ledger is truth" instinct this repo has used three
times already.

---

## 6.2 · Q9 measured — the ordering machinery already exists, at three layers

The risk in D0.1 was *"a partial order with no edges answers every question **unknown**."* Zero edges
exist. But three mechanisms are already built, and together they answer where edges come from.

| # | mechanism | where | state |
|---|---|---|---|
| **1** | **`rerank_chronological_order`** — ranks events by `event_date_iso`; **undated events → NULL**, with reading order as the *"dense, always-correct fallback"* | knowledge-service | ✅ built · **structurally cannot work here** |
| **2** | **`causal_edges.py`** — LLM *"narrative-causality analyst"* over a sliding window of ordered events, emitting `(:Event)-[:CAUSES]->(:Event)`; window 12 / stride 6 / max 40 calls; wired at `internal_extraction.py:1983`, budgeted in `llm_budget.py`, **advisory and never raises** | knowledge-service | ✅ **built and wired · 0 instances in data** |
| **3** | **`motif_link kind='precedes'`** — a partial order with a **DB trigger that refuses to close a cycle** | composition-service | ✅ built and in use — **at the motif layer** |

**Three findings.**

**(1) The 5.9 % is not a bug — it is mechanism 1 being honest.** `chronological_order` is derived
*only* from `event_date_iso`, and undated events are deliberately left NULL. **62 of 1,059 events have
a date.** That is the PO's *"the book doesn't really mention the time"*, measured. Mechanism 1 will
never cover this corpus and no amount of running it will help.

**(2) Mechanism 2 is the edge supply, and it is already built.** Same pattern as `archive_entity`:
designed, implemented, wired, never triggered. It emits `CAUSES`, and **causation implies order** — if
A causes B then A precedes B — so `CAUSES ⊆ HAPPENS_BEFORE`. The causal edges are also the *hardest and
most valuable* subset; plain succession is easier to infer, not harder.

**(3) The DAG-with-cycle-guard pattern D0.1 needs is already implemented one service over.**
`motif_link` enforces acyclicity in a trigger. D0.1 does not need to invent partial-order validation —
it needs to **copy a working local precedent up to the event layer**.

> ### D8 · Populate the event partial order — reuse, do not invent
>
> 1. **Widen `causal_edges.py`'s prompt from `causes/enables` to `causes | precedes`**, emitting a typed
>    edge. Same window/stride/cap, same advisory posture, same budget profile — a prompt and a schema
>    change, not a new pipeline. Prose supplies succession constantly (*"three years later"*, *"after
>    the funeral"*, *"meanwhile"*), which is *easier* for a model than causality.
> 2. **Copy the `motif_link` cycle-guard** to the event DAG. A temporal order that admits a cycle is
>    worse than none.
> 3. **Keep mechanism 1 as a high-confidence minority source** — the 62 dated events are real signal,
>    just rare. Dates outrank inferred edges when they conflict.
> 4. **Author curation stays the escape hatch.** The graph GUI already edits edges; a human fixing one
>    ordering is cheaper than a model getting the whole timeline right.
>
> **Bite:** run D8 over 封神演義 and assert the edge count is non-zero and the graph is acyclic. Today
> both the count and the guard are absent, so the test is red before it is green.
>
> **Residual risk, honestly:** edge *quality* is unmeasured. The dogfood already showed the relation
> proposer at **3 of 8 defensible**, so an ordering extractor may well land similarly. That argues for
> D8 shipping with **`unknown` as a first-class answer** — an ordering the model is unsure of must
> yield "unknown", never a guess, because a wrong order is worse than an absent one for a canon check.

---

## 6.3 · Q4 measured — the as-of state read, and the index it does not have

**Rig** (stated, per [`21` §2](../../03_planning/LLM_MMO_RPG/21_architecture_ceilings.md) — a number
without its rig is not a result): PostgreSQL **18.1** in Docker, dev `loreweave_glossary`,
`fsync=on`, `synchronous_commit=on`. Subject: book `019fb89f` — **26,192 facts · 1,673 entities ·
ordinals 0–97**, the only book in the corpus with real ordinal spread (封神演義's 18,620 facts are
**all at ordinal −1** — cold-start seeded, never chapter-extracted).

Query = D2's `state@as_of`: `DISTINCT ON (entity_id, attr_or_predicate)` over the half-open predicate.

| `as_of` | rows returned | execution |
|---:|---:|---:|
| 10 | 3,730 | **8.72 ms** |
| 50 | 8,914 | **8.62 ms** |
| 97 | 10,640 | **8.66 ms** |

**Flat across the entire story range** — cost tracks *output* size, not story position. At today's book
size the read is cheap, and D2 is not obviously expensive.

**Bite:** forcing `enable_indexscan=off` moves it **8.66 → 11.67 ms (1.35×)**. The number *does* move,
so the gate is not vacuous — but **only 1.35×**, which is the honest tell: at 48k rows a sequential
scan is barely worse than an index scan. **This measurement is characterising a small table, not index
behaviour.** Do not read it as a ceiling.

### The finding: D2 introduces a query shape with no supporting index

The plan is `Index Scan (idx_entity_facts_book) → quicksort → Unique`. It does **not** use
`idx_entity_facts_asof`, because that index is keyed `(entity_id, attr_or_predicate, …)` — built for
**single-entity** as-of reads, not a **book-wide** state sweep. Index-usage counters make the split
visible:

| index | scans | what it serves |
|---|---:|---|
| `idx_entity_facts_asof` | **136,655** | the per-entity as-of path — hot and well-served |
| `uq_entity_facts_natural` | 74,258 | write dedup |
| **`idx_entity_facts_book`** | **128** | ← the one D2's read falls back to. **Book-wide as-of is not a path that exists today** |

**Projection, stated as a projection.** 26,192 facts across 97 ordinals ≈ **270 facts/chapter**. A
4,000-chapter book at the same density ≈ **1.08 M facts**. The plan shape is *scan-the-book-then-sort*,
so it grows **linearly with book length**, and sort memory (1,181 kB at 10,640 rows) would reach tens
of MB — **spilling past `work_mem`** — well before that. The flatness measured above is flatness in
`as_of`, **not** in book size.

> ### D9 · A covering index for the book-wide as-of read
>
> ```sql
> CREATE INDEX idx_entity_facts_book_asof ON entity_facts
>   (book_id, entity_id, attr_or_predicate, valid_from_ordinal DESC)
>   WHERE invalidated_at IS NULL AND cardinality = 'single';
> ```
>
> Turns `DISTINCT ON` into an index-ordered scan and **removes the sort entirely** — which is the part
> that will not survive book growth. Cheap, additive, and it can ship with S1.
>
> **Bite:** drop the index and the plan must return to `Sort`. If it does not, the index is decoration.
> **Not yet measured** — deliberately not created on the shared dev DB; it belongs in a throwaway-DB run
> at synthetic 4,000-chapter scale, which is the ceiling test D2 actually needs.

**Verdict on Q4:** D2 is **not** invalidated — the read is ~9 ms at real book size and flat in `as_of`.
But the ceiling is **unmeasured at book scale**, and the shape is known to degrade. **D9 before S1
ships to large books**, and the synthetic ceiling run stays a gate.

---

## 7 · Proposed order

> **Revised 2026-08-09 after the [RED TEAM](2026-08-09-architecture-RED-TEAM.md).** The original order
> put AC1/AC2 — the reported defect — **behind** the KAL write path and the storage ports, i.e. months
> of infrastructure. **RT-1 killed that.** The as-of read runs on today's schema and is days of work;
> it now goes first, and it de-risks everything after it by proving the read shape on real data.

| slice | scope | proves |
|---|---|---|
| **S1** ⬅ *was S2* | **`state?as_of` read (required param)** over today's `entity_facts`; planner/packer migrate off `roster` for cast state | **AC2 — the PO's headline case** |
| **S2** ⬅ *was S1* | `fact_kind='status'`; reconcile `alive` and `:EntityStatus`; liveness as-of | **AC1** |
| **S3** | KAL **write path** + gate extension; every lore mutation becomes a command carrying position + evidence + actor | AC3 |
| **S4** | opaque identity; name/kind become facts; `e.id` hash retired | rename + re-kind leaves no stale node and mints no duplicate |
| **S5** | physical lifecycle ledger; emit on delete/restore/purge; wire `archive_entity` | per-consumer conformance |
| **S6** | `entity_facts` partitioning; digest-keyed caches | Q4's ceiling, re-measured after S1 |

**S1 is now the entry point and the headline.** It is AC2, it needs no new storage, and it is mostly
*routing reads through machinery that already works* — `entity_facts` is bitemporal, `emitChapterFacts`
writes at chapter ordinals, `maintain_chain` maintains pin-aware supersession, and the as-of predicate
is correct. `composition-service` simply passes `as_of` **zero times**.

S2 follows immediately because liveness is the simplest possible as-of fact — a one-value case that
hardens the read shape S1 introduced.

> ⚠️ **Gate before S1 commits *(RT-7)*:** `state@as_of` has **never been measured**, and D2 makes it
> **required rather than optional**, so it runs *more* than the reads it replaces. Measure it doc-21
> style — rig stated, ratios not absolutes, with a bite — before the caller migration lands. This is
> the measurement most likely to invalidate the design.

> ✅ **RT-2 dissolved 2026-08-09 — the premise was wrong.** There is no unowned artifact. **A lore
> bible is just a book**: a *world* is a **world-bible book + member books**, and `multi_project`
> already unions them (`:14` — *"the world-bible entity that also appears in a member book collapses
> to one"*; `:280` — *"grounded on SEVERAL knowledge graphs (worlds/books)"*). The outstanding work is
> to **extend planforge** to author game-focused lore books — not to design a new layer.
> `D-CANON-CHECK-BLIND-TO-ROLE` is therefore closed by **S-role below**, which is in scope.

---

## 8 · What this deliberately does not touch

- **The manifest, the reality DB, and everything below the boundary** (§2) — including `Q-L5A-1`
  canon emission. The book layer must work first; the manifest is compiled *from* it.
- **The lore bible** — not designed yet, per the PO. This proposal only ensures the book layer can
  answer the queries a bible builder would need.
- **Anything the MMO track has SEALED** — `ONT-*`, `GDA-*`, `SL-A12`, `ACT-A5`, `DL-A8` are consumed,
  not re-litigated.
- **The graph datastore choice** — deferred behind the KAL until Q4/Q5 produce a measured ceiling.
  An earlier draft of this file argued for a migration on unmeasured grounds; that argument is
  withdrawn (`SR06` classifies the graph P2, and the sparse-graph benchmark that motivated it was
  the flattering-number trap [`21` §1](../../03_planning/LLM_MMO_RPG/21_architecture_ceilings.md) forbids).
