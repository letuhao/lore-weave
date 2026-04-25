# 09 — Causal References Framework

> **Status:** LOCKED Phase 4 (Option C discipline 2026-04-25). Per [EVT-A6 typed single-reality causal-refs](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free), this file specifies the **causal-reference framework** at mechanism level — shape, validation rules, multi-parent semantics, graph-walk patterns. Specific causal-ref usage per category is documented in each category's contract section ([`06_per_category_contracts.md`](06_per_category_contracts.md)).
> **Stable IDs:** EVT-L12..EVT-L15. Continuation of EVT-L* lifecycle namespace.
> **Resolves:** [EVT-Q5](99_open_questions.md) (causal-ref multi-parent semantics).

---

## How to use this file

When designing a feature emitting events with causal dependencies:

1. Determine if your category **requires** causal_refs (per [`06_per_category_contracts.md`](06_per_category_contracts.md) per-category policy table).
2. If required, populate `causal_refs: Vec<CausalRef>` per the typed shape (EVT-L12).
3. Honor **single-reality** constraint (EVT-L13) — references stay within the emitting event's reality.
4. For **multi-parent** scenarios (aggregator emits referencing N descendant sources), use the multi-parent rules per EVT-L14.
5. When walking the causal graph (debug replay, audit), use the **graph-walk patterns** per EVT-L15.

Specific reference patterns per category live in each category's contract section + each feature's design doc. This file specifies the **mechanism** the references obey.

---

## EVT-L12 — Causal-ref shape

**Rule:** A causal reference is the typed structure:

```
CausalRef {
  channel_id: ChannelId,
  channel_event_id: u64,
}
```

Both fields **required**. The `channel_id` identifies which channel the referenced event lives in (could be the same channel as the referencing event or a different channel within the same reality). The `channel_event_id` is the gapless monotonic per-channel ID assigned by DP per [DP-A15](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25).

**Field declaration on event payloads:**

Every event payload that may carry causal_refs declares the field:
```
causal_refs: Vec<CausalRef>     // empty Vec if no refs; missing field forbidden if category requires
```

**Why both fields:** `channel_event_id` alone is not unique (each channel has its own counter). The composite `(channel_id, channel_event_id)` is globally unique within a reality and stable for replay (DP-A15 guarantees gapless monotonic assignment per channel, never re-issued).

**Why typed (not opaque UUID):** typed shape lets the validator pipeline run integrity checks at commit time (does the referenced channel exist? does the channel_event_id range to a real event?). Opaque UUID would defer checks to runtime queries with weaker guarantees.

**Forbidden:** untyped string refs, JSON-blob refs without typed schema, refs that contain only `channel_event_id` (would be ambiguous across channels).

**Cross-ref:** [EVT-A6](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free), [DP-A15 channel ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), [DP-Ch11 channel_event_id allocation](../06_data_plane/13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism).

---

## EVT-L13 — Single-reality constraint + integrity validation

**Rule:** All causal references are **single-reality** — the referenced event MUST be in the same reality as the referencing event. Cross-reality references are FORBIDDEN; they're the responsibility of `meta-worker` cross-instance coordination per R5, not of the per-reality event log.

**Validator integrity checks** (run at causal-ref integrity stage of EVT-V* per [`05_validator_pipeline.md`](05_validator_pipeline.md)):
1. **Same-reality check** — implicit in DP scoping (`channel_id` resolves to a specific reality). Cross-reality channel_id raises `DpError::CausalRefCrossReality`.
2. **Reference-exists check** — the referenced `channel_event_id` MUST exist at validation time. Missing reference raises `DpError::CausalRefMissing`.
3. **Forward-reference check** — referenced `channel_event_id` MUST be ≤ a known recent event in that channel (no references to future events). Forward references raise `DpError::CausalRefForward`.
4. **Required-non-empty check** — for categories that require causal_refs (per per-category contract policy), empty `Vec` raises `DpError::CausalRefRequired`.

**Why same-reality:** DP-A12 + R5 cross-instance policy enforce reality isolation. Cross-reality state propagation flows through `meta-worker` xreality.* topics — that's a different mechanism with explicit coordinator service (DF-related, not Event Model). Allowing cross-reality causal_refs in the event log would weaken reality isolation invariant.

