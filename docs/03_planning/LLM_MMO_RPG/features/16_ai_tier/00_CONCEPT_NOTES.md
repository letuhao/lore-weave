# AIT_001 AI Tier Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — captures user 3-tier framing + 10+ open questions. Awaits user direction on Q-deep-dive batching (mirror PROG_001 / RES_001 6-batch pattern).
>
> **Purpose:** Capture the brainstorm + gap analysis + open questions for AIT_001 AI Tier Foundation. NOT a design doc; the seed material for the eventual `AIT_001_ai_tier_foundation.md` design.
>
> **Promotion gate:** When (a) Q1-QN are locked via deep-dive discussions, (b) `_boundaries/_LOCK.md` is free → main session drafts `AIT_001_ai_tier_foundation.md` with locked V1 scope.

---

## §1 — User's core framing (2026-04-26)

User-stated, in original Vietnamese (preserved verbatim for fidelity):

1. **Chúng ta sẽ có kiến trúc phân tầng AI mà chúng ta chưa design, sẽ có design sau progression system.** — AI tier architecture pending design (post-PROG_001).

2. **1 thế giới rộng lớn với hàng tỷ NPC, làm sao mô phỏng?** — How to simulate a vast world with billions of NPCs? (Scaling problem statement.)

3. **Chúng ta sẽ chia NPC ra thành nhiều cấp độ tồn tại, được track và không được track.** — NPCs split into multiple existence tiers — tracked vs untracked.

4. **Generate ngẫu nhiên rồi biến mất theo session HOẶC major NPC được track với số lượng rất hạn chế và cực kỳ thông minh.** — Random generation then disappear by session, OR major tracked NPCs with very limited count and very intelligent behavior.

5. **Có rule based action bao gồm training process VÀ có loại LLM tự điều khiển hành vi giống như 1 PC.** — Has rule-based action including training process AND a subtype with LLM-driven behavior matching PC.

6. **Dữ liệu của NPC chỉ được cập nhật khi có quan sát bới PC/event/LLM (giống khái niệm trong lý thuyết lượng tử).** — NPC data only updates when observed by PC/event/LLM (Schrödinger principle).

### Implicit corollaries (from user framing)

- **C1.** At least 3 NPC tiers (PCs are separate concern):
  - **Tracked-LLM (Major)**: limited count + LLM-driven behavior + matches PC capabilities
  - **Tracked-Rule (Minor)**: rule-based scripted actions including training
  - **Untracked (Background)**: ephemeral; LLM/RNG-generated per session; discarded

- **C2.** Quantum-observation principle (already locked in PROG_001 Q4 REVISED) extends to ALL NPC dynamic state, not just progression. RES_001 NPC eager auto-collect Generator V1 is architecturally inconsistent — V1+30d migration tracked as PROG-D19.

- **C3.** "Major" tier is intentionally **limited count** to bound storage + LLM context. Likely cap per-reality (e.g., 100 Major / 500 Minor / unlimited Untracked).

- **C4.** Untracked NPC generation is **on-demand** (when PC enters cell needing scene populated). Determinism per EVT-A9 critical for replay.

- **C5.** Behavior model is **per-tier closed-set**:
  - PC: full agency (player or LLM if abandoned-PC)
  - Tracked-LLM: full agency (LLM acts as PC)
  - Tracked-Rule: deterministic scripts (no LLM dialogue generation; pre-canned reactions)
  - Untracked: narrative-only (LLM mentions them; they don't write events themselves)

---

## §2 — Reference patterns

| Game | Pattern | LoreWeave applicability |
|---|---|---|
| **Stellaris** | Pops vs named characters — pops are nameless aggregates with stats; named characters have full agency | Stellaris pops ≈ Untracked NPCs; named ≈ Tracked |
| **Crusader Kings 3** | Living characters age in background but only "decide" when on-screen or relevant | Background-aging matches Untracked LLM regen; on-screen decisions match Tracked observation triggers |
| **Skyrim** | Distance culling — NPCs at far distance frozen; persistent NPCs (shopkeepers / quest-givers) always tracked | Tracked NPCs have persistent state; Untracked culled when out of scene |
| **Mount & Blade Bannerlord** | Lord NPCs (Tracked) vs town pops (untracked aggregates) | Mirrors LoreWeave's split |
| **Dwarf Fortress** | Legends mode — historical figures fully simulated; current actors tracked individually | Legendary NPCs may have own tier (Major beyond Major V2+) |
| **Patrician IV** | Player + competitors tracked; pops aggregate per city | Same pattern |
| **Frostpunk** | Citizen counts vs named characters (engineers / officials) | Same |
| **The Sims** | All sims fully simulated (no Untracked equivalent) — opposite extreme; LoreWeave can't afford this at billion scale | Anti-pattern reference |

→ All major sim/strategy games solve scaling via tier-based existence. LoreWeave's 3-tier (PC/Tracked-Major/Tracked-Minor/Untracked) is consistent with industry pattern.

---

## §3 — Tier ontology (open question Q1)

User's framing implies at least 3 NPC tiers. Concrete ontology candidates:

### Option A — 2 tiers (minimal)
```rust
pub enum NpcTrackingTier {
    Tracked,    // ActorProgression aggregate stored; lazy materialization on observation
    Untracked,  // No aggregate; LLM/RNG-generated per session; discarded after observation window
}
```
Pros: simplest. Cons: doesn't distinguish LLM-driven vs rule-based Tracked NPCs (user's C1).

