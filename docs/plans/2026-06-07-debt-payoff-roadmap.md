# Roadmap — Debt Payoff (063 + K17 + 064 re-scout)

> **⚠️ SUPERSEDED 2026-06-08 — absorbed into [`2026-06-08-pre-merge-closeout-roadmap.md`](2026-06-08-pre-merge-closeout-roadmap.md).**
> This doc is retained for its detailed per-item **design + AC** (the close-out roadmap links back here for 063 and K17). Execution sequencing now lives in the close-out roadmap:
> - **K17** → close-out **Cycle 12** · **063** → close-out **Cycle 17** · **064** → close-out **Cycle 15** (already re-scouted cy5 = no clean slice).
> Don't plan from this doc's "Recommended sequence" below — use the close-out roadmap's cycle order. The technical content (§Item 1/2/3) is still current.

- **Date:** 2026-06-07 · **Branch:** `feat/composition-service` (or a fresh branch per cycle)
- **Origin:** user-requested debt-payoff plan for the residual deferred rows after mui#3/#4.
- **Scope (PO-locked 2026-06-07):** pay off **K17** (entity-embedding write pipeline) + **063** (grounding-compose migrate); **064** gets a cheap re-scout for a clean slice before deciding (default: keep deferred).
- **No deadline** (hobby project) — order is value/cost-driven, each item runs its own 12-phase `/loom` cycle.

---

## Recommended sequence

Cheap, conclusion-driven items first to clear backlog noise, then the substantive feature:

1. **064 re-scout** (XS, ~30 min) — confirm/deny a clean slice. Likely outcome: keep deferred with a firmer rationale, OR surface one small safe slice.
2. **063 D-GROUNDING-COMPOSE-MIGRATE** (M) — self-contained lore-enrichment data-shape migration.
3. **K17 entity-embedding write pipeline** (L/XL) — the real net-new value; needs its own CLARIFY.

Order is flexible — if you'd rather front-load value, do K17 first. The cheap items don't block it.

---

## Item 1 — 064 D-GROUNDING-C-ADOPT re-scout (XS)

**Goal:** decide, with fresh eyes on current code, whether composition can adopt `loreweave_grounding` via any clean+valuable slice, or stays correctly deferred.

