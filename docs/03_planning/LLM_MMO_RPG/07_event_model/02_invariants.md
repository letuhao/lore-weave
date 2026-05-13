# 02 — Invariants (Axioms)

> **Status:** LOCKED. Every axiom here was decided in user-approved Phase 0 / Phase 1 / Option-C-redesign POST-REVIEWs (2026-04-25) and may not be changed without a superseding decision recorded in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) and a cross-reference entry in [`99_open_questions.md`](99_open_questions.md).
> **Stable IDs:** EVT-A1..EVT-A12. Never renumber. Retired IDs use `_withdrawn` suffix.
> **Redesign note (2026-04-25):** Option C redesign reframed A4 / A7 / A8 to mechanism level + added A9..A12. Original Phase 1 axioms (commit `ce6ea97`) preserved by ID; substance evolved per the changelog in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) and `_boundaries/99_changelog.md`.

---

## How to use this file

Each axiom is a locked constraint on every feature emitting or consuming events. When designing a feature:

1. Read every axiom before declaring an event in your feature's design doc.
2. If a feature requirement appears to conflict with an axiom, escalate via [`99_open_questions.md`](99_open_questions.md) — do not work around.
3. When referencing an axiom from another doc, cite it by ID (e.g., "per EVT-A1, ...").

Axioms are not principles. They are mechanically checked at design review.

---

## EVT-A1 — Closed-set event taxonomy

**Rule:** Every event committed to a per-reality channel event log (or, for EVT-T6 Proposal, emitted onto the proposal bus) belongs to **exactly one** EVT-T* category from the closed set defined in [`03_event_taxonomy.md`](03_event_taxonomy.md). New events that don't fit an existing category require a superseding decision adding a new EVT-T* row before they can ship — never a "Misc" / "Other" category. Sub-types within a category are feature-defined and additive per I14 (see [EVT-A11](#evt-a11--sub-type-ownership-discipline) + [EVT-A12](#evt-a12--extensibility-framework)).

**Why:** Open-set taxonomy is the documented failure mode of long-lived MMO systems — every team adds its own event type, no two consumers agree on shape, schema migration becomes impossible. A closed set enumerated up-front gives feature designers a fixed menu and forces unfamiliar events through the design process before they reach production.

**Enforcement:**
- **Design review** — every feature design must cite an EVT-T* category for each event type it emits or consumes.
- **Runtime (V1+30d goal)** — DP wire format adds a `category` field per event; SDK validates against the EVT-T* allowlist.
- **Schema lint (V2+ goal)** — codegen step extracts every emitted event type from feature crates and asserts EVT-T* mapping.

**Consequence:** Adding a 7th category is a deliberate process: open EVT-Q*, justify why no existing category fits, get user sign-off, add EVT-T13 (next free), lock. Renaming an existing category requires `_withdrawn` suffix per I15.

**Cross-ref:** [`03_event_taxonomy.md`](03_event_taxonomy.md) for the full enumeration + closed-set proof.

---

## EVT-A2 — Event Model layers above DP, never modifies DP

**Rule:** Every commit mechanism in Event Model uses an existing DP primitive (`dp::advance_turn` / `dp::t2_write` / `dp::t3_write` / DP-internal canonical event emission / aggregator runtime). Event Model adds no new primitive to DP, never bypasses DP rulebook (DP-R1..R8), and does not modify DP wire format beyond what DP itself supports as additive data.

**Why:** DP is LOCKED 2026-04-25 across 53 stable IDs across 25 files. Modifying DP from Event Model would re-open the entire LOCK ceremony. Layering above DP keeps both contracts coherent.

**Enforcement:** Read-only access to all `06_data_plane/` files from this folder's edit scope. Design review redirects DP-namespace queries. Drift surfaces as EVT-Q* escalation.

**Consequence:** New events use existing DP commit primitives. If a category truly needs a new commit primitive, it is escalated as a DP gap, not implemented in Event Model.

