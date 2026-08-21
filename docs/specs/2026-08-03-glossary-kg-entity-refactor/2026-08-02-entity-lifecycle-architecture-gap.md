# There is no entity lifecycle

**Status:** INVESTIGATION COMPLETE · 2026-08-02 · input to the glossary↔KG entity-consistency refactor
**Tracked in:** [`README.md`](README.md) — the refactor's index and deferral register. There is
**no design yet**; this document is one of its three inputs.
**Verdict:** this is not a missing `WHERE` clause. It is a **missing concept**, and every layer
invented its own private substitute.

---

## 1. The thesis

Ask the system "is this entity gone?" and four services answer with four different columns that
have never been introduced to each other:

| layer | its notion of "gone" | who honours it |
|---|---|---|
| glossary-service | `glossary_entities.deleted_at` | ~40 of its own reads · **nothing outside the service** |
| glossary-service | `glossary_entities.status` (`draft`/`active`/`inactive`/`rejected`) | **4 call sites**, all wiki-gen / translation-glossary / export |
| glossary-service | `glossary_entities.alive` | **2 reads** — and it is a *narrative* flag (the character died in-story), not a lifecycle one |
| knowledge-service | `:Entity.archived_at` (Neo4j) | 38 retrieval sites — **and glossary's delete never sets it** |
| translation-service | `chapter_translations.is_glossary_stale` | the Coverage UI — **and a delete never raises it** |

No column is authoritative, none of them agree, and no event connects any two of them.

**The single most compact statement of the defect:**

```
grep -rn "deleted_at|entity_deleted" services/knowledge-service/app  →  0 occurrences
```

The knowledge layer has never heard of glossary deletion. Not "handles it badly" — has never
been told the concept exists.

### How it happened

KAL (the knowledge/graph layer) was built **after** glossary, against a glossary that already
had `deleted_at`, and nobody wrote down what an entity's lifecycle IS. So KAL invented
`archived_at` for its own needs (the FE "archive this KG entity" button), and the two flags grew
up as strangers. The same is true one layer further out: translation-service invented
`is_glossary_stale`, and composition-service denormalised `entity_name` into its own table.

Each of those was a locally reasonable decision. The defect is that **no layer was ever told
what the layers below it mean by "this entity is gone"**, so each answered the question itself.

### Why this is a game-tier problem, not a glossary-tier one

The game reads canon. An entity that the author deleted but which the graph still serves as
`canonical` is not a cosmetic bug — it is **the game generating narrative from lore its author
retracted**, with no surface anywhere that says so. At 4,000 chapters and several enrichment
layers, a wrong retraction propagates into world state, NPC memory and quest text, and there is
no mechanism that would ever pull it back.

---

## 2. Provenance of the findings below

Verified **directly, by the session author**, by reading the code and querying the live dev
stack: everything in §3.1, §3.2 and §3.5, plus the four ranked symptoms in §4.
Contributed by four read-only audit agents over disjoint service trees and then spot-checked on
the load-bearing claims: the exhaustive per-call-site tables in §3.3 and §3.4.

Where a claim was NOT independently re-verified it is marked ⚠.

---

## 3. The audit

### 3.1 The root-cause pair inside glossary-service

Two near-identical guards, one correct:

```go
// entity_genres_handler.go:37   ← WRONG
SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)

// pipeline_read_tools.go:104    ← RIGHT ("reports whether a LIVE entity belongs to the book")
SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)
```

The wrong one guards **canonical-translation, fold, append-fact, split-entity** and two MCP genre
tools. Concretely: `internalGetCanonicalTranslation` passes that guard, then reads
`short_description` at `canonical_translation_handler.go:51` with no lifecycle filter, then fires
a **real, paid LLM translation call** and persists the result into
`canonical_snapshot_translations`. Deleted content → billed generation → a cached artifact.

**A second, subtler one:** soft-delete emits nothing, but **editing after deletion does**.
`apply_edit_handler.go:126` locks the row without `deleted_at`, so a trashed entity is still
editable; the edit then emits `entity_updated` whose payload comes from `outbox.go:394`
(`WHERE e.entity_id = $1`, no filter at all), carrying name/aliases/short_description.
knowledge-service re-embeds it. **The deletion is silently reversed in the consumer's index.**

