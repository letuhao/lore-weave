# ACT_001 Actor Foundation — Concept Notes

> **Status:** Q1-Q6 LOCKED 2026-04-27 — main session deep-dive analysis (Opportunity 1 actor_core unification + Q3 REVISION + Q6 user-revised to full unify all 3 opportunities). DRAFT promotion ready when `_boundaries/_LOCK.md` free (commit 2/4).
>
> **Purpose:** Capture architectural insight + 3-layer control model + 4-aggregate decomposition + Q1-Q6 LOCKED for ACT_001 Actor Foundation. The seed material for the eventual `ACT_001_actor_foundation.md` design.
>
> **Promotion gate:** ✓ Q1-Q6 locked via main session deep-dive 2026-04-27. ✓ `_boundaries/_LOCK.md` free at this commit. → Next commit (2/4): main session drafts `ACT_001_actor_foundation.md` with 4 aggregates + cascading closure-pass-extensions for NPC_001/002/003 + 02_storage R8 update.

---

## §1 — User framing + architectural origin (2026-04-27)

User direction 2026-04-27 raised the deep design question: "tiếp theo thảo luận về PC/NPC — câu hỏi là có cần tách chúng ra riêng không? hình như toàn bộ giống nhau" (do PC and NPC need to be separated? they seem entirely similar).

### Main session response analysis

Confirmed user observation HAS MERIT:
- **Substrate IS unified Tier 5 (8+ features):** EF_001 + IDF_001..005 + FF_001 + FAC_001 + REP_001 + PROG_001 + RES_001 + PL_006 + WA_006 — all per-actor (PC + NPC) unified
- **Behavior IS legitimately separate:** 8 differences between PC + NPC (control / lifecycle / authoring / scale / memory / xuyên không / mortality / node binding)
- **3 unification opportunities at behavior layer** identified:
  - Opp 1: `actor_core` (replace `npc` + future `pc`)
  - Opp 2: `actor_actor_opinion` bilateral (replace one-directional `npc_pc_relationship_projection`)
  - Opp 3: `actor_session_memory` unified (replace `npc_session_memory` + PC chat history fragmentation)

### Critical architectural insight: NPC_001 is the OUTLIER pattern

ALL OTHER Tier 5 substrate features use unified per-actor pattern. NPC_001 was designed BEFORE Tier 5 substrate emerged; pattern drifted. This is structural inconsistency to fix.

### User insight 2026-04-27: AI-controls-PC-offline V1+ feature

User raised: "Q3 — npc.desires (NPC_003) move to actor_core? -> cân nhắc lại chỗ này, sau này có tính năng AI điều khiển người chơi offline" (reconsider — future AI-controls-PC-offline feature).

This insight CHANGED the architectural calculus:
- desires + greeting_obligation + priority_tier_hint are NOT NPC-specific properties
- They are "AI-drive metadata" — applicable to any AI-driven actor
- NPCs always AI-driven; PCs offline V1+ AI-driven
- Control source is DYNAMIC for PC (User online; AI offline); ActorKind doesn't shift but control state does

### 3-layer architectural model emerged

| Layer | Concept | Stable? | Examples |
|---|---|---|---|
| **L1 Identity** | Who is this actor? | ✅ Stable post-creation | ActorId, canonical_traits, knowledge_tags, voice_register, core_beliefs_ref |
| **L2 Capability/Kind** | What kind? | ✅ Stable post-creation | ActorKind = PC / NPC / Synthetic (encoded in ActorId variant) |
| **L3 Control source** | Who's driving RIGHT NOW? | ❌ DYNAMIC | User (PC online) / AI (NPC always; PC offline V1+) / Engine (Synthetic) |

**Insight:** Q3 fields live at LAYER 3 (control state) — populated when control source = AI. NOT NPC-specific (L2).

### User decision 2026-04-27

Sequential approval:
- R1 picked: APPROVE unify direction → start NEW feature ACT_001 Actor Core
- Q1-Q5 approved (with Q3 REVISION based on AI-controls-PC-offline insight)
- Q6 user-revised from (B) defer Opp 2+3 → (A) full unify all 3 opportunities NOW

**Rationale:** Future-proofing comprehensively. Once AI-controls-PC-offline V1+ ships, ALL 3 opportunities matter (control source + bilateral opinion + session memory continuity). Unifying once now avoids 3 closure-pass-extensions later.

---

## §2 — 3-layer control model + 4-aggregate decomposition

### Field-level decomposition across 4 aggregates

