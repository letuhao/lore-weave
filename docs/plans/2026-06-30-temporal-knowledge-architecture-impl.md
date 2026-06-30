# Implementation Plan — Incremental Temporal Knowledge Architecture

**Date:** 2026-06-30 · **Branch:** `feat/temporal-knowledge-architecture` · **Size:** XL · **Type:** FS
**Spec (authoritative):** [`docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md`](../specs/2026-06-29-incremental-temporal-knowledge-architecture.md) — §12 + §12.7.8 govern; upstream §3.3/§5/§6B/§4-Path-B-step-5 are superseded by §12 where they conflict.
**Pairs with:** `docs/analysis/2026-06-29-ontology-extraction-bloat.md`

> **Execution model (user-directed):** build the **foundation SERIALLY** (single-writer, this branch),
> **checkpoint**, then **fan out PARALLEL worktree agents** for consumer migrations + FE + lints. The
> serial/parallel cut is dictated by INV-FACTS (§12.0) + the KAL contract: everything depends on one SSOT
> substrate and one frozen contract, so those are serial; everything *behind* the frozen contract is parallel.

---

## 0. Locked decisions (this plan)

| # | Decision | Source |
|---|---|---|
| D-KAL-LANG | **KAL = new TypeScript gateway service** (`services/knowledge-gateway`), I3 gateway-tier convention; federates glossary-svc (Go) + knowledge-svc (Python) behind one versioned typed contract. MCP tools become one client of it. | user 2026-06-30; spec §9.9 |
| D-RUN-SCOPE | This run = plan + **serial foundation** (F0–F4), then human checkpoint before fanout (X1–X7). | user 2026-06-30 |
| D-SUBSTRATE-HOME | The `entity_facts` SSOT + `episodes` + `canonical_snapshot` live in **glossary-service** (Postgres, the SSOT side). KG side gets the **ordinal valid-time unify** in knowledge-service (Neo4j). | spec §8B |

---

## 1. Code reality (verified by 3 read-only sweeps, 2026-06-30)

**Glossary-service (Go/Chi):** forward-only migration ledger, latest `0043_canonical_summary`
(`internal/migrate/ledger.go:104`). EAV `UNIQUE(entity_id, attr_def_id)` in-place overwrite
(`migrate.go:99-108`). `evidences` carries quote+chapter (`migrate.go:124-137`). `merge_journal` repoints a
**fixed child-table list** that omits any facts/episodes table (`migrate.go:1486-1510`); merge uses row-level
`FOR UPDATE` sorted by entity_id (`merge_handler.go:262-289`). Writeback under per-book
`pg_advisory_xact_lock(0x45585457, hashtext(book))` + `writeback_key`/`extraction_writeback_log` idempotency
(`extraction_handler.go:611-644`). Canonical compare-and-clear md5 guard
(`canonical_summary_handler.go:182-191`), `canonicalMaxRunes=2000`. Resolver:
`findEntityByNameOrAlias`/`findEntityCrossKind` + `uq_entity_dedup` partial index on
`(book_id,kind_id,normalized_name) WHERE normalized_name<>''` (`extraction_concurrency.go:50-59`). Wiki reads
EAV directly via LEFT JOIN (`wiki_handler.go`).

**Knowledge-service (Python/Neo4j):** `valid_from/valid_until` = **wall-clock** (`facts.py:104-105`),
`from_order` = the reading-axis (`facts.py:112`) — **not unified** as story valid-time on the fact.
`single_active` close-prior is by `datetime()`, **zero ordinal awareness** (`relations.py:180-201`) → the A2
out-of-order bug. Retract primitives exist (`remove_evidence_for_source`/`_for_natural_key` + zero-evidence
cleanup, `provenance.py:417-505`, `facts.py:459-465`) but are **not extraction-driven**. Content-hash identity
`canonical_content` (`facts.py:89`). Null-sink `9223372036854775807` in `events.py:55`; fail-closed `-1` in
`spoiler_window.py:27`. Hierarchical summaries `level_summaries.py` + `summary_processor.py` (`RETRY_BUDGET=3`,
inline backoff). MCP `kg_graph_query(as_of_chapter)`, `kg_entity_edge_timeline` already as-of-parameterized.

**Consumers (all on stable book-scoped clients — migration is LOW risk):** composition
(`glossary_client._cast_roster` **truncates at 100, ignores `next_cursor`** — live D4 bug; `knowledge_client`
already temporal via `timeline`/`fact_for_check`), lore-enrichment (full-book `list_entities`, cached),
chat (MCP `glossary_search`/`get_entity`; KG side already as-of), translation
(`fetch_translation_glossary(chapter_id)` + occurrence scoring + rolling summary). **No KAL exists** — net-new.
Lints: `scripts/ai-provider-gate.py` + `.githooks/pre-commit` + `contracts/language-rule.yaml`.

