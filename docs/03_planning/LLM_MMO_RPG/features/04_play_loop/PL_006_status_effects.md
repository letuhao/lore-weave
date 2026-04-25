# PL_006 — Status Effects (Status Foundation)

> **Conversational name:** "Status" (STA). Closed-set foundation for actor status effects (Drunk / Exhausted / Wounded / Frightened V1 + reserved V1+ kinds) — owns `StatusFlag` enum + `actor_status` aggregate + apply/tick/expire/dispel lifecycle. Cross-actor uniformity: same enum + lifecycle covers PCs (referenced by PCS_001) AND NPCs (referenced by future NPC_003). Foundation discipline mirrors NPC_001's ActorId enum pattern — own the closed-set once, consume from many features.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** DRAFT 2026-04-26
> **Catalog refs:** Inferred from V1 vertical-slice gaps (Use:wine outcome / Strike Stun intent / Exhausted post-/sleep). No catalog row pre-existed; PL category extension.
> **Builds on:** [PL_001 Continuum](PL_001_continuum.md) (turn-slot + fiction-clock substrate for tick/expire), [PL_005 Interaction](PL_005_interaction.md) + [PL_005b contracts](PL_005b_interaction_contracts.md) (Interaction OutputDecl applies statuses), [PL_005c integration](PL_005c_interaction_integration.md) §4 (opinion drift parallel pattern), [WA_001 Lex](../02_world_authoring/WA_001_lex.md) (axiom enforcement at validator stage).
> **Defers to:** [PCS_001 brief](../06_pc_systems/00_AGENT_BRIEF.md) (`pc_stats_v1_stub.status_flags: Vec<StatusFlag>` references PL_006 enum); future [`NPC_003 mortality`](../05_npc_systems/) (will reference same enum for NPC statuses); V1+30d scheduler (auto-expire via Scheduled:StatusExpire generator).
> **Event-model alignment:** Status apply/dispel = EVT-T3 Derived (sub-discriminator `aggregate_type=actor_status`). Status auto-expire (V1+30d) = EVT-T5 Generated::Scheduled. No new EVT-T* category.

---

## §1 User story (concrete — V1 status scenarios)

**SPIKE_01-grounded scenarios extended:**

1. **Drunk after Use:wine** — PC `/use rượu` (Interaction:Use, UseIntent=Consume, target=self). PL_005 actual_outputs include `OutputDecl { target: Actor(LM01), aggregate: actor_status, delta: ApplyStatus(Drunk, magnitude=2, source=interaction_id) }`. PL_006 owner-service consumes Derived → updates `actor_status` aggregate. Subsequent Speak by LM01 carries Drunk in scene context (V1+ slurred speech narration cue).

2. **Exhausted after `/sleep` skipped** — PC plays for 16+ fiction-hours without `/sleep`. Background world-rule (V1+30d scheduler) detects threshold cross → emits Status apply. Or V1: world-service's PL_001 §13 fast-forward chain checks fiction-time-since-last-sleep; if exceeds 16h, applies Exhausted.

3. **Wounded after Strike (V1+)** — PC takes Strike with HP delta but survives. Strike's actual_outputs include both HpDelta AND ApplyStatus(Wounded, magnitude=1). Wounded affects subsequent NPC reactions (Chorus may show concerned reactions per opinion drift).

4. **Frightened after observing Strike (V1+)** — Tiểu Thúy sees Lý Minh strike Lão Ngũ. Chorus orchestrator's NPCTurn for Tiểu Thúy includes ApplyStatus(Frightened, magnitude=3, source=observed_strike) on her actor_status. Future NPC_003 reads Frightened from her status to gate available reactions (flee / cower / scream).

**PL_006 specifies:** the V1 closed-set `StatusFlag` enum; the `actor_status` aggregate (one per (reality, actor) — covers PCs + NPCs uniformly per D6); the apply/tick/expire/dispel lifecycle; the integration with PL_005 Interaction OutputDecl (statuses apply via existing OutputDecl mechanism, no new path); the V1+30d scheduler for auto-expire; the rejection rules + Vietnamese reject copy in `status.*` namespace; the Lex axiom integration (V1+ — some realities forbid certain statuses).

