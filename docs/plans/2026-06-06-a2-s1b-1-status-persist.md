# A2-S1b-1 — Entity-status persist plumbing (eval-SAFE)

**Date:** 2026-06-06 · **Track:** LOOM · **Size:** L · **Workflow:** v2.2 human-in-loop
**Design SSOT:** [`docs/specs/2026-06-06-kg-entity-status-model.md`](../specs/2026-06-06-kg-entity-status-model.md)
**Builds on:** A2-S1a (`:EntityStatus` storage primitive, commit `db68ab25`)

## Goal

Wire the `:EntityStatus` node (A2-S1a) into the live extraction persist path — **plumbing
only, no prompt change** — so it's eval-neutral and provable with a synthetic payload. The
prompt change + backfill that activates it (and re-runs the F1=0.869 eval gate) is **A2-S1b-2**.

## Why eval-safe

The extraction prompt is **unchanged**, so the LLM never emits `status_effects` → the new
field is always `[]` in production → model behaviour and the extraction eval are byte-identical.
The full SDK→worker→persist plumbing is reserved now (the "reserve early" pattern) so b2 is a
pure prompt edit + one backfill job.

## Scope — 6 files (3 source + 3 test)

### 1. SDK — `sdks/python/loreweave_extraction/extractors/event.py`
- New `StatusEffect(BaseModel)`: `entity_ref: str`, `status: Literal["active","gone"]`. Export in `__all__`.
- `_LLMEvent` (raw): add `status_effects: list[StatusEffect] = []` + `@field_validator(mode="before")`
  that **tolerates+filters** (drop non-dict / empty `entity_ref` / status∉{active,gone}; never reject the
  event — per `feedback_llm_schema_tolerate_filter`).
- `LLMEventCandidate` (output): add `status_effects: list[StatusEffect] = Field(default_factory=list)`.
- `_postprocess`: thread `status_effects=evt.status_effects` into the candidate.
- `_tolerant_parse_events`: pass `status_effects=item.get("status_effects")` into `_LLMEvent` (validator coerces).
- **No prompt-file edit. No change to `event_extraction` prompt.**

### 2. Knowledge — `services/knowledge-service/app/db/neo4j_repos/provenance.py`
- Add `"EntityStatus"` to `TargetLabel` Literal + `TARGET_LABELS` tuple → `add_evidence` accepts it
  (the per-label `_ADD_EVIDENCE_CYPHER` template auto-builds for the new label; `evidence_count`/`mention_count`
  increment works generically).
- `cleanup_zero_evidence_nodes` + `CleanupResult`: add the `entity_statuses` sweep via
  `delete_entity_status_with_zero_evidence` (A2-S1a) for reconciler parity.
- *(No change to `remove_evidence_for_source` — it is already label-generic, so retract decrements
  `:EntityStatus` evidence unchanged.)*

### 3. Knowledge — `services/knowledge-service/app/extraction/pass2_writer.py`
- Import `merge_entity_status` from `entity_status`.
- New `_resolve_status_entity_id(entity_ref, chapter_entity_by_canonical_name, anchor_index, project_id)`
  helper → returns `str | None`: sanitize→fold→chapter-map single-candidate (Tier A.1) → anchor index (Tier A.2)
  → else `None`. **No autocreate.**
- Inside the **event loop** (after `merge_event` + `add_evidence`), consume `evt.status_effects`:
  - if `event_order is None` → **skip + LOG** (`status_effect skipped: event has no event_order (legacy/chat)`); M2 blind-spot guard.
  - resolve `entity_ref`; if `None` → skip + LOG (`status_effect entity unresolved`).
  - else `merge_entity_status(from_order=event_order, status=eff.status, source_type=source_type,
    source_chapter=hierarchy chapter_id or source_id, provenance=provenance)` +
    `add_evidence(target_label="EntityStatus", target_id=status.id, source_id=source.id, confidence=evt.confidence, job_id)`.
- `Pass2WriteResult`: new `statuses_merged: int = 0` counter.
- Status writes happen **inside the per-chapter Tx** (same `CypherSession`) — retract-then-write atomicity preserved.

## Canon-safety (proven by construction)

- `add_evidence(EntityStatus)` ties each status to the chapter `ExtractionSource`.
- Re-publish → `persist_pass2` calls `remove_evidence_for_source` (generic) → decrements status evidence to 0
  + deletes the edge → write re-adds evidence for statuses still asserted.
- A **moved** death (edited revision → new `event_order` → new deterministic id) leaves the old status
  orphaned at `evidence_count=0`; `status_at_order` filters `evidence_count >= 1` → **invisible to reads**
  before cleanup even runs. New status fresh. **No canon drift.**
- Idempotent re-extract of the same revision: retract zeroes + deletes edge → MERGE no-ops (ON MATCH leaves
  `evidence_count` untouched) → `add_evidence` ON-CREATE re-increments to 1.

## Test plan

- **SDK** (`tests/.../test_event_extractor.py` or new): `status_effects` round-trips on `LLMEventCandidate`;
  tolerant parse drops malformed (non-dict, bad status, empty ref) but keeps the event; absent field → `[]`.
- **provenance** (`tests/integration/db/test_provenance_repo.py`): `add_evidence(target_label="EntityStatus")`
  creates the edge + increments `evidence_count`; `cleanup_zero_evidence_nodes` sweeps a zero-evidence status
  (and reports it in `CleanupResult`).
- **pass2_writer** (`tests/unit/test_pass2_writer.py`): event with `status_effects` →
  `merge_entity_status` + `add_evidence(EntityStatus)` called with `from_order==event_order`; `event_order=None`
  → skip+no status call; unresolved `entity_ref` → skip; **retract-idempotency** (re-run same source → status
  evidence returns to 1, no dup node).

## VERIFY (cross-service → live-smoke token required)

- knowledge unit suite green; SDK unit green; worker-ai unit green (no worker code change — confirm round-trip test).
- **live smoke:** rebuild knowledge service+worker images (git-SHA stamped); `persist-pass2` with a **synthetic**
  `events[].status_effects` payload on the demo book → `status_at_order` read-back returns the asserted `gone`;
  re-POST same source → no dup (retract-idempotency). Token: `live smoke: synthetic status_effects persist+read-back`.

## Out of scope (→ A2-S1b-2, eval-GATED)

- The `event_extraction` **prompt** change (coarse active/gone, multilingual-safe).
- The one-time **backfill** job (non-null `event_order` only, project+user scoped, idempotent).
- The **BLOCKING eval-gate** re-run vs F1=0.869.
