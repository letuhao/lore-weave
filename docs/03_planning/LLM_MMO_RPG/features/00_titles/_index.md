# 00_titles — Index

> **Category:** TIT — Title Foundation (foundation tier candidate post-FF_001 + FAC_001 + REP_001; Tier 5 Actor Substrate; closes the political-rank triangle)
> **Catalog reference:** `catalog/cat_00_TIT_title_foundation.md` (planned; created at DRAFT 2/4 commit per established pattern)
> **Purpose:** The substrate for **per-(actor, title) political/social rank holding** — captures one actor's *title-grant from a reality* (king / emperor / sect master 掌门 / family patriarch 族长 / lord / regent / etc.). Distinct from FAC_001 actor_faction_membership (per-(actor, faction) sect/order/guild membership with role) AND from REP_001 actor_faction_reputation (per-(actor, faction) bounded standing). Resolves FF-D8 (title inheritance rules + heir succession) + FAC-D6 (sect succession rules) + WA_006 sect-leader-death cascade gap. Wuxia-critical (sect-master inheritance / emperor succession / family-patriarch passing); D&D-critical (noble background + lord titles); CK3-pattern primary.

**Active:** TIT_001 — **Title Foundation** (CANDIDATE-LOCK 2026-04-27 — 4-commit cycle complete: Phase 0 f9e7600f + DRAFT 2/4 9456a446 + Phase 3 cleanup 3/4 2c00400f + closure 4/4 this commit)

**Folder closure status:** **COMPLETE 2026-04-27** — TIT_001 at CANDIDATE-LOCK. Folder ready. RESOLVES FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial; runtime gating V1+ alongside REP-D1) + WA_006 sect-leader-death cascade gap (full V1). Next priority candidates: PO_001 Player Onboarding (UI flow consumes PCS_001 primitives) / DIPL_001 Diplomacy Foundation V2+ (consumes FAC_001 + REP_001 + V1+ FactionElect TIT-D1) / AI-controls-PC-offline activation (cross-ref ACT-D1) / DRAFT closure passes for PROG_001/RES_001/AIT_001/TDIL_001 / SPIKE_01 turn 5 integration test design.

