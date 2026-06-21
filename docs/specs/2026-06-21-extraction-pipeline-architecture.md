# Extraction / LLM-Pipeline Architecture — Design Spec

**Status:** DESIGN (CLARIFY) — no build yet. PO checkpoint pending.
**Date:** 2026-06-21
**Branch:** `feat/extraction-knowledge-architecture`
**Author:** session design pass after the 26-scenario test surfaced 5 architectural gaps.

---

## 0. The through-line

The five problems the user raised are **not five bugs — they are five facets of one
missing architectural layer.** Today the extraction/translation pipelines are a set of
**implicit, scattered decisions**: batching is decided in 5+ modules, failures vanish into
a 500-char string, evidence loses its source location, skip-vs-append is a blanket rule with
no reason surfaced, and the raw LLM output is thrown away.

Every mature LLM data system converges on the same explicit spine (confirmed by the
enterprise research below):

```
            ┌──────────────────────────────────────────────────────────────────┐
            │                     EXTRACTION PIPELINE                           │
  source ──▶│  PREPROCESS ─▶ PLAN ─▶ EXECUTE(+CACHE) ─▶ VALIDATE ─▶ WRITEBACK   │──▶ glossary/KG
  (chapter) │      │           │          │               │            │        │
            │      │           │          │               │            │        │
            └──────┼───────────┼──────────┼───────────────┼────────────┼────────┘
                   │           │          │               │            │
                   ▼           ▼          ▼               ▼            ▼
                 (P3 provenance carried end-to-end)   (P4 merge policy)
                   └────────────────── OBSERVE (P1) ──────────────────┘
                                  (every stage emits a structured event)
```

- **P2 Planner** owns the `PLAN` stage — one explicit role decides *how many LLM calls* and *what each contains*.
- **P5 Raw cache** is the `EXECUTE(+CACHE)` stage — idempotent, replayable, cost-saving.
- **P3 Provenance** is metadata that the `PREPROCESS` stage stamps and every later stage carries, so `WRITEBACK` can land traceable evidence.
- **P4 Merge policy** is the `WRITEBACK` contract — explicit per-attribute skip/fill/append/overwrite with a recorded reason.
- **P1 Observability** is the cross-cutting `OBSERVE` lane — every stage emits a structured event to the (already-built) statistics + notification services.

This spec designs each, then sequences them. **None of these is a code-level fix; each is a
contract.** That is why the user is right to treat them as architecture.

---

## 1. Current state (evidence map)

> Full file:line references in the four investigation reports captured this session. Summary:

| Area | What EXISTS | What is MISSING (the gap) |
|---|---|---|
| **P1 Observability** | `statistics-service` (Redis-stream consumer, book/translation/voice events) + `notification-service` (RabbitMQ `loreweave.events`, consumes LLM `TerminalEvent`, writes `notifications`). Extraction emits a **job-level** terminal event. | Extraction failure detail is a single **500-char `error_message` blob** — no structured `finish_reason` (`length`/truncation!), no per-batch/per-kind granularity. **Statistics never ingests extraction outcomes.** Per-chapter failures live only in `extraction_chapter_results.error_message`, queryable by nobody. |
| **P2 Planner** | `plan_kind_batches` (extraction), `build_batch_plan`+`compute_input_budget` (translation, **model-aware**), `split_chapter`, `segment_blocks`, glossary per-entity loop. | **No single owner.** Batching decided in **5+ modules** with **inconsistent model-awareness** (translation reads `context_window`; extraction hardcodes `SCHEMA_TOKEN_BUDGET=2000`, `MAX_KINDS_PER_BATCH=3`, ignores the model). Glossary translation = **1 LLM call per entity** (1000 attrs ⇒ ~1000 calls). No unit abstraction (kind vs chapter vs entity vs attribute). |
| **P3 Provenance** | `evidences` table has `chapter_id, chapter_index, block_or_line, chapter_title, original_text`. | Extraction writes **only `chapter_id` + `original_text`**. `chapter_index`, `chapter_title`, `block_or_line` are **never populated** → you cannot trace an evidence quote to a paragraph/line. The model is never asked for, and the pipeline never carries, an offset. |
| **P4 Merge policy** | Explicit `fill\|overwrite\|skip` action map (`AttributeActions[kind][attr]`); `extraction_audit_log` for overwrites. | `fill` **silently skips** when a value already exists (the "new power in ch.3" case) — **no append**. **No multi-value/append policy** in the ontology schema (list attrs are JSON arrays replaced wholesale). **Skip reason never surfaced** to the user. No per-attribute cardinality/merge-strategy column. |
| **P5 Raw cache** | **Full spec + plan already exist** (`docs/specs/2026-06-12-extraction-raw-output-cache.md` + plan): `extraction_raw_outputs` table, content-hash cache-gate, replay endpoint. | **Not built** — deferred as `D-EXTRACTION-RAW-OUTPUT-CACHE`, PO-gated behind `world-core-foundation` → extraction-pipeline refactor. Raw LLM response is **discarded after parse** today. No prompt-caching either. |

