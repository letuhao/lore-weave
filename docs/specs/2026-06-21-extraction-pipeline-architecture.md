# Extraction / LLM-Pipeline Architecture — Design Spec

**Status:** DESIGN (CLARIFY) — no build yet. PO checkpoint pending.
**Date:** 2026-06-21 (rev 2 — hardened after a 4-lens adversarial evaluation; see §7–§11)
**Branch:** `feat/extraction-knowledge-architecture`
**Author:** session design pass after the 26-scenario test surfaced 5 architectural gaps.

> **Rev 2 note:** §1–§6 are the original decomposition (still valid). §7 is an adversarial
> scenario evaluation (concurrency / failure / scale / tenancy) that found the decomposition
> sound but specced at *single-writer, happy-path* altitude — every real failure lives in the
> **seams between stages**. §8 adds the contracts that close those seams (two-ledger model,
> concurrency, batch taxonomy, two-phase planner, provenance trust, merge integrity, tenancy).
> §9 revises the milestones, §10 the open questions. **The 4 HIGH findings in §7 must be
> resolved in the design before any BUILD.**

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

---

## 7. Architecture evaluation — adversarial scenarios (rev 2)

Four independent evaluators stress-tested §1–§6 against the **live code** (not just the spec)
through distinct lenses. The decomposition held; **the failures are all in the seams the spec
left unspecified.** Verdicts: **HOLDS** (design covers it) · **GAP** (under-specified, fixable
in spec text) · **BREAKS** (would lose/corrupt data as written). Edge cases that matter:

### 7.1 Concurrency & idempotency

| # | Scenario (incl. edge) | Verdict | The seam |
|---|---|---|---|
| C1 | Two jobs extract the **same** chapter concurrently (double-click / broker redelivery while in-flight). Both `findEntityByNameOrAlias` miss, both CREATE "Lin Feng". | **BREAKS** | `glossary_entities` has **no `UNIQUE(book_id,kind_id,normalized_name)`**; dedup is a lock-free read-then-write on the pool → duplicate entities + duplicate Neo4j nodes. |
| C2 | Alias dedup: job A writes entity w/ alias "Brother Lin"; job B extracts "Brother Lin" as a primary name before A commits. | **BREAKS** | Alias match is an app-layer JSON scan — **unprotectable by a constraint**. Needs per-book write serialization. |
| C3 | A 40-entity writeback fails at entity #25. | **BREAKS** | `bulkExtractEntities` is **non-transactional**; #1–24 already committed; retry re-POSTs all 40 → duplicate `evidences` (no content-unique), double counters. |
| C4 | Chapter **edited mid-flight**: slow job A (old hash H1) finishes *after* job B (new hash H2) and overwrites B's current entities with stale data; evidence offsets point into text that changed. | **BREAKS** | No **content-hash precondition** on writeback; last-writer-wins by completion order, not content recency. |
| C5 | Partial-kind cache race: job A wants {char,loc}, job B wants {loc,faction}; both read `covered_kinds=∅` → both call LLM for `loc`. | **GAP** | The cache-gate `covered_kinds` check-then-act is a **TOCTOU**; defeats the cost-saving + writes divergent `loc` entities. |
| C6 | `append` (P4): ch.3 and ch.7 both append a power to the same character via parallel jobs. | **GAP** | JSON-array append is read-modify-write on one cell → **lost update**; no dedup-by-normalized-value key. |
| C7 | Observability: a truncated batch emits `batch_failed`, then the message redelivers and re-emits. | **GAP** | Outbox relay is **at-least-once**; stats double-count truncations → false alerts. No stable `event_id`. |

### 7.2 Failure & partial completion