### Option B — 3 tiers (matches user framing)
```rust
pub enum NpcTrackingTier {
    Major,      // Tracked-LLM — full agency; LLM-driven behavior; behaves like PC
    Minor,      // Tracked-Rule — scripted actions; deterministic; including training
    Untracked,  // No aggregate; ephemeral generation
}
```
Pros: matches user's C1. Cons: V1 may not need Minor (just Major + Untracked might suffice).

### Option C — 4+ tiers (V2+ richer)
Add `Legendary` (historical figures fully simulated even longer) or `Faction` (collective entity tier) etc. V1 overengineering.

### Recommendation
**Option B (3 tiers)** for V1; matches user's explicit framing. V1+ may add `Legendary` etc.

---

## §4 — Tier assignment rules (open question Q2)

How is an NPC's tier determined?

### Option A — Author-declared in RealityManifest
Each canonical_actor in RealityManifest declares `tracking_tier: NpcTrackingTier`. Authors explicitly mark major NPCs.

### Option B — Auto-assigned by significance heuristic
Engine computes significance (PC-interaction count / quest-relevance / dynasty membership / etc.) and assigns tier. Untracked default; promote when threshold reached.

### Option C — Hybrid
- Author declares initial tier for canonical_actors
- Engine auto-promotes Untracked → Major based on significance
- Author Forge can manually override

### Recommendation
**Option C hybrid** for richness. Authors control major NPCs; engine handles emergent promotion of background NPCs that gain narrative significance.

---

## §5 — Untracked NPC generation (open question Q4-Q5)

### Q4 Generation mechanism
- (a) **Pure LLM**: LLM proposes persona + name + stats + appearance. Risk: token cost; non-determinism.
- (b) **Template-based**: Author declares Untracked templates per cell type ("villager template" with name pool + stat ranges). Engine instantiates with seeded RNG.
- (c) **Hybrid**: Template provides skeleton; LLM fills in flavor (specific name choice, dialogue style).

### Q5 When generated
- (a) **On cell entry**: PC enters cell → engine generates Untracked NPCs to populate scene per cell-density profile
- (b) **On-demand**: Untracked generated only when PC interacts with "the bartender" reference; otherwise cell scene shows aggregate ("crowd of patrons")
- (c) **At RealityManifest bootstrap**: All untracked pre-generated (defeats ephemeral concept)

### Recommendation
**Q4 = Option (c) hybrid** + **Q5 = Option (a) on cell entry** with deterministic seed (per `blake3(reality_id || cell_id || fiction_day)`) for replay determinism per EVT-A9.

---

## §6 — Discard policies (open question Q6)

When do Untracked NPCs disappear?

### Option A — Cell-leave
PC leaves cell → all Untracked NPCs in that cell discarded immediately

### Option B — Session-end
Untracked NPCs persist throughout session; discarded only when session ends (PC logs off / sleep major)

### Option C — Time-based
Discard after N fiction-days no-observation (per quantum-observation principle)

### Option D — Hybrid
- Cell-leave: discard if PC left cell within session AND no causal-ref pinning Untracked (no quest mention / no event referencing)
- Session-end: discard all remaining Untracked
- Promotion saves: if Untracked got promoted to Tracked during session, persist as Tracked (skip discard)

