# Current architecture and blast radius — glossary · KG · wiki

**Reconciles:** **Module/service boundaries** · **Per-service DB ownership / no cross-DB FK** — the blast radius is measured ALONG those two boundaries; the document is a measurement of the existing rows, not a proposal.

**Status:** SURVEY · not a design, not an investigation. **Opened:** 2026-08-09
**Verified at:** `df18e9049` (branch `refactor/entity-lifecycle`)
**Purpose:** the three inputs to this refactor each followed one bug. None of them draws the map.
This does. It is the answer to *"if an entity's lifecycle changes, what has to hear about it?"*

> **How to read a claim here.** Every number and every path in this file was re-derived by
> command at `df18e9049` during the survey; §10 lists the commands. Where a claim is carried
> from another document rather than re-run, it says so inline. Where the survey **contradicts**
> an existing spec, §8 says so explicitly rather than quietly correcting it.

---

## 1 · Headline

**27 of 47 services** touch glossary, KG or wiki data. **8 datastores** hold it. **The authored
lifecycle reaches exactly one of them.**

| | |
|---|---|
| services referencing glossary / KG / wiki | **27 of 47** |
| Postgres logical databases holding entity-shaped data | **8** (`loreweave_glossary`, `_knowledge`, `_composition`, `_translation`, `_book`, `_lore_enrichment`, `_learning`, `_events`) |
| Neo4j node labels in the entity graph | **10** (`:Entity` `:Event` `:Fact` `:Passage` `:EntityStatus` `:ExtractionSource` `:Chapter` `:Part` `:Book` `:Scene`) |
| frontend feature folders rendering entity data | **31 of 43** |
| `glossary.*` event types actually emitted | **3** (`entity_updated`, `entity_merged`, `name_confirmed`) — no delete, no restore, no purge |
| `glossary.*` entries in the "AUTHORITATIVE" event registry | **0** |
| reads honouring `deleted_at` inside glossary-service | **241** |
| reads honouring `deleted_at` **outside** glossary-service | **0** |

The last two lines are the refactor, stated as a ratio.

---

## 2 · The storage map — every store that holds entity-shaped data

### 2.1 Postgres — one instance, eight logical DBs that hold entity data

All on `postgres:5432` in dev (`infra/docker-compose.yml`), one logical DB per owning service.
**There is no FK between any two of them.** Every cross-DB reference below is a bare `UUID`
column, and at least one migration says so in a comment: *"glossary entity (cross-DB, no FK)."*

| DB | owner | tables that hold or point at an entity | lifecycle column |
|---|---|---|---|
| `loreweave_glossary` | glossary-service (Go) | **the authored SSOT.** `glossary_entities`, `entity_attribute_values`, `entity_attribute_value_items`, `entity_facts`, `entity_genres`, `entity_kinds`, `entity_kind_votes`, `entity_kind_aliases`, `entity_revisions`, `entity_enrichments`, `entity_research_jobs`, `chapter_entity_links`, `merge_candidates`, `merge_journal`, `canonical_snapshot(_translations)`, `canonical_fold_state`, `evidences`, `episodes`, **`wiki_articles`, `wiki_revisions`, `wiki_staleness`, `wiki_suggestions`, `wiki_article_source_usage`** | `deleted_at`, `permanently_deleted_at`, `status`, `alive` |
| `loreweave_knowledge` | knowledge-service (Python) | `entity_canonical_snapshots`, `entity_alias_map`, `entity_access_log`, `knowledge_summaries(_versions)`, `knowledge_pending_facts`, `knowledge_rejected_facts`, `kg_triage_items`, `kg_graph_schemas`, `kg_schema_node_kinds`, `kg_edge_types`, `kg_fact_types`, `kg_views`, `kg_vocab_sets/_values`, `extraction_*`, `wiki_gen_jobs`, `sweeper_state` | **none for entities** |
| `loreweave_composition` | composition-service | `voice_profile(entity_id, entity_name)`, `outline_node(pov_entity_id, present_entity_ids[], location_entity_id)`, `canon_rule(entity_id)`, `entity_override(target_entity_id)`, `plan_bootstrap_proposal(proposed_entity_id)`, `motif_application`, `derivatives`, `glossary_build_items/_runs` | **none** |
| `loreweave_translation` | translation-service | `chapter_translation_glossary_usage(entity_id)`, `segment_glossary_usage(entity_id)`, `chapter_translations.resume_state` **(JSONB — freezes the glossary block + correction map)**, `chapter_translations.is_glossary_stale`, `extraction_raw_outputs` (the kind-vote source corpus) | `is_glossary_stale` only |
| `loreweave_book` | book-service (Go) | `chapters.kg_indexed_revision_id`, `chapters.kg_exclude`, two `entity_id UUID` columns commented *"soft cross-service ref → glossary location entity"* | **none** |
| `loreweave_lore_enrichment` | lore-enrichment-service | `writeback_entity_id`, `promoted_entity_id` — both commented *"glossary entity (cross-DB, no FK)"* | **none** |
| `loreweave_learning` | learning-service | `corrections`, `quality_scores` keyed by the entity in the event payload | **none** |
| `loreweave_events` | worker-infra | the meta/event spine | n/a |