After this lock: Use:wine outcome locked; Strike intents Stun/Restrain unblocked (V1+); PCS_001 + future NPC_003 reference shared StatusFlag enum without drift.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **StatusFlag** | Closed enum V1: `{ Drunk, Exhausted, Wounded, Frightened }` | V1 = 4 kinds (per D3 sub-decision). V1+ extensions ADDITIVE per I14: `Stunned`, `Bleeding`, `Poisoned`, `Charmed`, `Encumbered`, `Buffed`, `Tired`, `Hungry`, `Restrained`. New kinds register in `_boundaries/01_feature_ownership_matrix.md` per EVT-A11. |
| **StatusInstance** | Per-(actor, flag) record: `{ flag: StatusFlag, magnitude: u8, applied_at_turn: u64, applied_at_fiction_ts: i64, expires_at_fiction_ts: Option<i64>, source_event_id: u64 }` | Magnitude scales effect intensity (Drunk magnitude=1 mild buzz; magnitude=5 stumbling drunk). `expires_at_fiction_ts: None` = no auto-expire (manual dispel only V1; auto-expire V1+30d scheduler). |
| **actor_status** | T2 / Reality aggregate; per-(reality, actor_id) row holds `Vec<StatusInstance>` | Generic for PC + NPC (D6 — cross-actor uniformity). Covers both ActorId::Pc and ActorId::Npc; Synthetic actors don't accumulate status (V1). |
| **StatusLifecycle** | `Apply` (add or merge instance) → `Tick` (V1+ fiction-time-driven effect; V1 no tick) → `Expire` (auto-remove at fiction-time threshold V1+30d, or manual Dispel) → `Dispel` (V1: explicit OutputDecl removes instance) | V1 minimum: Apply + Dispel via OutputDecl. Tick + Expire deferred to V1+30d scheduler. |
| **ApplyStatusDelta** | `OutputDecl` delta_kind for `aggregate_type=actor_status` | `ApplyStatus { flag, magnitude, expires_at_fiction_ts: Option<i64>, source_event_id }` |
| **DispelStatusDelta** | OutputDecl delta_kind | `DispelStatus { flag }` (single instance per flag V1; V1+ may target specific source_event_id) |
| **StatusStackPolicy** | `enum { ReplaceIfHigher, Sum, Coexist }` per flag | V1: Drunk = `Sum` (multiple drinks accumulate magnitude); Exhausted = `ReplaceIfHigher` (one Exhausted instance with max magnitude); Wounded = `Sum` (multiple wounds stack); Frightened = `ReplaceIfHigher`. |
| **StatusEffect** | Behavioral effect from a status (e.g., Drunk reduces Speak coherence) | Per-flag effect descriptor. V1: descriptive only (text in feature design); V1+ formalized as effect-trait that subsequent validators / Chorus consume programmatically. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

PL_006 emits / consumes events that all map to existing active categories — no new EVT-T* row needed.

| PL_006 path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Status applied (from PL_005 Interaction outcome) | **EVT-T3 Derived** | `aggregate_type=actor_status`, delta_kind=`ApplyStatus` | Aggregate-Owner role (PL_006 owner-service, integrated into world-service) | Causal-ref REQUIRED to triggering Interaction event |
| Status dispelled (V1: explicit OutputDecl from PL_005 Use:antidote V1+) | **EVT-T3 Derived** | `aggregate_type=actor_status`, delta_kind=`DispelStatus` | Aggregate-Owner role | Causal-ref REQUIRED to triggering event |
| Status auto-expired (V1+30d via scheduler) | **EVT-T5 Generated** | `Scheduled:StatusExpire` | Generator role (world-rule-scheduler) | Causal-ref REQUIRED to original Apply event; per EVT-A9 RNG-deterministic via causal_refs |
| Status tick effect (V1+ Bleeding HP drain) | **EVT-T5 Generated** | `Scheduled:StatusTick` | Generator role (V1+ scheduler) | V1 not active; V1+ defers to combat feature |

**Closed-set proof for PL_006:** every status path produces an active EVT-T* (T3 / T5). No new EVT-T* row.

---

## §3 Aggregate inventory

**One** aggregate. PL_006 is small + foundational.

### 3.1 `actor_status`

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_status", tier = "T2", scope = "reality")]
pub struct ActorStatus {
    pub reality_id: RealityId,                  // (also from key)
    pub actor_id: ActorId,                      // PC or NPC; identifies actor
    pub instances: Vec<StatusInstance>,         // active statuses; empty = no statuses
    pub last_modified_at_turn: u64,             // for staleness telemetry
    pub schema_version: u32,
}