**V1+ priority signal:**
- FF_001 FF-D8 LOCKED: "Title inheritance rules + heir succession → V1+ TIT_001 Title Foundation reads FF_001 dynasty.current_head_actor_id"
- FAC_001 FAC-D6 LOCKED: "Sect succession rules → V1+ TIT_001 reads sect_leader role + master_actor_id"
- REP_001 REP-D9 LOCKED: "V1+ TIT_001 title-grant requires min rep" (now active V1 per Q4 anticipation; min_reputation_required field on TitleDecl)
- REP_001 _index.md coordination note: "Future TIT_001 + V1+ DIPL_001 + V1+ NPC_002 Tier 4 + V1+ WA_001 requires_reputation consume REP_001"
- FAC_001 _index.md kernel touchpoint: "WA_006 sect-leader death triggers V1+ TIT_001 succession"
- FAC_001 closure changelog: "TIT_001 Title Foundation (heir succession via FF_001 + FAC_001 + min REP_001 rep)" — flagged as V1+ next priority candidate
- REP_001 closure changelog: same — flagged V1+ next priority alongside CULT_001 + PCS_001
- 99_changelog.md 2026-04-27 (CULT_001 V2+ defer commit): "TIT_001 Title Foundation" listed as #1 next-priority candidate

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — TIT_001 brainstorm capture | CONCEPT 2026-04-27 — captures user framing post-FF/FAC/REP closure + 10-dimension gap analysis + Q1-Q10 placeholder for batched deep-dive | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit Phase 0) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | DRAFT 2026-04-27 — CK3 (primary; title hierarchy + succession laws) + Bannerlord (lord titles) + Game of Thrones political fantasy (king/regent/heir) + Wuxia novels (sect-leader 掌门 / emperor 皇帝 / family-head 族长) + Imperator Rome (senate titles) + Stellaris (ruler-traits) + WoW (achievement titles) + Dwarf Fortress (noble succession) + D&D 5e (noble background) — anchor: CK3 + Wuxia hybrid | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit Phase 0) |
| TIT_001 | **Title Foundation** (TIT) | Per-(actor, title) political/social rank holding via sparse `actor_title_holdings` aggregate (T2/Reality, sparse per-(actor, title_id) edge). 2 RealityManifest extensions: canonical_titles + canonical_title_holdings (both OPTIONAL V1). TitleDecl: TitleBinding 3-variant Discriminated enum (Faction/Dynasty/Standalone per Q2 B LOCKED) + SuccessionRule 3 V1 + 1 V1+ (Eldest FF_001 dynasty traversal / Designated canonical+Forge / Vacate; FactionElect V1+ DIPL_001 V2+ dependency per Q3 A LOCKED) + min_reputation_required Option<MinRepGate> V1 schema-reserved (validator V1+ alongside REP-D1 per Q4 C LOCKED) + TitleAuthorityDecl (faction_role_grant V1 active + narrative_hint I18nBundle V1 active LLM persona briefing + lex_axiom_unlock_refs V1 schema-reserved per Q10 B LOCKED) + MultiHoldPolicy 3-variant per-title author-declared (Exclusive/StackableUnlimited default/StackableMax(N) per Q5 C LOCKED) + VacancySemantic 3-variant per-title author-declared (PersistsNone default/Disabled/Destroyed per Q9 D LOCKED). 1 EVT-T4 TitleGranted (canonical seed + Forge admin + SuccessionCascade) + 3 EVT-T8 Forge admin (GrantTitle/RevokeTitle/DesignateHeir) + 1 EVT-T3 TitleSuccessionTriggered (sparse on cascade) + 1 EVT-T1 TitleSuccessionCompleted narrative milestone for LLM. Cross-aggregate validator TIT-C1 (immediate cascade synchronously on WA_006 mortality EVT-T3 actor_dies same turn per Q7 A LOCKED) + 7 schema validators TIT-C2..C8 (canonical seed bootstrap). 9 V1 reject rules in `title.*` namespace + 5 V1+ reservations. RESOLVES FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial) + WA_006 sect-leader-death cascade gap (full V1). 10 V1 AC + 4 V1+ deferred. 12 deferrals (TIT-D1..TIT-D12). 8 axioms TIT-A1..A8. Q1-Q10 LOCKED via 4-batch deep-dive zero revisions. Schema-stable / activation-deferred V1+ discipline (TIT-A8). Per-title author-declared policy discipline (TIT-A5). 3-layer separation discipline (TIT-A4): TIT_001 ≠ FAC_001 actor_faction_membership ≠ REP_001 actor_faction_reputation. | **CANDIDATE-LOCK** 2026-04-27 (4-commit cycle complete) | [`TIT_001_title_foundation.md`](TIT_001_title_foundation.md) | f9e7600f → 9456a446 → 2c00400f → (this commit 4/4) |

---

## Why this folder is concept-first

User direction 2026-04-27 picked TIT_001 as next-priority post-CULT_001 V2+ defer (commit d57fb7fc). Title Foundation is THE missing piece between FF_001 (family-graph dynasty.current_head_actor_id) + FAC_001 (sect_leader role + master_actor_id) + REP_001 (per-faction min rep gate) and the inheritance/succession mechanics that wuxia + D&D + CK3-style political realities require.

But — title system is wide. Three competing patterns in market:
1. **Hierarchical title tree** (CK3 baron→count→duke→king→emperor; Imperator Rome; Stellaris empires) — discrete tiers with vassalage relationships
2. **Faction-bound role** (Bannerlord lord = clan-bound; wuxia sect-master = sect-bound) — title = faction-level role grant
3. **Achievement-honor** (WoW "Slayer of the Lich King"; D&D 5e noble background; Dwarf Fortress nobility) — title = social-recognition without governance authority

V1 scope must be narrow. Concept-notes phase captures:

1. User framing (post-FF/FAC/REP closure + cross-feature seam consolidation per FF-D8 + FAC-D6 + REP-D9 + WA_006)
2. Worked examples (Wuxia 3-title scenario / Modern political-rank scenario / D&D noble-knight scenario)
3. Gap analysis (10 dimensions across 4 grouped concerns: aggregate model + binding scope + succession + authority)
4. Boundary intersections with locked features (10+ touched)
5. Critical Q1-Q10 for V1 minimum + V1+ extensibility
6. Reference materials slot

Pattern proven: RES_001 + IDF + FF_001 + FAC_001 + REP_001 + ACT_001 + PCS_001 Phase 0 — concept-notes → reference survey → Q-deep-dive → DRAFT.

---

## Kernel touchpoints (anticipated; finalized at TIT_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on `actor_title_holdings` aggregate
- `07_event_model/03_event_taxonomy.md` — EVT-T4 System sub-type for `TitleGranted` (canonical seed) + EVT-T8 AdminAction for `Forge:GrantTitle`/`Forge:RevokeTitle`/`Forge:DesignateHeir` + EVT-T3 Derived for `TitleSuccessionTriggered` + EVT-T1 Narrative for `TitleSuccessionCompleted`
- `_boundaries/01_feature_ownership_matrix.md` — `actor_title_holdings` aggregate added at DRAFT 2/4
- `_boundaries/02_extension_contracts.md` §1.4 — `title.*` rule_id namespace (~5-7 V1 reject rules + V1+ reservations)
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extensions for `canonical_titles` + `canonical_title_holdings`
- `00_entity/EF_001_entity_foundation.md` — ActorId source-of-truth consumed by TIT_001 holdings
- `00_family/FF_001_family_foundation.md` FF-D8 — TIT_001 RESOLVES (heir succession via dynasty.current_head_actor_id traversal)
- `00_faction/FAC_001_faction_foundation.md` FAC-D6 — TIT_001 RESOLVES (sect succession rules via sect_leader role + master_actor_id)
- `00_faction/FAC_001_faction_foundation.md` actor_faction_membership.role_id — TIT_001 V1 may grant FactionRoleId on title hold (TitleAuthorityDecl.faction_role_grant)
- `00_reputation/REP_001_reputation_foundation.md` REP-D9 — TIT_001 PARTIAL RESOLVES (min_reputation_required field on TitleDecl active V1; runtime rep gating V1+ alongside REP-D1 runtime delta milestone)
- `00_resource/RES_001_resource_foundation.md` I18nBundle pattern — TIT_001 conforms (TitleDecl.display_name + TitleDecl.description multi-language)
- `02_world_authoring/WA_001_lex.md` — V1+ AxiomDecl.requires_title hook (title-gated abilities; e.g., "only sect-master can perform Sect-Foundation Ritual"); WA_001 closure pass V1+ adds 5-companion-fields uniformly (race + ideology + faction + reputation + title)
- `02_world_authoring/WA_003_forge.md` — Forge admin handlers for GrantTitle / RevokeTitle / DesignateHeir + forge_audit_log 3-write atomic pattern
- `02_world_authoring/WA_006_mortality.md` — sect-leader/title-holder death event triggers TIT_001 succession cascade (cross-aggregate C-rule registered in `_boundaries/03_validator_pipeline_slots.md`)
- `00_progression/PROG_001_progression_foundation.md` — TIT_001 reads ProgressionInstance values? (TBD Q-decision; e.g., title may require min cultivation realm OR min character level for hold)
- `00_actor/ACT_001_actor_foundation.md` — actor_core canonical_traits.title_held? (TBD Q-decision; alternative model: title held tracked in canonical_traits hint)
- `05_npc_systems/NPC_001_cast.md` — V1+ NPC persona AssemblePrompt reads `actor_title_holdings` (Lý Minh's "Đông Hải Đạo Cốc Trưởng Lão" appears in persona briefing)
- `05_npc_systems/NPC_002_chorus.md` Tier 4 priority — V1+ titled-actor (high-rank holder) gets NPC_002 priority modifier (rare)
- `04_play_loop/PL_005_interaction.md` — V1+ Strike/Speak action by titled actor may carry title-narrative hint
- Future PCS_001 — PC creation form may set initial title (V1+ origin-pack-driven; default no title)
- Future CULT_001 V2+ template library — CultivationRealmDecl may declare title-grant per realm tier (e.g., reaching Hóa Thần grants "Đại Trưởng Lão" sect-elder title V2+)
- Future DIPL_001 Diplomacy V2+ — title-holder = inter-faction-war participant + treaty-signer authority
- Future quest features (V2+ 13_quests) — quest reward = title grant

---

## Naming convention

`TIT_<NNN>_<short_name>.md`. Sequence per-category. TIT_001 is the foundation; future TIT_NNN reserved for V1+/V2 extensions (TIT_002 V1+ FactionElect SuccessionRule active / TIT_003 V2+ vassalage hierarchy / TIT_004 V2+ multi-axis title taxonomy).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

TIT_001 is **priority 7+ post-IDF closure** per IDF folder closure roadmap (50d65fa) AND the **CULT_001 V2+ defer follow-up next-priority** per 99_changelog.md 2026-04-27 entry. Resolves three V1+ deferrals + one cross-aggregate cascade gap:

- **FF-D8** (FF_001): Title inheritance rules + heir succession → V1+ TIT_001 reads FF_001 dynasty.current_head_actor_id (V1 RESOLVES — full active)
- **FAC-D6** (FAC_001): Sect succession rules → V1+ TIT_001 reads FAC_001 sect_leader role + master_actor_id (V1 RESOLVES — full active)
- **REP-D9** (REP_001): V1+ TIT_001 title-grant requires min rep → V1 PARTIAL RESOLVES (schema active V1; runtime rep gating V1+ alongside REP-D1)
- **WA_006 sect-leader-death cascade** (gap from FAC_001 _index.md kernel touchpoint): WA_006 mortality event → TIT_001 succession cross-aggregate C-rule (V1 RESOLVES — full active)

**3-layer separation discipline (CRITICAL — must hold post-DRAFT):**

| Layer | Owner | Shape | Use case |
|---|---|---|---|
| **Faction membership** (operational role) | FAC_001 `actor_faction_membership` | per-(actor, faction) — faction_id + role_id + status_tags | Lý Minh là Đệ tử của Đông Hải Đạo Cốc with role=disciple |
| **Faction reputation** (standing) | REP_001 `actor_faction_reputation` | per-(actor, faction) — bounded i16 score + tier label | Lý Minh có Honored standing với Đông Hải Đạo Cốc |
| **Title held** (political/social rank) | TIT_001 `actor_title_holdings` (proposed) | per-(actor, title) — title_id + granted_at_fiction_ts + binding_ref | Lý Minh holds "Đông Hải Đạo Cốc Trưởng Lão" title |

These three layers are COMPLEMENTARY not duplicative. Wuxia narrative example "Lý Minh Đệ Tử của Đông Hải Đạo Cốc với Honored standing và Trưởng Lão title" uses ALL THREE layers simultaneously. NPC_002 Chorus + NPC_001 persona AssemblePrompt + LLM narration consume all three for political/social context.

Boundary discipline (anticipated; locked at DRAFT):
- TIT_001 V1 = per-(actor, title) holding aggregate; title declarations + initial holdings via canonical seed; Forge admin V1; runtime gameplay grant via Lex axiom + cascade triggers V1+ if needed
- TIT_001 V1+ = FactionElect SuccessionRule active + TitleAuthorityDecl.lex_axiom_unlock active (WA_001 requires_title hook activates) + cross-faction title hierarchy (vassalage)
- V2+ vassalage hierarchy (CK3 baron→count→duke→king→emperor) — separate TIT_NNN feature OR major TIT_001 schema migration
- V2+ Heresy cross-reality title migration (V2+ WA_002)
- Cross-feature: WA_001 V1+ requires_title axiom hook
- Cross-feature: PL_005 V1+ titled actor narrative carries title context
- Cross-feature: WA_006 sect-leader death → TIT_001 succession cascade (V1 active)
- Synthetic actors forbidden V1 (consistent with IDF + FF + FAC + REP + RES + PROG discipline)