**A latent seam worth naming now:** knowledge-service is configured with **`GLOSSARY_DB_URL`** and
opens a second asyncpg pool against the glossary database (`app/db/pool.py:17`). At `df18e9049`
that pool is used by **exactly one thing — the health check** (`routers/health.py:28`). So the
direct cross-service DB read is *wired but unused*. It is a loaded gun for anyone who "just needs
one column", and the refactor should decide deliberately whether to remove it or bless it.

### 2.2 Neo4j — the derived graph

One instance (`bolt://neo4j:7687`), owned solely by knowledge-service. `NEO4J_URI=` empty is a
supported "Track 1" mode in which the whole graph is skipped — several handlers branch on it.

```
:Entity ──EVIDENCED_BY──▶ :ExtractionSource         :Entity ──RELATES_TO──▶ :Entity
   │                                                    │
   ├──ABOUT──▶ :Fact / :Event                           ├──MENTIONED_IN──▶ :Passage / :Chapter
   └──(status)──▶ :EntityStatus                    :Book ──HAS_CHILD──▶ :Part ──HAS_CHILD──▶ :Chapter
```

`:Entity` node properties that matter to this refactor:

| property | meaning | who sets it |
|---|---|---|
| `id` | **`hash(user_id, project_id, name, kind)`** — the derived canonical id | `glossary_sync` `ON CREATE` only (see §8.2) |
| `glossary_entity_id` | FK to the authored SSOT — **the only stable key** | `glossary_sync` MERGE key |
| `archived_at` | KAL's private notion of "gone" | FE archive button + `archive_entity()` |
| `anchor_score` | 1.0 = anchored to glossary, 0 = archived | `compute_anchor_score`, `archive_entity` |
| `kind_code` | the mirrored scalar kind — **no facet column** (`D-KG-KIND-FACETS`) | `glossary_sync` |
| `status` | **derived, not stored** — `archived_at→archived`, else `glossary_entity_id→canonical`, else `discovered` | `entities.py:163` |

`archived_at IS NULL` is honoured at **38 sites**. `deleted_at` is honoured at **0** — confirmed
again at `df18e9049`: `grep -rn "deleted_at\|entity_deleted" services/knowledge-service/app` → **0**.

### 2.3 Redis — streams and locks, plus one dangerous cache class

Redis is the event bus (`loreweave:events:*` streams) and a lock/cooldown store. It holds
**almost no entity data**, and that is the problem: the caches that *do* hold entity data are
**in-process**, so no Redis `DEL` can reach them.

| cache | store | invalidation | consequence for a lifecycle change |
|---|---|---|---|
| `anchors.py::_CACHE` — the Aho-Corasick name/alias automaton | **in-process dict**, per replica | **300 s TTL only**; `clear_anchor_cache()` is documented as a *test seam* | a deleted entity stays anchorable for up to 5 min **per replica**, and there is no way to push an invalidation |
| `anchors.py::_PROTAGONIST_CACHE` | in-process dict | 300 s TTL | same |
| `jobs/glossary_anchor_cache.py::GlossaryAnchorCache` | **in-process LRU, 1000 entries** | **none** — its own docstring: *"per-process, never cleared"* | a deleted entity survives in an extraction run's anchor set **until the process restarts** |
| `knowledge:regen:cooldown:*` | Redis | TTL | not entity data |
| `wiki/writeback.py` `entity:{id}` / `kg:{id}` | request-scoped dict | n/a | citation source text, transient |

> **This is a design constraint, not a bug list.** Any lifecycle event that must take effect
> promptly cannot rely on cache-key deletion — the two caches that matter are per-replica memory.
> The options are a shorter TTL, a broadcast invalidation channel, or making the read path
> re-consult glossary (which is what the one safe selector already does — §4.3).

### 2.4 Other stores

