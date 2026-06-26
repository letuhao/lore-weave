# Spec — KG Extraction Cache (wire the dormant `extraction_leaves` into the live path)

- **Status:** DESIGN / decision recorded — **NOT built in `feat/composition-service`.**
  **Build target: a NEW branch** (proposed `feat/kg-extraction-cache`), knowledge-service /
  worker-ai. Deferred per PO decision 2026-06-26.
- **Date:** 2026-06-26 · **Size:** M–L / structural (live extraction path — load-bearing)
- **Origin:** PO asked "glossary has extraction caching (update glossary without re-paying
  raw extraction per chapter) — should KG have it?" Three read-only research passes
  (2026-06-26) answered it; this spec records the finding + the decision.

---

## 1. The question

KG (knowledge-graph) extraction is expensive (LLM over chapter text). Should
knowledge-service have a cache — like the one that lets the *glossary* be updated without
re-paying extraction — so the graph can be re-materialized/rebuilt without re-running the LLM?

The deeper concern the PO raised: glossary extraction is **one universal purpose** (find
entities → always reusable → cache obviously worth it), whereas KG extraction *feels*
**purpose-specific** ("extract for a specific problem, not extract-once-use-all"), so it
wasn't clear a cache would even pay off. **What should we cache, given that?**

## 2. Finding A — the "glossary cache" premise is misattributed

| Service | What it actually has |
|---|---|
| **glossary-service** | **No raw cache.** Only `extraction_writeback_log` — a counts/idempotency *ledger* (no LLM output). Makes a re-writeback a no-op; stores zero LLM output. (`internal/migrate/extraction_concurrency.go:61-75`) |
| **translation-service** | **The real glossary-feeding cache** — `extraction_raw_outputs` (raw LLM text + `parsed_entities`, content-hash keyed). A cache HIT replays parsed entities for **0 tokens** and re-drives the idempotent glossary writeback. (`app/workers/extraction_cache.py`, `extraction_worker.py:791-1006`, `migrate.py:324-362`) |
| **knowledge-service** | **Has a cache table + gate ALREADY built** — `extraction_leaves` (`candidates_jsonb`, materialized per-op output) + `extraction_leaves_raw` (opt-in `save_raw_extraction`), keyed `task_id = sha256(text, op, extractor_version, model_ref, schema)`, with a `fetch_cached` LLM-skip gate (`pass2_orchestrator._cached_extract`, `db/repositories/extraction_leaves.py`, `db/migrate.py:723-761`). **BUT the live path never uses it** (next finding). |

So "the feature glossary has" is really **translation-service's** content-addressed cache.

## 3. Finding B — KG's cache exists but is **dormant on the live path**

- The live extraction path is `worker-ai/app/decoupled_extract.py` → `POST /internal/extraction/persist-pass2`, which writes **only** Neo4j + Postgres-canon. It **never populates or reads** `extraction_leaves` (`worker-ai/app/sample_emit.py:4-8` states this explicitly; grep finds no `fetch_cached`/`task_id` in `decoupled_extract`).
- The `_cached_extract`→`fetch_cached` gate is wired only into the **legacy** `/extract-item`
  orchestrator path, which the live worker abandoned (`worker-ai/app/clients.py:4-5`).
- Therefore **`rebuild_extraction` re-LLMs every chapter** (`routers/public/extraction.py:1192-1261`: delete graph + fresh `scope="all"` job, no cache consult). This is the waste a working cache eliminates.

## 4. Finding C — KG extraction is NOT too purpose-specific (the concern is unfounded)

Two independent enumerations agreed:

- **Op-set is a FROZEN 5-tuple** — `entity, relation, event, fact, summarize_level` —
  enforced at **3 code layers** (`PROMPT_OPS`, `_OP_PROMPTS` raises on unknown op,
  `_VALID_OPS`). Adding an op is a deliberate code change, not a per-feature event.
  Recovery / precision-filter / custom-ontology are **refinements within the same atoms**,
  not new ops.
- **Bounded schema** — 6 node labels (`Entity, Event, Fact, EntityStatus, Passage,
  ExtractionSource`), 3 edge types (`RELATES_TO, EVIDENCED_BY, ABOUT`). No per-feature
  label growth; custom ontology adds *values within* the fixed types.
