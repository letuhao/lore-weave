# REP_001 — Reputation Foundation

> **Conversational name:** "Reputation" (REP). Tier 5 Actor Substrate Foundation feature owning per-(actor, faction) `actor_faction_reputation` aggregate (sparse — only declared/touched rows). Resolves V1+ deferral from FAC_001 (FAC-D7 per-(actor, faction) reputation projection separate aggregate). Wuxia critical (sect standing / Wulin reputation per sect / "thanh dự" tier-by-faction). D&D 5e + WoW + Sands of Salzaar pattern.
>
> **Boundary discipline (3-layer separation per Q10 LOCKED):**
>
> - **L1 NPC personal opinion** — NPC_001 `npc_pc_relationship_projection` (per-(NPC, PC) trust + familiarity + stance_tags); session-end derived.
> - **L2 Actor global fame** — RES_001 `resource_inventory` SocialCurrency::Reputation (per-actor unbounded i64 SUM scalar; "danh tiếng" wuxia world fame).
> - **L3 Actor-faction standing** — REP_001 `actor_faction_reputation` (per-(actor, faction) bounded i16 [-1000, +1000] + 8-tier engine-fixed display).
>
> These three layers are COMPLEMENTARY, NOT duplicative. NPC_002 Chorus consumes ALL THREE for priority resolution.
>
> **Category:** REP — Reputation Foundation (Tier 5 Actor Substrate post-FAC_001 priority)
> **Status:** CANDIDATE-LOCK 2026-04-27 (4-commit cycle complete: Phase 0 6b7d931 → Q-LOCKED 1/4 61e5019 → DRAFT 2/4 b2025a1 → Phase 3 cleanup 3/4 b321f74 → closure pass 4/4 this commit; Q1-Q10 LOCKED via 5-batch deep-dive; 1 REVISION on Q4 — Always Neutral V1, V1+ hybrid alongside Q6 cascade)
> **Stable IDs in this file:** `REP-A*` axioms · `REP-D*` deferrals · `REP-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern); [FAC_001 §3.1](../00_faction/FAC_001_faction_foundation.md#31-faction-t2--reality-scope--sparse) (FactionId source-of-truth); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (Wuxia tier display labels); [07_event_model EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT); [WA_003 Forge](../02_world_authoring/WA_003_forge.md) (forge_audit_log).
> **Defers to:** V1+ runtime gameplay rep events (PL_005 Strike on faction member triggers REP_001 delta); V1+ NPC_002 Tier 4 priority modifier (rival-faction NPCs read REP_001); V1+ WA_001 AxiomDecl.requires_reputation hook (faction-gated abilities require min rep tier); V1+ TIT_001 title-grant requires min rep; V1+ CULT_001 cultivation method requires min rep; V2+ DIPL_001 inter-faction war affects rep cascade; V2+ 13_quests quest reward = rep delta; V2+ WA_002 Heresy cross-reality migration per Q8 LOCKED.
> **Event-model alignment:** Reputation events = EVT-T4 System sub-type `ReputationBorn` (canonical seed) + EVT-T8 Administrative `Forge:SetReputation` + `Forge:ResetReputation` V1 active per Q5 LOCKED + EVT-T3 Derived (`aggregate_type=actor_faction_reputation` with delta_kinds Delta + CascadeDelta + DecayTick — V1+ runtime per Q5+Q6+Q7 LOCKED). No new EVT-T* category.

---

## §1 User story (Wuxia 3 declared rep + Modern + V1+ runtime)

### V1 Wuxia canonical reputation (RealityManifest.canonical_actor_faction_reputations — sparse)

| Actor | Faction | Score | Tier (display) | Wuxia label | Notes |
|---|---|---|---|---|---|
| Du sĩ | Đông Hải Đạo Cốc | +250 | Friendly | Đệ tử (disciple) | Outer disciple sect standing; matches FAC_001 membership role_id="outer_disciple" |
| Du sĩ | Ma Tông | -300 | Hostile | Nghịch tặc (rebel/foe) | Demonic-sect rival baseline; score -300 falls in Hostile tier (-500..=-251); matches FAC_001 default_relations Hostile narrative |
| Du sĩ | Tây Sơn Phật Tự | +25 | Neutral | Người lạ (stranger) | Daoist+Buddhist friendly cooperation; score in Neutral default zone |

**Sparse storage discipline:** Only ~3 declared rep rows V1. Most (actor, faction) pairs have NO row → "Neutral default" implied per Q4 LOCKED. PC Lý Minh has 0 rep rows V1 (no faction history yet).

### V1 canonical actor reputation defaults (no rows)

Actors below have ZERO declared rep rows V1 → engine `read_rep(actor, faction)` returns `unwrap_or(0)` = score=0, tier=Neutral, label="Người lạ" per Q4 LOCKED. NO entries written to canonical_actor_faction_reputations Vec for these actors.

- **Lý Minh** (PC) — 0 rep rows V1 (PC unaffiliated; default Neutral with all factions on read)
- **Tiểu Thúy** (NPC, innkeeper daughter) — 0 rep rows V1 (commoner; no faction history)
- **Lão Ngũ** (NPC, innkeeper) — 0 rep rows V1 (commoner; no faction history)

### V1+ runtime examples (canonical seed + Forge V1 only; runtime gameplay V1+)

- **Forge admin** "Lý Minh insults Đông Hải elder" → V1 active: `Forge:SetReputation { actor_id: lm01, faction_id: dong_hai, before_score: 0, after_score: -100, reason: "insulted elder" }` → Lý Minh's rep with Đông Hải drops from Neutral (implicit 0) to Hostile (-100; row created)
- **Forge admin** "wipe Lý Minh's rep with Ma Tông after public apology" → V1 active: `Forge:ResetReputation { actor_id: lm01, faction_id: ma_tong, before_score: -50, reason: "public apology" }` → row deleted (back to implicit Neutral)
- **PC kills rival Ma Tông cultivator in PL_005 Strike** → V1+ Delta event: `delta_kind=Delta { score_change: -200, source: "killed_member" }` → -rep with Ma Tông
- **PC's Strike on Ma Tông cascades V1+** → V1+ CascadeDelta event: `delta_kind=CascadeDelta { score_change: +50, source_event: <strike_evt>, source_faction: ma_tong }` → +rep with Đông Hải (Ma Tông's rival per FAC_001 default_relations Hostile) per Q6 V1+ enrichment
- **6 fiction-months pass without faction interaction** → V1+ DecayTick event: `delta_kind=DecayTick { score_change: -10 }` → rep drifts 10 closer to 0 per Q7 V1+ enrichment

**This feature design specifies:** `actor_faction_reputation` aggregate sparse storage per-(reality, actor_id, faction_id) with bounded i16 score in [-1000, +1000] + 8-tier engine-fixed ReputationTier display + asymmetric thresholds + Wuxia I18n labels + Always Neutral (0) default V1 (Q4 REVISION; V1+ hybrid via REP-D16); 6 V1 reject rule_ids in `reputation.*` namespace; canonical seed + Forge admin V1 active per Q5 LOCKED; runtime gameplay + cascade + decay V1+ per Q5+Q6+Q7 V1+ enrichment milestone.

After this lock: every (actor, faction) pair has deterministic reputation read (declared row OR implicit Neutral 0); FAC-D7 RESOLVED; V1+ NPC_002 Tier 4 priority modifier + V1+ WA_001 AxiomDecl.requires_reputation hook + V1+ TIT_001 + V1+ CULT_001 consume REP_001 for downstream features.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Reputation row** | `actor_faction_reputation` aggregate per-(reality, actor_id, faction_id) | Sparse storage; only declared/touched rows |
| **Score** | `i16` field in [-1000, +1000] (clamped) | Bounded per Q3 LOCKED; engine clamps any out-of-range to nearest endpoint |
| **Tier** | `ReputationTier` 8-variant enum (display layer; not stored) | Computed from score via engine-fixed thresholds; Wuxia I18n display labels |
| **Tier mapping** | Asymmetric thresholds per Q3 LOCKED | Wide Neutral (200) / narrow Exalted (100) / wide Hated (500) — Wuxia narrative shape |
| **Default Neutral** | Missing row → implicit score=0 per Q4 REVISION LOCKED | V1 simple `unwrap_or(0)`; V1+ hybrid (membership-derived) via REP-D16 alongside Q6 cascade |
| **Sparse storage** | Only declared/touched rows exist | V1 canonical seed declarations + V1+ lazy-create on first runtime delta touch |
| **3-layer separation** | REP_001 ≠ RES_001 SocialCurrency::Reputation ≠ NPC_001 NpcOpinion per Q10 LOCKED | Boundary discipline; LLM authoring conventions explicit |
| **8-tier ReputationTier** | Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted | WoW + D&D 5e + Wuxia novels hybrid; engine-fixed |
| **Wuxia I18n display** | Đại nghịch / Nghịch tặc / Kẻ thù / Người lạ / Đệ tử / Trưởng lão / Tôn sư / Đại Thánh nhân | Tier displayed via I18nBundle per RES_001 §2.3 contract |

### Tier mapping (engine-fixed; display layer)

```rust
pub enum ReputationTier {
    Hated,        // -1000..=-501  (width 500; wide negative apex)
    Hostile,      // -500..=-251   (width 250)
    Unfriendly,   // -250..=-101   (width 150)
    Neutral,      // -100..=+100   (width 200; wide default zone)
    Friendly,     // +101..=+250   (width 150)
    Honored,      // +251..=+500   (width 250)
    Revered,      // +501..=+900   (width 400; harder to reach)
    Exalted,      // +901..=+1000  (width 100; narrow apex; rare)
}