| # | Scenario | Verdict | The seam |
|---|---|---|---|
| F1 | Cache HIT for {A,B}, but the **writeback fails** (glossary 500). Job re-runs later: cache-gate sees {A,B} covered → **skips the LLM forever**, entities never land. | **BREAKS** | The raw-cache conflates **"LLM produced this"** with **"this is in glossary."** A failed writeback is permanently masked → **data-loss amplifier.** |
| F2 | Plan = 5 batches; 1–3 write, crash before 4–5; chapter stuck `running`. | **BREAKS/GAP** | Resume is **chapter-granular** (re-does 1–3, re-spends + double-writes). Partial entities sit in glossary unmarked. |
| F3 | LLM returns 15 entities, VALIDATE rejects **all** (kind mismatch) → `all_entities=[]` → chapter marked `completed` with 0. | **GAP** | **No taxonomy** distinguishing `empty_valid` from `validation_rejected` from `truncated` from `llm_error` — a total failure reads as clean success (the literal 26-scenario bug). |
| F4 | Provenance: model returns a **paraphrased** quote that doesn't substring-match, or matches **two** paragraphs. | **GAP** | §3.4 fallback "substring search" silently picks the **first** match → confidently-wrong citation. No offset taxonomy (exact/resolved/ambiguous/unmatched). |
| F5 | Outbox relay down when a batch fails → failure lives only in `extraction_chapter_results.error_message` "queryable by nobody." | **GAP** | OBSERVE reproduces the exact gap it claims to close. Events must be a **projection of an SSOT row**, with reconciliation. |
| F6 | 50 chapters each truncate one batch. | **GAP** | Per-batch → notification = **50 notifications.** §5-Q5 defers it; needs a default (per-batch→stats only; terminal rollup→notification). |

### 7.3 Scale, cost & model limits

| # | Scenario | Verdict | The seam |
|---|---|---|---|
| S1 | One entity / one kind whose **schema alone > context window**. | **BREAKS** | The `Unit` is "smallest indivisible thing"; planner only packs **up**, never **splits down** → 1-unit call that truncates, or a loop. |
| S2 | A 40k-token chapter vs a 32k model. | **BREAKS** | Extraction has **no chapter-chunking** — `split_chapter` lives in the *translation* path only. Packing kinds down to 1 still sends the whole chapter. |
| S3 | Re-run at `effort=high` a book that fit at `effort=none`. | **BREAKS** | The two specs aren't composed: the planner's output budget has **no effort term**; high effort 2–4× output → re-truncation. Cache key is effort-blind → replays a low-effort parse for a high-effort request. |
| S4 | 4k-context BYOK model, 500 ch × 30 kinds → ~15,000 calls. | **GAP** | "Model-aware" is *correct* but catastrophic; no **fan-out sanity floor** / model-fit warning / wall-clock estimate. |
| S5 | glossary_translate packs attrs from entities A,B,C into one call. | **GAP (correctness)** | Packing a single blob → **result re-attribution** can write B's translation onto A. Sold as cost win, it's a correctness risk without a `unit_id` echo + validation. |
| S6 | 1,500-call job; price drifts +30% mid-run (H14). | **GAP** | One PLAN-time estimate; no **price snapshot** or budget-breach re-confirm → re-confirm storm or silent overspend. |
| S7 | Book re-extracted N times; append-only raw rows × per-call granularity. | **GAP** | "~50MB/book" is optimistic by an order of magnitude; **retention is manual only** → unbounded growth; hot index bloats. |

### 7.4 Tenancy, security & data integrity

| # | Scenario | Sev/Verdict | The seam |
|---|---|---|---|
| T1 | Model **supplies** the source block index/offset; it's hallucinated/out-of-range/points at the wrong paragraph. | **HIGH / BREAKS** | Model output is **untrusted (INV-6)** but written as truth → OOB slice, fabricated "verifiable" citation, injection vector. |
| T2 | Extraction `overwrite` (or `append`) lands on a **human-verified** value. | **HIGH / BREAKS** | No **verified-clobber guard** — `merge_strategy` silently replaces canon. Trust-tier (verified) and merge-strategy axes are never reconciled. |
| T3 | New tables (`extraction_raw_outputs`, outcome ledger) + new stats/notification events. | **HIGH / GAP** | **No `owner_user_id` scope key**; cache-gate filters by `book_id` only. A View-only collaborator sees another tenant's `cost_per_book`/failures; notifications addressed by book, not user. |
| T4 | Replay re-applies cached entities under a **new** attribute-action profile "at zero cost." | **HIGH / GAP** | Replay is a **write** — but framed as free, implying it **skips the confirm/cost + grant gate**; `from_job_id` not tenant-scoped → cross-tenant cache theft. |
| T5 | Evidence `original_text` (raw chapter quote, possibly "ignore previous instructions…") flows into a later known-entities / deep-research prompt. | **MED / GAP** | **Stored prompt-injection** — INV-6 neutralization never applied to stored evidence before reuse. |
| T6 | A View-only collaborator fires `/effort=high` / MCP `reasoning_effort=high` on a shared book's expensive tool. | **MED / GAP** | Effort is a **cost lever with no spend authorization** — escalates spend on the owner's credentials. Must route through the confirm/cost + grant cap. |
| T7 | Provider error `detail` echoing an API key / prompt is put into a (cross-tenant-visible) stats/notification event. | **MED / GAP** | No **redaction contract**; `raw_response`/secrets must never reach a notification body. |

