# PCS_001 PC Substrate — Concept Notes

> **Status:** CONCEPT 2026-04-27 — captures user framing + post-ACT_001+TDIL_001 reconciliation (PCS brief 8 sections audited; 2 ABSORBED by ACT_001, 1 POSSIBLY SUPERSEDED by PROG_001, 5 still PCS_001 V1 scope) + Q1-Q10 critical scope questions PENDING. Awaits user Q-deep-dive before DRAFT promotion.
>
> **Purpose:** Capture brainstorm + reconciliation analysis + Q1-Q10 for PCS_001 PC Substrate. The seed material for the eventual `PCS_001_pc_substrate.md` design.
>
> **Promotion gate:** When (a) Q1-Q10 LOCKED via deep-dive discussion, (b) `_boundaries/_LOCK.md` free → main session drafts `PCS_001_pc_substrate.md` with locked V1 scope, registers ownership, creates catalog file.

---

## §1 — User framing + origin signal

User direction 2026-04-27 picked P3 (PCS_001 PC Substrate cycle) per IDF folder closure roadmap (FF_001 → FAC_001 → REP_001 → ACT_001 → PCS_001 sequencing per Q2 LOCKED).

### Q2 LOCKED sequencing (from ACT_001 cycle 2026-04-27)

> **Q2 LOCKED 2026-04-27:** (A) Sequential — ACT_001 cycle → PCS_001 cycle on stable base.

ACT_001 closed CANDIDATE-LOCK (commit a1ce3c8); PCS_001 now starts on stable substrate.

### PCS_001 brief context

PCS_001 brief was commissioned 2026-04-25 by main session (`00_AGENT_BRIEF.md`) for parallel agent design. Brief is comprehensive (8 sections S1-S8) but written BEFORE these subsequent design refactors:

- IDF folder (5 features Race/Lang/Personality/Origin/Ideology) CANDIDATE-LOCK 2026-04-26
- FF_001 Family Foundation CANDIDATE-LOCK 2026-04-26
- FAC_001 Faction Foundation CANDIDATE-LOCK 2026-04-26
- REP_001 Reputation Foundation CANDIDATE-LOCK 2026-04-27
- PROG_001 Progression Foundation DRAFT 2026-04-26
- AIT_001 AI Tier Foundation DRAFT 2026-04-27
- ACT_001 Actor Foundation CANDIDATE-LOCK 2026-04-27 (UNIFICATION REFACTOR — absorbed PC persona model)
- TDIL_001 Time Dilation Foundation DRAFT 2026-04-27 (clock-split for xuyên không)

Reconciliation analysis required to identify what PCS_001 V1 STILL needs to design vs what's absorbed.

### Wuxia narrative requirements (primary V1 use case)