impl ReputationTier {
    pub fn from_score(score: i16) -> Self {
        match score {
            -1000..=-501 => Self::Hated,
            -500..=-251 => Self::Hostile,
            -250..=-101 => Self::Unfriendly,
            -100..=100 => Self::Neutral,
            101..=250 => Self::Friendly,
            251..=500 => Self::Honored,
            501..=900 => Self::Revered,
            901..=1000 => Self::Exalted,
            _ => unreachable!("score must be clamped to [-1000, +1000] at write boundary"),
        }
    }

    pub fn display_label_vi(&self) -> &'static str {
        match self {
            Self::Hated => "Đại nghịch",
            Self::Hostile => "Nghịch tặc",
            Self::Unfriendly => "Kẻ thù",
            Self::Neutral => "Người lạ",
            Self::Friendly => "Đệ tử",
            Self::Honored => "Trưởng lão",
            Self::Revered => "Tôn sư",
            Self::Exalted => "Đại Thánh nhân",
        }
    }
}
```

### REP_001 axioms

- **REP-A1** (Bounded score) — Score is i16 clamped to [-1000, +1000] at write boundary; engine rejects no in-range values; clamps silently on Forge admin overflow attempts (preserves narrative flow per Q3 LOCKED).
- **REP-A2** (Sparse storage) — Missing row = implicit Neutral (0). Engine reads `unwrap_or(0)` per Q2 + Q4 LOCKED. V1+ lazy-create row on first delta touch (Q2-(C) deferred enrichment).
- **REP-A3** (Engine-fixed tier mapping) — 8-tier `ReputationTier` thresholds engine-fixed V1; FactionDecl.rep_tier_overrides V1+ enrichment (REP-D4) provides per-faction display label customization, NOT threshold customization.
- **REP-A4** (3-layer separation) — REP_001 ≠ RES_001 SocialCurrency::Reputation ≠ NPC_001 NpcOpinion per Q10 LOCKED. Distinct shapes; distinct semantics; distinct queries; distinct LLM authoring prompts.
- **REP-A5** (V1 canonical seed + Forge only) — V1 events: ReputationBorn + Forge:SetReputation + Forge:ResetReputation. Runtime gameplay delta + cascade + decay V1+ per Q5+Q6+Q7 V1+ runtime reputation milestone.
- **REP-A6** (Synthetic actor forbidden V1) — Synthetic actors cannot have reputation rows per Q9 LOCKED (universal substrate discipline).
- **REP-A7** (Cross-reality strict V1) — Reputation rows valid only within their reality_id; V2+ Heresy migration per Q8 LOCKED.

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Reputation declared at canonical seed | **EVT-T4 System** | `ReputationBorn { actor_id, faction_id, initial_score }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Reputation Forge admin set | **EVT-T8 Administrative** | `Forge:SetReputation { actor_id, faction_id, before_score, after_score, reason }` | Forge (WA_003) | ✓ V1 |
| Reputation Forge admin reset | **EVT-T8 Administrative** | `Forge:ResetReputation { actor_id, faction_id, before_score, reason }` | Forge (WA_003) | ✓ V1 |
| Reputation gameplay delta | **EVT-T3 Derived** | `aggregate_type=actor_faction_reputation`, `delta_kind=Delta { score_change, source }` | Aggregate-Owner (REP_001 owner-service) | ✗ V1+ per Q5 |
| Reputation cascade delta | **EVT-T3 Derived** | `delta_kind=CascadeDelta { score_change, source_event, source_faction }` | Aggregate-Owner | ✗ V1+ per Q6 (REP-D2) |
| Reputation decay tick | **EVT-T3 Derived** | `delta_kind=DecayTick { score_change }` | Aggregate-Owner (V1+ scheduled tick) | ✗ V1+ per Q7 (REP-D3) |

