# 03 — Validator Pipeline Slot Ordering (EVT-V*)

> **Status:** seed 2026-04-25 + alignment review 2026-04-26 (resolved EF-Q3 + PF-Q1 + MAP-Q1 + CSC-Q2 in single boundary pass; Stage 3.5 group inserted).
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.
>
> **Authoritative source pending:** event-model agent's Phase 3 (`07_event_model/05_validator_pipeline.md`) will LOCK the final ordering. Until that lands, this file is the working consensus. Foundation tier 4/4 structural validators (entity_affordance / place_structural / map_layout / cell_scene) now have explicit slot positions per Stage 3.5 group below.

---

## Why this file exists

Per EVT-A5 ("validator pipeline runs in fixed order, no skips"), the EVT-V* pipeline has a single ordering. Multiple features have already proposed where THEIR slot fits:

- **WA_001 Lex** §7.1: "schema → capability → A5 → A6-sanitize → ★ lex_check ★ → A6-output → canon-drift → causal-ref → commit"
- **WA_002 Heresy** §6.1: "★ heresy_check ★ runs immediately after Lex"
- **WA_006 Mortality** (provisional): hot-path mortality check is BEFORE validators (turn-submission gate, not validator pipeline)

Without coordination, drift accumulates. This file is the staging area for the final EVT-V* ordering.

---

## Proposed ordering (V1 — pending event-model agent's Phase 3 lock)

```text
incoming TurnEvent / EVT-T* candidate
    │
  [stage 0] schema validate
    │   purpose: payload shape per per-category contract (event-model Phase 2)
    │   owner: event-model
    │
  [stage 1] capability check (DP-K9)
    │   purpose: JWT carries required produce: claim and read/write permissions
    │   owner: DP / event-model
    │
  [stage 2] A5 intent classification
    │   purpose: confirms the proposal's intent matches the actor type
    │   owner: 05_llm_safety
    │
  [stage 3] A6 sanitize (input layer)
    │   purpose: jailbreak / injection scan on raw LLM output
    │   owner: 05_llm_safety
    │
  [stage 3.5] ★ structural validators ★ (alignment review locked 2026-04-26)
    │   purpose: world-state consistency checks (referenced entities/places/cells/map valid)
    │           runs BEFORE lex semantic check (cheaper rejects; fail-fast principle)
    │           each sub-stage has applicability predicate (early-exit when not relevant
    │           to event kind — see §applicability table below)
    │   ordering: fail-fast common-case-first; specific checks last
    │
    │   3.5.a ★ entity_affordance ★          → EF_001
    │         purpose: target entity exists + lifecycle ∈ {Existing,Suspended} +
    │                  required affordance flag in entity's effective AffordanceSet
    │         soft-override: per-InteractionKind tolerates_destroyed/tolerates_suspended
    │                        (PL_005 InteractionKindSpec; Examine tolerates Destroyed)
    │
    │   3.5.b ★ place_structural ★           → PF_001
    │         purpose: target place exists + structural_state allows action
    │                  (Pristine/Damaged/Restored = OK for most actions;
    │                   Destroyed = soft-rejectable per kind; Removed = hard-reject)
    │
    │   3.5.c ★ map_layout ★                 → MAP_001
    │         purpose: visual graph constraints — cross-tier disallowed V1;
    │                  Travel-specific (connection valid + tier matches)
    │
    │   3.5.d ★ cell_scene ★                 → CSC_001
    │         purpose: cell-internal layout constraints — zone integrity;
    │                  walkable/placeable for write events modifying cell state
    │
  [stage 4] ★ lex_check ★
    │   purpose: hard physics-axiom enforcement (does this ability exist in this reality?)
    │   owner: WA_001 Lex
    │
  [stage 5] ★ heresy_check ★ (only if lex_check returned AllowedWithBudget)
    │   purpose: budget tracking + cascade-on-exceed
    │   owner: WA_002 Heresy
    │
  [stage 6] A6 output filter
    │   purpose: post-LLM output filter — NSFW, persona-break, cross-PC leak
    │   owner: 05_llm_safety
    │   (also where WA_006 Mortality death-detection sub-validator lives — provisional)
    │
  [stage 7] canon-drift check (A6-related but distinct)
    │   purpose: L1/L2/L3 canon consistency
    │   owner: 05_llm_safety + knowledge-service
    │
  [stage 8] causal-ref integrity (EVT-A6)
    │   purpose: referenced parent events exist + same-reality + gap-free
    │   owner: event-model
    │
  [stage 9] world-rule lint (general)
    │   purpose: per-feature world-rule checks not covered by Lex/Heresy
    │   owner: cross-cutting (each feature's validator)
    │
  [commit] dp::advance_turn OR dp::t2_write per feature contract
```

