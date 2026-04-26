# TDIL_001 — Time Dilation Foundation

> **Category:** TDIL — Time Dilation (architecture-scale; 4-clock relativity model for cross-realm time + cultivation pace + xuyên không clock-split)
> **Catalog reference:** [`catalog/cat_17_TDIL_time_dilation.md`](../../catalog/cat_17_TDIL_time_dilation.md) (owns `TDIL-*` stable-ID namespace)
> **Status:** DRAFT 2026-04-27 — All 12 Qs LOCKED via 4-batch deep-dive 2026-04-27 (Q1+Q2+Q3 / Q4+Q5 / Q6+Q7+Q8 / Q9+Q10+Q11+Q12). Companion: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md).
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting pattern.
> **V1 testable acceptance:** 10 scenarios AC-TDIL-1..10 (§13).
> **NOT a foundation tier feature:** Foundation tier remains 6/6 (closed at PROG_001). TDIL_001 is **architecture-scale** (mirror AIT_001 / ACT_001 pattern). Opt-in per reality.
> **Origin:** User direction 2026-04-27 — concerns from Tiên Nghịch / Tây Du Ký / Dragon Ball; architectural insight rooted in Einstein's special + general relativity.

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

User raised 4 interconnected concerns 2026-04-27 (concept-notes §1.1):
1. **Cultivation rate mismatch** — newbie 練氣 cannot share fiction-time clock with 元嬰 elder
2. **Multi-realm time** — Tây Du Ký 天上一日人間一年 (heaven ≠ mortal time)
3. **Time chambers** — Dragon Ball 精神時光屋 (1 day outside = 1 year inside)
4. **PvP newbie-gank prevention** — high-cultivator camping newbie zones disincentivized via time variance

User then refined via 4 architectural insights:
1. **Generators fire per-turn O(1)** NOT per-day (corrects PROG/RES/AIT day-boundary semantic)
2. **Atomic-per-turn travel** (no mid-turn cross-channel)
3. **Per-realm turn streams** (heaven_clock independent from mortal_clock)
4. **4-clock model** (realm + actor + soul + body — twin paradox generalization)

User noted the architectural intuition originated from Einstein relativity. Physics analysis verified soundness (concept-notes §3); model maps cleanly to:
- Proper time τ → actor_clock
- Coordinate time t → realm_clock
- Time dilation γ → time_flow_rate (Convention B physics-aligned)
- Twin paradox → soul-body separability + xuyên không clock-split

### V1 minimum scope (per Q1-Q12 LOCKED)

- **`time_flow_rate: f32`** field on MAP_001 MapLayoutDecl (channel-level; default 1.0)
- **`time_flow_rate_override: Option<f32>`** field on PF_001 PlaceDecl (cell-level)
- Range V1 [0.001, 1000.0]; zero/negative forbidden
- **Cell override REPLACES** channel rate (not multiplies)
- **NEW aggregate `actor_clocks`** (T2/Reality, owner=Actor; ALWAYS-PRESENT V1)
- **3 actor-side clocks**: actor_clock + soul_clock + body_clock (i64 each)
- **Per-turn lockstep** advancement V1 (all 3 advance same proper_advance)
- **Initial value divergence at xuyên không** (PCS_001 §S8 mechanic)
- **Generator clock-source matrix** locked (channel-bound vs actor-bound discipline)
- **Atomic-per-turn travel** validator (`time_dilation.mid_turn_channel_cross_forbidden`)
- **Per-channel fiction_clock** causally tied to channel actor turn-events; idle = frozen
- **Cross-realm observation** O(1) materialization
- **AssemblePrompt dilation context** (~30-50 tokens per dilation-aware actor)
- **Replay determinism FREE V1** (static rates + per-channel turn streams + atomic travel)
- **Forge runtime mutation FORBIDDEN V1** (Forge time-edits V1+30d; past-clock edits PERMANENTLY forbidden)

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| Forge:EditChannelTimeFlowRate | V1+30d (TDIL-D1) | Q12a static V1 |
| Forge:EditCellTimeFlowRateOverride | V1+30d (TDIL-D11) | Q12c |
| Per-channel `narrative_dilation_phrasing` | V1+30d (TDIL-D2) | Q9d engine default V1 |
| Per-actor `subjective_rate_modifier` (Option B) | V1+30d (TDIL-D3) | Q5c |
| `dilation_target` enum (BodyOnly/SoulOnly/AllClocks) | V1+30d (TDIL-D4) | Q5c V1 lockstep only |
| Soul wandering / soul projection | V1+30d (TDIL-D5) | Q5c |
| Aging integration | V2+ (TDIL-D6) | depends future AGE feature reading body_clock |
| Cross-realm quest deadlines | V2 (TDIL-D7) | depends QST_001 |
| Time travel CTC | V2+ (TDIL-D8) | separate feature design |
| Combat reaction-speed reads body_clock | V1+30d (TDIL-D9) | combat extension |
| Lorentz-aware combat formula | V2+ (TDIL-D10) | DF7-equivalent V2+ |
| Forge:AdvanceChannelClock | V1+30d (TDIL-D2) | Q8d Q12d |
| Forge:GrantActorClockOffset | V1+30d (TDIL-D12) | Q12f |
| Hybrid Both author override | V1+30d (TDIL-D13) | Q6e per-progression-kind |
| Transit cells with own dilation | V1 supported via cell override; richer V1+30d (TDIL-D14) | Q7e |
| Teleport gate reduced cost | V1+ (TDIL-D15) | Q7f |
| RNG materialization seed includes channel | V1+30d (TDIL-D16) | Q10f when PROG-D9 ships |