**Good news, verified:** `findEntityCrossKind` (`extraction_handler.go:1548`) DOES filter
`deleted_at IS NULL`. A trashed entity cannot be resurrected as a dedup target. This was the
scariest hypothesis and it is false.

### 3.2 `status` is very nearly decorative

Exhaustive grep on `glossary_entities`. `status = 'active'` matches **13 lines in 9 files** — the
raw count, so the command in §7 and this section agree. Broken down:

| the 13 lines | what they are |
|---|---|
| `knowledge_client.go:411`, `:451` · `wiki_handler.go:1064` · `server.go:711,718,727,784` · `export_handler.go:222` | **the 8 lines that actually gate an entity read** — wiki-gen delegate, wiki stubs, the four `translation-glossary` CTE tiers, export. **4 functional call sites.** |
| `attr_value_items.go:219` · `migrate/multirow_attr_values.go:48` | a **different table** — `entity_attribute_value_items.status` (per-item tombstones). Not entity lifecycle at all. |
| `self_entity_handler.go:124` | a WRITE (`SET status='active'` when claiming the self-entity) |
| `entity_handler.go:1242` · `extraction_handler.go:275` | comments |

The comment at `extraction_handler.go:273` is worth quoting in full, because it is this codebase
already having learned the lesson once, in one place:

> *"Never surface soft-deleted entities. Soft-delete is a pure `SET deleted_at` (it leaves
> status/alive untouched and does NOT cascade chapter_entity_links), so without this a deleted
> `status='active'` entity still passes the frequency HAVING — and the W11-M3 public lore route
> would serve author-removed content to anonymous readers."*

Whoever wrote that understood the exact defect, fixed it **at that one call site**, and had no
place to write down the general rule. That is what §5 is for.

- `status <> …` / `status NOT IN …` on entities: **zero occurrences in the entire service.**

So setting an entity to `rejected` removes it from wiki generation and the translation glossary
**and nothing else**. It is still injected into LLM context every turn, still offered as an
enrichment target, still translated, still folded into canon, still exported to
knowledge-service for embedding.

`PATCH /entities/{id}` sets `status` and `alive` as **unlinked** fields — marking `rejected`
does not set `alive=false` and does not set `deleted_at`. The codebase has already recorded this
exact failure once, at `extraction_handler.go:246`: *"`status` was accepted by every caller …
but NEVER read here — a write-only parameter that silently lied."*

**Answer to "is there a status that removes an entity from every pipeline?" — No. There is not.**

### 3.3 knowledge-service: one safe path, everything else reads Neo4j directly ⚠

`select_glossary_semantic` (`context/selectors/glossary.py:294`) is the **only** entity path that
re-consults glossary. It vector-searches Neo4j, then calls `fetch_entities_by_ids`, and glossary
drops the trashed row → `if r is None: continue`. Safe by construction; it merely **wastes** a
top-N slot per trashed hit.

Every other path reads `:Entity` node properties and filters on `archived_at`, which glossary
never sets. And `Entity.status` is a **derived** projection (`entities.py:163`):

```python
if self.archived_at is not None:        return "archived"
if self.glossary_entity_id is not None: return "canonical"
return "discovered"
```

A trashed glossary entity still has `glossary_entity_id` set and `archived_at` NULL, so it reads
as **`canonical`**. It is not merely present — it is badged as canon.

Leaking paths (each returns entity name/aliases/relations for a trashed entity):