pub struct StatusInstance {
    pub flag: StatusFlag,                       // closed enum V1
    pub magnitude: u8,                          // 1..=10 (V1; V1+ may extend range)
    pub applied_at_turn: u64,                   // channel_event_id of triggering Interaction
    pub applied_at_fiction_ts: i64,             // millis from fiction-clock at apply time
    pub expires_at_fiction_ts: Option<i64>,     // None = manual dispel only V1; Some = auto-expire V1+30d scheduler
    pub source_event_id: u64,                   // causal-ref tracking
    pub source_kind: StatusSource,              // closed enum: which Interaction kind / Generator / etc. applied
}

pub enum StatusFlag {
    // V1 closed set (4 kinds)
    Drunk,
    Exhausted,
    Wounded,
    Frightened,
    // V1+ additions (additive per I14; reserved namespace; not active V1)
    // Stunned,
    // Bleeding,
    // Poisoned,
    // Charmed,
    // Encumbered,
    // Buffed,
    // Tired,
    // Hungry,
    // Restrained,
}

pub enum StatusSource {
    Interaction { kind: InteractionKind },      // applied by PL_005 Interaction outcome
    WorldRule { rule_id: String },              // applied by world-rule (e.g., Exhausted from sleep-skipped)
    Scheduled,                                  // V1+30d Scheduled:StatusApply Generator
    Admin,                                      // Administrative action
}
```

- T2 + RealityScoped: per-actor across reality lifetime.
- One row per `(reality_id, actor_id)`.
- Generic shape covers PC + NPC (D6 cross-actor uniformity).
- Synthetic actors (ChorusOrchestrator / BubbleUpAggregator / etc.) don't accumulate status V1 (their actor_status row stays empty).

---

## §4 Tier+scope table (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `actor_status` | T2 | T2 | Reality | ~1 per turn (UI status icons + Chorus persona context) | ~0.1-1 per turn (status applies on Use/Strike/Frightened observation) | Persistent across sessions; reality-global per actor; eventual consistency on cross-session reads OK; no T3-grade urgency. |

---

## §5 DP primitives this feature calls

By name. No raw clients (DP-R3).

### 5.1 Reads

- `dp::read_projection_reality::<ActorStatus>(ctx, actor_id, wait_for=None, ...)` — UI status bar + Chorus persona context + validator pre-checks (e.g., Strike rejects target=Frozen V1+)
- `dp::query_scoped_reality::<ActorStatus>(ctx, predicate=field_eq(actor_id, X))` — operator queries

### 5.2 Writes

- `dp::t2_write::<ActorStatus>(ctx, actor_id, ApplyStatusDelta { flag, magnitude, ... })` — apply path
- `dp::t2_write::<ActorStatus>(ctx, actor_id, DispelStatusDelta { flag })` — V1 manual dispel
- `dp::t2_write::<ActorStatus>(ctx, actor_id, ExpireStatusDelta { flag, source_event_id })` — V1+30d scheduler-driven

### 5.3 Subscriptions

- UI subscribes to `actor_status` invalidations via DP-X cache invalidation broadcast → re-renders status bar
- Chorus orchestrator reads at SceneRoster build time (cached for batch duration per NPC_002 §6)

### 5.4 Capability + lifecycle

- `produce: [Derived]` + `write: { aggregate_type: actor_status, tier: T2, scope: reality }` — for PL_006 owner-service (world-service in V1; logical role)
- V1+30d scheduler service: `produce: [Generated]` + `write: actor_status` for auto-expire

---

## §6 Capability requirements (JWT claims)

Inherits PL_001 + PL_005 patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Derived]` + `write: actor_status @ T2 @ reality` | world-service backend (PL_006 owner role) | apply/dispel from PL_005 Interaction outcomes |
| `produce: [Generated]` + `write: actor_status @ T2 @ reality` | V1+30d world-rule-scheduler service | Scheduled:StatusExpire / Scheduled:StatusTick |
| `read: actor_status @ T2 @ reality` | every PC session + Chorus orchestrator | UI display + Chorus persona context |

---

## §7 Subscribe pattern