| Field | Layer | Owner aggregate | When populated |
|---|---|---|---|
| `canonical_traits` (name + role + voice + physical) | L1 Identity | `actor_core` | Always (post-creation) |
| `flexible_state` (mood + emotional state) | L1 Identity | `actor_core` | Always |
| `knowledge_tags` (closed-set strings) | L1 Identity | `actor_core` | Always |
| `voice_register` (TerseFirstPerson / Novel3rdPerson / Mixed) | L1 Identity | `actor_core` | Always |
| `core_beliefs_ref` (canon belief reference) | L1 Identity | `actor_core` | Always (Optional<>) |
| `desires` (NPC_003 author-declared goals) | **L3 AI-drive** | `actor_chorus_metadata` | NPCs always; PCs V1+ when AI-driven offline |
| `greeting_obligation` (NPC_002 priority hint) | **L3 AI-drive** | `actor_chorus_metadata` | NPCs always; PCs V1+ |
| `priority_tier_hint` (NPC_002 chorus priority) | **L3 AI-drive** | `actor_chorus_metadata` | NPCs always; PCs V1+ |
| `(observer, target) opinion_score` | **L3 Relationship** | `actor_actor_opinion` (bilateral) | Sparse — populated when interactions create opinion |
| `trust + familiarity + stance_tags` | L3 Relationship | `actor_actor_opinion` | Sparse |
| `memory_facts (per session)` | L3 Memory | `actor_session_memory` | Per-(actor, session); V1 NPCs; V1+ PCs offline |
| `last_seen_at` | L3 Memory | `actor_session_memory` | Per-(actor, session) |
| `user_id` ref (auth-service) | L3 User-binding | `pc_user_binding` (PCS_001 future) | PCs only (always; even when offline) |
| `current_session` ref | L3 User-binding | `pc_user_binding` | PCs only (Some=online; None=offline) |
| `body_memory` (xuyên không SoulLayer + BodyLayer) | L2 PC-specific | `pc_user_binding` | PCs only V1; V2+ NPCs may xuyên không |
| `npc_node_binding` (writer-node owner with epoch fence) | L2 NPC-specific | NPC_001 (kept post-unify) | NPCs only |
| `pc_mortality_state` (Alive/Dying/Dead/Ghost) | L2 PC-specific | `pc_mortality_state` (PCS_001 future) | PCs only |

**Result: 4 ACT_001 aggregates substrate-level + 1 NPC_001 kept (`npc_node_binding`) + 3 PCS_001 future (`pc_user_binding` + `pc_mortality_state` + `pc_stats_v1_stub`).**

---

## §3 — Q1-Q6 critical scope questions — ✅ ALL LOCKED 2026-04-27

User confirmed "approve all but revise Q6 to (A) full unify all 3 now" 2026-04-27. **2 REVISIONS** noted:
- Q3 REVISION: from (B) keep NPC-specific → (NEW C) rename to `actor_chorus_metadata`; own under ACT_001; sparse; future-proofs AI-controls-PC-offline V1+
- Q6 REVISION (user-revised): from main session recommendation (B) defer Opp 2+3 → (A) full unify all 3 opportunities NOW

### Q1 — Owner of `actor_core` aggregate?

✅ **LOCKED 2026-04-27: (C) NEW feature ACT_001 Actor Foundation**

**Reasoning:**
- Pattern consistency — All Tier 5 substrate features are independent (IDF / FF / FAC / REP / PROG / RES / PL_006 each their own); ACT_001 follows
- Single-responsibility — ACT_001 owns IDENTITY; NPC_001 owns CHORUS BEHAVIOR (kept narrow); PCS_001 owns USER BINDING; clear separation
- Lock-cycle clean — ACT_001 has its own 4-commit cycle; NPC_001 closure-pass-extension is small follow-up; PCS_001 builds on stable base
- Naming: `ACT_001` + folder `features/00_actor/` + catalog `cat_00_ACT_actor_foundation.md` + stable-ID prefix `ACT-*`

### Q2 — Sequencing: ACT_001 cycle vs PCS_001 cycle?

✅ **LOCKED 2026-04-27: (A) Sequential**

**Reasoning:**
- ACT_001 + R8 update + NPC_001/002/003 closure-pass-extensions fit in one 4-commit cycle (single lock claim)
- PCS_001 builds on stable substrate (no lock contention with ACT_001 work)
- Clean dependency: ACT_001 ships → NPC closures patched in same cycle → PCS_001 designs separately
- Each cycle bounded ~1-2 days; 2 cycles total ~3-4 days