### Recommendation
**Option D hybrid** — preserves Untracked while session active for narrative continuity (PC may return to cell within session and see same Untracked NPCs); discards on session end + cell-leave-without-pin.

---

## §7 — Behavior models per tier (open question Q7)

Per user's C5 implicit corollary:

| Tier | Action capability | LLM presence | Determinism |
|---|---|---|---|
| **PC** | Full PL_005 InteractionKind range | Player or fallback LLM | N/A (player choice) |
| **Tracked-Major (LLM-driven)** | Full PL_005 InteractionKind range | LLM proposes actions per NPC_002 Chorus | LLM-driven non-deterministic V1; deterministic-replay V1+ |
| **Tracked-Minor (rule-based)** | Scripted limited subset (training tick + scheduled routines + pre-canned reactions) | NO LLM presence in dialogue (canned responses); LLM still narrates outcome | Fully deterministic V1 |
| **Untracked** | Narrative-only mention (LLM references them in scene description); cannot write events | LLM presence only at cell-scene narration | Deterministic via seeded generation |

### Q7 Boundary V1
Should engine treat Tracked-Major and Tracked-Minor as fundamentally different tiers, OR as same tier with `behavior_mode: enum { LlmDriven, RuleBased }` field?

Recommendation: same `Tracked` tier with `behavior_mode` discriminator. Cleaner than 4 tiers.

→ Revised Q1: Option B' — 2 enum variants but Tracked has internal sub-discriminator:
```rust
pub enum NpcTrackingTier {
    Tracked { behavior_mode: BehaviorMode },
    Untracked,
}

pub enum BehaviorMode {
    LlmDriven,    // Major; full agency
    RuleBased,    // Minor; scripted
}
```

Or simpler: 3-variant enum keeping Major/Minor/Untracked + BehaviorMode collapsed.

---

## §8 — Storage model per tier

| Tier | ActorProgression aggregate? | resource_inventory? | npc core (R8 import)? |
|---|---|---|---|
| PC | ✅ eager | ✅ eager | n/a (PCs not in NPC core) |
| Tracked-Major | ✅ lazy materialization (per PROG_001 Q4) | ✅ lazy V1+30d (PROG-D19) | ✅ stored |
| Tracked-Minor | ✅ lazy materialization | ✅ lazy V1+30d | ✅ stored |
| Untracked | ❌ no aggregate | ❌ no inventory storage | ❌ no NPC core; ephemeral cache only |

V1 Untracked has NO persistent storage. Ephemeral cache only (in-memory; cleared on cell-leave + session-end per Q6).

---

## §9 — Tier transitions (open question Q3)

Promotion (Untracked → Tracked):
- (a) **Author Forge admin action** — explicit
- (b) **Significance threshold** — auto-promote when PC interactions count ≥ N
- (c) **LLM proposes promotion** — LLM detects narrative significance ("this NPC's name appeared in 3 turns")
- (d) **Hybrid all-of-above**

V1: probably (a) + (b) with simple threshold (PC named the Untracked NPC explicitly OR PC exchanged > N tokens dialogue).

Demotion (Tracked → Untracked):
- (a) **Disabled V1** (Tracked is permanent)
- (b) **Author Forge admin action** — explicit
- (c) **Auto-demote** when Tracked NPC has no PC observation for N fiction-years (very aggressive)

V1: (a) disabled. Tracked is permanent V1; demotion V1+30d.

---

## §10 — Boundary intersection table