### Hot-path checks (PRE-pipeline gate)

These run BEFORE the validator pipeline (cheap rejects to save validator cost):

| Check | Owner | Purpose |
|---|---|---|
| Turn-slot availability | PL_001 (turn-slot Strict) + DP-Ch51 | Claim turn-slot before processing turn |
| Idempotency cache | PL_001 §14 | Cached response returns immediately for retries |
| Mortality state | WA_006 Mortality (PROVISIONAL — should be PL_001 hook) | Reject turns from Dead/Dying/Ghost PCs |
| Concurrent-turn detection | PL_002 §6 | Reject second turn-submit while first is in-flight |

### Post-commit side-effects

These run AFTER commit (queued during validator pipeline; executed in same handler):

| Side-effect | Owner | Trigger |
|---|---|---|
| FictionClock advance | PL_001 §3.1 | After Accepted PlayerTurn with `fiction_duration > 0` |
| ContaminationState increment | WA_002 Heresy | After Accepted action that consumed contamination budget |
| WorldStability strain bump | WA_002 Heresy | After Accepted contamination action with `ConvertWorldEnergy` substrate |
| NpcReactionPriority `last_reacted_turn` update | NPC_002 Chorus | After Accepted NPCTurn from Chorus |
| MortalityState transition (provisional) | WA_006 Mortality | After PlayerTurn/NPCTurn with death-detection trigger |
| ForgeAuditEntry append | WA_003 Forge | After every ForgeEdit AdminAction |
| Idempotency cache write | PL_001 §14 | After every accepted/rejected turn (60s TTL) |
| **PlaceDestroyed cascade** (added 2026-04-26 alignment review) | PF_001 §6.1 | After Accepted PF_001 place state delta `→ Destroyed`; emits dedicated EVT-T3 sub-shape with occupants list; consumer features (PCS_001 / NPC_001 / future Item / future EnvObject) subscribe for cascade response; cascade ordering 4-step deterministic per PF_001 §7 |
| **EntityLifecycle cascade (HolderCascade)** (added 2026-04-26) | EF_001 §6.1 | After Accepted EF_001 lifecycle delta from cascade source (parent destroyed → held items drop / containers cascade); deterministic atomic batch with cascading entity_binding deltas |

---

## Stage 3.5 sub-stage applicability (alignment review 2026-04-26)

Each sub-stage in the structural-validators group has an applicability predicate. When `applies_to_event(event) == false`, the sub-stage early-exits without running its expensive checks. This keeps the pipeline cheap for events where structural validation isn't relevant.