UI receives `actor_status` updates via DP-X cache invalidation (DP-A4 pub/sub) → re-renders status icons. No durable channel-event subscription needed (status changes are EVT-T3 Derived, propagated through normal channel event stream — UI multiplex stream catches them per PL_001 §7).

Chorus orchestrator reads `actor_status` at SceneRoster build time per NPC_002 §6 — Tier 1-4 priority algorithm may use status as input (Frightened NPCs deprioritized for combat reactions; Drunk PCs may receive amused NPCTurn reactions).

---

## §8 Pattern choices

### 8.1 Closed-set enum discipline (per D3)

V1 minimum = 4 kinds: Drunk / Exhausted / Wounded / Frightened. Sufficient for V1 vertical-slice (Use:wine outcome + post-/sleep + V1+ Strike survival + V1+ social observation). V1+ additive per I14; new kinds register in boundary matrix.

### 8.2 Cross-actor uniformity (per D6)

Single `actor_status` aggregate covers PC + NPC. PCS_001 references via `pc_stats_v1_stub.status_flags` → resolves to `actor_status` aggregate query for the PC's actor_id. Future NPC_003 references same aggregate for NPC actor_id. No drift risk.

### 8.3 Stack policy per flag

| Flag | Stack policy | Rationale |
|---|---|---|
| Drunk | **Sum** (magnitudes accumulate) | drinking more increases drunkenness |
| Exhausted | **ReplaceIfHigher** | exhausted is a state, not a count |
| Wounded | **Sum** (multiple wounds stack) | each wound accumulates |
| Frightened | **ReplaceIfHigher** | frightened is a state |

V1+ kinds declare their stack policy at registration in boundary matrix.

### 8.4 Magnitude semantics

`magnitude: u8` range 1..=10 V1. Higher = more intense effect. Specific behavior per flag:
- Drunk magnitude 1-3: mild buzz; 4-7: noticeable; 8-10: stumbling drunk
- Wounded magnitude 1-3: minor; 4-7: significant; 8-10: critical (V1+ may trigger MortalityTransition)
- Exhausted magnitude scales recovery time
- Frightened magnitude scales reaction intensity

### 8.5 Lifecycle: V1 simplification

V1 = Apply + Dispel manual only. **No auto-expire V1.** V1+30d scheduler adds Scheduled:StatusExpire (via EVT-T5 Generated per EVT-G2 trigger source kind (c) FictionTimeMarker matching `expires_at_fiction_ts`).

### 8.6 Source tracking (StatusSource enum)

Every StatusInstance records its source (which Interaction / world-rule / scheduler applied it). Enables:
- Forensic audit ("what made Lý Minh Drunk?")
- Selective dispel (V1+: dispel only Wounded from specific Strike, not all Wounds)
- Replay traceability per EVT-A6 causal-refs

### 8.7 Lex axiom integration (V1+ deferred)

WA_001 Lex may forbid certain statuses per reality (e.g., "no Frightened in stoic monk reality"). V1+ Lex extension; V1 all 4 kinds allowed in all realities. Reject path: `status.flag_forbidden_in_reality`.

---

## §9 Failure-mode UX

| Reject reason | When | Vietnamese reject copy |
|---|---|---|
| `status.flag_forbidden_in_reality` (V1+) | Lex axiom rejects status flag for this reality | "[Status] không tồn tại trong thế giới này." |
| `status.target_dead` | Apply on actor with Mortality≠Alive | "Không thể áp dụng trạng thái cho người đã khuất." |
| `status.unknown_flag` | flag value not in V1 closed enum | (Should not reach validator — schema check at stage 0) |
| `status.dispel_not_present` | Dispel a flag the actor doesn't have | (V1: silent no-op + audit-log; not user-facing reject) |
| `status.invalid_magnitude` | magnitude outside 1..=10 V1 range | (Schema check; not user-facing) |

V1 most rejects are schema-level (unreachable in normal operation). User-facing rejects only for `target_dead`.

---

## §10 Cross-service handoff

PL_006 doesn't introduce a new cross-service flow. Status apply/dispel happens **as part of PL_005 Interaction's actual_outputs flow** (PL_005c §3 mortality flow + §4 opinion drift flow are precedent patterns).