| Touched feature | AIT_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|
| **PROG_001** | NpcTrackingTier enum + tier semantics + Untracked-no-aggregate clean default | `actor_progression` aggregate; `tracking_tier: Option<NpcTrackingTier>` field | AIT_001 populates tracking_tier; PROG_001 reads it for eager/lazy decision |
| **NPC_001** | Tier-aware NpcId scoping (Untracked NpcId may have shorter lifetime) | NpcId base type + npc core aggregate | NPC_001 npc aggregate only stored for Tracked tiers |
| **NPC_002 Chorus** | Tier filter for chorus participation (Tracked-Rule may opt-out of chorus) | Multi-NPC turn ordering | Chorus reads tracking_tier to decide priority |
| **RES_001** | (none — but flags PROG-D19 alignment) | resource_inventory + Generators | V1 RES_001 eager NPC auto-collect inconsistent; V1+30d closure pass migrates to lazy |
| **PL_005** | Tier-aware action availability (Untracked narrative-only; Tracked-Rule scripted-only) | InteractionKind + cascade | PL_005 closure pass adds tier check on action initiation |
| **PL_001 Continuum** | scene_state membership reflects tier (Untracked as ephemeral participants) | scene_state aggregate | PL_001 reads tier for scene roster rendering |
| **CSC_001 Cell Scene** | Procedural Untracked generation per cell per Q4-Q5 | cell_scene_layout + Layer 3 LLM categorical | CSC_001 §6 Layer 3 may receive Untracked NPCs from AIT_001 generation |
| **WA_003 Forge** | NEW AdminActions: `Forge:PromoteToTracked` / `Forge:DemoteToUntracked` (V1+30d) | ForgeEditAction enum | WA closure folds in |
| **EVT-T3 Derived** | NEW sub-shape: `TrackingTierTransition` | Event taxonomy | Cascade-trigger for downstream consumers |
| **EVT-T5 Generated** | NEW sub-type: `Generated:UntrackedNpcSpawn` (deterministic per cell entry) | Event taxonomy | EVT-G2 trigger source CellEntry V1+ |
| **RealityManifest** | NEW fields: tier_density_per_place_type / untracked_template_registry / tier_promotion_thresholds | Envelope contract | Per `_boundaries/02_extension_contracts.md` §2 |

---

## §11 — Q1-Q12 critical scope questions (OPEN)

| Q | Topic |
|---|---|
| Q1 | Tier enum closed set V1 (2 / 3 / 4+ variants) — recommend 3 (Major/Minor/Untracked) OR (Tracked{behavior_mode}, Untracked) |
| Q2 | Tier assignment rules V1 (author-declared / auto-significance / hybrid) — recommend hybrid |
| Q3 | Promotion mechanism V1 (Forge / threshold / LLM-propose / hybrid) — recommend Forge + threshold V1; demotion V1+30d |
| Q4 | Untracked generation V1 (pure LLM / template / hybrid) — recommend hybrid (template skeleton + LLM flavor) |
| Q5 | Untracked generation timing V1 (cell-entry / on-demand / bootstrap) — recommend cell-entry with deterministic seed |
| Q6 | Discard policy V1 (cell-leave / session-end / time-based / hybrid) — recommend hybrid (cell-leave + session-end) |
| Q7 | Behavior model V1 (Major LLM-driven; Minor rule-based; Untracked narrative-only) — recommend per-tier closed-set |
| Q8 | Per-cell-type Untracked density V1 (author-declared per PlaceType) — recommend YES; e.g., tavern: 1-3 patrons + 1 server |
| Q9 | Action availability per tier (PL_005 InteractionKind subset per tier) — recommend Tracked-LLM full / Tracked-Rule scripted-only / Untracked narrative-only |
| Q10 | Replay determinism for Untracked (deterministic seed required by EVT-A9) — recommend YES blake3(reality_id || cell_id || fiction_day) |
| Q11 | Untracked promotion preserves identity? (when promoted, NpcId stable; persona crystallized into NPC core aggregate) — recommend YES |
| Q12 | Tier-aware AssemblePrompt budget (Tracked-LLM gets full persona; Untracked gets summary line only) — recommend YES; LLM context cost critical for scale |

---

## §12 — Provisional V1 scope (placeholder — finalized after Q-lock)

This section INTENTIONALLY EMPTY pending Q1-Q12 deep-dive. Premature V1 scope locking risks issues seen in PROG_001 Q4 original design (corrected via REVISED quantum-observation).

---

## §13 — What this concept-notes file is NOT

- ❌ NOT the formal AIT_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger (no `_boundaries/_LOCK.md` claim made for this notes file)
- ❌ NOT registered in ownership matrix yet (deferred to AIT_001 DRAFT promotion)
- ❌ NOT consumed by other features yet (PROG_001 `tracking_tier` field is `Option<NpcTrackingTier>` with `None` V1 default; AIT_001 DRAFT activates the enum)
- ❌ NOT prematurely V1-scope-locked (Q1-Q12 OPEN; recommendations pending deep-dive)

---