**Why reference-exists check:** missing references make the causal graph dangling — replay walking the graph hits a void; debug "what caused this event?" returns "unknown event"; the audit completeness invariant (per EVT-A10) breaks. Hard reject is the only safe option.

**Why forward-reference check:** forward refs would imply events causing earlier events — temporal paradox in the canonical ordering. If a feature legitimately wants to express "this event is part of a multi-event group that completes later," it does so via OTHER mechanisms (transactional cluster via `t3_write_multi`, or a parent-event-id pattern where the parent commits first), not causal_refs.

**Cross-ref:** [EVT-A6](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free), [DP-A12 RealityId newtype](../06_data_plane/02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype), R5 cross-instance policy (`02_storage/R05_cross_instance.md`).

---

## EVT-L14 — Multi-parent semantics (resolves EVT-Q5)

**Rule:** `causal_refs` is `Vec<CausalRef>` — events MAY reference multiple parents. Multi-parent semantics are **inclusive AND** (the event was caused by the conjunction of all referenced parents), not OR. Order within the Vec is preserved but does NOT imply causal sequence — parents are treated as a set.

**When multi-parent is appropriate:**
- **Bubble-up aggregator** (EVT-T5 Generated/BubbleUp) aggregates N descendant events → emits ONE Generated event with N causal_refs (one per source). Per DP-Ch25..Ch30.
- **Synthesis events** that genuinely depend on multiple prior events (e.g., a quest beat outcome that depends on both PC choice + NPC reaction).

**When single-parent is appropriate:**
- **NPCTurn reaction** to a triggering PCTurn → ONE causal_ref (the triggering turn).
- **AggregateMutation** side-effect of a parent turn → ONE causal_ref (the parent).
- **CalibrationEvent** derived from FictionClock advance → ONE causal_ref (the FictionClockAdvance).

**Validator policy on multi-parent:** the integrity checks (EVT-L13) apply per parent. ALL parents must pass (single-reality + reference-exists + non-forward). If any fails, the entire commit fails — partial multi-parent commits forbidden.

**Cap on parent count:** **soft cap 16** parents per event (enforced as warning at validator stage; hard reject at 64). High-multiplicity refs (>16) are a smell pointing toward either (a) the event should be split into multiple events, or (b) a different aggregation mechanism is needed. Specific cap value is operational tunable.

**Why inclusive-AND not OR:** "this event was caused by parent A OR parent B" is semantically ambiguous (which one caused it? was it both?). AND is precise (this event was caused by all listed parents conjunctively). If a feature wants to express "alternative causes", it splits into two events with one parent each.

