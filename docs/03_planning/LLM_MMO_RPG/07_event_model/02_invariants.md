# 02 — Invariants (Axioms)

> **Status:** LOCKED. Every axiom here was decided in user-approved Phase 0 + Phase 1 POST-REVIEW (2026-04-25) and may not be changed without a superseding decision recorded in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) and a cross-reference entry in [`99_open_questions.md`](99_open_questions.md).
> **Stable IDs:** EVT-A1..EVT-A8. These IDs are referenceable from any other doc in this project. Never renumber. Retired IDs use `_withdrawn` suffix.

---

## How to use this file

Each axiom is a locked constraint on every feature emitting or consuming events. When designing a feature:

1. Read every axiom before declaring an event in your feature's design doc.
2. If a feature requirement appears to conflict with an axiom, escalate via [`99_open_questions.md`](99_open_questions.md) — do not work around.
3. When referencing an axiom from another doc, cite it by ID (e.g., "per EVT-A1, ...").

Axioms are not principles. They are mechanically checked at design review.

---

## EVT-A1 — Closed-set event taxonomy

**Rule:** Every event committed to a per-reality channel event log (or, for EVT-T8 LLMProposal, emitted onto the proposal bus) belongs to **exactly one** EVT-T* category from the closed set defined in [`03_event_taxonomy.md`](03_event_taxonomy.md). New events that don't fit an existing category require a superseding decision adding a new EVT-T* row before they can ship — never a "Misc" / "Other" category.

**Why:** Open-set taxonomy is the documented failure mode of long-lived MMO systems — every team adds its own event type, no two consumers agree on shape, schema migration becomes impossible. A closed set enumerated up-front gives feature designers a fixed menu and forces unfamiliar events through the design process before they reach production. Eight categories like PlayerTurn/SystemEvent are nearly free to enumerate now; eighty ad-hoc categories accumulated later are impossible to refactor.

**Threat model — IN scope:**
- Feature emits a new event shape without an EVT-T* assignment → caught at design review (DP-R2 + EVT review checklist)
- Producer disagreement (one feature classifies LLM-driven NPC turn as PlayerTurn, another as NPCTurn) → resolved by taxonomy reference at design review

**Threat model — OUT of scope:**
- Bypass via direct DB write → already prevented by DP-R3 (no raw kernel client imports)
- Malicious code injection inside a service process → out of scope per DP-A1 threat model

**Enforcement:**
- **Design review** — every feature design that emits or consumes events MUST cite an EVT-T* category for each event type. Missing citation blocks review.
- **Runtime (V1+30d goal)** — DP wire format adds a `category` field per event; SDK validates against the EVT-T* allowlist; unknown category → `DpError::UnknownEventCategory` (new variant) and audit-log a SEV2 event.
- **Schema lint (V2+ goal)** — codegen step extracts every emitted event type from feature crates and asserts it has an EVT-T* mapping in this folder.

**Consequence:** Adding a 12th category is a deliberate process: open EVT-Q*, justify why no existing category fits, get user sign-off, add EVT-T12 row, lock. Cheap if done early; impossible to skip later. Renaming an existing category requires `_withdrawn` suffix on the old ID per stable-ID rules (foundation I15).

**Cross-ref:** [`03_event_taxonomy.md`](03_event_taxonomy.md) for the full EVT-T1..T11 enumeration + closed-set proof.

---

## EVT-A2 — Event Model layers above DP, never modifies DP

**Rule:** Every commit mechanism in Event Model uses an existing DP primitive (`dp::advance_turn` / `dp::t2_write` / `dp::t3_write` / DP-internal canonical event emission / aggregator runtime). Event Model adds no new primitive to DP, never bypasses DP rulebook (DP-R1..R8), and does not modify DP wire format (channel_event_id allocation, capability JWT shape, cache key format) beyond what DP itself supports as additive data.

**Why:** DP is LOCKED 2026-04-25 across 53 stable IDs across 25 files. Modifying DP from Event Model would re-open the entire LOCK ceremony and potentially break feature designs already citing DP IDs. Layering above DP keeps both contracts coherent and keeps Event Model changes cheap.

**Enforcement:**
- **Read-only access** to all `06_data_plane/` files from this folder's edit scope.
- **Design review** — any Event Model design citing a DP primitive must use the DP-K* signature unchanged. Modifications surface as EVT-Q* escalation, not silent edits.
- **Cross-folder boundary test** (per [`01_scope_and_boundary.md`](01_scope_and_boundary.md) §3) — queries that fall in DP namespace get redirected, not answered.