---

## §2 — i18n Contract Reference

Conforms to RES_001 §2 cross-cutting pattern:
- Stable IDs English `snake_case`: `actor_clocks`, `time_flow_rate`, `time_dilation.rate_out_of_bounds`
- User-facing strings I18nBundle: AssemblePrompt dilation context phrasing (V1 default English-supplied; V1+30d author-customizable per-channel)

---

## §3 — `time_flow_rate` Semantic (Q1+Q2+Q3 LOCKED)

### §3.1 Convention B physics-aligned

**Convention B (LOCKED)**: `time_flow_rate` = proper time per wall time.
- `1.0` = default (mortal-equivalent normal)
- `> 1.0` = proper time runs FASTER than wall time (Dragon Ball time chamber pattern)
- `< 1.0` = proper time runs SLOWER than wall time (Tây Du Ký heaven pattern)

Range V1: `[0.001, 1000.0]` — 3 orders magnitude each direction.

### §3.2 Channel-level + cell-level layering

```rust
// MAP_001 MapLayoutDecl extension (Q2):
pub struct MapLayoutDecl {
    // ... existing per MAP_001 §9 ...
    pub time_flow_rate: f32,                              // V1 default 1.0; range [0.001, 1000.0]
}

// PF_001 PlaceDecl extension (Q2):
pub struct PlaceDecl {
    // ... existing per PF_001 §9 ...
    pub time_flow_rate_override: Option<f32>,             // V1 default None (inherits channel)
}

// Effective rate at cell:
fn effective_time_flow_rate(cell: &Cell) -> f32 {
    cell.time_flow_rate_override
        .unwrap_or(cell.parent_channel.time_flow_rate)
}
```

### §3.3 Override REPLACE semantic

Cell override REPLACES channel rate (not multiplies):
- Heaven channel rate=0.0027 + time chamber cell override=365 → effective = **365** (not 365×0.0027=0.985)
- Author intent: time chamber is a "pocket of own time", not multiplicative modifier
- Multiplicative would cause precision issues + counter-intuitive UX

### §3.4 Default fallback (Q3)

Reality without `time_flow_rate` declarations:
- `effective_time_flow_rate(any_cell) = 1.0` (default)
- ActorClocks still created for all actors; advance per fiction-time × 1.0 = wall-time
- Generators read clocks normally (no special-case logic needed)
- Backwards-compatible — existing realities (PL_001/RES_001/PROG_001 etc.) work unchanged

### §3.5 Player UI examples

```
Phong Vũ Lâu (mortal world)         | Time flow: 1.0× (normal)
Heavenly Palace (heaven realm)      | Time flow: 0.0027× (very slow; 1 heaven-day = 1 mortal-year)
Spirit Time Chamber                 | Time flow: 365× (very fast; train years per day)
Newbie Village (anti-grief)         | Time flow: 0.5× (slow; high-tier visitors waste days)
```

Single rule, direction self-evident from value, intuitive across genres.

---

## §4 — `actor_clocks` Aggregate (Q4 LOCKED)

### §4.1 Aggregate definition

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_clocks", tier = "T2", scope = "reality")]
pub struct ActorClocks {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,
    
    /// Proper time τ — total experiential time integrated over actor existence.
    /// Monotonically increasing. Reset only at canonical seed events.
    /// V1: Forge edits to past values FORBIDDEN (Q10e + Q12e PERMANENTLY).
    pub actor_clock: i64,                                 // fiction-seconds
    
    /// Soul's proper time. BodyOrSoul::Soul progressions read this.
    /// V1 default lockstep with actor_clock. Diverges at xuyên không (Q11a).
    /// V1+30d divergence cases: soul wandering (TDIL-D5).
    pub soul_clock: i64,
    
    /// Body's proper time. BodyOrSoul::Body progressions read this + future aging V2+.
    /// V1 default lockstep with actor_clock. Diverges at xuyên không (Q11b).
    /// V1+30d divergence cases: time chamber DilationTarget (TDIL-D4).
    pub body_clock: i64,
    
    pub last_advanced_at_turn: u64,
    pub schema_version: u32,                              // V1 = 1
}
```

### §4.2 Always-present V1

ActorClocks created at actor creation alongside actor_core (per ACT_001 always-present L1 pattern):
- Canonical NPCs: created at RealityManifest bootstrap (with optional InitialClocksDecl override)
- Runtime-spawned actors: created at EntityBorn cascade
- Untracked NPCs (per AIT_001): ephemeral version in `session.untracked_cache`; promotion crystallizes into persistent aggregate
- PCs: created at PC creation (PCS_001)

### §4.3 InitialClocksDecl extension on CanonicalActorDecl

```rust
pub struct CanonicalActorDecl {
    // ... existing fields per ACT_001 §3.1 + Tier 5 actor substrate ...
    
