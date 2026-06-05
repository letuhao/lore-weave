# KG Entity-Status Model (A2-S1) — DESIGN

> **Track:** LOOM · **Status:** DESIGN checkpoint (2026-06-06) — PO decisions locked; pending `/review-impl` then a fresh-session BUILD.
> **Why:** the **load-bearing prerequisite** for composition A2 (`check→revise vs KG`). The SCORE-style symbolic canon guard (spec [`2026-06-05-composition-v1-reasoning-engine.md`](2026-06-05-composition-v1-reasoning-engine.md) §5.1) needs to ask *"is entity E in a contradicted status at story position P?"* (a dead character acting, a destroyed object reappearing). **The KG does not model entity status today** — this design adds it.
> **Boundary:** `loreweave_extraction` SDK · worker-ai · knowledge-service (+ a backfill). **NEVER lore-enrichment.** Additive only.

## A2 slice map (this doc = S1)
- **A2-S1 — KG entity-status model** ← THIS DESIGN (the prerequisite)
- A2-S2 — knowledge-service `fact-for-check` read (entities + relations + timeline + **status** by id set, project-scoped)
- A2-S3 — composition `canon_check` (symbolic guard incl. status + LLM-judge) + `reflect(check→revise ≤N)` + auto-path wiring + eval-gate
- A2-S4 — co-write FE gate (revise affordance)

## Grounding (actual KG, read 2026-06-06)
- `:Entity` — timeless/canonical, `user_id`+`project_id` first-class, `glossary_entity_id` FK, embeddings, `evidence_count`. **No status property.**
- `:Event` — `event_order` (reading axis) + `chronological_order` (in-world axis) + `chapter_id`, project-scoped, evidence-backed.
- `:Fact` — evidence-backed node; participates in the `EVIDENCED_BY` + `evidence_count` + retract-before-reextract machinery.
- Relations already carry temporal validity (`valid_until`).
- `persist-pass2` ([internal_extraction.py](../../services/knowledge-service/app/routers/internal_extraction.py) `PersistPass2Request`) writes `entities/relations/events/facts` from the `loreweave_extraction` SDK candidate models (`LLMEntityCandidate`/`LLMEventCandidate`/…). worker-ai runs Pass-2 then POSTs the candidates.

## Locked PO decisions
1. **Population = extraction-time additive field.** New `status_effects: [{entity_ref, status}]` on `LLMEventCandidate` — the Pass-2 LLM, when it extracts an event, also flags entity status changes ("X dies" → `{X, gone}`). Real-time, evidence-backed, aligned with **canon=published**. Touches the SDK (schema + prompt) → worker-ai (passthrough) → knowledge persist (write status records). Additive: legacy/omitting events → no status → `active`.
2. **Vocabulary = coarse `active` / `gone`** for V1 (the discriminating contradiction is "referenced as present/acting while `gone`"). Extensible later to {dead, destroyed, lost, departed, transformed}; V1 maps all of those → `gone`.
3. **Backfill = a one-time classify job** over existing events so current books get the guard immediately (vs forward-only). Coarse vocab keeps the backfill prompt cheap.

## Schema — status as an evidence-backed, order-keyed record
Model a status change as an **evidence-backed status record keyed to `event_order`**, reusing the `:Fact`/evidence/retract infra so **retract-before-reextract and zero-evidence cleanup work for free** (re-publishing a chapter must not strand stale status — the canon=published invariant):
- Shape (confirm exact node/edge against `pass2_writer` at BUILD): a `:Fact { fact_type:'status', status:'active'|'gone', valid_from_order:<event_order>, user_id, project_id, evidence_count, provenances }` linked to its `:Entity` (subject) and `EVIDENCED_BY` its source.
- **"Status at position P"** = the latest status record with `valid_from_order ≤ P` per entity; default `active` when none. Pure Cypher, user+project scoped (K11.4 wrapper).
- **Two-axis note:** `valid_from_order` uses the **reading axis** (`event_order`) to match the composition packer's spoiler/position axis; chronological is secondary.

## Component changes (BUILD plan for A2-S1)
1. **`loreweave_extraction` SDK** — add `status_effects` to the event candidate model + the Pass-2 prompt (a multilingual-safe, abstract instruction per the prompt-bias lessons; coarse active/gone). Optional → back-compat.
2. **worker-ai** — pass `status_effects` through in the `persist-pass2` body (no logic).
3. **knowledge-service persist-pass2** — write a status record per `status_effect` at the event's `event_order`, evidence-backed, **retract-then-write** on re-extract (same pattern as events). Idempotent.
4. **knowledge-service Neo4j schema** — index for `(user_id, project_id, fact_type)` / status lookup.
5. **backfill job** — a one-time, project-scoped classify pass over existing `:Event` summaries → status records (reuses the extraction LLM path; internal endpoint like the CM4 backfill).
6. **the "status at P" query helper** (consumed by A2-S2).