**Consequence:**
- New events use existing DP commit primitives. If a category truly needs a new commit primitive (e.g., a "broadcast-to-all-channels" emission), it is escalated as a DP gap, not implemented in Event Model.
- The wire-format coupling between Event Model categories and DP commitment mechanisms is documented per category in [`03_event_taxonomy.md`](03_event_taxonomy.md). Drift between EVT-T* and DP-K* requires both folders to update in lockstep.

**Cross-ref:** [DP-A2](../06_data_plane/02_invariants.md#dp-a2--control-plane--data-plane-split) (CP/DP split). [DP-K12](../06_data_plane/04d_capability_and_lifecycle.md#dp-k12--api-surface-summary) (~42-primitive surface).

---

## EVT-A3 — All canonical state changes flow through validated events

**Rule:** A change to per-reality canonical state (event log content, projection-derived state, fiction-clock advancement, NPC-PC relationship state, scene state, etc.) must occur as the **commit step of an EVT-T* event that has passed the EVT-V* validator pipeline**. Feature code may not bypass the pipeline by writing directly to projections or by emitting events that skip required validators.

**Why:** Without this rule, validators become advisory and feature-skippable. Canon-drift defense (A6) and capability gating (DP-K9) only work if every state-changing path is gated by validators. Bypass paths produce silent canon corruption that's near-impossible to detect after the fact.

**Threat model — IN scope:**
- Feature emits an event but skips validator pipeline (e.g., direct outbox write) → caught by producer-rule enforcement (EVT-P*) + design review
- Feature writes to projection directly without an event → already prevented by DP-R3 (no raw client imports) + DP-A8 (durable tier delegates to 02_storage event-log)
- LLM-driven action commits without world-rule validation → caught by EVT-V* mandatory ordering

**Threat model — OUT of scope:**
- Compromised service process performing arbitrary writes → infrastructure threat, not Event Model
- Admin-action overrides — these have a separate EVT-T10 category with their own validator subset (audit-only, fewer game-rule validators); not "bypass", just a different validator chain

**Enforcement:**
- **Design review** — every state-changing operation in a feature design must cite the EVT-T* event it commits as.
- **Lint (Phase 3 deliverable)** — EVT-V* pipeline implementation rejects commit attempts not preceded by the required validator chain for the event's category.
- **Producer-rule binding (EVT-P*)** — each producer-service is registered with a category-specific commit path; off-path writes fail at the SDK layer.

**Consequence:**
- Internal SDK / DP-emitted canonical events (EVT-T9 SystemEvent) bypass user-level validators — they are DP-internal and trusted by construction. Their validator chain is "DP commit succeeded" only.
- AdminAction (EVT-T10) has its own validator subset documented in EVT-V* — not a bypass.
- LLMProposal (EVT-T8) is the explicit pre-validation lifecycle stage: a proposal exists BEFORE it has cleared validators. Once validated, it is promoted to PlayerTurn or NPCTurn. Rejection emits a separate audit event but never commits the original proposal.

**Cross-ref:** [DP-R3 No raw clients](../06_data_plane/11_access_pattern_rules.md#dp-r3--no-raw-db-or-cache-client-imports-in-feature-code), [DP-A8 Durable = 02_storage](../06_data_plane/02_invariants.md#dp-a8--durable-tier-delegates-to-02_storage-unchanged), I13 outbox pattern.

---

## EVT-A4 — Producer-category binding

**Rule:** Each EVT-T* category has **exactly one** authorized producer service/role (or a small enumerated set), defined in [`04_producer_rules.md`](04_producer_rules.md) (Phase 2). Cross-category emission — a service emitting events outside its assigned categories — is forbidden at design time and rejected at runtime. The capability JWT (DP-K9) is the runtime enforcement: each producer-service receives a JWT with claims listing the EVT-T* categories it may emit.

**Why:** Without producer binding, any service could emit any event, and the validator pipeline would be the only line of defense. Capability discipline at the producer level adds an early-gate defense before the validator runs, and makes audit trails clean ("PlayerTurn always comes from gateway → roleplay-service → world-service" is a precise statement, not a guideline).

**Threat model — IN scope:**
- Quest engine accidentally emitting PlayerTurn instead of QuestBeat → JWT denies + audit-logs
- Roleplay-service emitting committed PlayerTurn instead of LLMProposal → JWT denies (roleplay-service has `produce: LLMProposal` only, not `produce: PlayerTurn`)
- Wrong service committing AdminAction → JWT denies; admin-cli is the only authorized producer

**Threat model — OUT of scope:**
- Compromised admin-cli credentials — infrastructure threat
- Capability-token forgery — covered by DP-K9 signing (not Event Model concern)

**Enforcement:**
- **Capability JWT** (DP-K9) carries `produce: [EVT-T*]` claim per producer service.
- **SDK layer** rejects emission attempts where the event's category is not in the producer's claim set.
- **Design review** — feature design declares which categories its service produces; review checks against EVT-P* and adjusts JWT issuance.
- **Audit log** — every cross-category emission attempt logged as SEV2 (security-relevant misuse).

**Consequence:**
- Multi-role services need multiple JWT claims (e.g., world-service has `produce: PlayerTurn, NPCTurn, AggregateMutation, CalibrationEvent`).
- DP-emitted EVT-T9 SystemEvent has no service producer — DP itself is the "producer" and is trusted by construction. Capability JWT does not gate DP-internal emission.
- LLMProposal vs PlayerTurn split is the canonical example: roleplay-service can ONLY emit LLMProposal, never the validated PlayerTurn. World-service can ONLY emit validated PlayerTurn (after consuming the proposal), never proposals.

**Cross-ref:** [DP-K9 Capability tokens](../06_data_plane/04d_capability_and_lifecycle.md#dp-k9--capability-tokens), [`04_producer_rules.md`](04_producer_rules.md) (Phase 2).

---

## EVT-A5 — Validator pipeline runs in fixed order, no skips

**Rule:** Every event candidate (a freshly produced EVT-T* event before commit) passes through the EVT-V* validator pipeline in the **fixed order** defined in [`05_validator_pipeline.md`](05_validator_pipeline.md) (Phase 3). Producers cannot reorder, skip, or short-circuit validators. Per-category validator subsets are allowed (e.g., AdminAction skips canon-drift but runs capability + schema), but within an applicable validator's scope, its order relative to others is fixed.

**Why:** Validator order matters: schema validation must precede canon-drift (you can't drift-check a malformed payload); capability check must precede schema (no point parsing if caller is unauthorized); intent classification must precede world-rule lint (you can't apply combat-relevant rules to a `/whisper`); causal-ref integrity must run before commit because it can fail with referenced-event-missing. A fixed order makes failure modes diagnoseable (you know which validator caught a fault) and retry policy precise (which validators are idempotent on retry).

**Enforcement:**
- **Pipeline implementation (Phase 3)** is the single chokepoint for all events. No alternate paths.
- **Lint** flags any direct commit call (`dp::advance_turn` / `dp::t2_write`) from feature code that wasn't preceded by `EventValidator::validate(event).await?`.
- **Per-category validator subset declared statically** in EVT-P* — cannot be modified at runtime.
- **Design review** — feature designs that claim "skip canon-drift here because…" are rejected; if a real reason exists, it goes through EVT-Q* + validator-policy adjustment, not feature-level bypass.

**Consequence:**
- Validator order changes are an axiom-level edit (this file) requiring superseding decision in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md). Cheap once; chaos repeated.
- Per-category subsets are documented per EVT-T* in [`03_event_taxonomy.md`](03_event_taxonomy.md) and locked in EVT-P*.
- Performance optimization that skips a validator must be reformulated as "validator X is fast-path-eligible if Y" with explicit ordering, not as bypass.

**Cross-ref:** [`05_validator_pipeline.md`](05_validator_pipeline.md) (Phase 3), [`../05_llm_safety/`](../05_llm_safety/) for A3/A5/A6 internals.

---

## EVT-A6 — Causal references are typed, single-reality, gap-free

**Rule:** When event B causes event A, the causal reference uses the shape **`CausalRef { channel_id: ChannelId, channel_event_id: u64 }`** (extending DP-A15's bubble-up shape for general use). Multiple parents allowed: `causal_refs: Vec<CausalRef>`. All referenced events MUST be in the **same reality** as the referencing event; cross-reality references are rejected with `DpError::CausalRefCrossReality` at validator-pipeline time. The referenced event MUST exist in the channel's event log at validation time; missing-reference is rejected with `DpError::CausalRefMissing` (do not silently drop).

**Why:** Causal references make the event log auditable as a graph rather than a flat sequence. Bubble-up needs them (DP-A15). Quest beats need them (QuestBeat → causes → WorldTick when quest completion triggers a world event). LLMProposal-to-PlayerTurn validation needs them. NPC reaction turns need them (NPCTurn caused-by previous PlayerTurn in the same scene). A single typed shape across all use cases prevents the "every feature reinvents this" anti-pattern.

Single-reality constraint mirrors DP's reality-scoped channel model (DP-A7, DP-A12). Cross-reality references would require coordination outside DP — which is the dedicated `meta-worker` service's job (R5), not Event Model.

**Enforcement:**
- **Schema (Phase 4 EVT-S*)** — every event payload carries optional `causal_refs: Vec<CausalRef>` field.
- **Validator pipeline (EVT-V*)** has a dedicated causal-ref integrity validator that:
  - rejects empty `causal_refs` for categories that REQUIRE them (e.g., NPCTurn must reference the triggering turn; QuestBeat::Outcome must reference the QuestBeat::Trigger),
  - rejects cross-reality references with `DpError::CausalRefCrossReality`,
  - rejects missing references with `DpError::CausalRefMissing`,
  - accepts forward references only at producer-side queueing (the validator runs after target-event-commit).

**Consequence:**
- Replay (Phase 4 EVT-L*) can walk the causal graph for debugging — given any committed event, find its full upstream chain via repeated `causal_refs` lookup.
- Bubble-up RNG seed (DP-Ch27) uses the deterministic `channel_event_id` of the triggering source — already aligned with this axiom.
- Cross-reality canon propagation (DF12 withdrawn V1; potentially V2+) is intentionally NOT supported by causal_refs — that flows through `meta-worker` xreality.* topics, not the per-reality event log.

**Cross-ref:** [DP-A15 Per-channel total ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), [DP-Ch27 Deterministic RNG](../06_data_plane/16_bubble_up_aggregator.md#dp-ch27--deterministic-rng), [`09_causal_references.md`](09_causal_references.md) (Phase 4).

---

## EVT-A7 — LLM proposals are pre-validation only; never authoritative

**Rule:** Events emitted by LLM-driven services (Python `roleplay-service`, future LLM services) are **always EVT-T8 LLMProposal** events on the proposal bus, **never directly committed canonical events**. A proposal becomes a committed event (EVT-T1 PlayerTurn or EVT-T2 NPCTurn) only after the EVT-V* validator pipeline running in Rust `world-service` consumes the proposal, validates it, and commits via `dp::advance_turn`. A rejected proposal is logged + dead-lettered; the original proposal is never promoted retroactively.

**Why:** LLM outputs are untrusted. They fail in three categories that the EVT-V* pipeline catches:
1. **Injection** — A6 5-layer defense detects jailbreaks; output filter blocks cross-PC leaks
2. **Canon drift** — world-rule lint + canon-drift detector catch L1 axiom violations and L3 internal contradictions
3. **Capability** — DP-K9 ensures LLM cannot escalate (NPC tries to "transmute" a player; classifier+world-rule reject)

Putting LLMs directly on the commit path collapses all three defenses into prompt-engineering luck. The proposal-bus split keeps Rust authoritative and Python advisory.

This is the concrete realization of [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) (Python event-only) — DP-A6 locked the direction; EVT-A7 locks the lifecycle stage and validator chain.

**Enforcement:**
- **Capability JWT** — `roleplay-service` JWT carries `produce: [LLMProposal]` only. Direct emission of PlayerTurn/NPCTurn/AggregateMutation is denied (EVT-A4 producer binding).
- **Bus protocol** ([`07_llm_proposal_bus.md`](07_llm_proposal_bus.md), Phase 3) — proposals carry `lifecycle_stage = Proposal`; commit primitives reject events tagged with non-`Validated` lifecycle.
- **Validator pipeline** runs A3/A5/A6 (LLM-safety internals) as core stages on every proposal before promoting it to a commit.
- **Audit** — every Proposal → Validated/Rejected transition is audit-logged with proposal_id, validator_results, decision.

**Consequence:**
- Roleplay-service cannot emit AggregateMutation directly. Any state delta must be derived by world-service from a validated PlayerTurn/NPCTurn (e.g., FictionClockAdvance after validating a PC turn that took 30s of fiction time).
- The "advisory tool-call" (A5-D3 allowed flavor tool-calls — `whisper`, `gesture`, `look_at`, `recall_memory`) does not require a separate event category; it lands as part of the NPCTurn payload after world-service validates and commits.
- Proposal idempotency uses an LLM-generated proposal_id to dedupe retries; world-service rejects double-commits via DP-A19 CausalityToken (subsequent reads see the prior commit). Detail in EVT-S* (Phase 4).
- Tool-call failure (A5-D4) emits a distinct EVT-T9 SystemEvent or audit-log entry; never silently fills with a fallback proposal.

**Cross-ref:** [DP-A6 Python event-only](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`../05_llm_safety/`](../05_llm_safety/) A3/A5/A6, [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## EVT-A8 — Flavor narration is NOT events

**Rule:** LLM-generated narrative text describing **non-canonical** scene texture during fast-forward (`/sleep`, `/travel`), paused-mode periods, or routine-fill (V1+30d NPCRoutine flavor), or any narration explicitly marked `flavor=true` by the producing service, is **NOT committed as an event** to the channel event log. Such text is regenerable per retell; non-canonical; not subject to EVT-V* validators (other than basic safety filters); not in causal-ref graph. Only the **structural deltas** caused by the fast-forward (money decremented, location changed, fiction-clock advanced) are committed as canonical events.

**Why:** SPIKE_01 §6 obs#16 + obs#21 surfaced this rule. During a `/travel` of 23 days, the LLM narrates "Hai mươi ba ngày đường sau" + travel encounters + body-memory shifts — that text is feature texture, not a canon-grade fact. If that narration were canonical, replay would have to reproduce identical text (impossible with LLM non-determinism), validators would have to canon-check 23 days of generated travel encounters (cost-prohibitive), and the event log would balloon with disposable text.

The split is principled: LLM narration during a fast-forward = flavor; the structural delta (money -8, location=Tương Dương cổng Nam) = canonical. Each retell of "what did Lý Minh see during travel?" can vary; "where is Lý Minh now and how much money does he have?" cannot.

**Enforcement:**
- **Producer-side discipline** — services emitting fast-forward narration tag the text payload `flavor: true`; SDK rejects commits attempting to log flavor as canonical EVT-T1/T2/T3/T4.
- **Per-category contract (Phase 2 EVT-T*)** — TurnEvent::FastForward + TurnEvent::Narration sub-shapes have an explicit `flavor_text: Option<String>` field that does NOT replicate to canon-affecting state, only into a separate non-canonical text store (audit-log retention only, not canon).
- **Validator pipeline (EVT-V*)** — flavor text passes ONLY safety filters (A6 output filter, NSFW), not canon-drift / world-rule / causal-ref validators.
- **Replay (EVT-L*, Phase 4)** — flavor text is regenerated per retell via prompt context, not replayed verbatim. Time-travel debug replay shows the original flavor text from audit log when available, but does not validate it.

**Consequence:**
- A future PC arriving in Yên Vũ Lâu after Lý Minh's sleep cannot retrieve "what did Lý Minh dream?" because that flavor never committed. NPC Lão Ngũ may answer differently each retell.
- Long-skip narration (LLM creative writing during /travel) does not consume canon-drift validator budget. Saves cost.
- The boundary between flavor and structural-delta is a feature-design decision per category. PL_001 §12 + SPIKE_01 §11 candidate MV12-D8 will land it in EVT-T1 PlayerTurn FastForward sub-type contract (Phase 2).

**Cross-ref:** SPIKE_01 §6 obs#16 / obs#21, MV12-D8 candidate (deferred per [`99_open_questions.md`](99_open_questions.md)).

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-A1 | Closed-set taxonomy | Every event maps to exactly one EVT-T*; no "Other" |
| EVT-A2 | Layers above DP | Event Model uses DP primitives unchanged; never modifies DP |
| EVT-A3 | Validated events for canonical writes | All canonical state changes go through EVT-V* validator pipeline |
| EVT-A4 | Producer-category binding | Each EVT-T* has authorized producers; capability JWT enforces |
| EVT-A5 | Fixed validator order | EVT-V* pipeline order is locked; no skip / no reorder |
| EVT-A6 | Typed single-reality causal refs | `CausalRef { channel_id, channel_event_id }`; same-reality only; gap-free |
| EVT-A7 | LLM proposals pre-validation only | Python emits LLMProposal; Rust validates → commits PlayerTurn/NPCTurn |
| EVT-A8 | Flavor narration is not events | Fast-forward narration text is non-canonical; structural delta is canonical |

Any change to an axiom is logged in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) with a new locked-decision entry; the superseded axiom gets a `_withdrawn` suffix rather than being deleted.

---

## How invariants get added

New EVT-A* invariants follow the same process as foundation I*:

1. A concrete enforcement point (validator-pipeline check, capability JWT claim, design-review checklist row, lint script).
2. A subfolder owner (this folder; all EVT-A* live here).
3. Architect sign-off via Phase POST-REVIEW.
4. Same-commit update to the enforcing mechanism (validator pipeline spec, capability claims doc, design-review template).

Invariants without concrete enforcement are wishes. Wishes are not invariants.