---

## 8. Hardening adopted (rev 2 design changes)

These amend the named §1–§5 sections; **the HIGH items (T1–T4, F1, C1–C4, S1–S3) are design-blocking.**

### 8.1 The two-ledger model (the linchpin — fixes F1, and underpins all idempotency)

Split the conflated "covered" concept into **two** records:
- **`extraction_raw_outputs`** = the **EXECUTE** record: "the LLM produced this parse" (raw + parsed). Keyed `(owner_user_id, book_id, chapter_id, content_hash, kinds, batch_idx, profile_hash)`. Gates **LLM-skip** (don't re-spend tokens).
- **`extraction_writeback_log`** (NEW) = the **WRITEBACK** record: "these entities landed in glossary," written **only on a confirmed glossary-200**. Gates **writeback-skip**.

So a retry/replay correctly does **skip the LLM AND re-drive the writeback** until it lands.
Resume skips a chapter only when `completed AND writeback_committed`.

### 8.2 Concurrency & idempotency contract (NEW §3.7 — fixes C1–C7, F2)

1. **WRITEBACK is per-book serialized** (`pg_advisory_xact_lock(hashtext(book_id))`) and **transactional** (whole-chapter atomic) — the only correct closure for alias-based dedup.
2. **Constraint-backed dedup:** add `normalized_name` on `glossary_entities` + `UNIQUE(book_id, kind_id, normalized_name) WHERE deleted_at IS NULL`; CREATE path = `INSERT … ON CONFLICT DO NOTHING` → re-resolve to existing → MERGE.
3. **Writeback idempotency key** = the §8.1 writeback-log key; a duplicate key is a no-op returning the prior result (dedupes retry = replay = concurrent fresh).
4. **Content-hash precondition:** the writeback carries the `content_hash` it was computed from; abort `409 STALE_EXTRACTION` if the chapter changed (optimistic concurrency on source version).
5. **Idempotent evidence + append:** `UNIQUE(attr_value_id, evidence_type, md5(original_text))` on `evidences`; append is an atomic server-side `jsonb` dedup-merge (or `UNIQUE(entity_id, attr_def_id, normalized_value)` in the multi-row model).
6. **Cache-gate read-decide-write runs inside the per-(book,chapter,content_hash) lock** (fixes the C5 TOCTOU).
7. **Writeback granularity = per chapter, not per call:** stage per-call parses into the raw-cache, commit the chapter's writeback once as one transaction after all its calls settle (or at a deadline, marking missing calls partial). Restores per-chapter atomicity + clean resume.

### 8.3 Batch-outcome taxonomy + finish_reason (fixes F3; M0 prerequisite)

- **M0 prerequisite:** verify the gateway SDK result propagates **`finish_reason`** per call. Without it the entire P1 story is undeliverable (today the worker never reads it).
- **Closed status enum:** `ok` · `empty_valid` (ran, genuinely 0) · `truncated` (finish_reason=length, partial salvage) · `validation_rejected` (LLM returned items, all dropped — a **distinct warning**, never success) · `llm_error` · `writeback_failed`.
- **Chapter rollup:** `completed` only if every batch ∈ {ok, empty_valid}; anything else → `completed_with_warnings`/`failed`, flowing to job status + notification. `validation_rejected`/`truncated` **must** persist `raw_response` (P5 earns its keep as the debugging artifact). A `truncated` batch feeds back to the planner as a **re-plan-smaller** signal.

### 8.4 Two-phase planner (fixes S1–S5)

Replace the pack-only model with **normalize → pack**:
1. **Phase 1 — normalize/split (the missing direction):** any `Unit` with `est > per_call_budget` is split along a declared `split_axis` (entity→attribute-subset; chapter×kind → **chapter-chunk** [new extraction chunking, mirroring `split_chapter`, with overlap] → kind). Irreducible → emit `UNPLANNABLE{unit, reason}` so the cost-gate surfaces it instead of the executor truncating.
2. **Phase 2 — pack** fitting units up to budget (as in §3.2).
3. **`per_call_budget` is a function of `reasoning_effort`** — `effort_output_multiplier(effort, caps)` (composes the reasoning spec); the effort resolver runs **before** planning and feeds `PlanRequest.policy`.
4. **Fan-out guard:** surface `est_llm_calls`, `calls_per_chapter`, a `model_fit_warning` when `calls_per_unit > threshold`; the cost-gate shows **call count + wall-clock**, not just dollars, and suggests a larger model when fan-out is pathological.
5. **Throttle/backpressure:** the executor chunks the plan into bounded broker work-units with a **per-job + per-user in-flight cap**, provider-aware rate limiting, and checkpointed resume *through the cache* (completed calls are free on resume).
6. **Packing preserves attribution:** each packed unit carries a stable `unit_id` the model must echo; VALIDATE asserts every `unit_id` present exactly once before WRITEBACK (fixes S5). Cross-chunk entity merge is specced **with** P4, not bolted on (extraction chunking creates same-chapter duplicates to dedup).
7. **Cost:** snapshot price at confirm; track running actual; **auto-pause + re-confirm at a budget breach** (e.g. ≥120% of approved), not per-tick; report estimate as a **range** (low/expected/high via the effort multiplier).

### 8.5 Provenance trust (fixes T1, F4)

- Model-supplied offset is a **hint only**. ALWAYS validate `original_text` actually occurs at the claimed block; clamp `char_start/end` to `[0, len]`; on mismatch fall back to authoritative substring search — **never persist an unverified offset.** Validation is the default path, not the fallback.
- **Offset taxonomy:** `exact` (model index verified) · `resolved` (unique substring) · `ambiguous` (multi-match → flag, don't blind-pick) · `unmatched` (hallucinated → `block_or_line=null, provenance_status='unverified'`, keep the evidence, don't fabricate). Never fail the entity on bad provenance; grounding consumers filter on `provenance_status`.

### 8.6 Merge integrity (fixes T2, C6, F-append)

- **Verified-clobber guard supersedes `merge_strategy`:** if the existing value (or list item) is human-`verified`, `overwrite`/`replace`/`append` **downgrade to `manual`** (queue for review) + emit skip-reason `verified` — checked at write time, never assumed.
- **Trust-tier × merge-strategy matrix** is explicit: machine appends never modify/shadow a verified value; a list with a verified item still accepts new machine appends but flags them.
- **Tombstone check** wired into append: an ai-rejected/tombstoned value is never re-appended (the user's deletion sticks).
- **Append is atomic + idempotent by normalized value** (server-side, under the row lock; §8.2.5).
- **System-tier `merge_strategy` defaults to safe** (`fill_if_empty`/`manual`), admin-only; users override only into their per-user/per-book tier.

### 8.7 Tenancy & Trust contract (NEW §3.8 — fixes T3–T7)

- **Scope key on everything new:** `owner_user_id` (+`book_id`) on `extraction_raw_outputs`, `extraction_writeback_log`, the BatchOutcome event payload, and every statistics row. Every cache/replay/usage/stats query filters by tenant + an **E0 grant check**, never `book_id` alone.
- **Cache key carries the tenant dimension forever;** cross-book/cross-tenant cache reuse is **forbidden** (not merely out-of-scope). `content_hash` is a *within-tenant* idempotency key.
- **Replay is a write:** gated by the **same EDIT-grant + confirm/cost authorization** as a normal extraction (cost may be $0, the *write authorization + confirm token* are not); `from_job_id` tenant-scoped; the verified-clobber guard applies.
- **Effort = a cost dimension:** the resolver clamps to model capability **and** to the caller's authorized spend on the target book (grant-level cap / owner-budget consent). A non-owner cannot raise effort past a policy ceiling on a book they don't own.
- **INV-6 on stored evidence:** `original_text` (and any stored raw snippet) is untrusted DATA — neutralized/fenced before it flows into any downstream prompt (known-entities, deep-research).
- **Redaction contract:** structured enumerated `error_code` for routing; `detail` scrubbed of secrets + raw source/prompt text before it leaves the worker into the cross-tenant-readable stats/notification lanes; **never** put `raw_response`/BYOK config into a notification.
- **Notifications addressed to the triggering user** (+ explicitly-granted collaborators by grant level), never broadcast by book.

### 8.8 Observability integrity (fixes C7, F5, F6)

- **SSOT = the outcome rows** (`extraction_chapter_results` / BatchOutcome); events are a **derived projection** written in the **same transaction** (transactional outbox). A **reconciliation sweep** recomputes stats aggregates from rows so a dropped event is eventually consistent, not lost.
- **Stable `event_id`** = `hash(job_id, chapter_id, batch_idx, content_hash)` (redelivery-stable); consumers dedup before aggregating; idempotent set-union aggregation, not running counters.
- **Two sinks by cardinality:** per-batch outcomes → **statistics only** (aggregation-tolerant). The **notification** sink gets **only the job-terminal rollup** ("14 entities, 3 batches truncated — raise model"), debounced with a per-job dedup key. This is the spec default, not a PO question.

---

## 9. Revised milestones (rev 2)

| M | Scope | Why this order |
|---|---|---|
| **M0** | `finish_reason` propagation through the gateway SDK result (verify/wire) | Prerequisite — without it P1 is undeliverable (§8.3). |
| **M1** | Concurrency & two-ledger foundation: entity unique-constraint + `ON CONFLICT`, per-book serialized transactional writeback, `extraction_writeback_log`, idempotency key, content-hash precondition, idempotent evidence | **Design-blocking** — every later milestone writes through this seam (§8.1–8.2). |
| **M2** | P1 observability: BatchOutcome taxonomy + transactional-outbox events + reconciliation + 2-sink routing | §8.3, §8.8 |
| **M3** | P3 provenance: validated offsets + taxonomy + INV-6 on stored evidence | §8.5, §8.7 |
| **M4** | P2 two-phase planner: normalize/split (+ extraction chapter-chunking) → pack, effort-aware budget, fan-out guard, throttle, attribution | §8.4 |
| **M5** | P4 merge: `merge_strategy` + verified-clobber guard + atomic idempotent append + tombstone | §8.6 (data-model change → own plan + migration) |
| **M6** | P5 raw-cache executor + replay (grant+confirm-gated) + retention | §8.1, §8.7; PO gate (§4) |

Tenancy/trust (§8.7) and concurrency (§8.2) are **cross-cutting contracts every milestone honors**, not standalone milestones.

## 10. New open questions surfaced by the evaluation

6. **Writeback atomicity unit** — confirm per-chapter (recommended, §8.2.7) vs per-call; affects resume + partial-visibility UX.
7. **Effort ↔ cache key** — add `reasoning_effort` (or an effort band) to the raw-cache key, or make raising effort require `force_reextract`? (§8.4.3 / S3.)
8. **Append data model** — JSON-array atomic-merge interim vs the multi-row `entity_attribute_values` change now (provenance per list item needs the latter). (§8.6 / C6.)
9. **Fan-out admission control** — hard per-user job/concurrency caps and a queue-depth guard: what limits? (§8.4.5 / S4–S5.)
10. **Raw-cache retention** — keep-latest + bounded history depth, and MinIO offload of cold `raw_response` at what age/size? (§8.4.7 / S7.)
11. **Effort spend authorization** — what is the non-owner effort ceiling on a shared book, and does it consume the owner's budget or the actor's? (§8.7 / T6.)

## 11. Evaluation verdict

The five-facet decomposition (§0) is the right architecture. But as written it was a set of
**single-writer, happy-path contracts deployed into a multi-writer, at-least-once-retry,
multi-tenant, untrusted-LLM-output runtime.** The hardening above adds the missing seam
contracts — **two-ledger** (don't mask un-landed writes), **concurrency** (constraint + lock +
idempotency), **taxonomy** (empty-valid ≠ failed ≠ truncated), **two-phase planning** (split,
not just pack), **provenance trust** (validate model offsets), **merge integrity** (never
clobber verified), and **tenancy** (scope key + grant gate + INV-6 on every new surface). With
§8 folded in, the design is build-ready *as a design*; without the 4 HIGH items it would ship
data-loss and tenancy holes. **Still no build — this remains the CLARIFY/DESIGN artifact.**