---

## 2. The serial/parallel cut

```
        ┌──────────────────────── SERIAL FOUNDATION (this run) ────────────────────────┐
F0  KAL contract freeze  ─────────────────────────────────────────┐  (reconcile artifact)
F1  Glossary bi-temporal substrate (entity_facts/episodes/maintain_chain/projection/locks/merge/names)
F2  Canonical = versioned regenerable cache
F3  KG ordinal valid-time unify  (must precede KG as_of exposure)
F4  KAL service skeleton (TS) impl v1 + per-substrate as_of gating + roster + 2 INV-KAL lints
        └───────────────────────────────── CHECKPOINT ─────────────────────────────────┘
                                              │  freeze of kal.v1.yaml is the cut line
        ┌──────────────────── PARALLEL FANOUT (worktree agents, post-checkpoint) ───────┐
X1 composition→KAL (+drain _cast_roster)   X2 lore-enrichment→KAL   X3 wiki→KAL (kill direct-EAV)
X4 chat→KAL                                X5 translation as-of + immutable-once cache
X6 FE temporal surfaces (canonical card / slider / change-timeline / diff / retrieval / translation)
X7 lint enforcement + DEFERRED rows
        └───────────────────────────────────────────────────────────────────────────────┘
```

**Why this cut:** INV-FACTS (§12.0) makes `entity_facts` the only SSOT, so the substrate (F1) cannot be
parallelized — every derived layer reacts to it. The KAL contract (F0) is the artifact every fanout agent
binds to; freezing it as a written `kal.v1.yaml` **before** any consumer is touched is the reconcile node
that makes X1–X7 provably disjoint. F3 must precede F4's KG `as_of` exposure (§12.5.1 build-order amendment).

---

## 3. FOUNDATION milestones (serial)

### F0 — Freeze KAL v1 contract  *(keystone; ~XS code, high leverage)*
**Deliverable:** `contracts/api/knowledge-gateway/kal.v1.yaml` — the typed read/write surface from §6D, with
§12 hardening baked in. v1 semantics == **today's current-projection** (so consumers migrate with no behavior
change); temporal is an **additive** `as_of` param + new write verbs.
- **Reads (bounded by construction):** `get_canonical(entity, as_of?)`, `get_facts(entity, as_of?, attrs?)`,
  `timeline(entity, before_order, after_order, cursor)`, `retrieve(scope, query, k)`, `search(query, k)`,
  `neighborhood(entity, hops=1, cap)`, **`roster(book, fields=[id,name], cursor)`** (bounded-complete, §12.5.2),
  **`list_attr_values(entity, attr, cursor)`** (multi-valued structured, §12.5.3).
- **Writes:** `ingest_episode`, `resolve_entity`, `append_fact`, `close_fact`, `retract`, **`split_entity`**
  (§12.4.2), `fold_canonical`.
- **Typed `temporal_capability` per source** (§12.5.1): KG branch returns `temporal_unsupported` until F3 lands.
- Add `knowledge-gateway: typescript` to `contracts/language-rule.yaml`.
**Risk boundary → commit.** No consumer is touched.

### F1 — Glossary bi-temporal substrate  *(the heavy net-new lift; L→XL on its own)*
Migrations are forward-only; append after `0043`. Slices (each its own commit at a risk boundary):
- **F1a — schema (migration `0044_entity_facts`):**
  - `entity_facts(entity_id, fact_kind, attr_or_predicate, value, value_hash, valid_from_ordinal,
    valid_to_ordinal, valid_to_eff GENERATED coalesce(valid_to_ordinal, INT_MAX), created_at, invalidated_at,
    source_episode_id, cardinality)` + `UNIQUE(entity_id, fact_kind, attr_or_predicate, value_hash,
    valid_from_ordinal, source_episode_id)` (§12.2.2) + index `(entity_id, attr_or_predicate, valid_from_ordinal,
    valid_to_eff)` (§12.3.1).
  - `episodes(episode_id, book_id, chapter_id, chapter_ordinal, char_range, token_count, content_hash, status
    {pending,reconciled}, ingested_at)` + `UNIQUE(chapter_id, content_hash)` (§12.2.5).
  - `merge_journal` new columns: moved fact ids + close/invalidation ids (§12.4.1 step 5).
  - Half-open interval convention **locked** (§12.3.1); KG `INT64_MAX` null-sink reused.