## §14 — Promotion checklist (when Q1-Q12 answered)

Before drafting `AIT_001_ai_tier_foundation.md`:

1. [ ] User answers Q1-Q12 (or approves recommendations after deep-dive batches)
2. [ ] Update §12 V1 scope based on locked decisions
3. [ ] Wait for `_boundaries/_LOCK.md` to be free
4. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
5. [ ] Create `AIT_001_ai_tier_foundation.md` with full §1-§N spec
6. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — register `NpcTrackingTier` enum ownership + any new aggregates + AIT-* stable-ID prefix
7. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `ai_tier.*` RejectReason prefix
8. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest extensions (tier_density_per_place_type / untracked_template_registry / tier_promotion_thresholds)
9. [ ] Update `_boundaries/99_changelog.md` — append entry
10. [ ] Create `catalog/cat_16_AIT_ai_tier.md` — feature catalog
11. [ ] Update `16_ai_tier/_index.md` — replace concept row with AIT_001 DRAFT row
12. [ ] Coordinate with PROG_001 `tracking_tier` field (now active; not just reserved)
13. [ ] Coordinate with NPC_001 closure pass to fold tier-aware persona assembly
14. [ ] Coordinate with PL_005 closure pass to add tier-aware action availability gate
15. [ ] Coordinate with CSC_001 closure pass for procedural Untracked generation in cell-scene Layer 3
16. [ ] Update `features/_index.md` to add `16_ai_tier/` to layout + table
17. [ ] Release `_boundaries/_LOCK.md`
18. [ ] Commit with `[boundaries-lock-claim+release]` prefix

---

## §15 — Status

- **Created:** 2026-04-26 by main session post PROG_001 DRAFT closure (commit `9908940`)
- **Phase:** CONCEPT — Q1+Q2 LOCKED 2026-04-26 (see §16); Q3 implicitly resolved by Q2c-e; Q4-Q12 batched deep-dive ongoing
- **Lock state:** `_boundaries/_LOCK.md` free as of PROG_001 DRAFT commit + FAC_001 closure (commits `9908940` then FAC_001 4-commit cycle). AIT_001 DRAFT promotion can proceed when Q-lock complete.

---

## §16 — Q1 + Q2 LOCKED 2026-04-26 (Tier ontology + assignment rules paired)

### §16.1 Q1 LOCKED — 2-variant `NpcTrackingTier` enum (Untracked = no aggregate)

| Sub | Decision |
|---|---|
| Q1a | Tier enum variants V1 | **2 variants**: `Major` / `Minor` (Untracked = absence of ActorProgression aggregate; type-system enforced via PROG_001 §3.1 storage model) |
| Q1b | V1+ tier extensibility | Reserved (`Legendary` for fully-simulated historical figures DF Legends mode V2; `Faction` for collective entity tier V3) — additive per I14 |
| Q1c | PC vs NPC distinction | PC has `tracking_tier=None` on actor_progression (always tracked, eager Generator); NPC has `Some(Major\|Minor)` (lazy materialization); Untracked NPC = no aggregate at all |

```rust
pub enum NpcTrackingTier {
    Major,    // V1 — LLM-driven; full PC-like agency; max ≤20 default
    Minor,    // V1 — Rule-based scripted; max ≤100 default
    // Untracked = absence of ActorProgression aggregate (PROG_001 §3.1 semantic)
    // V1+ reserved: Legendary (V2 DF Legends mode); Faction (V3 collective tier)
}
```

### §16.2 Q2 LOCKED — Tier assignment rules

