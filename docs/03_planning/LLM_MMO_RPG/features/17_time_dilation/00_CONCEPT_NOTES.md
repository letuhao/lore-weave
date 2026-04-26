# TDIL_001 Time Dilation Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-27 — captures user 4 concerns + 4 architectural insights + Einstein-relativity analysis + 4-clock model + Convention B `time_flow_rate` semantic. Awaits Q-deep-dive batched (mirror PROG_001 / AIT_001 pattern).
>
> **Purpose:** Capture brainstorm + gap analysis + open questions for TDIL_001 Time Dilation Foundation. NOT a design doc; the seed material for the eventual `TDIL_001_time_dilation_foundation.md` design.
>
> **Promotion gate:** When (a) Q1-Q12 LOCKED via deep-dive, (b) `_boundaries/_LOCK.md` is free, (c) PROG_001 + RES_001 + AIT_001 closure-pass revisions ready (turn-boundary Generator semantic) → main session drafts `TDIL_001_time_dilation_foundation.md` in single combined boundary commit.

---

## §1 — User's core framing

### §1.1 4 concerns raised 2026-04-27

User-stated, in original Vietnamese (preserved verbatim):

> "ví dụ cột mốc thời gian trong Tiên Nghịch hoặc Tây Du Ký
> nếu 1 turn (page-flip effect) cho 1 người chơi đều là cố định thì có 1 vấn đề là hệ thống tu luyện không thể hoạt động được
> ví dụ bạn không thể tu tuyện cùng thời gian với 2 người khác cảnh giới được
>
> thần tiên trên trời và phàm nhân dưới đất thuộc 2 thế giới khác nhau có khái niệm thời gian khác nhau
> và ngay cả cùng 1 thế giới thì mỗi người có thời gian trôi qua khác nhau (như câu chuyện phòng tập thời gian trong dragon ball)
>
> nếu chúng ta không giải quyết được điều này thì game tu tiên rất vô lý, ngoài ra nếu giải quyết tốt thì sẽ hạn chế việc mấy người chơi tu vi cao cứ canh ở làng tân thủ đi giết người chơi tu vi thấp"

4 concerns:

1. **Cultivation rate mismatch** — newbie 練氣 cannot share fiction-time clock with 元嬰 elder. Same-rate clock breaks both narratives (newbie too slow OR elder too fast).
2. **Multi-realm time** — Tây Du Ký 天上一日人間一年: heaven channel ≠ mortal channel time-wise. Cross-realm visits feel cosmic.
3. **Time chambers** — Dragon Ball 精神時光屋: 1 day outside = 1 year inside. Cell-level extreme time multiplier.
4. **PvP gank prevention** — high-cultivator camping newbie zone disincentivized via time variance (visiting newbie zone "wastes" their cultivation).

### §1.2 4 architectural insights from deep-dive

User refinements 2026-04-27:

**Insight 1 — Generators fire per-turn O(1), NOT per-day:**

> "if you go to very high realm that time factor bigger than lower realm 1 billion time, you still have only one calculation"
> "in Tây Du Ký, heaven realm have 365 days in one turn, that don't mean you trigger 365 event generating but only 1, and it same at mortal realm, 1 turn 1 event trigger call, 1 trigger call can generate multiple event base on other condition and object that can trigger event"

Translation: 1 turn = 1 generator trigger regardless of fiction-time elapsed. Computation = `base_rate × elapsed_time × multiplier` (O(1)). The trigger may emit 0/1/N events based on conditions, but it's NOT looping per-day.

→ This **invalidates** PROG_001 Q3f + RES_001 Q4 + AIT_001 §7.5 day-boundary Generator semantic. They need closure-pass revision.

**Insight 2 — Atomic-per-turn travel:**

> "don't allow they cross in mid-turn, travel always make time, it don't immediately
> remember we have map distance, they can use teleport gate but it still cost time"

Translation: actor in ONE channel for entire turn. Travel takes turns (governed by MAP_001 distance × default_fiction_duration). Even teleport gate V1+ costs time. No mid-turn cross-channel.

→ Eliminates path-weighted dilation complexity; replay determinism preserved.

**Insight 3 — Per-realm turn streams:**

> "the turn advanced have same at all realm, only different is time factor
> remember our turn advanced define in continuum is event accumulating
> so turn advanced different per realm/world"