| path | filter it actually applies |
|---|---|
| `context/anchors.py:152` → `list_project_entity_names` (`entities.py:889`) | `archived_at IS NULL` only |
| `context/anchors.py:203` → `get_most_connected_entity` (`entities.py:928`) | `archived_at IS NULL` only |
| `context/selectors/facts.py:146` → `find_entities_by_name` (`entities.py:968`) | `archived_at IS NULL` only |
| `context/selectors/facts.py:281/305` → `find_relations_for_entity` (`relations.py:525`) | `peer.archived_at IS NULL` |
| `entities.py:2165` `get_entity_with_relations` · `:2282` `get_neighborhood_by_glossary_id` | **no lifecycle filter at all** |
| `entities.py:2005` `list_entities_filtered(status="canonical")` | `archived_at IS NULL AND glossary_entity_id IS NOT NULL` — a trashed entity matches *exactly* |
| `routers/public/entities.py:471 / :558 / :695` (Entities tab, semantic search, detail) | node props |
| `routers/internal_wiki.py:147` `/wiki-neighborhood` · `:228` `kg-hashes` | node props |
| `tools/executor.py:551` `memory_recall_entity` | node props |
| `mcp/server.py:2017` resource `knowledge://project/{id}/entities` | via `list_entities_filtered` |
| `routers/public/graph_views.py:597` graph · `:698` edge timeline | `:698` has no archived filter at all |
| `wiki/context.py:120` `gather_kg_facts` | subject is protected; **neighbours are not** |

And on the status half: `extraction/anchor_loader.py:72` defaults `status_filter=None`
**deliberately** — the comment explains that defaulting to `'active'` would stop anchoring draft
entities and mint duplicates. Correct for its purpose, and it means every `draft`/`inactive`/
`rejected` entity is MERGEd into Neo4j at `anchor_score=1.0` as canonical.

**Cost, not correctness:** `entities.py:1490` `find_entities_needing_embedding` keeps paying to
re-embed trashed entities forever, which keeps them competing for the top-N slots that
`select_glossary_semantic` then discards.

### 3.4 Consumers hold STALE COPIES — the genuinely dangerous shape ⚠

A local copy is filtered correctly *at write time* and then served forever.

**① Translation force-substitutes a deleted entity's term into output text.**
`decoupled_block_translate.py:243` freezes `glossary_prompt_block` **and**
`glossary_correction_map` into `chapter_translations.resume_state` (JSONB), fetched once per
chapter. Later batches re-read them: `:112` splices the block into the system prompt as
*"you MUST use the EXACT translations provided"*, and `:345` runs `auto_correct_glossary`
(`glossary_client.py:583`), which is a blind global replace — verified:

```python
result = result.replace(source_zh, target)
```

Translation jobs are **pausable** and re-driven by a sweeper, so this window is not seconds.
*Observed:* delete a character, resume a paused job → the deleted name is still a mandatory term
in every remaining block, and every occurrence of the source term in the model's output is
silently rewritten to the deleted entity's translation.

**② "The entity I deleted keeps coming back."** Verified: `extraction_worker.py:472` fetches
`known_entities` **before** the chapter loop (`for idx, chapter_id_str in enumerate(chapter_ids)`),
comment and all: *"Fetch **initial** known entities"*. A book-wide job holds that list for its
whole lifetime. Delete a junk entity mid-run and every remaining chapter still lists it under
"known entities", the model keeps re-emitting it, and the writeback re-creates it.

**③ Deleting marks nothing stale.** `glossary_consumer.py:34` subscribes to `entity_updated`
only, so `is_glossary_stale` stays `false`. Delete an entity whose bad translation is baked into
300 chapters and the Coverage screen reports **0 stale / nothing to re-translate**.

**④ Composition puts a deleted character's NAME into the drafting prompt with no glossary read
at all.** `voice_profile.entity_name` is denormalised and looked up by
`WHERE project_id = $1 AND entity_id = ANY($2)` (`style_voice.py:159`) against
composition's own `outline_node.present_entity_ids`. The bio correctly vanishes from `<present>`;
the voice directive keeps steering every generated scene.

**Clean:** `ai-gateway` and `api-gateway-bff` hold no entity data (catalog cache / dumb proxy).

### 3.5 The mechanism that was built for exactly this, and never wired

`services/knowledge-service/app/db/neo4j_repos/entities.py:1113`:

```python
async def archive_entity(session, *, user_id, canonical_id, reason):
    """Soft-archive an entity (KSA §3.4.F glossary-deletion path)."""
```

Verified: it preserves every `EVIDENCED_BY`/`RELATES_TO` edge and the timeline, changes only
`archived_at`, `anchor_score → 0`, `glossary_entity_id → NULL`; `archived_at IS NULL` is honoured
at **38 sites**; `restore_entity` exists as its inverse; and its only non-test caller is
`user_archive_entity(reason='user_archived')` — a *different* function for the FE panel.
`reason='glossary_deleted'` is named in its own docstring and **has only test callers.**

