# 00_actor — Index

> **Category:** ACT — Actor Foundation (foundation tier; unified substrate underlying NPC_001 + future PCS_001)
> **Catalog reference:** [`catalog/cat_00_ACT_actor_foundation.md`](../../catalog/cat_00_ACT_actor_foundation.md) (will be added with ACT_001 DRAFT 2/4)
> **Purpose:** UNIFIED actor identity + AI-drive metadata + bilateral opinion + session memory substrate. Eliminates the `npc` aggregate anomaly (only Tier 5 feature NOT per-actor unified pre-ACT_001) by lifting per-NPC aggregates to per-actor symmetric pattern. Future-proofs **AI-controls-PC-offline V1+** + **multi-PC realities** + **NPC↔NPC drama V1+** simultaneously.

**Active:** ACT_001 — **Actor Foundation** (DRAFT 2026-04-27 — commit 2/5 `[boundaries-lock-claim]` DRAFT promotion + boundary register; commits 3-5/5 next)

**Folder closure status:** **OPEN** — Phase 0 commit 1/5 (1c0d2d7; Q1-Q6 LOCKED) → commit 2/5 DRAFT + boundary register (this commit) → commit 3/5 cascading closure-pass-extensions (R8 + NPC_001/002/003) → commit 4/5 Phase 3 cleanup → commit 5/5 closure + lock release.

**Origin signal:**
- Main session insight 2026-04-27: substrate already unified Tier 5 (8+ features per-actor); `npc` aggregate anomaly identified
- User insight 2026-04-27: future "AI điều khiển người chơi offline" V1+ feature — control source DYNAMIC for PC (User online; AI offline); ActorKind doesn't shift but control state does
- 3-layer architectural model emerged: L1 Identity (stable) + L2 Capability/Kind (stable) + L3 Control source (dynamic)
- Q6 user-revised to (A) full unify all 3 opportunities NOW: actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — ACT_001 unification analysis + Q1-Q6 LOCKED | Q-LOCKED 2026-04-27 — captures 3-layer architectural model + 4-aggregate decomposition + Q1-Q6 LOCKED via main session deep-dive (Q3 REVISION + Q6 user-revised to full unify) | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| ACT_001 | **Actor Foundation** (ACT) | Unified per-actor substrate aggregating identity + AI-drive metadata + bilateral opinion + session memory. Replaces `npc` (R8 anomaly) with `actor_core` (L1 identity, always present) + `actor_chorus_metadata` (L3 AI-drive metadata, sparse — NPCs always; PCs V1+ when AI-driven). Replaces `npc_pc_relationship_projection` with `actor_actor_opinion` (bilateral; per-(observer, target)). Replaces `npc_session_memory` with `actor_session_memory` (per-(actor, session); supports AI-controls-PC-offline LLM context continuity V1+). NPC_001 closure-pass-extension transfers 3 aggregates to ACT_001; keeps `npc_node_binding`. Synthetic actors forbidden V1. 6 V1 reject rules (`actor.*` namespace) + 3 V1+ reservations. RealityManifest CanonicalActorDecl ownership transfers to ACT_001 + chorus_metadata field additive. 2 EVT-T4 + 4 EVT-T8 + 2 EVT-T3 sub-types. 10 V1 AC + 4 V1+ deferred. 10 deferrals (ACT-D1..ACT-D10). | **DRAFT** 2026-04-27 (commit 2/5 `[boundaries-lock-claim]` DRAFT promotion + boundary register) | [`ACT_001_actor_foundation.md`](ACT_001_actor_foundation.md) | 1c0d2d7 → (this commit 2/5) |

---

## Why this folder is concept-first

User direction 2026-04-27 picked R1 (start ACT_001 unification cycle) after deep-dive analysis of 3 opportunities at behavior layer (npc → actor unification).

But — this is the LARGEST mid-design refactor of LoreWeave to date:
- 4 NEW aggregates designed
- 02_storage R8 update (R-locked spec; main session ownership)
- 3 NPC features (NPC_001 + NPC_002 + NPC_003) require closure-pass-extensions
- Boundary docs extensive update (ownership matrix + extension contracts + changelog)

Concept-notes phase captures:

1. User framing (substrate consistency + future-proof AI-controls-PC-offline)
2. 3-layer architectural model (Identity / Capability / Control source)
3. Field decomposition across 4 aggregates
4. Q1-Q6 LOCKED via deep-dive (Q3 REVISION + Q6 full unify)
5. Cross-feature impact map (NPC_001/002/003 + 02_storage R8 + PCS_001 future)
6. Boundary intersections with all 8+ Tier 5 substrate features

Pattern proven: RES_001 + IDF + FF_001 + FAC_001 + REP_001 Phase 0 cycle. ACT_001 follows same — but with deeper architectural impact.

---

