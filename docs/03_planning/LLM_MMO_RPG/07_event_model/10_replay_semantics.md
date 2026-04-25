# 10 — Replay Semantics Framework

> **Status:** LOCKED Phase 4b (Option C discipline 2026-04-25). Per [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) + [EVT-A10 event as universal SSOT](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), replay is a foundation property: replaying the event log + validators reconstructs any past state. This file specifies the **replay framework** for three distinct use cases (session catch-up, canon-promotion, time-travel debug) at mechanism level.
> **Stable IDs:** EVT-L16..EVT-L19. Continuation of EVT-L* lifecycle namespace.
> **Resolves:** [EVT-Q6](99_open_questions.md) (replay filter for flavor narration) + [EVT-Q10](99_open_questions.md) (time-travel debug replay determinism guarantee).

---

## How to use this file

Three replay use cases have distinct contracts:

1. **Session catch-up replay** (UI client reconnects after disconnect): EVT-L16. Transport via DP-K6; Event Model adds category visibility filter.
2. **Canon-promotion replay** (V2+ DF3 — emergent events promoted to L2 canon): EVT-L17. Chain validation re-runs validator pipeline against multiverse rules.
3. **Time-travel debug replay** (operator forensic): EVT-L18. Deterministic reconstruction of past state from event log.

Plus the **flavor handling** rule (EVT-L19) shared across all three.

When implementing a replay-aware feature, identify which use case applies, then honor the corresponding contract.

---

## EVT-L16 — Session catch-up replay

**Rule:** When a UI client reconnects after disconnect, it resumes the durable channel-event subscription per [DP-K6](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives) which gives gap-free per-channel ordering. Event Model adds a **category visibility filter** atop DP-K6 transport: the UI receives only **user-visible categories**; internal-only categories are filtered out (delivered to internal services as needed but not surfaced to UI).

**User-visible vs internal-filtered:**

| Category | UI delivery | Rationale |
|---|---|---|
| EVT-T1 Submitted | ✅ visible | PC/NPC actions are the player narrative |
| EVT-T3 Derived | depends on `aggregate_type` | scene_state / participant_presence / fiction_clock visible (UI uses for rendering); npc_pc_relationship_projection / npc_node_binding internal-filtered (telemetry-only) |
| EVT-T4 System (MemberJoined/Left, ChannelPaused/Resumed) | ✅ visible | presence + lifecycle changes shown to player |
| EVT-T4 System (TurnSlotClaimed/Released, TurnBoundary wire) | filtered | internal coordination — UI gets the payload via Submitted instead |
| EVT-T5 Generated (BubbleUp:RumorBubble) | ✅ visible | gossip/rumors shown as ambient UI |
| EVT-T5 Generated (Scheduled:NPCRoutine V1+30d) | depends on `pc_observed` flag | if PC was in cell at fire time, visible; if not, internal-only (per EVT-A8 flavor) |
| EVT-T6 Proposal | filtered | bus-only; never reaches UI directly |
| EVT-T8 Administrative | depends on sub-shape | Pause/Resume visible; ForgeEdit/Charter*/Succession* internal/admin-UI-only |

**Authoritative current visibility map** is feature-design-owned (each feature declares visibility for its sub-types in feature design + boundary matrix). This file specifies the **mechanism** (filter exists, filter is per-(category, sub-type)); specific visibility decisions live with feature owners.

**Resume mechanism:**
- UI persists `last_seen_channel_event_id` per channel in localStorage (per CLAUDE.md "preferences synced server-side").
- On reconnect, UI calls `dp::subscribe_channel_events_durable<E>` with `from=last_seen_channel_event_id`.
- DP-K6 streams gap-free events from that point forward.
- Event Model filter applies per the visibility map; UI receives only visible events.

**Failure mode:** if filter logic itself errors, fail-closed (deliver nothing, surface error to UI as "stream interrupted, retry") — never deliver incorrect events.

**Cross-ref:** [DP-K6 durable subscribe](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives), [PL_001 §7 subscribe pattern](../features/04_play_loop/PL_001_continuum.md), CLAUDE.md "no localStorage for user data" (visibility decisions are per-server, not per-device).

---

## EVT-L17 — Canon-promotion replay (V2+, deferred)