- **~22 : 2 of consumers are pure projections.** Every packer lens, public endpoint, RAG
  context-builder, wiki-neighborhood, flywheel just **reads + filters** the core atoms.
  The 2 "new-extraction" cases both reuse the core: **delta extraction** (`/extract-item`,
  derivative-only) reuses the same 5-op engine scoped to the delta project; **wiki gen** is
  a separate external LLM pipeline producing prose, not core atoms.

**Conclusion:** KG extraction is a **bounded substrate that nearly everything projects
from** — caching is as worthwhile as glossary's. The "purpose-specific → poor reuse" worry
would hold only if the op-set were open-ended; it is closed.

## 5. The SSOT nuance (why "realize the plan's SSOT" is NOT the answer)

There are two different "SSOT-ish" layers — don't conflate them:

- **The plan's SSOT** (`docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` §3.8) = raw text +
  `event_log` + curated glossary, with "Neo4j is a derived view." **But rebuilding Neo4j
  from *this* still re-runs the LLM** (the plan itself says rebuild "possibly costs AI
  credits"). It does NOT materialize the extracted atoms. So realizing the plan-SSOT does
  not, by itself, solve the cache problem.
- **The built `extraction_leaves` layer** = a **content-addressed materialization of the
  per-op LLM output** the plan never spec'd. On unchanged `(text, op, extractor_version,
  model_ref, schema)` it returns candidates with **zero LLM calls**
  (`pass2_orchestrator.py:613-619`). *This* is the layer that makes re-derivation free.

## 6. Decision — what to cache, and the work

**Cache the materialized per-op candidates** (`extraction_leaves`), content-addressed by
`(text, op, extractor_version, model_ref, schema)`. This is the right *unit* precisely
because the op-set is closed and consumers project from it. **Do NOT** build a new cache,
and **do NOT** do a speculative "maximal extraction" hoping to cover future needs.

The config-keyed busting is **correct semantics, not a limitation**: a prompt/model/schema
change *should* re-extract (you want quality improvements to re-run); the only waste to
remove is re-extracting on an **unchanged** config (every rebuild today).

**The work is wiring, not a new feature:**
1. In `worker-ai/decoupled_extract.py`, before each op's LLM call → compute `task_id` and
   `fetch_cached`; on HIT skip the LLM and use cached candidates.
2. After a clean LLM call → `put` candidates into `extraction_leaves` (+ `_raw` when
   `save_raw_extraction`). Only cache clean/OK batches (mirror translation-service's gate).
3. `rebuild_extraction` → consult the cache (re-materialize) instead of unconditional
   re-LLM; keep `invalidate-cache` for genuine config bumps.
4. Resume **DEFERRED 077** (the `mode='replay'` job + `POST …/replay` endpoint,
   `docs/plans/2026-06-12-extraction-raw-output-cache.md` Phase 3).

**Reference implementation to mirror:** translation-service's
`get_cached_batch`/`put_batch` content-hash gate (`app/workers/extraction_cache.py`,
`extraction_worker.py:791-1006`) — same pattern, different store.

## 7. Acceptance

- A `rebuild` on an unchanged book makes **0 LLM calls** (cache HIT on every chapter/op),
  re-deriving the same Neo4j graph.
- A genuine config bump (new prompt/model/schema → new `extractor_version`) correctly
  **misses** and re-extracts.
- The live `decoupled_extract` path **populates** `extraction_leaves` on every clean
  extraction (verify a row lands per chapter×op).
- **Live-smoke required** (live extraction path, ≥2 services). **`/review-impl` mandatory**
  (load-bearing: a bug here silently corrupts the graph or wastes spend).

## 8. Scope / branch

- **NOT `feat/composition-service`.** Build on a **new branch** (proposed
  `feat/kg-extraction-cache`), knowledge-service + worker-ai.
- Independent of the composition branch-clearing milestones; can proceed in parallel once
  scheduled. Note M7 (per-chapter mention frequency, composition plan) is **deterministic
  string-counting** and does NOT depend on this cache.
