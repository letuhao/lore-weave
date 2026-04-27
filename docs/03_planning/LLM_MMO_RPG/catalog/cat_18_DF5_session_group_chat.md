<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_18_DF5_session_group_chat.md
namespace: DF5-*
generated_by: hand-authored (DF cluster catalog seed; multi-session-per-cell sparse architecture)
-->

## DF5 — Session / Group Chat (V1-blocking biggest unknown — RESOLVED 2026-04-27)

> Big Deferred Feature DF05 — multi-session-per-cell sparse architecture for in-game group conversations. Sessions are explicit social acts; per-actor POV memory distill on close. Owns `DF5-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `DF5-A*` | Axioms (locked invariants) |
> | `DF5-D*` | Per-feature deferrals (V1+30d / V2 / V3 phases) |
> | `DF5-Q*` | Open questions (post-DRAFT) |
> | `DF5-V*` | Validator slots |
> | `DF5-C*` | Cross-aggregate consistency rules |

### Core architectural axioms

**DF5-A1 (Same-channel):** All session participants ∈ exactly same channel_id at any moment. Per TDIL-A5 atomic-per-turn travel.

**DF5-A2 (Container, not single event):** Session = aggregate; turn-events fire WITHIN session at PL_005 grain. Replay-determinism + scalability.

**DF5-A3 (Time-flow inheritance):** Session inherits channel time_flow_rate; per-turn fiction_clock advance follows TDIL-A6 per-realm turn streams.

**DF5-A4 (PC anchor invariant):** Active session MUST have ≥1 PC. Last PC leaves → auto-close cascade. Avoids NPC-only ghost sessions; AIT scaling discipline.

**DF5-A5 (One Active per actor):** Any actor (PC or NPC) ∈ ≤1 Active session at a time. UI sanity + LLM context lifecycle clarity.

**DF5-A6 (Tier eligibility):** Session participants ∈ {PC, Major NPC, Minor NPC}. Untracked NPC = NOT eligible per AIT-A8 capability matrix.

**DF5-A7 (Closed = immutable):** After Closed transition, no session_participation writes; session aggregate frozen except archival queries. Memory ownership integrity.

**DF5-A8 (Per-cell soft cap):** ≤50 Active sessions per cell V1. Prevents runaway; matches AIT density discipline.

**DF5-A9 (Memory distill on close):** Each participant gets POV-summary written to actor_session_memory; cached in EVT-T3 commit data per Q12-D1 LOCKED. Lossless from participant POV; no reopen for "objective truth".

**DF5-A10 (No cross-session leak):** Session A's content NOT readable by session B participants. Privacy + real-world parallel; LLM context isolation.

**DF5-A11 (Replay deterministic):** Session state derivable from EVT-T1 + EVT-T3 stream filtered by session_id; POV-distill cached per Q12-D3 LOCKED. Per EVT-A9.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| DF5-1 | `session` aggregate (T2/Reality, sparse — Active hot; Closed archival) | ✅ | V1 | EF-1 (ActorId), DP-A14, PF-1 (cell channel) | [DF5_001 §3.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#31-session-t2--reality-sparse--active-hot-closed-archival--primary) |
| DF5-2 | `session_participation` aggregate (T2/Reality, sparse per-(session, actor)) | ✅ | V1 | DF5-1, ACT-1 | [DF5_001 §3.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#32-session_participation-t2--reality-sparse-per-session-actor--per-participant) |
| DF5-3 | Reuse `actor_session_memory` (ACT_001 §3.4) — primary post-close memory | ✅ | V1 | ACT-4 | [DF5_001 §3.3](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#33-reuse-actor_session_memory-act_001-34) |
| DF5-4 | `SessionState` 2-variant V1 enum (Active/Closed) | ✅ | V1 | DF5-1 | [DF5_001 §3.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#31-session-t2--reality-sparse--active-hot-closed-archival--primary) |
| DF5-5 | `ParticipantRole` 2-variant V1 enum (Anchor/Joined) | ✅ | V1 | DF5-2 | [DF5_001 §3.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#32-session_participation-t2--reality-sparse-per-session-actor--per-participant) |
| DF5-6 | `PresenceState` 3-variant V1 enum (Connected/Disconnected/Left) | ✅ | V1 | DF5-2 | [DF5_001 §3.2 + §13](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#13--disconnect-grace--presence-q10-locked) |
| DF5-7 | `LeftReason` 6-variant V1 enum (Explicit/MovedCell/Inactive/SessionClosed/AnchorPcLeft/Kicked) | ✅ | V1 | DF5-2 | [DF5_001 §3.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#32-session_participation-t2--reality-sparse-per-session-actor--per-participant) |
| DF5-8 | `CloseReason` 5-variant V1 enum (LastPcLeft/AllParticipantsLeft/ForgeClose/RealityClosed/SessionTimeoutWallClock) | ✅ | V1 | DF5-1 | [DF5_001 §3.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#31-session-t2--reality-sparse--active-hot-closed-archival--primary) |
| DF5-9 | EVT-T4 System sub-type — `SessionBorn { session_id, channel_id, anchor_pc_id }` (canonical seed V1+) | ✅ | V1 | EVT-A11, DF5-1 | [DF5_001 §2.5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#25--event-model-mapping-per-07_event_model) |
| DF5-10 | EVT-T3 Derived sub-type — `aggregate_type=session` Born/Update/ClosingTransition/ClosedTransition | ✅ | V1 | EVT-A11, DF5-1 | [DF5_001 §2.5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#25--event-model-mapping-per-07_event_model) |
| DF5-11 | EVT-T3 Derived sub-type — `aggregate_type=session_participation` Born/Update (LeftTransition) | ✅ | V1 | EVT-A11, DF5-2 | [DF5_001 §2.5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#25--event-model-mapping-per-07_event_model) |
| DF5-12 | EVT-T6 Proposal + EVT-T3 Derived — `actor_session_memory` SessionPovDistill (cached payload) | ✅ | V1 | EVT-A11, ACT-4, Q12 LOCKED | [DF5_001 §11](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#11--replay-determinism-via-pov-distill-cache-q12-locked) |
| DF5-13 | EVT-T8 AdminAction `Forge:CreateSession` | ✅ | V1 | WA-3, DF5-1 | [DF5_001 §14.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-14 | EVT-T8 AdminAction `Forge:CloseSession` | ✅ | V1 | WA-3, DF5-1 | [DF5_001 §14.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-15 | EVT-T8 AdminAction `Forge:KickFromSession { actor_id, force }` | ✅ | V1 | WA-3, DF5-2 | [DF5_001 §14.1 + §13.3](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-16 | EVT-T8 AdminAction `Forge:EditActorSessionMemory` (pre-close edits) | ✅ | V1 | WA-3, ACT-4 | [DF5_001 §14.1 Q11-D1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-17 | EVT-T8 AdminAction `Forge:RegenSessionDistill` (post-close regen) | ✅ | V1 | WA-3, DF5-12 | [DF5_001 §14.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-18 | EVT-T8 AdminAction `Forge:PurgeActorSessionMemory` (GDPR per-actor erasure) | ✅ | V1 | WA-3, ACT-4 | [DF5_001 §14.1 + §15.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#152-gdpr-per-actor-erasure-q6-d4-locked) |
| DF5-19 | EVT-T8 AdminAction `Forge:AnonymizePcInSessions` (GDPR cascade other actors) | ✅ | V1 | WA-3, DF5-18 | [DF5_001 §15.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#152-gdpr-per-actor-erasure-q6-d4-locked) |
| DF5-20 | EVT-T8 AdminAction `Forge:BulkRegenSessionDistill` (bulk reality-scoped) | ✅ | V1 | WA-3, DF5-17 | [DF5_001 §14.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-21 | EVT-T8 AdminAction `Forge:BulkPurgeStaleSessions` (admin cleanup reality-scoped) | ✅ | V1 | WA-3, DF5-18 | [DF5_001 §14.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#141-v1-forge-adminaction-sub-shapes-9-total) |
| DF5-22 | SDK SessionService trait (7 lifecycle ops) — `contracts/api/session/v1/session_service.rs` | ✅ | V1 | DF5-1, DF5-2 | [DF5_001 §16.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#162-sessionservice-trait-7-lifecycle-ops) |
| DF5-23 | SDK MemoryProvider trait (4 read ops + capabilities probe) — `contracts/api/session/v1/memory_provider.rs` | ✅ | V1 | DF5-3, ACT-4 | [DF5_001 §16.3](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#163-memoryprovider-trait-4-read-ops--capabilities-probe) |
| DF5-24 | SDK PersonaContextBlock DTO V1 (versioned; tolerant readers) — `contracts/api/session/v1/dto.rs` | ✅ | V1 | DF5-23 | [DF5_001 §16.4](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#164-versioned-dto-forward-compatible) |
| DF5-25 | SDK MemoryFactView DTO V1 (with MemoryFactKind closed enum 5 variants) | ✅ | V1 | DF5-24 | [DF5_001 §16.4 + §6.2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#62-pov-distill-prompt-template-q5-d1d6-locked) |
| DF5-26 | SDK MemoryQuery DSL V1 (4 query variants) — `contracts/api/session/v1/query.rs` | ✅ | V1 | DF5-23 | [DF5_001 §16.5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#165-memoryquery-dsl) |
| DF5-27 | SDK MemoryProviderCapabilities probe struct — fine-grained boolean + Duration | ✅ | V1 | DF5-23 | [DF5_001 §16.3](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#163-memoryprovider-trait-4-read-ops--capabilities-probe) |
| DF5-28 | LruDistillProvider V1 backend implementation (Option A close-distill) — `services/session-service/src/adapters/lru_distill.rs` | ✅ | V1 | DF5-22, DF5-23, ACT-4 | [DF5_001 §16.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#161-three-layer-architecture) |
| DF5-29 | ContractTestSuite (~30 scenarios) — mandatory CI gate every backend MUST pass | ✅ | V1 | DF5-22..28 | [DF5_001 §16.6 Pattern 5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#166-migration-patterns-5-patterns) |
| DF5-30 | RealityManifest extension `canonical_sessions: Vec<CanonicalSessionDecl>` (OPTIONAL V1) | ✅ | V1 | DF5-1 | [DF5_001 §17](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#17--realitymanifest-extensions) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| DF5-31 | `session.*` RejectReason namespace (13 V1 rule_ids + 5 V1+ reservations) | ✅ | V1 | DF5-1..30 | [DF5_001 §21](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#21--rejectreason-rule_id-catalog-session-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| DF5-32 | 11 invariants DF5-A1..A11 (collectively documented; consumed by §6 + validator slots) | ✅ | V1 | DF5-1..30 | [DF5_001 §6 + cat_18 axioms](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md) |
| DF5-33 | DF5-V1..V4 validator slots (ParticipantCap + OneActiveSession + SameChannel + TierEligibility) | ✅ | V1 | DF5-1, DF5-2, ACT-1, AIT-1 | [DF5_001 §18](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#18--validator-chain-df5-v1v4) |
| DF5-34 | V1+30d — Idle state auto-detect (DF5-D4) | 📦 | V1+ | DF5-4 | [DF5_001 §1 DF5-D4](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-35 | V1+30d — Wall-clock 24h timeout sweep (DF5-D5) | 📦 | V1+ | DF5-4 | [DF5_001 §1 DF5-D5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-36 | V1+30d — Per-tier customized POV-distill prompt (DF5-D6) | 📦 | V1+ | DF5-12 | [DF5_001 §1 DF5-D6](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-37 | V1+30d — Async background distill (DF5-D13) | 📦 | V1+ | DF5-12 | [DF5_001 §6.5](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#65-async-background-distill-v130d-df5-d13) |
| DF5-38 | V2 — Multi-PC join existing session (DF5-D1) | 📦 | V2 | DF5-2, SR11 | [DF5_001 §1 DF5-D1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-39 | V2 — Whisper 1-to-1 within session (DF5-D2) | 📦 | V2 | DF5-38 | [DF5_001 §1 DF5-D2](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-40 | V2 — PvP within session (DF5-D3) | 📦 | V2 | DF5-38, DF4 | [DF5_001 §1 DF5-D3](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-41 | V2 — NPC initiates session desire-driven (DF5-D7) | 📦 | V2 | NPC-12 (NPC_003) | [DF5_001 §1 DF5-D7](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-42 | V2 — Frozen state Forge/DF4 explicit pause (DF5-D8) | 📦 | V2 | DF5-1, DF4 | [DF5_001 §1 DF5-D8](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-43 | V2+ — SalienceTranscriptProvider backend (Option C; opt-in raw blob for high-salience sessions) | 📦 | V2+ | DF5-22, DF5-23 | [DF5_001 §16.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#161-three-layer-architecture) |
| DF5-44 | V2+ — KnowledgeServiceBridge backend (Option B; cross-reality user-level insight) | 📦 | V2+ | knowledge-service | [DF5_001 §16.1](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#161-three-layer-architecture) |
| DF5-45 | V3 — NPC-NPC autonomous continuation (DF5-D9) | 📦 | V3 | NPC-8, DF1 | [DF5_001 §1 DF5-D9](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-46 | V3 — Closed session resume (DF5-D10) | 📦 | V3 | DF5-1 | [DF5_001 §1 DF5-D10](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-47 | V3 — Cross-cell session cluster (DF5-D11) | 📦 | V3 | TDIL-A5 | [DF5_001 §1 DF5-D11](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |
| DF5-48 | V3+ — Public broadcast PC shouts to cell (DF5-D12) | 📦 | V3+ | DF5-1 | [DF5_001 §1 DF5-D12](../features/DF/DF05_session_group_chat/DF05_001_session_foundation.md#v1-not-shipping-deferred) |

### V1 minimum delivery

33 V1 catalog entries (DF5-1..DF5-33) all ✅. SDK contract + LruDistillProvider V1 backend + ContractTestSuite ~30 scenarios + 13 V1 reject rule_ids + 9 Forge AdminAction sub-shapes + 4 validator slots + 11 invariants + RealityManifest OPTIONAL canonical_sessions extension.

### V1+30d deferrals (DF5-34..DF5-37)

4 V1+30d items planned for 30-day fast-follow window after V1 ship: Idle state + 24h timeout + per-tier distill prompt + async background distill. Most schema reservations already in place — minimal migration cost.

### V2+ deferrals (DF5-38..DF5-48)

11 V2/V3+ deferrals tied to:
- DF4 World Rules dependency (PvP consent, Frozen state)
- SR11 multi-PC turn arbitration (multi-PC join, whisper)
- NPC_003 Desires V1+ (NPC initiates)
- DF1 Daily Life (NPC-NPC autonomous)
- knowledge-service integration (KnowledgeServiceBridge backend)

### Coordination / discipline notes

- **V1-blocking biggest unknown RESOLVED 2026-04-27:** original DF05 placeholder marked V1-blocking biggest unknown 2026-04-25. After 4-batch Q-deep-dive 2026-04-27 (zero revisions) + §16 SDK Architecture LOCKED, all architectural questions converged.
- **Architectural pivot (LOCKED):** initial single-session-per-cell rejected per user direction billion-NPC AIT scaling concern + real-life conversation parallel. Multi-session-per-cell sparse model adopted; sessions are explicit social acts not spatial co-location.
- **Per-actor POV memory (LOCKED):** subjective per-participant records on close; LLM × N participants distill cascade; cached in EVT-T3 payload for replay-determinism.
- **SDK boundary discipline:** consumers (NPC_001/002 + PCS_001 + WA_003) depend on `contracts/api/session/v1/` traits ONLY. CI lint blocks `services/session-service/src/adapters/` imports outside service. Contract test suite mandatory CI gate; every backend MUST pass.
- **Cross-cultivation extensibility:** session_participation tier_filter respects AIT_001 NpcTrackingTier; future LegendaryTier (AIT-D3) adds 4th tier without breaking DF5 V1 schema.
- **16 cross-feature closure-pass-extensions** queued: PL_002 + PL_005 + NPC_001..003 + ACT_001 + REP_001 + WA_003 + WA_006 + AIT_001 + PCS_001 + PL_001 + PF_001 + EM-7 + 07_event_model + RealityManifest + (NEW) `contracts/api/session/v1/` + `services/session-service/`.
- **RESOLVES:** PC-D1 (multi-PC parties redirected to V2 multi-PC join via DF5-38) + PC-D2 (PvP V2 deferred per V1 scope cut via DF5-40) + PC-D3 (no global chat per multi-session-per-cell sparse model) + B4 PARTIAL (multi-NPC turn arbitration via NPC_002 Chorus integration).
- **DF5-A4 anchor invariant** is the MAIN gameplay-loop discipline: PC presence drives session lifetime; NPCs cannot sustain session V1 (V2+ DF1 daily-life ambient may relax via DF5-D9).
- **Token cost discipline:** per-tier soft-cap with priority dropping (Free 2K / Paid 3K / Premium 5K); never drop persona/world rules/system prompt; recent turns + low-salience memories drop first.

### Cross-aggregate consistency rules (DF5-C1..C4)

| C-rule | Description | Enforcement |
|---|---|---|
| **DF5-C1** | `session.anchor_pc_id` MUST be PC kind | Cross-validator with ACT_001 actor_core (verify ActorKind::Pc) |
| **DF5-C2** | `session.channel_id` MUST be cell-tier | Cross-validator with PF_001 (cell-only invariant) |
| **DF5-C3** | Active session count per cell MUST be ≤50 (DF5-A8) | Stage 0 write-time count check |
| **DF5-C4** | Active session count per actor MUST be ≤1 (DF5-A5) | Stage 0 write-time count check |

Mapped to global cross-aggregate consistency rules in `_boundaries/03_validator_pipeline_slots.md` (next available C-rule numbers post TIT_001's C18..C25).