**Why it's blocked today (DEFERRED 064 / spec §4.4):**
- `app/packer/sanitize.py` `neutralize` is structurally divergent: `⟦…⟧` marker (not `[FICTIONAL] `), angle-bracket escaping `<`→`＜` to protect `<canon>`/`<guide>` assembly delimiters; the SDK's NFKC prenormalize would fold `＜` back, **undoing** the delimiter defense.
- `GroundingCite` emission is net-new with **no downstream consumer** (composition packs one prompt, doesn't ground per-item).

**Scout steps (conclusion only — do NOT build):**
1. Re-read `services/composition-service/app/packer/sanitize.py` + the packer assembly that consumes its output, and `sdks/python/loreweave_grounding/sanitize.py`.
2. Check whether composition has gained any per-item citation surface since 2026-06-07 (grep packer/router for cite/grounding/evidence emission).
3. Verdict in one of three forms:
   - **No slice** → update DEFERRED 064 rationale ("re-scouted YYYY-MM-DD, still no clean slice"), close the scout.
   - **Sanitize-only slice exists** → only if the SDK can be parameterized to accept composition's marker + skip angle-bracket NFKC without behavior change (an SDK opt-out flag, not a composition rewrite). If found, spin a separate S cycle.
   - **Emission slice exists** → only if a real `GroundingCite` consumer now exists. Spin a separate cycle.

**AC:** a written verdict + DEFERRED row updated. No production change unless a slice is both clean AND valuable.

---

## Item 2 — 063 D-GROUNDING-COMPOSE-MIGRATE (M)

**Goal:** migrate lore-enrichment's grounding-COMPOSE path from the local `GroundingRef` to the SDK's `GroundingCite`, so all four consumers share one evidence shape (closes the last mui#3 compose-side gap). SDK already ships `compose_cites` + `from_grounding_ref` ([cites.py](../../sdks/python/loreweave_grounding/cites.py)).

**Surface (verified 2026-06-07):**
- `GroundingRef` is a pydantic model at [strategy.py:74](../../services/lore-enrichment-service/app/retrieval/strategy.py#L74); `compose_grounding` + providers at [grounding.py](../../services/lore-enrichment-service/app/retrieval/grounding.py).
- **Persisted:** refs are stored in `proposals.source_refs_json` via `SourceRef` (`app/services/review.py`, `app/strategies/*`). → read-compat for existing rows is mandatory.
- **License coupling:** re-cook (P3) resolves a per-source license via `UUID(corpus_id)` ([recook.py](../../services/lore-enrichment-service/app/strategies/recook.py)). Synthetic ids (`glossary:canon`, `knowledge:context`, `author_draft`) are non-UUID by design and must stay distinguishable post-migration. P2/P3 are gate-locked, so this is a forward-guard, not a live path.

**Decision to lock at CLARIFY:** is this a *wire-format* migration (change what's persisted in `source_refs_json` → needs read-compat shim for old rows) or an *internal-only* migration (keep `SourceRef`/`source_refs_json` as-is on disk, only swap the in-memory compose algorithm to `compose_cites` and adapt at the boundary)? **Recommended: internal-only** — keep `source_refs_json` shape unchanged (zero data migration, zero read-compat risk), route the compose step through `compose_cites` + `from_grounding_ref`, and convert `GroundingCite`→`SourceRef` at the persistence boundary. This banks the shared-algorithm win without touching stored data.

**Build order (TDD; recommended internal-only):**
1. CLARIFY: confirm internal-only vs wire-format with PO. (If wire-format: add `+1` migration + read-compat for legacy `source_refs_json` rows.)
2. Replace `compose_grounding` body with a call to `loreweave_grounding.compose_cites` (providers return `GroundingCite`; corpus base mapped via `from_grounding_ref`).
3. Keep the `corpus_id`/license semantics: map synthetic ids → `source_type`, preserve real corpus UUID round-trip so re-cook's `UUID(corpus_id)` still resolves.
4. Adapt at the persistence boundary (`GroundingCite` → existing `SourceRef`), so `source_refs_json` is byte-stable.
5. Update/lift the existing tests (`test_grounding_composer.py`, `test_recook_strategy.py`, `test_draft_expand_strategy.py`) as parity baselines.

**AC:**
- `compose_grounding` (or its replacement) is behavior-identical on the existing parity fixtures (dedup-higher-score → stable-sort → top-K).
- `source_refs_json` persisted shape unchanged (internal-only) OR migrated + read-compat proven (wire-format).
- re-cook license resolution path (`UUID(corpus_id)`) still works for real corpus refs and still refuses synthetic ids.
- lore-enrichment unit suite green; single-service (no cross-service live-smoke needed — note it).

**Risks:** parity drift in the lift (mitigate: lift existing tests verbatim); accidentally changing persisted shape (mitigate: internal-only + a regression-lock asserting `source_refs_json` byte-stability).

---

## Item 3 — K17 entity-embedding write pipeline (L/XL)

**Goal:** generate + stamp vector embeddings on `:Entity` nodes so the **already-shipped** semantic read path works at scale (no more hand-stamping). mui#4 read path is live: `/internal/context/glossary-semantic` → `select_glossary_semantic` → `find_entities_by_vector` over `entity_embeddings_{dim}` ([context.py:157](../../services/knowledge-service/app/routers/context.py#L157), [glossary.py:221](../../services/knowledge-service/app/context/selectors/glossary.py#L221)).

**What the read path requires on each `:Entity` (verified):**
- `embedding_{dim}` vector property, indexed by `entity_embeddings_{dim}` (indexes already declared: 384/1024/1536/3072 — [neo4j_schema.cypher], KSA §3.4.B).
- `embedding_model` property (read path filters cross-model: `node.embedding_model = $embedding_model`).
- `anchor_score` (already set; two-layer `weighted_score = raw_score * anchor_score`).
- `glossary_entity_id` anchor (already set; read path keeps only anchored hits).

**The gap:** nothing WRITES `embedding_{dim}` / `embedding_model`. The merge cypher ([entities.py:205](../../services/knowledge-service/app/db/neo4j_repos/entities.py#L205)) never sets them. EmbeddingClient → provider-registry `/internal/embed` exists ([embedding_client.py](../../services/knowledge-service/app/clients/embedding_client.py)); dimension probe exists. So K17 is the producer that ties them together.

**Open questions for CLARIFY (the load-bearing design decision):**
1. **Trigger point** — three options:
   - **A. Inline at extraction** (stamp in/after `pass2_writer.merge_entity`): freshest, but couples extraction latency to the embedding provider (a slow/cold local model stalls extraction). EmbeddingClient is best-effort, so degrade-to-skip is possible.
   - **B. Dedicated batch/backfill job** (worker, processes anchored entities lacking a current-model embedding): decoupled, batchable (provider `/internal/embed` takes `texts: list`), re-runnable; needs a "dirty" signal (entity created/updated/model-changed). **Recommended primary** — embeddings are expensive + batchable + must backfill existing entities anyway.
   - **C. Event-driven** (consume `knowledge.entity_*` / glossary events → enqueue embed): incremental + decoupled, more moving parts. Could layer on top of B as the "dirty" signal.
   - **Recommended:** B (backfill + incremental drain) with the dirty-signal sourced from entity `version`/`updated_at` vs a stored `embedding_version`/`embedding_model` mismatch; optionally add C later.
2. **Embed text composition** — name + aliases + short_description (mirror `_estimate_entity_tokens` text build in [glossary.py:203](../../services/knowledge-service/app/context/selectors/glossary.py#L203)); confirm glossary `short_description` is fetched (cross-service read) or KG-local text only.
3. **Dim/model source** — per-project `embedding_model` + `embedding_dimension` (already on `Project`); route SET to `embedding_{dim}` for that project's dim. Re-embed on model change (existing `change_embedding_model` flow should enqueue a re-embed).
4. **Re-embed triggers** — name/alias/description edit (user_edited, version bump), merge_entity absorb, model change. Avoid re-embedding unchanged entities (cost).
5. **Scope of entities** — only `glossary_entity_id`-anchored (read path filters to those anyway), or all `:Entity`? Recommend anchored-first (matches read path + GraphRAG seed-graph basis), widen later if needed.
6. **Idempotency + cost guard** — UsageMeter/token accounting, batch size, max per run (inner-loop drain with safety cap pattern), best-effort degrade (provider down → leave entity unembedded, read path already degrades to FTS).

**Likely build slices (refine at PLAN after CLARIFY):**
- S1: schema/repo — `set_entity_embedding(entity_id, vector, model, dim)` + an "entities needing (re)embed" query (anchored, model-mismatch or missing).
- S2: the producer — batch embed via EmbeddingClient (project model), SET properties, metered + degrade-safe, drain-with-cap.
- S3: trigger wiring — backfill entrypoint (admin/internal route or worker job) + incremental dirty-signal (version/model mismatch; optional event consumer).
- S4: re-embed on model change + entity edit; eval/live-smoke (embed real entities → `/glossary-semantic` returns `tier=semantic`, replacing the 5-entity hand-stamp from DEFERRED 061).

**AC:**
- A fresh extraction (or a backfill run) leaves anchored `:Entity` nodes with `embedding_{dim}` + `embedding_model` set for the project's model.
- `/internal/context/glossary-semantic` returns `tier=semantic` ranked results with **no hand-stamping** (the 061 stand-in is retired).
- Cross-model safety: changing a project's embedding model re-embeds (or invalidates) so the read path never mixes vector spaces.
- Degrade-safe: provider down → extraction/job doesn't fail; read path falls back to FTS (existing behavior).
- Cost-bounded: metered + capped per run; no unbounded embed storms.
- **Cross-service live-smoke required** (knowledge ↔ provider-registry ↔ glossary) — embed real entities end-to-end, not mock-only.

**Risks:** extraction-latency coupling (mitigate: option B); cost storms (mitigate: dirty-signal + cap); cross-model vector mixing (mitigate: stamp + filter on `embedding_model`, re-embed on change); stale embeddings after edits (mitigate: version/model dirty-signal).

**Dependencies:** provider-registry `/internal/embed` (live), Neo4j vector indexes (declared), `Project.embedding_model`/`embedding_dimension` (set via `change_embedding_model`). No new external dep.

---

## Tracking

On completion of each item, update `docs/deferred/DEFERRED.md`:
- 063 → move to "Recently cleared" with the migration commit.
- 064 → either keep with re-scout note, or clear if a slice shipped.
- K17 → it's not a numbered DEFERRED row (lives in the 061 note + KSA); record completion in SESSION_HANDOFF + retire the 061 hand-stamp note.
