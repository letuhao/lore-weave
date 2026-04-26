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
- **Phase:** CONCEPT — awaiting Q1-Q12 deep-dive
- **Lock state:** `_boundaries/_LOCK.md` free as of PROG_001 DRAFT commit. AIT_001 DRAFT promotion can proceed when Q-lock complete.
- **Estimated time to DRAFT (post-Q-deep-dive):** 5-7 hours focused design work; ~1200-1500 lines projected (smaller than PROG_001 since AIT is architecture-scale not multi-genre-coverage)
- **Dependencies (when DRAFT):**
  - PROG_001 `tracking_tier` field activation (currently `None` V1 default; AIT_001 populates enum)
  - NPC_001 closure pass folds tier-aware persona assembly
  - PL_005 closure pass adds tier-aware action availability
  - CSC_001 closure pass for Untracked procedural generation
  - WA_003 closure pass folds Forge:PromoteToTracked / DemoteToUntracked AdminActions
  - 07_event_model agent registers AIT_001 sub-types
  - V1+30d RES_001 closure pass aligns NPC eager → lazy migration (PROG-D19)
- **Next action:** User decides Q-deep-dive batching strategy (mirror PROG_001 6-batch pattern OR alternative)