MinIO (assets), RabbitMQ (worker-infra job fan-out), Qdrant/pgvector — **none holds entity
records.** Embeddings live on the Neo4j nodes and in knowledge-service's own tables, so they
inherit `:Entity`'s lifecycle, not a separate one.

---

## 3 · The service map — 27 services, in four rings

Counted by file references to `glossary` / `knowledge-service|neo4j` / `wiki`.

### Ring 0 — the owners (2)

| service | lang | owns |
|---|---|---|
| **glossary-service** | Go | the authored entity SSOT + the whole wiki article store. 273 refs to `glossary_entities`, 241 `deleted_at` reads |
| **knowledge-service** | Python | the derived graph (Neo4j), extraction, context selection, wiki *generation*, summaries. 345 KG refs |

### Ring 1 — hold their own copy of entity data (6) · *the dangerous ring*

| service | what it keeps | refreshed by |
|---|---|---|
| **composition-service** | `voice_profile.entity_name` (denormalised), `outline_node.present_entity_ids[]`, `canon_rule.entity_id`, `entity_override` | nothing — written once at plan time |
| **translation-service** | `resume_state` JSONB freezing the glossary prompt block + correction map; `*_glossary_usage(entity_id)`; `is_glossary_stale` | `glossary.entity_updated` only |
| **lore-enrichment-service** | `writeback_entity_id`, `promoted_entity_id` | `glossary.*` stream |
| **book-service** | `chapters.kg_indexed_revision_id`, two location `entity_id` refs | `chapter.*` events |
| **learning-service** | `corrections` / `quality_scores` derived from entity events | `glossary.*`, `wiki.*` |
| **campaign-service** | consumes `loreweave:events:knowledge` | events |

### Ring 2 — read live, hold nothing (7)

