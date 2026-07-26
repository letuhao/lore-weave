# Extraction-branch deferral clearing ("sạch nợ") — DETAILED DESIGN + BATCH-FIX PLAN

Status: **DESIGN + PLAN — awaiting approval** · 2026-06-22 · branch `feat/extraction-knowledge-architecture`
Goal: clear EVERY deferral this branch created — no permanent defers. Each item gets a concrete
design + disposition (fix-now batch, own-epic spec, or blocked-with-named-prerequisite).
Backed by 4 parallel code investigations (translation quick-wins, admission-control, the
agentic-effort inventory, and the two structural epics).

## Already cleared this session
`D-CACHE-REPLAY`, `D-RAWCACHE-MINIO-OFFLOAD`, keep-K retention, `D-CACHE-PLANNER-WIRING` (Part
1+2), `D-SDK-DISTRIBUTION-SPLIT`, `D-MERGE-APPEND/STRATEGY-ONTOLOGY/RESTORE-VERIFY`,
`D-OBS-RECONCILE-SWEEP`, `D-OBS-BATCH-OUTCOME-PROJECTION`, `D-PROV-EVIDENCE-INV6-REUSE`,
`D-PROV-MODEL-OFFSET-HINT`, `D-EXTRACTION-FND-E2E-SMOKE`.

## The remaining six — corrected triage (post-investigation)

| ID | Was assumed | Investigation found | Size | Disposition |
|---|---|---|---|---|
| **D-RE-EFFORT-COST-ESTIMATE** | XS quick win | confirmed; planner grows output with effort; effort available in both callers | **XS** | **Batch — Wave 1** |
| **D-RE-WORKER-GRADED-EFFORT** | M | already plumbed to the job boundary, truncated to a bool there; SDK `reasoning_fields()` ready | **M** (+trivial migration) | **Batch — Wave 1** |
| **D-CACHE-MODEL-KEY** | S | `model_ref` already on the row; opt-in force-refresh (don't add to key — would fragment) | **S** | **Batch — Wave 2** |
| **D-EXTRACTION-ADMISSION-CONTROL** | "covered by P5" | **P5 does NOT touch extraction** — real (small) per-user job-count gap | **S** | **Batch — Wave 3** |
| **D-RE-OTHER-AGENTIC-EFFORT** | M-L cross-service Go | named target (`glossary_deep_research`) has NO LLM; real gap = `kg_build_graph`+`kg_build_wiki` (knowledge, Python) | **M** | **Batch — Wave 4** |
| **D-EXTRACTION-REHOME-KNOWLEDGE** | XL keep-deferred | XL + **blocked on `world-core-foundation`**; design = co-located move, NOT HTTP proxy | **XL** | **Own epic — blocked; design ready** |
| **D-GLOSSARY-MULTIROW-ATTR-VALUES** (pre-existing) | XL keep-deferred | buildable; concrete child-table design | **XL** | **Own epic — spec + plan** |

---

## PART A — the batch-fixable four (this branch, ~one continuous run)

### Wave 1 — graded reasoning effort, end-to-end (the effort-control theme)
Graded effort is clamped at mint + re-clamped at confirm, but `CreateExtractionJobPayload` only
carries `thinking_enabled: bool`, so `low`/`high` collapse to `medium` before the worker. Finish it.

**D-RE-WORKER-GRADED-EFFORT (M, +migration)** — exact seams:
1. `routers/extraction.py`: add `reasoning_effort: str = "none"` to `CreateExtractionJobPayload`
   (keep `thinking_enabled` as a deprecated alias); in `_create_extraction_job_core` resolve
   `effort = payload.reasoning_effort or ("medium" if payload.thinking_enabled else "none")` and
   add it to `job_params`, the INSERT, and the `extraction.job` message.
2. `routers/actions.py` confirm branch: pass `reasoning_effort=effort` into the payload (instead
   of only the bool downcast).
3. `migrate.py`: `ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS reasoning_effort TEXT NOT
   NULL DEFAULT 'none'` (idempotent; `extraction_raw_outputs` already has this column).
4. `extraction_worker.py`: read `reasoning_effort` from the message → thread to
   `_process_extraction_chapter` → `effort_band_for(thinking_enabled, reasoning_effort)` (the
   param already exists) → replace `thinking_llm_fields(enabled=…)` with
   `loreweave_llm.reasoning.reasoning_fields(ReasoningDirective(effort=…))`.
5. `llm_thinking.py`: deprecate once the worker is off it (grep — `glossary_translate_worker.py`
   still calls it; leave it until that's migrated, don't delete blind).
- Tests: low/high → distinct `reasoning_fields` output + distinct cache `effort_band`.

**D-RE-EFFORT-COST-ESTIMATE (XS)** — depends on Wave-1's effort resolution (the MCP side already
has it):
- `extraction_prompt.py` `estimate_extraction_cost`: add `reasoning_effort="none"` →
  `Policy(max_units_per_call=1, reasoning_effort=reasoning_effort)` (keep `max_units_per_call=1`).
