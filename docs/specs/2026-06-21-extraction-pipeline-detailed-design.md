# Extraction / LLM-Pipeline — Detailed Design (decisions locked)

**Status:** DESIGN COMPLETE — every open question resolved. Ready to PLAN/BUILD next session.
**Date:** 2026-06-21
**Branch:** `feat/extraction-knowledge-architecture`
**Parents:** [`architecture`](2026-06-21-extraction-pipeline-architecture.md) (rev 2, §7–§11 evaluation) ·
[`reasoning-effort`](2026-06-21-reasoning-effort-control.md) · [`raw-output-cache`](2026-06-12-extraction-raw-output-cache.md)
**Plan:** [`2026-06-21-extraction-pipeline-plan.md`](../plans/2026-06-21-extraction-pipeline-plan.md)

This doc **locks the decisions** for every open question (architecture §5 Q1–5, §10 Q6–11, the
reasoning-effort §4 Q1–5, and the Option-A/B gate), then gives the **implementable detail** —
DDL, interfaces, invariants — for each component. Decisions marked **[PO-reversible]** are my
recommendation as delegated; the rest follow directly from the evaluation (§7–§8 of the parent).

---

## 1. Decisions (locked)

| # | Question | **Decision** | Rationale |
|---|---|---|---|
| Gate | Foundation-first vs pipeline-first | **A — pipeline-first, in place** (build in translation-service; cache logic behind an interface; physical re-home deferred). **[PO-reversible]** | User-visible wins now; P1–P4 are additive + independent of where extraction is ultimately homed; the cache interface makes the re-home a move, not a rewrite. |
| Q1 | Scope | **Full epic P1–P5**, sequenced M0→M6, **built in parallel lanes** (this is what "work parallel" means). | User asked to clear all design + parallelize build. |
| Q2/Q3 | Planner home | **Shared SDK `sdks/python/loreweave_planner`** from the start. | The planner is the *same role* for extraction + glossary-translate + (future) knowledge; centralize once, no extract-later rework. |
| Q4/Q8 | Append data model | **Interim: atomic server-side JSON-array dedup-merge** now; **multi-row `entity_attribute_values` deferred** to `D-GLOSSARY-MULTIROW-ATTR-VALUES`. | The JSON atomic-merge satisfies append + idempotency (§8.2.5); only *per-list-item provenance* needs multi-row, and that can wait without blocking the append feature. Avoids a wide-blast-radius schema change in the first epic. |
| Q5 | Notification volume | **Per-batch → statistics only; job-terminal rollup → notification** (debounced, per-job dedup key). | §8.8; storm is a known anti-pattern, not a judgment call. |
| Q6 | Writeback atomicity unit | **Per-chapter** (stage per-call parses into the raw-cache; commit the chapter's writeback once, transactionally, after all its calls settle). | §8.2.7; restores per-chapter atomicity + clean resume; per-call writeback is the source of partial-visibility. |
| Q7 | Effort ↔ cache key | **Include a coarse `effort_band` (none/low/medium/high) in the cache key.** Raising effort misses → re-extracts. | Prevents replaying a low-effort parse for a high-effort request (§7.3 S3); cleaner than a force-reextract flag. |
| Q9 | Fan-out admission control | **Per-user max 2 concurrent extraction jobs; per-job max 8 in-flight LLM calls; global queue-depth guard; provider-aware rate limit** (all config, defaults here). | §8.4.5; prevents a mega-job self-DoS / starving other tenants. |
| Q10 | Raw-cache retention | **Keep-latest per cache key for function + bounded history depth K=3 for audit; auto-purge older; offload cold `raw_response` to MinIO at age > 30d (keep `parsed_entities` in DB so replay still works).** | §8.4.7; bounds unbounded growth without losing replay. |
| Q11 | Effort spend authorization | **Effort clamped to a per-grant ceiling: View→none, Edit→medium, Manage/owner→high. Any paid escalation goes through the existing confirm/cost gate, metered to the actor, using the resolved (owner's) model credential.** | §8.7 T6; a non-owner can't escalate spend on a book they don't own past their grant ceiling. |
| RE-1 | Platform default effort | **`none`** (cheapest; thinking is opt-in). | Cost on every turn; opt-in is the safe default. |
| RE-2 | Effort vocabulary | **`none / low / medium / high`** now; reserve `max`/`xhigh` for when a model exposes more. | Keep the enum small + universal. |
| RE-3 | `/no_thinking` scope | **Chat-only** (server-side parse in chat-service); other surfaces use the `reasoning_effort` param. | Smallest correct surface; MCP already has a param path. |
| RE-4 | `thinking:bool` deprecation | **Keep the alias one cycle** (normalize to `reasoning_effort` on ingest), then hard-cut. | Back-compat without carrying two fields forever. |
| RE-5 | Per-tool MCP effort exposure | **Agentic/expensive tools** (extraction, deep-research, translation) via the shared kit, identical param. | Where effort actually changes cost/quality. |

---

## 2. New data model (DDL sketch)

All new tables carry the tenant scope key `owner_user_id` (+ `book_id`) and are queried with an
E0 grant check — never `book_id` alone (§8.7).

### 2.1 `extraction_raw_outputs` (EXECUTE ledger — "the LLM produced this")
```
extraction_raw_outputs (
  id uuid pk, job_id uuid fk, owner_user_id uuid NOT NULL, book_id uuid NOT NULL,
  chapter_id uuid NOT NULL,
  chapter_content_hash text NOT NULL,        -- sha256(prepared text) = cache key dimension + truth
  chapter_chunk_idx int NOT NULL DEFAULT 0,  -- NEW: extraction chapter-chunking (§3.4)
  chapter_draft_version bigint,
  kinds_requested text[] NOT NULL,
  batch_idx int NOT NULL DEFAULT 0,
  extraction_profile jsonb NOT NULL,         -- snapshot of attribute_actions at extract time
  profile_hash text NOT NULL,                -- for the writeback idempotency key
  model_source text NOT NULL, model_ref uuid, model_name text,
  reasoning_effort text NOT NULL DEFAULT 'none',
  effort_band text NOT NULL DEFAULT 'none',  -- coarse band IN the cache key (Q7)
  input_tokens int, output_tokens int, cost_usd numeric(12,6),
  finish_reason text,                        -- M0: first-class (length/stop/...)
  raw_response text NOT NULL,                 -- verbatim (TOAST-compressed; MinIO-offloaded cold)
  parsed_entities jsonb NOT NULL,
  parse_status text NOT NULL DEFAULT 'ok',
  created_at timestamptz NOT NULL DEFAULT now()
)
-- cache lookup (partial to the live/keep set):
UNIQUE (owner_user_id, book_id, chapter_id, chapter_chunk_idx, chapter_content_hash, effort_band, batch_idx)
INDEX idx_ero_cache (owner_user_id, book_id, chapter_id, chapter_content_hash, effort_band)
```

### 2.2 `extraction_writeback_log` (WRITEBACK ledger — "this landed in glossary") **[NEW — the linchpin]**
```
extraction_writeback_log (
  id uuid pk, owner_user_id uuid NOT NULL, book_id uuid NOT NULL, chapter_id uuid NOT NULL,
  writeback_key text NOT NULL,               -- = hash(book_id, chapter_id, content_hash, kinds, profile_hash)
  content_hash text NOT NULL,
  status text NOT NULL,                       -- 'committed' | 'partial' | 'failed'
  entities_created int, entities_updated int, entities_skipped int,
  committed_at timestamptz
)
UNIQUE (writeback_key)                         -- idempotency: duplicate apply is a no-op (§8.2.3)
```
- **LLM-skip** keys on `extraction_raw_outputs` (don't re-spend). **Writeback-skip** keys on this
  log's `committed` status (re-drive POST from cached `parsed_entities` until it lands). Resume
  skips a chapter only when `committed`.

### 2.3 `extraction_batch_outcomes` (OBSERVE SSOT — events are a projection of these)
```
extraction_batch_outcomes (
  id uuid pk, job_id uuid, owner_user_id uuid NOT NULL, book_id uuid, chapter_id uuid,
  batch_idx int, chunk_idx int,
  status text NOT NULL,                        -- ok|empty_valid|truncated|validation_rejected|llm_error|writeback_failed
  finish_reason text, kinds text[],
  entities_found int, entities_written int, validation_rejected_count int,
  input_tokens int, output_tokens int, cost_usd numeric(12,6),
  error_code text, detail_redacted text,      -- redacted; NO raw_response, NO secrets (§8.7)
  event_id text NOT NULL,                      -- stable: hash(job_id, chapter_id, batch_idx, content_hash)
  created_at timestamptz NOT NULL DEFAULT now()
)
UNIQUE (event_id)                              -- redelivery-stable dedup for the projection
```

### 2.4 Glossary integrity (existing tables — added constraints)
```
ALTER glossary_entities ADD normalized_name text;  -- generated/maintained
CREATE UNIQUE INDEX uq_entity_dedup ON glossary_entities(book_id, kind_id, normalized_name)
  WHERE deleted_at IS NULL;                         -- constraint-backed dedup (§8.2.2)
CREATE UNIQUE INDEX uq_evidence_dedup ON evidences(attr_value_id, evidence_type, md5(original_text));
ALTER evidences ADD provenance_status text NOT NULL DEFAULT 'unverified';  -- exact|resolved|ambiguous|unmatched
-- populate the already-existing-but-unused columns: chapter_index, chapter_title, block_or_line, char_start, char_end
```

### 2.5 Ontology — merge policy
```
ALTER system_kind_attributes ADD merge_strategy text NOT NULL DEFAULT 'fill_if_empty';  -- safe System default
ALTER user_attributes        ADD merge_strategy text NOT NULL DEFAULT 'fill_if_empty';
ALTER book_attributes        ADD merge_strategy text NOT NULL DEFAULT 'fill_if_empty';
-- values: replace | fill_if_empty | append | overwrite | manual
-- System-tier is admin-only; users override only into their per-user/per-book tier (§8.6)
```

---

## 3. Component contracts

### 3.1 Planner SDK (`loreweave_planner`)
```python
PlanRequest(pipeline, units: list[Unit], model: ModelCaps, policy: Policy)
Unit(id, kind, est_input, est_output, splittable: bool, split_axis: "attr"|"kind"|"chunk"|None)
Policy(reasoning_effort, budget_ratio, expansion_ratio, max_units_per_call, fan_out_warn_threshold)

Planner.plan(req) -> Plan(
  calls: list[LLMCall(units, est_input, est_output, unit_ids)],
  est_llm_calls, calls_per_chapter, est_cost_range(low, expected, high),
  model_fit_warning: str | None,
  unplannable: list[Unplannable(unit, reason)],   # irreducible > context_window
  rationale: list[str])                            # WHY this split — logged + surfaced
```
- **Two-phase** (§8.4): phase 1 *normalize/split* (oversized unit → split along `split_axis`;
  irreducible → `Unplannable`); phase 2 *pack* up to `per_call_budget`.
- `per_call_budget = f(model.context_window, model.output_ceiling, effort_output_multiplier(effort), expansion_ratio)`.
- Each `LLMCall` carries stable `unit_ids` the model must echo → VALIDATE asserts 1:1 (§8.4.6).

### 3.2 Reasoning effort resolver (shared kit)
```python
resolve_effort(turn) -> ReasoningEffort     # precedence: inline-cmd > per-msg > session > model-default > platform("none")
                                            # then clamp to model capability AND to grant ceiling (View=none/Edit=medium/Manage=high)
reasoning_fields(effort, model_caps) -> dict   # {} if not reasoning-capable; else {reasoning_effort, chat_template_kwargs}
```
- Replaces `thinking_llm_fields` + composition's inline copies. `thinking:bool` normalized to
  effort on ingest. `/no_think|/think|/effort=high` parsed server-side in chat (anchored grammar,
  stripped before the model, identical strip/persist normalization).
- **Wiring fix (M-RE):** `_stream_via_gateway` must actually put `reasoning_fields(...)` into the
  provider request — today the toggle is a no-op.

### 3.3 Executor (the EXECUTE+CACHE stage)
```
for each chapter (under pg_advisory_xact_lock(hashtext(book_id))):     # per-book serialized
  for each call in plan.calls_for(chapter):
    cache-gate (inside the lock): covered = raw_outputs WHERE key matches (incl. effort_band)
       missing_kinds = requested − covered
       if missing == ∅: skip LLM, load cached parsed_entities
       else: LLM(call, reasoning_fields(effort)) → finish_reason → VALIDATE → write raw_outputs row
    record extraction_batch_outcomes row (SSOT) + outbox event in the SAME txn
  # chapter writeback barrier: one transaction, content-hash precondition
  if current_content_hash != computed_hash: abort 409 STALE_EXTRACTION
  upsert all chapter entities (constraint-backed create-or-merge, verified-clobber guard,
      atomic append-dedup) → on 200, write extraction_writeback_log(committed)
```

### 3.4 Extraction chapter-chunking (NEW — §8.4 / S2)
- Mirror translation's `split_chapter` in the extraction preprocess: `(chapter_chunk × kind-group)`
  units with an **overlap window**. Cross-chunk same-entity duplicates are deduped by the
  constraint-backed merge (§8.2.2). Provenance offsets are **chunk-relative**, mapped back to
  chapter coordinates at writeback.

---

## 4. Invariants (enforceable, cross-cutting — every milestone honors these)

**Concurrency (INV-C):**
1. WRITEBACK is per-book serialized + whole-chapter transactional.
2. Entity dedup is constraint-backed (`UNIQUE(book_id,kind_id,normalized_name) WHERE deleted_at IS NULL`) + `ON CONFLICT` create-or-merge.
3. Writeback idempotency key dedupes retry = replay = concurrent fresh.
4. Writeback is content-hash-conditional (409 on source drift).
5. Evidence + append are idempotent (unique-by-content; atomic dedup-merge).

**Trust / tenancy (INV-T):**
6. Every new table/event carries `owner_user_id`; every query is grant-gated.
7. Model-supplied provenance offsets are **hints**, validated against the real text; never persisted unverified.
8. Verified data is never clobbered — the verified-clobber guard supersedes `merge_strategy`.
9. Replay is a grant+confirm-gated **write**; cache keys are tenant-scoped forever.
10. INV-6 neutralization on stored evidence before any prompt reuse; redaction on event metadata.
11. Effort is authorized spend (grant ceiling + confirm/cost gate).

**Observability (INV-O):**
12. Outcome rows are the SSOT; events are a same-txn projection; a reconciliation sweep re-derives stats.
13. Events carry a redelivery-stable `event_id`; consumers dedup before aggregating.
14. Per-batch → stats only; job-terminal rollup → notification (debounced).

**Failure taxonomy (INV-F):**
15. Batch status ∈ {ok, empty_valid, truncated, validation_rejected, llm_error, writeback_failed}; chapter is `completed` only if every batch ∈ {ok, empty_valid}; `validation_rejected`/`truncated` persist `raw_response`.

---

## 5. Deferred (gate-passing, tracked)

- `D-GLOSSARY-MULTIROW-ATTR-VALUES` — multi-row `entity_attribute_values` for per-list-item provenance (interim JSON merge ships first).
- `D-EXTRACTION-REHOME-KNOWLEDGE` — physical move of the extraction tables to knowledge-service when `world-core-foundation` lands (the cache interface makes it a move).
- `D-RAWCACHE-MINIO-OFFLOAD` — cold `raw_response` → MinIO (parsed_entities stay in DB).

All resolved; nothing left unclear. Build sequencing → the plan doc.