**chat-service** (81 glossary refs — the `<glossary>` and `<facts>` prompt blocks),
**knowledge-gateway** (KAL — a NestJS façade over glossary + knowledge, `main.ts` boots pointing
at both), **api-gateway-bff** (15 knowledge + 8 glossary URL refs — the browser's door),
**ai-gateway**, **worker-ai** (has `KNOWLEDGE_DB_URL` — direct DB), **worker-infra**,
**jobs-service**.

### Ring 3 — the game tier · *contract-only, not yet built* (2)

**world-service** (Rust) reads canon through `reality_seeder::canon_reader`, bound in production
to `glossary_client::export_canon_for_seed`. **game-server** is stateless at V0 (echo room, no
canon read).

Two things are true and both matter:

1. The contract exists — `contracts/api/glossary-service/seed_export.yaml` — and **carries no
   lifecycle field at all**. No `deleted`, no `status`, no `alive`. Its description says
   *"Includes ALL canon entries regardless of `canon_layer`."*
2. **Neither side is implemented.** `grep -rn "seed_export" services/glossary-service` → nothing;
   `canon_entries` is not a table in any migration. world-service has the trait and a mock.

> **This is the one piece of good news in the whole survey.** The lifecycle audit called the game
> tier *"the worst gap, because it is where the consequences are worst"* — and it turns out the
> game tier's canon read is still a contract on paper. The refactor can put lifecycle into
> `seed_export.yaml` **before** it ships, instead of retrofitting a fifth consumer afterwards.
> That window closes the day someone implements the handler.

### Ring 4 — frontend (31 of 43 feature folders)

`knowledge` (189 files) · `studio` (95) · `composition` (89) · `glossary` (68) · `chat` (65) ·
`wiki` (30) · `campaigns` (18) · `plan-hub` (18) · `world` (16) · `knowledge-temporal` (16) ·
`jobs` (16) · `plan-forge` (15) · `assistant` (14) · `standards` (13) · `glossary-translate` (12) ·
`translation` (9) · `enrichment` (8) · `books` (5) · `extraction` (5) · `extensions` (5) ·
`world-setup` (5) · `raw-search` (4) · `settings` (4) · `home` (3) · `onboarding` (3) ·
`profile` (3) · `trash` (3) · and 4 single-file folders (`notifications`, `oauth`, `usage`,
`workflows`).

---

## 4 · Dataflow

### 4.1 The write path — how an entity comes to exist

```
 chapter text
     │
     ├─▶ translation-service · extraction_worker            [Python]
     │      ├─ fetch_known_entities(book)  ← ONCE, before the chapter loop (:474 vs :589)
     │      ├─ LLM extract → extraction_raw_outputs         ← the kind-vote corpus
     │      └─ POST /internal/books/{id}/extract-entities
     │                    │
     │                    ▼
     │         glossary-service · extraction_handler        [Go]
     │            ├─ findEntityCrossKind (oldest-wins, DOES filter deleted_at)
     │            ├─ entity_kind_votes  → domain.ResolveKind → maybe re-kind   ← M1–M3, shipped
     │            ├─ UPSERT glossary_entities  (kind_id, name, aliases, …)
     │            └─ INSERT outbox_events ('glossary.entity_updated')
     │                    │
     │                    ▼  publisher drains FOR UPDATE SKIP LOCKED
     │            Redis Stream  loreweave:events:glossary
     │                    │
     │                    ├─▶ knowledge-service   handle_glossary_entity_updated
     │                    │      └─ glossary_sync → Neo4j MERGE on glossary_entity_id
     │                    ├─▶ learning-service    (actor=user ⇒ a correction)
     │                    ├─▶ translation-service (⇒ is_glossary_stale = true)
     │                    ├─▶ lore-enrichment-service
     │                    └─▶ glossary-service    (self: revision + staleness consumers)
     │
     └─▶ knowledge-service · extraction (Pass 0 → Pass 2)   [Python]
            ├─ load_glossary_anchors(book)  → GlossaryAnchorCache (in-process, never cleared)
            ├─ entity_resolver: anchor hit ⇒ anchor · MISS ⇒ MINT      ← the identity root
            └─ pass2_writer → :Entity, :Fact, :Event, :EntityStatus
```

### 4.2 The wiki path — it spans both owners

Worth drawing because the wiki is the one artifact a **reader outside the system** can see, and
it is the only one of the three that already has a delete event.

```
knowledge-service                                  glossary-service
─────────────────                                  ────────────────
wiki_gen_enqueue ─▶ wiki_gen_jobs (knowledge DB)
       │
wiki_gen_processor
       ├─ wiki/context.py  gather_kg_facts   ← subject protected, NEIGHBOURS ARE NOT
       ├─ wiki/generate.py (LLM)
       ├─ wiki/verify.py + rulegate.py
       └─ wiki/writeback.py ──── HTTP ────▶  wiki_articles / wiki_revisions   (glossary DB)
                                             wiki_article_source_usage  ← the citation index
                                             wiki_staleness             ← fed by staleness_consumer
                                                    │
                                                    └─▶ 'wiki.deleted' / 'wiki.generated'
                                                        / 'wiki.corrected' / 'wiki.suggestion_reviewed'
```

The wiki has **four** lifecycle-aware events including a real `wiki.deleted`. The entity the
article is *about* has none. A published article can therefore outlive its subject with no signal.

### 4.3 The read path — and the one selector that is safe

```
chat turn / drafting / game
     │
     ├─▶ <glossary> block ─▶ select_glossary_semantic (selectors/glossary.py:294)
     │        vector-search Neo4j → fetch_entities_by_ids → GLOSSARY RE-CONSULTED
     │        └─ trashed row dropped (`if r is None: continue`)      ✅ SAFE BY CONSTRUCTION
     │
     └─▶ <facts> block ─▶ anchors.py · facts.py · relations.py · get_entity_with_relations
              reads :Entity node properties, filters `archived_at IS NULL`
              └─ glossary NEVER sets archived_at                     ❌ LEAKS
```

**Two blocks of the same prompt disagree, by construction.** The `<glossary>` block re-consults
the SSOT and is correct; the `<facts>` block trusts the graph's private flag and is wrong. That
one diagram is the clearest statement of the defect in the whole survey — and it also names the
fix pattern that already works.

### 4.4 The event topology

Producers write to a per-service `outbox_events` table in the **same transaction** as the data
write; a publisher drains `FOR UPDATE SKIP LOCKED` and `XADD`s to `loreweave:events:<aggregate>`;
consumers are idempotent on `(source_service, source_outbox_id)`.

**Who listens to `loreweave:events:glossary`** — 5 consumers:
knowledge-service · learning-service · translation-service · lore-enrichment-service ·
glossary-service (its own revision + staleness projections).

**Who listens to `loreweave:events:knowledge`** — 4:
campaign-service · learning-service · worker-ai · knowledge-service.

**The `glossary.*` vocabulary actually emitted — 3:** `entity_updated`, `entity_merged`,
`name_confirmed`. **No deletion event of any kind.**

Three near-misses that a naive grep reports as events and which are **not**, recorded so the next
session does not chase them: `glossary.batch` and `glossary.merge` are **confirm-token
descriptors** (`action_confirm_token.go:81`), and `glossary.entity_created` appears **only in
tests** — as a deliberately-negative case in `staleness_consumer_test.go:32` and a dispatch fixture
in learning-service. The Go `const` block in `outbox.go` remains the whole real list.

Confirmed at the source. `softDeleteEntityCore` (`entity_handler.go:1493`) is a bare
`UPDATE … SET deleted_at = now()` with **no outbox write**, and `bulkDeleteEntities` carries a
comment that states the gap in the codebase's own words:

> *"No outbox event is emitted — mirrors the single-entity deleteEntity (the `glossary.entity_*`
> events carry no 'deleted' variant today; adding one is a separate cross-cutting change)."*