| Sub | Decision |
|---|---|
| Q2a | Canonical NPCs tier source | **Author-declared REQUIRED on `CanonicalActorDecl.tracking_tier`** at NPC_001 closure pass — forces explicit choice (no default; prevents accidental Major-tier overuse → LLM cost) |
| Q2b | Untracked NPCs source | **NEVER in canonical_actor_decl** — Untracked is purely ephemeral; generated on-demand at observation events (Q4-Q5 deferred batch) |
| Q2c | Promotion Untracked → Tracked V1 | **Forge admin action only** — NEW `Forge:PromoteUntrackedToTracked { ephemeral_npc_id, cell_id, new_tier }` AdminAction (WA_003 closure folds in). Effect: ephemeral NpcId becomes persistent; persona+stats crystallize into NPC_001 npc core aggregate; ActorProgression created with author-declared tracking_tier |
| Q2d | Auto-promotion V1 | **NO V1** — V1+30d significance threshold mechanism (AIT-D1 deferral); LLM-propose with author-confirm V1+30d (AIT-D7 deferral) |
| Q2e | Demotion Tracked → Untracked V1 | **NO V1 — disabled** — Tracked is permanent V1; V1+30d via Forge `Forge:DemoteTrackedToUntracked` (AIT-D2 deferral); use cases: deceased NPC simplified to memorial / sect dissolved members lose Major status |
| Q2f | Untracked NpcId scoping V1 | **Session-ephemeral + deterministic blake3 seed** — `NpcId(blake3(reality_id \|\| cell_id \|\| fiction_day \|\| slot_index))`; replay determinism per EVT-A9 |
| Q2g | Untracked NpcId reclaim V1 | **Cell-leave + session-end (hybrid)** — Q6 deep-dive deferred for full discard policy specification; V1 default per these 2 triggers + causal-ref pin override (V1+ defer details) |
| Q2h | Tier capacity caps V1 | **Author-declared `tier_capacity_caps: Option<TierCapacityCaps>` on RealityManifest** — engine defaults: `max_major_tracked: 20`, `max_minor_tracked: 100`, Untracked unlimited (per-cell density Q8 deferred) |

### §16.3 Q3 IMPLICITLY RESOLVED by Q2c-e

Per Q2 LOCKED sub-decisions, Q3 (promotion mechanism) is fully covered:
- **V1 promotion**: Forge admin action only (Q2c)
- **V1 auto-promotion**: NO (Q2d → AIT-D1 V1+30d)
- **V1 LLM-propose**: NO (Q2d → AIT-D7 V1+30d)
- **V1 demotion**: NO disabled (Q2e → AIT-D2 V1+30d)

No additional Q3 deep-dive needed. Status: LOCKED via Q2.

### §16.4 Concrete V1 shape from Q1+Q2

```rust
// ─── Q1 enum ───
pub enum NpcTrackingTier {
    Major,
    Minor,
}

// ─── Q2a NPC_001 closure pass extension (downstream) ───
pub struct CanonicalActorDecl {
    // ... existing fields per NPC_001 ...
    pub tracking_tier: NpcTrackingTier,    // V1 REQUIRED
}

// ─── Q2c WA_003 closure pass extension (downstream) ───
pub enum ForgeEditAction {
    // ... existing ...
    PromoteUntrackedToTracked {
        ephemeral_npc_id: NpcId,           // session-ephemeral; stable per blake3 seed
        cell_id: ChannelId,                // observation cell
        new_tier: NpcTrackingTier,         // Major or Minor (must respect tier_capacity_caps)
    },
}

// ─── Q2f deterministic Untracked ID generation ───
fn untracked_npc_id_for(
    reality_id: RealityId,
    cell_id: ChannelId,
    fiction_day: u64,
    slot_index: u8,
) -> NpcId {
    NpcId(blake3_hash(reality_id, cell_id, fiction_day, slot_index))
}

// ─── Q2h RealityManifest extension ───
pub struct RealityManifest {
    // ... existing PROG_001 + NPC_001 + IDF + FF + FAC fields ...
    pub tier_capacity_caps: Option<TierCapacityCaps>,
}

pub struct TierCapacityCaps {
    pub max_major_tracked: u32,    // engine default 20
    pub max_minor_tracked: u32,    // engine default 100
    // Untracked unlimited (per-cell density Q8)
}
```

### §16.5 V1+ deferrals from Q1+Q2

| ID | Deferral | Trigger to revisit |
|---|---|---|
| **AIT-D1** | Auto-promotion via significance threshold | V1+30d significance heuristic |
| **AIT-D2** | Demotion Tracked → Untracked via Forge | V1+30d narrative use cases |
| **AIT-D3** | Legendary tier (DF Legends mode) | V2 worldbuilding extension |
| **AIT-D4** | Faction tier (V3 collective entity) | V3 with future ORG/FAC integration |
| **AIT-D5** | Tier capacity dynamic adjustment (LLM proposes increase based on narrative load) | V2+ |
| **AIT-D6** | Untracked NpcId persistence beyond cell-leave (causal-ref pin) | V1+30d when QST_001 V2 needs it |
| **AIT-D7** | LLM-propose-promotion with author-confirm | V1+30d UX iteration |