SPIKE_01 Lý Minh PC scenarios:
- **Lý Minh xuyên không** — soul of 2026 Saigon student in body of 1256 Hangzhou peasant
- **Turn 5 literacy slip** (SPIKE_01 obs#5) — Lý Minh body cannot read but soul knows Daoist scripture; quotes "Đạo Đức Kinh chú" → A6 canon-drift detection
- **Body-soul knowledge mismatch** — body has motor skills (manual labor, regional dialect Hangzhou); soul has cognitive knowledge (modern STEM, classical Chinese reading from school)
- **Mortality** — Lý Minh dies → V1+ Respawn at temple cell (per WA_006 mortality_config); V1 Permadeath default

### Multi-genre support post-V1

- **Modern detective**: PC = single body+soul aligned (no xuyên không); native PC pattern
- **Sci-fi possession**: V1+ multiple souls in one body (defer)
- **D&D party**: V1+ multi-PC charter coauthors (each PC own user binding)

---

## §2 — Reconciliation analysis: PCS_001 brief 8 sections post-ACT_001+TDIL_001

| Brief § | Topic | Post-refactor status | PCS_001 V1 scope |
|---|---|---|---|
| **§S1** PcId newtype + ActorId::Pc variant | Identity primitive | ⚠ ActorId::Pc reserved by EF_001 §5.1; PcId newtype itself still needs definition | ✅ V1 PCS_001 owns PcId(uuid) + module-private constructor (DP-A12 pattern) |
| **§S2** PC persona model (canonical_traits + flexible_state + knowledge_tags + voice_register) | Persona | ✅ ABSORBED by ACT_001 `actor_core` (B1 LOCKED multi-axis ActorMood + B2 LOCKED FlexibleState typed standard fields) | ❌ NOT in PCS_001 V1 (delegated to ACT_001) |
| **§S3** PC body-memory model xuyên không (SoulLayer + BodyLayer + LeakagePolicy) | Novel design | ⚠ PC-only mechanic; not absorbed by ACT_001; integrates with TDIL_001 §10 clock-split | ✅ V1 PCS_001 owns (CORE NOVEL DESIGN) |
| **§S4** `pc_mortality_state` aggregate (Alive/Dying/Dead/Ghost) | Mortality | ⚠ WA_006 closure-pass-extension already handed off ownership to PCS_001 (commit f436e60); aggregate body still needs design | ✅ V1 PCS_001 owns |
| **§S5** PC stats foundation V1 stub (HP + status_flags) | Combat stub | ⚠ PROG_001 SUPERSEDED DF7 placeholder per PROG_001 DRAFT (commit a76a4e4 mention); but combat hot-path may still need stats stub for fast lookup | ⚠ Q-decision pending (Q4); may defer or keep simplified |
| **§S6** PC-NPC relationship read-side (PcSocialMap trait) | Read interface | ✅ ABSORBED by ACT_001 `actor_actor_opinion` (bilateral; ActorOpinion::for_target replaces NpcOpinion::for_pc) | ❌ NOT in PCS_001 V1 (delegated to ACT_001) |
| **§S7** Acceptance criteria | Test scenarios | ⚠ Still needed; aligned with revised V1 scope post-reconciliation | ✅ V1 PCS_001 owns ~10 V1-testable AC |
| **§S8** Xuyên không body-substitution + cell-ownership inheritance | Event sequence | ⚠ PC-specific; integrates with TDIL_001 §10 clock-split + RES_001 §5.3 body-bound resource inheritance | ✅ V1 PCS_001 owns (event flow + cross-feature integration) |

### Net V1 PCS_001 scope (post-reconciliation)

- **3 aggregates V1** (down from brief's 5):
  1. `pc_user_binding` (T2/Reality, sparse PC-only) — user_id + current_session + body_memory
  2. `pc_mortality_state` (T2/Reality, sparse PC-only) — Alive/Dying/Dead/Ghost
  3. (Q-decision Q4) `pc_stats_v1_stub` (TBD — kept simplified or deferred V1+)
- **Identity primitives**:
  - PcId newtype (Q-decision Q1 — uuid pattern matching NpcId)
- **Schemas**:
  - PcBodyMemory (SoulLayer + BodyLayer + LeakagePolicy) — Q5+Q6 deep-dive
- **Events**:
  - 1 EVT-T1 PcXuyenKhongCompleted (xuyên không transition; integrates TDIL_001 clock-split)
  - 4 EVT-T8 Forge sub-shapes (Forge:RegisterPc + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState)
- **Namespace**: `pc.*` (~6-8 V1 reject rules)
- **RealityManifest extension**: PC creation pathway (canonical seed + V1+ runtime login + V1 Forge admin)
- **Stable-ID prefix**: `PCS-*` (catalog cat_06_PCS_pc_systems.md already exists)

---

## §3 — 3-layer architectural model post-ACT_001 (PCS_001 fits where?)

Per ACT_001 §1 + ACT-A2 LOCKED 3-layer model:

| Layer | Concept | PCS_001 contribution |
|---|---|---|
| **L1 Identity** | actor_core (always present post-creation) | NONE — ACT_001 owns identity unified across PC + NPC |
| **L2 Capability/Kind** | ActorId::Pc / ActorId::Npc / ActorId::Synthetic (encoded in ActorId variant; stable post-creation) | PCS_001 owns PcId newtype (the variant data); ActorKind::Pc discriminator EF_001-owned |
| **L3 Control source** | DYNAMIC (User / AI / Engine); sparse aggregate population | PCS_001 owns `pc_user_binding` (User control state); PCS_001 owns `pc_mortality_state` (lifecycle state); PCS_001 owns `body_memory` (xuyên không discriminator) |

**Insight:** PCS_001 is **pure L3 PC-specific behavior layer** post-ACT_001 unification. Identity (L1) is unified; PCS_001 only adds PC-specific extensions.

This explains the scope reduction (5 → 3 aggregates): persona (S2) lifted to L1; relationship-read (S6) lifted to L1.

---

## §4 — Q1-Q10 critical scope questions (PENDING — for user deep-dive)

These determine V1 scope. NOT yet locked. User confirmation needed before DRAFT promotion.

### Q1 — `PcId` newtype shape?

**Question:** PcId newtype matches NpcId pattern (uuid)?

**Options:**
- (A) `pub struct PcId(pub Uuid)` — mirror NpcId; module-private constructor (DP-A12)
- (B) `pub struct PcId(pub String)` — mirror RaceId (opaque string); user-readable
- (C) Composite ID (user_id + reality_id + seq) — multi-user discrimination

**Recommendation:** (A) Uuid; mirror NpcId pattern; module-private constructor for forge-controlled creation.

### Q2 — `pc_user_binding` aggregate shape (single vs split)?

**Question:** Single aggregate (user_id + current_session + body_memory) or split into 2-3 aggregates?

**Options:**
- (A) Single `pc_user_binding` aggregate — all 3 fields together; per-PC row
- (B) Split into 2 — `pc_user_binding` (user_id + current_session) + `pc_body_memory` (xuyên không soul/body)
- (C) Split into 3 — `pc_user_binding` (user_id only) + `pc_session_state` (current_session) + `pc_body_memory`

**Recommendation:** (A) Single aggregate V1 — cohesive PC-specific data; sparse per-PC; matches FAC_001 simple aggregate pattern. V1+ split if pain emerges.

### Q3 — PC creation pathway?

**Question:** How does PC get created at canonical seed + runtime?

**Options:**
- (A) Canonical seed only V1 — Lý Minh declared in RealityManifest.canonical_actors (PC kind); user_id binding deferred to runtime login
- (B) Runtime login flow only V1 — PC creation form (interactive UI); no canonical seed PC declarations
- (C) Both V1 — canonical seed declares PCs (kind=Pc + spawn_cell); runtime login binds user_id to existing PC actor_id
- (D) Forge admin V1 — author-driven PC creation via Forge:RegisterPc

**Recommendation:** (C) Both V1 — canonical seed creates PC actor_core + pc_user_binding (user_id=None initially); runtime login flow binds user_id when PC is "claimed" by user. SPIKE_01 Lý Minh canonical declared. Multi-PC charter coauthor V1+ supports multi-user.

### Q4 — `pc_stats_v1_stub` aggregate kept or deferred?

**Question:** PROG_001 actor_progression supersedes DF7 placeholder per PROG_001 DRAFT note. Does PCS_001 still need separate pc_stats_v1_stub aggregate?

**Options:**
- (A) Keep `pc_stats_v1_stub` V1 — combat hot-path needs fast HP + status_flags lookup (per brief §S5)
- (B) Defer V1+ — PROG_001 actor_progression covers HP via vital_pool (RES_001) + status via PL_006 actor_status; PCS_001 doesn't add V1 aggregate
- (C) Hybrid — PCS_001 V1 does NOT add stats aggregate; consumes existing RES_001 vital_pool (HP) + PL_006 actor_status (status_flags)

**Recommendation:** (B) Defer V1+ — PROG_001 + RES_001 + PL_006 together cover stats stub semantics; redundant aggregate adds storage cost. PCS_001 V1 = 2 aggregates instead of 3 (pc_user_binding + pc_mortality_state).

### Q5 — `body_memory` schema V1 (full SoulLayer + BodyLayer + LeakagePolicy)?

**Question:** Brief §S3 defines full schema. V1 ships full or simplified?

**Options:**
- (A) Full V1 per brief §S3 — SoulLayer (origin_world_ref + knowledge_tags + native_skills) + BodyLayer (host_body_ref + knowledge_tags + motor_skills + native_language) + LeakagePolicy (4-variant)
- (B) V1 minimal — SoulLayer.knowledge_tags + BodyLayer.knowledge_tags only (drives A6 canon-drift V1+); LeakagePolicy V1+ enrichment
- (C) V1+ deferred entirely — V1 PC = native (no xuyên không); xuyên không V1+ feature

**Recommendation:** (A) Full V1 — SPIKE_01 Lý Minh requires full schema for canonical reproducibility (turn 5 literacy slip). LeakagePolicy 4-variant matches brief; can simplify to 2-variant V1 if scope-creep concerns. Defer V1+ enrichments (Reincarnation / Possession variants per brief §S3).

### Q6 — `LeakagePolicy` enum variants?

**Question:** Brief §S3 lists 4 variants. V1 ships all 4?

**Options:**
- (A) Full 4-variant V1 — NoLeakage / SoulPrimary { body_blurts_threshold } / BodyPrimary { soul_slips_threshold } / Balanced
- (B) 2-variant V1 — NoLeakage / SoulPrimary; defer BodyPrimary + Balanced V1+
- (C) Single boolean V1 — `is_transmigrator: bool`; threshold/balance V1+ enrichment

**Recommendation:** (A) Full 4-variant — SPIKE_01 Lý Minh = SoulPrimary; SPIKE_01 turn 5 literacy slip = body_blurts_threshold detection; full schema enables A6 detector V1+ integration. Brief §S3 already designed this carefully.

### Q7 — `pc_mortality_state` state machine V1?

**Question:** V1 simple (Alive/Dying/Dead) or full (Alive/Dying/Dead/Ghost)?

**Options:**
- (A) Full 4-state V1 per brief §S4 — Alive / Dying { will_respawn_at_fiction_time, spawn_cell } / Dead { died_at_turn, died_at_cell } / Ghost
- (B) V1 simple 3-state — Alive / Dying / Dead; Ghost V1+ deferred
- (C) V1 minimal 2-state — Alive / Dead; mortality flow via WA_006 mortality_config

**Recommendation:** (A) Full 4-state — Wuxia narrative supports Ghost (oan hồn ngạ quỷ; ghost wandering after unjust death); V1+ Respawn flow needs Dying state with respawn_at_fiction_time. Brief §S4 designed this.

### Q8 — Cross-reality PC migration V1 vs V2+ Heresy?

**Question:** Can PC migrate across realities? (Universal substrate discipline established at IDF + FF + FAC + REP + ACT.)

**Options:**
- (A) V1 strict single-reality; V2+ Heresy migration via WA_002
- (B) V1 PC migration permitted (xuyên không cross-reality V1)

**Recommendation:** (A) V1 strict — universal discipline (IDF + FF + FAC + REP + ACT all locked V2+). Note: xuyên không V1 SPIKE_01 is single-reality (Lý Minh's soul came from 2026-Saigon to 1256-Hangzhou but BOTH are realities; if treated as 2 realities then V2+ Heresy is needed). Q-decision needs clarification: SPIKE_01 = single-reality (Lý Minh's "origin world" is a separate REFERENCE not active reality V1) or 2-reality V2+?

### Q9 — Multi-PC reality V1 cap?

**Question:** Single PC per reality V1 (SPIKE_01 only Lý Minh)? Or multi-PC V1 for charter coauthors?

**Options:**
- (A) V1 cap=1 PC per reality — single PC narrative; multi-PC V1+ for charter coauthors
- (B) V1 multi-PC — charter coauthors each own PC; V1 supports
- (C) V1 cap=1 + Vec<PcId> on reality with V1 validator (mirror FAC_001 Q2 pattern)

**Recommendation:** (C) Vec<PcId> with V1 cap=1 validator — schema future-proofs multi-PC charter coauthors; V1 enforces single PC; V1+ validator relax = no schema migration. Matches FAC_001 Q2 REVISION pattern.

### Q10 — Xuyên không TDIL_001 clock-split integration?

**Question:** PCS_001 §S8 PcXuyenKhongCompleted event triggers TDIL_001 clock-split (soul_clock follows soul; body_clock follows body; actor_clock=0 reset)?

**Options:**
- (A) PcXuyenKhongCompleted EVT-T1 emits → TDIL_001 actor_clocks aggregate consumes → splits clocks per TDIL §10
- (B) PCS_001 directly writes actor_clocks (cross-aggregate write at xuyên không event)
- (C) Two-stage event flow — PCS_001 emits PcXuyenKhongCompleted → TDIL_001 emits ActorClockSplit follow-up event → actor_clocks updated

**Recommendation:** (A) Single event PcXuyenKhongCompleted; TDIL_001 actor_clocks subscribes to EVT-T1 and updates per TDIL §10 contract. Single event simpler; aggregate-owner (TDIL) writes its own aggregate.

---

## §5 — Boundary intersection summary

When PCS_001 DRAFT lands, these boundaries need careful handling:

| Touched feature | Status | PCS_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| ACT_001 Actor Foundation | CANDIDATE-LOCK | (none) | actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory | PCS_001 reads actor_core for PC identity; PC pc_user_binding REQUIRES corresponding actor_core row |
| EF_001 Entity Foundation | CANDIDATE-LOCK | (none) | entity_binding + EntityKind | PCS_001 reads ActorId::Pc(PcId); EntityKind::Pc trait impl |
| WA_006 Mortality | CANDIDATE-LOCK | `pc_mortality_state` aggregate (handoff received) | mortality_config (per-reality singleton) | PCS_001 OWNS aggregate; WA_006 owns config; cross-feature flow at death event |
| WA_003 Forge | CANDIDATE-LOCK | (none — PCS_001 declares own AdminAction sub-shapes) | forge_audit_log + AdminAction enum | PCS_001 adds 4 EVT-T8 sub-shapes |
| RES_001 Resource | DRAFT | (none) | vital_pool + resource_inventory | PC consumes vital_pool HP via PROG_001; PC inventory follows actor_id |
| PROG_001 Progression | DRAFT | (none) | actor_progression | PC consumes actor_progression for stats; supersedes pc_stats_v1_stub V1+ per Q4 |
| PL_006 Status | CANDIDATE-LOCK | (none) | actor_status | PC status_flags read from actor_status (kind-agnostic per PL_006) |
| TDIL_001 Time Dilation | DRAFT 2026-04-27 | (none) | actor_clocks (3 clocks) | PCS_001 PcXuyenKhongCompleted triggers TDIL_001 clock-split per Q10 |
| AIT_001 AI Tier | DRAFT 2026-04-27 | (none) | tier semantics | PC always Tier 0 (eager full simulation); not subject to NPC tiering |
| auth-service | external | (none — user_id is auth-service ref) | user_id namespace | PCS_001 user_id field references auth-service identity |
| 03_player_onboarding (PO_001) | not started | (none — PCS_001 owns PC substrate; PO_001 owns onboarding flow UI) | PC creation form UI | PO_001 V1+ feature consumes PCS_001 PC primitives |
| 07_event_model | LOCKED | EVT-T1 Submitted sub-type (PcXuyenKhongCompleted) + EVT-T8 Administrative (4 Forge sub-shapes) | Event taxonomy | Per EVT-A11 sub-type ownership |
| RealityManifest envelope | unowned | PC entries in canonical_actors with pc-specific fields (kind=Pc + body_memory init) | Envelope contract | Additive on CanonicalActorDecl |
| `pc.*` rule_id namespace | not yet registered | All PC RejectReason variants | RejectReason envelope (Continuum) | Per `02_extension_contracts.md` §1.4 — register at PCS_001 DRAFT |
| Future PO_001 Player Onboarding | not started | (none) | Onboarding UI flow | V1+ PC creation form via PO_001 consumes PCS_001 |
| Future combat / DF7 | V2+ deferred | (none) | Combat damage law chain | PROG_001 strike_formula V1; full V2+ DF7 |
| Future A6 canon-drift detector | not started | (none — PCS_001 supplies body_memory schema) | A6 detection algorithm in 05_llm_safety | A6 V1+ reads body_memory.body.knowledge_tags vs body_memory.soul.knowledge_tags for SPIKE_01 turn 5 literacy slip |

---

## §6 — Reference materials placeholder

User stated 2026-04-27: may provide reference sources (per RES_001 + IDF + FF_001 + FAC_001 + REP_001 + ACT_001 pattern). PCS_001 follows same template.

When references arrive:
1. Capture verbatim
2. Cross-reference with main session knowledge (already in `01_REFERENCE_GAMES_SURVEY.md` companion)
3. Update Q1-Q10 recommendations + lock LOCKED decisions

**Status:** awaiting user input.

---

## §7 — V1 scope (PROVISIONAL — pending Q-deep-dive)

This section will be LOCKED after Q1-Q10 confirmed. Provisional V1 scope below assuming recommendations approved as-is:

### V1 aggregates (2; potentially 3 per Q4)

1. **`pc_user_binding`** (T2/Reality, sparse PC-only)
   - pc_id (PcId; FK to actor_core via ActorId::Pc) + user_id (Option<UserId>; auth-service ref) + current_session (Option<SessionId>) + body_memory (PcBodyMemory)
   - **Mutable** via canonical seed (PcRegistered) + Forge admin (Forge:EditPcUserBinding + Forge:EditBodyMemory) + runtime login/logout (V1+ AI-controls-PC-offline) + xuyên không event (PcXuyenKhongCompleted)
   - Synthetic actors forbidden V1
   - Cross-reality forbidden V1 (V2+ Heresy)

2. **`pc_mortality_state`** (T2/Reality, sparse PC-only — handoff from WA_006)
   - pc_id + state (MortalityStateValue: Alive / Dying { will_respawn_at_fiction_time, spawn_cell } / Dead { died_at_turn, died_at_cell } / Ghost) + last_transition_at_turn + history (Vec<MortalityTransition>)
   - **Mutable** via mortality events (DyingTransition / DeathTransition / GhostTransition / RespawnTransition V1+) + Forge admin (Forge:EditPcMortalityState)

3. **(Q4 PENDING)** `pc_stats_v1_stub` — POSSIBLY DEFERRED V1+ pending Q4 LOCKED decision

### PcBodyMemory schema (Q5+Q6 PENDING)

```rust
pub struct PcBodyMemory {
    pub soul: SoulLayer,
    pub body: BodyLayer,
    pub leakage_policy: LeakagePolicy,
}

pub struct SoulLayer {
    pub origin_world_ref: Option<RealityRef>,        // None = native (no xuyên không)
    pub knowledge_tags: Vec<KnowledgeTag>,           // soul brought knowledge
    pub native_skills: Vec<SkillRef>,                // mind-skills (academic, languages)
}

pub struct BodyLayer {
    pub host_body_ref: BodyRef,                      // canonical body from this reality
    pub knowledge_tags: Vec<KnowledgeTag>,           // body retains knowledge from former occupant
    pub motor_skills: Vec<SkillRef>,                 // motor-skills (combat, crafts)
    pub native_language: LanguageRef,
}

pub enum LeakagePolicy {                              // (Q6 PENDING — full 4-variant proposed)
    NoLeakage,                                       // V1 default for native PC
    SoulPrimary { body_blurts_threshold: f32 },      // body sometimes leaks; soul controls
    BodyPrimary { soul_slips_threshold: f32 },       // body controls but soul instinct slips
    Balanced,                                        // both layers contribute equally
}
```

### V1 events (in channel stream per EVT-A10)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| PC declared at canonical seed | **EVT-T4 System** | uses ACT_001 ActorBorn (kind=Pc) + PCS_001 follows with pc_user_binding init | Bootstrap | ✓ V1 (ACT_001 absorbs ActorBorn) |
| PC user-binding registered | **EVT-T8 Administrative** | `Forge:RegisterPc { pc_id, user_id, body_memory_init }` | Forge | ✓ V1 |
| PC user-binding edited | **EVT-T8 Administrative** | `Forge:EditPcUserBinding { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| PC body memory edited | **EVT-T8 Administrative** | `Forge:EditBodyMemory { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| PC mortality state edited | **EVT-T8 Administrative** | `Forge:EditPcMortalityState { pc_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| PC xuyên không completed | **EVT-T1 Submitted** | `PcXuyenKhongCompleted { old_actor_id, new_pc_id, body_actor_id, soul_origin_ref, ... }` | World-service (xuyên không transition) | ✓ V1 (per Q10 LOCKED) |
| PC mortality transition (V1 events from WA_006) | **EVT-T3 Derived** | `aggregate_type=pc_mortality_state` + delta_kinds (DyingTransition / DeathTransition / GhostTransition) | Aggregate-Owner (PCS_001 owner-service); WA_006 mortality_config consumes | ✓ V1 |
| PC respawn transition | **EVT-T3 Derived** | `delta_kind=RespawnTransition` | Aggregate-Owner | V1+ (Q7 RespawnFlow) |
| PC offline session change (V1+) | **EVT-T3 Derived** | `delta_kind=SessionChange` | Aggregate-Owner | V1+ (AI-controls-PC-offline ACT-D1) |

### V1 `pc.*` reject rule_ids (proposed; finalized at DRAFT)

V1 rules:
1. `pc.unknown_pc_id` — Stage 0 schema (pc_id not in pc_user_binding)
2. `pc.synthetic_actor_forbidden` — Stage 0 schema (consistent universal discipline)
3. `pc.cross_reality_mismatch` — Stage 0 schema (V2+ Heresy reservation)
4. `pc.invalid_xuyenkhong_combination` — Stage 0 schema (soul/body inconsistency at PcXuyenKhongCompleted; e.g., soul knowledge_tags overlap body knowledge_tags inconsistently)
5. `pc.user_id_already_bound` — Stage 0 schema (one user_id can't bind to multi PCs V1 cap=1)
6. `pc.mortality_invalid_transition` — Stage 0 schema (e.g., Dead → Alive without RespawnTransition)
7. `pc.multi_pc_per_reality_forbidden_v1` — Stage 0 schema (per Q9 cap=1 V1 validator)

V1+ reservations:
- `pc.runtime_login_unsupported_v1` (V1+ when PC creation form ships per Q3)
- `pc.respawn_unsupported_v1` (V1+ when respawn flow ships per Q7)
- `pc.body_substitution_unsupported_v1` (V1+ when full xuyên không runtime ships beyond canonical seed)

### V1 RealityManifest extensions

V1 adds PC-specific fields to CanonicalActorDecl (already ACT_001-owned post-unify):
- `body_memory_init: Option<PcBodyMemory>` — PC declarations (kind=Pc) MAY include initial body memory state; PCs without xuyên không init = None (defaults to NoLeakage policy + body=soul aligned)
- `user_id_init: Option<UserId>` — V1 typically None at canonical seed; user binds at runtime login

V1 user-message envelope: `RejectReason.user_message: I18nBundle` per RES_001 §2 i18n contract.

### V1 acceptance criteria (proposed; ~10 V1-testable)

V1:
- AC-PCS-1: Wuxia canonical bootstrap declares Lý Minh PC with kind=Pc + body_memory_init Some(SoulPrimary{...}) → actor_core row + pc_user_binding row written
- AC-PCS-2: Lý Minh xuyên không SoulLayer.knowledge_tags=["modern_stem", "classical_chinese_reading"] + BodyLayer.knowledge_tags=["regional_hangzhou_dialect", "manual_labor"] → A6 V1+ detector reads schema correctly
- AC-PCS-3: SPIKE_01 turn 5 literacy slip reproducible — Lý Minh body cannot read but soul leaks knowledge → SoulPrimary { body_blurts_threshold } triggers
- AC-PCS-4: Multi-PC reality rejected V1 (`pc.multi_pc_per_reality_forbidden_v1`)
- AC-PCS-5: Synthetic actor PC rejected (`pc.synthetic_actor_forbidden`)
- AC-PCS-6: Cross-reality PC migration rejected (`pc.cross_reality_mismatch`)
- AC-PCS-7: Forge admin RegisterPc 3-write atomic
- AC-PCS-8: Mortality transition Alive → Dying validated
- AC-PCS-9: PcXuyenKhongCompleted event emit triggers TDIL_001 clock-split (soul_clock + body_clock + actor_clock=0)
- AC-PCS-10: PcId newtype module-private constructor enforced (DP-A12 pattern)

V1+ deferred:
- AC-PCS-V1+1: V1+ runtime login flow PC creation
- AC-PCS-V1+2: V1+ Respawn transition (Dying → Alive at fiction_time + spawn_cell)
- AC-PCS-V1+3: V1+ AI-controls-PC-offline activates actor_chorus_metadata for PC
- AC-PCS-V1+4: V1+ multi-PC reality (charter coauthors)

### V1 deferrals (proposed; finalized at DRAFT)

- PCS-D1: V1+ runtime login flow PC creation (Q3 enrichment)
- PCS-D2: V1+ Respawn transition flow (Q7 enrichment)
- PCS-D3: V1+ multi-PC reality cap relax (Q9 single-line validator change)
- PCS-D4: V1+ PROG_001 actor_progression integration replaces pc_stats_v1_stub (Q4)
- PCS-D5: V1+ AI-controls-PC-offline activates pc_user_binding.current_session = None + actor_chorus_metadata population (cross-ref ACT-D1)
- PCS-D6: V2+ cross-reality PC migration via WA_002 Heresy (Q8)
- PCS-D7: V1+ A6 canon-drift detector reads body_memory.{soul, body}.knowledge_tags (V1+ 05_llm_safety integration)
- PCS-D8: V1+ Reincarnation pattern (body resets each death; soul preserves)
- PCS-D9: V1+ Possession pattern (temporary occupation by another soul)
- PCS-D10: V1+ PO_001 Player Onboarding integration (UI flow consumes PCS_001 primitives)

### V1 quantitative summary (provisional)

- 2 PCS_001 aggregates (pc_user_binding + pc_mortality_state); Q4 may add 3rd or defer
- 1 EVT-T1 PcXuyenKhongCompleted event sub-type
- 4 EVT-T8 Forge sub-shapes (RegisterPc + EditPcUserBinding + EditBodyMemory + EditPcMortalityState)
- 7 V1 reject rule_ids in `pc.*` namespace + 3 V1+ reservations
- 2 RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init); both Optional
- PcBodyMemory schema (3 nested types: SoulLayer + BodyLayer + LeakagePolicy)
- 10 V1 AC + 4 V1+ deferred
- 10 deferrals (PCS-D1..PCS-D10)
- ~700-900 line DRAFT spec estimate
- 4-commit cycle (Phase 0 this commit + DRAFT 2/4 + Phase 3 3/4 + closure+release 4/4)

---

## §8 — What this concept-notes file is NOT

- ❌ NOT the formal PCS_001 design (no full Rust struct definitions, no full §1-§N spec structure, no full acceptance criteria)
- ❌ NOT a lock-claim trigger (commit 2/4 will claim)
- ❌ NOT registered in ownership matrix yet
- ❌ NOT consumed by other features yet (WA_006 closure still references future PCS_001 owner)
- ❌ NOT prematurely V1-scope-locked (Q1-Q10 OPEN; recommendations pending)

---

## §9 — Promotion checklist (when Q1-Q10 answered + references reviewed)

Before drafting `PCS_001_pc_substrate.md`:

1. [ ] User reviews market survey + provides additional references if any
2. [ ] User answers Q1-Q10 (or approves recommendations after deep-dive)
3. [ ] Update §7 V1 scope based on locked decisions
4. [ ] Wait for `_boundaries/_LOCK.md` to be free
5. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
6. [ ] Create `PCS_001_pc_substrate.md` with full §1-§N spec
7. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add 2-3 aggregates + EVT sub-types + namespace + PCS-* prefix
8. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 + §2 (CanonicalActorDecl additive fields)
9. [ ] Update `_boundaries/99_changelog.md` — append entry
10. [ ] Update `catalog/cat_06_PCS_pc_systems.md` — fill catalog entries
11. [ ] Update `06_pc_systems/_index.md` — replace concept row with PCS_001 DRAFT row
12. [ ] Coordinate with WA_006 closure pass extension to mark pc_mortality_state handoff RESOLVED
13. [ ] Coordinate with TDIL_001 to confirm Q10 PcXuyenKhongCompleted clock-split contract
14. [ ] Release `_boundaries/_LOCK.md`
15. [ ] Commit cycle (Phase 0 this commit + DRAFT 2/4 + Phase 3 3/4 + closure+release 4/4)

---

## §10 — Status

- **Created:** 2026-04-27 by main session (commit 1/4 this turn)
- **Phase:** CONCEPT — awaiting Q1-Q10 deep-dive + market survey review
- **Lock state:** `_boundaries/_LOCK.md` FREE (last released by ACT_001 Phase 2 P2 closure 2026-04-27 commit f4d0258)
- **Estimated time to DRAFT 2/4:** 3-5 hours focused design work (~700-900 line spec; smaller than ACT_001's ~1000 since 2-3 aggregates only + L3 PC-specific only)
- **Co-design dependencies (when DRAFT):**
  - WA_006 closure pass extension confirms pc_mortality_state handoff
  - TDIL_001 confirms PcXuyenKhongCompleted → actor_clocks split contract
  - ACT_001 actor_core stable base (CANDIDATE-LOCK 2026-04-27)
- **Next action:** User reviews reference survey + answers Q1-Q10 (or approves recommendations) → DRAFT promotion when lock free
