# 22 — Event Design Quickstart

> **Status:** LOCKED Phase 5 (bridging doc, Option C closure 2026-04-25). Not an axiom or primitive — a **mental-model + worked-example** entry point for feature designers emitting/consuming events. If anything here conflicts with files 02 / 03 / 04 / 05 / 06 / 07 / 08 / 09 / 10 / 11 of `07_event_model/`, those files win — re-open this doc to fix.
> **Audience:** any agent (or human) about to design a feature that emits or consumes events. Read this FIRST; then drill into specific EVT-A* / EVT-T* / EVT-V* / EVT-L* / EVT-S* sections via the cross-reference table at the end.
> **Models:** mirrors [`../06_data_plane/22_feature_design_quickstart.md`](../06_data_plane/22_feature_design_quickstart.md) shape. Worked example uses PL_001's TurnEvent + BubbleUpEvent re-mapped under Option C (mechanism-level) taxonomy.

---

## 1. The 5-minute mental model

Every interaction with a per-reality LoreWeave world goes through **events**. An event is a typed payload + universal envelope, committed to a per-reality channel event log (or, for pre-validation untrusted-origin proposals, emitted onto a proposal bus).

Per [EVT-A10 event as universal source of truth](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), events ARE canonical state — projections and caches are derived. Per [EVT-A1 closed-set taxonomy](02_invariants.md#evt-a1--closed-set-event-taxonomy), every event maps to exactly one of **6 mechanism-level categories**:

| EVT-T* | Mechanism | Origination |
|---|---|---|
| **T1 Submitted** | actor explicitly emits with intent | PC turn / NPC reaction / quest outcome |
| **T3 Derived** | side-effect state delta of another event | FictionClockAdvance / scene update / calibration |
| **T4 System** | DP-internal lifecycle | MemberJoined / TurnSlot / ChannelPaused |
| **T5 Generated** | rule/aggregator/scheduler emits with deterministic RNG | bubble-up rumor / NPC routine / world tick |
| **T6 Proposal** | untrusted-origin pre-validation message | LLM proposal awaiting validation |
| **T8 Administrative** | operator-emitted via S5 dispatch | admin pause / Forge edit / Charter invite |

Within each category, **sub-types are feature-defined** per [EVT-A11 sub-type ownership discipline](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) and registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

Features extend events along **6 well-defined extension points** per [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25). Extensions outside these are forbidden.

---

## 2. Worked example: PL_001 turn flow re-mapped under Option C

PL_001 §11 sequence (PC says "Tiểu nhị, lấy cho ta một bình trà"). Trace each event under the redesigned taxonomy.

### 2.1 PC submits turn

PC types text → gateway → roleplay-service (Python LLM) generates narration → emits **EVT-T6 Proposal** (sub-type `PCTurnProposal`, owner roleplay-service per [EVT-P6](04_producer_rules.md#evt-p6--proposal-evt-t6)). Roleplay-service JWT carries `produce: [Proposal]` ONLY.

```
EVT-T6 Proposal {
  event_category: "Proposal",
  event_sub_shape: "PCTurnProposal",
  producer_service: "roleplay-service",
  proposal_id: <UUIDv4>,
  payload: PCTurnProposalPayload { actor: pc_id, intent: Speak, narrator_text, ... }
}
```

### 2.2 World-service consumes + validates

Commit-service (Rust world-service) consumes the proposal from the bus per [EVT-L1 transport](07_llm_proposal_bus.md#evt-l1--bus-transport-mechanism). Runs full EVT-V* validator pipeline per [`05_validator_pipeline.md`](05_validator_pipeline.md):
- Schema → Capability → A5 intent classify → A6 5-layer injection defense → world-rule lint → canon-drift → causal-ref integrity → commit.

### 2.3 Validated → fresh Submitted committed

Pipeline passes → world-service commits a **fresh** EVT-T1 Submitted via `dp::advance_turn` per [EVT-L2 lifecycle state machine](07_llm_proposal_bus.md#evt-l2--lifecycle-state-machine):

```
EVT-T1 Submitted {
  event_category: "Submitted",
  event_sub_shape: "PCTurn::Speak",        // sub-type owned by PL_001 + PL_002
  producer_service: "world-service",
  origin_proposal_id: <ref to original>,
  payload: PCTurnPayload { ... }
}
```

The original Proposal is acked off the bus; the Submitted event is the canonical record.

### 2.4 Side-effect Derived events

After advance_turn commits, world-service emits **EVT-T3 Derived** events as side-effects per [EVT-V6 post-commit side-effects](05_validator_pipeline.md#evt-v6--post-commit-side-effects):

```
EVT-T3 Derived {
  event_category: "Derived",
  event_sub_shape: "fiction_clock::Advance",   // aggregate_type=fiction_clock, delta_kind=Advance
  causal_refs: [(cell_channel, <Submitted_event_id>)],
  payload: FictionClockAdvanceDelta { duration_ms: 30000 }
}
```

Each Derived event has its own channel_event_id + causal-ref to the parent Submitted (per [EVT-L12 causal-ref shape](09_causal_references.md#evt-l12--causal-ref-shape)).

### 2.5 NPC reaction (Chorus orchestration)

World-service orchestrator (NPC_002 Chorus) decides Tiểu Thúy reacts. Emits another **EVT-T6 Proposal** (sub-type `NPCTurnProposal`) referencing the PC's Submitted event. Same flow: validated → committed as **EVT-T1 Submitted** with sub-type `NPCTurn::Speak`, REQUIRED causal_refs to triggering PC turn.

### 2.6 Bubble-up at tavern level (Generated)

Hours of fiction-time later, gossip aggregator (registered Generator) at tavern level has accumulated 5 PC-NPC interactions. Emits an **EVT-T5 Generated** event:

```
EVT-T5 Generated {
  event_category: "Generated",
  event_sub_shape: "BubbleUp::RumorBubble",
  producer_service: "gossip-aggregator",
  causal_refs: [<5 source cell-channel events>],   // multi-parent inclusive AND
  payload: RumorBubblePayload { rumor_text: "Có một người lạ tới Yên Vũ Lâu...", ... }
}
```

**Probability gate** uses `dp::deterministic_rng(channel_id, channel_event_id)` per [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — replay produces same output.

### 2.7 Closed-set proof for this scenario

| Step | Event | Category | Sub-type | Owner |
|---|---|---|---|---|
| 2.1 | PC narrative proposal | T6 Proposal | PCTurnProposal | roleplay-service |
| 2.3 | Committed PC turn | T1 Submitted | PCTurn::Speak | PL_001 + PL_002 |
| 2.4 | Fiction-clock advance | T3 Derived | fiction_clock::Advance | PL_001 |
| 2.5a | NPC reaction proposal | T6 Proposal | NPCTurnProposal | roleplay-service |
| 2.5b | Committed NPC reaction | T1 Submitted | NPCTurn::Speak | NPC_001 + NPC_002 |
| 2.6 | Tavern rumor bubble | T5 Generated | BubbleUp::RumorBubble | gossip aggregator |

Every event maps to exactly one active EVT-T* + sub-type registered in `_boundaries/`. Closed-set property satisfied.

---

## 3. Decision flowchart per event your feature emits

```
1. CATEGORY?
   - Actor explicitly emits with intent? .................... T1 Submitted
   - Side-effect state delta of another event? .............. T3 Derived
   - DP-internal lifecycle? ................................. T4 System (DP-emitted; you can't produce these)
   - Rule/aggregator/scheduler with probability? ............ T5 Generated
   - Untrusted-origin (LLM/agent) pre-validation? ........... T6 Proposal
   - Operator via S5 dispatch? .............................. T8 Administrative
   When unsure: walk the worked example above; map your event to one row.

2. SUB-TYPE?
   - Search _boundaries/01_feature_ownership_matrix.md for an existing sub-type.
   - If your concept already has an owner: cite + use; don't redefine.
   - If new: register ownership under your feature in the boundary matrix
     (claim _boundaries/_LOCK.md first).

3. PRODUCER ROLE?
   - Check EVT-A4 producer-role table; pick role class matching your service.
   - Confirm your JWT carries `produce: [<EVT-T*>]` claim per role's pattern.
   - Service-binding registered in _boundaries/01_feature_ownership_matrix.md.

4. CAUSAL-REF POLICY?
   - Per-category policy in 06_per_category_contracts.md or 03_event_taxonomy.md.
   - REQUIRED categories: T1 Submitted (NPCTurn / QuestOutcome) · T5 Generated.
   - Optional: T1 Submitted (PCTurn) · T3 Derived (recommended) · T6 Proposal · T8 Administrative.

5. VALIDATOR SUBSET?
   - Per-category subset in `_boundaries/03_validator_pipeline_slots.md`.
   - T4 System: none (DP-trusted).
   - T5 Generated: no A6 (deterministic, not LLM input); EVT-A9 RNG enforced.
   - T8 Administrative: no A6 (operator-authenticated); has S5 dual-actor for Tier 1.

6. SCHEMA VERSIONING?
   - Pure additive (new optional field) → no version bump per I14.
   - Breaking change → two-phase rollout per EVT-S2 + upcaster per EVT-S3.
```

---

## 4. Anti-patterns (what NOT to do)

| ❌ Don't | ✅ Do | Reason / Enforcement |
|---|---|---|
| Invent a 7th event category | Pick from EVT-T1/T3/T4/T5/T6/T8 | EVT-A1 closed-set; new categories are axiom-level decisions |
| Define a sub-type owned by another feature | Cite existing owner OR register your own in `_boundaries/` | EVT-A11 sub-type ownership; cross-feature definition forbidden |
| Emit canonical events from an LLM-driven service | Emit EVT-T6 Proposal; trusted commit-service validates → commits | EVT-A7 untrusted-origin pre-validation lifecycle |
| Use `chrono::Utc::now()` or `rand::thread_rng()` in a Generator | Use `dp::deterministic_rng(channel_id, channel_event_id)` | EVT-A9 RNG determinism; replay-correctness |
| Write state to a projection cache without emitting an event | Emit canonical event; projection updates from event-replay | EVT-A10 event as universal SSOT; no sideline-writes |
| Reorder validators or skip stages "for performance" | Use per-category subset (declared statically) OR add a hot-path PRE-pipeline gate per EVT-V5 | EVT-A5 fixed validator order; EVT-V1 pipeline framework |
| Silently drop a failing event | Use EVT-V2 fail-mode taxonomy: reject_hard / reject_soft_with_retry / sanitize / quarantine / warn_and_proceed | EVT-V2 silent_drop forbidden |
| Reference an event in a different reality via causal_refs | Cross-reality coordination via meta-worker (R5 cross-instance policy) | EVT-A6 single-reality constraint; EVT-L13 integrity check |
| Forward-reference a future event in causal_refs | Use a different mechanism (transactional cluster via t3_write_multi) | EVT-L13 forward-ref check rejects |
| Include LLM-generated narration as canonical payload | Use `flavor_text_audit_id` pointer; flavor goes to audit log | EVT-A8 non-canonical regenerable content |
| Bump schema without writing an upcaster | Two-phase rollout: write upcaster + deploy consumer first, then producer | EVT-S2 + EVT-S3 + EVT-S6 DP-C5 boundary |
| Drop a field while old events with that field still in retention | Wait for retention expiry; canonical events with `Forever` tier require permanent upcasters | EVT-S3 + S8-D3 retention bounds |
| Generate flavor text via LLM during forensic time-travel debug replay | Use audit-log only (Mode 2); show `[flavor unavailable]` if missing | EVT-L19 (no LLM fallback in forensic context misleads investigation) |

---

## 5. Pattern selection cheatsheets

### 5.1 Picking validator fail mode per stage

| Failure character | Use mode |
|---|---|
| Malformed payload (cannot proceed) | `reject_hard` |
| LLM persona-break (one retry might fix) | `reject_soft_with_retry` |
| User input contains escape character (rewriteable) | `sanitize_and_proceed` |
| Suspicious operation requiring manual review | `quarantine` |
| Style guide violation (logged but not blocking) | `warn_and_proceed` |
| Anything without an explicit decision | (forbidden — declare one of the 5) |

### 5.2 Picking causal-ref cardinality

| Origination | Cardinality | Example |
|---|---|---|
| Free narrative PCTurn | 0 (none) | "Lý Minh nâng chén trà nhìn ra cửa sổ" |
| Chained command resolution | 1 | `/travel` resolution refs the parent `/travel` command |
| NPC reaction | 1 | NPCTurn refs triggering PCTurn |
| Side-effect Derived | 1 | FictionClockAdvance refs parent Submitted |
| Aggregator emit (BubbleUp) | 1-N | Rumor refs N source cell events (multi-parent inclusive AND) |
| Synthesis events (rare) | 2-3 | Quest beat outcome refs PC choice + NPC reaction |

If cardinality >16: re-examine — likely event should split or use different aggregation.

### 5.3 Picking V1 vs V1+30d phasing

| Concern | V1 | V1+30d | V2+ |
|---|---|---|---|
| Fiction-clock advance | only on PC turn (paused-when-solo per MV12-D4) | + scheduled-canon-events fire | + per-tier autonomous tick |
| EVT-T5 Generated::Scheduled emissions | none | NPC routines + author-placed beats fire | + Quest:Trigger (when quest-engine ships) |
| Replay flavor handling | audit-log replay (cheaper) | + LLM re-prompt as feature flag | + per-tier flavor cost model |
| Dead-letter retention | 7-day default | + 30-day for security-relevant rejections | + tiered retention per S6 cost model |

---

## 6. Feature design checklist

When submitting a feature design that emits/consumes events, your doc must answer:

1. **Event categories used** — list each EVT-T* category; map sub-types to your feature.
2. **Sub-type ownership registered** — ensure boundary matrix entry exists for each new sub-type (claim `_boundaries/_LOCK.md` if adding).
3. **Producer role** — which EVT-A4 role class your service plays; cite EVT-P* row.
4. **JWT capability** — what `produce: [<EVT-T*>]` claim your service-account needs (cite DP-K9 + boundary matrix).
5. **Causal-ref policy** — per category, declare cardinality + integrity expectations.
6. **Validator subset** — confirm your category's standard subset; flag any deviation as boundary review item.
7. **Generator determinism** (if EVT-T5) — declare RNG seed source per EVT-A9.
8. **Schema version** — declare envelope version + sub-shape version starting points.
9. **Replay visibility** — for EVT-L16 session catch-up, declare which sub-types are user-visible vs internal-filtered.
10. **Phasing** — declare V1 / V1+30d / V2+ status for new EVT-T5 Generated emitters.

If any of these is missing or "TBD", design review will block per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) + [EVT-A12](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25).

---

## 7. Where to look next

| Question | File |
|---|---|
| Why each axiom exists | [`02_invariants.md`](02_invariants.md) EVT-A1..A12 |
| Closed-set proof; per-category mechanism | [`03_event_taxonomy.md`](03_event_taxonomy.md) |
| Producer roles + JWT patterns + idempotency-key shape | [`04_producer_rules.md`](04_producer_rules.md) |
| Validator pipeline framework + fail modes + rejection-path | [`05_validator_pipeline.md`](05_validator_pipeline.md) |
| Common envelope + extensibility framework | [`06_per_category_contracts.md`](06_per_category_contracts.md) |
| Proposal bus protocol (transport / lifecycle / dead-letter) | [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) |
| Scheduled events (NPCRoutine / WorldTick / QuestTrigger) | [`08_scheduled_events.md`](08_scheduled_events.md) |
| Causal-ref shape + integrity + multi-parent + graph-walk | [`09_causal_references.md`](09_causal_references.md) |
| Replay (session / canon / time-travel) + flavor handling | [`10_replay_semantics.md`](10_replay_semantics.md) |
| Schema versioning + DP-C5 boundary | [`11_schema_versioning.md`](11_schema_versioning.md) |
| Open questions + deferral landing points | [`99_open_questions.md`](99_open_questions.md) |
| Sub-type ownership SSOT | [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) |
| TurnEvent envelope + AdminAction sub-shape contracts | [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) |
| Validator pipeline current ordering | [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) |
| DP primitive surface (advance_turn / t2_write / etc.) | [`../06_data_plane/04d_capability_and_lifecycle.md` DP-K12](../06_data_plane/04d_capability_and_lifecycle.md#dp-k12--api-surface-summary) |
| LLM safety internals (A3 Oracle / A5 dispatch / A6 defense) | [`../05_llm_safety/`](../05_llm_safety/) |
| First feature consuming events (PCTurn) | [PL_001 Continuum](../features/04_play_loop/PL_001_continuum.md) + [PL_002 Grammar](../features/04_play_loop/PL_002_command_grammar.md) |
| First feature emitting NPCTurn | [NPC_001 Cast](../features/05_npc_systems/NPC_001_cast.md) + [NPC_002 Chorus](../features/05_npc_systems/NPC_002_chorus.md) |

---

## 8. When this doc is wrong

This is a *bridging doc*. The locked spec lives in 02 / 03 / 04 / 05 / 06 / 07 / 08 / 09 / 10 / 11. If a primitive name, signature, or guarantee here disagrees with those files:

- **The locked spec wins.** Do not infer behavior from this doc.
- **Open a fix PR for this doc** targeting THIS file for correction, not the locked spec.
- **If you find a real Event Model gap** (something a feature genuinely needs but no mechanism exists), record it in [`99_open_questions.md`](99_open_questions.md) with severity, and stop trying to design around it locally — escalate.