**Cross-ref:** [DP-A2](../06_data_plane/02_invariants.md#dp-a2--control-plane--data-plane-split), [DP-K12](../06_data_plane/04d_capability_and_lifecycle.md#dp-k12--api-surface-summary).

---

## EVT-A3 — All canonical state changes flow through validated events

**Rule:** A change to per-reality canonical state (event log content, projection-derived state, fiction-clock advancement, NPC-PC relationship state, scene state, etc.) must occur as the **commit step of an EVT-T* event that has passed the EVT-V* validator pipeline**. Feature code may not bypass the pipeline by writing directly to projections or by emitting events that skip required validators.

**Why:** Without this rule, validators become advisory and feature-skippable. Canon-drift defense and capability gating only work if every state-changing path is gated. Bypass paths produce silent canon corruption that's near-impossible to detect after the fact.

**Enforcement:** Design review cites EVT-T* event for every state-change. EVT-V* pipeline implementation rejects non-piped commits. Producer-rule binding (EVT-A4) registers each producer-service with category-specific commit path.

**Consequence:**
- DP-emitted EVT-T4 System events bypass user-level validators — DP-internal, trusted by construction.
- EVT-T8 Administrative has its own validator subset (S5 actor + dual-actor for Tier 1) — not a bypass, just a different chain.
- EVT-T6 Proposal is the explicit pre-validation lifecycle stage; rejection emits audit event, never commits the original proposal.

**Cross-ref:** [DP-R3](../06_data_plane/11_access_pattern_rules.md#dp-r3--no-raw-db-or-cache-client-imports-in-feature-code), [DP-A8](../06_data_plane/02_invariants.md#dp-a8--durable-tier-delegates-to-02_storage-unchanged), I13 outbox pattern. Reinforced by [EVT-A10 event-as-SSOT](#evt-a10--event-as-universal-source-of-truth).

---

## EVT-A4 — Producer-role binding (REFRAMED 2026-04-25)

**Rule:** Each EVT-T* category has authorized **producer ROLE classes** (closed set, see below). A producing service inherits a role via its capability JWT (DP-K9). Specific service-name binding (which Rust service plays which role for V1) lives in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md), NOT in Event Model.

**Producer role classes** (closed set; mirrors `ActorId` enum from [NPC_001 §2](../features/05_npc_systems/NPC_001_cast.md#2-domain-concepts)):

| Role class | Emits | Trust model |
|---|---|---|
| **Player-Actor** (`ActorId::Pc`) | EVT-T1 Submitted (PC sub-types) via gateway → trusted-pipeline | untrusted input → validated |
| **Orchestrator** (`ActorId::Synthetic { ChorusOrchestrator }`) | EVT-T1 Submitted (NPC reactions); EVT-T6 Proposals on behalf of NPCs | partial-trust (LLM output validated) |
| **Aggregate-Owner** (per-feature, owns specific aggregate types) | EVT-T3 Derived (state deltas on owned aggregates) | service-trusted |
| **Generator** (`ActorId::Synthetic { BubbleUpAggregator | Scheduler | RealityBootstrapper }`) | EVT-T5 Generated | service-trusted; deterministic per EVT-A9 |
| **LLM-Originator** (Python) | EVT-T6 Proposal ONLY — never canonical commits | untrusted; pre-validation lifecycle |
| **Administrative** (`ActorId::Admin`) | EVT-T8 Administrative | operator-trusted via S5 dispatch |
| **DP-Internal** (DP itself) | EVT-T4 System | DP-trusted by construction |

**Why:** Anchoring to ROLE (not service name) keeps Event Model framework-level. When V1+ adds a quest-engine service or a non-LLM agentic service, the role class accommodates them without redefining axioms. Specific service↔role mappings are recorded in `_boundaries/`, the SSOT for ownership.

**Enforcement:**
- **Capability JWT** (DP-K9) carries `produce: [EVT-T*]` claim per producer service; the role class determines which categories.
- **SDK layer** rejects emission attempts where the event's category is not in the producer's claim set.
- **Boundary matrix** [`_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) records the current role↔service binding.

**Consequence:**
- Multi-role services exist (e.g., world-service plays Aggregate-Owner for several aggregates AND Orchestrator for NPC reactions).
- LLM-Originator role is a strict subset — Python services cannot escalate to other categories even if their JWT is forged. Matches DP-A6 direction.

**Cross-ref:** [DP-K9](../06_data_plane/04d_capability_and_lifecycle.md#dp-k9--capability-tokens), [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md), [NPC_001 §2 ActorId enum](../features/05_npc_systems/NPC_001_cast.md), [`04_producer_rules.md`](04_producer_rules.md).

---

## EVT-A5 — Validator pipeline runs in fixed order, no skips

**Rule:** Every event candidate (a freshly produced EVT-T* event before commit) passes through the EVT-V* validator pipeline in the fixed order defined in [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) (authoritative; Phase 3 [`05_validator_pipeline.md`](05_validator_pipeline.md) will lock the framework rules). Producers cannot reorder, skip, or short-circuit validators. Per-category validator subsets are allowed (e.g., EVT-T8 Administrative skips canon-drift but runs S5 dual-actor); within an applicable validator's scope, its order relative to others is fixed.

**Why:** Validator order matters: schema must precede canon-drift; capability must precede schema parse; intent classification must precede world-rule lint; causal-ref integrity must run before commit. A fixed order makes failure modes diagnoseable and retry policy precise.

**Enforcement:** Pipeline implementation is the single chokepoint for all events. Lint flags any direct commit call from feature code that wasn't preceded by validator pipeline. Per-category validator subset declared statically in EVT-V*; cannot be modified at runtime.

**Consequence:** Validator order changes are an axiom-level edit requiring superseding decision. Per-category subsets documented per EVT-T* in [`03_event_taxonomy.md`](03_event_taxonomy.md). Performance optimization that skips a validator must be reformulated as "validator X is fast-path-eligible if Y" with explicit ordering, not as bypass.

**Cross-ref:** [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) (current consensus ordering), [`../05_llm_safety/`](../05_llm_safety/) (A3/A5/A6 internals slot in).

---

## EVT-A6 — Causal references are typed, single-reality, gap-free

**Rule:** When event B causes event A, the causal reference uses the shape **`CausalRef { channel_id: ChannelId, channel_event_id: u64 }`** (extending DP-A15's bubble-up shape for general use). Multiple parents allowed: `causal_refs: Vec<CausalRef>`. All referenced events MUST be in the **same reality** as the referencing event; cross-reality references are rejected at validator-pipeline time. The referenced event MUST exist at validation time; missing-reference is rejected with `DpError::CausalRefMissing` (do not silently drop).

**Why:** Causal references make the event log auditable as a graph rather than a flat sequence. Bubble-up needs them (DP-A15). NPC reactions need them (NPCTurn refs PlayerTurn). Future quest features need them (Outcome refs Trigger). A single typed shape across all use cases prevents the "every feature reinvents this" anti-pattern.

Single-reality constraint mirrors DP's reality-scoped channel model. Cross-reality references would require coordination outside DP — that's `meta-worker`'s job (R5), not Event Model.

**Enforcement:**
- **Schema (Phase 4 EVT-S*)** — every event payload carries optional `causal_refs: Vec<CausalRef>` field.
- **Validator pipeline** has a dedicated causal-ref integrity validator that rejects empty `causal_refs` for categories that REQUIRE them (e.g., EVT-T1 Submitted with `actor_kind=Npc` reaction must reference triggering turn; EVT-T5 Generated must reference source events).
- **Cross-reality reject:** `DpError::CausalRefCrossReality`.

**Consequence:** Replay can walk the causal graph for debugging. Bubble-up RNG seed (DP-Ch27 / EVT-A9) uses the deterministic `channel_event_id` of the triggering source — already aligned. Cross-reality canon propagation flows through `meta-worker`, not the per-reality event log.

**Cross-ref:** [DP-A15](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), [DP-Ch27](../06_data_plane/16_bubble_up_aggregator.md#dp-ch27--deterministic-rng), [`09_causal_references.md`](09_causal_references.md) (Phase 4).

---

## EVT-A7 — Untrusted-origin events require pre-validation lifecycle (REFRAMED 2026-04-25)

**Rule:** Events produced by **untrusted-origin** services (Python LLM-driven services, future LLM/agentic services, future plugin/extension hosts) are **always EVT-T6 Proposal** events on the proposal bus, **never directly committed canonical events**. A proposal becomes a committed event (typically EVT-T1 Submitted) only after the EVT-V* validator pipeline running in a trusted commit-service consumes the proposal, validates it, and commits via the appropriate DP primitive. A rejected proposal is logged + dead-lettered; the original proposal is never promoted retroactively.

**"Untrusted-origin"** means the producer cannot self-attest to its output's safety: LLM outputs (jailbreak risk, canon drift, cross-PC leak), third-party plugins (V2+), agentic services (V2+) without provenance attestation. Trusted-origin producers (orchestrator emitting deterministic content, scheduler firing pre-declared beats) can commit directly.

**Why:** Untrusted outputs fail in three categories that the EVT-V* pipeline catches: injection (A6), canon drift (world-rule + canon-drift detector), capability escalation (DP-K9). Putting untrusted producers directly on the commit path collapses all three defenses into prompt-engineering luck. The proposal-bus split keeps trusted services authoritative and untrusted advisory.

This is the concrete realization of [DP-A6 Python event-only](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) — DP-A6 locked the direction; EVT-A7 locks the lifecycle stage and validator chain. Generalized beyond Python LLM to any future untrusted-origin source.

**Enforcement:**
- **Capability JWT** — untrusted-origin services carry `produce: [Proposal]` ONLY. Direct emission of canonical categories denied (EVT-A4).
- **Bus protocol** — proposals carry `lifecycle_stage = Proposal`; commit primitives reject events tagged with non-`Validated` lifecycle.
- **Validator pipeline** runs A3/A5/A6 + canon-drift + world-rule on every proposal before promoting to a commit.
- **Audit** — every Proposal → Validated/Rejected transition is audit-logged.

**Consequence:** Untrusted-origin services cannot emit EVT-T3 Derived directly. Any state delta must be derived by a trusted commit-service from a validated EVT-T1 Submitted (or other trusted source). Future non-LLM agentic services slot into this same pattern without further axiom changes.

**Cross-ref:** [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`../05_llm_safety/`](../05_llm_safety/) A3/A5/A6, [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## EVT-A8 — Non-canonical regenerable content is NOT events (REFRAMED 2026-04-25)

**Rule:** Content marked **non-canonical** by the producing service — typically LLM-generated narrative texture (`/sleep` dream sequences, `/travel` encounter flavor, paused-mode atmospheric narration), routine-fill flavor, or any payload explicitly tagged `flavor=true` — is **NOT committed as an event** to the channel event log. Such content is regenerable per retell; non-canonical; not subject to EVT-V* validators (other than basic safety filters); not in causal-ref graph. Only the **structural deltas** caused by the parent event (money decremented, location changed, fiction-clock advanced) are committed as canonical events.

**Why:** SPIKE_01 §6 obs#16 + obs#21 surfaced this rule. During a `/travel` of 23 days, the LLM narrates 23 days of travel encounters — that text is feature texture, not a canon-grade fact. If that narration were canonical, replay would have to reproduce identical text (impossible with LLM non-determinism), validators would have to canon-check 23 days of generated content (cost-prohibitive), and the event log would balloon with disposable text.

The split is principled: producer-tagged "flavor" = audit-stream-only, regenerable; "canonical" = committed to event log, replayable verbatim, validator-gated. Reframed from "narration" to "non-canonical regenerable content" so the rule applies to future cases beyond narrative text (e.g., procedurally regenerated decorative ambient state, LLM-inferred atmospheric details).

**Enforcement:**
- **Producer-side discipline** — services emitting flavor tag the payload `flavor: true` at the boundary; SDK rejects commits attempting to log flavor as canonical EVT-T1/T3/T5.
- **Per-category contract** — sub-shapes that carry both canonical + flavor split them into distinct fields (e.g., FastForward sub-type carries `structural_delta` canonical + `flavor_text_audit_id` non-canonical pointer).
- **Validator pipeline** — flavor passes ONLY safety filters (A6 output filter, NSFW), not canon-drift / world-rule / causal-ref validators.
- **Replay (EVT-L*)** — flavor is regenerated per retell via prompt context, not replayed verbatim. Time-travel debug replay shows original flavor from audit log when available, but does not validate it.

**Consequence:** A future PC arriving in a place after another PC's fast-forward cannot retrieve "what did they dream?" because that flavor never committed. Long-skip narration does not consume canon-drift validator budget. The flavor / canonical boundary is a feature-design decision per category; per-category contract section (Phase 2 [`06_per_category_contracts.md`](06_per_category_contracts.md)) specifies the split mechanism.

**Cross-ref:** SPIKE_01 §6 obs#16 / obs#21, MV12-D8 (resolved in Phase 2 contracts), reinforced by [EVT-A10 event-as-SSOT](#evt-a10--event-as-universal-source-of-truth) — events ARE canonical; flavor is not.

---

## EVT-A9 — Probabilistic generation determinism (NEW 2026-04-25)

**Rule:** EVT-T5 Generated events (rule/aggregator/scheduler-emitted with conditional or probabilistic logic) MUST use **deterministic RNG** seeded from a stable causal-ref — typically the triggering event's `(channel_id, channel_event_id)` per [DP-Ch27](../06_data_plane/16_bubble_up_aggregator.md#dp-ch27--deterministic-rng). Wall-clock time, system entropy, or any other non-deterministic source is FORBIDDEN inside generation rules. Replay reproduces same output given same input event log.

**Why:** Replay determinism is a foundation property of the event-sourced system. Without it: time-travel debug replay produces different traces each time → cannot diagnose; canon-promotion replay produces different canonical states → cannot validate; session catch-up replay produces different reconstructed projections → divergence between clients.

DP-Ch27 already enforces this for bubble-up aggregators specifically. EVT-A9 generalizes the rule to ALL probabilistic generation: future combat damage RNG, loot drop RNG, weather drift RNG, NPC routine selection, faction movement probability, etc. Locking it as an axiom prevents each future feature from re-litigating "should our RNG be deterministic?" — yes, always.

**Enforcement:**
- **Lint (Phase 3 EVT-V*)** — generation rule code (registered aggregator/scheduler hooks) must use the SDK-provided `dp::deterministic_rng(channel_id, channel_event_id)`. Direct `rand::thread_rng()` / `std::time::SystemTime::now()` / equivalent calls flagged.
- **Design review** — feature designs that propose new EVT-T5 Generated emitters must declare the RNG seeding strategy + cite EVT-A9.
- **Replay test (Phase 4 EVT-L*)** — replay-test harness re-runs event log; output divergence triggers test failure.

**Consequence:**
- Generation rules cannot use wall-clock for "now" — must use `fiction_ts` from the triggering event.
- Generation rules cannot read external state (HTTP fetch, file read) inside `on_event` — only DP-readable projection state (which is itself deterministic).
- Future authoring features (procedural quest generation, dynamic events) inherit this constraint by category — they're EVT-T5 Generated, so EVT-A9 applies.

**Cross-ref:** [DP-Ch27](../06_data_plane/16_bubble_up_aggregator.md#dp-ch27--deterministic-rng), [`16_bubble_up_aggregator.md`](../06_data_plane/16_bubble_up_aggregator.md) DP-Ch25..Ch30, [`08_scheduled_events.md`](08_scheduled_events.md) (Phase 4), [`10_replay_semantics.md`](10_replay_semantics.md) (Phase 4).

---

## EVT-A10 — Event as universal source of truth (NEW 2026-04-25)

**Rule:** Every observable change to per-reality state has a corresponding **committed event** in the channel event log. Reading the channel event log + replaying through validators is **sufficient** to reconstruct any past state. State projections (cache rows, denormalized lookups, in-memory aggregates) are **derived**; events are authoritative. Features cannot sideline-write state without emitting an event.

This axiom realizes the original intent of Event Model: *"mọi tương tác với thế giới này đều sẽ thông qua event"* — every interaction with the world goes through events.

**Why:**
- **Replay correctness:** if some state changes silently outside the event log, replay produces incorrect projections — silent canon corruption.
- **Audit completeness:** if state can change without an event, audit logs are incomplete — security incident response and forensic debugging fail.
- **Performance optimization trap:** without this axiom, future features may "skip emitting events" to optimize hot paths; over time the event log becomes a partial record of reality. EVT-A10 prevents this from being even tempting — every state-change must emit; performance is solved at projection layer (cache, batching), not by skipping events.
- **Extensibility:** every future feature inherits the guarantee that "if I subscribe to the event log, I see ALL state changes" — no missed-update bugs.

**Enforcement:**
- **DP rulebook** — DP-R3 already prevents raw kernel-client imports; EVT-A10 strengthens this by requiring the SDK call to commit an event (not just write a projection cell).
- **Schema lint** — projections derive from events; the codegen step verifies projection-update functions are called from event-replay handlers, not from arbitrary code paths.
- **Design review** — every feature design that proposes a state-change must cite the EVT-T* event that commits it.

**Consequence:**
- Hot-path optimizations like "directly bump a counter without an event" are forbidden. The counter is a derived projection; events that bump it must commit.
- Cache layer (Redis, in-process) is allowed but is read-only relative to authoritative state — DP cache invalidation flushes cache on event commit per DP-X*.
- T0 ephemeral (DP-T0) tier is the ONE exception — T0 is explicitly memory-only per DP-T1 and not part of canonical state; events on T0 don't commit to event log per DP design. T0 use is rare and design-review-gated.

**Cross-ref:** [DP-A8 durable = 02_storage](../06_data_plane/02_invariants.md#dp-a8--durable-tier-delegates-to-02_storage-unchanged), [DP-R3](../06_data_plane/11_access_pattern_rules.md#dp-r3--no-raw-db-or-cache-client-imports-in-feature-code), reinforces [EVT-A3 validated events for canonical writes](#evt-a3--all-canonical-state-changes-flow-through-validated-events).

---

## EVT-A11 — Sub-type ownership discipline (NEW 2026-04-25)

**Rule:** Each EVT-T* sub-type has exactly **ONE owning feature**, registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md). Sub-types are additive per I14; cross-feature sub-type definition (two features both declaring the same sub-shape) is FORBIDDEN. When a feature wants to extend an existing sub-type (e.g., add an optional field), the extension goes through `_boundaries/02_extension_contracts.md` per the additive-only rule.

**Why:** The boundary failure mode that triggered the `_boundaries/` folder seed (2026-04-25 WA_006 over-extension review) was sub-type ambiguity: WA_006 had `pc_mortality_state` aggregate that overlapped with PCS_001 territory; multiple features all proposed validator slots for EVT-V* without coordination. EVT-A11 prevents this at the axiom level: every sub-type has an owner; the boundary matrix is the single source of truth; design review checks against it.

This makes "feature extends event" (your stated original intent for Event Model) concrete:
- **Add a new sub-type** = additive per I14, register in boundary matrix → no axiom change
- **Extend an existing sub-type** = additive per I14 + extension contract → no axiom change
- **Change someone else's sub-type** = forbidden; either escalate via boundary review (lock-claim, propose transfer) or design your own sub-type

**Enforcement:**
- **Design review** — every feature design that emits an EVT-T* event must list the sub-types it owns + register them in the boundary matrix during the same commit.
- **Boundary matrix CI lint (V2+)** — codegen step extracts sub-type discriminators from feature crates and asserts each is registered with exactly one owner.
- **Lock-gated edits** — boundary matrix is the single-writer mutex per `_boundaries/_LOCK.md`; concurrent feature designs cannot accidentally co-author the same sub-type.

**Consequence:**
- A feature design that proposes an EVT-T* sub-type but doesn't register ownership in `_boundaries/` is rejected at review.
- Cross-feature collaboration on a sub-type (rare but legitimate, e.g., two features both want to extend `TurnEvent.metadata`) goes through the extension contract — additive optional fields with feature attribution.
- Retired sub-types follow I15 stable-ID discipline — `_withdrawn` suffix, never reused.

**Cross-ref:** [`../_boundaries/00_README.md`](../_boundaries/00_README.md), [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md), [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md), foundation I14 (additive-first) + I15 (stable-ID retirement).

---

## EVT-A12 — Extensibility framework (NEW 2026-04-25)

**Rule:** Events extend along **6 well-defined extension points**:

| # | Extension point | Mechanism | Where coordinated |
|---|---|---|---|
| (a) | New sub-type within existing category | Additive per I14 + register in boundary matrix per EVT-A11 | `_boundaries/01_feature_ownership_matrix.md` |
| (b) | New EVT-T* category | Axiom-level decision; superseded `99_open_questions.md` entry → user sign-off → add row to `03_event_taxonomy.md` | This file + locked decisions |
| (c) | New envelope field | Schema bump per Phase 4 EVT-S* (envelope-level version increment); old consumers see optional field, treat as None | [`11_schema_versioning.md`](11_schema_versioning.md) |
| (d) | New validator stage | Coordinated via boundary slot ordering; producer-feature claims lock + edits validator pipeline doc | `_boundaries/03_validator_pipeline_slots.md` |
| (e) | New producer role class | Update EVT-A4 + JWT capability schema; NPC_001 ActorId enum may need new variant | EVT-A4 + DP-K9 |
| (f) | New generation rule (under EVT-T5) | Register aggregator/scheduler per DP-Ch25 / Phase 4 [`08_scheduled_events.md`](08_scheduled_events.md); MUST honor EVT-A9 RNG determinism | `_boundaries/01_feature_ownership_matrix.md` aggregator rows |

Extensions outside these 6 points are FORBIDDEN. If a future feature genuinely needs a 7th extension point, that's an axiom-level discussion.

**Why:** Without an explicit extensibility framework, future features extend ad-hoc — adding fields where convenient, slotting validators where they fit best, producing new event types without taxonomy review. This is exactly the failure mode that triggered the WA_006 over-extension review and the `_boundaries/` folder. EVT-A12 makes the extension contract first-class.

This realizes your stated original intent: *"sau này các feature khác có thể extend/mở rộng event nếu cần"* — features extend through these 6 documented mechanisms, not by inventing new ones.

**Enforcement:**
- **Design review** — every feature design that extends Event Model must cite the extension point (a..f) it uses + the corresponding mechanism doc.
- **Boundary matrix discipline** — extensions across (a), (d), (e), (f) all flow through `_boundaries/` lock-claim.
- **Schema CI (Phase 4 EVT-S*)** — additive-only checks at codegen catch ad-hoc breaking changes.

**Consequence:**
- Future features have a decision tree — *"I want to add an event-related thing; which extension point?"* — instead of an invent-something path.
- Foundation is genuinely a foundation: EVT-A1..A12 + `_boundaries/` covers 100+ future features without axiom additions, except (b) new category which is intentionally rare.
- The 6 extension points are themselves a closed set — adding a 7th extension point requires axiom-level discussion (meta-extensibility lock).

**Cross-ref:** [`../_boundaries/`](../_boundaries/) folder, all extension contracts, foundation I14 + I15.

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-A1 | Closed-set taxonomy | Every event maps to exactly one EVT-T*; no "Other" |
| EVT-A2 | Layers above DP | Event Model uses DP primitives unchanged; never modifies DP |
| EVT-A3 | Validated events for canonical writes | All canonical state changes go through EVT-V* validator pipeline |
| EVT-A4 | Producer-ROLE binding (reframed) | Each EVT-T* has authorized producer roles; service-name binding lives in `_boundaries/` |
| EVT-A5 | Fixed validator order | EVT-V* pipeline order locked; no skip / no reorder; subsets per category |
| EVT-A6 | Typed single-reality causal-refs | `CausalRef { channel_id, channel_event_id }`; same-reality only; gap-free |
| EVT-A7 | Untrusted-origin pre-validation (reframed) | Untrusted producers (LLM + future) emit EVT-T6 Proposal only; trusted commit-service validates → commits |
| EVT-A8 | Non-canonical regenerable not events (reframed) | Flavor/regenerable content lives in audit log via pointer; only structural deltas commit canonical |
| EVT-A9 | Probabilistic generation determinism (NEW) | EVT-T5 Generated uses deterministic RNG seeded from causal-ref; replay-correct by axiom |
| EVT-A10 | Event as universal source of truth (NEW) | Every observable state change has a committed event; projections are derived; no sideline-writes |
| EVT-A11 | Sub-type ownership discipline (NEW) | Each EVT-T* sub-type has exactly one owning feature in `_boundaries/01_feature_ownership_matrix.md` |
| EVT-A12 | Extensibility framework (NEW) | Events extend along 6 well-defined points (a..f); extensions outside these are forbidden |

Any change to an axiom is logged in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) with a new locked-decision entry; the superseded axiom gets a `_withdrawn` suffix rather than being deleted.

---

## How invariants get added

New EVT-A* invariants follow the same process as foundation I*:

1. A concrete enforcement point (validator-pipeline check, capability JWT claim, design-review checklist row, lint script).
2. A subfolder owner (this folder; all EVT-A* live here).
3. Architect sign-off via Phase POST-REVIEW.
4. Same-commit update to the enforcing mechanism (validator pipeline spec, capability claims doc, design-review template).

Invariants without concrete enforcement are wishes. Wishes are not invariants.