---

## 2. What enterprise LLM systems do (research, 2025–2026)

| Theme | Industry pattern | Source signal |
|---|---|---|
| **Observability** | Trace *every* LLM request as a span (prompt, response, tool calls, **finish_reason**, tokens, cost, latency); aggregate error-rate/cost/latency metrics; **real-time alerts on specific failure modes** (truncation, quota, content-filter). | Datadog / Splunk / MLflow LLM-observability guides. |
| **Planner / batching** | A **token-budget scheduler**: preprocess → batch within the *model's actual* context limit → execute → validate. Dynamic micro-batching by prompt length, not fixed counts. | "Dynamic Micro-Batch and Token-Budget Scheduling" (Preprints/MDPI); "5 Steps to Cost-Efficient LLM Pipelines". |
| **Provenance** | **Grounding** = every extracted claim is traceable to a *specific, verifiable location* in the source. Anchor-constrained extraction with provenance tracking; claim→evidence→citation→section stored structurally. | PyMuPDF "Grounding in document extraction"; "Grounded KG Extraction… with Provenance Tracking" (MDPI); PaperTrail (arXiv). |
| **Incremental merge** | Allow duplicates + **semantic** resolution; LLM modules **merge** subgraphs and **resolve conflicts** rather than blanket-skip; change-signaling strategies for evolving sources. | iText2KG (arXiv); "Incremental Multi-source Entity Resolution"; KG-construction surveys. |
| **Caching** | Layered: **prompt/prefix caching** (Anthropic ~90% cost cut), **semantic caching** (GPTCache), and **raw-output persistence** for replay. | Anthropic prefix caching; Redis/AWS prompt-caching guides; GPTCache. |

**Takeaway:** our scattered SDKs already implement *pieces* (token estimators, a model-aware
budget calc, a confirm/cost spine, a terminal-event bus). The missing work is **composition** —
a named pipeline that wires the pieces into the spine above, with the planner and provenance as
first-class roles.

---

## 3. Proposed architecture

### 3.1 The unifying component: a Pipeline Planner + Executor

Introduce **one** explicit module per pipeline family that owns PLAN+EXECUTE, replacing the
scattered ad-hoc batching. It is a *library role* (an SDK), not necessarily a new service.

```
PlanRequest {
  pipeline: "glossary_extract" | "glossary_translate" | "chapter_translate"
  units:    [Unit]                  # the atomic work items (see §3.2)
  model:    {source, ref, context_window, output_ceiling}   # RESOLVED, never hardcoded
  policy:   {budget_ratio, expansion_ratio, max_units_per_call, output_per_unit_est}
}
        │
        ▼
Planner.plan(req) -> Plan {
  calls: [ LLMCall { units[], est_input_tokens, est_output_tokens } ]
  est_llm_calls, est_cost_usd        # one place owns the cost estimate
  rationale: [ "why this split" ]    # EXPLICIT, logged + surfaced
}
        │
        ▼
Executor.run(plan) -> for each call:  cache-gate (P5) → LLM → validate → emit event (P1)
```