### §16.6 Q4+Q5+Q11 LOCKED 2026-04-27 (Untracked generation pipeline)

| Sub | Decision |
|---|---|
| Q4a | Generation architecture | **Hybrid 2-stage** — Stage 1 template+RNG (deterministic, cheap) at cell-entry; Stage 2 LLM-flavor (lazy, on first PL_005 interaction) |
| Q4b | Stage 1 template declaration | Author declares `UntrackedTemplateDecl` per PlaceType in RealityManifest with role list (role_id + display_name_template + actor_class + name_pool + stat_ranges + appearance_hints + default_dialogue_register) |
| Q4c | Stage 1 RNG seed | `blake3(reality_id \|\| cell_id \|\| fiction_day \|\| slot_index)` — same as Q2f for replay determinism |
| Q4d | Stage 2 LLM trigger | **First PL_005 interaction targeting Untracked** (lazy on-demand) |
| Q4e | Stage 2 cache | In-memory per session; discarded with NPC at cell-leave / session-end |
| Q4f | Author UX V1 | RealityManifest editing via WA_003 Forge; richer template editor V1+30d |
| Q5a | Generation timing V1 | **Cell-entry** (PC entity_binding location change INTO cell triggers); on-demand AIT-D8 V1+30d |
| Q5b | Batched per cell entry | YES — single Stage 1 batch per cell+day; all density slots filled at observation moment |
| Q5c | Re-entry within same day | Same blake3 seed → same Untracked NPCs (deterministic) |
| Q5d | Re-entry new day | Different seed → DIFFERENT Untracked (natural crowd rotation) |
| Q5e | Generation event | NEW EVT-T5 sub-type `Generated:UntrackedNpcSpawn { reality_id, cell_id, fiction_day, slot_index, npc_id, role_id }` |
| Q5f | Stage 2 LLM-flavor timing | Lazy first-interaction only; one LLM call per Untracked per session |
| Q11a | NpcId continuity at promotion | **STABLE** — ephemeral blake3-derived NpcId becomes persistent in same NPC_001 namespace |
| Q11b | Persona crystallization | Stage 1 stats + Stage 2 LLM-flavor (if cached; else synthesized at promotion moment) snapshot into NPC_001 npc core aggregate |
| Q11c | Causal-ref preservation | Events with `actor: NpcId` from pre-promotion remain valid; full history queryable post-promotion |
| Q11d | Demotion reverse path | V1+30d (AIT-D2) — TBD when AIT-D2 designed |
| Q11e | Promotion timing | Atomic at turn-boundary; ActorProgression aggregate created with Stage 1 stats as initial_value per kind_id |

**Concrete shape additions (Q4+Q5+Q11):**

```rust
pub struct UntrackedTemplateDecl {
    pub place_type: PlaceTypeRef,
    pub roles: Vec<UntrackedRoleDecl>,
}

pub struct UntrackedRoleDecl {
    pub role_id: String,
    pub display_name_template: I18nBundle,           // {name} substituted from name_pool
    pub actor_class: ActorClassRef,
    pub name_pool: Vec<String>,                      // RNG picks per slot_index
    pub stat_ranges: Vec<StatRangeDecl>,             // PROG_001 ProgressionInstance min/max
    pub appearance_hints: I18nBundle,
    pub default_dialogue_register: DialogueRegister,
}

pub struct StatRangeDecl {
    pub kind_id: ProgressionKindId,
    pub min: u64,
    pub max: u64,
}

// V1 NEW EVT-T5 sub-types:
//   Generated:UntrackedNpcSpawn { reality_id, cell_id, fiction_day, slot_index, npc_id, role_id }
//   Generated:UntrackedNpcDiscarded — see Q6 §16.7
```

### §16.7 Q6+Q12 LOCKED 2026-04-27 (Discard policy + LLM context budget)