## /review-impl corrections (2026-06-06, folded)
- **MED#1 — order-validity is NET-NEW, not inherited.** `:Relation.valid_until` is a *datetime* (latest-wins supersession); `:Fact` has no order-validity. Evidence/retract IS reused, but **"status at `event_order` P" is a new temporal model** — it needs its own property (`valid_from_order`), its own "latest ≤ P" query, and its own index + tests. Do NOT claim it for free. BUILD must design the order-validity + retract interplay explicitly (a death record superseded by a revival record at a later order).
- **MED#2 — `event_order=None` defeats positioning (the backfill's blind spot).** Per CM4, legacy/chat/no-P3-hierarchy events have `event_order=None` (null-sinks) — and those are exactly what the backfill targets → unpositionable status. **Gate status records to non-null `event_order`**; either run the CM4 order-backfill first OR fall back to `chronological_order`; the backfill must SKIP+LOG events with no position (no silent unusable rows).
- **MED#3 — coarse `active/gone` false-positives on revivals → symbolic flags are ADVISORY, not hard.** `gone→active` is a legitimate move (resurrection, a "lost" item found), and the draft under check may BE the revival. So "entity is gone ⇒ contradiction" is wrong as a HARD gate. The A2-S3 symbolic guard emits **candidate flags the LLM-judge confirms** (does the draft establish the return?); it does NOT auto-block. This refines D4: a coarse-status flag alone is advisory; HARD = LLM-judge-confirmed canon-fact contradiction.
- **MED#4 — the extraction prompt change is eval-gated.** Adding `status_effects` to the Pass-2 prompt risks regressing the locked extraction baseline (knowledge eval F1 = 0.869) + multilingual prompt-bias traps. **A2-S1 VERIFY MUST re-run the knowledge extraction eval** (entity/relation/event F1 vs baseline) after the SDK prompt change — ship the field only if F1 holds.
- **LOW#5 — exclude status-Facts from RAG fact selectors.** `FACT_TYPES` is closed + a prior fact-type filter exists; a `fact_type='status'` record must NOT surface in the composition grounding context as a normal fact (audit the fact context selectors).
- **LOW#6 — retract by event source.** Status records must retract by the **same `source_id` as their originating event**, inside the per-chapter retract-then-write Tx (one-active-job-per-project K17.9) — confirm at BUILD.

## Invariants + risks (for /review-impl)
- **Retract-safety (load-bearing):** status records MUST participate in retract-before-reextract + `cleanup_zero_evidence_nodes`, or a re-published chapter leaves stale status → canon drift. This is the CM3b risk class.
- **Idempotence:** re-extracting the same chapter must converge (same status records), not accumulate.
- **Multi-tenant:** every status query/write through the K11.4 `user_id` wrapper.
- **Coarse-vocab honesty:** active/gone can't catch fine contradictions (revival, transformation) — documented V1 limit; the LLM-judge (A2-S3) covers semantic residue.
- **Backfill cost/idempotence:** the one-time job must be re-runnable + project-scoped + not double-write.

## Verify plan (A2-S1, future session)
- SDK: unit — `status_effects` round-trips; prompt emits coarse vocab.
- knowledge: unit — persist writes a status record at the right order; **retract-then-write** drops stale status on re-extract (regression-lock); "status at P" returns the latest ≤ P + default active.
- backfill: integration — re-runnable, project-scoped, idempotent.
- **Live-smoke (cross-service):** extract a chapter with a death event → status record written at the event's `event_order`; re-extract → no duplicate, stale dropped (retract-then-write); query status at a later position → `gone`, at an earlier position → `active`; an event with `event_order=None` → SKIP+LOG (MED#2).
- **★ Extraction eval-gate (MED#4, blocking):** re-run the knowledge extraction eval (entity/relation/event F1) after the SDK Pass-2 prompt gains `status_effects` — **ship only if F1 holds vs the 0.869 baseline**; check the multilingual fixtures for prompt-bias regression.

## NOT in A2-S1 (later slices)
The fact-for-check read (A2-S2), the composition symbolic guard + LLM-judge + revise loop (A2-S3), the co-write FE gate (A2-S4). This slice only makes status **exist + queryable** in the KG.