**Rule:** When emergent events from a reality are promoted to L2 SEEDED canon (per DF3 V2+ canonization flow per [`../03_multiverse/01_four_layer_canon.md`](../03_multiverse/01_four_layer_canon.md)), the promotion replays the original event chain through validator-pipeline re-run against multiverse-level canon rules. Validation result determines if promotion proceeds.

**Replay mechanism (V2+ design sketch):**
1. Author selects a chain of events from a reality's log (typically a quest line, a scene, a narrative arc).
2. Promotion service walks the causal-ref graph (per [EVT-L15](09_causal_references.md#evt-l15--graph-walk-patterns)) backward from the chain endpoints to find all dependencies.
3. Promotion service re-runs the chain through a **multiverse-level validator** that checks: (a) chain doesn't violate L1 axioms in any reality forked from this book; (b) chain coherence with already-promoted L2 facts; (c) author consent + dual-actor approval per S5 Tier 1 destructive policy.
4. On Validated: write to book SSOT + glossary canonical entries; cascade to forked realities via `meta-worker` xreality.* topics.
5. On Rejected: surface to author; no promotion; original reality unchanged.

**Causal-ref dependency:** chain promotion REQUIRES each event to have valid causal_refs per [EVT-L13 integrity rules](09_causal_references.md#evt-l13--single-reality-constraint--integrity-validation). Events with dangling refs cannot be promoted (the promotion would be incomplete by construction).

**Determinism note:** canon-promotion replay is NOT bit-deterministic across realities — it's a fresh validation pass, not a state-reconstruction. The replay's purpose is gating (does this chain make canonical sense?), not reconstruction.

**V1 status:** **placeholder.** Canon promotion (DF3) is V2+. This framework reserves the mechanism; concrete protocol locks when DF3 lands.

**Cross-ref:** [`../03_multiverse/01_four_layer_canon.md`](../03_multiverse/01_four_layer_canon.md) §3 four-layer model, DF3 V2+ canonization, [EVT-L15 graph-walk](09_causal_references.md#evt-l15--graph-walk-patterns), R5 cross-instance policy + meta-worker.

---

## EVT-L18 — Time-travel debug replay (resolves EVT-Q10)

**Rule:** Operators may query past state ("what happened in cell X between turn N and M") via a **deterministic time-travel replay** that reconstructs canonical state from the event log. Determinism is guaranteed per [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25): same input event log + same fiction-clock state + same RNG seed → same output state.

**Two operator modes:**

**Mode 1 — Structural-only replay:**
- Reconstructs aggregates by replaying EVT-T3 Derived events + EVT-T1 Submitted commits (canonical structural deltas only).
- Produces deterministic projection state at any past point: actor locations, scene state, fiction-clock value, NPC-PC relationships.
- **Bit-deterministic** (same inputs → same bytes).
- Use case: forensic investigation, audit, "what was Lý Minh's money at turn 17?"

**Mode 2 — With-narration-best-effort replay:**
- Mode 1 + retrieve original flavor text from audit-log via `flavor_text_audit_id` pointers per [EVT-A8](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25).
- Flavor text is read from audit-log when available; if missing (audit retention expired) or original LLM-non-deterministic, replay shows `[flavor unavailable]` or operator can opt-in to LLM regeneration.
- **NOT bit-deterministic** — flavor text may differ from original.
- Use case: rich debug context, "show me the scene as it appeared", incident root-cause review.

**Determinism guarantee scope:**
- Structural deltas: bit-deterministic.
- Flavor text: best-effort; NOT a determinism guarantee.
- Validator behavior: bit-deterministic against same event payloads.
- Generator output (EVT-T5): bit-deterministic per EVT-A9 RNG seeded from causal-ref event_id.

**Implementation pattern:** time-travel replay is a **cold-path** operation — typically operator-initiated via admin-cli command. Specific implementation (read entire event log range + apply in-memory; or use existing projection-rebuild mechanism per [DP-R02](../02_storage/R02_projection_rebuild.md)) is operational design.

**Bound on replay window:** operator MUST specify `--from-event-id` + `--to-event-id` bounds; unbounded replay forbidden (would scan entire reality history). Default operator UX: "replay events in cell X between fiction-time A and B" → resolves to event-id range.

**Cross-ref:** [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [EVT-A8 flavor exclusion](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25), [DP-R02 projection rebuild](../02_storage/R02_projection_rebuild.md), [EVT-L15 graph-walk](09_causal_references.md#evt-l15--graph-walk-patterns), S5 admin-cli for operator commands.

---

## EVT-L19 — Flavor handling across all replay modes (resolves EVT-Q6)

**Rule:** Per [EVT-A8](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25), flavor content is non-canonical and lives in audit-log via `flavor_text_audit_id` pointers, NOT in the event log. Replay handling:

**Session catch-up replay (EVT-L16):**
- Default: regenerate flavor on demand. UI receives the canonical event (with `flavor_text_audit_id` pointer); UI calls a "fetch flavor" endpoint that either returns audit-log flavor (if recent) or triggers LLM re-prompt to regenerate.
- V1 simplification: audit-log replay (cheaper). UI fetches audit-log flavor by id; if missing, shows `[narration unavailable]`.
- V1+30d evolution: re-prompt fallback as feature flag (operator-tunable cost vs UX quality).

**Canon-promotion replay (EVT-L17):**
- Flavor is irrelevant to promotion (only structural canon promotes).
- Promotion validator ignores `flavor_text_audit_id` pointers.

**Time-travel debug replay (EVT-L18):**
- Mode 1 (structural-only): ignores flavor entirely.
- Mode 2 (with-narration): retrieves flavor from audit-log; missing flavor shows `[flavor unavailable, audit retention expired]` (do not fall back to LLM regeneration in audit/forensic context — would mislead investigation with fresh-LLM output).

**Cost implications:**
- V1 audit-log replay: bounded by audit-log retention (30 days `events_sensitive` per S8-D3, 90 days projection cache for `events_normal`).
- V1+30d re-prompt: requires LLM call per re-render → cost per session reconnect. Operational decision: enable per-tier (premium tier opt-in).

**Why NOT include flavor in event log:** repeats the EVT-A8 reasoning — replay would have to reproduce identical LLM text (impossible with non-determinism); validators would canon-check generated narration content (cost-prohibitive); event log would balloon. All three replay modes operate cleanly without flavor in the log.

**Cross-ref:** [EVT-A8](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25), [EVT-Q6 replay filter for flavor](99_open_questions.md), S8-D3 retention tiers (audit-log retention bounds), [SPIKE_01 obs#16 flavor narration insight](../features/_spikes/SPIKE_01_two_sessions_reality_time.md).

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-L16 | Session catch-up replay | DP-K6 transport + Event Model category visibility filter; user-visible vs internal-filtered per (category, sub-type) |
| EVT-L17 | Canon-promotion replay (V2+) | Walks causal-ref graph + re-validates against multiverse canon rules; placeholder for DF3 |
| EVT-L18 | Time-travel debug replay (EVT-Q10 resolved) | Two modes: structural-only bit-deterministic; with-narration-best-effort (not bit-deterministic); bounded operator queries |
| EVT-L19 | Flavor handling (EVT-Q6 resolved) | V1 audit-log replay; V1+30d re-prompt as feature flag; canon-promotion ignores flavor; time-travel debug Mode 2 retrieves audit-log only (no LLM fallback) |

---

## Cross-references

- [EVT-A8 non-canonical regenerable content](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25) — flavor exclusion
- [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — replay-correctness invariant
- [EVT-A10 event as universal SSOT](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25) — replay sufficient to reconstruct
- [`09_causal_references.md` EVT-L15](09_causal_references.md#evt-l15--graph-walk-patterns) — graph-walk used by time-travel replay + canon-promotion
- [`11_schema_versioning.md`](11_schema_versioning.md) — schema migration + replay against migrated schemas
- [DP-K6 durable subscribe](../06_data_plane/04c_subscribe_and_macros.md#dp-k6--subscription-primitives) — transport for session catch-up
- [DP-R02 projection rebuild](../02_storage/R02_projection_rebuild.md) — implementation pattern for time-travel
- [`../03_multiverse/01_four_layer_canon.md`](../03_multiverse/01_four_layer_canon.md) — canon-promotion ground (DF3 V2+)
- S5 ADMIN_ACTION_POLICY — admin-cli for operator-initiated time-travel
- S8-D3 retention tiers — audit-log retention bounds
