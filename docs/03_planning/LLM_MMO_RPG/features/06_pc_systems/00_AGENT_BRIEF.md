# 00 — Agent Brief: PCS_001 PC Substrate (parallel work commission)

> **Status:** LOCKED brief. Issued 2026-04-25 by the main session that designed Continuum (PL_001/PL_001b) + NPC foundation (NPC_001/NPC_002) + WA closure pass (WA_001..006). The agent receiving this brief is expected to design `06_pc_systems/PCS_001_*.md` with the depth + discipline established by NPC_001 Cast precedent.
>
> **Read order before starting:** §0 Identity → §1 Why → §2 IN scope → §3 OUT of scope → §4 Required reading → §5 Phase plan → §6 Stable ID namespace → §7 Process discipline → §8 Coordination → §9 Success criteria → §10 First-session deliverable → Appendix A SPIKE_01 grounding.

---

## §0 — Your identity for this work

You are the **PCS PC-substrate design agent**. You own `docs/03_planning/LLM_MMO_RPG/features/06_pc_systems/` end-to-end. You are NOT the same agent that designed the kernel layers (06_data_plane LOCKED, 07_event_model in progress), the world layer (Continuum / Lex / Heresy / Forge / Mortality), or NPC foundation (Cast / Chorus). You design the **PC side** of the inhabitants pair (NPC ↔ PC).

**Output language:** English (matches existing feature design convention). User-facing summaries / commit messages may include Vietnamese annotations.

**User communicates in:** Vietnamese + English mixed.

---

## §1 — Why this work exists

Many features designed during 2026-04-25 reference PCs but defer the PC substrate to a future agent:

| Feature | Reference / Hand-off |
|---|---|
| **NPC_001 Cast** §2 | Reserved `ActorId::Pc(PcId)` variant; `PcId` newtype itself deferred to PCS_001 |
| **NPC_001 Cast** §3.3 | `npc_pc_relationship_projection` references `pc_id: PcId`; PC-side READ view deferred |
| **NPC_001 Cast** §6.4 | Persona memory-fact selection assumes `PcId` is identifiable + comparable |
| **WA_006 Mortality** thin-rewrite | `pc_mortality_state` aggregate ownership EXPLICITLY HANDED OFF from WA_006 to PCS_001 (per WA closure pass) |
| **WA_003 Forge** §7.3 | Per-PC overrides in `MortalityConfig.per_pc_overrides` reference `pc_id: PcId` |
| **PL_001 Continuum** §3.6 | `entity_binding.actor: ActorId` includes `Pc(PcId)`; runtime location lookup needs PcId |
| **PL_002 Grammar** §3.1 | Tool-call allowlist for `actor_type=PC` references PC concept abstractly |
| **NPC_002 Chorus** §6 | Priority algorithm reads `NpcOpinion::for_pc(npc_id, pc_id)`; PC-side identity required |
| **SPIKE_01** obs#5 | Lý Minh xuyên không (soul=2026 Saigon student, body=1256 Hàng Châu peasant) — concrete PC scenario UNDESIGNED at data-model level |

**The gap is real and V1-blocking.** Without PCS_001:
- Cannot type `ActorId::Pc(_)` in Rust — compile error
- Mortality state aggregate has no owner — WA_006 closure pass-through is incomplete
- LLM persona assembly cannot identify PCs vs NPCs in scene roster
- SPIKE_01 turn 5 literacy slip cannot be reproduced (no body-memory model)
- Forge per-PC overrides cannot validate `pc_id` references

The main session SHOULD HAVE deferred PCS_001 to a separate agent from the start (matching the precedent set by 07_event_model agent). Instead, after WA closure the main session almost designed PCS_001 inline — the user caught the session-scope boundary issue and requested PCS_001 be split off to a parallel agent.

That is you.

---

## §2 — IN scope (you MUST design these)