| Sub-stage | Applies when | Early-exit when |
|---|---|---|
| **3.5.a entity_affordance** | EVT-T1 Submitted with target entity_ids in payload (PL_005 InteractionKinds: Speak/Strike/Examine/Give/Use); EVT-T1 sub-types referencing entities | EVT-T4 System (DP-emitted; no actor target) · EVT-T8 Administrative scope-based (no entity reference) · EVT-T3 Derived (already-validated cascade outputs) · payload has no entity_id field |
| **3.5.b place_structural** | Any event with cell-context (most PC actions; PL_005 InteractionKinds; Travel) | EVT-T8 Administrative pre-canon-active phase · cross-reality refs (V1+ only; structural across realities) · pure metadata events (no place reference) |
| **3.5.c map_layout** | Travel events specifically (PL_001 §13 cell-to-cell or non-cell-tier scripted-NPC-travel); Forge:EditMapLayout admin events | Non-Travel EVT-T1 · cell-internal events (PL_005 Speak/Strike/Examine/Give/Use within same cell) · entity_binding lifecycle deltas (handled by entity_affordance instead) |
| **3.5.d cell_scene** | Write events modifying cell state — Forge:EditCellScene; PL_005 Strike Destructive cascade triggers (place state transition); CSC's own Layer 3 LLM commit | Read events (cell scene UI subscribe) · non-cell scope events · already-canonical events that don't mutate cell layout |

**Applicability is determined by event-kind match against the predicate table.** Each sub-stage's owner-feature documents the predicate in their spec (EF_001 §11 / PF_001 §12 / MAP_001 §12 / CSC_001 §13). Validator implementation calls `applies_to_event(event)` first; skips cleanly if false.

---

## Soft-override mechanism (Q4 alignment 2026-04-26)

EF_001 §8 declares per-rule_id soft-override eligibility (e.g., `entity.entity_destroyed` is soft-overridable for Examine kind). The mechanism is INTERNAL to the entity_affordance validator (Stage 3.5.a):

```
entity_affordance validator logic:
  ┌─────────────────────────────────────────────────────────────┐
  │ for each entity_ref in event.targets:                       │
  │   tile = lookup(entity_ref) → fail entity.unknown_entity    │
  │   lifecycle = tile.lifecycle_state                          │
  │                                                              │
  │   if lifecycle == Destroyed:                                │
  │     if event.kind has tolerates_destroyed flag:             │
  │       ★ SOFT-PASS: emit warning; pipeline continues ★       │
  │     else:                                                    │
  │       ✗ HARD-FAIL: reject entity.entity_destroyed           │
  │                                                              │
  │   if lifecycle == Removed:                                  │
  │     ✗ HARD-FAIL: reject entity.entity_removed               │
  │     (Removed has NO soft-override; "this entity never was")│
  │                                                              │
  │   if lifecycle == Suspended:                                │
  │     similar tolerates_suspended check per kind              │
  │                                                              │
  │   ... affordance checks                                      │
  └─────────────────────────────────────────────────────────────┘
```

Pipeline downstream (lex / heresy / etc.) sees pass/fail only — soft-override is invisible at stage boundary. PL_005 InteractionKindSpec declares `tolerates_destroyed: bool` and `tolerates_suspended: bool` per kind (EF_001 §8 referenced contract).

Same pattern applies to other sub-stages with rule_ids marked "soft-override eligible" in their respective namespace tables (PF_001 §9 + MAP_001 §9 + CSC_001 §10.2).

---

## Stage → rule_id namespace matrix (Q6 alignment 2026-04-26)

Helps onboarding — quick lookup "which stage owns my rule_id":

| Stage | Validator | rule_id prefix | Owner namespace V1 count | V1+ reservations |
|---|---|---|---|---|
| 0 | schema validate | (none — engine error) | — | — |
| 1 | capability check | `capability.*` | DP-K9 | — |
| 2 | A5 intent classification | (logged) | 05_llm_safety A5 | — |
| 3 | A6 sanitize | `oracle.*` / `canon_drift.*` (input layer subset) | 05_llm_safety | — |
| **3.5.a** | **entity_affordance** | **`entity.*`** | **EF_001 (10 V1)** | 2 V1+ (cyclic_holder_graph, cross_reality_reference) |
| **3.5.b** | **place_structural** | **`place.*`** | **PF_001 (12 V1)** | 4 V1+ (scheduled_decay_collision, cross_reality_connection, procedural_generation_rejected, connection_gate_unresolved) |
| **3.5.c** | **map_layout** | **`map.*`** | **MAP_001 (13 V1)** | 3 V1+ (cross_reality_layout, layout_too_dense, connection_method_unsupported) |
| **3.5.d** | **cell_scene** | **`csc.*`** | **CSC_001 (9 V1)** | 4 V1+ (skeleton_invalid, procedural_density_too_high, narration_unsafe_content, layer3_occupant_set_changed) |
| 4 | lex_check | `lex.*` | WA_001 | — |
| 5 | heresy_check | `heresy.*` | WA_002 | — |
| 6 | A6 output filter | (logged) | 05_llm_safety A6 | — |
| 7 | canon-drift check | `canon_drift.*` | 05_llm_safety | — |
| 8 | causal-ref integrity | (event-model) | event-model EVT-A6 | — |
| 9 | world-rule lint | `world_rule.*` | cross-cutting | — |