Translation: each realm has its OWN turn-advancement clock. Heaven_clock advances ONLY when heaven activity occurs (NPC actions / scheduled Minor routines). If no heaven activity → heaven_clock frozen while mortal_clock advances. PL_001 fiction_clock is per-channel — already supports this.

→ Cross-realm observation reads target channel's clock directly; deterministic.

**Insight 4 — 4-clock model:**

> "to avoid confuse let's add actor clock
> realm have realm's clock
> actor have clock itself
> a soul have soul's clock
> a body have body's clock"

Translation: split clocks into 4 — realm (channel) + actor (total integrated proper time) + soul (BodyOrSoul::Soul progressions) + body (BodyOrSoul::Body progressions + future aging).

→ Generalizes twin paradox (soul + body separable observers). Maps cleanly to Einstein SR/GR + xuyên không state preservation.

### §1.3 Einstein relativity origin

User's intuition:

> "ý tưởng này của tôi đến từ thuyết tương đối trong vật lý của Albert Einstein"

→ TDIL design rooted in physics. Concepts:
- **Proper time τ** (per-observer worldline) ↔ actor_clock
- **Coordinate time t** (chosen reference frame) ↔ realm_clock
- **Time dilation factor** (γ in SR; gravitational potential in GR) ↔ `time_flow_rate`
- **Twin paradox** (worldline divergence + reunion with different proper times) ↔ soul-body separation + reunion
- **Worldline integrity** (proper time monotonic) ↔ actor_clock monotonic V1

Physics analysis confirmed model is sound (see §3 below).

---

## §2 — Reference patterns

### §2.1 Source narratives

| Source | Pattern | LoreWeave applicability |
|---|---|---|
| **Tây Du Ký** | 天上一日人間一年 (heaven 1 day = mortal 1 year) | Heaven channel `time_flow_rate = 0.0027 (1/365)`; gods long-lived from mortal POV |
| **Tiên Nghịch** | Cultivation tier requires centuries proper-time; time-control techniques | Per-actor + per-channel rate; V2+ time-control techniques (PROG-D-equivalent) |
| **Dragon Ball 精神時光屋** | 1 day outside = 1 year inside | Time chamber cell `time_flow_rate = 365`; intense training zone |
| **Naruto** | Genjutsu time-distortion within illusion | V1+ specialized cells (illusion zones); reuse time_flow_rate mechanism |
| **One Piece (Strawhat training timeskip)** | 2-year training off-screen, return upgraded | V1 time-skip via fast-forward command + intentionally-rare high-rate training cells |

### §2.2 Physics analogs

| Einstein concept | LoreWeave 4-clock mapping |
|---|---|
| **Proper time τ along worldline** | actor_clock (per actor) |
| **Coordinate time t in frame** | realm_clock (per channel) |
| **Time dilation γ (SR)** | `time_flow_rate` per channel — proper time per wall time |
| **Gravitational time dilation (GR)** | `time_flow_rate < 1` for "deep gravity well" channels (heaven near "celestial mass" — wuxia narrative interpretation) |
| **Twin paradox (worldline divergence)** | soul vs body separable proper times; xuyên không = max divergence (different bodies; different souls fused) |
| **Worldline monotonicity** | actor_clock / soul_clock / body_clock monotonically increasing |
| **Causal-ordering > simultaneity** | EVT-A6 causal-ref system (already locked); cross-channel events ordered by causation not absolute time |

### §2.3 Game-design references

| Game | Pattern | LoreWeave applicability |
|---|---|---|
| **EVE Online safe zones** | Different rules in different sectors | Channel-level rules (Lex axiom + time_flow_rate) |
| **WoW level brackets** | PvP queue separation by level | Lex axiom tier-locked zones (anti-grief Option E from concern 4) |
| **Skyrim sleep-skipping** | Player skips fiction-time | LoreWeave fast-forward command interacts with channel time_flow_rate |
| **Minecraft beds** | Pass time atomically | Same; resolved via PL_002 sleep command + channel rate |

---

## §3 — Einstein physics analysis (verified sound 2026-04-27)

### §3.1 Map LoreWeave 4-clock to physics

Verified during deep-dive 2026-04-27:

| Clock | Physics analog | Match quality |
|---|---|---|
| Realm clock | Coordinate time t in that frame | ✅ Strong |
| Actor clock | Proper time τ along worldline | ✅ Excellent (canonical) |
| Soul clock | Proper time of "soul" sub-observer | 🔶 Novel (no direct analog; physically plausible as separable logical observer) |
| Body clock | Proper time of "body" sub-observer | 🔶 Novel |
| `time_flow_rate` | Proper time per wall time (Convention B) | ✅ Physics-correct |

### §3.2 Issues surfaced + resolved

| Issue | Resolution |
|---|---|
| Frame absolute vs relative | Pragmatic: declare rate relative to default-reality clock (one chosen frame per reality) |
| Simultaneity | Uses EVT-A6 causal-ref system; cross-channel ordering by causation (GR-aligned) |
| Speed of causation (light cone) | Ignored — game simulation, not physics |
| Gravitational potential analogy | LoreWeave dilation is artistic/narrative; author chooses rate per genre |
| Closed timelike curves (CTC) | V2+ time-travel feature; defer |
| Worldline monotonicity | V1 forbids Forge edits to past clocks; future state edits OK |
| Twin paradox at soul-body reunion | Both clocks preserved; LLM narrates discrepancy |

### §3.3 Convention B locked (`time_flow_rate` = proper time per wall time)

**Heaven (Tây Du Ký)**: `time_flow_rate = 0.0027 (1/365)` — proper time runs slow → gods cultivate slowly per wall-time → appear long-lived from mortal POV.
**Mortal (default)**: `time_flow_rate = 1.0` — proper time = wall time.
**Time chamber (Dragon Ball)**: `time_flow_rate = 365` — proper time runs fast → cultivators gain years per wall-day.

Physics-correct + matches all 5 reference narratives without contradiction.

---

## §4 — `time_flow_rate` semantic (Convention B)

```rust
// MAP_001 channel decl extension:
pub struct MapLayoutDecl {
    // ... existing per MAP_001 ...
    pub time_flow_rate: f32,    // V1 default 1.0; range [0.001, 1000.0]
}

// PF_001 PlaceType cell-level override:
pub struct PlaceDecl {
    // ... existing per PF_001 ...
    pub time_flow_rate_override: Option<f32>,
}

// Effective rate at any cell:
fn effective_time_flow_rate(cell: &Cell) -> f32 {
    cell.time_flow_rate_override
        .unwrap_or(cell.parent_channel.time_flow_rate)
}
```

### §4.1 Per-turn application

```pseudo
on turn_event(actor, cell, fiction_duration):
  let wall_advance = fiction_duration;                          // coordinate time elapsed
  let proper_advance = (wall_advance as f32 * effective_time_flow_rate(cell)) as i64;
  
  actor.clocks.actor_clock += proper_advance;
  actor.clocks.body_clock += proper_advance;     // V1 default lockstep
  actor.clocks.soul_clock += proper_advance;     // V1 default lockstep
  
  // V1+30d: dilation_target enum splits which clocks accrue (BodyOnly / SoulOnly / AllClocks)
```

### §4.2 Player UI examples

```
┌──────────────────────────────────────────────┐
│ Phong Vũ Lâu (mortal world)                  │
│ Time flow: 1.0× (normal)                     │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Heavenly Palace (heaven realm)               │
│ Time flow: 0.0027× (very slow)               │
│ ⚠ Cultivation accrues at heaven pace.        │
│   Mortal world advances 365× faster outside. │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Spirit Time Chamber (Dragon Ball-style)      │
│ Time flow: 365× (very fast)                  │
│ ⚠ Cultivation accrues 365× faster!           │
│   Mortal world only sees 1 day pass outside. │
└──────────────────────────────────────────────┘
```

Single rule, direction self-evident from value, intuitive across genres.

---

## §5 — 4-clock model

### §5.1 ActorClocks aggregate