| Sub | Decision |
|---|---|
| Q6a | Cell-leave trigger | **EF_001 entity_binding location change AWAY from cell** — atomic at turn-boundary |
| Q6b | Session-end trigger | PL_001 §session lifecycle: disconnect / sleep major (8h+) / explicit `/end` MetaCommand / 24h idle timeout |
| Q6c | Causal-ref pin V1 | **NO** — defer V1+30d (AIT-D6); V1 simple discard regardless; Forge promotion is V1 escape valve |
| Q6d | Time-based discard V1 | **NO** — daily rotation Q5d covers ephemeral feel |
| Q6e | Discard event | NEW EVT-T5 sub-type `Generated:UntrackedNpcDiscarded { reality_id, cell_id, fiction_day, slot_index, npc_id, reason }` (mirror spawn for audit symmetry) |
| Q12a | Per-tier persona detail | **PC: FullPersona / Major: FullPersona / Minor: CondensedPersona / Untracked: SummaryLine** (V1 defaults) |
| Q12b | Untracked summary composition | Stage 1 template `display_name_template` + `actor_class` + `appearance_hints` + Stage 2 cached flavor (if available) |
| Q12c | Roster ordering | Tier-priority (PC > Major > Minor > Untracked); within tier: NPC_002 Chorus priority |
| Q12d | Roster caps V1 | **5 FullPersona + 8 Condensed + 12 Summary** defaults; author-tunable in `tier_roster_caps: Option<TierRosterCaps>` |
| Q12e | Overflow handling | **Aggregate format**: "...and N other patrons go about their business" |
| Q12f | Author per-NPC bump | V1+30d (AIT-D12) |

**Concrete shape additions (Q6+Q12):**

```rust
pub enum UntrackedDiscardReason {
    CellLeave,                                       // V1 — Q6a
    SessionEnd,                                      // V1 — Q6b
    PromotedToTracked,                               // V1 — Q11
    StaleTimeout,                                    // V1+30d — AIT-D8
    CausalRefExpired,                                // V1+30d — AIT-D6
}

pub enum PromptDetail {
    FullPersona,                                     // ~300-500 tokens
    CondensedPersona,                                // ~80-150 tokens
    SummaryLine,                                     // ~20-40 tokens
    Hidden,                                          // 0 tokens
}

pub struct TierRosterCaps {
    pub max_full_persona: u8,                        // V1 default 5 (PC + Major shared cap)
    pub max_condensed: u8,                           // V1 default 8 (Minor)
    pub max_summary: u8,                             // V1 default 12 (Untracked)
    pub overflow_format: OverflowFormat,
}

pub enum OverflowFormat {
    Truncate,
    Aggregate,                                       // V1 default — "...and N other patrons"
}
```

### §16.8 V1+ deferrals (cumulative AIT-D1..D15 from Q1-Q6+Q11+Q12)

| ID | Deferral | Trigger |
|---|---|---|
| AIT-D1 | Auto-promotion via significance threshold | V1+30d |
| AIT-D2 | Demotion via Forge | V1+30d |
| AIT-D3 | Legendary tier (DF Legends mode) | V2 |
| AIT-D4 | Faction tier collective | V3 |
| AIT-D5 | Dynamic capacity adjustment | V2+ |
| AIT-D6 | Untracked NpcId persistence beyond cell-leave (causal-ref pin) | V1+30d |
| AIT-D7 | LLM-propose-promotion with author-confirm | V1+30d |
| AIT-D8 | On-demand generation beyond cell-entry | V1+30d |
| AIT-D9 | Multi-day Untracked persistence | V1+30d |
| AIT-D10 | Stage 2 LLM-flavor cache cross-session | V2 |
| AIT-D11 | Untracked-to-Untracked interactions | V2 |
| AIT-D12 | Author per-NPC persona-detail bump | V1+30d |
| AIT-D13 | Dynamic roster caps | V2 |
| AIT-D14 | Adaptive PromptDetail | V2 |
| AIT-D15 | Untracked summary localization variants | V1+30d |

### §16.9 Q7-Q9 still open

After Q1-Q6+Q11+Q12 LOCKED, remaining:

- **Q7 — Behavior model per tier** (next deep-dive batched with Q8+Q9): closed-set capability per PC/Major/Minor/Untracked
- **Q8 — Per-cell-type Untracked density** (full DensityDecl shape; Q5 already set up RealityManifest field)
- **Q9 — Action availability per tier** (PL_005 InteractionKind subset per tier)

Q7+Q8+Q9 are tightly coupled (all about per-tier behavior/availability). Natural next batch.

Q10 already locked by Q2f (deterministic blake3 seed for Untracked replay). No deep-dive needed.
