# WA_002 — Heresy (Forbidden Knowledge & Cross-Reality Contamination)

> **Conversational name:** "Heresy" (HER). The model for actors importing foreign-world abilities into a reality where they are normally forbidden — controlled, budget-tracked, with cascade-consequences when limits are exceeded. Pairs with [WA_001 Lex](WA_001_lex.md): Heresy violates the Lex; this feature designs how violation is detected, optionally permitted, and what happens to the world when it tears.
>
> **Category:** WA — World Authoring
> **Status:** **CANDIDATE-LOCK 2026-04-25** (DRAFT → split into root + lifecycle 2026-04-25 closure pass; §14 acceptance criteria added in WA_002b — 10 scenarios). LOCK granted after the 10 acceptance scenarios have passing integration tests.
> **Companion file:** [`WA_002b_heresy_lifecycle.md`](WA_002b_heresy_lifecycle.md) — sequences (§11-§13), acceptance criteria (§14), deferrals (§15), cross-references (§16), readiness checklist (§17).
> **Catalog refs:** **DF4 World Rules** (sub-feature: forbidden-knowledge / contamination model). Companion to WA_001 Lex.
> **Builds on:** [WA_001 Lex](WA_001_lex.md) (extends `Axiom.allowed: bool` to `Axiom.allowance: Allowance` enum), [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) (consumes scaffold; reality stability lives at reality root channel), [NPC_001 Cast](../05_npc_systems/NPC_001_cast.md) §3.6 reality_root channel for stability events, [07_event_model EVT-T11 WorldTick](../../07_event_model/03_event_taxonomy.md) (stage transitions emit WorldTick events V2+; V1 admin/manual).
> **Resolves:** WA_001 Lex deferrals LX-D1 (per-actor exception), LX-D2 (budget model), LX-D3 (cascade-consequence on violation). The user's "transmigrator brings ma pháp into a world of khoa học và logic" scenario.

---

## §1 User story (concrete)

**Scenario A — Controlled transmigrator (the canonical Heresy case):**