```rust
// NEW aggregate owned by TDIL_001:
#[derive(Aggregate)]
#[dp(type_name = "actor_clocks", tier = "T2", scope = "reality")]
pub struct ActorClocks {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,
    
    /// Proper time τ — total experiential time integrated over actor existence.
    /// Monotonically increasing. Reset only at canonical seed (V1+ Forge edit forbidden V1).
    pub actor_clock: i64,                                // fiction-seconds (or fiction-days V1)
    
    /// Soul's proper time. Diverges from actor_clock when soul separates from body
    /// (V1+30d soul wandering / xuyên không). V1 default: equal to actor_clock.
    pub soul_clock: i64,
    
    /// Body's proper time. Used for body-bound progressions (BodyOrSoul::Body)
    /// + future aging V2+. V1 default: equal to actor_clock.
    pub body_clock: i64,
    
    pub last_advanced_at_turn: u64,
    pub schema_version: u32,                             // V1 = 1
}
```

### §5.2 Realm clock

Already existing per **PL_001 fiction_clock** aggregate (channel-level). No change V1 — TDIL_001 reads existing fiction_clock per channel.

### §5.3 Generator clock-source matrix

Different generators read different clocks:

| Generator | Reads | Why |
|---|---|---|
| `Scheduled:CellProduction` (RES_001) | **wall_advance** (channel coordinate time) | Production tied to realm time, not actor experience |
| `Scheduled:NPCAutoCollect` (RES_001) | **wall_advance** | Channel-level economic flow |
| `Scheduled:CellMaintenance` (RES_001) | **wall_advance** | Channel-level decay |
| `Scheduled:HungerTick` (RES_001) | **body_clock proper time** | Hunger is body experience |
| `Scheduled:CultivationTick` (PROG_001) | **soul_clock or body_clock per BodyOrSoul** | Cultivation is actor experience |
| Future aging V2+ | **body_clock proper time** | Aging is body experience |
| AIT_001 materialization | **actor_clock + body_clock + soul_clock per relevance** | Tracked NPC observation |

This is a **SIGNIFICANT clarification** of Generator semantics. PROG/RES/AIT closure passes need to specify per-generator clock-source.

### §5.4 Worked example — xuyên không clock-split

Lý Minh's soul transmigrates into Trần Phong's body:

```
Pre-event:
  Lý Minh (in 2026 Saigon, mortal time_flow_rate=1.0):
    actor_clock = 26 years
    soul_clock = 26 years
    body_clock = 26 years (in 2026 Saigon body)
  Trần Phong (in 1256 Hàng Châu, mortal time_flow_rate=1.0):
    actor_clock = 20 years
    soul_clock = 20 years (now lost — soul released)
    body_clock = 20 years

Post-xuyên-không (PCS_001 §S8 mechanic; new combined PC):
  new_pc.actor_clock = 0  (new actor identity starts fresh)
  new_pc.soul_clock = 26  (Lý Minh soul brings its clock)
  new_pc.body_clock = 20  (Trần Phong body keeps its clock)

Forward:
  All 3 clocks advance per current channel time_flow_rate × wall-time
  Body-bound progressions (martial skills, motor memory) inherited from Trần Phong (body_clock=20)
  Soul-bound progressions (academic knowledge, modern context) inherited from Lý Minh (soul_clock=26)
```

LLM narrates: "Your body's hands feel like a 20-year-old's; your mind carries 26 years of memory in modern world; you are simultaneously young man and ancient stranger."

PERFECT match with twin paradox + soul-body model.

---

## §6 — Per-turn O(1) Generator semantic (corrects PROG/RES/AIT)

User correction Insight 1 invalidates PROG_001 + RES_001 + AIT_001 day-boundary Generator semantic. Closure-pass revisions needed.

### §6.1 Old (locked) model — WRONG

```pseudo
// PROG_001 Q3f + §10 + RES_001 Q4 + §10 (LOCKED but wrong):
on day_boundary:
  for each elapsed_day:
    Generator.fire()
    // 30 days = 30 invocations
```

### §6.2 New (revised) model — CORRECT

```pseudo
// Per-turn-event:
on turn_event(actor, cell, fiction_duration):
  let wall_advance = fiction_duration;
  let proper_advance = wall_advance * effective_time_flow_rate(cell);
  
  // Pure-accumulation events — O(1):
  cultivation_accrual = base_rate × proper_advance × derives_from_multiplier;  // 1 calculation
  emit 1 ProgressionDelta with aggregated amount
  
  // State-transition events — at most 1 per turn:
  if at_tier_max && breakthrough_condition_met:
    advance_tier; emit 1 TierAdvance + 1 BreakthroughAdvance
  
  // Discrete-occurrence events — bounded:
  for occurrence in scheduled_within(start, end):  // bounded by author-declared schedule
    emit 1 event per occurrence
    // Often aggregated for high-dilation channels (365 dawns → 1 "365 dawns passed" narrative)
```