    /// Optional author override for initial clock values. V1 OPTIONAL.
    /// None = all 3 clocks start at 0.
    /// Some = author-declared initial values (e.g., "this NPC is 200 years old").
    pub initial_clocks: Option<InitialClocksDecl>,
}

pub struct InitialClocksDecl {
    pub actor_clock_initial: i64,                         // for "this NPC has been alive for N years"
    pub soul_clock_initial: i64,                          // typically same as actor unless author wants split
    pub body_clock_initial: i64,                          // typically same as actor; xuyên không exceptions
}
```

Validator at bootstrap: all 3 fields ≥ 0; non-negative invariant.

### §4.4 ACT_001 coordination

ACT_001 (post-DRAFT 2026-04-27) owns 4 actor aggregates:
- `actor_core` (always-present; identity L1)
- `actor_chorus_metadata` (sparse; AI-drive L3)
- `actor_actor_opinion` (sparse bilateral)
- `actor_session_memory` (per-(actor, session))

TDIL_001 adds `actor_clocks` as 5th actor-related aggregate. Naming convention `actor_*` matches ACT_001 family. Always-present (matches actor_core L1 pattern).

ACT_001 closure-pass V1+ may reference TDIL_001 in EVT-T4 ActorBorn cascade for actor_clocks creation.

---

## §5 — Per-Turn Advancement (Q5 LOCKED)

### §5.1 V1 lockstep semantic

```pseudo
on turn_event(actor, cell, fiction_duration):
  let wall_advance = fiction_duration;                          // coordinate time elapsed
  let proper_advance = (wall_advance as f32 * effective_time_flow_rate(cell)) as i64;
  
  actor.clocks.actor_clock += proper_advance;
  actor.clocks.body_clock += proper_advance;     // V1 lockstep
  actor.clocks.soul_clock += proper_advance;     // V1 lockstep
  actor.clocks.last_advanced_at_turn = current_turn;