Reality `R-modern-earth-2026` (the user's example: "thế giới của khoa học và logic"). LexConfig:
- `energy_system: None`
- `MagicSpells: Forbidden`
- `default_disposition: Restrictive`

Author wants to allow ONE protagonist PC to be a transmigrator with imported magic ability — but the world is fundamentally hostile to magic (it doesn't have mana to begin with). Author declares in RealityManifest:

```yaml
contamination_allowances:
  - actor_id: pc_protagonist
    imported_kind: MagicSpells
    allowance:
      kind: AllowedWithBudget
      budget:
        max_per_fiction_day: 3
        max_total_lifetime: 100
      energy_substrate:
        kind: ConvertWorldEnergy        # draws from world ambient energy
        efficiency: 0.10                # 10% conversion (90% wasted as world strain)
      cascade_on_exceeded: RejectAndStrainWorld
```

When PC casts a fireball:
- Lex checks: `MagicSpells` is `Forbidden` for this reality → would normally reject
- BUT Heresy reads `actor_contamination_decl` → finds an `AllowedWithBudget` exception for this (actor, kind) → Lex defers to Heresy
- Heresy reads `actor_contamination_state` (today's budget usage):
  - usage < `max_per_fiction_day` → allow + increment counter + emit world strain side-effect
  - usage >= `max_per_fiction_day` → reject with `HeresyViolation::BudgetExceeded`

If PC exceeds 100 lifetime → `cascade_on_exceeded: RejectAndStrainWorld` → world stability stage advances.

**Scenario B — Uncontrolled "god-mode" transmigrator (the world-shattering case):**

Same reality, but no `contamination_allowances` declared. PC tries to cast a fireball:
- Lex check rejects immediately (`MagicSpells: Forbidden`)
- Heresy never even runs — Lex catches it first
- PC is just a mortal in this reality; foreign abilities are inaccessible
- This is the V1 default: hard-forbidden + no exceptions = no contamination possible

The "god-mode transmigrator" the user worried about is structurally impossible without an explicit author declaration. Authors can SCREW UP by declaring overly permissive `contamination_allowances` (no budget, no cascade), but that's an authoring choice with explicit knobs — not an accidental world-shatter.

**Scenario C — Stage transition (V1 admin-driven):**

Reality has accumulated 50 contamination violations across 3 transmigrator PCs. Author/admin (via S5 admin action) decides to advance world stability from `Strained` → `Cracking`. Heresy commits a `world_stability` mutation + emits `EVT-T11 WorldTick` at reality root channel; bubble-up propagates to all cells; NPCs see "strange weather, birds fleeing, walls cracking". V2+ may automate this transition based on threshold counters; V1 keeps it manual to avoid runaway dynamics during prototyping.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Allowance** | Replaces WA_001 Lex's `Axiom.allowed: bool` with a 3-variant enum | `Allowed \| Forbidden \| AllowedWithBudget(BudgetSpec)`. WA_002 ships LexConfig schema bump to v2. |
| **ContaminationDecl** | Author-declared per-actor exception to a Lex axiom | One row per `(reality, actor, imported_kind)`. Declares the budget, energy substrate, cascade behavior. |
| **ContaminationState** | Per-actor runtime budget tracking | Counters: today's usage, lifetime usage, last violation. Updated on each accepted contamination action. |
| **BudgetSpec** | Numeric caps + reset cadence | V1: per-fiction-day count + lifetime count. V2+: per-fiction-week, ramping decay, ability-power-tier. |
| **EnergySubstrate** | Where contamination draws power from | V1: closed set (None / DrawFromActor / ConvertWorldEnergy). Determines world-strain rate. |
| **CascadeOnExceeded** | What happens when budget is exceeded | V1 closed set: `Reject \| RejectAndStrainWorld \| AllowAndStrainWorld`. |
| **WorldStability** | Reality-level state machine | 5 stages: `Stable \| Strained \| Cracking \| Catastrophic \| Shattered`. Terminal `Shattered` per parallel to DP-A18 channel-lifecycle "Dissolved is terminal". |
| **HeresyViolation** | Rejection-path data when budget exceeded | Carries actor_id + imported_kind + current_usage + budget_cap + Vietnamese reject copy. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

Heresy is mostly a validator (like Lex) but ALSO emits side-effect aggregate mutations and (V2+) world-stage transition events.

| Heresy output | EVT-T* impact |
|---|---|
| Allow contamination action through | Pipeline continues; the proposed action commits as EVT-T1/T2 with `outcome=Accepted`. |
| Allow + side-effect contamination counter increment | Side-effect emits **EVT-T3 AggregateMutation** on `actor_contamination_state` (causal_ref to the parent EVT-T1/T2). |
| Allow + side-effect world strain | Additional **EVT-T3 AggregateMutation** on `world_stability` (only if `energy_substrate=ConvertWorldEnergy` and strain accumulator threshold crossed). |
| Reject (BudgetExceeded) | Standard PL_001 §15 rejection path; `TurnEvent { outcome: Rejected { reason: WorldRuleViolation { rule_id: "heresy.budget_exceeded" } } }` via plain `t2_write`. |
| Stage transition (V1 admin / V2+ auto) | **EVT-T11 WorldTick** at reality root channel + **EVT-T8 AdminAction** (V1 path) recording who triggered it. |

No new EVT-T* row; all existing categories cover Heresy.

---

## §3 Aggregate inventory

Three NEW aggregates + one EXTENSION to `lex_config`.

### 3.0 `lex_config` schema bump (extends WA_001)

```rust
// SCHEMA BUMP from LexSchema=1 (WA_001) to LexSchema=2 (WA_002).
// Additive change per foundation I14: Axiom.allowed: bool → Axiom.allowance: Allowance.
// LexSchema=1 reads upgraded transparently: bool true → Allowed; bool false → Forbidden.

pub struct Axiom {
    pub kind: AxiomKind,
    pub allowance: Allowance,                     // ← was `allowed: bool`
    pub note: Option<String>,
}

pub enum Allowance {
    Allowed,                                      // freely available to all actors
    Forbidden,                                    // hard-rejected by Lex
    AllowedWithBudget(BudgetTemplate),            // available to actors with matching ContaminationDecl
}

pub struct BudgetTemplate {
    // Default budget if a ContaminationDecl doesn't specify its own.
    // ContaminationDecl-specified budgets override this.
    pub max_per_fiction_day: Option<u32>,
    pub max_total_lifetime: Option<u32>,
    pub default_energy_substrate: EnergySubstrate,
    pub default_cascade: CascadeOnExceeded,
}
```

### 3.1 `actor_contamination_decl`

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_contamination_decl", tier = "T2", scope = "reality")]
pub struct ActorContaminationDecl {
    #[dp(indexed)] pub actor_id: ActorId,         // typically Pc(PcId); also valid for Npc(NpcId) for V2+ canonical contaminator NPCs
    #[dp(indexed)] pub imported_kind: AxiomKind,  // which forbidden kind this actor can use
    pub budget: BudgetSpec,                       // overrides Allowance's BudgetTemplate
    pub energy_substrate: EnergySubstrate,
    pub cascade_on_exceeded: CascadeOnExceeded,
    pub declared_at: Timestamp,
    pub declared_by: AuthorRef,                   // typically book author or admin
    pub note: Option<String>,                     // narrative justification for audit
}

pub struct BudgetSpec {
    pub max_per_fiction_day: Option<u32>,
    pub max_total_lifetime: Option<u32>,
    // V2+: max_per_fiction_week, max_simultaneous_actors_with_kind, ramping_decay
}

pub enum EnergySubstrate {
    None,                                          // ability is "free" (e.g., transmigrator inherent skill)
    DrawFromActor,                                 // actor's own resource (HP, fatigue) drained per use
    ConvertWorldEnergy { efficiency: f32 },        // draws from world ambient; 1-efficiency wasted as world strain
}

pub enum CascadeOnExceeded {
    Reject,                                        // budget exceeded → just reject; no world impact
    RejectAndStrainWorld,                          // reject + bump world strain accumulator
    AllowAndStrainWorld,                           // unsafe: allow despite cap, world degrades faster
}
```

- T2 + RealityScoped: per-(reality, actor, kind) declarations; one row per combination.
- Authored at PC creation (book canon) or runtime via admin/author UI (V2+).
- Read at validate time when an actor proposes a contaminating ability.

**Composite key:** `(actor_id, imported_kind)` — an actor can have multiple ContaminationDecls for different imported kinds (e.g., transmigrator with both MagicSpells AND Cybernetics from a sci-fi source world).

### 3.2 `actor_contamination_state`

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_contamination_state", tier = "T2", scope = "reality")]
pub struct ActorContaminationState {
    #[dp(indexed)] pub actor_id: ActorId,
    #[dp(indexed)] pub imported_kind: AxiomKind,
    pub usage_today: u32,                          // count this fiction-day
    pub usage_lifetime: u32,                       // count since reality-start
    pub last_violation: Option<u64>,               // channel_event_id of last attempted-when-exceeded
    pub day_marker: FictionTimeTuple,             // for daily reset comparison
}
```

- T2 + RealityScoped: per-(reality, actor, kind) runtime state, one row per matching ContaminationDecl.
- Created lazily at first contamination attempt (matching ContaminationDecl found, no state yet).
- Daily reset: when `day_marker.day_of_season < current_fiction_clock.day_of_season`, reset `usage_today=0` + advance `day_marker`. Reset is lazy (computed on next read after day boundary).

### 3.3 `world_stability`

```rust
#[derive(Aggregate)]
#[dp(type_name = "world_stability", tier = "T3", scope = "reality")]
pub struct WorldStability {
    pub reality_id: RealityId,                    // singleton per reality
    pub current_stage: WorldStabilityStage,
    pub strain_accumulator: u32,                  // accumulated strain; thresholds advance stage in V2+
    pub stage_entered_at_turn: u64,
    pub stage_entered_at_fiction_time: FictionTimeTuple,
    pub stage_entered_by: ActorOrAdminRef,         // who triggered the transition
    pub stage_history: Vec<StageTransition>,      // up to 16 most recent transitions
}

pub enum WorldStabilityStage {
    Stable,                                        // baseline; no strain; nothing visible
    Strained,                                      // first violation; subtle ambient signs only
    Cracking { stage: u8 },                        // worsening; visible to NPCs (1..=3 sub-stages)
    Catastrophic,                                  // visible to all; reality is destabilizing
    Shattered,                                     // TERMINAL — reality unplayable; PCs forcibly extracted (V2+)
}

pub struct StageTransition {
    pub from_stage: WorldStabilityStage,
    pub to_stage: WorldStabilityStage,
    pub at_turn: u64,
    pub at_fiction_time: FictionTimeTuple,
    pub triggered_by: ActorOrAdminRef,
    pub reason: String,
}
```

- **T3** + RealityScoped: stability transitions affect canon and player UX globally. Atomicity matters because stage advance + bubble-up event must be seen consistently.
- One row per reality; singleton.
- `Shattered` is terminal per pattern with DP-A18 channel `Dissolved`. Reality cannot return from Shattered without DF8 canon-fork (V3+).
- Initialized at reality bootstrap to `Stable`.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `lex_config` (extension) | T2 | T2 | Reality | per Lex check (already counted in WA_001) | rare (author edits) | (already counted in WA_001 §4) |
| `actor_contamination_decl` | T2 | T2 | Reality | ~1/turn for actors with declarations (cached) | ~0 hot path; rare on author edits | Per-(actor, kind); durable; eventual consistency on edit OK. |
| `actor_contamination_state` | T2 | T2 | Reality | ~1/turn for contaminating actions | ~1/contaminating-action | Per-(actor, kind); durable; counter increments are write-amplified but bounded by budget. |
| `world_stability` | T2 (cache) | T3 | Reality | ~1/turn for cells with strain visible (cache hit >99%) | ~0 hot path; rare on stage transition | Singleton; transitions are major canon events; T3 atomicity for stage advance. |

T3 is justified ONLY for `world_stability` writes (rare; major). Reads are T2 cached.

---

## §5 DP primitives this feature calls

### 5.1 Reads

```rust
// At Lex's validator slot, AFTER Lex passes (or AFTER Lex's bool→Allowance check returns AllowedWithBudget):
let decl = dp::read_projection_reality::<ActorContaminationDecl>(
    ctx,
    ActorContaminationDeclId::derive(actor_id, imported_kind),
    wait_for=None, ...
).await?;

let state = dp::read_projection_reality::<ActorContaminationState>(
    ctx,
    ActorContaminationStateId::derive(actor_id, imported_kind),
    wait_for=None, ...
).await?;

let stability = dp::read_projection_reality::<WorldStability>(
    ctx,
    WorldStabilityId::singleton(reality_id),
    wait_for=None, ...
).await?;
```

3 reads at validator time, all T2 cached. Wall-clock <10 ms p99.

### 5.2 Writes

```rust
// On accepted contamination action: increment counter
dp::t2_write::<ActorContaminationState>(ctx, state_id, ContaminationStateDelta::Increment {
    today: 1,
    lifetime: 1,
}).await?;

// If energy_substrate=ConvertWorldEnergy: emit world-strain bump
dp::t2_write::<WorldStability>(ctx, WorldStabilityId::singleton(reality_id),
    StabilityDelta::AddStrain { amount: strain_calc(efficiency, ability_tier) }).await?;

// Stage transition (V1 admin-driven, V2+ auto):
dp::t3_write::<WorldStability>(ctx, WorldStabilityId::singleton(reality_id),
    StabilityDelta::AdvanceStage { to_stage, triggered_by, reason }).await?;
// T3 ensures stage transition is globally visible before any subsequent action observes stale stage.
```

### 5.3 EVT-T11 WorldTick emission (stage transition)

When stage advances:
```rust
dp::advance_turn(ctx,
    &ChannelId::reality_root(reality_id),       // root channel — broadcasts to all descendants
    turn_data: TurnEvent { /* WorldTick payload */ },
    causal_refs: vec![triggering_admin_action_id]
).await?;
```

WorldTick at reality root → bubble-up propagates per DP-Ch25 to all descendant channels (cells get the strain event). NPCs may react via PL_003 / NPC_002 Chorus (NPCs in a Strained world act differently).

---

## §6 Validator pipeline integration (slot AFTER Lex)

Heresy slots in IMMEDIATELY AFTER Lex in EVT-V*. Drift watchpoint with event-model agent's Phase 3.

### 6.1 Slot ordering (proposed extension to WA_001 §7.1)

```text
EVT-V* pipeline:

  schema → capability → A5 intent → A6 sanitize
    │
  ★ lex_check (WA_001) ★              ← evaluates Allowance
    │ Allowance::Allowed              → continue pipeline
    │ Allowance::Forbidden            → reject (Lex catches; Heresy never runs)
    │ Allowance::AllowedWithBudget    → defer to Heresy
    │
  ★ heresy_check (WA_002, THIS) ★     ← runs only when Lex returned AllowedWithBudget
    │ ContaminationDecl + State checks
    │ pass → continue pipeline (with side-effect writes queued post-commit)
    │ fail → reject (HeresyViolation::BudgetExceeded)
    │
  A6 output filter → canon-drift → causal-ref → commit
    │
  POST-COMMIT side-effects (queued during heresy_check):
    increment ActorContaminationState
    bump WorldStability strain (if ConvertWorldEnergy)
```

### 6.2 Heresy validator algorithm

```text
fn heresy_check(
    proposed_event: &TurnEvent,
    ability_kinds: &[AxiomKind],            // from WA_001 classify_action
    lex: &LexConfig,
) -> Result<HeresyResult, HeresyViolation> {
    let actor = proposed_event.actor;

    for kind in ability_kinds {
        // Find the axiom
        let axiom = lex.axioms.iter().find(|a| a.kind == kind);
        let allowance = axiom.map(|a| &a.allowance).unwrap_or(&default_disposition_allowance(lex));

        match allowance {
            Allowance::Allowed       => continue,                       // not a Heresy concern
            Allowance::Forbidden     => unreachable!("Lex would have rejected"),
            Allowance::AllowedWithBudget(template) => {
                // Find actor's specific ContaminationDecl, fall back to template
                let decl = read_contamination_decl(actor, kind)?
                    .unwrap_or_else(|| template.into_default_decl());

                let state = read_or_create_contamination_state(actor, kind)?;

                // Daily reset check
                let state = if state.day_marker.day_of_season < current_fiction_clock().day_of_season {
                    state.with_day_reset()
                } else { state };

                // Budget check
                if let Some(cap) = decl.budget.max_per_fiction_day {
                    if state.usage_today >= cap {
                        return Err(HeresyViolation::DailyBudgetExceeded {
                            actor, kind: *kind,
                            current: state.usage_today, cap,
                            cascade: decl.cascade_on_exceeded,
                        });
                    }
                }
                if let Some(cap) = decl.budget.max_total_lifetime {
                    if state.usage_lifetime >= cap {
                        return Err(HeresyViolation::LifetimeBudgetExceeded {
                            actor, kind: *kind,
                            current: state.usage_lifetime, cap,
                            cascade: decl.cascade_on_exceeded,
                        });
                    }
                }

                // Pass: queue post-commit side-effects
                queue_post_commit(SideEffect::IncrementContaminationState {
                    actor, kind: *kind, today: 1, lifetime: 1
                });
                if let EnergySubstrate::ConvertWorldEnergy { efficiency } = decl.energy_substrate {
                    let strain = strain_calc(efficiency, ability_tier(kind));
                    queue_post_commit(SideEffect::AddWorldStrain { amount: strain });
                }
            }
        }
    }

    Ok(HeresyResult::Passed)
}
```

### 6.3 Cascade behavior on rejection

When `HeresyViolation::*BudgetExceeded` returns, the rejection path branches by `cascade_on_exceeded`:

| Cascade | Behavior |
|---|---|
| `Reject` | Standard PL_001 §15 rejection. Action does NOT commit. State NOT incremented. World strain NOT bumped. Net effect: it's as if PC just tried something the world said no to. |
| `RejectAndStrainWorld` | Standard rejection + side-effect: world strain accumulator gets a "violation attempt" bump (smaller than a successful contamination would cause, but non-zero). Repeated attempts cumulate. |
| `AllowAndStrainWorld` | **DANGEROUS author choice.** Action DOES commit despite cap exceeded. State increments. World strain gets a 2x bump (extra penalty). For "uncontrolled god-mode" scenarios where author wants the world to actively burn down. |

V1 default cascade for `AllowedWithBudget` axioms = `RejectAndStrainWorld` if `energy_substrate=ConvertWorldEnergy`, else `Reject`.

---

## §7 World stability state machine

### 7.1 Stage definitions

| Stage | Strain threshold (V2+) | Visible to | UX |
|---|---|---|---|
| `Stable` | 0 | nobody | normal play |
| `Strained` | strain >= 50 | NPCs (subtle) | ambient unease in narration |
| `Cracking { stage: 1 }` | strain >= 200 | NPCs (visible) | NPCs comment on omens |
| `Cracking { stage: 2 }` | strain >= 500 | All actors | weather goes wrong; bubble-up rumors |
| `Cracking { stage: 3 }` | strain >= 1000 | All actors | scene ambient explicitly broken |
| `Catastrophic` | strain >= 2500 | All actors | reality is visibly tearing |
| `Shattered` | strain >= 5000 | All actors | TERMINAL: reality unplayable |

V1 thresholds are placeholders. V2+ tunes from prototype telemetry.

### 7.2 Transition rules (V1)

V1: stage transitions are **manual-only via S5 admin action** (EVT-T8 AdminAction). The thresholds above are advisory; actual transitions require operator decision. Reasons:

- Auto-cascade is dangerous during prototype — runaway dynamics could shatter realities accidentally.
- Operator-in-the-loop matches V1 paused-when-solo model (MV12-D6).
- V2+ adds threshold-based auto-transitions with admin-overrideable safety net.

### 7.3 Stage progression is monotonic

Stages can advance (`Stable → Strained → Cracking → Catastrophic → Shattered`) but generally do NOT regress. V1 exception: admin can revert via S5 (per dual-actor approval per Tier-1 action). V2+ may add narrative recovery quests that lower stage (e.g., "the world was healed by the protagonist's sacrifice"); deferred.

`Shattered` is TERMINAL like DP-A18 channel `Dissolved`. Reality can be re-instantiated only via DF8 canon-fork (V3+).

### 7.4 Stage transition emits EVT-T11 WorldTick at reality root

On stage advance:
1. `t3_write::<WorldStability>` to commit new stage (T3 atomicity)
2. `dp::advance_turn(ctx, &ChannelId::reality_root(...), turn_data: WorldTick { stage_transition }, causal_refs: ...)` at reality root channel
3. Bubble-up aggregators at country/continent/town/cell levels emit derivative ambient events per DP-Ch25
4. UI receives via multiplex stream — players see ambient broken-world signs

Note: WorldTick is EVT-T11 (V1+30d per event-model taxonomy). V1 may emit it as EVT-T8 AdminAction instead (admin-triggered, exists today). Drift watchpoint HER-D8.

---

## §8 Pattern choices

### 8.1 V1 = budget-allowed only; cascade is data-only (no auto-progression)

V1 ships:
- `Allowance::AllowedWithBudget` ✓
- `BudgetSpec { per_fiction_day, lifetime }` ✓
- `EnergySubstrate` enum (used for strain calc, not for cost validation V1) ✓
- `cascade_on_exceeded` field ✓ (Reject / RejectAndStrainWorld / AllowAndStrainWorld)
- `world_stability` aggregate + state machine ✓
- Stage transitions: **admin-only via S5** (V1)

V1 does NOT ship:
- Auto-cascade based on threshold (V2+)
- Per-actor energy cost validation (depends on PCS_001 stats — defer)
- Recovery quests (V2+)
- Multi-reality contamination accounting (DF12 withdrawn)

### 8.2 No "hidden" contamination — explicit author declarations only

V1 locked: contamination is ONLY possible when author explicitly declares `ActorContaminationDecl`. There is no "auto-detect transmigrator from PC backstory" feature. Reasons:

- Detection-by-content is non-deterministic and easy to game
- Author intent is explicit; "someone snuck a transmigrator in" is a content-author bug, not a runtime concern
- PC creation flow (PCS_001, future) will surface contamination-decl as a first-class option in author UI

### 8.3 Contamination is for PCs primarily; NPC contamination is V2+

V1 supports `ActorId::Pc(...)` ContaminationDecls. NPC contamination (an NPC who is itself a transmigrator from another reality) is structurally allowed by the `actor_id: ActorId` field — but no V1 author UI surfaces it. V2+ may add "canonical NPC transmigrator" as a CanonicalActorDecl extension.

### 8.4 World strain is unbounded counter; stage IS bounded

`strain_accumulator: u32` can grow indefinitely. The STAGE is the bounded UX-visible state. V2+ may add strain-decay (natural healing over fiction-time), but V1 ships strain as monotonic-only. This means a reality with many violations can "stack up" strain even at Stable stage; admin-triggered transition then reflects accumulated harm.

### 8.5 Heresy rejections also follow PL_001 §15 contract

Like Lex rejections, Heresy rejections commit a `TurnEvent { outcome: Rejected }` via plain `t2_write`. `turn_number` does NOT advance. `fiction_clock` does NOT advance. The rejected event IS in the audit log so operators can debug "why is PC bouncing on lifetime cap?".

---

## §9 Failure-mode UX

### 9.1 Per-violation reject copy

| HeresyViolation | rule_id | Vietnamese (PC) | English (ops) |
|---|---|---|---|
| `DailyBudgetExceeded` | `heresy.budget_daily.<kind>` | "Hôm nay bạn đã dùng {kind_vi} đủ rồi. Hãy đợi đến mai." | "Daily budget {current}/{cap} exceeded for {actor}/{kind}" |
| `LifetimeBudgetExceeded` | `heresy.budget_lifetime.<kind>` | "Bạn đã dùng hết khả năng {kind_vi} của mình trong thế giới này." | "Lifetime budget {current}/{cap} exhausted for {actor}/{kind}" |
| `NoDeclMatching` (fallthrough — should not happen if Lex returned AllowedWithBudget) | `heresy.no_decl` | (internal — surfaces as Lex `lex.ability_forbidden` instead; see §11.4) | `unreachable: AllowedWithBudget without ContaminationDecl for actor` |

### 9.2 Stage-transition UX (broadcast)

When stage advances, ALL active sessions in the reality see a banner via the multiplex stream:

| Stage | Banner copy (Vietnamese) |
|---|---|
| `Stable → Strained` | (none — Strained is "subtle"; only NPCs notice via narration cues) |
| `Strained → Cracking { stage: 1 }` | (none — visible only via NPC dialogue) |
| `Cracking { stage: 2..3 }` | "Thế giới đang xuất hiện điềm bất an..." |
| `Catastrophic` | "⚠ Thực tại đang nứt vỡ. Hậu quả khó lường." |
| `Shattered` | "💀 Thế giới đã sụp đổ. Thực tại này không còn vận hành được nữa." (UI auto-redirects after 10 s) |

V2+ adds: per-cell ambient adjustments based on stage (LLM prompts include `world_stability_stage` so narration reflects the broken world).

---

## §10 Cross-service handoff

### 10.1 Validator hot path (per turn)

```text
(world-service consumer, post-Lex)
    Lex returned AllowedWithBudget for kind K, actor A
        │
        ▼
    ★ heresy_check ★
        ① read_projection ActorContaminationDecl(A, K)
        ② read_projection ActorContaminationState(A, K)
        ③ apply daily reset (in-process; no write yet)
        ④ check budgets → pass / DailyExceeded / LifetimeExceeded
        ⑤ on pass: queue post-commit increments
        ⑥ on cascade=AllowAndStrainWorld AND exceeded: pass anyway with extra strain
        │
        ▼
    pipeline continues: A6 output filter → canon-drift → commit
        │
        ▼
    POST-COMMIT (after main TurnEvent commits, in same transaction or queued):
        t2_write ActorContaminationState(A, K, increments)
        t2_write WorldStability AddStrain (if energy_substrate = ConvertWorldEnergy)
```

Wall-clock per heresy_check: ~10 ms p99 (3 cached reads + budget arithmetic).

### 10.2 Stage transition (admin path)

```text
admin-cli → world-service:
    AttemptStateTransition(reality_id, advance_stage_to: Cracking{1}, reason: "...")
        │
    S5 dual-actor enforcement (Tier 1 action)
        │
    world-service:
        t3_write WorldStability::AdvanceStage(...)            → globally visible
        advance_turn(reality_root, turn_data: WorldTick{...}) → propagates to all cells via bubble-up
        emit EVT-T8 AdminAction recording who triggered
        │
    bubble-up aggregators at every channel level emit derivative ambient events
        │
    UI multiplex stream delivers banner per §9.2
```

### 10.3 Coordination with WA_001 Lex

Lex schema bump (LexSchema v1 → v2) is an additive evolution per foundation I14. Migration:
- v1 readers see `Axiom.allowed: bool` — auto-upgrade reads: `true → Allowed`, `false → Forbidden`
- v2 writers emit `Axiom.allowance: Allowance` — v1 readers ignore unknown variant `AllowedWithBudget` (defaults to `Forbidden` for safety)
- All world-service nodes deploy v2 codebase before any reality commits a v2-only axiom. Schema gate at validator pipeline.

Drift watchpoint HER-D9: schema migration sequencing.

### 10.4 Coordination with PL_001 Continuum

`world_stability` is RealityScoped (singleton per reality). Reality root channel from PL_001 channel hierarchy is where WorldTick events fire. No Continuum modification needed; Heresy uses the existing scaffold.

---


## §11..§17 — Continued in WA_002b

End of contract layer. The dynamic layer (sequences, acceptance criteria, deferrals, cross-references, readiness) is in the companion file:

→ **[`WA_002b_heresy_lifecycle.md`](WA_002b_heresy_lifecycle.md)**

Sections:

- §11 Sequence: contamination allowed (Scenario A — within budget)
- §12 Sequence: contamination exceeded (Scenario A2 — RejectAndStrainWorld cascade)
- §13 Sequence: stage transition (V1 admin-driven Strained → Cracking{1})
- §14 Acceptance criteria (10 scenarios — AC-HER-1..AC-HER-10 across happy-path / failure-path / boundary)
- §15 Open questions deferred + landing point (HER-D1..D12; HER-D8 boundary-folder-tracked)
- §16 Cross-references
- §17 Implementation readiness checklist (combined WA_002 + WA_002b)

WA_002b is required reading before implementing world-service `heresy_check` handler.