PCS_001 is a single feature design (not a multi-phase folder like 07_event_model). Target: ~600-700 lines, mirrors NPC_001 Cast structure.

### S1. PcId newtype + ActorId::Pc variant

```rust
// Mirror NpcId from NPC_001 §2 + RealityId from DP-K1
pub struct PcId(pub Uuid);
// Module-private constructor (DP-A12 pattern)
impl PcId { pub(crate) fn new_verified(uuid: Uuid) -> Self { Self(uuid) } }
```

NPC_001 §2 reserved the `ActorId::Pc(PcId)` variant. PCS_001 owns the `PcId` type itself. Authentication / user-account binding is auth-service territory; PCS_001 just owns the per-reality PC identity.

### S2. PC persona model

Parallel to NPC persona at 02_storage R8:
- **canonical_traits** — name, role, voice register, physical description (immutable post-create)
- **flexible_state** — emotional state, mood, opinions, relationships drift; mutable
- **knowledge_tags** — closed set of strings (e.g., "modern_tech", "wuxia_lore", "scholar_canon") — used by 05_llm_safety A6 canon-drift detection AND by NPC_002 Chorus Tier-3 priority
- **voice_register** — `enum { TerseFirstPerson, Novel3rdPerson, Mixed }` consumer of PL-22 voice mode

### S3. PC body-memory model (xuyên không) — THE NOVEL DESIGN

This is the unique LoreWeave concept. Most RPGs treat PC as one identity (mind=body). LoreWeave allows PCs to be transmigrators with split soul/body:

```rust
pub struct PcBodyMemory {
    pub soul: SoulLayer,
    pub body: BodyLayer,
    pub leakage_policy: LeakagePolicy,
}

pub struct SoulLayer {
    pub origin_world_ref: Option<RealityRef>,        // None = native to this reality (no xuyên không)
    pub knowledge_tags: Vec<KnowledgeTag>,           // soul brought knowledge
    pub native_skills: Vec<SkillRef>,                // mind-skills (academic, languages, etc.)
}

pub struct BodyLayer {
    pub host_body_ref: BodyRef,                      // canonical body from this reality
    pub knowledge_tags: Vec<KnowledgeTag>,           // body retains knowledge from former occupant
    pub motor_skills: Vec<SkillRef>,                 // motor-skills (combat, crafts learned by body)
    pub native_language: LanguageRef,
}

pub enum LeakagePolicy {
    NoLeakage,                                       // (V1 default for non-transmigrator)
    SoulPrimary { body_blurts_threshold: f32 },      // body sometimes leaks; soul controls
    BodyPrimary { soul_slips_threshold: f32 },       // soul controls but body instinct slips through
    Balanced,                                        // both layers contribute equally
}
```

**Why this matters for canon-drift:** SPIKE_01 turn 5 (Lý Minh quotes 《Đạo Đức Kinh chú》) is a body-knowledge mismatch. Body of an illiterate peasant SHOULD NOT be able to quote classical text. The slip happens because soul (2026 student who read the book) leaks knowledge through the body. A6 canon-drift validator needs PcBodyMemory to detect this.

V1 cases to support:
- **Native PC** (no xuyên không): SoulLayer.origin_world_ref = None; body and soul knowledge align
- **Transmigrator PC**: distinct SoulLayer.origin_world_ref + separate knowledge_tags lists
- **(V2+ deferred)** Reincarnation: body resets each death; soul preserves
- **(V2+ deferred)** Possession: temporary occupation by another soul

### S4. `pc_mortality_state` aggregate (handoff from WA_006)

WA_006 Mortality THIN-REWROTE its over-extended sections out, including this aggregate. PCS_001 picks it up:

```rust
#[derive(Aggregate)]
#[dp(type_name = "pc_mortality_state", tier = "T2", scope = "reality")]
pub struct PcMortalityState {
    pub pc_id: PcId,
    pub state: MortalityStateValue,
    pub last_transition_at_turn: u64,
    pub history: Vec<MortalityTransition>,
}

pub enum MortalityStateValue {
    Alive,
    Dying { will_respawn_at_fiction_time: FictionTimeTuple, spawn_cell: ChannelId },
    Dead { died_at_turn: u64, died_at_cell: ChannelId },
    Ghost { died_at_turn: u64, died_at_cell: ChannelId },
}
```

PCS_001 owns the aggregate body; WA_006 owns the CONFIG (`MortalityConfig` reality-singleton); the runtime detection / hot-path check / respawn flow is shared between PCS_001 + 05_llm_safety + PL_001/PL_002.

**Cite WA_006 closure pass** (commit `f436e60`) and the over-extension marker history (`de9cf1a`) when implementing — the WA_006 file itself has the handoff already documented in §14 Cross-references.

### S5. PC stats foundation (V1 stub)

Minimum to support Mortality + combat-context checks WITHOUT designing the full DF7 stats system:

```rust
#[derive(Aggregate)]
#[dp(type_name = "pc_stats_v1_stub", tier = "T2", scope = "reality")]
pub struct PcStatsV1Stub {
    pub pc_id: PcId,
    pub hp: u32,                                     // simple integer; not full combat
    pub status_flags: Vec<StatusFlag>,
    pub last_modified_at_turn: u64,
}

pub enum StatusFlag {
    InCombat,                                        // referenced by WA_006 §6.3 sleep blocker
    InPrivateSafe,                                   // referenced by WA_006 §10.1 sleep allow
    Sleeping,                                        // PC is in /sleep state
    Disabled,                                        // for V2+ status effects
    // ...
}
```

V1 stub is intentionally minimal. DF7 V2+ replaces with full stats. PCS_001 documents the V1→V2 migration path.

### S6. PC-NPC relationship read-side

NPC_001 §3.3 owns `npc_pc_relationship_projection` (write side, derived at session-end). PCS_001 owns the PC-side READ:

```rust
pub trait PcSocialMap {
    /// PC's view of the NPCs they have met
    fn known_npcs(&self, pc_id: PcId) -> Vec<NpcRelationshipSummary>;

    /// Specific (PC, NPC) relationship lookup for prompt assembly
    fn relationship_with(&self, pc_id: PcId, npc_id: NpcId) -> Option<NpcRelationshipSummary>;
}
```

This is a READ-ONLY interface backed by `npc_pc_relationship_projection`. No new aggregate.

### S7. Acceptance criteria

Mirror NPC_001 / WA_001 / WA_002 / WA_003 / WA_006 pattern. Target ~10 scenarios:
- **Happy-path**: native PC creation; transmigrator PC with soul+body; mortality state Alive→Dying→Alive cycle; stats stub HP modification; PC-NPC relationship read
- **Failure-path**: invalid soul/body combination; canon-drift detection on body-knowledge mismatch (SPIKE_01 turn 5 case); attempting to read `pc_mortality_state` for invalid PcId
- **Boundary**: PC permanently removed → `entity_binding` cleanup hook (PL_001 §3.6); migration v1 stub → DF7 (V2+)

**SPIKE_01 obs#5 acceptance scenario is REQUIRED.** PCS_001 must reproduce Lý Minh's literacy slip detection. If it can't, the body-memory model is wrong.

---

## §3 — OUT of scope (you MUST NOT touch)

### O1. `02_world_authoring/` is CLOSED

WA folder went through a closure pass (commits `4be727d` + `f436e60` + `5d23e3c`). Five WA features at CANDIDATE-LOCK. The WA `_index.md` includes an "Extension pattern guide" with 6 anti-patterns explicitly listed. Do NOT:
- Add new WA_NNN files
- Edit WA_001..006 (Lex / Heresy / Heresy-b / Forge / Mortality)
- Move PCS aggregates into WA folder

PCS aggregates live in `06_pc_systems/`. Period.

### O2. `05_npc_systems/` is NPC's territory

