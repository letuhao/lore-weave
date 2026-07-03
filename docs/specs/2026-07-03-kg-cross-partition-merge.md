# Spec — KG Track B B1(4): Cross-Partition Entity Merge (cross-book unification)

**Status:** DESIGN — PO-signed-off (Q1=b, Q2=ephemeral-first, Q3=pairwise). Ready to build T0.
**Date:** 2026-07-03
**Track:** KG Architecture — Track B (agent multi-KG), item B1(4)
**Predecessors (shipped):** B1(1) `kg_world_query` (`487f78c9c`), B1(2) multi-KG chat-session context union (`5dfcd9460`), B1(3) `kg_multi_query` (`da60f8085`).
**Plan:** [`2026-07-03-kg-architecture-schema-authoring-multi-kg.md`](../plans/2026-07-03-kg-architecture-schema-authoring-multi-kg.md) §Track B B1 option 4.

---

## 1. Problem

`kg_world_query` / `kg_multi_query` today return a **forest of per-book islands**:
`get_world_subgraph` (`app/db/neo4j_repos/relations.py:1136`) loops the member `project_ids`,
runs an isolated per-partition `get_project_subgraph`, tags each node with `source_project_id`,
and unions the results. Because a KG node's `id` is `entity_canonical_id`, which **folds
`project_id` into the SHA-256 hash** (`sdks/python/loreweave_extraction/canonical.py:172`),
the same real entity — "Alice" in the canon book and "Alice" in a side-story — hashes to **two
different node ids**. So there is no edge between them; a cross-book graph is disconnected by
construction (the docstring at `relations.py:1156` states this is deliberate — "world-core
territory").

**Goal:** recognize when the same real entity appears across ≥2 of a user's owned partitions and
**unify** them, so the agent gets a *connected* cross-book graph for synthesis (recurring
characters, cross-book relationships) — **and** surface where the books disagree, without silently
asserting a wrong identity.

## 2. Non-goals (this epic)

- **Cross-owner unification.** Owner-only, like B1(1)–B1(3). Grant-gated cross-tenant merge is a
  separate epic.
- **Rewriting the stored graph.** No `DETACH DELETE`, no new canonical ids written, no migration in
  the shippable tiers (T0–T2). Unification is **computed, not committed**. (A persisted substrate is
  T3, explicitly re-decided later.)
- **Automatic destructive merge.** The existing `merge_entities` (`entities.py:2488`) collapses two
  entities and deletes the source; we do **not** invoke it cross-partition. Over-merge is the whole
  risk that made this "design-first" — so we **propose with confidence, never assert**.

---

## 3. Grounding (what exists — verified 2026-07-03)

| Fact | Location | Consequence for design |
|---|---|---|
| Node `id` folds `project_id` into the hash | `canonical.py:172` | Same entity ≠ same id across books → the forest. Unification must be app-side, keyed on **content** (vector/name), not id. |
| Per-entity cosine embeddings + 4 vector indexes (`entity_embeddings_{384,1024,1536,3072}`) | `neo4j_schema.cypher:212`; `entities.py:80` | Semantic similarity is **buildable now** — the index infra exists. |
| Embeddings exist **only for anchored** entities (`glossary_entity_id IS NOT NULL`) | `entity_embedder.py`; `entities.py:1250` | **Discovered** cross-book characters carry **no vector** → must fall back to name/alias. This is the key limitation (see §7 Open Q1). |
| `find_entities_by_vector` (query-vector KNN, filters `user_id`, optional `project_id`) | `entities.py:1085` | Reuse the index, but **no entity↔entity cross-project KNN exists** → build one new query. |
| Cross-model cosine is meaningless (`embedding_model` must match) | `entities.py:1120` | **Model-space gate**: never compare vectors across differing `embedding_model`. |
| Rich name normalizer `canonicalize_entity_name` (NFKC + casefold + CJK fold + honorific strip) | `canonical.py:76` | The name/alias fallback should use THIS, not B1(2)'s plain `lower()`. |
| `merge_entities` = rehome edges/facts → `DETACH DELETE` source; same-partition; **no kind-gate**; refuses on `glossary_conflict` | `entities.py:2488` | The durable-merge mechanic to reuse **only in T3**; kind-gate is **absent** and must be added. |
| `kind` is a plain `:Entity.kind` property (no per-kind label), folded into the id hash | `canonical.py:172` | Kind-gate = compare `e.kind`. Cheap. |
| BYOK reranker (`RerankerClient.rerank(query, docs, …)`) is generic, cross-partition-usable, not wired to the graph path | `clients/reranker_client.py:53` | Available for T4 cluster/edge ranking; degrade-safe. |
| Salience is **per-(user,project)-normalized**; no cross-project renormalization (B1(2) compares per-project scores directly) | `selectors/salience.py:64` | Inherited asymmetry → T4 addresses; T0–T2 document it. |
| **No** `SAME_AS`/`MERGED_INTO`/`ALIAS_OF` Neo4j edge; **no** cross-project alias/identity store; **no** conflict/contradiction model (only temporal supersession + `glossary_conflict` guard + an LLM prompt hint) | grep-confirmed absent | Bridge edges + disagreements are **greenfield**; we introduce them as **ephemeral result-only** constructs (T0–T2), not stored graph. |
| `SubgraphNode` is a lightweight 6-field projection (no aliases/embedding) | `relations.py:809` | The unifier needs the **full `Entity`** (`entities.py:83`) — a supplementary detail/vector fetch per seed, not the lightweight node. |
| `get_project_subgraph` binds BOTH `$user_id` AND `$project_id`; no cross-partition Cypher anywhere | `relations.py:1028` | **Preserve this**: keep per-partition reads isolated; unify in Python. Never issue a cross-partition Cypher (tenancy invariant the whole file relies on). |

---

## 4. Approach (the design)

A **query-time unification pass** layered *over* the existing per-partition forest, in application
code (never a cross-partition Cypher). Pipeline:

```
resolve owner-owned partitions        (unchanged — the tools already do this)
  └─ per partition: get_project_subgraph  → forest nodes + intra-project edges (unchanged)
  └─ per partition: load seed entity DETAILS (name, canonical_name, aliases, kind,
       embedding_{dim}, embedding_model, glossary_entity_id)   ← NEW supplementary fetch
UNIFY (app-side):
  1. bucket seeds by kind          (EC-M3 kind-gate: only same-kind can merge)
  2. within a kind, find cross-partition matches:
       a. SEMANTIC: (Q1=b) first embed unembedded/discovered seeds ON DEMAND under the
          partition's anchored embedding_model (§7.1, in-memory-only, spend-capped), then
          PAIRWISE COSINE **in Python** over all seed vectors
          (bucketed by kind AND embedding_model); a pair matches when cosine ≥ τ_sem.
          The seed set is bounded (≤ SUBGRAPH_MAX_NODE_CAP per partition, already loaded),
          so this is an O(Σ per-bucket²) numpy step — NOT a per-seed Neo4j KNN. The vector
          INDEX is deliberately NOT used here: it serves whole-DB query-vector search, but
          we already hold a small bounded seed set, so N index round-trips would be both
          slower and needless. Cross-model pairs are never compared (EC-M1).           (EC-M1)
       b. LEXICAL:  canonicalize_entity_name + alias-overlap match (covers unanchored
          entities with no vector, and a recall boost)                                (EC-M2)
  3. CLUSTER matches via union-find; cap cluster size; flag weak transitive links     (EC-M7)
  4. build the UNIFIED result:
       - unification_clusters: [{cluster_id, kind, members:[{project_id, entity_id,
         name}], method, score}]
       - bridge_edges: a synthetic edge per cross-partition pair in a cluster,
         predicate "SAME_AS", inferred=true, method, score                            (EC-M10)
       - disagreements: per cluster, predicate-level divergence across members        (§5)
  5. keep default-off byte-identical to today's forest                                (EC-M5)
```

### 4.1 Decisions (locked unless sign-off changes them)

- **D1 — Signal = kind-gated blend.** Semantic (cosine over the existing indexes, primary for
  anchored+same-model) **⊕** lexical (`canonicalize_entity_name` + alias overlap, fallback/recall).
  Never cross-kind (EC-M3), never cross-model cosine (EC-M1).
- **D2 — Propose, don't assert.** The result is **confidence-scored clusters + inferred bridge
  edges + disagreements**, not a destructive collapse. The forest nodes stay; bridges are tagged
  `inferred=true, method, score` so the agent (and a future human-confirm) can judge. This is the
  over-merge safeguard.
- **D3 — Ephemeral in T0–T2 (no DESTRUCTIVE writes; on-demand embeds are in-memory-only).** No
  migration, no `DETACH DELETE`, no new stored canonical id, no cross-book identity row. The clustering
  result is computed, never committed. **Q1=b clarification:** the on-demand embed of *discovered*
  seeds (§7.1) computes vectors **in application memory for the duration of the call only** — it does
  **NOT** call `set_entity_embedding` (that durable `:Entity.embedding_{dim}` stamp is the extraction
  pipeline's job and is T3 territory). So T1 stays byte-for-byte non-mutating to the stored graph; the
  cost of that choice is recompute-per-call, bounded by the embed-spend cap (EC-M15). Persisting
  on-demand embeds (to amortize cost + hold human "same"-corrections) is re-decided at **T3**.
- **D4 — Conflict = expose, don't reconcile.** A `disagreements` list; never pick a winner (§5).
- **D5 — Cost = in-Python pairwise cosine over the loaded seed set (no per-seed index round-trip).**
  One supplementary Cypher per partition loads the seed entities' `embedding_{dim}` + details (seed
  count already capped by `SUBGRAPH_MAX_NODE_CAP=500`/partition); cross-partition matching is then a
  numpy pairwise-cosine bucketed by kind+`embedding_model` (O(Σ per-bucket²), bounded), and lexical
  is an O(N) dict over normalized names. The 4 Neo4j vector indexes are NOT used for the
  cross-partition step (they exist for whole-DB query-vector search; our seed set is small and
  already loaded). Hard caps on cluster count/size; report `unify_capped` like `node_cap_hit`
  (EC-M11).
- **D6 — Surface = opt-in enum on both tools.** Arg named **`unify`** (NOT `merge` — "one name for
  one concept": `merge` already means the destructive same-partition `merge_entities` collapse; this
  is non-destructive cross-book linking). On `KgMultiQueryArgs` + `KgWorldQueryArgs`: `"off"` (default
  → today's forest, byte-identical), `"by_name"` (lexical only — cheap, no embeddings), `"semantic"`
  (blend). Enum-locked (LLM-client-first). Result gains `unification_clusters`, `bridge_edges`,
  `disagreements`, `unify_method`, `unify_capped` — all additive and **OMITTED** (not present-empty)
  when `unify="off"`, so existing consumers see byte-identical JSON.
- **D7 — Owner-only + tenancy-preserving.** Unification runs only over partitions the caller owns
  (the tools already enforce this). The NEW seed-detail/vector fetch MUST bind `user_id` and the
  explicit partition `project_id` set; the KNN query reuses `find_entities_by_vector`'s
  `user_id`-mandatory, oversample-then-filter discipline. No cross-partition Cypher — clustering is
  Python over per-partition reads.
- **D8 — Confidence bands, PER-METHOD thresholds.** `score ≥ τ_high` → "same"; `τ_low ≤ score <
  τ_high` → "likely"; below τ_low → not a candidate. **Cosine and lexical scores are NOT on the same
  scale** — a 0.6 cosine and a 0.6 alias-overlap mean different things — so each method carries its
  OWN (τ_low, τ_high) in `settings` (`τ_sem_*` vs `τ_lex_*`); a blended cluster records `method` so the
  band is read against the right pair. Bands (not a single cutoff) so the agent treats strong vs weak
  bridges differently. Conservative defaults; tunable. (EC-M17)

---

## 5. Conflict / disagreement handling (greenfield)

After clustering, for each cluster of unified members, collect each member's RELATES_TO edges
(already loaded per partition) and group by `(predicate, target-cluster)`:

- **Agreement:** members assert the same predicate to the same (unified) target → one bridged edge.
- **Disagreement:** members assert **different predicates** to the same target-cluster, OR one
  asserts an edge another temporally-closed/contradicts → emit
  `{cluster_id, predicate_a, project_a, predicate_b, project_b, target_cluster_id}`.

Expose in `disagreements`; **never reconcile**. This upgrades the current LLM-prompt hint
("note when books disagree", `multi_project.py:281`) into structured data the agent can cite.
Fact-level (`:Fact`) disagreement is the same pattern, deferred to a T2 sub-slice if edge-level lands
first.

---

## 6. Edge cases (folded, LOCKED at build)

### 🔴 must-honor invariants
- **EC-M1 — model-space gate.** Never cosine-compare two entities with differing `embedding_model`
  (meaningless). Such pairs fall back to lexical only.
- **EC-M2 — unanchored entities have no vector.** They MUST still participate via lexical matching;
  never silently dropped from unification.
- **EC-M3 — kind-gate.** Never unify across `kind` (character↔location), even at 0.99 name/vector
  similarity. Bucket by kind first.
- **EC-M4 — tenancy.** Unification spans ONLY owner-owned partitions (tool-enforced); every new
  fetch binds `user_id` + the partition set; no global vector query without the `user_id` filter; no
  cross-partition Cypher (Python clustering over isolated per-partition reads).
- **EC-M5 — default-off regression.** `unify="off"` (default) returns the CURRENT forest
  byte-identical (a golden test locks node/edge equality).

### 🔴 must-honor — Q1=b (on-demand embed, T1) — see §7.1
- **EC-M14 — embed-model match.** On-demand embeds MUST use the partition's anchored `embedding_model`
  (or the user's default; else skip→lexical). Embedding under a mismatched model is wasted work that
  EC-M1 then refuses. Never guess a model.
- **EC-M15 — embed-spend cap.** `unify="semantic"` fires priced BYOK embed calls; cap on-demand-embedded
  seeds per call, set `unify_capped=true` + `unify_embed_skipped=<n>` when trimmed; an `EmbeddingError`
  degrades that partition to lexical (never fails the tool). `by_name`/`off` embed nothing.
- **EC-M16 — in-memory only.** On-demand vectors live only for the call; NEVER `set_entity_embedding`.
  T1 leaves the stored Neo4j graph byte-identical (durable stamping is T3).

### 🟡 build-shaping
- **EC-M6 — over-merge safeguard.** Confidence-scored proposals + bands (D2/D8), not destructive
  merge. A wrong bridge is visibly low-confidence, not an asserted identity.
- **EC-M7 — transitivity.** Union-find clusters A~B~C, but cap cluster size and mark links that are
  transitive-only (A~C via B) so a weak chain can't silently glue distinct entities. Optionally
  require the cluster's *induced* pairwise scores to clear τ_low.
- **EC-M8 — N>2 partitions.** A world with many books → cluster, not pairwise; bridge edges are
  pairwise within a cluster (Q3=pairwise at T0; synthetic-centroid star reassessed at T1).
- **EC-M9 — rank asymmetry.** Per-project-normalized salience compared cross-project (inherited from
  B1(2)). T0–T2: document + rank clusters by a model-free signal (max mention_count / anchor_score);
  T4: cross-partition renormalization or reranker.
- **EC-M10 — no fabricated direct edges + cross-partition ONLY.** A cross-book relationship is expressed
  ONLY via the tagged `inferred` bridge + the members' real edges; never mint a real-looking edge
  between two books' nodes. Bridge edges are **strictly cross-partition** — two same-named entities
  *within one book* are `merge_entities` territory, NOT a bridge (no intra-partition self-pair).
- **EC-M17 — per-method score scale.** Cosine and lexical scores are not comparable; bands use
  per-method thresholds (D8). A blended cluster carries `method` so the right (τ_low, τ_high) applies.
- **EC-M18 — degenerate lexical key.** Skip any seed whose `canonicalize_entity_name` normalizes to
  empty/whitespace (honorific-only, stray punctuation) — never cluster two entities on an empty key.
- **EC-M19 — zero-norm / missing vector.** Skip zero-norm or absent vectors before pairwise cosine
  (no divide-by-zero / NaN); such seeds match via lexical only.
- **EC-M20 — common-name over-cluster.** Generic names ("Master", "the King", "Mother") over-cluster
  lexically. T0: for short/common normalized keys require alias-overlap ≥1 (not name-equality alone);
  a tunable stoplist is a T1 refinement if precision suffers.

### 🟢 low / documented
- **EC-M11 — cost caps.** Seed cap (existing 500/partition), on-demand-embed cap (EC-M15), max
  clusters; set `unify_capped=true` when trimmed (honest partial, like `node_cap_hit`).
- **EC-M12 — singleton cluster.** An entity with no cross-partition match = the original node, no
  bridge, not in `unification_clusters`.
- **EC-M13 — reranker optional.** If BYOK rerank is unavailable, degrade to cosine/lexical (never
  fail the tool).
- **EC-M21 — cluster-cap ordering.** Cap clusters/bridges by **confidence-descending** (sort THEN
  trim), so `unify_capped` drops the weakest, not a random tail — truncation must keep the best.
- **EC-M22 — ephemeral, deterministic `cluster_id`.** `cluster_id` is per-call and NOT durable (a
  later call may assign a different id) — the agent must not cite it across turns. Derive it
  deterministically (stable hash of sorted member entity_ids), never from RNG, so the default-off /
  golden tests are reproducible.
- **EC-M23 — disagreement singleton target.** When a disagreement's target is not itself clustered,
  `target_cluster_id` is null → fall back to the target's `entity_id` so the record stays resolvable.
- **EC-M24 — bridge id-space consistency.** `bridge_edges.source/target` MUST reference the exact node
  `id` used by `edges`/forest nodes (so `edges ∪ bridge_edges` joins) — asserted in a unit test.

---

## 7. Open questions — RESOLVED (PO sign-off 2026-07-03)

1. **Q1 — semantic coverage gap → DECISION: (b) embed discovered seeds on demand.** Embeddings exist
   **only for glossary-anchored** entities, so a recurring character that stays "discovered" would fall
   back to lexical. PO chose **(b)**: T1 adds an on-demand embed pass over unembedded seeds (real BYOK
   cost). Build contract + its edge cases in **§7.1** — this is the load-bearing part of T1.
2. **Q2 — persist or stay ephemeral? → DECISION: ephemeral-first.** Build the ephemeral proposal engine
   (T0–T2); the persisted cross-book substrate + `SAME_AS` Neo4j edge + confirm-token spine is **T3**,
   re-decided with usage/precision numbers. Per D3, the Q1=b on-demand embeds are **in-memory-only** (no
   `set_entity_embedding`), so ephemeral-first holds even with semantic on.
3. **Q3 — bridge representation for N>2 → DECISION: pairwise at T0.** Pairwise `SAME_AS` bridges (O(k²)
   within a cluster), reassess a synthetic-centroid star at T1 only if pairwise blows the result size.

### 7.1 Q1=b build contract (on-demand embedding of discovered seeds — T1)

Chosen path (b) turns `unify="semantic"` into a **priced, latency-bearing** operation. The following
is LOCKED for T1:

- **Model MUST match the partition's anchored `embedding_model` (EC-M14).** A vector embedded with a
  *different* model is unusable — EC-M1's model-gate would (correctly) refuse to cosine-compare it
  against the partition's anchored entities, so the embed would be wasted. Resolution order per
  partition: **(1)** the `embedding_model` already stamped on that partition's anchored entities (the
  dominant one if mixed); **(2)** if the partition has ZERO anchored entities, resolve the user's
  default embed model via provider-registry; **(3)** if that resolves to nothing (e.g. the test account
  has an empty `user_default_models`), **skip semantic for that partition and degrade to lexical** —
  never guess a model. Cross-partition, seeds embedded under different per-partition models still only
  compare within their own model bucket (EC-M1 unchanged).
- **In-memory only — no durable stamp (D3, EC-M16).** Reuse `EmbeddingClient.embed(...)` (provider-
  registry BYOK) to get vectors, hold them in the call's working set, and feed the same in-Python
  pairwise-cosine step (D5). Do **NOT** call `set_entity_embedding`. T1 mutates nothing in Neo4j.
- **Spend is capped + honest (EC-M15).** `unify="semantic"` may fire embed calls that cost real money
  and tokens (`EmbeddingResult.prompt_tokens`). Cap the number of on-demand-embedded seeds per call
  (`UNIFY_ONDEMAND_EMBED_CAP`, conservative default); when the cap trims, set `unify_capped=true` and
  add `unify_embed_skipped=<n>` so the agent knows recall was bounded by cost, not by data. An embed
  failure (`EmbeddingError`) degrades that partition to lexical (never fails the tool) — the existing
  `embed_failed` short-circuit already gives this.
- **Text source for unembedded seeds:** discovered entities carry no glossary FK, so build embed text
  from KG-local `name`+`aliases` (the `g is None` branch `entity_embedder.build_embed_text` already
  takes) — no glossary round-trip.
- **`by_name` never embeds.** Only `unify="semantic"` triggers the on-demand pass; `by_name` and `off`
  make zero embed calls (zero spend).

---

## 8. Tier build (gated — commit T0–T2; re-decide T3–T4)

| Tier | Scope | Gate (measurable) |
|---|---|---|
| **T0** | Unification engine (lexical only: `canonicalize_entity_name` + alias overlap, kind-gated, union-find clusters, bridge edges) + `unify` enum on both tools + `unification_clusters`/`bridge_edges` output + **default-off byte-identical**. Ephemeral. | Default-off golden test passes (forest byte-identical); a 2-project fixture with a shared-named same-kind character produces exactly one cluster + one bridge; a same-name **different-kind** pair produces NONE (kind-gate). |
| **T1** | Semantic signal: in-Python pairwise cosine over the loaded seed vectors (model-gated D5), blended with lexical; **Q1=b on-demand embed of discovered seeds** (§7.1 — model-match EC-M14, spend-cap EC-M15, in-memory-only EC-M16); per-method confidence bands (D8/EC-M17). `unify="semantic"`. | On a labeled 2-book fixture, semantic beats lexical-only on recall for a renamed/aliased recurring entity, with no cross-model/cross-kind false merge; model-mismatch pair falls back to lexical; a discovered (unembedded) recurring entity is embedded on demand under the anchored model and clusters; a partition with no resolvable embed model degrades to lexical (no crash); embed spend respects the cap (`unify_embed_skipped` set when trimmed); NO `set_entity_embedding` write occurs (stored graph unchanged). |
| **T2** | Disagreement detection (`disagreements` output, edge-level). | A seeded contradiction (Alice→LOVES→Bob in A, Alice→KILLS→Bob in B) is surfaced as one disagreement record; an agreement is not. |
| **T3** *(deferred, re-decide)* | Persisted cross-book canonical substrate: a cross-project identity store + a `SAME_AS` Neo4j edge + a human-confirm merge spine (mirror `kg_schema_edit` confirm-token). Durable, corrected, reused merges. | — (re-scope after T0–T2) |
| **T4** *(deferred)* | Cross-partition salience/rank renormalization + reranker-assisted cluster/edge ranking (EC-M9). | — |

**Committed scope of this epic:** T0–T2 (the ephemeral proposal + conflict engine). T3–T4 get their
own PLAN after T0–T2 land and we have precision/recall numbers.

---

## 9. Tool contract (T0–T1)

`KgMultiQueryArgs` / `KgWorldQueryArgs` gain:
```
unify: Literal["off","by_name","semantic"] = "off"   # enum-locked (LLM-client-first)
```
Result (additive; keys OMITTED entirely when `unify="off"` → byte-identical to today):
```
unification_clusters: [{cluster_id, kind, members:[{project_id, entity_id, name}], method, score}]
bridge_edges:         [{source, target, predicate:"SAME_AS", inferred:true, method, score}]
disagreements:        [{cluster_id, predicate_a, project_a, predicate_b, project_b, target_cluster_id|target_entity_id}]  # T2, EC-M23
unify_method:         "by_name"|"semantic"
unify_capped:         bool
unify_embed_skipped:  int    # T1 only, EC-M15 — on-demand-embed seeds trimmed by the spend cap (recall bounded by cost)
```
`cluster_id` is **ephemeral/per-call** and deterministically derived (EC-M22); clusters/bridges are
returned **confidence-descending** so the cap (EC-M21) drops the weakest. All keys OMITTED when
`unify="off"`.
`bridge_edges` is kept a SEPARATE key (not folded into `edges`) so the agent cleanly distinguishes
real intra-book relationships from inferred cross-book identity links; the connected graph = `edges`
∪ `bridge_edges`.
Registered across all 4 KG-tool sources + the FastMCP signature (the B1(3) discipline); enum
value-set pinned in the drift-lock test; advertised bounds in the schema (per /review-impl #1).

## 10. Tests

- **Unit (no Neo4j):** a capturing `_FakeSession` (mirror `test_world_subgraph_w2.py`) with a canned
  2–3 partition forest + seed details + a fake `EmbeddingClient` → assert: cluster formation,
  **kind-gate** (EC-M3), **model-gate** (EC-M1), unanchored-via-lexical (EC-M2), **default-off
  byte-identical** (EC-M5), transitivity cap (EC-M7), singleton→no bridge (EC-M12), disagreement
  detection (T2), `unify_capped` (EC-M11). **Q1=b:** on-demand embed uses the anchored model
  (EC-M14), no-resolvable-model→lexical-degrade (EC-M14/§7.1 step 3), spend-cap sets
  `unify_embed_skipped` (EC-M15), **fake embed asserts `set_entity_embedding` NEVER called** (EC-M16),
  `EmbeddingError`→lexical-degrade. **Guards:** empty-normalized-key skip (EC-M18), zero-norm vector
  skip (EC-M19), common-name needs alias-overlap (EC-M20), per-method bands (EC-M17), cap ordering
  confidence-descending (EC-M21), deterministic `cluster_id` (EC-M22), no intra-partition self-bridge
  (EC-M10), `bridge_edges` id-space matches `edges` (EC-M24), disagreement singleton-target fallback
  (EC-M23). Arg-model enum + drift-lock (tool count 30→30, enum value-set) + advertised bounds.
- **Integration (`TEST_NEO4J_URI`):** build 2 projects via `merge_entity` + `set_entity_embedding`
  with a shared-named same-kind character (one anchored w/ vector, one lexical-only) → assert the
  cluster + bridge + a seeded disagreement.
- **Live-smoke:** 2 real KG-populated projects on the test account → `kg_multi_query(unify="semantic")`
  → a known recurring entity clusters; `unify="off"` unchanged. (Rebuild knowledge image; the B1(2)
  smoke recipe.)

## 11. Risks

- **Over-merge (primary)** — mitigated by propose-don't-assert (D2), kind-gate (EC-M3),
  confidence bands (D8), and never invoking destructive `merge_entities` cross-partition.
- **Semantic blind spot → CLOSED by Q1=b** — discovered entities are embedded on demand under the
  anchored model (§7.1); the residual risk is a partition with no resolvable embed model, which
  degrades to lexical (never crashes) — measured at the T1 gate.
- **Surprise spend on a query tool (NEW, Q1=b)** — `unify="semantic"` fires priced BYOK embed calls.
  Mitigated by: `by_name`/`off` embed nothing; a per-call on-demand-embed cap (EC-M15) with honest
  `unify_embed_skipped`; in-memory-only (no durable stamp, EC-M16); `EmbeddingError`→lexical-degrade.
  A cost-gate (propose→confirm) is explicitly deferred to T3 alongside persistence.
- **Cost** — bounded by the existing seed caps + the on-demand-embed cap; `unify_capped` /
  `unify_embed_skipped` report partiality.
- **Scope creep into T3/T4** — hard-stopped: this epic commits T0–T2 only.