### §6.3 Event classification

| Category | Examples | V1 Generator behavior |
|---|---|---|
| **Pure-accumulation** | Cultivation training accrual / cell production / currency / hunger | O(1) calculation; emit 1 aggregated event with computed amount |
| **State-transition** | Tier breakthrough / cap crossing / mortality threshold | Compute post-elapsed state; if changed: emit 1 transition event |
| **Discrete-occurrence** | NPC daily routine / scheduled narrative beats | Enumerate scheduled in elapsed period; emit N events (1 per occurrence); aggregate for high-dilation |

### §6.4 Closure-pass impact

PROG_001 / RES_001 / AIT_001 LOCKED features need:
- Q3f revision: "fires per turn-event with elapsed-time parameter" (NOT "fires on day boundary")
- §10 Generator pseudocode: O(1) computation + per-clock-source resolution
- §AC scenarios: re-write per-day references → per-turn references

These are **mechanical edits** (no semantic change to user-facing behavior); but boundary-coordinated.

---

## §7 — Per-realm turn streams + atomic travel

### §7.1 Per-realm turn streams (already partial in PL_001)

PL_001 fiction_clock aggregate is per-channel. Each channel has independent turn stream. Heaven_clock advances ONLY when heaven activity occurs:
- Heaven NPC takes turn
- Heaven Tracked Minor scheduled action runs
- Forge admin time-advance (V1+30d)

If no heaven activity → heaven_clock frozen while mortal_clock advances. Quantum-observation principle (AIT_001 Q4 REVISED) extends naturally.

### §7.2 Atomic-per-turn travel

User Insight 2: travel always takes time; no mid-turn cross-channel.

```pseudo
Turn N (in mortal-cell-A): /travel to heaven-gate
Turn N+1 (in mortal-cell-A → travel transit cell — 1 mortal-day fiction): travel begins
Turn N+2 (still transit): travel continues
...
Turn N+K (arrival at heaven-cell-B): location change atomic at turn boundary
Turn N+K+1 (in heaven-cell-B): first heaven turn for this PC — heaven_clock advances
```

Each turn in **exactly one channel**. fiction_duration applied to that turn's channel. No interpolation.

V1+30d: teleport gate (still costs time). V2+: instant cross-channel via specialized magical mechanics (separate feature design).

### §7.3 Cross-realm observation O(1)

Mortal PC observes heaven NPC after heaven_clock advanced N heaven-turns:
- elapsed_heaven_proper_time = (heaven_clock_now - heaven_clock_at_last_observed) × heaven.time_flow_rate
- Materialize: `accrual = base_rate × elapsed_heaven_proper_time` (1 calculation)

Even if 1 trillion heaven-fiction-days elapsed: 1 calculation. AIT_001 §7.5 materialization closure-pass revises from per-day replay to O(1).

---

## §8 — LLM context (dilation-aware)

### §8.1 Persona section addition

For actor in cell with non-default `time_flow_rate`:

```
[ACTOR_CONTEXT: Lý Lão]
canonical_traits: { ... }
desires: { ... }
progression: { qi_cultivation: 元嬰中期 }

# NEW dilation context (~30-50 tokens):
channel: heaven_cell_immortal_palace (time flow 0.0027× / very slow)
subjective_time_frame: 元嬰 stage cultivated for ~1500 heaven-years (~547500 mortal-years equivalent)
```

Cost: ~30-50 tokens per dilation-aware actor. Bounded by AIT_001 Q12d AssemblePrompt budget.

### §8.2 V1 mechanism

```rust
fn render_dilation_context(actor: &ActorRef, cell: &Cell) -> Option<I18nBundle> {
    let rate = effective_time_flow_rate(cell);
    if (rate - 1.0).abs() < 0.01 {
        return None;  // default rate; no special context needed
    }
    
    Some(I18nBundle::en(format!(
        "Time flow in this location: {}× ({})",
        rate,
        if rate > 1.0 { "faster than normal" } else { "slower than normal" }
    )))
}
```