NPC_001 + NPC_002 own NpcId, npc_persona, npc_session_memory, npc_pc_relationship_projection (write-side). Do NOT:
- Redefine NpcId
- Add new NPC aggregates (defer to NPC agent)
- Modify Cast or Chorus design docs

PCS_001 CONSUMES NPC_001's projections (read-side); does not redesign.

### O3. PC creation flow is `03_player_onboarding/PO_001`

PCS_001 owns the DATA SHAPE of a PC. The CREATION FLOW (signup → character builder → first-PC tutorial) is `03_player_onboarding/` — a separate folder + future agent.

PCS_001 says "a PC has these fields"; PO_001 says "this is how a player gets one".

### O4. Combat / DF7 stats system is V2+

PCS_001 ships a V1 STUB only (`hp: u32` + `status_flags`). DF7 owns the full stats system (attributes, skills, modifiers, dice, equipment, etc.). Do NOT design combat damage formulas, skill checks, or item interaction here.

### O5. LLM safety internals (05_llm_safety A3/A5/A6) are not yours

A6 canon-drift detection consumes `PcBodyMemory.knowledge_tags`. PCS_001 specifies the data model A6 reads; PCS_001 does NOT design A6's detection algorithm. If A6 needs new fields, raise it in `99_open_questions.md` (your folder) — do not modify 05_llm_safety files.

### O6. Turn flow / hot-path check is `04_play_loop/PL_001/002`

The hot-path check at turn submission ("is this PC's `pc_mortality_state == Alive`?") lives in PL_001 / PL_002. PCS_001 specifies the contract (`PcMortalityState` shape + accessor); PL_001/002 owns the hot-path call site.

### O7. Authentication / user accounts (auth-service)

PcId is per-reality-per-PC. UserId-to-PcId mapping (which user owns which PCs across realities) is auth-service / `04_player_character/` territory. PCS_001 does not own user accounts.

### O8. Existing locked / drafted feature designs

Per the WA_006 marker pattern: do not modify other features' designs. If PCS_001 design needs a change in another feature, write it as an open question in `99_open_questions.md` (under `06_pc_systems/`) and escalate.

---

## §4 — Required reading (in order)

Before drafting PCS_001:

### 4.1 SPIKE_01 obs#5 (mandatory grounding)

`docs/03_planning/LLM_MMO_RPG/features/_spikes/SPIKE_01_two_sessions_reality_time.md` §6 obs#5 — the literacy slip is the canonical xuyên không scenario. Read it twice. PCS_001 body-memory model must reproduce this.

### 4.2 NPC_001 Cast (parallel design — pattern to mirror)

`docs/03_planning/LLM_MMO_RPG/features/05_npc_systems/NPC_001_cast.md` — NPC's design pattern for inhabitants. Read in full. PCS_001 mirrors this structure for PCs.

### 4.3 WA_006 Mortality (handoff source)

`docs/03_planning/LLM_MMO_RPG/features/02_world_authoring/WA_006_mortality.md` (post thin-rewrite) — `pc_mortality_state` aggregate ownership transfer is documented. The thin-rewrite notice + §14 Cross-references explicitly point at PCS_001 as future owner.

### 4.4 PL_001 Continuum (consumer)

`docs/03_planning/LLM_MMO_RPG/features/04_play_loop/PL_001_continuum.md` §3.6 entity_binding (transferred to EF_001 2026-04-26 — see 4.4b) + §3.7 hard limits. PCS_001's entity lifecycle hook (per PL_001 §3.6 + EF_001 §6) needs awareness.

### 4.4b EF_001 Entity Foundation (mandatory — PCS_001 builds on this) (added 2026-04-26)