**Event ordering at canonical seed (per PL_001 §16.2):** EntityBorn → PlaceBorn → MapLayoutBorn → SceneLayoutBorn → RaceBorn → FamilyBorn → FactionBorn → FactionMembershipBorn → **ReputationBorn** → (other Tier 5 actor substrate). REP_001 emits AFTER FactionMembershipBorn since reputation references both actor (EF_001) and faction (FAC_001).

---

## §3 Aggregate inventory

REP_001 ships **1 aggregate** V1.

### §3.1 `actor_faction_reputation` (T2 / Reality scope — primary)

```rust
pub struct ActorFactionReputation {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub faction_id: FactionId,
    pub score: i16,                    // bounded [-1000, +1000] per Q3 LOCKED; clamped at write
    pub last_updated_at_turn: u64,
    pub last_event_id: Option<EventId>, // causal-ref to triggering event
    // V1+ extensions (additive per I14)
    // No V1+ schema fields yet — Q4 hybrid enrichment uses derivation, not schema; Q6 cascade
    // and Q7 decay use FactionDecl additive fields (NOT actor_faction_reputation schema additions).
}
```

**Key:** `(reality_id, actor_id, faction_id)`. Unique constraint enforced; duplicate rows rejected with `reputation.duplicate_row` (reject rule 6).

**Storage discipline (Q2 LOCKED):**
- **V1 sparse:** Only canonical-seed-declared rows + V1+ lazy-created rows exist. Most (actor, faction) pairs HAVE NO ROW.
- **V1 read:** `unwrap_or(0)` for missing rows → implicit Neutral.
- **V1+ lazy-create:** When first runtime delta event fires for unseen pair (V1+ Q5 enrichment), owner-service inserts row with `score = 0 + delta` then continues normal flow.

**Mutability:**
- V1: Mutable via canonical seed (ReputationBorn) + Forge admin (SetReputation / ResetReputation) only per REP-A5.
- V1+: Mutable via runtime gameplay (Delta — REP-D1) + cascade (CascadeDelta — REP-D2) + decay (DecayTick — REP-D3) — Q5+Q6+Q7 V1+ runtime reputation milestone. **Coherence note:** all 3 V1+ enrichments ship together in single milestone — Delta without Cascade is partial; Cascade without configurable attenuation creates loops; Decay without scheduled tick mechanism is a stub. Lazy-create row pattern (Q2-(C)) activates with REP-D1 (V1+ runtime gameplay): owner-service inserts row with `score = 0 + delta` on first delta touch then updates on subsequent deltas.

**Score clamping (REP-A1):**
- Engine clamps `score: i16` to [-1000, +1000] at write boundary.
- Forge admin overflow: `Forge:SetReputation { after_score: 1500 }` → engine clamps to 1000 silently (no reject; preserves narrative flow per Q3 LOCKED).
- V1+ delta overflow: `Delta { score_change: +500 }` against existing score=900 → engine clamps to 1000 (saturating arithmetic).

**Synthetic actors forbidden V1 (REP-A6):**
- Reject `reputation.synthetic_actor_forbidden` Stage 0 schema for actor.kind == ActorKind::Synthetic.

**Cross-reality strict V1 (REP-A7):**
- Reject `reputation.cross_reality_mismatch` Stage 0 schema for actor.reality_id ≠ faction.reality_id.

**3-layer separation discipline (REP-A4):**
- REP_001 actor_faction_reputation is per-(actor, faction) bounded standing — DISTINCT from RES_001 SocialCurrency::Reputation (per-actor unbounded global "danh tiếng" sum) and NPC_001 npc_pc_relationship_projection (per-(NPC, PC) personal opinion).
- LLM authoring discipline: prompts MUST disambiguate "faction reputation with [faction]" (REP_001) vs "global fame" (RES_001) vs "NPC opinion" (NPC_001).

---

## §4 Tier+scope (DP-R2)

| Aggregate | Tier | Scope | Read frequency | Write frequency | Storage notes |
|---|---|---|---|---|---|
| `actor_faction_reputation` | T2 | Reality | ~1.0 per turn (V1+ NPC_002 Tier 4 + V1+ WA_001 requires_reputation + UI display) | ~0 V1 (canonical seed only); V1+ rare runtime delta on PL_005 Strike | Sparse storage; mutable; ~3 rows V1 Wuxia preset; AI Tier scaling = touched-only |

---

## §5 DP primitives

REP_001 reuses standard 06_data_plane primitives:

```rust
// V1 reads
let rep = dp::read_aggregate_reality::<ActorFactionReputation>(ctx, reality_id,
              key=(actor_id, faction_id))
    .await?;
let score = rep.map(|r| r.score).unwrap_or(0);  // sparse read fallback per Q4 LOCKED
let tier = ReputationTier::from_score(score);

// V1 writes (canonical seed + Forge only per Q5 LOCKED)
dp::t2_write(ctx, "ReputationBorn",
    aggregate=actor_faction_reputation,
    payload=ActorFactionReputation { ... },
    causal_ref=bootstrap_event)
.await?;

dp::t2_write(ctx, "Forge:SetReputation",
    aggregate=actor_faction_reputation,
    payload=updated_row,
    causal_ref=forge_admin_event)
.await?;

// V1+ writes (gameplay delta + cascade + decay)
// (V1+ Q5+Q6+Q7 enrichment; not V1)
```

---

## §6 Capability requirements (JWT claims)

| Operation | JWT claim required | Notes |
|---|---|---|
| Read `actor_faction_reputation` | `reality.read` | Standard reality-scope read |
| Write canonical seed (ReputationBorn) | `bootstrap.canonical_seed` | RealityBootstrapper role only |
| Write Forge admin (SetReputation / ResetReputation) | `forge.admin` (WA_003 contract) | Reuses WA_003 Forge JWT contract; no new claim |
| Write V1+ runtime gameplay delta | (V1+ — TBD when V1+ ships) | Aggregate-Owner role; depends on Q5 V1+ activation |

---

## §7 Subscribe pattern

| Aggregate | Subscribe to | Use case |
|---|---|---|
| `actor_faction_reputation` | `aggregate_type=actor_faction_reputation` (V1+ runtime) | V1+ NPC_002 Tier 4 priority modifier on rep change; V1+ WA_001 requires_reputation gate cache invalidation |
| (V1+) | `aggregate_type=faction` (FAC_001 SetCurrentHead) | (V1+ optional — sect succession may invalidate cached reputation tier display) |

---

## §8 Pattern choices

### §8.1 Materialized aggregate over projection (Q1 LOCKED)

REP_001 V1 chooses materialized aggregate over projection per Q1 LOCKED:
- FAC_001 V1 already chose materialized over projection (Q1 LOCKED) — same trade-off applies
- Projection (NPC_001 pattern) works for high-volume session-end derivation; reputation is rare event (canonical seed V1; V1+ runtime sparse)
- Direct mutation keeps event flow simple V1; AI Tier projection optimization is V1+30d if needed (consumed by AIT_001 layered tier scheduling)
- Term "projection" in FAC_001 docs was loose terminology — actual implementation = materialized aggregate per FAC_001 pattern

### §8.2 Sparse storage + V1+ lazy-create (Q2 LOCKED)

REP_001 V1 chooses sparse storage with V1+ lazy-create combined per Q2 LOCKED:
- Wuxia V1 SPIKE_01 has ~3 declared rep rows; dense storage = 88% wasted (5 actors × 5 factions = 25 rows; only 3 narratively meaningful)
- AI Tier billion-NPC scaling: dense = O(NPC × Faction) catastrophic
- Sparse + Neutral default = cheap; matches FAC_001 sparse storage discipline
- V1+ on-demand row creation when first delta event fires for unseen (actor, faction) pair (lazy-create with `score = 0 + delta`)
- Read fallback: missing row → Neutral default per Q4 LOCKED

### §8.3 Bounded i16 [-1000, +1000] + 8-tier engine-fixed (Q3 LOCKED)

REP_001 V1 chooses bounded i16 + 8-tier engine-fixed per Q3 LOCKED:
- Bounded prevents inflation (CK3-style runaway prestige); narrative authenticity holds
- 8-tier WoW pattern most expressive for wuxia (Hated→Exalted maps to 江湖恩怨 spectrum); D&D 5e + Sands of Salzaar + Path of Wuxia validate
- Asymmetric thresholds: wide Neutral (200) = default zone; narrow Exalted (100) = rare apex; wide Hated (500) = "mortal enemy" deeper; wide Revered (400) = elder threshold takes effort
- i16 storage minimal; sparse storage trivial cost
- Tier mapping engine-fixed (display layer); LLM/UI computes label
- V1+ author-declared per-faction tier display labels via FactionDecl.rep_tier_overrides: HashMap<i16, I18nBundle> (additive REP-D4 enrichment)

### §8.4 Always Neutral (0) V1; V1+ hybrid alongside Q6 cascade (Q4 REVISION LOCKED)

REP_001 V1 chooses Always Neutral default per Q4 REVISION LOCKED (revised from initial hybrid recommendation):
- Q6 (cascade) defers V1+; without cascade reads of FAC_001 default_relations, hybrid Layer 2 semantics underspecified V1
- V1 simplicity wins: `unwrap_or(0)` everywhere; declared rows in canonical seed override
- Wuxia V1 SPIKE_01 — Du sĩ outer disciple author EXPLICITLY DECLARES rep row +250 in canonical_actor_faction_reputations; no need for Layer 2 derivation V1
- V1+ enrichment trivial: add Layer 2 read function consulting actor_faction_membership + faction.default_relations; activates with Q6 cascade enrichment together (coherent V1+ runtime reputation milestone — REP-D16)
- Avoids premature coupling of REP_001 V1 read path to FAC_001 default_relations interpretation

### §8.5 Forge admin V1 + canonical seed V1; runtime gameplay V1+ (Q5 LOCKED)

REP_001 V1 chooses Forge admin + canonical seed only per Q5 LOCKED:
- Forge admin universal V1 — every foundation feature ships own EVT-T8 Forge sub-shapes V1 (universal substrate discipline)
- Author needs admin override from day 1 ("Lý Minh insults Đông Hải elder" → Forge:SetReputation -100)
- Gameplay events (PL_005 Strike on faction member) need cascade design first (Q6 LOCKED V1+); coupling = runtime gameplay activates V1+ alongside cascade + decay
- Matches FAC_001 V1 pattern (Forge:RegisterFaction V1 active; runtime JoinFaction/LeaveFaction V1+ per FAC-D11)