```
PL_005 Interaction:Use commits → actual_outputs include
   OutputDecl { target: Actor(LM01), aggregate: actor_status,
                delta: ApplyStatus(Drunk, magnitude=2, source_event_id: T1) }
   → world-service (PL_006 owner role) emits Derived:
   dp::t2_write::<ActorStatus>(ctx, LM01, ApplyStatusDelta { ... }) → T2
   (causal_refs=[T1])

UI receives T1 (Use commit) + T2 (status apply) via multiplex stream.
Renders wine consumption + status icon (Drunk).

V1+30d scheduler: when fiction_clock crosses expires_at_fiction_ts:
   scheduler emits EVT-T5 Generated::Scheduled:StatusExpire → T3
   (causal_refs=[T2])
   PL_006 owner consumes → dp::t2_write ExpireStatusDelta → T4
   UI receives → status icon clears
```

CausalityToken chain inherits from PL_005 §10 Strike example pattern.

---

## §11 Sequence: Apply Drunk (V1 — Use:wine on self)

```
PC `/use rượu` (Interaction:Use, UseIntent=Consume, target=self)

world-service (per PL_005c §1 validator chain):
  a. claim_turn_slot
  b. validator stages 0-9 ✓
     world-rule (stage 7): Use rượu on self → ActualOutputs include:
       [{ target: Actor(LM01), aggregate: pc_stats_v1_stub,
          delta: StatusFlagDelta(add Drunk via PL_006) },        // legacy reference
        { target: Actor(LM01), aggregate: actor_status,           // PL_006 path
          delta: ApplyStatus { flag: Drunk, magnitude: 2,
                               applied_at_turn: <current>,
                               applied_at_fiction_ts: <current>,
                               expires_at_fiction_ts: None,        // V1: no auto-expire
                               source_event_id: <Interaction T1>,
                               source_kind: Interaction { kind: Use } } }]
  c. dp.advance_turn → Submitted T1 (Interaction:Use commit)
  d. PL_006 owner-service (in world-service) emits Derived:
     dp.t2_write::<ActorStatus>(ctx, LM01, ApplyStatusDelta { ... })  → T2
     (causal_refs=[T1])
  e. release_turn_slot

UI:
  - receives T1 → render narration "Lý Minh nâng chén rượu, uống cạn"
  - receives T2 → display Drunk icon on Lý Minh's status bar (magnitude 2)

Subsequent Speak by LM01:
  - Chorus orchestrator reads actor_status(LM01) at SceneRoster
  - Sees Drunk magnitude=2 → may add "(slurred)" hint to NPC reaction prompt context (V1+ feature)
```

---

## §12 Sequence: Apply Exhausted (V1 — sleep-skipped detection)

```
Background world-rule (V1 simplification — no scheduler yet):
  Each PC turn, world-service checks:
    if (current_fiction_ts - last_sleep_fiction_ts > 16 hours)
      AND (LM01.actor_status doesn't already have Exhausted):
      apply Exhausted

When triggered (e.g., during PL_001 §13 fast-forward chain after long /travel):
  world-service emits Derived as side-effect of the parent event:
  dp.t2_write::<ActorStatus>(ctx, LM01, ApplyStatusDelta {
    flag: Exhausted, magnitude: 1,
    source_event_id: <parent event>,
    source_kind: WorldRule { rule_id: "exhaustion.sleep_skipped" }
  })  → T1 (or follow-on T_n)

UI receives → Exhausted icon

V1: actor_status remains until LM01 `/sleep` (which dispels Exhausted via
PL_005 Use:bed Use kind OR via direct OutputDecl from /sleep meta-command
flow per PL_002). V1+30d scheduler may add auto-recovery mechanism.
```

---

## §13 Sequence: Dispel via /sleep (V1 — manual)

```
PC `/sleep until dawn` (PL_002 MetaCommand → PL_001 §12 fast-forward chain)

world-service:
  - advance_turn (FastForward) commits → T1
  - world-rule post-commit derivation: PC was Exhausted before /sleep + slept ≥ 8 hours
    → ActualOutputs (from PL_001b §12 lifecycle) include:
    OutputDecl { target: Actor(LM01), aggregate: actor_status,
                 delta: DispelStatus(Exhausted) }
  - PL_006 owner emits Derived:
    dp.t2_write::<ActorStatus>(ctx, LM01, DispelStatusDelta { flag: Exhausted })  → T2

UI: Exhausted icon clears
```