The glossary-deletion path was designed, implemented, and never connected to a trigger.

**Two traps the merge flow already solved and a delete flow must solve again** (⚠ from the audit,
mechanism spot-checked):
1. **Archive is not a tombstone.** Merge writes the loser's names into `entity_alias_map` so
   re-extraction routes to the winner. An archived node has `glossary_entity_id = NULL` and will
   be re-matched **by name** on the next extraction and resurrected. A delete has no winner —
   unless the operation is "retire two, create one", where the new entity IS the winner.
2. **Restore is not symmetric.** `archive_entity` zeroes `anchor_score`; `restore_entity`
   deliberately does not recompute it. Restoring from trash must re-anchor, not just clear
   `archived_at`.

### 3.6 The event surface has no SoT ⚠

`contracts/events/_registry.yaml:3` declares itself *"AUTHORITATIVE list of every event_type
emitted by LoreWeave services"* and contains **zero** `glossary.*` entries. The real list is a Go
`const` block (`outbox.go:45,51,530`): `entity_updated`, `entity_merged`, `name_confirmed`. Every
consumer hand-mirrors those strings, with no generator and no drift gate. Adding
`glossary.entity_deleted` therefore forces a scope decision: register it **and** backfill the
three existing ones, or accept that glossary stays outside the SoT — but do not half-register.

---

## 4. Ranked by how often a user actually hits it

1. **Ghost canon.** Every chat turn naming the entity: the `<glossary>` block correctly omits it
   (that path re-consults glossary) while the `<facts>` block renders
   `DeletedName — allied_with — Other` (that path does not). **Two blocks of the same prompt
   contradict each other.**
2. **The anchor dictionary keeps the name and aliases** (`anchors.py:152`, 300 s TTL), so the
   entity is anchored even when the classifier would not have — which then feeds ①.
3. **The Entities tab still lists it, badged ⭐ canonical, with a working detail page.**
4. **Translation force-substitutes its term** into output text on a resumed job (§3.4①).
5. **"It keeps coming back"** — extraction re-creates it mid-job (§3.4②).
6. **Wiki articles cite deleted neighbours** — and a published article is hard to unpublish.
7. **`memory_recall_entity` returns `found: true`** to any agent that asks.

---

## 5. What the refactor has to decide

This document deliberately stops short of a design. The refactor must first answer:

1. **What ARE the states?** Proposed minimum: `draft → active → retired → trashed → purged`,
   with `retired` meaning *"keep it, stop using it"* — the state the product needs today and
   does not have. `alive` is orthogonal (narrative death) and should be renamed to say so.
2. **Which states are load-bearing where?** A single table: state × consumer × behaviour. Today
   that table would be almost entirely blank, which is the whole finding.
3. **How does a state change TRAVEL?** An event with a real SoT entry, or a reconcile sweep, or
   both. Merge proves the event path works end-to-end; there is no reconcile sweep anywhere.
4. **What is the anti-resurrection rule?** Extraction re-creates by name. Any retirement needs a
   tombstone, and the PO's "retire two, create one" shape gives it a natural redirect target.
5. **Who owns the lifecycle?** glossary is the authored SSOT; KAL is derived. A derived layer
   inventing its own lifecycle flag is the bug — `archived_at` should be a *projection* of the
   authored state, not a peer of it.
6. **What proves it?** A conformance test per consumer: trash an entity, assert it is absent
   from that consumer's output. Written once, run for every consumer, red before green.

---

## 6. Deferred items this subsumes or opens