```

All 3 actor-side clocks advance SAME proper_advance per turn V1.

### §5.2 V1 EXCEPTION: initial value divergence

Initial values may diverge at canonical seed events:

**(a) Author InitialClocksDecl** (§4.3) — author declares per-actor initial clocks:
```rust
CanonicalActorDecl {
    // ... ancient sage NPC ...
    initial_clocks: Some(InitialClocksDecl {
        actor_clock_initial: 200 * fiction_year,     // 200 years old
        soul_clock_initial: 200 * fiction_year,
        body_clock_initial: 200 * fiction_year,
    }),
}
```

**(b) Xuyên không clock-split** (Q11a-c LOCKED) — PCS_001 §S8 mechanic:
- Pre-event: Lý Minh actor=26y/soul=26y/body=26y; Trần Phong actor=20y/soul=20y/body=20y
- Post-event: new combined PC actor=0/soul=26y/body=20y
- Forward: lockstep advancement V1

### §5.3 V1+30d divergence cases

| Case | Mechanism | Deferral |
|---|---|---|
| Soul wandering (出体) | Use::SoulProject; soul_clock advances; body_clock paused | TDIL-D5 V1+30d |
| Time chamber DilationTarget | `cell.dilation_target: Option<DilationTarget>` enum (BodyOnly/SoulOnly/AllClocks) | TDIL-D4 V1+30d |
| Per-actor subjective rate (Option B) | `actor_clocks.subjective_rate_modifier: Option<f32>` | TDIL-D3 V1+30d |
| Aging | body_clock drives biological aging | TDIL-D6 V2+ AGE feature |

---

## §6 — Generator Clock-Source Matrix (Q6 LOCKED)

### §6.1 Matrix

| Generator | Owner | Reads | Why |
|---|---|---|---|
| `Scheduled:CellProduction` | RES_001 | **wall_advance** (channel fiction_clock delta) | Cell production is channel-bound |
| `Scheduled:NPCAutoCollect` | RES_001 | **wall_advance** | Channel-level economic flow |
| `Scheduled:CellMaintenance` | RES_001 | **wall_advance** | Channel-level decay |
| `Scheduled:HungerTick` | RES_001 | **body_clock** proper time | Hunger is body experience |
| `Scheduled:CultivationTick` | PROG_001 | **soul_clock OR body_clock per BodyOrSoul** | Cultivation is actor proper-time |
| AIT_001 materialization | AIT_001 | **soul_clock OR body_clock per BodyOrSoul** | Lazy materialization respects clock semantics |
| Future Aging V2+ | future AGE | **body_clock** proper time | Aging is body experience |

### §6.2 Channel-bound vs actor-bound discipline

- **Channel-bound generators** read `wall_advance` (channel fiction_clock delta) — production / maintenance / autocollect tied to realm time
- **Actor-bound generators** read appropriate actor clock (body_clock OR soul_clock per BodyOrSoul) — consumption / cultivation / aging tied to actor experience

Why: heaven cell with rate=0.0027:
- CellProduction reads wall_advance = 1 mortal-day → cell produces 1 day worth of output (channel rate doesn't slow cell mechanics)
- HungerTick reads body_clock_delta = 0.0027 mortal-day → heaven NPC barely hungry (body proper time slow)

### §6.3 BodyOrSoul::Both resolution

V1: `max(body_clock_delta, soul_clock_delta)` — preserves "either side advancement counts" semantic. V1+30d author override per-progression-kind (TDIL-D13).

### §6.4 Closure-pass coordination

PROG_001 + RES_001 + AIT_001 LOCKED features need closure-pass mechanical revisions in same lock cycle as TDIL_001 DRAFT (this commit):
- **PROG_001 Q3f revision**: "fires on day boundary" → "fires per turn-event with elapsed-time parameter"
- **PROG_001 §10**: ProgressionInstance reads body_clock OR soul_clock per BodyOrSoul (instead of last_observed_at_fiction_ts directly)
- **RES_001 Q4 revision**: "day-boundary tick model" → "per-turn-event tick model"
- **RES_001 §10**: 4 generators per matrix above (3 wall-bound + HungerTick body_clock)
- **AIT_001 §7.5 revision**: per-day replay → O(1) computation

These are **mechanical edits** (no semantic change to user-facing behavior); applied this commit.

---

## §7 — Per-Realm Turn Streams + Atomic Travel (Q7+Q8 LOCKED)

### §7.1 Per-channel turn stream

Per PL_001 fiction_clock per-channel aggregate (existing). Each channel has independent turn stream. Heaven_clock advances ONLY when heaven activity occurs:
- Heaven actor takes turn (NPC/PC action)
- Heaven Tracked Minor scheduled action runs (per AIT_001 MinorBehaviorScript)
- Forge admin time-advance V1+30d (TDIL-D2)

If no heaven activity → heaven_clock frozen while mortal_clock advances. Quantum-observation principle (AIT_001 Q4 REVISED) extends naturally.

### §7.2 Atomic-per-turn travel (Q7)

Actor in EXACTLY ONE channel for entire turn. Travel takes turns; no mid-turn cross-channel.

```
Turn N (in mortal-cell-A): /travel command initiated
Turn N+1..N+K (transit): travel continues
Turn N+K+1 (arrival at heaven-cell-B): location change atomic at turn boundary
Turn N+K+2 (in heaven-cell-B): first heaven turn for this PC
```

Each turn's `fiction_duration` applied to that turn's channel. No interpolation. Travel cost = `MAP_001 distance × travel_defaults.default_fiction_duration` (existing PL_002 mechanism).

V1+30d enrichments: transit cells with own rate (TDIL-D14 — already supported via per-cell override but richer V1+30d); teleport gate with reduced cost (TDIL-D15).

### §7.3 NEW validator TDIL-V1

```pseudo
fn tdil_v1_atomic_travel_validator(turn_event: TurnEvent) -> Option<RejectReason> {
    let starting_cell = turn_event.actor_cell_at_start;
    let ending_cell = turn_event.actor_cell_at_end;
    
    // Same-channel movement OK
    if starting_cell.parent_channel == ending_cell.parent_channel:
        return None;
    
    // Cross-channel must be atomic
    if turn_event.has_mid_turn_channel_cross():
        return Some(reject("time_dilation.mid_turn_channel_cross_forbidden", { ... }));
    
    None
}
```

### §7.4 Cross-realm observation O(1)

Mortal PC observes heaven NPC after heaven_clock advanced N heaven-turns:
```
elapsed_heaven_proper_time = (heaven_clock_now - heaven_clock_at_last_observed) × heaven.time_flow_rate
accrual = base_rate × elapsed_heaven_proper_time × derives_from_multiplier
```

ONE calculation regardless of magnitude. Even 1 trillion heaven-fiction-days = 1 calculation. AIT_001 §7.5 materialization closure-pass revises from per-day replay to O(1) — this commit.

---

## §8 — Xuyên Không Clock-Split Contract (Q11 LOCKED)

### §8.1 PCS_001 §S8 mechanic + TDIL_001 contract

PCS_001 §S8 owns the xuyên không event mechanic. TDIL_001 §8 owns the clock-split rule:

```pseudo
on PcXuyenKhongCompleted event (PCS_001 §S8 mechanic):
  let source_a = event.soul_origin_actor;     // Lý Minh's old actor (modern Saigon)
  let source_b = event.body_origin_actor;     // Trần Phong's old actor (1256 Hàng Châu)
  let new_pc = event.new_pc;                  // new combined PC actor
  
  // Per Q11 LOCKED:
  new_pc.actor_clocks.actor_clock = 0;                               // Q11c — fresh new actor identity
  new_pc.actor_clocks.soul_clock = source_a.actor_clocks.soul_clock; // Q11a — Lý Minh soul brings 26y
  new_pc.actor_clocks.body_clock = source_b.actor_clocks.body_clock; // Q11b — Trần Phong body keeps 20y
  
  // Forward: lockstep advancement (Q11d / Q5a)
  // All 3 advance per current channel time_flow_rate × wall-time per turn