### §8.6 No cascade V1; V1+ via REP-D2 (Q6 LOCKED)

REP_001 V1 chooses no cascade per Q6 LOCKED:
- Cascade design space is wide (depth + attenuation + loop prevention + filtering); not yet tested in narrative
- V1 LLM-emitted cascade is acceptable workaround: author/LLM emits multiple Forge:SetReputation calls to model cascade narratively; engine doesn't auto-derive
- V1+ REP-D2 enrichment scope: FactionDecl.rep_cascade_config: Option<RepCascadeConfig> (additive; { attenuation_factor: f32, max_depth: u8, loop_prevention: VisitedSet })

### §8.7 No decay V1; V1+ via REP-D3 (Q7 LOCKED)

REP_001 V1 chooses no decay per Q7 LOCKED:
- Decay design space is wide (linear vs exponential / per-faction config / fiction-time scaling / decay floor / tick mechanism)
- V1 narrative: rep persists explicitly until explicitly changed
- D&D 5e + WoW + Sands of Salzaar + Path of Wuxia all NO decay default — market consensus matches
- V1+ activation = additive field on FactionDecl (rep_decay_per_week: Option<i16>); cheap V1+ migration
- Tick mechanism could leverage AIT_001 tier scheduling (Tier 2 NPCs lazy decay; Tier 3 untracked = no decay; coherent with quantum-observation)

### §8.8 V1 strict single-reality + synthetic forbidden (Q8 + Q9 LOCKED)

Universal substrate discipline:
- Cross-reality forbidden V1 (Q8 LOCKED) — V2+ Heresy migration via WA_002
- Synthetic actors forbidden V1 (Q9 LOCKED) — V1+ may relax if admin/system-faction reputation needed (defer to REAL use case)

### §8.9 3-layer separation discipline coexist (Q10 LOCKED)

REP_001 V1 chooses coexist with RES_001 SocialCurrency::Reputation per Q10 LOCKED:
- Three semantically distinct concepts validated by wuxia novel canon (all three usages routine: per-NPC opinion / global fame / per-faction standing)
- (B) supersedes — RES_001 V1 lock break disruptive; loses global-fame semantic
- (C) merge — Sum stack policy ≠ Bounded clamp; resource_inventory.entries shape would explode
- LLM authoring discipline V1: prompts disambiguate via REP_001 §1 boundary statement
- V1+ REP-D17 enrichment (deferred): RES_001 SocialCurrency::Reputation rename to Fame + cross-cutting documentation in 11_cross_cutting

---

## §9 Failure-mode UX