`restoreEntityCore` and `purgeEntity` (`recycle_bin_handler.go:174`, `:192`) are likewise bare
UPDATEs. **All three lifecycle transitions — delete, restore, purge — are silent.**

---

## 5 · Where "gone" lives — the state × store table

The table [lifecycle §5.2](2026-08-02-entity-lifecycle-architecture-gap.md) asked for. It is
almost entirely blank, and the blankness is the finding.

| store | column | honoured by | set by delete? | set by restore? | set by purge? |
|---|---|---|---|---|---|
| glossary `glossary_entities` | `deleted_at` | **241 reads, all in-service** | ✅ | ✅ | — |
| glossary `glossary_entities` | `permanently_deleted_at` | transitively via `deleted_at` | — | — | ✅ |
| glossary `glossary_entities` | `status` (`draft`/`active`/`inactive`/`rejected`) | **4 functional call sites** (wiki-gen, translation-glossary CTE, export) | ❌ | ❌ | ❌ |
| glossary `glossary_entities` | `alive` | 2 reads · **narrative death, not lifecycle** | ❌ | ❌ | ❌ |
| Neo4j `:Entity` | `archived_at` | **38 sites** | ❌ | ❌ | ❌ |
| Neo4j `:Entity` | `anchor_score` | anchor preload | ❌ | ❌ | ❌ |
| Neo4j `:EntityStatus` | narrative liveness | the gone-cast guard | ❌ | ❌ | ❌ |
| knowledge `entity_alias_map` | merge tombstone | re-extraction redirect | ❌ | ❌ | ❌ |
| translation `is_glossary_stale` | Coverage UI | ❌ (`entity_updated` only) | ❌ | ❌ | ❌ |
| translation `resume_state` JSONB | the live translation prompt | ❌ frozen per chapter | ❌ | ❌ | ❌ |
| composition `voice_profile` | every generated scene | ❌ | ❌ | ❌ | ❌ |
| composition `present_entity_ids[]` | `<present>` block | ❌ | ❌ | ❌ | ❌ |
| glossary `wiki_articles` | published reader-facing text | ❌ | ❌ | ❌ | ❌ |
| game `canon_projection` | world state | **not built** | n/a | n/a | n/a |

One column, in one service, does anything. Note the two ❌ columns nobody has discussed: **restore
and purge are as unwired as delete.** A design that only emits `entity_deleted` fixes one third of
the transitions and leaves a restored entity permanently archived in the graph.

---

## 6 · The event-registry inversion

`contracts/events/_registry.yaml` calls itself *"AUTHORITATIVE list of every event_type emitted by
LoreWeave services"* and has a real generator pipeline behind it (`make eventgen`, a
`scripts/eventgen-validate.sh` CI gate, Go structs, upcasters, version cooldowns).

It contains **15 events. All 15 belong to the game tier**: `reality.*`, `npc.*`, `world.*`,
`canon.*`, `xreality.*`. Every event the actual platform emits — all `glossary.*`, `chapter.*`,
`book.*`, `translation.*`, `composition.*`, `knowledge.*`, `wiki.*` — is **outside it**, hand-mirrored
as Go/Python string constants with no generator and no drift gate. (A grep for `<domain>.<verb>`
string literals across `services/` returns ~100 candidates, but as the §4.4 near-misses show that
is a superset: without a registry there is no way to get the true number, which is itself the
finding.)

And the inversion is sharper than "glossary is missing." The registry already contains:

```yaml
- name: canon.entry.decanonized      # a retraction event, versioned, with a Go struct
- name: xreality.user.erased         # GDPR erasure, fully specified
```

**The game tier has a designed, generated, gated retraction event for canon it does not yet
store — while the glossary entity that will feed that canon cannot say it was deleted.**