`docs/03_planning/LLM_MMO_RPG/features/00_entity/EF_001_entity_foundation.md` — defines `EntityId` 4-variant sum type (Pc/Npc/Item/EnvObject), `entity_binding` aggregate (transferred from PL_001 §3.6), 4-state `LifecycleState` machine, 6 V1 `AffordanceFlag` closed enum, and the **`EntityKind` trait** (5 methods). PCS_001 MUST implement `EntityKind for Pc` including `type_default_affordances() = be_spoken_to + be_struck + be_examined + be_given + be_received + be_used` (full V1 set — PCs do everything). PC mortality cascades into EF_001 lifecycle `Existing → Destroyed` per §6; references to Destroyed PC reject `entity.entity_destroyed` per §8 (PCS_001's V1+ Respawn would transition `Destroyed → Existing` as a PCS-owned operation).

### 4.5 02_storage R8 (NPC memory pattern reference)

`docs/03_planning/LLM_MMO_RPG/02_storage/R08_npc_memory_split.md` — NPC aggregate split pattern. PCS may pattern-match for `pc` core + `pc_session_memory` (V2+ mirror).

### 4.6 Boundary folder

`docs/03_planning/LLM_MMO_RPG/_boundaries/01_feature_ownership_matrix.md` — confirm no aggregate name collision before declaring new aggregates. `_boundaries/02_extension_contracts.md` §1 — TurnEvent envelope rules if PCS extends TurnEvent fields.

### 4.7 Data plane (locked, transitively required)

You don't need to read all of `06_data_plane/` but you DO need:
- `02_invariants.md` DP-A12 (RealityId newtype pattern — mirror for PcId)
- `04a_core_types_and_session.md` DP-K1 (Aggregate trait + scope markers)
- `03_tier_taxonomy.md` (T2 = your default tier for PCS aggregates)

### 4.8 Catalog cross-reference

`docs/03_planning/LLM_MMO_RPG/catalog/cat_06_PCS_pc_systems.md` — existing PCS-* catalog. Reserve PCS-1, PCS-2 etc. as needed; cite catalog IDs.

### 4.9 Decisions (locked PC decisions)

`docs/03_planning/LLM_MMO_RPG/decisions/locked_decisions.md` — search for `PC-A1..E3`. Multiple PC-related decisions already locked; PCS_001 must respect them.

---

## §5 — Phase plan

PCS_001 is a single feature, NOT a multi-phase folder design. Suggested 2-pass approach:

### Pass 1: First-session deliverable (per §10)

Draft PCS_001 design with:
- §1-§5 contract layer (story, domain, EVT mapping, aggregates, tier+scope)
- §6 body-memory model (the novel piece)
- Skeleton for §7-§15 (placeholders ok)

Present POST-REVIEW (per §7.1) before continuing.

### Pass 2: Acceptance + refinement

After user approval of pass 1:
- Fill out §7-§15 (sequences, acceptance, deferrals, cross-refs, readiness)
- Acceptance criteria scenarios (10+)
- SPIKE_01 obs#5 reproducibility verified
- Boundary folder ownership matrix updated

If file approaches 800-line cap, consider split (mirror PL_001 / WA_002 split precedent).

---

## §6 — Stable ID namespace

You own the `PCS-*` prefix per `catalog/cat_06_PCS_pc_systems.md`.

| Prefix | Scope | File |
|---|---|---|
| `PCS-D*` | Per-feature deferral IDs (e.g., PCS-D1 means PCS_001's deferral #1) | within PCS_001 |
| `PCS-Q*` | Open questions | `99_open_questions.md` (if you need one) |
| `PCS-S*` | Schema versioning entries | within PCS_001 |

**MUST NOT collide with:**
- Existing catalog prefixes (DP-* / EVT-* / WA-* / PLT-* / NPC-* / PL-* / etc.)
- WA-006 MOR-D* / WA-001 LX-D* / NPC-001 CST-D* etc. (per-feature deferral namespaces)

---

## §7 — Process discipline

These are non-optional. The main session will reject commits violating them.

### 7.1 Phase 9 POST-REVIEW before every commit

Present a summary to the user (architect role) and **wait for explicit approval** before committing. Format:

```
## POST-REVIEW for <phase / file / change>

What changed:
- file X (NNN lines added/modified)

Key decisions locked:
- PCS-Ann: <one-line rule>

Deferred:
- PCS-Dnn: <question>

Risk / drift watchpoint:
- <any concern with WA / NPC / 05_llm_safety / PL boundaries>

Awaiting approval to commit with message:
  docs(mmo-rpg): <commit message draft>
```

### 7.2 Stable IDs never renumber

Once `PCS-D1` is locked, its number is permanent. Withdraw → `PCS-D1_withdrawn` suffix; entry stays for historical reference.

### 7.3 Boundary folder lock-claim if extending shared schemas

If PCS_001 extends:
- `TurnEvent` envelope (per `_boundaries/02_extension_contracts.md` §1) — REQUIRES lock-claim of `_boundaries/_LOCK.md`
- `RealityManifest` (per §2 — currently unowned, propose IF_001 path) — REQUIRES lock-claim
- `ActorId` enum (locked by NPC_001 §2; only `Pc(PcId)` slot is yours) — adding the slot does NOT require boundary lock; modifying NPC_001's enum DOES

If unsure: lock-claim is cheap; over-claim is fine.

### 7.4 Decisions log

Locked PC-A1..E3 decisions exist in `decisions/locked_decisions.md`. PCS_001 design must respect them. If PCS_001 needs a new locked decision, propose via POST-REVIEW + add to decisions doc.

### 7.5 Line cap soft 500 / hard 800

Match existing convention. PCS_001 estimate: 600-700 lines. Approaching 800 → split (PCS_001 + PCS_001b lifecycle, mirroring PL_001/PL_001b precedent).

### 7.6 No silent scope creep

Anti-patterns to avoid (mirror WA closure anti-patterns):
- ❌ Designing PC creation flow (PO_001's territory)
- ❌ Designing combat / DF7 stats
- ❌ Designing A6 canon-drift algorithm
- ❌ Modifying WA / NPC / PL feature files
- ❌ Adding aggregates that should belong elsewhere
- ❌ Re-deriving NpcId or RealityId

If you find yourself doing any of these: STOP. Raise as `99_open_questions.md` item or POST-REVIEW concern.

---

## §8 — Coordination with other streams

### 8.1 Main session (closure work + handoff)

The main session is wrapping up. After committing your PCS_001 design, the main session may NOT be available; future user interactions are with you (or a fresh main agent).

### 8.2 Event-model agent (07_event_model)

Phase 1 LOCKED (EVT-A1..A8 + EVT-T1..T11). PCS_001 maps PC-related events to existing categories:
- PC turn submission → EVT-T1 PlayerTurn
- PC mortality state transition → EVT-T3 AggregateMutation
- Do NOT propose new EVT-T*. Do NOT modify event-model files.

If PCS needs a new event category, escalate via `99_open_questions.md` to event-model agent (don't fix in-place).

### 8.3 NPC agent (if revisited)

NPC_001 + NPC_002 are at DRAFT (not closed). If a future NPC closure pass happens, your PCS_001 may need minor cross-ref updates. Treat NPC files as READ-ONLY until you see a NPC closure commit.

### 8.4 Conflicts with existing locked features

If PCS_001 design contradicts something in PL_001 / WA_001..006 / NPC_001..002 / PLT_001/002:
- 02_storage / 03_multiverse / 06_data_plane / 07_event_model / 05_llm_safety = LOCKED, immutable. Adapt PCS to fit.
- Other features at DRAFT or CANDIDATE-LOCK = raise via POST-REVIEW; user decides.

---

## §9 — Success criteria

You succeed if, at LOCK time:

1. **PcId newtype + ActorId::Pc variant** locked with module-private constructor pattern
2. **PC persona model** parallels NPC_001 §3 structure (canonical + flexible + knowledge_tags + voice_register)
3. **PC body-memory model** supports xuyên không V1 cases (native + transmigrator); SPIKE_01 obs#5 literacy slip is REPRODUCIBLE in §10/§11 sequence with concrete PcBodyMemory data
4. **`pc_mortality_state` aggregate** designed with state machine + handoff from WA_006 cited
5. **V1 stats stub** sufficient to support Mortality (`hp` + `InCombat` / `InPrivateSafe` flags); DF7 V2+ migration documented
6. **PC-NPC relationship read-side** specified as a trait/interface; backed by NPC_001 projection
7. **Acceptance criteria** ~10 scenarios; SPIKE_01 obs#5 is one of them
8. **Boundary clean** — no edits to WA / NPC / PL / 05_llm_safety files; no aggregates that belong elsewhere
9. **Boundary folder updated** — ownership matrix reflects PCS_001 aggregate ownership claims
10. **Acceptable doc size** — under 800-line hard cap (split if needed)

You fail if:
- Designed PC creation flow (that's PO_001)
- Designed combat / DF7 (that's V2+)
- Modified WA / NPC / PL files (boundary violation)
- Cannot reproduce SPIKE_01 obs#5 (the canonical xuyên không scenario)
- Did not follow POST-REVIEW gate (committed without user approval)
- Designed PCS_001 in `02_world_authoring/` or any folder other than `06_pc_systems/`

---

## §10 — First-session deliverable

Before drafting any axioms, deliver these as your Phase 0 confirmation that you understood the brief:

1. **Read confirmation** — list the §4 docs you read, with one-line notes on each (what you took from them).
2. **Aggregate inventory plan** — list aggregates you intend to declare (likely 3: `pc` core, `pc_mortality_state`, `pc_stats_v1_stub`); for each: tier, scope, why.
3. **Body-memory model sketch** — PcBodyMemory struct outline + how it reproduces SPIKE_01 obs#5.
4. **Cross-reference plan** — list features PCS_001 will reference (NPC_001, WA_006, PL_001, etc.) + how each is consumed.
5. **Open boundary questions** — list any §2 IN-scope item where you are unsure of boundary (e.g., "is voice_register PCS-side or PL_002 Grammar-side?"). Phrase as decisions for the user to resolve.

Present this as a POST-REVIEW (per §7.1) to the user. Once approved, you proceed to Pass 1 of the design.

---

## Appendix A — SPIKE_01 obs#5 grounding (the canonical xuyên không scenario)

From `features/_spikes/SPIKE_01_two_sessions_reality_time.md` §6 obs#5:

**Setting:** Reality `R-tdd-h-2026-04-25` (Thần Điêu Đại Hiệp / Kim Dung wuxia). PC `Lý Minh` is in cell `yen_vu_lau` interacting with NPCs Lão Ngũ + Tiểu Thúy + Du sĩ.

**PC backstory (xuyên không):**
- **Soul layer:** 2026 Saigon university student. Knowledge tags: `["modern_education", "vietnamese_native", "internet_culture", "daoist_text" (read 《Đạo Đức Kinh chú》 in a comparative-religion class)]`. Native language: Vietnamese (modern). Native skills: programming, English, abstract reasoning.
- **Body layer:** 1256 Hàng Châu peasant farmer (deceased). Knowledge tags: `["peasant_labor", "local_geography", "river_routes", "basic_jianghu_rumors"]`. Body is illiterate — never learned classical Chinese reading. Native language: Wu dialect (1256 Southern Song). Native skills: farming, basic carpentry, swimming.

**Turn 5 event:**
PC submits: "Tiểu nhị, vĩnh ngộ tại ư phi vi tà"
- This is a quote from 《Đạo Đức Kinh chú》(Tao Te Ching commentary), classical Chinese.
- Soul KNOWS this passage (read it as a student in 2026).
- Body has NEVER seen this text — illiterate peasant cannot read classical Chinese.

**The slip:** PC's quote is a body-memory mismatch. The PC's NARRATOR-level identity is that of the body (Lý Minh, peasant) — but the soul is leaking knowledge through.

**A6 canon-drift detection (consumer) needs:**
- `PcBodyMemory.body.knowledge_tags` contains `"basic_jianghu_rumors"` etc. but NOT `"daoist_text"` or `"classical_chinese"`
- `PcBodyMemory.soul.knowledge_tags` contains `"daoist_text"` (from comparative-religion class)
- The narrator_text contains a tag that overlaps with `soul.knowledge_tags` but NOT `body.knowledge_tags` → flag as `body-soul leakage` event
- LeakagePolicy determines whether this is allowed: in `SoulPrimary { body_blurts_threshold }` mode, soul-knowledge slipping is expected; A6 may not flag. In `BodyPrimary { soul_slips_threshold }` mode, slip is unusual; A6 flags as canon-drift.

**NPC_002 Chorus reaction (consumer):**
- Du sĩ has knowledge_tag `"daoist_text"` → Tier 3 priority match → Du sĩ visibly reacts (gesture, glare)
- Lão Ngũ has knowledge_tag `"basic_jianghu_rumors"` only → no overlap with `"daoist_text"` → ambient reaction or none
- Tiểu Thúy has knowledge_tag `"servant_gossip"` only → no overlap → no reaction or surprise

**This obs#5 scenario is the §10/§11 sequence in PCS_001.** If your design cannot reproduce it deterministically, the body-memory model is wrong. Iterate until it works.

**Acceptance criterion AC-PCS-N must include:** "Lý Minh xuyên không scenario — PC submits classical-text quote; A6 detects body-memory leakage; NPC_002 Chorus Tier-3 priority resolves Du sĩ as primary reactor; Lão Ngũ + Tiểu Thúy filtered out per their knowledge_tags."

---

## Appendix B — File-skeleton template

Mirror NPC_001 Cast structure:

```markdown
# PCS_001 — <Conversational name> (PC Substrate)

> [header with status, category, catalog refs, builds-on, defers-to]

---

## §1 User story (concrete — Lý Minh xuyên không grounded)

## §2 Domain concepts
[PcId, ActorId::Pc, PcPersona, PcBodyMemory, PcMortalityState, PcStatsV1Stub, PcSocialMap]

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)
[which EVT-T* events PCS emits or consumes]

## §3 Aggregate inventory
### 3.1 `pc` (core) — T2/Reality
### 3.2 `pc_mortality_state` (handoff from WA_006) — T2/Reality
### 3.3 `pc_stats_v1_stub` — T2/Reality
### 3.4 References (NPC_001 npc_pc_relationship_projection, etc.)

## §4 Tier+scope table (DP-R2 mandatory)

## §5 DP primitives this feature calls

## §6 PC body-memory model (xuyên không) — THE NOVEL PIECE
### 6.1 Native PC (no xuyên không) baseline
### 6.2 Transmigrator PC (split soul/body)
### 6.3 Leakage policy + A6 canon-drift integration
### 6.4 V2+ deferred cases (reincarnation, possession)

## §7 Pattern choices
[V1 default = native; transmigrator opt-in; leakage policies; consumer interfaces]

## §8 Capability requirements (JWT claims)

## §9 Failure-mode UX

## §10 Cross-service handoff
[How PCS interacts with PL_001 turn flow, NPC_001 read, WA_006 config, 05_llm_safety A6]

## §11 Sequence: SPIKE_01 obs#5 reproducibility (xuyên không slip detection)

## §12 Sequence: PC mortality state transition (handoff from WA_006)

## §13 Acceptance criteria (LOCK gate)
[10 scenarios incl. SPIKE_01 obs#5]

## §14 Open questions deferred (PCS-D1..)

## §15 Cross-references

## §16 Implementation readiness checklist
```

---

**End of brief.** Begin with §10 first-session deliverable. Good luck.