### Q3 — `npc.desires` (NPC_003) move? ⚠ REVISION

✅ **LOCKED 2026-04-27: REVISION (NEW C) — Rename `npc_chorus_metadata` → `actor_chorus_metadata`; own under ACT_001 substrate; sparse storage; future-proofs AI-controls-PC-offline V1+**

**Reasoning (REVISION from initial (B) keep NPC-specific):**
- User insight: AI-controls-PC-offline V1+ feature — PCs need desires + greeting_obligation + priority_tier_hint when AI takes over
- These fields are L3 AI-drive metadata, NOT L2 NPC-specific
- Rename to neutral `actor_chorus_metadata` — substrate-level aggregate
- Sparse storage: NPCs always populated (always AI-driven); PCs V1+ when control source = AI
- Owner: ACT_001 (substrate level)
- NPC_002 Chorus reads from this aggregate (consumer; not owner); chorus orchestration extends to AI-driven PCs V1+ via same path (no new orchestrator code)
- core_beliefs_ref MOVED to `actor_core` (identity, not behavior)

### Q4 — Synthetic actors get `actor_core` row?

✅ **LOCKED 2026-04-27: (B) Synthetic excluded V1**

**Reasoning:**
- Universal V1 substrate discipline (IDF + FF + FAC + REP + RES + PROG + PL_006 + REP_001 all forbid synthetic)
- Synthetic actors PRODUCE events on behalf of engine but don't HAVE narrative properties
- ActorId::Synthetic variant exists (EF_001) but no `actor_core` row required V1
- Reject `actor.synthetic_actor_forbidden` Stage 0 schema (matches existing pattern)
- V1+ may relax IF admin-faction synthetic narrative identity needed (defer to real use case)

### Q5 — 02_storage R8 update sequencing?

✅ **LOCKED 2026-04-27: (B) R8 update WITHIN ACT_001 cycle**

**Reasoning:**
- R8 is R-locked spec but allows additive updates with main session ownership
- ACT_001 effectively splits R8's `npc` aggregate into 2 (`actor_core` + `actor_chorus_metadata`) — additive split, not destructive
- Main session updates R8 + 01_feature_ownership_matrix together (single lock claim)
- (A) too sequential; storage-agent may not be available; main session can do R8 split since it's structural reorganization not new domain logic
- (C) creates dual-write problem (race conditions; data drift); rejected

**R8 changes V1:**
- Keep R8 file path
- Update R8 schema: split `npc` core into `actor_core` (kind-agnostic) + `actor_chorus_metadata` (sparse AI-drive)
- Rename `npc_session_memory` → `actor_session_memory` (per-(actor, session))
- Rename `npc_pc_relationship_projection` → `actor_actor_opinion` (bilateral; per-(observer, target))
- Update R8 ownership note: ACT_001 owns 4 unified aggregates; NPC_001 keeps `npc_node_binding` only
- Append R8 changelog entry: "2026-04-27 ACT_001 unify split — npc → actor_core + actor_chorus_metadata; bilateral opinion; unified session memory"

### Q6 — Unify all 3 opportunities or defer 2-3? ⚠ REVISION

✅ **LOCKED 2026-04-27: REVISION (A) Full unify all 3 NOW** (user-revised from main session recommendation (B) defer)

**Reasoning (user-revised):**
- AI-controls-PC-offline V1+ ALL 3 opportunities matter:
  - Opp 1 (actor_core + actor_chorus_metadata) — control source dispatch
  - Opp 2 (actor_actor_opinion bilateral) — PC↔NPC opinion when AI drives offline PC
  - Opp 3 (actor_session_memory unified) — LLM context continuity for AI-driven offline PC
- Unifying once now avoids 3 closure-pass-extensions later
- ACT_001 cycle scope expands but bounded
- V1 SCOPE: 4 aggregates instead of 2; V1 functionality identical to current (behavior preserved); structural unification for future-proofing

**Trade-off accepted:**
- ACT_001 cycle = larger scope (~1-2 days)
- 3 NPC features (NPC_001 + NPC_002 + NPC_003) require closure-pass-extensions in same cycle
- Boundary docs more extensive update
- Net: comprehensive future-proofing in single cycle vs multiple incremental cycles later

---

## §4 — V1 scope (LOCKED 2026-04-27)

### V1 aggregates (4 NEW; ACT_001-owned)