That is why `D-GLOSSARY-EVENTS-NO-SOT` fires first: `glossary.entity_deleted` cannot be added
honestly without deciding whether the platform's 100 events join the registry, and the game tier's
`canon.entry.decanonized` is the shape the answer should probably rhyme with.

---

## 7 · Blast radius of one delete, ranked

What must change state when an author trashes one entity, in dependency order:

| # | surface | mechanism today | needed |
|---|---|---|---|
| 1 | glossary `deleted_at` | ✅ works | — |
| 2 | glossary outbox | ❌ silent | emit `glossary.entity_deleted` |
| 3 | events registry | ❌ 0 glossary entries | register (or decide not to) |
| 4 | Neo4j `:Entity.archived_at` | ❌ never set | call the **already-built** `archive_entity(reason='glossary_deleted')` |
| 5 | Neo4j `:EntityStatus`, `:Fact`, `:Event`, `:Passage` | ❌ untraced | decide: cascade, orphan, or leave |
| 6 | `entity_alias_map` tombstone | ❌ absent | anti-resurrection redirect |
| 7 | in-process anchor caches ×2 | ❌ 300 s TTL / never cleared | broadcast, shorten, or re-consult |
| 8 | translation `is_glossary_stale` | ❌ `entity_updated` only | subscribe to the delete |
| 9 | translation `resume_state` JSONB | ❌ frozen per chapter | re-read or invalidate on resume |
| 10 | translation extraction `known_entities` | ❌ fetched once per job | re-fetch per chapter (`D-KNOWN-ENTITIES-PER-JOB`) |
| 11 | composition `voice_profile` | ❌ denormalised name | filter or re-resolve |
| 12 | composition `present_entity_ids[]` | ❌ static array | filter at read |
| 13 | glossary `wiki_articles` citing it | ❌ nothing | staleness or unpublish |
| 14 | knowledge `find_entities_needing_embedding` | ❌ re-embeds forever | exclude (cost) |
| 15 | game `canon_projection` | **not built** | put lifecycle in `seed_export.yaml` **now** |

Rows 2, 4 and 6 are one connected change. Rows 7–12 are six independent consumers, and each needs
its own conformance test — *trash an entity, assert it is absent from this consumer's output* —
which is what [lifecycle §5.6](2026-08-02-entity-lifecycle-architecture-gap.md) asked for.

---

## 8 · What this survey found that the three inputs did not

### 8.1 🔴 `glossary.entity_deleted` was fully designed in 2026 and never built — on either side

It is not a new idea to be invented by this refactor. It is a **specified, abandoned one**:

- `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md:3130` gives the exact handler semantics:
  *"`glossary.entity_deleted` → `handle_glossary_entity_deleted` — Soft-archive the linked entity:
  set `archived_at`, clear `glossary_entity_id`, set `anchor_score = 0`. Do NOT delete (preserves
  graph/timeline)."*
- `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md:740` lists it in the dispatch table
  and `:753` restates the no-cascade rule.

That is why `archive_entity` exists, is correct, preserves every edge, and has only test callers:
**the consumer half was built to spec and the producer half never was.** The dispatch registration
was never added either.

**Consequence for the design:** the "how does a state change travel" question already has a
written, reviewed answer from the original architecture. The refactor should start by deciding
whether to adopt it or supersede it — not by re-deriving it.

### 8.2 🔴 An entity rename or re-kind leaves a stale `e.id` in Neo4j — and the kind refactor just fired 77 of them

Found by the **2026-06-20** data-architecture audit as its finding #2. Re-verified at `df18e9049`:

```python
# app/extraction/glossary_sync.py
ON CREATE SET  e.id = $canonical_id,  …     # :84   ← hash(user, project, name, kind)
ON MATCH  SET  e.name = $name, e.kind = $kind, e.aliases = …   # :100-107
#              ^^^ e.id is NOT in this list
```

`e.id` is `hash(user_id, project_id, name, kind)`. `ON MATCH` updates `name` and `kind` and leaves
`id` frozen at the hash of the **old** values. **48 Cypher sites key on `Entity.id`.**

The part nobody has connected: **the kind-vote resolution shipped 2026-08-02 emits
`glossary.entity_updated` on every primary-kind change** (`kind_votes_handler.go:167` →
`insertEntityOutboxEvent`). That event drives `glossary_sync` → `ON MATCH SET`. So the backfill's
**77 applied re-kinds each mutated `e.kind` while leaving `e.id` hashed on the old kind.** The
graph currently holds 77 nodes whose derived id disagrees with their own properties.