V1+30d enrichment (TDIL-D-equivalent):
- Per-channel `narrative_dilation_phrasing: I18nBundle` (author override)
- Per-actor subjective age display (body + soul age)
- Cross-realm dialogue tone hints

### §8.3 5 LLM challenges (V1 vs V1+)

| Challenge | V1 mechanism | V1+ enrichment |
|---|---|---|
| Subjective vs wall-clock | AssemblePrompt rate context | Per-channel narrative_dilation_phrasing |
| Cross-realm dialogue tone | LLM trusted with rate context | Explicit dialogue_register_dilation_aware flag |
| Aging mechanics | NOT V1 | V2+ AGE feature reads body_clock |
| Memory references | LLM trusted with subjective time-frame | Explicit memory-time-frame hints |
| Quest deadlines cross-realm | NOT V1 | V2 QST_001 closure |

---

## §9 — Replay determinism

### §9.1 V1 trivially deterministic

| Concern | V1 mechanism | Determinism status |
|---|---|---|
| Channel rate stability | Static RealityManifest declaration | ✅ Trivially deterministic V1 |
| Per-channel turn stream | heaven_clock advances only on heaven activity | ✅ Causally deterministic |
| Materialization seed | blake3 includes channel_id + elapsed_in_channel | ✅ V1 N/A (no RNG); V1+30d when shipped |
| Cross-channel travel | Atomic per turn; one channel per turn | ✅ No interpolation |

V1 conclusion: **replay determinism is FREE** with static rates + per-channel turn streams. No special handling needed.

### §9.2 V1+30d concerns

- Forge:EditChannelTimeFlowRate: requires timestamp-versioned rate lookup (TDIL-D-equivalent)
- RNG materialization seed (PROG-D9 Random TrainingAmount): seed includes channel_id

---

## §10 — Boundary intersection table

| Touched feature | TDIL_001 contribution | Closure-pass revision needed? |
|---|---|---|
| **PL_001 Continuum** | fiction_clock per-channel (existing) — no change | No |
| **MAP_001 Map Foundation** | NEW field `time_flow_rate: f32` on MapLayoutDecl (channel-level) | YES at TDIL DRAFT |
| **PF_001 Place Foundation** | NEW field `time_flow_rate_override: Option<f32>` on PlaceDecl (cell-level) | YES at TDIL DRAFT |
| **PROG_001** | Q3f day-boundary → turn-boundary; §10 Generator pseudocode revision; ProgressionInstance reads body_clock OR soul_clock per BodyOrSoul; §16 acceptance scenarios re-write | **YES — MAJOR closure pass** |
| **RES_001** | Q4 day-boundary → turn-boundary; 4 Generators revised (CellProduction/NPCAutoCollect: wall_advance; CellMaintenance: wall_advance; HungerTick: body_clock); §14 acceptance scenarios re-write | **YES — MAJOR closure pass** |
| **AIT_001** | §7.5 materialization O(1) instead of per-day replay; §AC scenarios re-write | **YES — closure pass** |
| **EF_001** | entity_binding location change cascade triggers ActorClocks-aware effective_time_flow_rate computation | YES at TDIL DRAFT |
| **NPC_001** | Persona assembly may include subjective time-frame for high-tier NPCs | LOW priority closure |
| **PL_005** | V1+ combat reads body_clock for reaction speed | V1+ DEFER |
| **WA_001 Lex** | Lex axiom for tier-locked zones (anti-grief Option E) | LOW priority closure (may already support via existing Lex axiom mechanism) |
| **WA_006 Mortality** | V2+ aging reads body_clock | V2+ DEFER |
| **PCS_001 brief** | §S8 xuyên không mechanic clock-split semantics (soul brings soul_clock; body keeps body_clock) | YES at PCS DRAFT |
| **07_event_model** | Generator semantic revision (per-turn O(1) instead of per-day) | YES at next event-model agent pass |

---

## §11 — Q1-Q12 critical scope questions