## Kernel touchpoints (anticipated; finalized at ACT_001 DRAFT 2/4)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on 4 NEW aggregates
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types for actor_actor_opinion + actor_session_memory; EVT-T8 Forge sub-shapes for actor_core + actor_chorus_metadata
- `_boundaries/01_feature_ownership_matrix.md` — 4 NEW aggregates added; 3 transfers from NPC_001 to ACT_001
- `_boundaries/02_extension_contracts.md` §1.4 — `actor.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for canonical_actor_cores (REQUIRED V1; renamed from npc_decls or merged with CanonicalActorDecl)
- `02_storage/R08_npc_memory_split.md` — UPDATE: split `npc` core into `actor_core` (kind-agnostic) + `actor_chorus_metadata` (sparse AI-drive); rename `npc_session_memory` → `actor_session_memory`; rename `npc_pc_relationship_projection` → `actor_actor_opinion` (bilateral)
- `00_entity/EF_001_entity_foundation.md` — ActorId source-of-truth consumed; ActorKind discrimination for sparse extension routing
- `05_npc_systems/NPC_001_cast.md` — closure-pass-extension: 3 aggregates moved to ACT_001; keep `npc_node_binding`; persona assembly §6 updated to read actor_core
- `05_npc_systems/NPC_002_chorus.md` — closure-pass-extension: read paths updated (NpcOpinion::for_pc reads actor_actor_opinion; priority Tier 2-3 reads actor_core; Tier 4 V1+ reads REP_001 unchanged)
- `05_npc_systems/NPC_003_desires.md` — closure-pass-extension: `desires` field moves from `npc.desires` → `actor_chorus_metadata.desires`
- Future PCS_001 — builds on ACT_001 stable base; owns `pc_user_binding` + `pc_mortality_state` + `pc_stats_v1_stub`
- Future AI-controls-PC-offline (V1+) — activates `actor_chorus_metadata` row for PCs when offline; `actor_session_memory` PC population
- Future multi-PC realities (V1+) — bilateral `actor_actor_opinion` supports PC↔PC dynamics

---

## Naming convention

`ACT_<NNN>_<short_name>.md`. Sequence per-category. ACT_001 is the foundation; future ACT_NNN reserved for V1+/V2 extensions (V1+ AI-controls-PC-offline activation feature / V1+ NPC↔NPC drama / V2+ actor cross-reality migration consolidation).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

ACT_001 is **the unification refactor** triggered by main session 2026-04-27 architectural review of PC vs NPC separation question. Resolves cross-feature inconsistencies:

- **`npc` aggregate anomaly** (only Tier 5 feature NOT per-actor unified pre-ACT_001) → ✅ RESOLVED via `actor_core` (kind-agnostic) + `actor_chorus_metadata` (sparse extension)
- **One-directional opinion** (`npc_pc_relationship_projection` PC→NPC only) → ✅ RESOLVED via `actor_actor_opinion` bilateral
- **PC chat history fragmentation** (chat-service vs world-service) → ✅ RESOLVED via `actor_session_memory` unified (V1 NPC populated; V1+ PC offline-AI-driven populated)

3-layer architectural model LOCKED:
- **L1 Identity** (`actor_core`) — canonical_traits + flexible_state + knowledge_tags + voice_register + core_beliefs_ref; always present post-creation
- **L2 Capability/Kind** — encoded in ActorId variant (PC / NPC / Synthetic); stable post-creation
- **L3 Control source** — dynamic (User / AI / Engine); determined at runtime
  - Control = User → PC online (drives via session/JWT)
  - Control = AI → NPC always; PC offline V1+ (drives via chorus orchestration; reads `actor_chorus_metadata`)
  - Control = Engine → Synthetic (no narrative substrate V1)

Boundary discipline (LOCKED at DRAFT 2/4):
- ACT_001 owns 4 substrate aggregates (kind-agnostic; per-actor)
- NPC_001 keeps `npc_node_binding` only (NPC-specific writer-node owner with epoch fence)
- PCS_001 (future) owns PC-specific aggregates (`pc_user_binding` + `pc_mortality_state` + `pc_stats_v1_stub`)
- 02_storage R8 updated to reflect new structure
- NPC_002 reads ACT_001 aggregates (no ownership transfer; consumer-only)
- NPC_003 `desires` field moves from npc to actor_chorus_metadata

V1+ activation features (downstream consumers):
- **AI-controls-PC-offline (V1+)** — activates `actor_chorus_metadata` row for offline PCs; chorus orchestrator drives offline PC via existing path (no new orchestrator code)
- **Multi-PC realities (V1+)** — bilateral `actor_actor_opinion` enables PC↔PC dynamics
- **NPC↔NPC drama (V1+)** — `actor_actor_opinion` enables sect rivalry NPC-internal opinion modifiers