- `mcp/server.py` + `routers/extraction.py`: pass the clamped effort at the two call sites.
- Test: estimate output tokens grow none→high.

### Wave 2 — cache correctness
**D-CACHE-MODEL-KEY (S)** — opt-in force-refresh (NOT model-in-key, which would permanently
fragment the cache on every model switch):
- `extraction_cache.py` `get_cached_batch`: add `model_ref` to the SELECT + return dict.
- `extraction_worker.py` cache-hit gate: if `settings.extraction_cache_bust_on_model_change` and
  the row's `model_ref` ≠ the resolved `model_ref` → treat as a miss (live call).
- `config.py`: `extraction_cache_bust_on_model_change: bool = False` (default off keeps the
  content-addressed default). No migration (`model_ref` already a column).
- Test: model-switch → miss when flag on, hit when off (in `test_extraction_cache.py`).

### Wave 3 — admission control (the P5 correction)
**D-EXTRACTION-ADMISSION-CONTROL (S)** — P5 (`p5_owner_cap`) is translation-chapter-only; it
places ZERO bound on extraction. Within a job chapters are sequential (1 in-flight); ACROSS jobs
per user is unbounded, and each concurrent job holds HTTP clients + contends the glossary per-book
`pg_advisory_xact_lock` (pool pressure). Smallest correct guard:
- `routers/extraction.py` `_create_extraction_job_core`, before the INSERT:
  `SELECT count(*) FROM extraction_jobs WHERE owner_user_id=$1 AND status IN ('pending','running')`
  → if `>= settings.extraction_max_concurrent_jobs_per_user` (new config, default 2) → 429.
  (translation owns `extraction_jobs`, so no cross-service call.)
- Test: the (N+1)-th concurrent job for one user → 429; a different user unaffected.

### Wave 4 — agentic-effort, the REAL targets (knowledge-service) — FULLY MAPPED 2026-06-22
**D-RE-OTHER-AGENTIC-EFFORT** — reframed twice by investigation + a deep code map.
`glossary_deep_research` drives no reasoning LLM (web-search; agent summarizes) → **won't-fix,
one-line rationale**. The real unclamped reasoning-LLM agentic tools are `kg_build_graph` +
`kg_build_wiki` in **knowledge-service**. The deep map found this is **broader than the M/L the
investigation guessed**, and splits exactly like translation did (clamp ≠ worker-honoring):

**SIZE: L (knowledge-service clamp+store) + a worker-ai follow-up.** The actual extraction worker
is **worker-ai (a separate service)** — so the effort being HONORED by the LLM is `D-KG-WORKER-
GRADED-EFFORT` (a NEW follow-up, the exact analog of translation's `D-RE-WORKER-GRADED-EFFORT`
that Wave 1 cleared). What clears D-RE-OTHER-AGENTIC-EFFORT itself = the **param + clamp + store**
in knowledge-service. Critically, **the clamp is dead code unless the effort is STORED on the job**
(else the clamped value is discarded) — so the job-storage L is not optional.