---

## §14 Sequence: V1+30d auto-expire (deferred)

V1+30d scheduler activates auto-expire per [EVT-L11 phasing](../../07_event_model/08_scheduled_events.md#evt-l11--phasing-v1--v130d--v2):

```
Scheduler subscribes via EVT-G2 trigger source (c) FictionTimeMarker:
  for each StatusInstance with expires_at_fiction_ts: Some(t),
  fire when fiction_clock crosses t

On fire:
  Generator emits EVT-T5 Generated::Scheduled:StatusExpire
  payload: { actor_id, flag, source_event_id }
  causal_refs: [original Apply event]
  RNG seed: deterministic_rng(channel_id, original_apply_event_id) per EVT-A9

PL_006 owner consumes Generated:
  dp.t2_write::<ActorStatus>(ctx, actor_id, ExpireStatusDelta { flag, source_event_id })

V1: this entire flow is **deferred** (no scheduler running). V1 statuses are persistent until manual Dispel.
```

---

## §15 Acceptance criteria (LOCK gate)

PL_006 implementation-ready when world-service can pass these scenarios.

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-STA-1 APPLY DRUNK** | LM01 `/use rượu` on self | Interaction:Use commits; ApplyStatusDelta(Drunk, mag=2) Derived event committed; UI receives status icon |
| **AC-STA-2 STACK SUM** | LM01 `/use rượu` twice in sequence | actor_status has single Drunk instance with magnitude summed (e.g., 2+2=4); per stack policy `Sum` |
| **AC-STA-3 STACK REPLACE** | Apply Frightened mag=1, then Frightened mag=3 | actor_status has single Frightened instance with magnitude=3; per stack policy `ReplaceIfHigher` |
| **AC-STA-4 DISPEL VIA /SLEEP** | LM01 Exhausted, then `/sleep until dawn` | ActorStatus Exhausted instance removed via DispelStatusDelta Derived |
| **AC-STA-5 CROSS-ACTOR UNIFORMITY** | NPC tieu_thuy receives Frightened from observed Strike | NPC's actor_status (same aggregate type as PC's) updated; works identically |

### 15.2 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-STA-6 TARGET DEAD** | Apply Drunk to NPC with Mortality=Dead | rejected with `status.target_dead`; Vietnamese reject copy |
| **AC-STA-7 INVALID MAGNITUDE** | ApplyStatusDelta with magnitude=20 (out of 1..=10 range) | rejected at schema check (stage 0); not user-facing |

### 15.3 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-STA-V1+1** | V1+30d auto-expire after fiction-time elapsed | scheduler service ships |
| **AC-STA-V1+2** | Wounded magnitude=10 triggers MortalityTransition | combat feature design |
| **AC-STA-V1+3** | Lex forbids Drunk in alcohol-prohibition reality | WA_001 Lex extension to status axioms |

**Total V1-testable: 7 (AC-STA-1 to AC-STA-7).** PL_006 → CANDIDATE-LOCK when 7 V1 scenarios pass integration tests.

---

## §16 Open questions deferred + landing point

| ID | Question | Defer to |
|---|---|---|
| **STA-D1** | V1+ kinds enumeration (Stunned, Bleeding, Poisoned, Charmed, Encumbered, Buffed, Tired, Hungry, Restrained) | V1+ feature designs that need them (combat for Stunned/Bleeding; social for Charmed/Frightened expansion; inventory for Encumbered) |
| **STA-D2** | Per-status effect formalization (programmatic effect-trait vs descriptive) | V1+ when subsequent validators / Chorus need to programmatically read status effects |
| **STA-D3** | StatusFlag × Lex axiom integration (which realities forbid which statuses) | V1+ WA_001 Lex extension |
| **STA-D4** | V1+30d scheduler integration for auto-expire | scheduler service ships |
| **STA-D5** | Selective dispel (dispel only specific source) | V1+ when remedies/healing items differentiate |
| **STA-D6** | Status × NPC opinion modifier (Drunk PCs get more amused reactions) | V1+ NPC personality system (per PL_005c §4 INT-INT-D5) |
| **STA-D7** | Sleep-skipped detection mechanism (V1 hardcoded; V1+ configurable threshold) | V1+ tuning |
| **STA-D8** | Status × admin override (Administrative dispel for stuck players) | V1+ admin-cli command design |

