# KG storage migration — port first, then engine

**Status:** 🔒 **SEALED 2026-08-09** — the *reasoning* is closed and must not be re-litigated from memory; re-read it. **All 30 opened questions are closed.** No code has changed. Decision register: [ARCHITECTURE-OVERVIEW §9](2026-08-09-ARCHITECTURE-OVERVIEW.md#9--sealed--decision-register). **Opened:** 2026-08-09 · **Branch:** `refactor/entity-lifecycle`
**Verified against:** `df18e9049`
**Decision this serves (PO):** migrate off Neo4j **before** the lifecycle/versioning refactor.

> **The premise, in the PO's words:** *"we don't use clean architecture or hexagon from the beginning
> and now we pay for it."* This plan treats that as the diagnosis. The migration is not primarily a
> database swap — it is **building the boundary that should have existed**, after which the swap is a
> configuration change and is reversible.

---

## 1 · Why the port comes first, and is not a detour

Measured at `df18e9049`:

| | |
|---|---|
| direct imports of `app.db.neo4j_repos` | **128**, across **67 distinct modules** |
| the abstraction's name | `neo4j_repos` · `neo4j.py` · `neo4j_helpers.py` · `neo4j_schema.py` — **engine-shaped** |
| raw Cypher **outside** the repo package | `context/selectors/salience.py` · `events/handlers.py` · `extraction/coref_detect.py` · `extraction/glossary_passage.py` · `db/neo4j_helpers.py` (+ migrations, benchmark) |

A repository layer exists and its functions are already **domain-shaped** — `find_entities_by_name`,
`get_neighborhood_by_glossary_id`, `archive_entity`, `status_at_order`. What is missing is an
**interface**: 67 modules bind to concrete functions in a vendor-named package, and Cypher has leaked
into the selectors, the event handlers and the extraction path.

**Migrating without extracting the port first would rewrite 67 modules against a second vendor and
re-buy the identical debt.** The port is what makes this migration — and every later one — cheap.

Three things the port buys beyond the migration itself:

1. **A fake adapter for tests.** knowledge-service today needs a live Neo4j to test the graph layer;
   it carries **561 skips** and `-n auto` is unsafe there.
2. **Shadow comparison.** Two adapters, same call, diff results and latency on real traffic — so the
   engine is chosen by measurement, per [`21`](../../03_planning/LLM_MMO_RPG/21_architecture_ceilings.md)'s discipline.
3. **Reversibility.** The graph is **derived and classified P2** (`SR06` — *"does not block active
   play"*), so rollback is "point the adapter back" and, worst case, rebuild from Postgres.

### 1.1 Two boundaries — one was built, one was not

| boundary | scope | state |
|---|---|---|
| **KAL / INV-KAL** | *cross-service* — who may touch the graph | ✅ exists, CI-gated, **zero allowlist** — but read-only, 18 of 204 routes |
| **Graph port** | *intra-service* — what knowledge-service depends on | ❌ **absent** — 67 modules bind to the engine |

The platform got the access-control half of the boundary and none of the substitutability half. This
plan builds the second half.

---

## 2 · The port

The failure mode to avoid: a port shaped like the engine. `run_cypher(query)` renames the coupling and
buys nothing. It must be **domain operations returning domain models** — which the repo functions
largely already are.

```
GraphStore      resolve_or_merge_entity · find_entities_by_name · project_entity_names
                neighborhood(entity, depth, filters) · relations_for(entity, as_of)
                most_connected · list_filtered · archive_entity / restore_entity
                status_at_order · merge_entity_status · list_gone
                events_in_window(after, before, axis) · facts_before(order)
                upsert_relation · evidence_for(fact) · entities_needing_embedding

VectorStore     search(scope, embedding, k, filter) · upsert(scope, id, embedding)
                ensure_index(scope, model, dim) · drop_index(scope)

OntologyStore   node_kinds · edge_types · vocab_sets · graph_schemas     (already Postgres)
```

> **Splitting `VectorStore` out of `GraphStore` is the highest-value line here.** It lets the vector
> layer migrate **independently of any graph decision** — and the vector layer is the part that is
> unambiguously broken at target scale (§3).

---

## 3 · Why the vector layer moves first, and separately

It is the only part where the current design has a hard ceiling rather than a preference:

| | |
|---|---|
| summary vector indexes | `summary_index_name(project_id, embedding_model_uuid, level)` — **one per tenant** → ~30,000 HNSW indexes at 10k projects |
| passage vectors at 10k books | ~63 M vectors ≈ **390 GB** @1536-dim fp32, ~780 GB @3072-dim |
| why the per-tenant index exists | Neo4j cannot **pre-filter** a vector search by tenant, so isolation is achieved by index-per-tenant — and that is the thing that does not scale |
| what the book-layer design needs | **as-of-filtered semantic search** — validity intervals live in `entity_facts` in **Postgres**; vectors in Neo4j cannot be filtered against them in one query |

Postgres pre-filters natively, and **pgvectorscale's StreamingDiskANN** keeps the index on disk
rather than in RAM — the CosmosDB property, under a Postgres OSS license.

**Version compatibility, verified 2026-08-09:** [pgvector 0.8.5 supports PG18](https://github.com/pgvector/pgvector);
[Apache AGE 1.7.0 supports PG18](https://github.com/apache/age/releases). **pgvectorscale's PG18
status is UNVERIFIED** — §7 makes checking it the first task, with plain pgvector HNSW as the fallback.

---

## 4 · Target engine — ⛔ **AGE ELIMINATED 2026-08-09 (M2 audit)**

> ### The audit that killed it
>
> §4's original case for AGE rested on **one** load-bearing claim: *"Cypher is preserved, so the
> adapter is a mechanical port of ~132 existing queries rather than a reimplementation."* A construct
> audit of `services/knowledge-service/app` falsifies it:
>
> | construct | uses | AGE |
> |---|---:|---|
> | **`datetime()`** | **152** (101 assignments · 51 comparisons) | ❌ **not supported** |
> | **`MERGE … ON CREATE SET / ON MATCH SET`** | 131 MERGE · 19 · 14 | ❌ **not supported — syntax error** |
> | `CALL { … }` subquery | 14 | ⚠️ unsupported / unverified |
> | `FOREACH` | 7 | ⚠️ unsupported |
> | `EXISTS { … }` | 2 | ⚠️ restricted to SQL subquery form |
> | `CALL db.index.vector.query` | 5 | ❌ — but these leave with P1 anyway |
> | `CALL … IN TRANSACTIONS` | 1 | ❌ |
>
> Sources: [apache/age#2323](https://github.com/apache/age/issues/2323) ·
> [AGE Cypher manual](https://age.apache.org/age-manual/master/intro/cypher.html)
>
> **`MERGE … ON CREATE SET / ON MATCH SET` is the fatal one** — it is the *core entity-anchoring
> pattern*. `glossary_sync` is exactly that shape. The primary write path does not port.
>
> **Consequence:** AGE requires a full query rewrite, so its single advantage over every other
> candidate evaporates. **AGE is out.** PG18 support and Apache-2.0 licensing were never the issue.
>
> **This is the port-first thesis vindicated.** Discovering `MERGE … ON MATCH SET` unsupported
> *mid-migration*, with 67 modules already re-pointed, would have been a catastrophe. With the port it
> is a data point that changes one adapter choice and nothing else.

### Revised: the choice is now Postgres-relational vs Kuzu, decided by shadow comparison

Since **no candidate preserves the Cypher**, the queries get rewritten either way — so pick on the
other axes:

| candidate | rewrite target | pros | cons |
|---|---|---|---|
| **Postgres relational** (edge tables, recursive CTE) | SQL | **one datastore** · no extension · mature planner · **full temporal support** (the `datetime()` problem disappears entirely) · partitioning + Citus · Patroni HA already present | loses graph ergonomics if density grows |
| **KuzuDB** | Kuzu Cypher | **MIT** · disk-based columnar · Cypher-shaped · vector + full-text search built in · **one DB file per project** — natural fit for 10k tenants, zero server ops. ✅ **Passes the test that killed AGE: `MERGE … ON CREATE SET / ON MATCH SET` is supported** | ❌ **`CALL { … }` subquery NOT supported (14 uses)**; subqueries limited to a single `MATCH` + optional `WHERE`. `datetime()` support **unconfirmed** — must be verified, it is what killed AGE. Young; embedded single-writer model needs checking against the write path |

**Recommendation: default to Postgres-relational**, because the strongest objection to it — *"you have
to rewrite 132 queries"* — is now true of **every** option, and Postgres is the only one where the
152 `datetime()` uses become *easier* rather than a porting problem.

**Before committing to Kuzu, run the same M2 construct audit against its dialect.** Failing to do that
for AGE is what produced this reversal.

### The original AGE case, retained for the record

**Apache AGE + pgvector/pgvectorscale, inside the Postgres you already run.**

| requirement | how it is met |
|---|---|
| no license wall (the PO's founding concern) | **Apache 2.0** — vs Neo4j Community GPLv3 whose only scale path is commercial Enterprise |
| disk-resident indexing | it is Postgres; plus StreamingDiskANN for vectors |
| 10k+ tenants | partition by `project_id`; **Citus** if one node is outgrown (shard key partitions cleanly at the storage layer — multi-project union is app-layer fan-out, not cross-project Cypher) |
| **migration cost** | **Cypher is preserved.** The adapter is largely a mechanical port of ~132 existing queries rather than a reimplementation — the single biggest cost reducer |
| operational floor for self-hosters | **one datastore**; one HA story (Patroni, already present); one backup path |
| as-of-filtered semantic search (D2) | vectors and `entity_facts` in the same database — one query |
| PG18 | AGE 1.7.0 ✅ |

**Honest weaknesses, recorded rather than argued away:**

- **Deep traversal is slower than a native engine.** Acceptable *here* because the workload is shallow:
  **2** variable-length patterns in the entire codebase, the deepest being `HAS_CHILD*..3` over the book
  hierarchy; **0** `shortestPath`; **0** APOC. If the relationship pipeline matures into genuine
  multi-hop, this is the assumption that breaks — and the port is what makes that recoverable.
- **AGE is less battle-tested than Neo4j**, and its openCypher dialect has gaps. §7 makes dialect
  coverage a gate, not an assumption.
- **Single-node.** Fine here: you need *partitioning*, not distributed traversal.
- **Packaging:** `postgres:18-alpine` does not ship AGE. A custom image (or `pgvector/pgvector:pg18` +
  AGE build) is required — a real, unglamorous task that belongs in P0.

**Documented fallbacks, reachable *because* the port exists:** pure relational edge tables (no
extension at all) per-operation where AGE's dialect bites; **KuzuDB** (MIT, embedded, disk, one DB file
per project) if per-tenant isolation or Cypher fidelity matters more than single-datastore simplicity.

---

## 5 · Phases

Each phase is independently valuable and independently revertible.

### P-0.5 · Ship the reported defect fix first *(added after the red team — RT-1)*

**Before any port work.** `state?as_of` over today's schema + AC1/AC2 conformance tests, and one
caller (composition's cast read) migrated onto it.

Justification: the substrate already works — `entity_facts` is bitemporal, `emitChapterFacts` writes
every attribute at its chapter ordinal, `maintain_chain` maintains pin-aware supersession, and the
as-of predicate is correct and index-served. **`composition-service` passes `as_of` zero times.** This
is days of work, no port work touches it, and it proves the read shape on real data before 22k LOC
move.

**Gate:** AC1 (dead at 41, **alive at 39**) and AC2 (as-of 30 returns exactly the chapter-25 values).
**Bite:** both must be **red before green** — a `deleted_at`-style implementation passes AC1's first
half and fails its second.

### P0 · Extract the ports — **sliced, each independently shippable** *(revised — RT-12)*

> **Why sliced.** A single 22,390-LOC substrate refactor with no user-visible change is the least
> defensible work to protect under pressure, and this repo has already demonstrated the failure mode:
> **the KAL was specified, contracted, gated — and reached 18 of 204 routes.** Each sub-slice below
> ships and is separately valuable.

0. **Pull the 5 Cypher-leakage sites** into the repo layer — `salience.py`, `events/handlers.py`,
   `coref_detect.py`, `glossary_passage.py`, `neo4j_helpers.py`. Nothing can be abstracted while
   Cypher lives in a selector. *(prerequisite for all of the below)*

| slice | scope | why this order | ships |
|---|---|---|---|
| **P0a · `VectorStore`** | search · upsert · ensure_index | carries the **only hard ceiling** (30k per-tenant indexes) and unblocks P1 | the vector layer becomes swappable |
| **P0b · `OntologyStore`** | kinds · edge types · vocab | **smallest (2.5k)** — proves the pattern cheaply, low blast radius | pattern validated |
| **P0c · `GraphStore`** | entities · relations · events · status | the bulk; unblocks P2 | engine becomes swappable |
| **P0d · `TruthStore`** | bitemporal facts · episodes · lifecycle | last — needs the identity question (O1) settled first | truth becomes routable by scope |

Each slice: adapter = existing code lifted **byte-for-byte**, plus a **fake adapter** — which attacks
knowledge-service's **561 skips** and makes `-n auto` safe there.

**Gate:** no `MATCH (` / `MERGE (` / `CREATE (` outside the adapter package. Same shape as the two
INV-KAL gates, same enforcement mechanism.
**Bite:** delete the adapter package and the gate must go red. A gate that cannot fail is decoration.

### P1 · Move the vector layer *(the real ceiling)*

1. `PgVectorStore` adapter — per-dim tables/partitions using the **closed dim set already in the code**
   (`SUPPORTED_PASSAGE_DIMS = 384, 1024, 1536, 2560, 3072`), tenant filtered in the planner.
2. **Dual-write** embeddings; **shadow-read** and compare.
3. Cut over. Drop the Neo4j vector indexes → the 30k-index ceiling disappears.

**Gate:** recall@k on the existing `flat_knn_rawsearch.py` harness — Neo4j HNSW vs pgvector vs
StreamingDiskANN vs halfvec, on the same corpus.
**Bite:** halfvec must measurably lose recall somewhere. If it never does, the harness is not measuring.

### P2 · Second graph adapter + shadow comparison

1. `AgeGraphStore` — port the Cypher (mechanical for most of it).
2. Shadow-read on real traffic: **both adapters, same call, diff results and latency.**
3. **Property-based differential suite** over the port — generate operations, assert both adapters
   agree. *(added — RT-9)*
4. Publish the comparison as a ceilings-style document — ratios not absolutes, rig stated, durability
   settings stated, per [`21`](../../03_planning/LLM_MMO_RPG/21_architecture_ceilings.md).

**Gate:** result-set equivalence per operation. Divergence is a blocker, not a note.
**Gate (added — RT-9): shadow-coverage floor — no cutover while any port operation has zero shadow
observations.** Shadow comparison only sees *executed* paths; merge, split, restore, coref repair and
triage are rare and would diverge silently. The graph feeds **canon checks**, so a silent divergence
becomes wrong prose rather than an error. Shape equality is not semantic equality — null ordering,
tie-breaking, isolation and index behaviour differ between engines while shapes match.

### P3 · Cutover

1. Flip the adapter by config; keep Neo4j readable for rollback.
2. Soak; then decommission.
3. Rebuild-from-Postgres is the standing DR story — available *because* the graph is derived.

---

## 6 · What this does NOT do

- **Does not change the KG's model, scope or purpose.** The knowledge graph is the platform's memory
  and knowledge substrate — global/project/session/turn scoping, L0–L3 retrieval, multi-project union,
  ontology, triage, salience — serving novel writing, translation, coding and general chat. Migration
  is a **storage** change, full stop.
- **Does not touch the lifecycle / story-status / versioning refactor.** That work resumes on top of the
  port. Note it gets *cheaper* afterwards: an `as_of` operation on `GraphStore` is one interface
  change, not 67.
- **Does not decide the graph engine irreversibly.** P2 decides it on measurement; the port keeps it
  reversible.

---

## 7 · Open — must be resolved before P1 lands

| # | question | why it blocks |
|---|---|---|
| ~~**M1**~~ | ✅ **RESOLVED 2026-08-09.** pgvectorscale **supports PG18** (`--pg18 pg_config`) and is **PostgreSQL-OSS licensed**. ⚠️ **Residual, still a gate:** no documented dimension ceiling for StreamingDiskANN, and your set includes **2560 / 3072**. pgvector's own HNSW caps at 2000 (`vector`) / 4000 (`halfvec`). **Verify before P1 commits** | P1 — mostly clear |
| ~~**M2**~~ | ⛔ **RESOLVED 2026-08-09 — AGE ELIMINATED, Kuzu audited.** AGE: `datetime()` (152) and `MERGE … ON CREATE/ON MATCH SET` (131/19/14) unsupported — the latter is the core anchoring pattern. **Kuzu passes that test** (MERGE with ON CREATE/ON MATCH is supported) but **fails `CALL { … }` (14 uses)** and its `datetime()` support is **unconfirmed**. Net: **AGE dead · Kuzu viable with ~14 rewrites + a datetime check · Postgres-relational carries no dialect risk at all** | P2 target changed |
| ~~**M8**~~ | ✅ **RESOLVED 2026-08-09 — YES, as `current_timestamp()`.** Kuzu ships `current_timestamp()` plus `TIMESTAMP` / `DATE` / `INTERVAL` (DuckDB-style). So the **152 `datetime()` sites are a mechanical rename**, not a blocker — the construct that killed AGE. **Kuzu's final scorecard: ✅ `MERGE … ON CREATE/ON MATCH SET` · ✅ temporal · ✅ vector + full-text built in · ✅ MIT · ❌ `CALL { … }` (14 sites need rewriting).** Net: **~14 real rewrites + 152 renames** — genuinely viable, and the P2 shadow comparison is now a real contest rather than a formality *(orig)* **Does Kuzu support `datetime()`?** The exact construct that killed AGE, and 152 sites depend on it. **Verify before Kuzu is shortlisted** — this is the one check whose omission produced the AGE reversal | P2 |
| ~~**M3**~~ | ✅ **RESOLVED 2026-08-09 — YES, committed.** `projects.embedding_model TEXT`, user-settable via `project_tools.py` / `build_tools.py`, plus `D-RERANK-NOT-BYOK` (per-project BYOK **rerank** model mirroring it). ⇒ the 30k-index figure stands and **tenant-filtered ANN is required, not optional** | P1 sizing confirmed |
| ~~**M4**~~ | ✅ **DECIDED 2026-08-09 — publish a prebuilt image and own the extension matrix.** The alternative (every self-hoster compiles pgvector + pgvectorscale) destroys the operability argument that motivated leaving Neo4j in the first place. **Cost accepted and stated:** you own a Postgres distribution, its CVE cadence, and a 2–3 extension upgrade path. *(AGE is no longer in the matrix — see §4.)* *(orig)* **AGE + pgvector(+scale) in one image on PG18 — and who owns it?** *(RT-4)*. Today a self-hoster runs `docker compose up` and gets a working Neo4j; after this they need a **bespoke image with 2–3 compiled extensions, version-pinned together**. Publishing a prebuilt image reduces but does not remove it — you then own a Postgres distribution, its CVE cadence, and a 3-extension upgrade path. **The founding argument for this migration was open-source operability; this is the place it can invert** | belongs in P0, not discovered in P2 |
| ~~**M5**~~ | 🔴 **RESOLVED 2026-08-09 — WORSE THAN STATED. It does not exist.** There is **no rebuild-from-Postgres path at all**: the only sweepers in `app/jobs/` are `reconcile_evidence_count` (a counter reconciler) and `stats_updater`. So this is not *"never exercised"* — **there is nothing to exercise.** And for vectors it is not a rebuild at all but **re-embedding ~63 M passages — an LLM budget event** *(RT-3)*. Three claims depend on it: graph HA is unnecessary, P3 rollback, DR | **must be BUILT before P3 can claim a rollback** |
| ~~**M6**~~ | ✅ **SEALED 2026-08-09 — DURABLE PRIMARY DATA, BACKED UP.** Vectors are restored, never recomputed. **The decisive argument is BYOK:** embedding models are per-project and user-keyed (`projects.embedding_model`, `D-RERANK-NOT-BYOK`), so re-embedding after a DR event **spends the user's API budget without consent** — that is billing someone else for your outage, not a recovery procedure. Consequences: vector backups sized for ~390–780 GB at 10k books; **P3 rollback and DR must restore vectors, not regenerate them**; and the *"derived, therefore free to rebuild"* claim now applies to the **graph only**, never to embeddings | ✅ decided |
| ~~**M6-orig**~~ | *(superseded)* **Embedding durability — decide explicitly** *(RT-3)*. Vectors are either **(a)** durable primary data with real backups, or **(b)** recomputable with a **stated cost and time budget**. *"Derived, therefore free to rebuild"* is true for the graph and **false for embeddings**; the plan currently treats them identically | **blocks P1** |
| ~~**M7**~~ | ✅ **RESOLVED 2026-08-09 — two numeric triggers, both automatable as gates.** Re-open the graph-engine choice when **EITHER** (a) **p50 entity degree ≥ 3** — it is **0** today (p95 = 2, p99 = 10, max = 189), so the graph is currently a list with occasional links; **OR** (b) **any production query needs variable-length `RELATES_TO` traversal beyond depth 2** — today there are **2 variable-length patterns in the entire codebase** and the deepest is `HAS_CHILD*..3` over the *book hierarchy*, not the entity graph. Both are one query to check and belong in the same CI job as the other gates. **Rationale:** the current shallow workload is the stated reason a relational adapter suffices, and that workload is shallow partly *because relationship extraction is immature* (3 of 8 proposed edges defensible). These triggers convert an implicit assumption into a tripwire | ✅ trigger set |
| ~~**M7-orig**~~ | *(superseded)* **What re-opens the engine choice?** *(RT-8)*. AGE is accepted partly because the workload is shallow — but it is shallow *because relationship extraction is immature* (3 of 8 proposed edges defensible). That is the flattering-number trap in another costume. State a **numeric trigger** (e.g. *"median entity degree > N ⇒ re-open"*) rather than leaving the assumption implicit | P2 exit |