1. **`actor_core`** (T2/Reality, per-actor; ALWAYS present post-creation)
   - actor_id (EF_001 §5.1 sibling pattern)
   - canonical_traits: CanonicalTraits (name + role + voice register + physical description; immutable)
   - flexible_state: FlexibleState (mood + emotional state; mutable)
   - knowledge_tags: Vec<KnowledgeTag> (closed-set strings)
   - voice_register: VoiceRegister (TerseFirstPerson / Novel3rdPerson / Mixed)
   - core_beliefs_ref: Option<GlossaryEntityId> (canon belief reference)
   - **Mutable** via Apply events (canonical seed + Forge admin V1 active; runtime flexible_state drift V1+)
   - Synthetic actors forbidden V1 per Q4
   - Cross-reality forbidden V1 (universal substrate discipline)

2. **`actor_chorus_metadata`** (T2/Reality, sparse — populated when control source = AI)
   - actor_id (FK to actor_core)
   - desires: Vec<DesireDecl> (renamed from NpcDesireDecl; kind-agnostic; NPC_003 ownership transfers)
   - greeting_obligation: GreetingObligation
   - priority_tier_hint: PriorityTierHint
   - **Mutable V1** via canonical seed (NPCs always populated) + Forge admin
   - V1+ AI-controls-PC-offline activation: PCs populated when offline; row removed/inactive when online
   - **Sparse storage discipline:** V1 NPCs always have row; PCs never; missing row = "not AI-driven"

3. **`actor_actor_opinion`** (T2/Reality, sparse — per-(observer_actor, target_actor) bilateral)
   - observer_actor_id + target_actor_id (composite key)
   - opinion_score: i16 (or whatever NPC_001 currently uses; preserve V1 semantics)
   - trust: Trust (preserved from npc_pc_relationship_projection)
   - familiarity: Familiarity
   - stance_tags: Vec<StanceTag>
   - last_updated_at_turn: u64
   - **Bilateral:** symmetric pairs (NPC→PC + PC→NPC + NPC→NPC + PC→PC) — V1 active patterns:
     - NPC→PC: V1 active (preserved from npc_pc_relationship_projection)
     - PC→NPC: V1 stub (no events V1; V1+ runtime population)
     - NPC→NPC: V1+ (sect rivalry drama)
     - PC→PC: V1+ (multi-PC realities)
   - **Mutable** via session-end derivation (NPC_001 §13 pattern preserved) + V1+ runtime events

4. **`actor_session_memory`** (T2/Reality, per-(actor, session); supports LLM context)
   - actor_id + session_id (composite key)
   - memory_facts: Vec<MemoryFact> (preserved from npc_session_memory)
   - last_seen_at: u64
   - **V1:** NPCs populated (current behavior preserved)
   - **V1+:** PC chat history pathway unified — AI-controls-PC-offline can read PC session memory for LLM continuity
   - **Mutable** via session-end derivation + Forge admin

### V1 NPC_001-kept aggregate (1)

- **`npc_node_binding`** (NPC writer-node owner mapping with epoch fence) — UNCHANGED V1; PC uses entity_binding from PL_001/EF_001 (different mechanism); V1+ may unify if AI-controls-PC-offline needs node binding for offline PCs (defer)

### V1 PCS_001-future aggregates (3 — separate cycle)

- **`pc_user_binding`** — user_id + current_session + body_memory (xuyên không SoulLayer + BodyLayer)
- **`pc_mortality_state`** — handoff from WA_006 (Alive/Dying/Dead/Ghost)
- **`pc_stats_v1_stub`** — V1 minimal stats; V2+ DF7 replaces

### V1 closed enums (preserved from R8 + NPC_003)

- **`KnowledgeTag`** — closed-set strings (existing R8)
- **`VoiceRegister`** — 3-variant (TerseFirstPerson / Novel3rdPerson / Mixed; existing R8)
- **`StanceTag`** — preserved from npc_pc_relationship_projection
- **`DesireDecl`** — renamed from NpcDesireDecl per Q3 (NPC_003 ownership transfers field)