**Total V1 rule_ids in pipeline:** 10 + 12 + 13 + 9 + (existing pre-3.5 stages) = 44+ in `entity/place/map/csc` namespaces alone.

---

## Adding a new validator slot

When a future feature proposes a new validator slot:

1. Lock-claim `_LOCK.md`
2. Edit "Proposed ordering" above to insert the new stage at the right position
3. Document:
   - Slot name (e.g., `inventory_check`)
   - Owner feature
   - Purpose (one line)
   - Why it slots at that position (cost? dependency? safety?)
4. Update `01_feature_ownership_matrix.md` "Schema / envelope ownership" if applicable
5. Append `99_changelog.md`
6. Lock-release
7. Notify event-model agent if Phase 3 is still in progress; their work absorbs this final ordering

---

## Drift resolutions

These boundary-review decisions have been recorded here as the canonical resolution. When a feature's design doc disagrees, it's the feature doc that's stale.

| Drift watchpoint | Resolution |
|---|---|
| **LX-D5 (Lex slot ordering)** | Locked: stage 4 (per §7.1 above). |
| **HER-D8 (Heresy stage transitions emit EVT-T11 vs EVT-T8)** | Provisional: V1 emits EVT-T8 AdminAction-only; V1+30d adds EVT-T11 WorldTick. Captured in 04_event_taxonomy.md (event-model). |
| **GR-D8 (rejected-turn commit primitive)** | Pending event-model agent Phase 2 per-category contract for EVT-T1. PL_001/PL_002's `t2_write` interpretation stands as feature-side contract until reconciled. |
| **WA_006 Mortality hot-path slot** | Provisional: PRE-pipeline gate (see "Hot-path checks" table). When WA_006 is rewritten thin + PCS_001 owns `pc_mortality_state`, the gate logic stays here as a PL_001 hook. |
| **A6 sub-validator placement (death-detection / NSFW / canon-drift)** | A6 is multi-stage (sanitize at stage 3, output filter at stage 6, drift at stage 7). All sub-validators within A6 are 05_llm_safety territory. |
| **EF-Q3 (entity_affordance slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.a** (between A6-sanitize stage 3 and lex_check stage 4). Soft-override mechanism INTERNAL to validator per §"Soft-override mechanism" above. |
| **PF-Q1 (place_structural slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.b** (after entity_affordance, before map_layout/cell_scene). Same group as EF-Q3. |
| **MAP-Q1 (map_layout slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.c** (after entity_affordance + place_structural; Travel-specific applicability per §"Stage 3.5 sub-stage applicability" above). Same group. |
| **CSC-Q2 (cell_scene slot ordering)** | **RESOLVED 2026-04-26 alignment review.** Slotted at **Stage 3.5.d** (most specific; cell-internal write events only per applicability table). Same group. Completes the structural-validator group of 4. |

---

## Future hardening

V2+ may add:
- Telemetry per stage (latency, fail rate, fail reason) → SLO dashboards
- Per-tier validator subset (e.g., AdminAction skips canon-drift but runs capability)
- Async parallel validators where order doesn't matter
- Validator-result caching for repeat content (LLM outputs that get re-validated)

These are deferred. V1 is the linear ordering above.