**Cross-ref:** [DP-Ch25..Ch30 BubbleUp aggregator](../06_data_plane/16_bubble_up_aggregator.md), [EVT-T5 Generated](03_event_taxonomy.md#evt-t5--generated), [EVT-Q5 multi-parent semantics](99_open_questions.md).

---

## EVT-L15 — Graph-walk patterns

**Rule:** The causal-ref graph supports **deterministic, bounded-depth backward walks** for replay and audit purposes. Forward walks (find children of an event) are NOT supported by causal_refs alone — child→parent is the locked direction; if forward indexing is needed, features build their own projection.

**Backward walk pattern (canonical):**
```
walk_backward(start_event_id, max_depth):
  visited = empty set
  queue = [start_event_id at depth 0]
  while queue not empty:
    event_id, depth = queue.pop()
    if depth > max_depth: continue
    if event_id in visited: continue
    visited.add(event_id)
    event = read_event(event_id)
    yield event
    for parent_ref in event.causal_refs:
      queue.push(parent_ref, depth + 1)
  return visited
```

**Bounded-depth contract:** `max_depth` MUST be specified by caller. Default for debug-replay UI: 16 (matches multi-parent soft cap). Operator queries may exceed; admin-cli command enforces explicit `--max-depth` argument.

**Termination guarantee:** the graph is acyclic by construction (causal_refs only point to PRIOR events per EVT-L13 forward-ref check). Bounded depth + visited-set + acyclicity → walk terminates in finite time.

**Use cases for graph-walk:**
- **Time-travel debug replay** — operator queries "what caused event X?" → walk backward N levels.
- **Dead-letter replay** — when replaying a dead-letter entry, validator pipeline may need to walk the original causal graph to verify referenced events still exist.
- **Audit forensics** — security incident investigation walks from a suspicious event to find source.
- **Bubble-up provenance** — trace a Generated event back to the descendant source events that triggered it.

**Performance note:** graph walks are NOT hot-path operations. They're cold-path for debug/audit; specific implementation (recursive query / iterative cursor / projection table) is operational design. Default guidance: rely on DP indexed read on `event_log(channel_id, channel_event_id)`; specialize to a projection only if measured cost demands.

**Forbidden:** unbounded depth walks (would risk service stalling on graph bombs); cycle-tolerant walks (no cycles exist by construction; tolerance would mask bugs).

**Cross-ref:** [`10_replay_semantics.md`](10_replay_semantics.md) — uses graph-walk for time-travel debug replay; [EVT-V7 dead-letter replay](05_validator_pipeline.md#evt-v7--dead-letter-framework).

---

## Per-category causal-ref policy summary

Authoritative per-category policy is in [`06_per_category_contracts.md`](06_per_category_contracts.md). Quick reference:

| Category | Policy | Typical cardinality |
|---|---|---|
| EVT-T1 Submitted (PCTurn) | optional | 0-1 (free narrative empty; chained commands ref parent) |
| EVT-T1 Submitted (NPCTurn) | **required** | 1 (refs triggering Submitted or scene-trigger) |
| EVT-T1 Submitted (QuestOutcome, V1+) | **required** | 1 (refs QuestTrigger) |
| EVT-T3 Derived | optional but recommended | 0-1 (refs parent turn that caused the delta) |
| EVT-T4 System | N/A (DP-internal) | — |
| EVT-T5 Generated (BubbleUp) | **required** | 1-N (one per source descendant event; multi-parent OK per EVT-L14) |
| EVT-T5 Generated (Scheduled) | **required** | 1-2 (refs CalibrationEvent + optionally parent FictionClockAdvance) |
| EVT-T6 Proposal | optional | 0-1 (NPCTurnProposal refs triggering Submitted) |
| EVT-T8 Administrative | optional | 0-1 (refs target event when action targets specific event) |

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-L12 | Causal-ref shape | `CausalRef { channel_id, channel_event_id }`; both required; declared on event payload as `Vec<CausalRef>` |
| EVT-L13 | Single-reality constraint + integrity | Cross-reality refs forbidden; reference-exists + non-forward + required-non-empty validators at commit time |
| EVT-L14 | Multi-parent semantics (EVT-Q5 resolved) | Inclusive AND; soft cap 16 parents (warn) / hard cap 64 (reject); partial multi-parent commits forbidden |
| EVT-L15 | Graph-walk patterns | Bounded-depth backward walk only (forward index = projection); default depth 16; acyclic by construction; cold-path |

---

## Cross-references

- [EVT-A6 typed causal-refs](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free) — invariant this file implements
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — per-category policy in section headers
- [`05_validator_pipeline.md`](05_validator_pipeline.md) EVT-V1..V4 — causal-ref integrity stage runs in pipeline
- [`06_per_category_contracts.md`](06_per_category_contracts.md) — per-category policy table
- [`08_scheduled_events.md`](08_scheduled_events.md) — Scheduled events ref CalibrationEvent / FictionClockAdvance
- [`10_replay_semantics.md`](10_replay_semantics.md) — uses graph-walk for time-travel debug
- [DP-A15 per-channel ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) — `channel_event_id` allocation
- [DP-Ch11 channel_event_id mechanism](../06_data_plane/13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism)
- [DP-Ch25..Ch30 BubbleUp aggregator](../06_data_plane/16_bubble_up_aggregator.md) — multi-parent canonical use case
- [DP-A12 RealityId newtype](../06_data_plane/02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype) — single-reality enforcement
- R5 cross-instance policy — cross-reality coordination via meta-worker (out of EVT scope)