```

### §8.2 Twin paradox preserved

Both clocks remain valid post-event:
- body_clock = 20y (Trần Phong body's accumulated proper time)
- soul_clock = 26y (Lý Minh soul's accumulated proper time)
- LLM narrates: "Your body's hands feel like a 20-year-old's; your mind carries 26 years of memory in modern world; you are simultaneously young man and ancient stranger."

Body-bound progressions (BodyOrSoul::Body) inherited from Trần Phong's actor_progression (martial skills / motor memory).
Soul-bound progressions (BodyOrSoul::Soul) inherited from Lý Minh's actor_progression (academic knowledge / modern context).

### §8.3 Reverse direction

V2+ deferred. Soul leaving body (out-of-body) is V1+30d (TDIL-D5 soul wandering); soul travel BACKWARDS through time = CTC = V2+ separate feature TDIL-D8.

---

## §9 — LLM Context Dilation Awareness (Q9 LOCKED)

### §9.1 Persona section addition

For actor in cell with non-default rate (epsilon 0.01 tolerance):

```rust
fn render_dilation_context(actor: &ActorRef, cell: &Cell) -> Option<I18nBundle> {
    let rate = effective_time_flow_rate(cell);
    if (rate - 1.0).abs() < 0.01 {
        return None;  // default rate; no special context needed
    }
    
    let direction = if rate > 1.0 { "faster than normal" } else { "slower than normal" };
    Some(I18nBundle::en(format!("Time flow in this location: {:.4}× ({})", rate, direction)))
}
```

Token cost: ~30-50 tokens per dilation-aware actor. Bounded by AIT_001 Q12d AssemblePrompt budget.

### §9.2 Budget cap interaction

If AssemblePrompt cap exceeded: drop dilation hint last (preserve persona). LLM falls back to general scene narration without explicit rate.

### §9.3 V1+30d enrichments

- TDIL-D2: per-channel `narrative_dilation_phrasing: I18nBundle` (author override default phrasing)
- TDIL-D3: per-actor subjective time-frame display (high-tier cultivators perceive time slow)
- Cross-realm dialogue tone hints (V1+30d explicit flag)

---

## §10 — Replay Determinism (Q10 LOCKED)

### §10.1 V1 trivially deterministic

| Concern | V1 mechanism | Status |
|---|---|---|
| Channel rate stability | Static RealityManifest declaration; no runtime mutation V1 | ✅ Deterministic |
| Per-channel turn stream | Causally tied to channel actor turn-events | ✅ Causally deterministic |
| Materialization computation | O(1) from inputs; deterministic by math | ✅ Deterministic |
| Cross-channel travel | Atomic-per-turn; one channel per turn | ✅ No interpolation |
| Worldline monotonicity | Forge past-clock edits FORBIDDEN PERMANENTLY | ✅ Locked invariant |

V1 conclusion: **replay determinism is FREE** with static rates + per-channel turn streams + atomic travel + monotonic clocks. No special handling needed.

### §10.2 V1+30d concerns

- Forge:EditChannelTimeFlowRate (TDIL-D1): timestamp-versioned rate lookup pattern
- RNG materialization seed (TDIL-D16): seed includes channel_id + elapsed_in_channel for replay reproducibility when PROG-D9 Random TrainingAmount ships

---

## §11 — RealityManifest Extensions

### §11.1 Fields added by TDIL_001

Per `_boundaries/02_extension_contracts.md` §2:

```rust
RealityManifest {
    // ... existing fields per Continuum / NPC / WA / RES / PROG / IDF / FF / FAC / REP / AIT / ACT ...
    // (TDIL_001 doesn't add new top-level RealityManifest fields)
}

// MAP_001 MapLayoutDecl extension:
pub struct MapLayoutDecl {
    // ... existing per MAP_001 §9 ...
    pub time_flow_rate: f32,                              // V1 default 1.0; range [0.001, 1000.0]
}

// PF_001 PlaceDecl extension:
pub struct PlaceDecl {
    // ... existing per PF_001 §9 ...
    pub time_flow_rate_override: Option<f32>,             // V1 default None
}