---

## §17 Cross-references

- [`PL_001 Continuum`](PL_001_continuum.md) — turn-slot + fiction-clock substrate
- [`PL_001b lifecycle`](PL_001b_continuum_lifecycle.md) — fast-forward chain (sleep dispel pattern)
- [`PL_002 Grammar`](PL_002_command_grammar.md) — `/sleep` MetaCommand triggers Dispel
- [`PL_005 Interaction`](PL_005_interaction.md) — Use kind applies statuses; Strike applies Wounded V1+
- [`PL_005b contracts`](PL_005b_interaction_contracts.md) §6 — Use kind ProposedOutputs reference actor_status
- [`PL_005c integration`](PL_005c_interaction_integration.md) §3-§4 — mortality flow + opinion drift parallel patterns
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) — EVT-A6 typed causal-refs + EVT-A9 RNG determinism + EVT-A11 sub-type ownership
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T3 Derived (status apply/dispel) + EVT-T5 Generated (auto-expire V1+30d)
- [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) EVT-V6 — post-commit side-effect framework
- [`07_event_model/08_scheduled_events.md`](../../07_event_model/08_scheduled_events.md) EVT-L7..L11 — scheduler trigger sources for V1+30d auto-expire
- [`07_event_model/12_generation_framework.md`](../../07_event_model/12_generation_framework.md) — Generator Registry (V1+30d scheduler registration)
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `actor_status` aggregate ownership + StatusFlag enum ownership
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `status.*` rule_id namespace registered
- [`NPC_001 Cast`](../05_npc_systems/NPC_001_cast.md) — ActorId enum (status applies to both Pc and Npc variants)
- [`NPC_002 Chorus`](../05_npc_systems/NPC_002_chorus.md) — reads actor_status for SceneRoster context
- [`PCS_001 brief`](../06_pc_systems/00_AGENT_BRIEF.md) §S5 — `pc_stats_v1_stub.status_flags` references PL_006 enum
- Future `NPC_003 mortality` — references same StatusFlag enum (cross-actor uniformity)
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — V1+ status axiom integration
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative grounding (Drunk via Use; Exhausted via /sleep flow)

---

## §18 Implementation readiness checklist

PL_006 satisfies DP-R2 + 22_feature_design_quickstart.md required items:

- [x] §2 Domain concepts + StatusFlag closed enum + StatusInstance + StatusSource + Stack policy table
- [x] §2.5 Event-model mapping (T3 apply/dispel + T5 V1+30d auto-expire; no new EVT-T*)
- [x] §3 Aggregate inventory (1 new: `actor_status` T2/Reality)
- [x] §4 Tier+scope (per DP-R2)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT requirements
- [x] §7 Subscribe pattern (UI invalidation + Chorus read at SceneRoster build)
- [x] §8 Pattern choices (closed-set / cross-actor uniformity / stack policy / magnitude / V1 lifecycle simplification / source tracking / Lex V1+)
- [x] §9 Failure UX (Vietnamese reject copy in `status.*` namespace)
- [x] §10 Cross-service handoff (inherits PL_005 §10 Strike pattern)
- [x] §11-§14 Sequences (Apply Drunk / Apply Exhausted / Dispel via /sleep / V1+30d auto-expire deferred)
- [x] §15 Acceptance criteria (7 V1-testable + 3 V1+ deferred)
- [x] §16 Deferrals STA-D1..D8
- [x] §17 Cross-references
- [x] §18 Readiness (this section)

**Status transition:** DRAFT 2026-04-26 → CANDIDATE-LOCK after 7 V1 acceptance scenarios pass integration tests.

**Boundary registration in same commit:** `_boundaries/01_feature_ownership_matrix.md` adds `actor_status` aggregate ownership row + StatusFlag enum ownership note in EVT-T3 Derived sub-types row; `_boundaries/02_extension_contracts.md` §1.4 adds `status.*` prefix.

**Next** (when CANDIDATE-LOCK granted): world-service can implement Status apply/dispel as part of PL_005 Interaction outcome processing. First vertical-slice target = AC-STA-1 (APPLY DRUNK) reusing wine-Use scenario. AC-STA-4 (DISPEL VIA /SLEEP) integrates with PL_001b §12 fast-forward chain. V1+30d work (auto-expire) defers to scheduler service ship.