| Q | Topic |
|---|---|
| Q1 | `time_flow_rate` value range V1 — recommend [0.001, 1000.0] (3 orders magnitude each direction) |
| Q2 | Channel-level vs cell-level rate — recommend both (channel default; cell override optional) |
| Q3 | Default rate fallback — recommend 1.0 (no time dilation) if reality doesn't declare |
| Q4 | ActorClocks aggregate location — NEW aggregate vs PROG_001 extension — recommend NEW (Option B physics-aligned) |
| Q5 | V1 lockstep vs V1 divergence — recommend V1 lockstep (all 3 actor-side clocks advance same); divergence V1+30d |
| Q6 | Generator clock-source matrix — locked per §5.3 |
| Q7 | Cross-channel travel atomic — locked per §7.2 |
| Q8 | Per-realm turn stream advancement triggers — heaven_clock advances on heaven activity only — locked per §7.1 |
| Q9 | LLM context dilation token budget — recommend ~30-50 tokens per dilation-aware actor |
| Q10 | Replay determinism — locked V1 free per §9.1 |
| Q11 | xuyên không clock-split semantic — locked per §5.4 (soul brings soul_clock; body keeps body_clock) |
| Q12 | Forge:EditChannelTimeFlowRate runtime mutation — recommend V1+30d (TDIL-D-equivalent); V1 static only |

---

## §12 — V1 minimum scope sketch

If Q1-Q12 LOCKED with above recommendations:

**V1 ships:**
- 1 NEW aggregate `actor_clocks` (T2/Reality, owner=Actor) with 3 clocks (actor + soul + body)
- `time_flow_rate: f32` field on MAP_001 MapLayoutDecl (channel-level)
- `time_flow_rate_override: Option<f32>` field on PF_001 PlaceDecl (cell-level)
- `effective_time_flow_rate(cell)` helper
- Per-turn ActorClocks advancement (V1 lockstep)
- Generator clock-source matrix (per §5.3) — guides PROG/RES/AIT closure passes
- AssemblePrompt persona dilation context (~30-50 tokens per non-default actor)
- 2 V1 rule_ids (`time_dilation.rate_out_of_bounds` / `time_dilation.invalid_override`)
- TDIL-* stable-ID prefix
- 8-10 V1-testable acceptance scenarios AC-TDIL-1..N

**V1 NOT shipping (deferred):**
- TDIL-D1: Forge:EditChannelTimeFlowRate (V1+30d) — runtime rate edit
- TDIL-D2: Per-channel narrative_dilation_phrasing (V1+30d)
- TDIL-D3: Per-actor subjective rate Option B (V1+30d)
- TDIL-D4: Time chamber DilationTarget enum (V1+30d) — BodyOnly/SoulOnly/AllClocks
- TDIL-D5: Soul wandering / soul projection (V1+30d) — soul_clock advances; body_clock paused
- TDIL-D6: Aging integration V2+ (depends future AGE feature)
- TDIL-D7: Cross-realm quest deadlines V2 (depends QST_001)
- TDIL-D8: Time travel CTC V2+ (specialized feature)
- TDIL-D9: Combat reaction-speed reads body_clock V1+30d
- TDIL-D10: Lorentz-aware combat formula V2+

**V1 size estimate:** ~500-700 lines DRAFT (smaller than RES_001 / PROG_001 / AIT_001).

---

## §13 — Reference materials placeholder

User stated 2026-04-27 (during AIT_001 closure window):

> "đây là vấn đề rất lớn; cần discipline concept-notes-first để tránh design drift như đã thấy ở PROG Q4 original"

User may provide additional reference materials:
- Tiên Nghịch novel time mechanics
- Tây Du Ký classical structure
- Dragon Ball training arcs
- Einstein relativity formulas (already covered §3)
- EVE Online safe-zone mechanics
- WoW level-bracket PvP queues