**Design rules:**
- The planner is **model-aware by construction** — `context_window` and `output_ceiling`
  are *inputs*, never literals. (Fixes the extraction-ignores-the-model defect that caused
  the 26-scenario truncation.)
- The planner emits an explicit **`rationale`** (why N calls, why these units grouped) →
  this is logged and attached to the job, killing the "implicit batching" problem.
- **One cost estimator.** The planner's `est_cost_usd` is the single source feeding the
  existing confirm/cost-gate spine — no more three disconnected estimators.

### 3.2 The unit abstraction (answers "how many calls for 1000 attrs across 30 kinds")

Define a `Unit` as the smallest independently-extractable/translatable thing, with an
**estimated output size**. The planner packs units into calls under the output budget:

| Pipeline | Unit | Packing rule |
|---|---|---|
| glossary_extract | (chapter × kind-group) | pack kinds until `Σ output_est ≥ output_budget` OR `max_kinds` |
| glossary_translate | (entity, or attribute for very wide entities) | pack entities/attrs until input+output budget — **not 1-per-entity** |
| chapter_translate | block-batch | already correct (`build_batch_plan`) — adopt as the reference impl |

So **1000 attrs / 30 kinds** is no longer "1000 calls": the planner packs by token budget
against the model's real window. The *number* becomes a computed, explainable output of one
function — `Plan.est_llm_calls` — not an emergent property of three loops.

### 3.3 P1 — Observability wiring (foundation exists; wire it)

The services are built; the work is to **emit structured stage events** and route them.

1. **Structured outcome, not a blob.** Replace the 500-char `error_message` with a typed
   `BatchOutcome { stage, status, finish_reason, kinds, tokens, cost, error_code, detail }`
   per LLM call. `finish_reason=length` (truncation) becomes a **first-class, queryable**
   signal — the exact thing that was invisible in the 26-scenario run.
2. **Statistics ingestion.** Publish an `extraction.batch_completed` / `…batch_failed`
   outbox event (the outbox→Redis relay already exists) → statistics-service aggregates
   `extraction_failure_rate`, `truncation_rate`, `avg_calls_per_chapter`, `cost_per_book`.
3. **Notification on real failure.** The notification-service already consumes LLM terminal
   events; enrich the extraction terminal event so a user gets *"Extraction finished: 14
   entities, 1 batch truncated (raise model or it will under-extract)"* instead of silence.
4. **Alert-worthy failure modes** (truncation, quota, parse-fail) are distinguished by
   `error_code`, enabling the dashboards the research describes.

### 3.4 P3 — Evidence provenance (schema exists; populate + extend)

1. **Carry the offset end-to-end.** PREPROCESS already produces the chapter text; have it
   also produce a **block/paragraph index map** so each extracted quote can be located.
   Ask the model to return, per evidence, the **source block index** (cheap: it already
   sees the text); fall back to a substring search of `original_text` in the prepared text
   to compute `block_or_line` when the model omits it.
2. **Populate the columns that already exist.** Write `chapter_index`, `chapter_title`,
   `block_or_line` on the evidence INSERT (currently omitted). Zero schema change for these.