### V1 events (preserved + unified)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Actor declared at canonical seed | **EVT-T4 System** | `ActorBorn { actor_id, kind, core_traits }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| AI-drive metadata declared at canonical seed | **EVT-T4 System** | `ActorChorusMetadataBorn { actor_id }` | Bootstrap (NPCs only V1) | ✓ V1 |
| Actor opinion update | **EVT-T3 Derived** | `aggregate_type=actor_actor_opinion`, `delta_kind=Update` | Aggregate-Owner (session-end derivation) | ✓ V1 (preserved from NPC_001 §13) |
| Actor session memory update | **EVT-T3 Derived** | `aggregate_type=actor_session_memory`, `delta_kind=Update` | Aggregate-Owner (session-end) | ✓ V1 (preserved from NPC_001) |
| Forge admin edit actor core | **EVT-T8 Administrative** | `Forge:EditActorCore { actor_id, edit_kind, before, after, reason }` | Forge (WA_003) | ✓ V1 |
| Forge admin edit chorus metadata | **EVT-T8 Administrative** | `Forge:EditChorusMetadata { actor_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin edit opinion | **EVT-T8 Administrative** | `Forge:EditActorOpinion { observer, target, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| AI-controls-PC-offline transition (V1+) | EVT-T3 Derived (V1+) | `delta_kind=ActorControlSourceChange { actor_id, before: User, after: AI }` | (V1+ AI-controls-PC-offline feature) | ✗ V1+ |

### V1 `actor.*` reject rule_ids (proposed; finalized at DRAFT)

V1 rules:
1. `actor.unknown_actor_id` — Stage 0 schema
2. `actor.synthetic_actor_forbidden` — Stage 0 schema (per Q4)
3. `actor.cross_reality_mismatch` — Stage 0 schema (universal V2+ Heresy reservation)
4. `actor.kind_specific_field_mismatch` — Stage 0 schema (e.g., chorus_metadata for non-AI-driven actor V1)
5. `actor.opinion_self_target_forbidden` — Stage 0 schema (observer == target rejected)
6. `actor.duplicate_session_memory` — Stage 0 schema (multi-row per (actor, session) pair)

V1+ reservations:
- `actor.bilateral_opinion_unsupported_v1` (V1+ when NPC→NPC + PC→PC events ship)
- `actor.ai_control_pc_offline_unsupported_v1` (V1+ AI-controls-PC-offline activation)
- `actor.canon_drift_detected` (V1+ A6 detector cross-feature integration)

### V1 RealityManifest extensions

V1 ACT_001 RealityManifest extension:
- `canonical_actors: Vec<CanonicalActorDecl>` — UPDATE: existing PL_001 + NPC_001 extension; ACT_001 takes ownership; CanonicalActorDecl shape extends with chorus_metadata fields (Optional; populated for NPCs)

V1 user-message envelope: `RejectReason.user_message: I18nBundle` per RES_001 §2 i18n contract.

### V1 acceptance criteria (proposed; finalized at DRAFT)

V1 (10+ V1-testable):
- AC-ACT-1: Wuxia canonical bootstrap declares 4 NPCs + 1 PC → 5 actor_core rows + 4 actor_chorus_metadata rows (NPCs only)
- AC-ACT-2: actor_core read returns identity for any kind (PC + NPC); read path uniform
- AC-ACT-3: actor_chorus_metadata sparse storage validated (PC has NO row V1; missing row = not AI-driven)
- AC-ACT-4: actor_actor_opinion bilateral keys validated (observer ≠ target enforced)
- AC-ACT-5: actor_session_memory per-(actor, session) keying validated
- AC-ACT-6: NPC_001 closure-pass-extension verified — NpcOpinion::for_pc reads actor_actor_opinion (not npc_pc_relationship_projection)
- AC-ACT-7: NPC_002 closure-pass-extension verified — Chorus priority Tier 2-3 reads actor_core (not npc directly)
- AC-ACT-8: NPC_003 closure-pass-extension verified — desires field reads from actor_chorus_metadata
- AC-ACT-9: Synthetic actor rejected (`actor.synthetic_actor_forbidden`)
- AC-ACT-10: 02_storage R8 update verified — schema split applied; backward-incompatible documented

V1+ deferred:
- AC-ACT-V1+1: AI-controls-PC-offline activates actor_chorus_metadata for PC
- AC-ACT-V1+2: PC↔NPC bilateral opinion (PC view of NPC populated)
- AC-ACT-V1+3: NPC↔NPC opinion (sect rivalry drama)
- AC-ACT-V1+4: PC↔PC opinion (multi-PC realities)

### V1 deferrals (proposed; finalized at DRAFT)

- ACT-D1: V1+ AI-controls-PC-offline feature activation
- ACT-D2: V1+ PC↔NPC bilateral opinion runtime population
- ACT-D3: V1+ NPC↔NPC opinion (sect rivalry drama; consumes actor_actor_opinion)
- ACT-D4: V1+ PC↔PC opinion (multi-PC realities; multiplayer)
- ACT-D5: V1+ NPC xuyên không (currently PC-only V1 via PCS_001 body_memory)
- ACT-D6: V2+ cross-reality migration (universal V2+ Heresy)
- ACT-D7: V1+ canon-drift detector integration (A6 + actor_core knowledge_tags + actor_session_memory)
- ACT-D8: V1+ NPC_003 desires lifecycle events (currently author-only via Forge)
- ACT-D9: V1+ actor_chorus_metadata schema enrichment (additional AI-drive metadata as features ship)
- ACT-D10: V1+ unified node_binding (currently NPC-only npc_node_binding; PC offline V1+ may need consolidation)

### V1 quantitative summary

- 4 ACT_001 aggregates (actor_core + actor_chorus_metadata sparse + actor_actor_opinion sparse bilateral + actor_session_memory)
- 1 NPC_001-kept aggregate (npc_node_binding)
- 3 PCS_001-future aggregates (pc_user_binding + pc_mortality_state + pc_stats_v1_stub)
- 6 V1 reject rule_ids in `actor.*` namespace + 3 V1+ reservations
- RealityManifest extension: canonical_actors ownership transfer + chorus_metadata fields additive
- 4 EVT-T8 Forge sub-shapes (Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory)
- 2 EVT-T4 System sub-types (ActorBorn + ActorChorusMetadataBorn)
- 2 EVT-T3 delta_kinds active V1 (Update on actor_actor_opinion + Update on actor_session_memory; preserved from NPC_001 §13 derivation)
- 10+ V1 AC + 4 V1+ deferred
- ~10 deferrals (ACT-D1..ACT-D10)
- ~800-1000 line DRAFT spec estimate (large refactor; multiple aggregates + cross-feature integration)
- 4-commit cycle (Phase 0 this commit + DRAFT 2/4 + Phase 3 3/4 + closure+release 4/4)

---

## §5 — Cross-feature impact map (cascading closure-pass-extensions in commit 2/4)

### NPC_001 Cast closure-pass-extension (commit 2/4)

**Aggregate ownership transfers:**
- `npc` (R8 import) → SPLIT: `actor_core` (ACT_001 owns) + `actor_chorus_metadata` (ACT_001 owns; NPC-populated V1)
- `npc_session_memory` (R8 import) → RENAMED `actor_session_memory` (ACT_001 owns; per-(actor, session))
- `npc_pc_relationship_projection` (R8 import) → RENAMED `actor_actor_opinion` (ACT_001 owns; bilateral)
- `npc_node_binding` (NPC_001 owned) → KEPT (NPC-specific writer-node owner with epoch fence)

**Persona assembly §6 update:**
- `assemble_persona(npc_id)` → `assemble_persona(actor_id)` (kind-agnostic)
- 4 input reads: actor_core + actor_chorus_metadata (if AI-driven) + actor_session_memory + actor_actor_opinion
- Combiner logic preserved; 4 inputs same as NPC_001 §6 4 inputs

**§14 acceptance scenarios:** 10 scenarios preserved; AC names updated to actor_* terminology.

### NPC_002 Chorus closure-pass-extension (commit 2/4)

**Read path updates:**
- `NpcOpinion::for_pc(npc_id, pc_id)` → `ActorOpinion::for_target(observer_id, target_id)` (kind-agnostic)
- Tier 2-3 priority reads `actor_core.knowledge_tags` (was `npc.knowledge_tags`)
- Tier 4 V1+ reads REP_001 unchanged
- `npc_reaction_priority` aggregate (NPC_002-owned) UNCHANGED — NPC-specific orchestration data

**§14 acceptance scenarios:** 10 scenarios preserved; AC names updated to actor_* terminology.

### NPC_003 NPC Desires closure-pass-extension (commit 2/4)

**Field ownership transfer:**
- `npc.desires: Vec<NpcDesireDecl>` → `actor_chorus_metadata.desires: Vec<DesireDecl>` (renamed; kind-agnostic)
- DesireDecl type renamed from NpcDesireDecl
- Lifecycle preserved (author-declared V1; satisfaction toggle V1 via Forge)
- §16 acceptance: 5 scenarios preserved; AC names updated

### 02_storage R08 update (commit 2/4)

**Schema split + ownership transfer:**
- `npc` core schema split into `actor_core` + `actor_chorus_metadata`
- `npc_session_memory` renamed `actor_session_memory`
- `npc_pc_relationship_projection` renamed `actor_actor_opinion` (bilateral; key composite changed)
- Ownership note: ACT_001 owns 3 aggregates (formerly R8-locked NPC_001-imported); NPC_001 keeps `npc_node_binding`

**Storage agent buy-in:**
- Main session attributes R8 update to ACT_001 unification
- Additive split (not destructive); existing schema decomposed
- R8 changelog appended

### Boundary docs update (commit 2/4)

**`_boundaries/01_feature_ownership_matrix.md`:**
- 4 NEW aggregate rows: actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory (all ACT_001 owned)
- 3 transferred rows: REMOVE old `npc` + `npc_session_memory` + `npc_pc_relationship_projection` (NPC_001-imported); ADD new ACT_001-owned versions
- 1 NEW EVT-T4 sub-type: ActorBorn + ActorChorusMetadataBorn (ACT_001 owns)
- 4 NEW EVT-T8 sub-shapes: Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory
- 2 NEW EVT-T3 entries: actor_actor_opinion + actor_session_memory (ACT_001 owns; replaces NPC_001 entries)
- RejectReason namespace: `actor.*` → ACT_001
- NEW stable-ID prefix: `ACT-*`

**`_boundaries/02_extension_contracts.md`:**
- §1.4: `actor.*` namespace registration (6 V1 rules + 3 V1+ reservations)
- §2: CanonicalActorDecl ownership transfers from PL_001 + NPC_001 → ACT_001 (with NPC_001 contribution preserved as additive layered fields)

**`_boundaries/99_changelog.md`:** entry for ACT_001 unification

**`features/00_actor/_index.md`:** REP_001 row updated to DRAFT 2026-04-27

**Catalog:** `catalog/cat_00_ACT_actor_foundation.md` (NEW; ACT-A1..A8 axioms + ACT-D1..D10 deferrals + 14+ catalog entries)

### PCS_001 (separate future cycle) builds on ACT_001 stable base

When PCS_001 design starts:
- Reads `actor_core` + `actor_chorus_metadata` (sparse; PC populated V1+ when AI-driven offline) + `actor_actor_opinion` + `actor_session_memory`
- Owns `pc_user_binding` + `pc_mortality_state` + `pc_stats_v1_stub`
- xuyên không body_memory in `pc_user_binding`
- AC scenario: SPIKE_01 obs#5 literacy slip detection unchanged

---

## §6 — Boundary intersection summary

| Touched feature | Status | ACT_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | (none) | EntityRef + entity_binding | actor_core references ActorId per EF_001 §5.1 |
| IDF features (1..5) | CANDIDATE-LOCK | (none) | actor identity (race/lang/persona/origin/ideology) | All IDF aggregates remain per-actor; ACT_001 actor_core complements (canonical_traits ≠ IDF identity fields) |
| FF_001 Family | CANDIDATE-LOCK | (none) | family_node + dynasty | ACT_001 actor_core for identity; FF_001 for family graph |
| FAC_001 Faction | CANDIDATE-LOCK | (none) | faction + actor_faction_membership | Independent layers |
| REP_001 Reputation | CANDIDATE-LOCK | (none) | actor_faction_reputation | Independent layers |
| PROG_001 Progression | DRAFT | (none) | actor_progression + tracking_tier field | tracking_tier already on PROG_001 (NPC tier semantics); independent |
| RES_001 Resource | DRAFT | (none) | resource_inventory + vital_pool | Independent layers (EntityRef any) |
| PL_006 Status | CANDIDATE-LOCK | (none) | actor_status | Independent layer |
| WA_006 Mortality | CANDIDATE-LOCK | (none) | mortality_config (per-reality) | Independent layer; pc_mortality_state handoff to PCS_001 future |
| AIT_001 AI Tier | DRAFT 2026-04-27 | (none) | tier semantics | tracking_tier on PROG_001; chorus_metadata informs Tier 2-4 priority V1+ |
| NPC_001 Cast | CANDIDATE-LOCK ⚠ closure-pass-extension | actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory | npc_node_binding (kept) | 3 aggregates transferred to ACT_001; persona assembly §6 updated |
| NPC_002 Chorus | CANDIDATE-LOCK ⚠ closure-pass-extension | (none) | npc_reaction_priority + chorus_batch_state | Read paths updated to actor_* aggregates |
| NPC_003 NPC Desires | DRAFT ⚠ closure-pass-extension | desires field on actor_chorus_metadata | (no aggregate; field-on-actor_chorus_metadata) | Field ownership transfers; type renamed DesireDecl |
| 02_storage R08 | R-LOCKED ⚠ update within ACT_001 cycle | (none — R8 hosts schema) | R8 schema spec | Split + rename; main session attribution; additive change |
| RealityManifest envelope | unowned | canonical_actors ownership transfer + chorus_metadata fields | Envelope contract | Main session takes ownership transfer responsibility; PL_001 + NPC_001 contributions layered |
| `actor.*` rule_id namespace | not yet registered | All actor RejectReason variants | RejectReason envelope (Continuum) | Per `02_extension_contracts.md` §1.4 — register at ACT_001 DRAFT |
| Future PCS_001 PC substrate | brief (BLOCKED on ACT_001) | (none) | PC identity + mortality + stats stub | PCS_001 builds on ACT_001 stable base |
| Future AI-controls-PC-offline (V1+) | not started | (none — activates existing actor_chorus_metadata) | (V1+ feature owns activation logic) | Sparse row creation/removal on PC online↔offline transition |
| Future multi-PC realities (V1+) | not started | (none) | (V1+ multiplayer feature) | Bilateral actor_actor_opinion supports PC↔PC dynamics |

---

## §7 — What this concept-notes file is NOT

- ❌ NOT the formal ACT_001 design (no full Rust struct definitions, no §1-§N spec structure, no full acceptance criteria)
- ❌ NOT a lock-claim trigger (commit 2/4 will claim+release)
- ❌ NOT registered in ownership matrix yet
- ❌ NOT consumed by other features yet (NPC_001/002/003 closure-pass-extensions deferred to commit 2/4)

---

## §8 — Promotion checklist (when boundary lock free)

Before drafting `ACT_001_actor_foundation.md`:

1. [x] Q1-Q6 LOCKED via main session deep-dive 2026-04-27 (with Q3 REVISION + Q6 user-revised)
2. [ ] Wait for `_boundaries/_LOCK.md` to be free
3. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL — large cycle)
4. [ ] Create `ACT_001_actor_foundation.md` with full §1-§N spec (~800-1000 lines)
5. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — 4 NEW aggregates + 3 transferred from NPC_001 + EVT-T4/T8/T3 entries + namespace + ACT-* prefix
6. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 + §2
7. [ ] Update `_boundaries/99_changelog.md` — append ACT_001 entry
8. [ ] Update `02_storage/R08_npc_memory_split.md` — schema split + rename
9. [ ] Closure-pass-extension `features/05_npc_systems/NPC_001_cast.md` — ownership transfer + persona §6 update
10. [ ] Closure-pass-extension `features/05_npc_systems/NPC_002_chorus.md` — read paths updated
11. [ ] Closure-pass-extension `features/05_npc_systems/NPC_003_desires.md` — field ownership transfer
12. [ ] Create `catalog/cat_00_ACT_actor_foundation.md` — feature catalog (ACT-A1..A8 + ACT-D1..D10)
13. [ ] Update `00_actor/_index.md` — replace concept row with ACT_001 DRAFT row
14. [ ] Release `_boundaries/_LOCK.md` (in commit 4/4 closure pass)
15. [ ] Commit cycle: Phase 0 this commit + DRAFT 2/4 + Phase 3 3/4 + closure+release 4/4

---

## §9 — Status

- **Created:** 2026-04-27 by main session (commit 1/4 this turn)
- **Phase:** Q-LOCKED → DRAFT promotion ready (commit 2/4 next)
- **Lock state:** `_boundaries/_LOCK.md` FREE (last released by REP_001 closure 4/4 ec67d17). ACT_001 DRAFT 2/4 commit will claim+release in single `[boundaries-lock-claim]` cycle.
- **Estimated time to DRAFT 2/4:** 4-6 hours focused design work (large cycle); ~800-1000 line spec
- **Co-design dependencies (at DRAFT 2/4):**
  - NPC_001 closure-pass-extension (3 aggregates ownership transfer + persona §6 update)
  - NPC_002 closure-pass-extension (read paths updated)
  - NPC_003 closure-pass-extension (desires field transfer)
  - 02_storage R08 update (schema split + rename)
  - PCS_001 BLOCKED on ACT_001 stable base (separate cycle Q2 LOCKED)
- **Next action:** Commit 1/4 this turn — concept-notes Q1-Q6 LOCKED. Then commit 2/4 — DRAFT promotion + boundary register + cascading closure-pass-extensions + R8 update.