// CanonicalActorDecl extension (ACT_001 §3.1):
pub struct CanonicalActorDecl {
    // ... existing ...
    pub initial_clocks: Option<InitialClocksDecl>,        // V1 OPTIONAL author override
}
```

### §11.2 Default values

- Reality without `time_flow_rate` declarations on map_layout: all channels rate=1.0
- Cell without `time_flow_rate_override`: inherits parent channel rate
- CanonicalActorDecl without `initial_clocks`: all 3 clocks start at 0

Backwards-compatible — existing realities work unchanged.

### §11.3 Per-reality opt-in

Authors can omit TDIL fields entirely (sandbox/freeplay realities); TDIL V1 is opt-in per reality.

---

## §12 — Validator Chain

### §12.1 TDIL_001 validator slots

| Slot | Validator | Order |
|---|---|---|
| `TDIL-V1` | `AtomicTravelValidator` | At PL_005 cascade pre-validation (location-change check) |
| `TDIL-V2` | `RateBoundsValidator` | At RealityManifest bootstrap (range [0.001, 1000.0] check) |
| `TDIL-V3` | `InitialClocksValidator` | At RealityManifest bootstrap (non-negative + ≤ MAX_FICTION_TIME check) |
| `TDIL-V4` | `WorldlineMonotonicityValidator` | At Forge AdminAction (V1: REJECT all clock past-edits; V1+30d: timestamp-versioned validation) |

### §12.2 Validator behaviors

**TDIL-V1 AtomicTravelValidator** (Q7g): per §7.3 pseudocode — rejects mid-turn cross-channel.

**TDIL-V2 RateBoundsValidator** (Q1): for each channel + cell rate, asserts in [0.001, 1000.0]; rejects with `time_dilation.rate_out_of_bounds`.

**TDIL-V3 InitialClocksValidator** (§4.3): asserts all 3 clock initial values ≥ 0; rejects with `time_dilation.invalid_initial_clocks`.

**TDIL-V4 WorldlineMonotonicityValidator** (Q10e + Q12e): V1 rejects ALL Forge edits to past clock values; only future advancement via per-turn lockstep allowed; rejects with `time_dilation.past_clock_edit_forbidden`.

---

## §13 — Acceptance Criteria

10 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-TDIL-1 — Default rate = 1.0
- Setup: reality with no time_flow_rate declarations
- Action: bootstrap reality + PC turn
- Expected: effective_time_flow_rate(any_cell) = 1.0; ActorClocks created; per-turn lockstep advancement = wall_advance × 1.0

### AC-TDIL-2 — Channel-level rate
- Setup: heaven channel `time_flow_rate = 0.0027` declared in RealityManifest
- Action: PC enters heaven cell, takes turn fiction_duration=1 day
- Expected: effective_time_flow_rate(heaven_cell) = 0.0027; PC's all 3 clocks advance by 1*0.0027 = 0.0027 days

### AC-TDIL-3 — Cell-level override REPLACES
- Setup: heaven channel rate=0.0027 + time chamber cell override=365
- Action: PC enters time chamber cell
- Expected: effective_time_flow_rate(chamber_cell) = 365 (NOT 0.0027 × 365); 1 day fiction_duration → all 3 clocks +365

### AC-TDIL-4 — Range validation
- Setup: RealityManifest with channel rate=2000 (out of [0.001, 1000.0])
- Action: bootstrap
- Expected: TDIL-V2 rejects with `time_dilation.rate_out_of_bounds`

### AC-TDIL-5 — Per-turn lockstep advancement
- Setup: PC in mortal cell rate=1.0; turn fiction_duration=10 days
- Action: turn ends
- Expected: actor_clock += 10; soul_clock += 10; body_clock += 10; all advanced same amount

### AC-TDIL-6 — Initial value divergence at xuyên không
- Setup: PCS_001 §S8 xuyên không event with source_a (Lý Minh actor=26y/soul=26y/body=26y) + source_b (Trần Phong actor=20y/soul=20y/body=20y)
- Action: PcXuyenKhongCompleted event commits
- Expected: new_pc.actor_clock = 0; new_pc.soul_clock = 26y; new_pc.body_clock = 20y; subsequent turns all advance lockstep

### AC-TDIL-7 — Generator clock-source matrix (channel-bound)
- Setup: heaven cell rate=0.0027; tavern cell with ProducerProfile (5 copper/day); PC enters
- Action: turn fiction_duration=1 mortal-day
- Expected: CellProduction reads wall_advance=1 day; cell produces 5 copper (NOT 5×0.0027=0.0135); heaven cell produces at channel rate not actor rate

### AC-TDIL-8 — Generator clock-source matrix (actor-bound)
- Setup: heaven cell rate=0.0027; PC has Hungry status; turn fiction_duration=1 mortal-day
- Action: HungerTick generator fires
- Expected: HungerTick reads body_clock_delta=0.0027 day; PC body experiences 0.0027 days hunger (long lifespan in heaven feel)

### AC-TDIL-9 — Atomic-per-turn travel rejection
- Setup: turn submits with mid-turn channel cross (mortal_cell → heaven_cell mid-turn)
- Action: turn validation
- Expected: TDIL-V1 rejects with `time_dilation.mid_turn_channel_cross_forbidden`

### AC-TDIL-10 — Cross-realm observation O(1) materialization
- Setup: heaven NPC last_observed_at heaven_clock=0; heaven_clock now=10 turns × heaven rate=0.0027 = 0.027 day proper-time
- Action: mortal PC enters heaven cell after 100 mortal-days; observes heaven NPC
- Expected: 1 calculation: elapsed_heaven_proper = 0.027 day; cultivation accrual = base_rate × 0.027 (not 100 separate per-day events); emit 1 ActorProgressionMaterialized event

---

## §14 — V1 Minimum Delivery Summary

TDIL_001 V1 ships:

| Component | Count |
|---|---|
| New aggregates | 1 (`actor_clocks` always-present per actor) |
| MAP_001 extensions | 1 field (`time_flow_rate`) |
| PF_001 extensions | 1 field (`time_flow_rate_override: Option<f32>`) |
| ACT_001 CanonicalActorDecl extensions | 1 field (`initial_clocks: Option<InitialClocksDecl>`) |
| Validator slots | TDIL-V1..V4 (AtomicTravel + RateBounds + InitialClocks + WorldlineMonotonicity) |
| Rule_ids `time_dilation.*` | 4 V1 + 6 V1+30d reservations |
| Acceptance scenarios | 10 (AC-TDIL-1..10) |
| Deferrals | 16 (TDIL-D1..D16) |

V1 architecture enables:
- ✅ **Multi-realm time** (Tây Du Ký 天上一日人間一年 via channel rate=0.0027)
- ✅ **Time chambers** (Dragon Ball 精神時光屋 via cell override=365)
- ✅ **PvP newbie-gank prevention** (newbie zone rate=0.5 — high-tier wastes time visiting)
- ✅ **Cultivation pace consistency** (per-tier WithinTierCurve + per-channel rate)
- ✅ **Xuyên không clock-split** (soul brings soul_clock; body keeps body_clock; twin paradox preserved)
- ✅ **Per-realm turn streams** (heaven_clock independent from mortal_clock)
- ✅ **Cross-realm observation O(1)** (1 calculation regardless of elapsed magnitude)
- ✅ **Replay determinism FREE** (static rates + per-channel turn streams + atomic travel)

V1 architecture does NOT enable (deferred):
- ❌ Forge runtime mutation of rates (V1+30d TDIL-D1)
- ❌ Per-actor subjective rate Option B (V1+30d TDIL-D3)
- ❌ Per-clock dilation target (BodyOnly/SoulOnly chamber V1+30d TDIL-D4)
- ❌ Soul wandering / projection (V1+30d TDIL-D5)
- ❌ Aging integration (V2+ AGE feature)
- ❌ Time travel CTC (V2+ TDIL-D8)
- ❌ Combat reaction-speed (V1+30d TDIL-D9)

---

## §15 — Deferrals Catalog (TDIL-D1..D16)

**V1+30d (12):**
- TDIL-D1 Forge:EditChannelTimeFlowRate
- TDIL-D2 Per-channel narrative_dilation_phrasing + Forge:AdvanceChannelClock
- TDIL-D3 Per-actor subjective_rate_modifier (Option B)
- TDIL-D4 Time chamber DilationTarget enum (BodyOnly/SoulOnly/AllClocks)
- TDIL-D5 Soul wandering / soul projection
- TDIL-D9 Combat reaction-speed reads body_clock
- TDIL-D11 Forge:EditCellTimeFlowRateOverride
- TDIL-D12 Forge:GrantActorClockOffset
- TDIL-D13 Hybrid Both author override per-progression-kind
- TDIL-D14 Transit cells with own rate (richer V1+30d UX)
- TDIL-D15 Teleport gate reduced cost
- TDIL-D16 RNG materialization seed includes channel_id (when PROG-D9 ships)

**V2 (2):**
- TDIL-D6 Aging integration (depends future AGE feature)
- TDIL-D7 Cross-realm quest deadlines (depends QST_001)

**V2+ (1):**
- TDIL-D8 Time travel CTC (separate feature design)

**V3+ (1):**
- TDIL-D10 Lorentz-aware combat formula (depends DF7-equivalent V2+)

---

## §16 — RejectReason rule_id Catalog

### §16.1 `time_dilation.*` namespace V1

| rule_id | Trigger |
|---|---|
| `time_dilation.rate_out_of_bounds` | TDIL-V2 — channel/cell rate outside [0.001, 1000.0] |
| `time_dilation.invalid_initial_clocks` | TDIL-V3 — InitialClocksDecl negative values |
| `time_dilation.mid_turn_channel_cross_forbidden` | TDIL-V1 — turn ends in different channel from start without atomic travel |
| `time_dilation.past_clock_edit_forbidden` | TDIL-V4 — Forge edit to past clock values; PERMANENTLY forbidden V1+ |

### §16.2 V1+30d reservations

- `time_dilation.subjective_rate_invalid` (TDIL-D3)
- `time_dilation.dilation_target_invalid` (TDIL-D4)
- `time_dilation.soul_already_wandering` (TDIL-D5)
- `time_dilation.actor_clock_offset_invalid` (TDIL-D12)
- `time_dilation.channel_clock_advance_invalid` (TDIL-D2)
- `time_dilation.versioned_rate_lookup_failed` (TDIL-D1)

---

## §17 — Cascade Integration with Other Features

### §17.1 PROG_001 closure pass (this commit)

- Q3f revision: "fires on day boundary" → "fires per turn-event with elapsed-time parameter"
- §10 ProgressionInstance reads body_clock OR soul_clock per BodyOrSoul (instead of last_observed_at_fiction_ts)
- §12 CultivationTick Generator updated per Q6 matrix
- §16 acceptance scenarios re-write per-day → per-turn references

### §17.2 RES_001 closure pass (this commit)

- Q4 revision: "day-boundary tick model" → "per-turn-event tick model"
- §10 4 generators per Q6 matrix (3 wall-bound + HungerTick body_clock)
- §14 acceptance scenarios re-write per-day → per-turn references

### §17.3 AIT_001 closure pass (this commit)

- §7.5 materialization: per-day replay → O(1) computation
- §AC scenarios re-write to reflect O(1) computation

### §17.4 PCS_001 brief §S8 (this commit)

- Add reference to TDIL_001 §8 xuyên không clock-split contract

### §17.5 ACT_001 (no immediate change)

- ActorClocks integrated alongside existing 4 actor-related aggregates
- ACT_001 closure pass V1+ may reference TDIL_001 in EVT-T4 ActorBorn cascade

### §17.6 PL_005 (closure pass V1+)

- TDIL-V1 AtomicTravelValidator slot reference at pre-validation
- V1+ combat reads body_clock for reaction speed (TDIL-D9)

### §17.7 EF_001 (no immediate change)

- entity_binding location change cascade respects atomic-per-turn discipline (existing semantic preserved)

### §17.8 WA_003 Forge

- V1: NO new AdminActions (Q12a static V1)
- V1+30d: 4 new AdminActions (TDIL-D1 + TDIL-D2 + TDIL-D11 + TDIL-D12)

### §17.9 07_event_model

- Generator semantic revision (per-turn O(1)) — PROG/RES/AIT closure pass references
- No new EVT-T sub-types from TDIL_001 V1 (all integration via existing PROG/RES/AIT events)

---

## §18 — Open Questions (Closure Pass)

| ID | Question | Resolution path |
|---|---|---|
| TDIL-Q1 | Per-channel rate hot-path query optimization | Engineering optimization closure (cache effective_time_flow_rate per cell at bootstrap; refresh on Forge V1+30d) |
| TDIL-Q2 | i18n cross-cutting audit | Separate cross-cutting commit post TDIL_001 LOCK |
| TDIL-Q3 | Aging mechanism integration timing | V2+ AGE feature design — TDIL_001 reserves body_clock as input |
| TDIL-Q4 | Cross-realm causal-ref ordering | EVT-A6 causal-ref system handles via channel-local timestamps; V1+30d cross-channel ordering may need explicit rules |
| TDIL-Q5 | Player UI for time-frame display | V1: client renders effective_time_flow_rate in cell info panel; richer V1+30d (subjective time-frame for high-tier actors) |

---

## §19 — Coordination Notes / Downstream Impacts

### §19.1 Co-locked changes in this commit

- ✅ TDIL_001_time_dilation_foundation.md — this DRAFT
- ✅ catalog/cat_17_TDIL_time_dilation.md
- ✅ _boundaries/01_feature_ownership_matrix.md (actor_clocks aggregate + TDIL-* prefix)
- ✅ _boundaries/02_extension_contracts.md §1.4 (`time_dilation.*` namespace) + §2 (MAP_001 + PF_001 + ACT_001 field additions)
- ✅ _boundaries/99_changelog.md
- ✅ 17_time_dilation/_index.md (DRAFT row)
- ✅ 17_time_dilation/00_CONCEPT_NOTES.md (status DRAFT promoted)
- ✅ **Closure-pass mechanical revisions:** PROG_001 + RES_001 + AIT_001 (Q3f / Q4 / §7.5)
- ✅ **PCS_001 brief §S8 update** (reference to TDIL_001 §8 xuyên không clock-split contract)

### §19.2 Deferred follow-up commits

| Feature | Update | Priority |
|---|---|---|
| **MAP_001** | Add `time_flow_rate: f32` field doc (already locked via this commit's RealityManifest extension contract update; MAP_001 design doc closure pass) | LOW |
| **PF_001** | Add `time_flow_rate_override: Option<f32>` field doc (similar) | LOW |
| **ACT_001** | EVT-T4 ActorBorn cascade triggers actor_clocks creation (closure pass V1+) | MEDIUM |
| **PL_005** | TDIL-V1 AtomicTravelValidator slot reference (closure pass V1) | HIGH |
| **WA_003** | V1+30d 4 new AdminActions (TDIL-D1/D2/D11/D12) | LOW (V1+30d) |
| **07_event_model** | Document per-turn O(1) Generator semantic revision (mostly mechanical reference) | MEDIUM |

### §19.3 Future feature coordination

- **Future AGE feature V2+**: reads body_clock for biological aging
- **Future combat closure V1+30d**: PL_005 Strike kind reads body_clock for reaction speed (TDIL-D9)
- **Future CTC time-travel V2+**: separate feature with own consistency rules; TDIL_001 explicitly rejects past-clock edits V1
- **PCS_001 PC Substrate** (parallel agent commission): consumes ActorClocks via §S8 xuyên không mechanic; brief reads TDIL_001 §8

---

## §20 — Status

- **Created:** 2026-04-27 by main session post ACT_001 closure (commit 5/5) + REP_001 closure (4/4)
- **Phase:** DRAFT 2026-04-27
- **Status target:** CANDIDATE-LOCK after Phase 3 review cleanup + closure pass + downstream impacts applied
- **Companion docs:** [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q12 LOCKED matrix)
- **Lock-coordinated commit:** This commit + 6 sibling boundary file updates + 4 mechanical closure-pass revisions on PROG/RES/AIT/PCS_001 brief under single `[boundaries-lock-claim+release]` prefix