This belongs to this refactor by definition: it is the identity hash (`D-ENTITY-IDENTITY-HASH`)
and the kind resolution (M1–M3, shipped) colliding in the KG mirror, which is exactly the seam
`D-KG-KIND-FACETS` moves. It is **not** in any of the three inputs.

### 8.3 🟡 "No reconcile sweep exists anywhere" is too strong — the substrate exists

[Lifecycle §5.3](2026-08-02-entity-lifecycle-architecture-gap.md) says there is no reconcile sweep.
More precisely: there is **no entity-lifecycle sweep**, but the machinery for one is built and in
production use — `sweeper_state` (a per-sweeper user cursor table), `reconcile_evidence_count` +
its scheduler, `quarantine_cleanup(_scheduler)`, `orphan_extraction_source_cleanup`,
`anchor_refresh_loop`. A cross-DB integrity sweep was also the **2026-06-20 audit's follow-up #3**
and was never done.

This matters because it changes the cost of the "event vs sweep vs both" decision in
[lifecycle §5.3](2026-08-02-entity-lifecycle-architecture-gap.md): the sweep arm is a new
`sweeper_name` on an existing substrate, not a new subsystem.

### 8.4 🟡 Restore and purge are as unwired as delete

Every discussion so far has been about deletion. `restoreEntityCore` and `purgeEntity` are also
bare UPDATEs with no outbox write. Combined with `restore_entity`'s known asymmetry (it clears
`archived_at` but deliberately does not recompute `anchor_score`), a naive one-event design
produces a **permanently archived** entity after a restore.

### 8.5 🟢 The game-tier canon contract is still on paper

`seed_export.yaml` exists with no lifecycle field; no handler, no `canon_entries` table. The worst
consequence surface named by the lifecycle audit has **not been built yet**. Adding lifecycle to
that contract now costs a schema edit; adding it after the handler ships costs a fifth consumer
migration.

### 8.6 🟡 knowledge-service holds an unused direct pool into the glossary DB

`GLOSSARY_DB_URL` → `create_pools(...)` → used only by `/healthz`. Decide deliberately: remove it,
or bless it as the read path for a reconcile sweep (which is the one job where a direct cross-DB
read is genuinely the right tool).

---

## 9 · What this survey did NOT cover

Stated so the map's edge is visible rather than assumed.

- **Runtime measurement.** Everything here is code and schema. No query was run against a live
  Postgres or Neo4j. The controlled experiment [lifecycle §7](2026-08-02-entity-lifecycle-architecture-gap.md)
  asks for — trash a live entity with a Neo4j node, re-run a context selector — **is still not run.**
  Neither is identity §5's step **C**.
- **The 77 stale-`e.id` nodes are inferred, not counted.** The mechanism is verified at
  `df18e9049`; the number is carried from the kind spec's backfill report. A Cypher query
  comparing `e.id` against a recomputed `hash(user, project, name, kind)` would give the true
  figure across the whole graph, and would also catch renames.
- **The 31 frontend folders were counted, not read.** Which of them hold their own cache is
  unknown — the same gap [lifecycle §8](2026-08-02-entity-lifecycle-architecture-gap.md) named.
- **Neo4j orphans other than `:Entity`** — `:Fact`, `:Event`, `:Passage`, `:EntityStatus`
  referencing a trashed entity are still untraced.
- **`chapter_entity_links` cascade.** Soft-delete explicitly does not cascade it
  (per the `extraction_handler.go:273` comment); what that means for consumers is not analysed here.
- **20 services were not opened** — they showed zero references to glossary/KG/wiki. That is a
  grep result, not a proof.
- **Historical damage remains unmeasured**: how many *currently published* wiki articles or
  translated chapters already contain a retracted entity. Still the real cost, still unknown.

---

## 10 · Reproduce this survey

Line numbers rot; these do not. Run from the repo root.