3. **Add a stable source pointer** if needed: `{book_id, chapter_id, chapter_draft_version,
   block_index, char_start, char_end}` — so an evidence remains traceable even after the
   chapter is edited (version-stamped, mirrors the raw-cache spec's `chapter_content_hash`).
4. Result: every evidence answers "book? chapter? paragraph?" — the grounding the research
   treats as table stakes.

### 3.5 P4 — Explicit merge policy (the append problem)

Today merge is a blanket `fill|overwrite|skip` with no append and no reason. Make it a
**declared per-attribute policy** on the ontology:

1. **New attribute property `merge_strategy`** (on system/user/book attribute defs):
   `replace` (scalar, default) · `fill_if_empty` · `append` (multi-value) · `overwrite` ·
   `manual` (never auto-write; queue for review).
2. **`append`** is the missing case: a character's new power in ch.3 is **added** to the
   list (dedup by normalized value), each with its own provenance evidence — not skipped.
   This needs the value model to support multi-row (or a typed JSON-array merge), which the
   schema does **not** have today (single `entity_attribute_values` row per attr) → this is
   the one item with a real **data-model change**.
3. **Surface the reason.** Every skip records `{attr, reason: "value_present|verified|policy_skip|tombstone", existing_value}` and returns it in the extraction result + the
   batch outcome event — so "why did it skip?" is always answerable. (No more silent skips.)
4. Aligns with the research's "merge & resolve conflicts, don't blanket-skip" finding.

### 3.6 P5 — Raw extraction cache (un-defer; the spec is ready)

The design already exists (`2026-06-12-extraction-raw-output-cache.md`): an
`extraction_raw_outputs` append-only table keyed by `(book_id, chapter_id,
chapter_content_hash, kinds)`, a **cache-gate** that skips the LLM when content+kinds are
unchanged, and a **replay** endpoint that re-applies cached `parsed_entities` under a new
attribute-action profile at **zero LLM cost**.

It slots exactly into the `EXECUTE(+CACHE)` stage of §3.1. **It also gives P1/P3/P5 for
free**: the raw response is the ultimate provenance + the debugging artifact + the
truncation evidence. **Recommendation: promote it from deferred to in-scope as the executor's
storage layer** — but see §4 (it was PO-gated behind `world-core-foundation`).

---

## 4. Sequencing + the `world-core-foundation` reconciliation

The raw-cache (P5) was deferred **behind** a larger `world-core-foundation` → extraction
re-home refactor (extraction may move to `knowledge-service`). That gate is real and PO-owned.
Two honest options for the PO:

- **Option A — Pipeline-first (recommended).** Build the planner+observability+provenance+merge
  layer (P1–P4) *in place* in translation-service now (they're additive, low-blast-radius, and
  independent of where extraction is ultimately homed). Defer only P5's *physical table
  placement* to the re-home, but build P5's *cache-gate logic* against an interface so it moves
  cleanly. Delivers the user-visible wins (no silent failures, no truncation, traceable
  evidence, append) without waiting on the big refactor.
- **Option B — Foundation-first.** Honor the original gate: do `world-core-foundation` first,
  then build the whole spine in its final home. Cleaner end-state, much longer lead time.

This spec does **not** self-authorize crossing the PO gate — it surfaces the choice.

### Suggested milestone order (Option A)

| M | Scope | Blast radius | Depends on |
|---|---|---|---|
| **M1** | P1 structured `BatchOutcome` + emit to stats/notification | low (additive events) | — |
| **M2** | P2 unify the planner (start with glossary_extract + glossary_translate; reuse `build_batch_plan` as the reference) | medium | M1 (events) |
| **M3** | P3 evidence provenance (populate existing cols + offset map) | low–medium (1 INSERT + preprocess) | — |
| **M4** | P4 `merge_strategy` + `append` + skip-reason | **high (data-model change)** → its own plan + migration | M3 (provenance per value) |
| **M5** | P5 raw-cache executor (per existing spec) | medium | M2 (executor seam), PO gate |

---

## 5. Open questions for the PO (CLARIFY checkpoint)

1. **Gate:** Option A (pipeline-first, in place) or Option B (foundation-first)? This decides
   everything downstream.
2. **Scope of this effort:** all of P1–P5 as one epic, or land P1+P3 (cheap, high-value:
   observability + provenance) first and treat P2/P4/P5 as follow-on epics?
3. **Planner home:** a shared SDK (`sdks/python/loreweave_planner`) reused by translation +
   knowledge, or a translation-service-internal module for now?
4. **P4 data model:** are multi-value/append attributes worth the `entity_attribute_values`
   schema change now, or is "append into the JSON-array value with dedup" an acceptable
   interim (no migration, but weaker provenance per list item)?
5. **Notification volume:** per-batch failure notifications could be noisy — per-job summary
   only, or per-batch for truncation/quota specifically?

---

## 6. Deferred-rule note

Per the tightened defer rule (CLAUDE.md), the items here qualify to defer/plan because they
are **large/structural** (gate #2) and the cross-team gate (#1) — they are explicitly *not*
the "small in-scope bug" class that must be fixed inline. This doc is the "serious plan" that
the rule requires before such work proceeds.
