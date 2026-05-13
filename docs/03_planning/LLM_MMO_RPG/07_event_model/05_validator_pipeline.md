# 05 — Validator Pipeline Framework (EVT-V*)

> **Status:** LOCKED Phase 3a (Option C discipline 2026-04-25). Per [EVT-A5](02_invariants.md#evt-a5--validator-pipeline-runs-in-fixed-order-no-skips), the EVT-V* pipeline runs in fixed order with per-category subsets; this file specifies the **framework rules** (stages exist, fail-mode taxonomy, retry policy, hot-path gates, post-commit side-effects). Specific stage implementations + current stage ordering live in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) (SSOT, lock-coordinated as features add validators).
> **Stable IDs:** EVT-V1..EVT-V7. Never renumber. Retired IDs use `_withdrawn` suffix.
> **Resolves:** MV12-D11 (fiction_clock advance on world-rule rejection — answer: NO; per EVT-V4 rejected events commit with outcome=Rejected via t2_write but turn_number + fiction_clock unchanged).

---

## How to use this file

This file specifies the **mechanism + rules** the validator pipeline obeys. When implementing a validator stage:

1. Pick a slot in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) (claim boundary lock first if adding a stage).
2. Implement per the **fail-mode taxonomy** (EVT-V2) — every stage declares its fail mode.
3. Implement per the **retry policy** (EVT-V3) — validator-rejection vs validator-error are distinct.
4. Honor **EVT-V4 rejection-path semantics** if your stage causes rejection of a Submitted event.
5. **Hot-path gates** (EVT-V5) and **post-commit side-effects** (EVT-V6) are coordinated separately from the main pipeline.

Specific stage implementations (A6 5-layer, A5-D1 intent classifier, world-rule lint per feature, etc.) live in their owning folders ([`../05_llm_safety/`](../05_llm_safety/), feature designs). This file does NOT redesign them — it specifies the framework they plug into.

---

## EVT-V1 — Pipeline framework