When references arrive:
1. Capture verbatim (preserve user's preferred terminology)
2. Cross-reference with this concept-notes
3. Update §11 Q1-Q12 recommendations based on combined references
4. Lock LOCKED decisions in new §14 section at promotion time

---

## §14 — What this concept-notes file is NOT

- ❌ NOT the formal TDIL_001 design (no full §1-§N section structure; no acceptance criteria; no Rust struct field names finalized)
- ❌ NOT a lock-claim trigger (no `_boundaries/_LOCK.md` claim made for this notes file)
- ❌ NOT registered in ownership matrix yet (deferred to TDIL_001 DRAFT promotion)
- ❌ NOT consumed by other features yet (PROG/RES/AIT closure-pass revisions queued but not committed)
- ❌ NOT prematurely V1-scope-locked (Q1-Q12 OPEN; recommendations pending deep-dive)

---

## §15 — Promotion checklist (when Q1-Q12 answered)

Before drafting `TDIL_001_time_dilation_foundation.md`:

1. [ ] User answers Q1-Q12 (or approves recommendations after deep-dive batches)
2. [ ] Update §12 V1 scope based on locked decisions
3. [ ] Coordinate with PROG_001 + RES_001 + AIT_001 closure-pass revisions (boundary-coordinated single commit)
4. [ ] Wait for `_boundaries/_LOCK.md` to be free
5. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL minimum; 6-8 hours expected for combined revision)
6. [ ] Create `TDIL_001_time_dilation_foundation.md` with full §1-§N spec
7. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — register `actor_clocks` aggregate + TDIL-* stable-ID prefix
8. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `time_dilation.*` RejectReason prefix
9. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add MAP_001 + PF_001 RealityManifest extension fields
10. [ ] Update `_boundaries/99_changelog.md` — append entry
11. [ ] Create `catalog/cat_17_TDIL_time_dilation.md` — feature catalog
12. [ ] Update `17_time_dilation/_index.md` — replace concept row with TDIL_001 DRAFT row
13. [ ] **Closure-pass revisions in same commit (mechanical):**
    - PROG_001: Q3f revision (turn-boundary) + §10 + §12 + §16 acceptance scenarios
    - RES_001: Q4 revision + §10 + §14 acceptance scenarios
    - AIT_001: §7.5 materialization O(1) + §AC scenarios
14. [ ] Coordinate with PCS_001 brief §S8 (xuyên không clock-split addition)
15. [ ] 07_event_model agent registration of revised Generator semantic (per-turn O(1))
16. [ ] Update `features/_index.md` to add `17_time_dilation/` to layout + table
17. [ ] Release `_boundaries/_LOCK.md`
18. [ ] Commit with `[boundaries-lock-claim+release]` prefix (single combined commit OR multi-commit cycle if too large)

---

## §16 — Status

- **Created:** 2026-04-27 by main session post AIT_001 DRAFT closure (commit `88404f0`) — during REP_001 lock-held window (concept phase doesn't need lock)
- **Phase:** CONCEPT — awaiting Q1-Q12 deep-dive
- **Lock state:** `_boundaries/_LOCK.md` held by REP_001 work (commit 2/4 cycle). TDIL_001 DRAFT promotion blocked until lock free.
- **Estimated time to DRAFT (post-Q-deep-dive + closure-pass coordination):** 6-8 hours combined work (smaller TDIL_001 spec ~500-700 lines + PROG/RES/AIT closure-pass mechanical revisions)
- **Dependencies (when DRAFT):**
  - PROG_001 closure pass (Q3f day-boundary → turn-boundary; §10 + §12 + §16 revision)
  - RES_001 closure pass (Q4 day-boundary → turn-boundary; §10 + §14 revision)
  - AIT_001 closure pass (§7.5 materialization O(1); §AC revision)
  - PCS_001 brief §S8 update (xuyên không clock-split semantics)
  - 07_event_model agent registers revised Generator semantic
  - MAP_001 + PF_001 RealityManifest extension fields
- **Next action:** User decides Q-deep-dive batching strategy (mirror PROG/AIT pattern OR alternative)

---

## §17 — Q-batching proposal

Recommend mirror PROG_001 6-batch / AIT_001 4-batch pattern. Possible batches:

| Batch | Q's | Topic |
|---|---|---|
| **Batch 1** | Q1+Q2+Q3 | `time_flow_rate` semantic + value range + channel/cell layering + default fallback |
| **Batch 2** | Q4+Q5 | ActorClocks aggregate location + V1 lockstep vs divergence |
| **Batch 3** | Q6+Q7+Q8 | Generator clock-source matrix + atomic travel + per-realm turn streams (mostly already locked from §5/§6/§7) |
| **Batch 4** | Q9+Q10+Q11+Q12 | LLM context budget + replay determinism + xuyên không clock-split + Forge runtime mutation |

Most decisions already converged via concept-notes prior discussion. Q-deep-dive may complete in 2-3 quick batches with mostly approve-recommendation responses.