**Exact seams (mapped — ready to execute):**
1. **Local clamp helper** `services/knowledge-service/app/effort.py` — `clamp_effort_to_grant`
   mirroring `translation-service/grant_deps.py` (ceiling: NONE/VIEW→none, EDIT→medium,
   MANAGE/OWNER→high; rank none<low<medium<high), on `loreweave_grants.GrantLevel` (already
   imported, IntEnum NONE..OWNER). LOCAL, not an SDK promotion — avoids re-triggering the
   `D-SDK-DISTRIBUTION-SPLIT` landmine; ~15-line dup of translation's, acceptable.
2. **Grant-level resolver** `graph_schema_tools.py` — add `_resolve_project_owner_and_level(ctx,
   need) -> (UUID, GrantLevel)` beside `_resolve_project_owner` (today returns owner only; for an
   owner caller `ctx.user_id == owner` → level = `GrantLevel.OWNER`; else the resolved `lvl`).
3. **Mint clamp** `build_tools.py` — `reasoning_effort` arg on `KgBuildGraphArgs` + `KgBuildWikiArgs`;
   `_handle_kg_build_*` clamp via the new resolver → store in the token `params`.
4. **Confirm re-clamp** `kg_actions.py` — thread `caller` + `gc` into `_confirm_build_graph` /
   `_confirm_build_wiki` (call sites L351/L353) + re-resolve the grant + re-clamp
   `params.reasoning_effort` before the effect (defense-in-depth vs a grant downgrade in the
   token TTL — the load-bearing security property, mirror translation `actions.py`).
5. **Carry + store (graph)** `build_graph_effect.py` `BuildGraphParams.reasoning_effort` →
   `apply_build_graph` passes it into `StartJobRequest` (`routers/public/extraction.py` L179) →
   `_start_extraction_job_core` (L506) → `ExtractionJobCreate` (L777) → `_create_and_start_job`
   INSERT → **migration: `extraction_jobs.reasoning_effort TEXT DEFAULT 'none'`** → `ExtractionJob`
   model (re-read).
6. **Carry + store (wiki)** `build_wiki_effect.py` `BuildWikiParams.reasoning_effort` → the wiki-gen
   job path (its own storage; map at build time).
7. **Tests** — clamp unit (EDIT caps high→medium); mint stores clamped; confirm re-clamps a
   downgraded grant; job row carries the effort.
8. **Follow-up rows:** `D-KG-WORKER-GRADED-EFFORT` (worker-ai reads `extraction_jobs.reasoning_effort`
   → `reasoning_fields` on the LLM call) + optionally promote the now-duplicated clamp to
   `loreweave_grants` once the SDK-distribution split is resolved cluster-wide.
- **Live smoke (≥2 services):** `kg_build_graph` mint→confirm exercises knowledge extraction +
  provider-registry; assert the job row stores the clamped effort.
- **DECISION POINT:** ~10 files across knowledge-service + a confirm-token SPEND gate — a focused
  session is recommended over a tail-of-marathon grind. Per CLAUDE.md (don't rush load-bearing
  work), this earns its own run even though the user opted to "proceed".

**Batch-A sizing:** Waves 1-3 = translation-only (XS+M+S+S), DONE + pushed. Wave 4 = knowledge-
service L (clamp+store) + the worker-ai follow-up.

---

## PART B — the two XL epics (own spec + plan; designed here, built separately)

### D-GLOSSARY-MULTIROW-ATTR-VALUES (XL — glossary-schema epic, NOT this branch)
Today a list attribute is a JSON array in `entity_attribute_values.original_value`; `confidence`
is row-level, tombstones are entity-level (`ai-rejected` tag) — so no per-item provenance/verify/
tombstone. **Design (ready for its own spec):**
- New child `entity_attribute_value_items(item_id, attr_value_id FK, item_value, item_norm,
  sort_order, confidence, status active|tombstoned, source_chapter_id, …)`,
  `UNIQUE(attr_value_id, item_norm)`. Scalars keep `original_value` with zero items.