- **F1b — `maintain_chain(entity, attr)` (the single `valid_to` writer):** ordinal-aware interval-split insert
  (§12.3.2) + retract re-stitch (§12.3.3 step B.3.5) + merge reconcile (§12.4.1 step 3) — **one routine, three
  entry points.** Test: close-then-retract leaves predecessor current (§12.3.3).
- **F1c — synchronous-in-tx EAV projection (§12.2.1):** app-maintained `entity_attribute_values`-shaped row
  upserted in the **same tx** as the fact append (per-`(entity,attr)` row, §12.7.8 Probe-4). Standalone
  rebuild-from-facts repair job as the INV-FACTS backstop.
- **F1d — Path A append (idempotent natural key) + Path B retract (content-hash-gated diff + restitch):**
  drive from the writeback path; carry `writeback_key` forward; `allow_retract_on_remodel` opt-in flag (§12.3.5).
  **Re-run the "identical re-extract → 0 *fact* rows" validation** against the new store (does not transfer).
- **F1e — tiered locking (§12.7.8):** per-`(entity,attr)` chain advisory lock `pg_advisory_xact_lock(FACT_CHAIN_NS,
  hashtext(entity_id||':'||attr))` acquired in sorted **composite-key** order; resolver-create
  `UNIQUE(book,normalized_name,kind) ON CONFLICT DO NOTHING RETURNING` + re-read winner; merge/split entity-pair
  `FOR UPDATE` + affected chain locks held **read→commit**. Global lock order: create → rows `FOR UPDATE` →
  chain advisory.
- **F1f — fact-chain merge + `split_entity` (§12.4):** extend `mergeOne` to repoint/journal `entity_facts`+
  `episodes` (no `NOT IN` dodge); winner-scoped projection rebuild; `split_entity` by `source_episode_id`
  provenance as a new transaction-time event.
- **F1g — bi-temporal name/aliases (§12.4.3):** model name+aliases as multi-valued bi-temporal facts; resolver
  matches the full across-time alias set; as-of name read; resolver cold-start bootstrap (§12.7.4).
- **F1h — cold-start seed migration (`0045_facts_coldstart`):** one open fact per existing entity carrying the
  **current flat EAV value**, `valid_from = first-seen` as bound only (§12.5.4). **Migration test:
  `projection(entity) == flat_eav(entity)` for all entities.**

### F2 — Canonical = versioned regenerable cache  → spec §12.1
- `canonical_snapshot(entity_id, attr_scope, as_of_ordinal, content, content_hash, fold_algo_version,
  fact_coverage_txid, built_at)` PK `(entity_id, attr_scope, as_of_ordinal, fold_algo_version)`.
- Lazy **rebuild-on-read** validity check (`fold_algo_version` current AND no newer fact `created_at` >
  `fact_coverage_txid`); as-of below the fold head **always projects from facts**.
- **Re-ground = ordinal-bucketed tree** (bucket by `valid_from_ordinal`, carry-forward open intervals §12.7.5),
  map-reduce sub-summaries; deterministic trigger `folds_since_reground≥K OR invalidations_since_reground≥J`
  (§12.1 B2). Cap the #26/#7 fold input to one window's facts (fixes §8B false "bounded subset" claim).
- Fold backoff/quarantine: `fold_attempts`, `fold_failed_at`, `canonical_status='unbuildable'` (§12.1 B4);
  **keep the compare-and-clear md5 guard** (§12.2.4 C3).
- Multi-valued attrs are **structured, never folded** (§12.1 D9) → reads via `list_attr_values`.

### F3 — KG ordinal valid-time unify  → spec §8B + §12.5.1  *(must precede F4 KG as_of)*
- Add a **chapter-ordinal valid-time** axis on KG facts/relations and **unify** with `from_order` (today's
  `valid_*` stays the transaction-time axis).
- Make the close **ordinal-aware** (the §12.3.2 fix on the KG side — `single_active` is correct only for
  monotonic L7/user edits today).
- **Drive invalidate + retract from the extraction path** (Path A close-prior, Path B `remove_evidence_*`),
  not just L7/user.
- Store the **exact quote** on KG citations (today: chapter pointer only).
- Add the **per-entity ordinal-stamped canonical snapshot** (the summary tree is structural, not per-entity).

### F4 — KAL service skeleton (TypeScript) + lints  → spec §6D, §12.5
- New `services/knowledge-gateway` (TS) implementing `kal.v1.yaml` against glossary-svc + knowledge-svc;
  `glossary_client`/`knowledge_client` in consumers will later become thin adapters (X1–X5).
