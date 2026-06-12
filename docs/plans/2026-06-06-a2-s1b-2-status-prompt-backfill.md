# A2-S1b-2 — status_effects prompt activation + backfill (eval-GATED)

**Date:** 2026-06-06 · **Track:** LOOM · **Size:** L · **Workflow:** v2.2 human-in-loop
**Design SSOT:** [`docs/specs/2026-06-06-kg-entity-status-model.md`](../specs/2026-06-06-kg-entity-status-model.md) §A2-S1 + MED#2/#4
**Builds on:** A2-S1b-1 (`e868254a`, dormant `status_effects` plumbing) on the CM3b-fixed retract.

## Goal

Activate the dormant `status_effects` field: teach the Pass-2 event prompt to emit coarse
`active`/`gone`, + a one-time backfill over existing events, gated on event extraction not
regressing. **PO decisions (this session):** eval-gate = **relative A/B** (old vs new prompt,
currently-loaded model — isolates the prompt delta, since the F1=0.869 baseline model
qwen3.6-35b isn't loaded); **backfill bundled** into this cycle.

## Why the eval-gate scope is event-only

Extraction is a sequential entity→relation→event pipeline with **separate prompts + separate
LLM calls**. `status_effects` is added to the **event prompt only** → entity + relation F1 are
unaffected by construction. The gate's real risks (all event-local): (1) status output steals
budget → event recall drop; (2) the new rule's English vocab biases CJK/VN summaries to English
(`feedback_english_illustrative_phrases_bias_cjk_summary_to_english`); (3) malformed event JSON.

## Scope — 5 files

### 1. SDK prompt — `loreweave_extraction/prompts/event_extraction_system.md` (the live `event_system`)
- Output schema: add `status_effects: [{entity_ref, status:"active"|"gone"}]`.
- New Rule 10 — **abstract, multilingual-safe** (category verbs dies/destroyed/departs/lost, NO
  narrative illustrative phrases; explicit "judge from TEXT in any language; do NOT translate"
  guard against the CJK→English summary bias). `entity_ref` MUST be a participant; default `[]`.
- Extend the existing (baseline-safe) English example: `[]` on the travel event, `{Zhao, gone}`
  on the death event. (`event_extraction.md` non-system variant is unused — not edited.)

### 2. SDK — already done in b1 (`_LLMEvent`/`LLMEventCandidate.status_effects` + tolerant parse).

### 3. Backfill — `app/db/migrations/backfill_status.py` + `app/routers/internal_backfill.py`
- `run_status_backfill(session, llm_client, *, user_id, project_id)`: read `:Event` nodes with
  **non-null `event_order`** (MED#2 — skip+log null-order; they can't be positioned); batch their
  summaries to the extraction LLM with a coarse classify prompt (`{event_id → [{entity_ref,
  status}]}`); resolve entity_ref against the event's participants → `merge_entity_status` at the
  event's `event_order` + `add_evidence` (source = a synthetic `manual`/backfill source so retract
  semantics hold). **Idempotent** (deterministic status id) + project+user scoped.
- New endpoint `POST /internal/projects/{project_id}/backfill-status` mirroring backfill-orders.

### 4. tests — SDK prompt-shape unit (status_effects in schema + example parses); backfill
integration (idempotent re-run, non-null-order gate skips+logs, project-scoped).

## VERIFY (eval-gated)

- Unit: SDK + backfill green.
- **★ Relative-A/B eval-gate (blocking):** extract CJK (journey_west_zh) + VN (son_tinh) + EN
  (alice) fixtures with OLD vs NEW event prompt, same loaded model (qwen2.5-32b-abliterated),
  temp=0. Ship only if: event count parity (no recall collapse), **CJK/VN summaries stay in-script**
  (the bias check), JSON parses clean, and status_effects emitted sanely on death events.
- **Live smoke:** rebuild worker-ai (bakes the b1 SDK field) + knowledge; publish/extract a chapter
  with a death → status written from the PROMPT (not synthetic); query status at P.

## Out of scope

- Absolute F1=0.869 reproduction (needs qwen3.6-35b + gemma-26b judge loaded → user action).
- A2-S2 (fact-for-check read incl status), A2-S3 (composition guard), A2-S4 (FE).