```bash
# §1 — services touching the three domains
for s in $(ls services); do
  g=$(grep -rIl -iE "glossary" services/$s | wc -l)
  k=$(grep -rIl -iE "knowledge-service|neo4j" services/$s | wc -l)
  w=$(grep -rIl -iE "\bwiki\b" services/$s | wc -l)
  [ "$g" -gt 0 -o "$k" -gt 0 -o "$w" -gt 0 ] && echo "$s $g $k $w"
done

# §2.1 — the logical DBs and who owns them
grep -nE "DATABASE_URL|_DB_URL|NEO4J_URI|REDIS_URL" infra/docker-compose.yml

# §2.1 — knowledge-service's unused glossary pool (expect: pool.py + health.py only)
grep -rn "get_glossary_pool" services/knowledge-service/app --include=*.py | grep -v test

# §2.2 — the graph schema
grep -rhoE "\(\s*[a-z_]*\s*:\s*[A-Z][A-Za-z]+" services/knowledge-service/app --include=*.py \
  | grep -oE ":[A-Z][A-Za-z]+" | sort | uniq -c | sort -rn

# §2.3 — the caches that cannot be invalidated
sed -n '1,15p'   services/knowledge-service/app/jobs/glossary_anchor_cache.py   # "never cleared"
grep -n "_CACHE\|ttl_s" services/knowledge-service/app/context/anchors.py

# §4.4 — the glossary event vocabulary. The raw grep returns 6; three are near-misses
# (two confirm-token descriptors + one test-only string), so exclude tests and check
# each survivor has a producer. The real list is the const block in outbox.go.
grep -rhoE '"glossary\.[a-z_]+"' services --include=*.go --include=*.py | sort -u
grep -rn 'glossary\.entity_\|glossary\.name_confirmed' services/glossary-service/internal/api/outbox.go
grep -rn '"glossary\.batch"\|"glossary\.merge"\|"glossary\.entity_created"' services \
  --include=*.go --include=*.py     # expect: only descriptors + tests
grep -n "SET deleted_at" -B 8 services/glossary-service/internal/api/entity_handler.go
grep -n "No outbox event is emitted" -A 3 services/glossary-service/internal/api/entity_handler.go

# §5 — one column does the work; nothing outside the service reads it
grep -rn "deleted_at" services/glossary-service/internal --include=*.go | grep -v _test | wc -l   # 241
grep -rn "deleted_at\|entity_deleted" services/knowledge-service/app --include=*.py | wc -l       # 0
grep -rn "archived_at IS NULL" services/knowledge-service/app/db/neo4j_repos/*.py | wc -l         # 38

# §6 — the registry inversion: 15 events, all game-tier, 0 glossary
grep -cE "^\s+- name:" contracts/events/_registry.yaml     # 15
grep -E  "^\s+- name:" contracts/events/_registry.yaml
grep -c  "glossary\." contracts/events/_registry.yaml      # 0

# §8.1 — the abandoned design
grep -rn "glossary.entity_deleted" docs/03_planning/

# §8.2 — e.id updated ON CREATE, not ON MATCH
grep -n "ON CREATE SET" -A 12 services/knowledge-service/app/extraction/glossary_sync.py
grep -n "ON MATCH SET"  -A 10 services/knowledge-service/app/extraction/glossary_sync.py
grep -rn "insertEntityOutboxEvent" services/glossary-service/internal/api/kind_votes_handler.go

# §8.3 — the sweeper substrate that already exists
ls services/knowledge-service/app/jobs/ | grep -E "sweep|reconcile|cleanup|scheduler"

# §8.4 — restore and purge are silent too
sed -n '174,215p' services/glossary-service/internal/api/recycle_bin_handler.go

# §8.5 — the game-tier contract, unimplemented
grep -n "deleted\|status\|alive" contracts/api/glossary-service/seed_export.yaml   # expect: none
grep -rn "seed_export" services/glossary-service                                    # expect: none
```

---

## 11 · Prior art — read before designing

| doc | why |
|---|---|
| [`docs/analysis/2026-06-20-data-architecture-ssot/FINDINGS.md`](../../analysis/2026-06-20-data-architecture-ssot/FINDINGS.md) | **Found this exact gap 43 days before the lifecycle audit re-found it.** Its #1 is the missing delete event, its #2 is the stale `e.id` (§8.2 — still open, and no other document carries it), its #3 is the missing reconcile sweep. All three follow-ups were "suggested, not done" |
| `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` §3130 | the abandoned `handle_glossary_entity_deleted` spec — exact semantics, already reviewed |
| `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` §740, §753 | the dispatch-table entry and the no-cascade rule |
| `contracts/events/_registry.yaml` | the generator + gate the platform's 100 events are outside of; `canon.entry.decanonized` is the retraction shape to rhyme with |
| `contracts/api/glossary-service/seed_export.yaml` | the game-tier canon contract, still editable |

**The pattern across the first three rows is worth naming plainly.** This gap has been found three
times — 2026-06-20, 2026-08-01, 2026-08-02 — by three different investigations that did not know
about each other, and the *fix* was specified before the first of them. What is missing has never
been the analysis.