| id | what | gate | trigger |
|---|---|---|---|
| **D-ENTITY-LIFECYCLE** | this document — the whole gap | #2 large/structural | the glossary↔KG refactor |
| **D-KG-KIND-FACETS** | knowledge-service mirrors one `kind_code TEXT NOT NULL`, so the graph cannot filter on the facets shipped 2026-08-02 (`kind_labels`) | #1 out of scope — cross-service contract | the same refactor, which re-cuts this seam |
| **D-ENTITY-EXISTS-GUARD** | `entityExistsInBook` lacks `deleted_at`; 6 generation paths depend on it | **fix now**, one line — 🔴 **STILL OPEN** | — |
| **D-KNOWN-ENTITIES-PER-JOB** | extraction holds `known_entities` for a whole job | **fix now** — 🔴 **STILL OPEN** | — |
| **D-OUTBOX-PAYLOAD-TRASH** | `outbox.go:394` re-publishes a trashed entity on edit | **fix now** — 🔴 **STILL OPEN** | — |
| **D-GLOSSARY-EVENTS-NO-SOT** | three `glossary.*` events exist outside `contracts/events/_registry.yaml` | #2 large/structural | adding any new glossary event |

The three **fix-now** rows are deliberately not deferrals: each is a single-file change with a
clear root cause, and CLAUDE.md's defer-gate says writing the row would cost more than the fix.

