# 03 — Validator Pipeline Slot Ordering (EVT-V*)

> **Status:** seed 2026-04-25 — coordinates the validator slots multiple features have proposed for the EVT-V* pipeline.
>
> **Lock-gated:** edit only with the `_LOCK.md` claim active.
>
> **Authoritative source pending:** event-model agent's Phase 3 (`07_event_model/05_validator_pipeline.md`) will LOCK the final ordering. Until that lands, this file is the working consensus.

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

---

## Future hardening

V2+ may add:
- Telemetry per stage (latency, fail rate, fail reason) → SLO dashboards
- Per-tier validator subset (e.g., AdminAction skips canon-drift but runs capability)
- Async parallel validators where order doesn't matter
- Validator-result caching for repeat content (LLM outputs that get re-validated)

These are deferred. V1 is the linear ordering above.