**Rule:** Every event candidate (committed event or proposal) passes through a **single linear pipeline** of validator stages running in **fixed order**. The current stage list lives in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md). Per [EVT-A5](02_invariants.md#evt-a5--validator-pipeline-runs-in-fixed-order-no-skips): producers cannot reorder, skip, or short-circuit stages within an applicable subset.

**Per-category subset:** each EVT-T* category declares which stages run (e.g., EVT-T4 System runs zero stages; EVT-T8 Administrative runs schema + capability + S5 dual-actor + causal-ref but skips A6 injection-defense + canon-drift). Subsets are **closed-set declared statically** in EVT-V* per category — cannot be modified at runtime.

**Stage discovery:** Event Model does NOT enumerate specific stages here. The authoritative current list is in `_boundaries/03_validator_pipeline_slots.md`; that file is lock-coordinated so features adding stages don't conflict.

**Why mechanism-only:** specific stages (A6 5-layer, world-rule, canon-drift) are owned by other folders ([`../05_llm_safety/`](../05_llm_safety/), feature designs). Event Model's job is the **framework** that ensures fixed order + no-skip discipline applies regardless of what specific stages exist.

**Cross-ref:** [EVT-A5](02_invariants.md#evt-a5--validator-pipeline-runs-in-fixed-order-no-skips), [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md), [`../05_llm_safety/`](../05_llm_safety/).

---

## EVT-V2 — Fail-mode taxonomy

**Rule:** Every validator stage declares one of **5 fail modes**. The fail mode determines what happens when validation fails for that stage:

| Fail mode | Pipeline action | Audit | Caller-visible result |
|---|---|---|---|
| **reject_hard** | stop pipeline; commit nothing OR commit Rejected outcome per EVT-V4 | SEV varies | error/rejection visible to producer |
| **reject_soft_with_retry** | stop pipeline; one auto-retry with adjusted prompt/state; if retry fails → reject_hard | warn-only | retry transparent to producer; persistent fail visible |
| **sanitize_and_proceed** | mutate the event payload (e.g., escape delimiter), continue pipeline | warn-only | proceeds normally |
| **quarantine** | stop pipeline; isolate event in a holding area for manual operator review; do NOT auto-reject or auto-commit | SEV2 | producer sees `Quarantined { ticket_id }` |
| **warn_and_proceed** | log issue, continue pipeline; commit normally | warn-only | proceeds normally |

**Per-stage declaration:** each stage in `_boundaries/03_validator_pipeline_slots.md` declares its fail mode at registration time. Cannot be changed at runtime. Stages MAY have **per-rule fail-mode overrides** (e.g., A6 5-layer's persona-break check is `reject_soft_with_retry` while cross-PC-leak is `reject_hard`) — those overrides are documented in the owning folder, not redefined here.

**Why 5 modes:** matches the failure taxonomy from `05_llm_safety/04_injection_defense.md` (A6 has soft/hard split) + admin-action policy (S5 has quarantine for sensitive operations) + sanitize patterns (jailbreak input is sanitized + quoted, not rejected). 5 modes cover all observed cases without proliferation.

**Forbidden mode:** `silent_drop` — validator may not silently discard an event. Either it proceeds, gets rejected, gets sanitized, or gets quarantined. No invisible failures.

**Cross-ref:** [`../05_llm_safety/04_injection_defense.md`](../05_llm_safety/04_injection_defense.md) A6-D4 (4-tier output filter outcomes), [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md).

---

## EVT-V3 — Retry policy

**Rule:** Two distinct retry classes:

**Validator-rejection (the validator returned a Rejected verdict):**
- **NO automatic retry** by the pipeline. Producer/originator sees the rejection and decides next action (typically: PC sees soft-fail UX per A5-D4 fallback; LLM-Originator does NOT retry the same proposal).
- Exception: `reject_soft_with_retry` mode (EVT-V2) allows ONE retry with adjusted state; that's a per-stage decision, not pipeline-level.

**Validator-error (the validator itself errored out — bug, dependency timeout, etc.):**
- **3 retries with exponential backoff** (default 1s / 4s / 16s — operational tunable, not Event Model lock).
- After 3 retries fail → quarantine the event (EVT-V2 mode `quarantine`) → SEV2 alert per SR9.
- Distinct from validator-rejection: error means "we don't know if this passes"; rejection means "we know it fails".

**Idempotency-based dedup:** retried events use the same `idempotency_key` (per uniform shape from [EVT-P*](04_producer_rules.md)). Commit primitive returns existing event_id on duplicate key — defense-in-depth against double-commit during retry storms.

**Cross-ref:** [EVT-V2 fail-mode taxonomy](#evt-v2--fail-mode-taxonomy), [EVT-P* idempotency key shape](04_producer_rules.md), I13 outbox retry semantics.

---

## EVT-V4 — Rejection-path semantics (resolves MV12-D11)

**Rule:** When the validator pipeline rejects an EVT-T1 Submitted event candidate, the rejection path commits a Submitted event with `outcome = Rejected { reason }` via `dp::t2_write` — **NOT** via `dp::advance_turn`. Per DP-A17, only `advance_turn` increments `turn_number`; every other channel-event commit (including this `t2_write`) tags with the **current (un-incremented)** `turn_number`. Therefore:

- **`turn_number` does NOT advance** on rejection
- **`fiction_clock` does NOT advance** (no advance_turn → no FictionClockAdvance side-effect)
- **PC may immediately retry** with a different command (no penalty turn-slot)
- **Audit completeness preserved** — the Rejected event IS committed, queryable, and replayable

This resolves [MV12-D11](../decisions/locked_decisions.md) ("does fiction_clock advance even when world-rule rejects the turn?") with the answer: **NO** — fiction_clock + turn_number advance only on accepted events. Rejected events are canon no-ops for time but ARE auditable canonical events.

**Why:** rejected turns shouldn't punish the player by advancing fiction-time (a 23-day `/travel` rejected at world-rule shouldn't burn 23 days). They also shouldn't be silently dropped (audit completeness). Committing as a separate channel event with `outcome=Rejected` + `turn_number=N` (unchanged) splits these correctly.

**Mechanism:** PL_001b §15 specifies the concrete sequence (claim turn-slot → run validators → on rejection: build TurnEvent with outcome=Rejected → `t2_write` → release turn-slot → return ack). Event Model locks the framework rule; PL_001b owns the implementation sequence.

**Idempotency for rejected events:** the rejected event still consumes its `idempotency_key` (preventing double-submit producing duplicate Rejected events). PL_001b §14.4 + EVT-V3 idempotency-based dedup applies.

**Cross-ref:** [PL_001b §15](../features/04_play_loop/PL_001b_continuum_lifecycle.md), [DP-A17](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25), [MV12-D11 deferral](99_open_questions.md).

---

## EVT-V5 — Hot-path PRE-pipeline gates

**Rule:** Some checks run **BEFORE the main validator pipeline** as fast-fail gates (cheap rejects to save validator cost). These are NOT skips — they are explicit short-circuit gates documented in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) "Hot-path checks" section.

Hot-path gates have specific properties:
- **Cost-bounded** — must complete in <10ms (otherwise belongs in main pipeline)
- **Rejection-only** — gates either pass (proceed to main pipeline) or reject; cannot sanitize / retry / quarantine / warn-and-proceed
- **Boundary-coordinated** — adding/removing a hot-path gate requires `_boundaries/_LOCK.md` claim
- **Independent failure** — a gate's failure does NOT depend on another gate's outcome (gates run sequentially but each is self-contained)

Examples currently in `_boundaries/03_validator_pipeline_slots.md`: turn-slot availability check (PL_001 + DP-Ch51), idempotency cache lookup (PL_001 §14), concurrent-turn detection (PL_002 §6). Mortality state (WA_006 provisional, eventually PL_001 hook).

**Why:** without an explicit "hot-path gate" concept, features would either (a) skip the validator pipeline entirely for performance (forbidden per EVT-A5), or (b) put cheap checks at the front of the main pipeline (slowing it down for events that would have rejected anyway). The gate concept gives a sanctioned fast-fail path.

**Forbidden:** any check that LLM-classifies, accesses external services, or takes >10ms must run in the main pipeline (EVT-V1), not as a hot-path gate.

**Cross-ref:** [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) "Hot-path checks", [DP-Ch51 turn-slot](../06_data_plane/21_llm_turn_slot.md), [PL_001 §14 idempotency](../features/04_play_loop/PL_001_continuum.md).

---

## EVT-V6 — Post-commit side-effects

**Rule:** Some operations run **AFTER commit** (queued during validator pipeline execution; executed in the same handler context after the main commit succeeds). These are canonical EVT-T3 Derived events emitted as side-effects of the parent EVT-T1 Submitted (or other parent category). They are NOT validators — they are downstream consequences.

Side-effects have specific properties:
- **Conditional on parent acceptance** — if parent commit fails, side-effects don't fire
- **Each is its own canonical event** (typically EVT-T3 Derived) with own causal-ref to parent
- **Order-preserving within a single commit handler** — side-effects fire in declared order
- **Can fail independently** — a side-effect failure does NOT roll back the parent commit (parent already committed); failure is logged + may trigger compensating action per feature design

Examples currently in `_boundaries/03_validator_pipeline_slots.md`: FictionClockAdvance (PL_001 after Accepted PCTurn), ContaminationState increment (WA_002 after contamination action), NpcReactionPriority `last_reacted_turn` update (NPC_002 after Accepted NPCTurn), ForgeAuditEntry append (WA_003 after every ForgeEdit Administrative), idempotency cache write (PL_001 after every accepted/rejected turn).

**Why mechanism-only:** specific side-effects are feature-owned (PL_001 owns FictionClockAdvance; WA_002 owns Contamination updates; etc.). Event Model locks the framework: side-effects exist, fire after parent commit, are themselves canonical events with causal-refs.

**Forbidden:** side-effects that mutate state without emitting a canonical event (would violate [EVT-A10 event as universal source of truth](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25)). Every side-effect → an EVT-T* commit.

**Cross-ref:** [EVT-A10](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) "Post-commit side-effects".

---

## EVT-V7 — Dead-letter framework

**Rule:** Events that reach a terminal failure state (validator-rejection without retry, validator-error after exhausted retries, quarantine timeout) are committed to a **dead-letter destination** for operator review and potential replay. Dead-letter is a **framework**, not a specific Redis topic — operational design decides the concrete destination + retention.

**Dead-letter contents** (per entry):
- `original_event_id` (or `proposal_id` for Proposals that never got a channel_event_id)
- `producer_service` + `originator_service` (if differs)
- `failure_reason` (taxonomy: `ValidatorRejected { stage, rule_id, detail }` / `ValidatorError { stage, error }` / `QuarantineTimeout` / `ProposalExpired`)
- `retry_count` + `final_attempt_at`
- `original_payload` (preserved for forensic + replay)

**Retention:** operational tunable. Default guidance: 7 days for routine rejections; 30 days for security-relevant rejections (canon-drift, A6 cross-PC leak attempts). Specific values locked in operational ops doc, not Event Model.

**Replay:** operator-initiated via admin command (Phase 4 reserves admin command name). Replay re-runs the original event through the validator pipeline as if freshly submitted; idempotency key mechanism prevents duplicate commits.

**Why mechanism-only:** specific destinations (Redis Streams topic vs Postgres table vs object storage bucket) are operational; framework guarantees existence + retention + replay capability without locking implementation.

**Cross-ref:** [EVT-V3 retry policy](#evt-v3--retry-policy), I13 outbox dead-letter pattern, S5 admin command registry.

---

## Per-category validator subset summary

Authoritative current subsets are in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md). Quick reference:

| EVT-T* | Validator subset (high-level) | Special notes |
|---|---|---|
| **T1 Submitted** | full pipeline (schema → capability → A5 → A6 sanitize → world-rule lint → A6 output → canon-drift → causal-ref → commit) | A6 only fires for sub-types originated from EVT-T6 Proposal; rejected commits via `t2_write` per EVT-V4 |
| **T3 Derived** | schema → capability (DP-K9 write claim) → world-rule lint → causal-ref → commit | no A6 (Derived is producer-trusted output) |
| **T4 System** | none | DP-internal, trusted by construction |
| **T5 Generated** | schema → capability → causal-ref → commit; world-rule lint optional per Generator | no A6; **EVT-A9 RNG determinism enforced at lint + replay** |
| **T6 Proposal** | full pipeline runs ON the proposal as input | proposal lifecycle; output is `Validated → commit fresh T1 Submitted` or `Rejected → dead-letter` |
| **T8 Administrative** | schema → capability (S5 actor + impact-class) → S5 dual-actor (Tier 1 only) → world-rule lint (optional override) → causal-ref → commit | no A6 (operator-authenticated, not adversarial) |

Per-rule fail modes within each stage are documented in the stage's owning folder.

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-V1 | Pipeline framework | Single linear pipeline; fixed order; per-category subsets; current stage list in `_boundaries/03_validator_pipeline_slots.md` |
| EVT-V2 | Fail-mode taxonomy | 5 modes: reject_hard / reject_soft_with_retry / sanitize_and_proceed / quarantine / warn_and_proceed; silent_drop forbidden |
| EVT-V3 | Retry policy | Validator-rejection: no auto-retry; validator-error: 3 retries with backoff → quarantine; idempotency-based dedup |
| EVT-V4 | Rejection-path (MV12-D11) | Rejected events commit via `t2_write` with outcome=Rejected; `turn_number` + `fiction_clock` UNCHANGED |
| EVT-V5 | Hot-path PRE-pipeline gates | Fast-fail gates run before main pipeline; <10ms cost-bounded; rejection-only; boundary-coordinated |
| EVT-V6 | Post-commit side-effects | Side-effects fire after parent commit; each is its own canonical EVT-T3 with causal-ref; per EVT-A10 universal SSOT |
| EVT-V7 | Dead-letter framework | Terminal failures committed to dead-letter for operator review + replay; specific destinations operational |

---

## Cross-references

- [EVT-A5 fixed validator order](02_invariants.md#evt-a5--validator-pipeline-runs-in-fixed-order-no-skips) — invariant this file implements
- [EVT-A10 event as universal SSOT](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25) — drives EVT-V6 side-effect rule
- [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) + [EVT-A12 extensibility](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) — extension point (d) covers adding validator stages
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — per-category validator subset table (current)
- [`04_producer_rules.md`](04_producer_rules.md) — idempotency key shape used by EVT-V3 retry dedup
- [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) — Phase 3b: bus delivery + dead-letter destination
- [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) — **AUTHORITATIVE current stage ordering** (lock-coordinated)
- [`../05_llm_safety/`](../05_llm_safety/) — A3 / A5 / A6 stage implementations
- [PL_001b §15](../features/04_play_loop/PL_001b_continuum_lifecycle.md) — concrete rejection-path sequence (MV12-D11 implementation)
- [DP-Ch51 turn-slot](../06_data_plane/21_llm_turn_slot.md) — hot-path gate example
- S5 ADMIN_ACTION_POLICY — Tier 1 dual-actor in EVT-T8 Administrative subset