> **CORRECTION 2026-08-03.** This paragraph originally ended *"They are listed here only so the
> refactor knows they were already closed."* **That was false, and it was the only record of
> them.** Re-verified at `24dd7bdac`: `entity_genres_handler.go:40` still has no
> `deleted_at IS NULL`; `extraction_worker.py:473` still fetches `known_entities` before the
> chapter loop at `:556`; `outbox.go:398` still selects `WHERE e.entity_id = $1` with no
> lifecycle filter. Declaring them *not deferrals* meant no row was written anywhere, so a
> sentence asserting closure was the whole tracking mechanism — the exact prose-only failure
> CLAUDE.md's deferral rule exists to kill. They are now carried in
> [`README.md` §3](README.md#-three-bugs-this-folders-own-spec-records-as-closed-and-which-are-open)
> **as fix-now, not as deferrals.**

---

## 7. Reproduce every headline claim (so the next session does not re-investigate)

Line numbers below are as of **`00c8291c2`** (2026-08-02). They rot; the greps do not — each
command re-derives its claim from scratch. Run from the repo root.

```bash
# The one-line thesis: the knowledge layer has never heard of glossary deletion. Expect 0.
grep -rn "deleted_at\|entity_deleted" services/knowledge-service/app --include=*.py | wc -l

# The root-cause pair — one guard filters lifecycle, its twin does not.
grep -rn "func (s \*Server) entityExistsInBook" -A 7 services/glossary-service/internal/api/
grep -rn "func (s \*Server) entityBelongsToBook" -A 7 services/glossary-service/internal/api/

# ...and everything the broken one guards.
grep -rn "entityExistsInBook\|entityInBook" services/glossary-service/internal/api/*.go | grep -v _test

# `status` is decorative: a handful of `= 'active'`, and NOTHING ever excludes rejected/inactive.
grep -rn "status *= *'active'" services/glossary-service/internal --include=*.go | grep -v _test
grep -rnE "status *(<>|!=) *'|status NOT IN" services/glossary-service/internal --include=*.go | grep -v _test
#   ^ the second command must return nothing about `glossary_entities`.

# `alive` is honoured in exactly two reads, and is a NARRATIVE flag.
grep -rn "alive" services/glossary-service/internal/api/*.go | grep -v _test | grep -i "alive *= *true\|alive=true"
grep -n "Narrative-level alive flag" -A 4 services/glossary-service/internal/migrate/migrate.go

# The archive mechanism that exists and is unwired: only test callers for reason='glossary_deleted'.
grep -rn "archive_entity" services/knowledge-service --include=*.py | grep -v "def archive_entity" | sed 's/:.*//' | sort | uniq -c
grep -rn "archived_at IS NULL" services/knowledge-service/app/db/neo4j_repos/*.py | wc -l   # ~38

# KG Entity.status is DERIVED — a trashed entity reads as `canonical`.
sed -n '160,172p' services/knowledge-service/app/db/neo4j_repos/entities.py

# Translation freezes the glossary block, and auto-correct is a blind global replace.
grep -n "glossary_prompt_block\|glossary_correction_map" services/translation-service/app/workers/decoupled_block_translate.py
grep -n "def auto_correct_glossary" -A 30 services/translation-service/app/workers/glossary_client.py | grep "replace"

# Extraction fetches known_entities ONCE per job, before the chapter loop.
grep -n "known_entities = await fetch_known_entities" -B 2 services/translation-service/app/workers/extraction_worker.py
grep -n "for idx, chapter_id_str in enumerate" services/translation-service/app/workers/extraction_worker.py
#   ^ the fetch line number must be SMALLER than the loop line number.

# The events SoT does not know glossary exists.
grep -c "glossary\." contracts/events/_registry.yaml        # expect 0
grep -rn "glossary\.entity_" services/glossary-service/internal/api/outbox.go
```

Live-stack figures, measured **2026-08-02** against the dev Postgres (`localhost:5555`) and Neo4j
(`localhost:7688`). They are a snapshot of one machine, not invariants — re-run before quoting.

```sql
-- glossary: the four states, and how many are also trashed
SELECT status, count(*), count(*) FILTER (WHERE deleted_at IS NOT NULL) AS trashed
FROM glossary_entities GROUP BY 1;
--  draft 6364 (22) · active 913 (8) · rejected 10 (0) · inactive 3 (3)

-- `alive` has never been used for anything
SELECT alive, count(*) FROM glossary_entities GROUP BY 1;      -- true: 7290, false: 0

-- purge is ALSO a soft flag; there is no hard DELETE outside the self-entity reset
SELECT column_name FROM information_schema.columns
WHERE table_name='glossary_entities' AND column_name LIKE '%delet%';
--  deleted_at, permanently_deleted_at
```

```cypher
// KG: how many nodes are anchored to glossary at all (the blast radius)
MATCH (e:Entity) WHERE e.glossary_entity_id IS NOT NULL RETURN count(e);   // 5761 of 6274
```

**A warning about a test that looks decisive and is not.** "Do trashed glossary entities have a
Neo4j node?" answered **0/33** on this machine — which proves nothing: 27 of those 33 were
trashed *by a merge* (which does propagate and hard-deletes the loser), and the other 6 belong to
books that were never synced. Verify with:

```sql
SELECT count(*) FROM glossary_entities e WHERE e.deleted_at IS NOT NULL
  AND EXISTS (SELECT 1 FROM merge_journal m WHERE m.loser_entity_id = e.entity_id);   -- 27 of 33
```

The decisive experiment, if one is ever needed, is a controlled one: take a **live** entity that
has a Neo4j node, trash it through the API, and re-run a context selector. Nobody has run it —
the finding here rests on reading the code paths, which is why §3.3 is marked ⚠.

## 8. Scope of this audit — what was NOT looked at

Stated so a future session knows where the map ends rather than assuming it was covered.

**Audited:** glossary-service (all ~40 reads of `glossary_entities`), knowledge-service (context
modes, selectors, Neo4j repos, MCP tools, public routes, retrieval), translation-service,
chat-service, composition-service, ai-gateway, api-gateway-bff.

**NOT audited:**
- **The game tier** — `game-server`, world/travel/tilemap, and anything in the LLM_MMO_RPG track.
  This is the most important gap, because it is where the consequences are worst. If the game
  reads canon through knowledge-service it inherits every leak in §3.3 unchanged; if it has its
  own copy, that copy has never been examined.
- **The frontend**, beyond the glossary feature folder. Other panels may render entity data from
  their own caches.
- **enrichment-service / learning-service / usage-billing** and the remaining services of the 47
  — none was opened. They were judged unlikely to hold entity copies; that judgement was not
  tested.
- **Neo4j-side orphans other than `:Entity`** — `Event`, `Fact` and `Passage` nodes referencing a
  trashed entity were not traced.
- **Historical data damage.** No one has measured how many *currently published* wiki articles or
  translated chapters already contain a retracted entity. That number is the real cost and it is
  unknown.

## 9. What was NOT found (stated so the absence is on the record)

- `findEntityCrossKind` does **not** resurrect trashed entities — it filters correctly.
- `ai-gateway` and `api-gateway-bff` hold **no** entity data.
- Neither the retrieval/RAG passage path nor the fact/episode store reads entity records.
- "Purge" from the recycle bin is `permanently_deleted_at = now()`, another soft flag — there is
  no hard `DELETE` of an entity anywhere outside the self-entity reset. Reads that filter
  `deleted_at IS NULL` therefore exclude purged rows transitively; this is correct, not a gap.