- **Per-substrate `as_of` gating** (§12.5.1): KG returns `temporal_unsupported` until F3 is wired through.
- **`roster` keyset-cursor snapshot** (§12.7.3) + **`list_attr_values`** (§12.5.3).
- **Two INV-KAL lints (§12.5.5 D6):** (i) `scripts/knowledge-access-gate.py` — grep for direct
  `entity_attribute_values`/Neo4j reads outside owning-svc + KAL (allowlist, mirror `ai-provider-gate.py`);
  (ii) **HTTP-surface check** — no consumer client targets the owning services' `/internal/*` knowledge
  endpoints. Wire (i) into `.githooks/pre-commit`. (ii) lands as a **DEFERRED row** (planned, not yet
  enforcing — §12.7.7c).

---

## 4. FANOUT milestones (parallel worktree agents — POST-CHECKPOINT)

Each binds **only** to the frozen `kal.v1.yaml`; disjoint file sets → safe in parallel worktrees.

| ID | Slice | Files | Risk |
|---|---|---|---|
| X1 | composition → KAL adapters | `composition-service/app/clients/{glossary,knowledge}_client.py`, `routers/plan.py` (**fix `_cast_roster` cursor drain** §12.5.2) | LOW |
| X2 | lore-enrichment → KAL | `lore-enrichment-service/app/clients/{glossary,knowledge}.py` | LOW |
| X3 | wiki → KAL (kill direct-EAV) | glossary-svc `wiki_handler.go` direct-EAV LEFT JOIN → KAL read | LOW–MED |
| X4 | chat → KAL | `chat-service/app/services/{glossary_skill,knowledge_skill}.py`, MCP tools as KAL clients | LOW |
| X5 | translation as-of + immutable-once | `translation-service/app/workers/glossary_client.py` (as-of-N inject §6B; cache keyed on bounded-unit content-hash §12.1 D8) | MED |
| X6 | FE temporal surfaces | `frontend/` — canonical card, time/version slider, change timeline w/ citations, diff view, retrieval-not-scroll, per-episode translation (§7) | MED |
| X7 | lint enforcement + DEFERRED | enable INV-KAL grep lint repo-wide; land HTTP-surface DEFERRED row | LOW |

---

## 5. Quality gates (per milestone)

- **VERIFY evidence** — real command output, not "should work." Cross-service slices (F1↔F4, X*) need a
  **live-smoke token** (§ CLAUDE.md): a real call on a stack-up, or an explicit `LIVE-SMOKE deferred`/`live infra
  unavailable` note.
- **2-stage REVIEW** (spec-compliance + code-quality) per milestone; `/review-impl` on F1b/F1c/F1e/F1f
  (load-bearing concurrency + merge) and F3 (KG correctness).
- **Migration smoke** — each new migration applied idempotently on the real dev DB (forward-only; no down).
- **The 3 must-pass correctness tests** (spec-mandated): close-then-retract restitch (§12.3.3); identical
  re-extract → 0 fact rows (§12.2.2); `projection==flat_eav` post-seed (§12.5.4).

---

## 6. Risks / watch-items

- **R1 (highest): F1 is itself XL.** Treat F1a–F1h as a continuous run with commits at each risk boundary, not
  one mega-commit. Reclassify-and-announce if a slice grows.
- **R2: the locking model (§12.7.8) is the load-bearing correctness contract** — implement the global lock
  order exactly; `/review-impl` it; live-smoke a concurrent two-chapter append on disjoint chains.
- **R3: KG `as_of` must not ship before F3** — F4 enforces `temporal_unsupported` as the guard.
- **R4: cold-start seed must be byte-identical** to flat EAV or day-one consumers regress (§12.5.4 / D5).
- **R5: D6 HTTP-surface enforcement is a plan, not a gate** — do not claim gateway-grade INV-KAL until the
  HTTP-surface lint exists; carry the DEFERRED row.

---

## 7. Deferred (seeded)

- `D-KAL-HTTP-SURFACE-LINT` — gate #2 (large/structural): the HTTP-surface INV-KAL lint (no consumer client hits
  owning-svc `/internal/*` knowledge endpoints). Table-read grep ships in F4; HTTP-surface tracked. Target: X7.
- `D-KG-INSTORY-EVENTDATE` — gate #2: detected in-story time (`event_date_iso`) as a valid-time source is a later
  advanced follow-up (spec §9 dec-3). Target: post-foundation.