- `original_value` becomes a **write-synced denormalized cache** of the active list → readers
  (export/RAG/wiki/pipeline) keep working unchanged; only export/wiki opt into item-awareness
  where `tombstoned` exclusion is the product win.
- Append = `INSERT … ON CONFLICT (attr_value_id, item_norm) DO NOTHING` per item under the
  existing writeback lock; verified-clobber + tombstone become per-item; per-item verify/reject
  are new endpoints.
- Migration `0035`: additive table + **Go backfill** (reuse `normalizeEntity`/`parseListValue` —
  SQL can't reproduce NFC+ICU-lowercase); writers-first cutover, readers stay on the cache.
- Top risks: cache divergence (single `rebuildItemsCache` helper + trigger backstop), normalize
  parity, the verified-guard scalar-vs-item branching, merge-entity item union, online cutover
  ordering.
- **Disposition:** real, buildable epic with a wide reader blast radius across glossary +
  cross-service writeback. Needs its own `docs/specs/` + `docs/plans/` and likely its own branch.
  It is pre-existing (not extraction-branch-created), so it does not block this branch closing.

### D-EXTRACTION-REHOME-KNOWLEDGE (XL — BLOCKED on a prerequisite)
knowledge-service has NO equivalent raw-output cache; it has its OWN KG-triple extraction (a
different pipeline). Re-homing means relocating the WHOLE translation glossary-extraction cluster
(worker + `extraction_jobs`/`extraction_chapter_results`/`extraction_raw_outputs` + replay +
blobstore + broker/dispatch/billing/glossary-writeback) into knowledge-service so the cache
get/put stay **in-process** — the HTTP cache-proxy variant is **rejected** (two cross-service RTTs
per batch on a best-effort hot path + an uptime dependency = strictly worse than today).
- **Hard dependency:** the cache spec (`docs/specs/2026-06-12-extraction-raw-output-cache.md`)
  marks the placement "superseded in spirit by `world-core-foundation`" — a prerequisite
  boundary-refactor that decides where glossary-extraction ultimately lives. **Building before it
  risks re-homing into a placement the refactor then re-decides.**
- **Disposition (honest):** this cannot be truly "cleared" now without first doing
  `world-core-foundation`. The design above is ready; the clear is **contingent on that
  prerequisite**, which becomes the tracked blocker (not a vague defer). Recommendation: record
  the design + the named prerequisite; revisit when `world-core-foundation` runs. The interface
  seam already delivered the only value that mattered now (the future move is a localized swap).

---

## Recommended execution order
1. **Batch-A on THIS branch:** Wave 1 (graded effort + estimate) → Wave 2 (cache-model-bust) →
   Wave 3 (admission cap). All translation-service, each its own VERIFY + `/review-impl` + commit.
2. **Wave 4 (knowledge effort-clamp):** decide branch placement — its own branch (touches
   knowledge-service) vs here. Shared-SDK promotion first, then the two tools + live smoke.
3. **D-GLOSSARY-MULTIROW-ATTR-VALUES:** schedule as its own glossary epic (spec + plan + branch).
4. **D-EXTRACTION-REHOME-KNOWLEDGE:** parked behind `world-core-foundation` with the design ready;
   the prerequisite is the new tracked item (a real dependency, not a TODO).

## Outcome
Every extraction-branch deferral now has a concrete design and a disposition: four fixed in a
batch on this branch, one (knowledge effort) a small Python milestone, two XL epics with full
designs (one buildable-as-its-own-epic, one blocked on a named prerequisite). Nothing is a vague
"come back later" — the debt is itemized, designed, and sequenced.