| Reject rule | Stage | User-facing message (Wuxia I18n) | When fired |
|---|---|---|---|
| `reputation.unknown_actor_id` | 0 schema | "Actor không tồn tại trong hiện thực này" (Actor doesn't exist) | Canonical seed validation |
| `reputation.unknown_faction_id` | 0 schema | "Phái không tồn tại trong hiện thực này" (Faction doesn't exist) | Canonical seed validation |
| `reputation.score_out_of_range` | 0 schema (BUT clamps silently per REP-A1) | (No reject; engine clamps silently to nearest endpoint) | Forge admin attempts to set >1000 or <-1000 |
| `reputation.synthetic_actor_forbidden` | 0 schema | (Schema-level; not user-facing) | Synthetic actor cannot have rep row |
| `reputation.cross_reality_mismatch` | 0 schema | (Schema-level; not user-facing) | actor.reality_id ≠ faction.reality_id |
| `reputation.duplicate_row` | 0 schema | (Schema-level; not user-facing) | Duplicate (actor, faction) row insert attempt |

V1+ reservation rules:
- `reputation.runtime_delta_unsupported_v1` — V1+ when Q5 V1+ runtime gameplay activates
- `reputation.cascade_unsupported_v1` — V1+ when Q6 cascade ships (REP-D2)
- `reputation.decay_unsupported_v1` — V1+ when Q7 decay ships (REP-D3)
- `reputation.tier_threshold_violation` — V1+ when author-declared per-faction tiers ship (REP-D4)

**Per RES_001 §2 i18n contract:** All `reputation.*` rejects use `RejectReason.user_message: I18nBundle` with English `default` field + Vietnamese translation V1 from day 1.

---

## §10 Cross-service handoff (canonical seed flow)

REP_001 canonical seed flows through standard RealityBootstrapper pipeline:

1. **knowledge-service** ingests book canon → emits `RealityManifest` with `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (sparse opt-in)
2. **world-service RealityBootstrapper** validates manifest:
   - Stage 0 schema validation: actor_id ∈ canonical_actors; faction_id ∈ canonical_factions; score ∈ [-1000, +1000]; no duplicate rows; no synthetic actor; reality consistency
   - Stage 1: emit `ReputationBorn { actor_id, faction_id, initial_score }` per declared row
3. **REP_001 owner-service** writes `actor_faction_reputation` rows + emits EVT-T4 ReputationBorn events
4. Downstream features V1+ consume reputation:
   - V1+ NPC_002 Chorus Tier 4 priority modifier reads REP_001 for rival-faction NPCs
   - V1+ WA_001 AxiomDecl.requires_reputation Stage 4 lex_check
   - V1+ TIT_001 title-grant requires min rep
   - V1+ CULT_001 sect cultivation method requires min rep

---

## §11 Sequence: Canonical seed (Wuxia 3 declared rep)

```
RealityManifest {
    canonical_actor_faction_reputations: vec![
        ActorFactionReputationDecl {
            actor_id: "du_si",
            faction_id: "dong_hai_dao_coc",
            score: 250,
            canon_ref: Some(GlossaryEntityId("du_si_dong_hai_outer_disciple")),
        },
        ActorFactionReputationDecl {
            actor_id: "du_si",
            faction_id: "ma_tong",
            score: -300,                              // Hostile tier (-500..=-251)
            canon_ref: None,
        },
        ActorFactionReputationDecl {
            actor_id: "du_si",
            faction_id: "tay_son_phat_tu",
            score: 25,
            canon_ref: None,
        },
    ],
    // PC Lý Minh + Tiểu Thúy + Lão Ngũ have no entries → implicit Neutral default
}
```

**Validation flow:**
1. Stage 0 schema validation per row:
   - du_si ∈ canonical_actors → ✓
   - dong_hai_dao_coc ∈ canonical_factions → ✓
   - score=250 ∈ [-1000, +1000] → ✓
   - Not synthetic actor → ✓
   - Same reality → ✓
   - No duplicate (du_si, dong_hai_dao_coc) → ✓
2. RealityBootstrapper emits 3 EVT-T4 ReputationBorn events
3. REP_001 owner-service writes 3 rows to actor_faction_reputation
4. Causal-ref chain: bootstrap_event → ReputationBorn → row_insert

**Read examples post-bootstrap:**
- `read_rep("du_si", "dong_hai_dao_coc")` → score=+250, tier=Friendly (Đệ tử)
- `read_rep("du_si", "ma_tong")` → score=-300, tier=Hostile (Nghịch tặc)
- `read_rep("du_si", "tay_son_phat_tu")` → score=+25, tier=Neutral (Người lạ)
- `read_rep("ly_minh", "dong_hai_dao_coc")` → no row → unwrap_or(0) = score=0, tier=Neutral (Người lạ)
- `read_rep("tieu_thuy", "ma_tong")` → no row → unwrap_or(0) = score=0, tier=Neutral

**Authoring discipline:** Score must align with desired tier per Q3 thresholds (engine validates score range, not tier semantics). Wuxia narrative "Hostile rival sect" requires score ≤ -251; Du sĩ × Ma Tông uses -300 (mid-Hostile range) for narrative robustness. Author can fine-tune; rivalry baseline LOCKED via FAC_001 default_relations is independent of REP_001 score (author-set per actor).

---

## §12 Sequence: V1+ runtime delta (deferred — V1+ Q5+Q6+Q7 milestone)

```
// V1+ EXAMPLE (NOT V1 — deferred via REP-D1+D2+D3)
PC LM01 attacks Ma Tông cultivator via PL_005 Strike
  → PL_005 OutputDecl includes EVT-T3 Derived
  → REP_001 owner-service receives EVT-T3 with delta_kind=Delta
       { score_change: -200, source: "killed_member" }
  → owner-service reads existing rep (no row → score=0)
  → owner-service writes new row score=0+(-200)=-200, tier=Unfriendly
  → V1+ cascade per Q6 (REP-D2 if FactionDecl.rep_cascade_config present):
     → owner-service reads ma_tong.default_relations (Hostile to dong_hai)
     → owner-service emits CascadeDelta { score_change: +50 (attenuated 25%),
            source_event: <strike_evt>, source_faction: ma_tong }
     → +rep with dong_hai
  → V1+ NPC_002 Tier 4 priority modifier subscribes; updates rival-faction
       NPC priority cache
```

V1+ enrichment requires V1+30d additional design + boundary work.

---

## §13 Sequence: Forge admin SetReputation (V1 active)

```
Author types in Forge UI: "Lý Minh insults Đông Hải elder; rep -100"
  → Forge frontend emits POST /v1/forge/reputation/set
       { actor_id: "ly_minh", faction_id: "dong_hai_dao_coc",
         after_score: -100, reason: "insulted elder publicly" }
  → world-service Forge handler validates:
     - JWT has forge.admin claim
     - actor_id + faction_id valid
     - after_score ∈ [-1000, +1000]
     - actor not synthetic
  → 3-write atomic transaction:
     1. Read existing row → before_score=0 (no row, default)
     2. Write actor_faction_reputation row { score: -100, ... }
     3. Emit EVT-T8 Forge:SetReputation { actor_id, faction_id,
            before_score: 0, after_score: -100, reason }
     4. Write forge_audit_log entry referencing EVT-T8 event_id
  → AC-REP-7 covers atomicity (3-write transaction)
```

---

## §14 Sequence: Forge admin ResetReputation (V1 active)

```
Author types in Forge UI: "Lý Minh apologized publicly; reset Ma Tông rep"
  → Forge frontend emits POST /v1/forge/reputation/reset
       { actor_id: "ly_minh", faction_id: "ma_tong",
         reason: "public apology accepted" }
  → world-service Forge handler validates:
     - JWT has forge.admin claim
     - actor_id + faction_id valid
     - actor not synthetic
  → 3-write atomic transaction:
     1. Read existing row → before_score=-50 (existing row)
     2. Delete actor_faction_reputation row (back to implicit Neutral 0)
     3. Emit EVT-T8 Forge:ResetReputation { actor_id, faction_id,
            before_score: -50, reason }
     4. Write forge_audit_log entry referencing EVT-T8 event_id
  → AC-REP-8 covers reset atomicity
```

---

## §15 Acceptance criteria (LOCK gate)

V1 (8 testable scenarios):

| AC | Scenario | Expected outcome |
|---|---|---|
| **AC-REP-1** | Wuxia canonical bootstrap declares 3 rep rows (Du sĩ × Đông Hải +250 / Ma Tông -300 / Tây Sơn +25) | RealityBootstrapper emits 3 EVT-T4 ReputationBorn events; 3 rows written; sparse storage validated (~3 rows total V1; PC Lý Minh + Tiểu Thúy + Lão Ngũ have 0 rep rows) |
| **AC-REP-2** | Tier mapping computed correctly per Q3 thresholds | score=+250 → Friendly (Đệ tử); score=-300 → Hostile (Nghịch tặc); score=-100 → Neutral (boundary; -100 within Neutral range -100..=+100); score=0 → Neutral; score=+1000 → Exalted (Đại Thánh nhân); score=-1000 → Hated (Đại nghịch); boundary cases score=-251 → Hostile / score=-250 → Unfriendly enforce asymmetric threshold split |
| **AC-REP-3** | Sparse storage validated | PC Lý Minh has NO rep rows V1; `read_rep("ly_minh", any_faction)` → Neutral (score=0 default) per Q4 LOCKED |
| **AC-REP-4** | Score-out-of-range clamped silently per REP-A1 | Forge:SetReputation { after_score: 1500 } → engine clamps to 1000 (no reject; preserves narrative flow) |
| **AC-REP-5** | Unknown faction_id rejected at canonical seed | `reputation.unknown_faction_id` Stage 0 schema rejection |
| **AC-REP-6** | Unknown actor_id rejected at canonical seed | `reputation.unknown_actor_id` Stage 0 schema rejection |
| **AC-REP-7** | Forge admin SetReputation 3-write atomic | actor_faction_reputation row + EVT-T8 + forge_audit_log committed atomically; rollback if any fails |
| **AC-REP-8** | Forge admin ResetReputation 3-write atomic | row deletion + EVT-T8 + forge_audit_log committed atomically; subsequent read returns implicit Neutral |

V1+ deferred (4 scenarios):

| AC | Scenario | V1+ enrichment |
|---|---|---|
| **AC-REP-V1+1** | V1+ runtime delta event (PL_005 Strike on Đông Hải member → -100 rep) | REP-D1 V1+ runtime gameplay milestone |
| **AC-REP-V1+2** | V1+ cascade rep (Strike Ma Tông member → -rep with Ma Tông + +rep with Đông Hải via FAC_001 default_relations) | REP-D2 cascade enrichment |
| **AC-REP-V1+3** | V1+ decay tick (linear decay toward 0 per fiction-week) | REP-D3 decay enrichment |
| **AC-REP-V1+4** | V1+ author-declared per-faction tier display labels (FactionDecl.rep_tier_overrides) | REP-D4 tier override enrichment |

---

## §16 Boundary registrations (in same commit chain)

This DRAFT commit (2/4) adds the following boundary entries:

### `_boundaries/01_feature_ownership_matrix.md` (added)

- 1 NEW aggregate: `actor_faction_reputation` (REP_001 owner)
- 1 NEW EVT-T4 sub-type: `ReputationBorn` (REP_001 owner)
- 2 NEW EVT-T8 sub-shapes: `Forge:SetReputation` + `Forge:ResetReputation` (REP_001 owner; uses WA_003 forge_audit_log)
- 1 NEW EVT-T3 sub-types reserved V1+: 3 delta_kinds for `aggregate_type=actor_faction_reputation` (Delta + CascadeDelta + DecayTick)
- 1 NEW RealityManifest extension: `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (REP_001 owner; OPTIONAL V1)
- 1 NEW RejectReason namespace prefix: `reputation.*` → REP_001
- 1 NEW stable-ID prefix: `REP-*` (foundation tier — Tier 5 Actor Substrate post-FAC_001)

### `_boundaries/02_extension_contracts.md` (added)

- §1.4 namespace registration: `reputation.*` (6 V1 rules + 4 V1+ reservations)
- §2 RealityManifest extension: `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (OPTIONAL V1; sparse opt-in)

### `_boundaries/99_changelog.md` (added)

- Entry: REP_001 Reputation Foundation DRAFT promotion + boundary register

### `catalog/cat_00_REP_reputation_foundation.md` (created)

- New catalog file with REP-A1..A7 axioms + REP-D1..D17 deferrals + REP-Q1..Q10 decisions

### `features/00_reputation/_index.md` (updated)

- REP_001 row updated to DRAFT 2026-04-27

### Cross-feature coordination (deferred to commit 4/4 closure)

- FAC_001 closure pass extension marks FAC-D7 RESOLVED via REP_001
- Future PCS_001 PC creation form may set initial rep (V1+ default Neutral)

---

## §17 Open questions deferred + landing point

### V1+ deferrals (REP-D1..REP-D17)

| ID | Item | Landing point |
|---|---|---|
| **REP-D1** | V1+ runtime gameplay delta events (PL_005 Strike on faction member; Help/Quest reward; etc.) | Q5 V1+ runtime reputation milestone (REP-D1 + REP-D2 + REP-D3 + REP-D16 ALL ship together — coherent activation; partial activation creates broken state) |
| **REP-D2** | V1+ cascade rep via FAC_001 default_relations | Q6 V1+ enrichment; FactionDecl.rep_cascade_config additive (attenuation + max_depth + loop_prevention); ships with REP-D1 |
| **REP-D3** | V1+ decay over fiction-time | Q7 V1+ enrichment; FactionDecl.rep_decay_per_week additive + DecayTick EVT-T3; tick mechanism leverages AIT_001 tier scheduling (Tier 2 lazy decay; Tier 3 untracked = no decay); ships with REP-D1 |
| **REP-D4** | V1+ author-declared per-faction tier display labels | Q3 V1+ enrichment; FactionDecl.rep_tier_overrides: HashMap<i16, I18nBundle> |
| **REP-D5** | V2+ multi-axis reputation (CK3 Prestige + Piety) | RES_001 SocialKind expansion V2; schema migration `score: HashMap<SocialKind, i16>` |
| **REP-D6** | V2+ cross-reality migration | Q8 V2+ Heresy WA_002 |
| **REP-D7** | V1+ NPC_002 Tier 4 priority modifier integration | NPC_002 V1+ enrichment; reads REP_001 for rival-faction NPCs |
| **REP-D8** | V1+ WA_001 AxiomDecl.requires_reputation hook | WA_001 closure pass V1+ extension; AxiomDecl 4-companion-fields-uniform pattern (race + ideology + faction + reputation) |
| **REP-D9** ✅ V1 PARTIAL RESOLVED 2026-04-27 by TIT_001 V1 (CANDIDATE-LOCK; runtime gating remains V1+ alongside REP-D1) | V1+ TIT_001 title-grant requires min rep | TIT_001 V1 PARTIAL RESOLVES — TitleDecl.min_reputation_required: Option<MinRepGate> field schema-active V1 per Q4 C LOCKED (declarations stored at canonical seed + Forge admin); runtime validator V1+ alongside REP-D1 runtime delta milestone (when REP_001 ships runtime gameplay delta events, TIT-D2 runtime min_rep validator activates simultaneously). Schema-stable / activation-deferred V1+ discipline (TIT-A8). |
| **REP-D10** | V1+ CULT_001 sect cultivation method requires min rep | CULT_001 design when feature ships |
| **REP-D11** | V2+ DIPL_001 inter-faction war affects member rep cascade | DIPL_001 V2+ design |
| **REP-D12** | V2+ quest reward = REP_001 rep delta | 13_quests V2+ integration |
| **REP-D13** | V1+ rep as currency (burn rep for favor) | V2+ ECON feature |
| **REP-D14** | V1+ origin-pack default rep declaration | IDF_004 origin_pack.default_reputations enrichment |
| **REP-D15** | V1+ rep history audit trail | Separate aggregate vs event log query (analytics over rep changes) |
| **REP-D16** | V1+ Q4 hybrid default activation (Layer 2 membership-derived) | Ships alongside Q6 cascade enrichment (REP-D2); coupled coherence |
| **REP-D17** | V1+ RES_001 cross-cutting cleanup per Q10 LOCKED | Consider rename SocialCurrency::Reputation → Fame; add 11_cross_cutting/ documentation for L1/L2/L3 layer convention; RES_001 closure-pass §-cross-reference to REP_001 (doc-only additive edit) |

### Open questions (NONE V1)

All Q1-Q10 LOCKED via 5-batch deep-dive 2026-04-27 (1 REVISION on Q4). No outstanding V1 design questions.

---

## §18 Cross-references

### Resolved deferrals from upstream features

- **FAC-D7** (FAC_001 §17 deferrals) — Per-(actor, faction) reputation projection → ✅ RESOLVED via REP_001 actor_faction_reputation aggregate

### Consumes from locked features

- **EF_001 §5.1** ActorId source-of-truth — REP_001 aggregate key references ActorId
- **FAC_001 §3.1** FactionId source-of-truth — REP_001 aggregate key references FactionId; rep rows REQUIRE faction declared in canonical_factions
- **RES_001 §2.3** I18nBundle — REP_001 8-tier display labels use I18nBundle pattern (Wuxia VI + English EN per RES_001 §2 i18n contract)
- **RES_001 §3.2** SocialCurrency::Reputation — REP_001 §1 boundary discipline distinguishes 3 layers; REP_001 ≠ RES_001 SocialCurrency
- **NPC_001 §6** NpcOpinion — REP_001 §1 boundary discipline distinguishes; REP_001 ≠ NPC_001 NpcOpinion
- **WA_003** Forge audit log — REP_001 EVT-T8 sub-shapes use forge_audit_log pattern (3-write atomic)
- **07_event_model EVT-A10** event log = universal SSOT — REP_001 events flow in channel stream, no separate reputation_event_log aggregate

### Consumed by future features (V1+)

- **NPC_002 V1+** Tier 4 priority modifier — rival-faction NPCs read REP_001 for opinion baseline
- **WA_001 V1+** AxiomDecl.requires_reputation — sect-only abilities require min rep tier
- **TIT_001 V1+** title-grant requires min rep
- **CULT_001 V1+** sect cultivation method requires min rep
- **DIPL_001 V2+** inter-faction war affects rep cascade
- **13_quests V2+** quest reward = rep delta
- **PCS_001** PC creation form may set initial rep (V1+ default Neutral)

---

## §19 Implementation readiness checklist

- [ ] **§1** User story locked (Wuxia 3 rep + V1+ runtime examples)
- [ ] **§2** Domain concepts + REP-A1..A7 axioms locked
- [ ] **§2.5** Event-model mapping locked (EVT-T4 + EVT-T8 + V1+ EVT-T3 reserved)
- [ ] **§3** Aggregate inventory: 1 aggregate (actor_faction_reputation sparse)
- [ ] **§4** Tier+scope DP-R2 annotations
- [ ] **§5** DP primitives reuse standard
- [ ] **§6** Capability requirements: reuses WA_003 forge.admin JWT
- [ ] **§7** Subscribe pattern V1+ runtime
- [ ] **§8** Pattern choices: 9 sub-sections covering all Q1-Q10 LOCKED decisions
- [ ] **§9** Failure-mode UX: 6 V1 reject rules + 4 V1+ reservations + Wuxia I18n
- [ ] **§10** Cross-service handoff via standard RealityBootstrapper pipeline
- [ ] **§11** Sequence: Canonical seed (Wuxia 3 declared rep)
- [ ] **§12** Sequence: V1+ runtime delta (deferred V1+)
- [ ] **§13** Sequence: Forge admin SetReputation (V1 active)
- [ ] **§14** Sequence: Forge admin ResetReputation (V1 active)
- [ ] **§15** Acceptance criteria: 8 V1-testable AC-REP-1..8 + 4 V1+ deferred
- [ ] **§16** Boundary registrations (in same commit chain — this commit)
- [ ] **§17** Open questions deferred: 17 deferrals (REP-D1..REP-D17); 0 V1 open Q
- [ ] **§18** Cross-references: 1 RESOLVED upstream (FAC-D7) + 7 consumed-from + 7 consumed-by-future
- [ ] **§19** This checklist (filling at Phase 3 cleanup commit 3/4)

**Status transition:** DRAFT 2026-04-27 (commit 2/4 b2025a1) → Phase 3 cleanup applied (commit 3/4 b321f74) → **CANDIDATE-LOCK 2026-04-27** (commit 4/4 this commit) → **LOCK** when AC-REP-1..8 pass integration tests + V1+ scenarios after V1+ runtime reputation milestone ships.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold actor_faction_reputation aggregate + Forge admin handlers; V1+ NPC_002 Tier 4 priority + V1+ WA_001 requires_reputation hook + V1+ TIT_001 + V1+ CULT_001 consumers wire up. WA_001 closure pass V1+ adds AxiomDecl.requires_reputation field (4-companion-fields uniformly: requires_race + requires_ideology + requires_faction + requires_reputation).
