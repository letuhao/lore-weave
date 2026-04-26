# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

---

## 2026-04-26 — IDF folder 10/15: IDF_004 Origin Foundation DRAFT + boundary register

- Lock continues from commit 1/15
- `01_feature_ownership_matrix.md`: NEW row actor_origin (T2/Reality, IDF_004 DRAFT); EVT-T8 Forge:EditOrigin; ORG-* prefix
- `02_extension_contracts.md`: §1.4 origin.* (4 V1 rules + 2 V1+); §2 RealityManifest origin_packs OPTIONAL V1
- IDF_004 file: renamed concept → DRAFT; full §1-§19 spec
- V1 minimal stub 4 fields (birthplace + lineage_id opaque + native_language + default_ideology_refs) per POST-SURVEY-Q4
- ORG-D11 NEW: birth event metadata V1+ (thiên kiêu chi tử markers)
- ORG-D12 NEW: FF_001 Family Foundation V1+ HIGH PRIORITY post-IDF closure
- 10 V1-testable AC + 3 V1+ deferred; 12 deferrals (ORG-D1..D12)

---

## 2026-04-26 — IDF folder 9/15: IDF_003 closure pass → CANDIDATE-LOCK

3/5 IDF features now CANDIDATE-LOCK. Lock continues claimed.

---

## 2026-04-26 — IDF folder 8/15: IDF_003 Phase 3 cleanup

5 Phase 3 fixes (PersonalityArchetypeId typed newtype + Synthetic exclusion confirmed + opinion drift formula explicit + §15.4 LOCK criterion split + PRS-D-NEW deferral). No boundary changes.

---

## 2026-04-26 — IDF folder 7/15: IDF_003 Personality Foundation DRAFT + boundary register

- Lock continues from commit 1/15
- Files modified within `_boundaries/`:
  - `01_feature_ownership_matrix.md`: NEW row actor_personality (T2/Reality, IDF_003 DRAFT); EVT-T8 Forge:EditPersonality; PRS-* prefix
  - `02_extension_contracts.md`: §1.4 personality.* namespace (3 V1 rules + 2 V1+); §2 RealityManifest personality_archetypes REQUIRED V1
- IDF_003 file: renamed concept → DRAFT; full §1-§19 spec
- 12 V1 archetypes locked per POST-SURVEY-Q1 (Stoic/Hothead/Cunning/Innocent/Pious/Cynic/Worldly/Idealist + Loyal/Aloof/Ambitious/Compassionate)
- 5-variant VoiceRegister locked per POST-SURVEY-Q7 (Formal/Neutral/Casual/Crude/Archaic)
- Resolves PL_005b §2.1 speaker_voice orphan ref + PL_005c INT-INT-D5 per-personality opinion modifier
- 10 V1-testable AC + 2 V1+ deferred; 8 deferrals (PRS-D1..D7 + PRS-D-NEW)

---

## 2026-04-26 — IDF folder 6/15: IDF_002 closure pass → CANDIDATE-LOCK

- Lock continues from commit 1/15
- `01_feature_ownership_matrix.md` actor_language_proficiency row: DRAFT → **CANDIDATE-LOCK 2026-04-26**
- IDF_002 status header DRAFT → CANDIDATE-LOCK
- `_index.md` IDF_002 row updated CANDIDATE-LOCK
- 2/5 IDF features now CANDIDATE-LOCK

---

## 2026-04-26 — IDF folder 5/15: IDF_002 Phase 3 cleanup

- Lock continues from commit 1/15
- No boundary changes (Phase 3 = internal cleanup)
- 5 Phase 3 findings applied: LanguageId typed newtype + Synthetic actor exclusion + Speak validator threshold note + LNG-D9 deferral tightening + §15.4 LOCK criterion split
- §19 readiness checklist updated

---

## 2026-04-26 — IDF folder 4/15: IDF_002 Language Foundation DRAFT + boundary register

- **Lock continues** from commit 1/15
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - NEW row: `actor_language_proficiency` aggregate (T2/Reality, IDF_002 DRAFT 2026-04-26)
    - Fix: race_assignment Notes column restored (commit 3/15 inadvertently truncated; now restored)
    - EVT-T8 Administrative sub-shape: NEW `Forge:EditLanguageProficiency` (IDF_002 owns)
    - Stable-ID prefix: NEW `LNG-*` row
  - `02_extension_contracts.md`:
    - §1.4 `language.*` namespace: 4 V1 rule_ids (unknown_language_id / speaker_proficiency_insufficient / listener_proficiency_insufficient (V1+ active) / proficiency_axis_invalid) + 2 V1+ reservations (dialect_mismatch / code_switch_unsupported)
    - §2 RealityManifest: NEW `languages: Vec<LanguageDecl>` REQUIRED V1
- **IDF_002 file:** renamed concept → DRAFT; full §1-§19 spec (~530 lines). 10 V1-testable AC + 2 V1+ deferred. 9 deferrals LNG-D1..D9. SPIKE_01 turn 5 literacy slip canonical reproducibility gate (LM01 Quan thoại Native + Cổ ngữ Read=None).
- **Survey-informed adjustments locked** — concept-note IDF_002 already had no survey-mandated changes (Q's locked at original concept).
- **Critical distinction:** LanguageId (IDF_002 in-fiction) vs LangCode (RES_001 engine UI ISO-639-1) — runtime newtype assert V1; LNG-D8 compile-time V1+.

---

## 2026-04-26 — IDF folder 3/15: IDF_001 closure pass → CANDIDATE-LOCK

- **Lock continues** from commit 1/15
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md` race_assignment row: status DRAFT → **CANDIDATE-LOCK 2026-04-26 IDF folder closure 3/15**
- **IDF_001 status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` IDF_001 row updated:** status CANDIDATE-LOCK + Phase 3 + closure pass note
- **Reason:** IDF_001 design complete + Phase 3 cleanup applied (5 fixes) + boundary registered (race_assignment aggregate + RaceBorn EVT-T4 + Forge:EditRaceAssignment EVT-T8 + race.* namespace + races RealityManifest extension + RAC-* stable-ID prefix). Ready for AC-RAC-1..10 integration tests. CANDIDATE-LOCK → LOCK gate when all V1-testable scenarios pass against Wuxia + Modern reality fixtures.
- **Lock continues claimed** for IDF_002 cycle (commits 4-6/15) + IDF_003 (7-9) + IDF_004 (10-12) + IDF_005 (13-15 + final lock release).

---

## 2026-04-26 — IDF folder 2/15: IDF_001 Phase 3 cleanup

- **Lock continues** from commit 1/15 (still claimed by main session 2026-04-26 IDF folder cycle)
- **Files modified within `_boundaries/`:** none (Phase 3 is internal IDF_001 documentation cleanup; no aggregate/namespace/RealityManifest changes)
- **IDF_001 Phase 3 findings applied (5 items):**
  - S1.1 §2 RaceId clarified as typed newtype `pub struct RaceId(pub String)` (matches PlaceId / ChannelId foundation tier pattern); cross-type collision avoidance noted vs LangCode (RES_001) + LanguageId (IDF_002)
  - S1.2 §2 MortalityKind clarified as WA_006-owned (IDF_001 imports; does not redefine); Ghost AlreadyDead override semantics
  - S2.1 §11 Wuxia bootstrap Ghost lifespan changed from `0 (immortal)` → `1 (placeholder; AlreadyDead bypasses)` to comply with `lifespan_years ≥ 1` schema rule
  - S2.2 §11 Validate step rewording — Ghost lifespan=1 placeholder + override=AlreadyDead path documented
  - S3.1 §2 cross-feature distinction for RaceId vs LangCode vs LanguageId
- **§19 readiness checklist updated** with Phase 3 cleanup items per section
- **Lock continues claimed** for IDF_001 closure pass (commit 3/15) + IDF_002..005 cycle

---

## 2026-04-26 — IDF folder DRAFT promotion 1/15: IDF_001 Race Foundation DRAFT + boundary register

- **Lock claim:** main session 2026-04-26 (IDF folder Phase 1 — 5 IDF features DRAFT promotion + Phase 3 + closure pass cycle); this commit `[boundaries-lock-claim]` (claim only — release at IDF_005 closure final commit per PL folder pattern; ~15 commits total)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claimed by main session 2026-04-26 (IDF folder DRAFT promotion cycle)
  - `01_feature_ownership_matrix.md`:
    - NEW row: `race_assignment` aggregate (T2/Reality, owner=IDF_001 Race Foundation DRAFT 2026-04-26 — Tier 5 Actor Substrate)
    - EVT-T4 System sub-type ownership: NEW `RaceBorn` (IDF_001 owns; emitted alongside EF_001 EntityBorn at canonical seed)
    - EVT-T8 Administrative sub-shape ownership: NEW `Forge:EditRaceAssignment` (IDF_001 owns; uses forge_audit_log)
    - Stable-ID prefix table: NEW `RAC-*` row (axioms / deferrals / decisions; catalog/cat_00_IDF_identity_foundation.md to be added)
  - `02_extension_contracts.md`:
    - §1.4 RejectReason namespace: NEW `race.*` row with 5 V1 rule_ids (unknown_race_id / assignment_immutable / lex_axiom_forbidden / size_category_invalid / lifespan_invalid) + 4 V1+ reservations (cross_reality_mismatch / transformation_invalid / reincarnation_invalid_target / cyclic_lineage_v1plus). V1 user-facing rejects: unknown_race_id + assignment_immutable only. i18n: ships I18nBundle from day 1 per RES_001 §2 contract.
    - §2 RealityManifest: NEW `races: Vec<RaceDecl>` REQUIRED V1 extension entry. Wuxia preset 5 races; Modern 1; Sci-fi 3. Cross-reality RaceId collision allowed (different semantics).
- **IDF_001 file:** renamed `IDF_001_race_concept.md` → `IDF_001_race.md`; rewritten as full §1-§19 DRAFT spec mirroring EF_001 structure. Status header CONCEPT → DRAFT 2026-04-26. 10 V1-testable acceptance scenarios AC-RAC-1..10 + 3 V1+ deferred (AC-RAC-V1+1..3). 11 deferrals RAC-D1..D11.
- **Survey-informed adjustments locked** (per `ae7d280` POST-SURVEY confirmations):
  - RAC-Q4 (size categories) LOCKED 6 V1: Tiny/Small/Medium/Large/Huge/Gargantuan (Pathfinder 2e full coverage; POST-SURVEY-Q2)
  - RAC-D11 NEW: cultivation realm = SEPARATE V1+ feature CULT_001 (NOT IDF_001 expansion; POST-SURVEY-Q5)
- **Reason:** Tier 5 Actor Substrate Foundation start. IDF_001 is first of 5 IDF features. Mirrors PL folder closure pattern (lock-claim once; release at last commit). Ready for AC-RAC-1..10 integration tests against Wuxia + Modern reality fixtures.
- **Drift watchpoints unchanged at 8 active.**
- **Lock continues:** still claimed for IDF_001 Phase 3 + closure + IDF_002/003/004/005 cycle. Release at IDF_005 closure final commit with `[boundaries-lock-release]` prefix.

---

## 2026-04-26 — NPC_003 NPC Desires LIGHT DRAFT (sandbox-mitigation Path A V1)

- **Lock claim:** main session 2026-04-26 (NPC_003 Desires LIGHT — Path A V1 from `13_quests/00_V2_RESERVATION.md` §5); this commit `[boundaries-lock-claim+release]` (single-cycle)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim + release
  - `01_feature_ownership_matrix.md`:
    - **Updated `npc` (R8 import) row:** added 2026-04-26 NPC_003 extension note — `desires: Vec<NpcDesireDecl>` field per I14 additive evolution; NPC_001 still owns aggregate, NPC_003 owns desires field shape + lifecycle
    - **Updated `RealityManifest` extension row:** added NPC_003 contribution (`npc_desires: HashMap<NpcId, Vec<NpcDesireDecl>>` + `desires_prompt_top_n: u8`, OPTIONAL V1)
    - **Stable-ID prefix:** added `DSR-D*` / `DSR-Q*` deferral/question prefix owned by NPC_003
  - `02_extension_contracts.md` §2 (RealityManifest): added 2 OPTIONAL V1 fields (`npc_desires` + `desires_prompt_top_n`) with inline doc comments
  - `99_changelog.md`: this entry
- **Files created within `features/05_npc_systems/`:**
  - `NPC_003_desires.md` — DRAFT (this commit) — 11 sections / ~280 lines / 5 V1-testable acceptance scenarios AC-DSR-1..5 / 8 deferrals DSR-D1..D8 / 3 open questions DSR-Q1..Q3
- **Files modified within `features/05_npc_systems/`:**
  - `_index.md`: re-opened folder closure status (was CLOSED 2026-04-26 with NPC_001 + NPC_002 CANDIDATE-LOCK; NPC_003 ADDS to folder without modifying existing locks per I14 additive evolution); added NPC_003 row to feature list
- **Files modified within `catalog/`:**
  - `cat_05_NPC_systems.md`: added NPC-12 entry pointing at NPC_003 design file
- **Q-resolution / decision LOCKED:**
  - **Path A approach** (NPC desires LIGHT) selected over Path B (Reality scenario seed V1+30d) and Path C (full quest system V2) for V1 sandbox-mitigation
  - **NO state machine / NO objective tracking / NO rewards** — discipline maintained; this is LLM-context scaffolding only
  - **5 desires/NPC cap V1** — focuses authors on driving traits, not exhaustive goal lists
  - **i18n discipline** — desire.kind: I18nBundle (RES_001 §2 cross-cutting pattern adopted)
  - **Top-N filtering** — RealityManifest.desires_prompt_top_n (default 3) controls prompt budget impact (per PL_001 §17 prompt-budget discipline)
  - **Author-only satisfaction toggle V1** — Forge `ToggleNpcDesire` AdminAction (NEW; WA_003 closure pass folds into ForgeEditAction enum); LLM-detection-with-author-confirm V1+30d (DSR-D3)
  - **Satisfied desires PERSIST in Vec** — not removed; LLM may narratively reference past achievements
- **Drift watchpoints: 8 active** (no change). NPC_003 doesn't introduce new watchpoints — light feature with clear boundary.
- **Lock RELEASED** at end of this commit (`[boundaries-lock-claim+release]` single-cycle)
- **Reason / handoff:** NPC_003 closes the V1 sandbox-mitigation gap raised by user 2026-04-26 ("game giống sandbox, chả có gì để làm"). Foundation tier 5/5 + V1 vertical mechanics + V1 sandbox-mitigation now complete. NPCs have author-declared goals → LLM uses goals → game has direction without full quest system. QST_001 V2 quest system can later integrate via DSR-D4 bridge (quest completion auto-toggles desire) — boundary clean. Next priorities: PCS_001 parallel agent kickoff (brief ready) / PO_001 PC creation flow (V1-blocking, depends on PCS_001) / WA_003 closure pass to fold in `ToggleNpcDesire` AdminAction sub-shape.

---

## 2026-04-26 — RES_001 downstream HIGH-priority impacts applied (Phase 2 of foundation tier completion)

- **Lock claim:** main session 2026-04-26 (RES_001 §17.2 HIGH priority downstream); this commit `[boundaries-lock-claim+release]` (single-cycle)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-26 (RES_001 downstream Phase 2) → None at release
  - `99_changelog.md`: this entry (small — most downstream changes happen in feature design files, not boundary files)
- **Files modified within `features/` and `07_event_model/`** (HIGH priority downstream from RES_001 §17.2):
  - `features/04_play_loop/PL_006_status_effects.md`: **promoted Hungry from V1+reserved → V1 active** (5 V1 status kinds total); StatusFlag enum + StatusStackPolicy table + magnitude semantics §10 documented (1-3 mild / 4-6 severe-narrative-Starving / 7+ critical = MortalityTransitionTrigger Starvation); header status note added
  - `features/02_world_authoring/WA_006_mortality.md`: **§6.5 added MortalityCauseKind catalog** documenting V1 cause kinds (KilledBy / Starvation / AdminKill / + V1+ reserved Suicide / EnvironmentalHazard); enum implementation deferred to PCS_001 first design pass per thin-rewrite ownership boundary; header status updated
  - `features/04_play_loop/PL_005_interaction.md`: **§9.1 added RES_001 cross-reference** documenting (a) Use kind Harvest sub-intent for cell harvesting + (b) Trade flow as Give-reciprocal pair V1 (dedicated Trade kind V1+30d); clarifies `interaction.*` (PL_005-owned) vs `resource.*` (RES_001-owned) namespace boundary; PL_005 cascade emits `resource.*` rejects when RES-V3 fires; header status updated
  - `features/00_entity/EF_001_entity_foundation.md`: **§3.1 entity_binding extended** with `cell_owner: Option<EntityRef>` (Q9 LOCKED — body-bound cell ownership) + `inventory_cap: Option<CapacityProfile>` (Q6 schema reservation; enforcement V1+30d) + `EntityRef` enum (Actor/Cell/Item/Faction discriminator used by RES_001 ownership semantics) + `CapacityProfile` reserved struct; header status updated
  - `features/06_pc_systems/00_AGENT_BRIEF.md`: **§4.4f mandatory RES_001 reading added** + **§S8 NEW IN-scope clause "Xuyên không body-substitution + cell-ownership inheritance"** documenting body-bound vital_pool + actor-identity resource_inventory + body-bound cell_owner inheritance semantics during xuyên không event (PCS_001 owns mechanic; RES_001 owns resource-side semantics); validation contract via `PcXuyenKhongCompleted` event; AC scenario "Lý Minh xuyên không inherits Trần Phong's tiểu điếm cell ownership"
  - `07_event_model/03_event_taxonomy.md`: **EVT-T3 Derived V1 aggregate types list expanded** (added `vital_pool` + `resource_inventory` from RES_001) + **EVT-T5 Generated sub-types table expanded** (added 4 V1 RES_001 generators: Scheduled:CellProduction / Scheduled:NPCAutoCollect / Scheduled:CellMaintenance / Scheduled:HungerTick with day-boundary trigger + Coordinator sequencing) + Phase 5 examples table extended with 6 RES_001 mappings (4 EVT-T5 + 2 EVT-T3)
- **Downstream impact items resolved (6 of 17 from RES_001 §17.2):**
  - ✅ HIGH: PL_006 Hungry V1+reserved → V1 active (5 V1 status kinds)
  - ✅ HIGH: WA_006 §6.5 MortalityCauseKind catalog (Starvation reserved for PCS_001 implementation)
  - ✅ HIGH: PL_005 §9.1 harvest sub-intent + trade flow + namespace boundary clarity
  - ✅ HIGH: EF_001 §3.1 cell_owner + inventory_cap fields + EntityRef enum + CapacityProfile struct
  - ✅ HIGH: PCS_001 brief §4.4f + §S8 body-substitution mechanic + RES_001 mandatory reading
  - ✅ HIGH: 07_event_model 4 EVT-T5 + 2 EVT-T3 RES_001 sub-types registered
- **Remaining downstream items deferred** (11 of 17 — MEDIUM/LOW priority follow-ups):
  - MEDIUM: NPC_001 auto-collect Generator doc / WA_003 4 ForgeEditAction sub-shapes / PL_001 RejectReason user_message envelope field / PCS_001 first design pass (parallel agent)
  - LOW: PF_001 cell-as-economic-entity cross-reference / NPC_001 vital_profiles per-class declaration / i18n cross-cutting audit (existing Vietnamese reject copy migration)
- **Drift watchpoints: 8 active** (no change). RES_001 downstream Phase 2 doesn't introduce new watchpoints — all changes were targeted edits to already-LOCKED features.
- **Lock RELEASED** at end of this commit (`[boundaries-lock-claim+release]` single-cycle)
- **Reason / handoff:** RES_001 downstream Phase 2 closes the 6 HIGH priority impact items from RES_001 §17.2. Foundation tier 5/5 + foundation-tier-cross-feature-integration is now consistent across all V1 LOCK/DRAFT features. Next priorities: (a) PCS_001 PC Substrate parallel agent kickoff (brief §4.4f + §S8 ready; xuyên không mechanic now formally specified; can start design pass), (b) MEDIUM/LOW downstream cleanups in subsequent commits as time permits, (c) PO_001 PC Creation flow design (V1-blocking; depends on PCS_001).

---

## 2026-04-26 — RES_001 Resource Foundation DRAFT promotion + i18n cross-cutting pattern introduction

- **Lock claim:** main session 2026-04-26 (RES_001 DRAFT promotion); this commit `[boundaries-lock-claim+release]` (single-commit cycle)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-26 (RES_001 DRAFT) → None at release
  - `01_feature_ownership_matrix.md`:
    - **NEW aggregate rows:** `vital_pool` (T2/Reality, body-bound, actor-only, NON-TRANSFERABLE) + `resource_inventory` (T2/Reality, portable, EntityRef-any) — both owned by RES_001 DRAFT
    - **Updated `actor_status` row:** flag downstream impact — PL_006 closure pass promotes Hungry from V1+reserved → V1 active with magnitude semantics 1/4/7 thresholds (Q5 LOCKED)
    - **Updated `RealityManifest` extension row:** RES_001 contributes 9 OPTIONAL V1 fields (resource_kinds / currencies / vital_profiles / producers / prices / cell_storage_caps / cell_maintenance_profiles / initial_resource_distribution / social_initial_distribution) with engine defaults
    - **Updated `RejectReason` namespace prefixes row:** added `resource.*` → RES_001 (12 V1 rule_ids); flagged i18n envelope-extension (`user_message: I18nBundle`)
    - **NEW row `i18n I18nBundle cross-cutting type`:** RES_001 §2 introduces engine-wide pattern (English `snake_case` stable IDs + `I18nBundle` for user-facing strings)
    - **NEW EVT-T3/T5/T8 sub-type ownership rows:** `aggregate_type=vital_pool` + `aggregate_type=resource_inventory` (T3 Derived); 4 V1 Generators `Scheduled:CellProduction`/`NPCAutoCollect`/`CellMaintenance`/`HungerTick` (T5 Generated); 4 AdminAction sub-shapes `Forge:EditCellProducerProfile`/`Forge:EditPriceDecl`/`Forge:EditCellMaintenanceCost`/`Forge:GrantInitialResources` (T8 Administrative; WA_003 Forge ForgeEditAction enum extension at WA closure)
    - **Stable-ID prefix:** added `RES-*` foundation tier (catalog/cat_00_RES_resource.md created)
  - `02_extension_contracts.md` §1 (TurnEvent envelope): added `RejectReason.user_message: I18nBundle` field + `I18nBundle` type definition (introduces engine-wide cross-cutting i18n type)
  - `02_extension_contracts.md` §1.4 (RejectReason rule_id namespace): added `resource.*` row with 12 V1 rule_ids enumerated + 3 V1+ reservations + i18n update note
  - `02_extension_contracts.md` §2 (RealityManifest): added 9 RES_001 OPTIONAL V1 extension fields with inline doc comments + engine defaults
- **Files created within `features/00_resource/`:**
  - `_index.md` — folder index with status DRAFT 2026-04-26 + Q1-Q12 LOCKED summary + reference-games-survey link + i18n notice
  - `00_CONCEPT_NOTES.md` — concept brainstorm + 5-axiom user definition + 10-dimension gap analysis (A-J) + 5-feature boundary intersection table + Q1-Q7 original recommendations + 12-step promotion checklist + §10 Q1-Q5 LOCKED decisions matrix + §10.5 17-item downstream impacts + §10.6 Q6-Q12 status
  - `01_REFERENCE_GAMES_SURVEY.md` — 10 reference games (CK3 / M&B Bannerlord / Anno 1800 / Civ VI / Stellaris / DF / RimWorld / Vic3 / EU4 / Patrician) with per-game LoreWeave applicability mapping; 12 recurring patterns synthesized (P1-P12); V1 / V1+30d / V2 / V3 phase mapping; revised Q1-Q7 + new Q8-Q12; V1 scope summary post-survey
  - `RES_001_resource_foundation.md` — DRAFT (this promotion) — 18 sections covering: §1 Purpose / §2 i18n contract NEW / §3 ResourceKind ontology / §4 Aggregates split (vital_pool + resource_inventory) / §5 Ownership semantics / §6 Production model / §7 Consumption model / §8 Transfer/trade model / §9 RealityManifest extensions / §10 Generator bindings / §11 Validator chain / §12 Cascade integration / §13 RejectReason rule_id catalog / §14 10 V1 acceptance scenarios AC-RES-1..10 / §15 27 deferrals (RES-D1..27 across V1+30d/V2/V3) / §16 6 open questions / §17 Coordination + downstream / §18 Status
- **Files created within `catalog/`:**
  - `cat_00_RES_resource.md` — feature catalog with stable-ID namespace `RES-*` (RES_001..N + RES-A* axioms + RES-D* deferrals + RES-Q* open questions)
- **Q1-Q12 deep-dive decisions LOCKED (full matrix in `00_CONCEPT_NOTES.md` §10):**
  - **Q1**: 5 V1 categories (Vital / Consumable / Currency / Material / **SocialCurrency** — added for wuxia/xianxia danh tiếng); ResourceBalance shape locks `instance_id: Option<ItemInstanceId>` from V1 (None V1, Some V1+30d Item kind — zero migration); Property NOT in ResourceKind (handled by EF_001 entity_binding)
  - **Q2**: Open economy + 3 V1 sinks (food consumption + cell maintenance cost + trade buy/sell spread); cell_maintenance_profiles RealityManifest extension; cell with owner=None → production halts
  - **Q3**: **Split 2 aggregates** (was unified) — vital_pool (body-bound, type-system-enforced non-transferable) + resource_inventory (portable, EntityRef-any). VitalKind V1 = Hp + Stamina (Mana V1+ reserved); VitalProfile shape RES_001-owned, per-actor-class declared via PCS_001/NPC_001 + RealityManifest vital_profiles
  - **Q4**: Hybrid production: cell auto-produces + NPC owner auto-collects (Generator daily) + PC owner manual-harvests (PL_005 Use kind harvest sub-intent) + no-owner halts. Day-boundary tick model (no float arithmetic V1). 3 V1 production-side Generators registered as EVT-T5 sub-types
  - **Q5**: Soft hunger PC+NPC symmetric. Reuse PL_006 Hungry (reserved → V1 active downstream impact). Magnitude scaling 1=mild / 4=severe / 7+=mortality trigger via WA_006 Starvation cause_kind. Day-boundary HungerTick Generator. Narrative-only effect V1, NO hydration V1, universal 1 food/day rate V1
  - **Q6**: NO PC inventory cap enforcement V1; SCHEMA RESERVED on EF_001 entity_binding (`inventory_cap: Option<CapacityProfile>`) — None V1 → Some V1+30d slot cap (zero migration)
  - **Q7**: NO quality/grade variation V1 (V2 with crafting module)
  - **Q8** (resolved by Q3+Q4): Both per-character + per-cell ownership tier (resource_inventory.owner = EntityRef any)
  - **Q9**: Author-declared cell ownership V1 + Forge transfer (WA_003) + **body-substitution inheritance via xuyên không (PCS_001 mechanic — Q9c LOCKED)** + NPC death → orphan. PC-to-PC trade + PC-buy-from-NPC V1+30d
  - **Q10**: Author-configurable currencies in RealityManifest (default single Copper); multi-tier display via I18nBundle formatter; storage = total smallest unit V1; per-denomination tracking V1+30d
  - **Q11** (resolved by Q4d): Production rate canonical in RealityManifest (fixed V1; modifier chain V1+30d)
  - **Q12**: Global pricing V1 with **buy/sell spread** (sink #3 — was missing in original recommendation) + **NPC finite liquidity** validator-enforced (was implicit assumption — now explicit via RES-V3); per-cell variance V1+30d
- **i18n NEW cross-cutting pattern:**
  - User direction 2026-04-26: "game của chúng ta là game quốc tế, lấy tiếng anh làm chuẩn"
  - English `snake_case` for all stable IDs (rule_ids, aggregate_type, sub-types, enum variants) — RES_001 introduces engine standard
  - `I18nBundle { default: String, translations: HashMap<LangCode, String> }` for user-facing strings — English `default` required, per-locale translations optional
  - RES_001 conformance: CurrencyDecl.display_name + ResourceKindDecl.display_name + RejectReason.user_message (envelope extension)
  - Existing features (PL_006 / NPC_001 / NPC_002 / PL_002 / WA_*) currently use Vietnamese hardcoded reject copy — **i18n cross-cutting audit DEFERRED** (low priority cosmetic, doesn't block V1 functionality; tracked in RES_001 §17.2)
- **Foundation tier completion: 5/5 V1 foundation features now have DRAFT or higher status:**
  - EF_001 Entity Foundation (CANDIDATE-LOCK) — WHO
  - PF_001 Place Foundation (CANDIDATE-LOCK) — WHERE-semantic
  - MAP_001 Map Foundation (CANDIDATE-LOCK) — WHERE-graph
  - CSC_001 Cell Scene Composition (DRAFT) — WHAT-inside-cell
  - **RES_001 Resource Foundation (DRAFT 2026-04-26)** — WHAT-flows-through-entity
- **17 downstream impact items deferred to follow-up commits** (per RES_001 §17.2):
  - HIGH priority: PL_006 Hungry promotion / WA_006 Starvation cause_kind / PL_005 trade+harvest rule_ids / EF_001 cell_owner+inventory_cap fields / PCS_001 brief body-substitution + RES_001 reading / 07_event_model 4 EVT-T5 sub-types
  - MEDIUM priority: NPC_001 auto-collect doc / WA_003 4 ForgeEditAction sub-shapes / PL_001 user_message envelope field
  - LOW priority: PF_001 cell-as-economic-entity cross-ref / i18n cross-cutting audit
- **Drift watchpoints: 8 active** (no change from PL folder closure). RES_001 doesn't introduce new watchpoints — Q1-Q12 fully resolved before DRAFT promotion (CONCEPT phase discipline worked).
- **Lock RELEASED** at end of this commit (`[boundaries-lock-claim+release]` single-cycle)
- **Reason / handoff:** RES_001 DRAFT closes V1 foundation tier (5/5). i18n NEW pattern propagates engine-wide as future features ship. Next priorities: (a) PCS_001 PC Substrate (parallel agent commission already seeded — body-substitution mechanic now blocked on RES_001 LOCK reading), (b) PO_001 PC Creation flow (V1-blocking, depends on PCS_001), (c) downstream Phase 2 commits applying RES_001 §17.2 to PL_006 / WA_006 / PL_005 / EF_001 / 07_event_model.

---

## 2026-04-26 — PL folder closure (commit 8/8): PL_006 closure pass → CANDIDATE-LOCK + final lock release

- **Lock claim:** main session 2026-04-26 (PL folder closure 8-commit cycle); this commit `[boundaries-lock-release]` (FINAL release after 8-commit chain)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 2026-04-26 → None; release timestamp + summary added
  - `01_feature_ownership_matrix.md` `actor_status` row: PL_006 status DRAFT → **CANDIDATE-LOCK 2026-04-26 PL folder closure** + ActorId EF_001 §5.1 source note + status.target_dead → entity.lifecycle_dead allocation note + PCS_001 read-side projection note
- **PL_006 status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` PL_006 row updated:** status CANDIDATE-LOCK + ActorId EF_001 + Stage 3.5.a entity.lifecycle_dead allocation + status.* V1 enumeration (3 rules) + PCS_001 read-side projection note
- **`_index.md` Active note updated:** PL folder closure COMPLETE 2026-04-26
- **PL folder closure milestone summary:**
  - 4 files at CANDIDATE-LOCK: PL_005 + PL_005b + PL_005c (commits 1-6) + PL_006 (commits 7-8)
  - PF-Q4 + MAP-Q3 drift watchpoints RESOLVED via PL_005 ExamineTarget extension (commit 1)
  - `interaction.*` namespace expanded to 5 V1 rules (commit 1) + sub-namespace canonical mapping (commit 3)
  - `status.*` namespace expanded to 3 V1 rules (commit 7)
  - Stage 3.5 group fully integrated across all 4 files (commits 1, 3, 5, 7)
  - actor_status post-commit migration note added in PL_005c §1.1 (commit 5)
  - PCS_001 brief §S5 read-side projection pattern documented in PL_006 §11 + §17 (commit 7)
  - 27 total deferrals across PL_005 (INT-D1..D11) + PL_005b (INT-CON-D1..D10) + PL_005c (INT-INT-D1..D8) + PL_006 (STA-D1..D8) — 35 deferrals total counting PL_006
  - 22 acceptance scenarios for PL_005 family (6 root + 16 contracts) + 7 PL_006 = 29 total acceptance scenarios
- **Drift watchpoints: 8 active** (after Phase 3 cleanup commits 1-8). Remaining: GR-D8 / CST-D1 / LX-D5 (locked at Stage 4) / HER-D8 / HER-D9 / CHR-D9 / WA_006 over-extension / B2 RealityManifest envelope / EF-Q2.
- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Reason / handoff:** PL folder is the second domain folder to fully close (after foundation tier 4/4 milestone). All 4 files at CANDIDATE-LOCK with consistent boundary integration, namespace enumeration, and Stage 3.5 alignment. Next domain folders for closure: NPC folder (NPC_001/002 already at CANDIDATE-LOCK; NPC_003 mortality V1+ deferred to PL_006 §16 STA-D timeline); WA folder (WA_001..006 various states); foundation tier complete (4/4); 05_llm_safety folder design pending; PCS_001 spawn pending.

---

## 2026-04-26 — PL folder closure (commit 7/8): PL_006 Phase 3 cleanup + status.* namespace V1 enumeration

- **Lock continues** from commit 1
- **Files modified within `_boundaries/`:**
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `status.*` row expanded prefix-only → 3 V1 rule_ids — unknown_flag / dispel_not_present / invalid_magnitude (+3 V1+ reservations: flag_forbidden_in_reality / scheduled_expire_collision / stack_policy_violation). Note added: `status.target_dead` is allocated to `entity.lifecycle_dead` per Stage 3.5.a entity_affordance namespace, NOT `status.*` — same pattern as `interaction.*` namespace allocation.
- **PL_006 Phase 3 findings applied:**
  - S1.1 §2 Domain concepts + §3.1 ActorStatus struct + §11 sequence — ActorId cross-ref to EF_001 §5.1 (single source of truth)
  - S1.2 §11 Apply Drunk sequence dual OutputDecl resolved — legacy pc_stats_v1_stub.StatusFlagDelta path RETIRED V1 in favor of actor_status canonical; PCS_001 brief §S5 read-side projection note (still references PL_006 enum but resolves via actor_status query; writes target actor_status directly)
  - S2.1 §9 Failure UX — Stage column added; per-reject Stage allocation; `status.target_dead` re-allocated to canonical `entity.lifecycle_dead` (Stage 3.5.a EF_001 owner) avoiding duplicate rule between PL_006 and EF_001
  - S2.2 §17 Cross-refs reorganized into 4 categorized blocks (foundation tier / play-loop substrate / event model + boundaries / NPC + PCS consumers / world-authoring + spikes); foundation tier EF_001 (ActorId + Stage 3.5.a) + PF_001 (V1+ place co-location) added
  - S3.1 §15 Status transition criteria split DRAFT→CANDIDATE-LOCK vs CANDIDATE-LOCK→LOCK
  - S3.2 §9 status.* V1 enumeration (3 rules + 3 V1+ reservations) added; boundary file synchronized in same commit
- AC-STA-6 acceptance scenario rule_id alignment: `status.target_dead` → canonical `entity.lifecycle_dead` (Stage 3.5.a)
- **Drift watchpoints unchanged** (no new resolutions in this commit)
- **Lock continues:** released at commit 8 with `[boundaries-lock-release]` prefix

---

## 2026-04-26 — PL folder closure (commit 6/8): PL_005c closure pass → CANDIDATE-LOCK

- **Lock continues** from commit 1
- **Files modified within `_boundaries/`:** none (PL_005c closure pass is metadata-only — file status header bump + `_index.md` row update; no aggregate or namespace boundary changes since PL_005c is integration layer, no new owned items)
- **PL_005c status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` PL_005c row updated:** status CANDIDATE-LOCK + Stage 3.5 group + §1.2 timing + §3.1 pre-condition + §6.1 stage allocation + actor_status post-commit + 27 total deferrals across PL_005/b/c
- **Reason:** PL_005c integration documentation aligned with Stage 3.5 boundary (already locked); Strike race eliminated via §3.1 pre-condition; per-stage namespace allocation in §6.1 failure scenarios. Combined PL_005 + PL_005b + PL_005c form complete Interaction feature (root + contracts + integration) all at CANDIDATE-LOCK.

---

## 2026-04-26 — PL folder closure (commit 5/8): PL_005c Phase 3 cleanup (Stage 3.5 group inserted in §1.1 common chain + §1.2 timing refresh + §3.1 Strike pre-condition + §6.1 stage allocation)

- **Lock continues** from commit 1
- **Files modified within `_boundaries/`:** none (PL_005c Phase 3 is internal documentation alignment with already-locked Stage 3.5 boundary; no new aggregate or namespace registration)
- **PL_005c Phase 3 findings applied:**
  - S1.1 §1.1 common chain — Stage 3.5 group with 4 sub-stages (entity_affordance EF_001 · place_structural PF_001 · map_layout MAP_001 · cell_scene CSC_001) inserted between Stage 3 A6 sanitize and Stage 4 lex_check; per-kind applicability rules per Stage 3.5 sub-stage; canonical reject namespaces noted (entity.lifecycle_dead, place.connection_target_unknown, map.missing_layout_decl, csc.actor_on_non_walkable, lex.ability_forbidden, interaction.* PL_005-owned at Stage 7)
  - S1.2 §1.2 timing summary — target-dead/target-absent rejects MOVED from Stage 7 (world-rule physics) to Stage 3.5.a (entity_affordance); per-kind "most-likely-reject" column updated for all 5 kinds
  - S2.1 §3.1 Strike Lethal pre-condition — Stage 3.5.a target Existing (Alive) gates BEFORE Stage 7 physics derivation; eliminates Stage 7 race re-deriving MortalityTransition for already-Dying targets
  - S2.2 §6.1 failure scenarios — "Validator stage 0-9 fail" reworded "Validator stage 0-3.5-9 fail" with per-stage namespace allocation (3.5.a→entity.* / 3.5.b→place.* / 3.5.c→map.* / 3.5.d→csc.* / 4→lex.* / 7 PL_005→interaction.*)
  - S2.3 §10 cross-refs reorganized into 4 categorized blocks (foundation tier / play-loop substrate / NPC+world-authoring / event model + boundaries) — added EF/PF/MAP/CSC/PL_006/Stage 3.5 boundary
- §1.1 also added: post-commit side-effects entry for actor_status (PL_006) — Use:wine outcome migrates from legacy pc_stats_v1_stub.status_flags to actor_status aggregate

---

## 2026-04-26 — PL folder closure (commit 4/8): PL_005b closure pass → CANDIDATE-LOCK

- **Lock continues** from commit 1
- **Files modified within `_boundaries/`:** none (PL_005b closure pass is metadata-only — file status header bump + `_index.md` row update; no aggregate or namespace boundary changes since PL_005b inherits all PL_005-owned envelopes/namespaces)
- **PL_005b status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` PL_005b row updated:** status CANDIDATE-LOCK + §8 Stage 0-9 pipeline + §8.1 sub-stage applicability + §8.2 lex severity + §8.3 world-rule actions + §9.0 namespace allocation + 10 deferrals (was 8)
- **Reason:** PL_005b contracts complete + Stage 3.5 sub-stage allocation in §8 + namespace canonicalization in §9.0 + ExamineTarget extension consumed in §5.3. Ready for AC-INT-SPK/STK/GIV/EXM/USE-* integration tests.

---

## 2026-04-26 — PL folder closure (commit 3/8): PL_005b Phase 3 cleanup (Stage 3.5 sub-stage allocation + §8 pipeline expansion + §9.0 namespace allocation)

- **Lock continues** from commit 1
- **Files modified within `_boundaries/`:** none (PL_005b Phase 3 is internal — sub-namespace allocation note in §9.0 documents canonical mapping but does NOT add new V1 enumeration entries to `02_extension_contracts.md` §1.4 since the 5 V1 root rules already cover all Stage 7 PL_005-owned rejects; sub-namespaced IDs explicitly noted as PL_005b-internal UX hints, not boundary-registered)
- **PL_005b Phase 3 findings applied:**
  - S1.1 `InteractionPayloadBase` doc-comment notes — TargetRef::Place uses PlaceId(ChannelId) per PF_001 §3.1; ActorId from EF_001 §5.1
  - S1.2 §6.3 Use TargetRef table — V1 EnvObject targets (door-locks, wine-bottles, etc.) referenced via Item(GlossaryEntityId) per B2; no runtime EnvObject state aggregate V1
  - S2.1 §8 expanded to full Stage 0-9 pipeline including Stage 3.5 group; new §8.1 per-kind Stage 3.5 sub-stage applicability matrix; new §8.2 per-kind Stage 4 lex severity; new §8.3 per-kind Stage 7 world-rule actions
  - S2.2 §9.0 namespace allocation note added — sub-namespaced rule_ids (`interaction.{kind}.{specific}`) map to canonical namespaces at validator runtime (entity.* / place.* / map.* / csc.* / lex.* / interaction.* / schema-level); PL_005b-internal UX pattern, not boundary-registered
  - S2.3 §5.3 Examine TargetRef table extended with ExamineTarget enum reference (PL_005 §2 — Place via PlaceId V1 + MapNode V1+ author-content-gated)
  - S3.1 New deferrals INT-CON-D9 (ProposedOutputs vs ActualOutputs per-EVT-T category serialization rules) + INT-CON-D10 (sub-namespace pattern formal registry vs retire)
  - Acceptance scenario rule_id alignment: AC-INT-STK-2 + AC-INT-GIV-2 + AC-INT-GIV-3 updated to show canonical Stage 3.5.a / Stage 0 allocation

---

## 2026-04-26 — PL folder closure (commit 2/8): PL_005 closure pass → CANDIDATE-LOCK

- **Lock continues** from commit 1 (still claimed by main session 2026-04-26)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md` EVT-T1 Submitted sub-types row: PL_005 status DRAFT → **CANDIDATE-LOCK 2026-04-26 PL folder closure**; ExamineTarget enum noted (resolves PF-Q4 + MAP-Q3); Stage 3.5 group integration noted; 11 deferrals INT-D1..D11
- **PL_005 status header DRAFT → CANDIDATE-LOCK 2026-04-26** (Phase 3 cleanup + closure pass complete in commit 1+2 chain)
- **`_index.md` PL_005 row updated:** status CANDIDATE-LOCK + ExamineTarget extension note + 11 deferrals + 5 V1 interaction.* rules
- **Reason:** PL_005 design complete + boundary registered + foundation tier integrated (Stage 3.5 + ExamineTarget) + V1 namespace enumerated. Ready for AC-INT-1..6 integration tests against SPIKE_01 fixtures (CANDIDATE-LOCK → LOCK gate).

---

## 2026-04-26 — PL folder closure (commit 1/8): PL_005 Phase 3 cleanup + PF-Q4 + MAP-Q3 watchpoints RESOLVED + interaction.* namespace V1 enumeration

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — PL folder closure per user direction "Option A"); this commit `[boundaries-lock-claim]` (claim only — release at end of commit 8)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md` Drift Watchpoints table: 2 watchpoints struck-through with RESOLVED markers
    - **PF-Q4** ~~Place addressability ExamineTarget discriminator~~ → RESOLVED via PL_005 §2 ExamineTarget enum + §14.1 Examine Place sequence; V1+ collapse to `EntityId::Place` deferred per INT-D10
    - **MAP-Q3** ~~Examine non-cell-tier map node~~ → RESOLVED via PL_005 §2 ExamineTarget::MapNode(ChannelId, ChannelTier) variant + §14.2 Examine MapNode sequence; V1+ author-content-gated activation per INT-D11
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `interaction.*` row expanded prefix-only → 5 V1 rule_ids — target_unreachable / tool_unavailable / tool_invalid / target_invalid / intent_unsupported (+1 V1+ reservation cross_cell_disallowed). Note added: `target_dead` is allocated to `entity.lifecycle_dead` per Stage 3.5.a entity_affordance namespace, NOT `interaction.*` — avoids duplicate rule between PL_005 and EF_001.
- **PL_005 Phase 3 cleanup (in same commit):** S1.1 PlaceId(ChannelId) newtype + S1.2 ActorId source-of-truth EF_001 §5.1 + S2.1 Stage 3.5 group integration in §10 sequence + §9 reject paths split between PL_005-owned vs foundation-owned namespaces + S2.2 ExamineTarget enum (V1: Place; V1+: MapNode) + S2.3 CSC_001 Layer 4 cross-ref in §11 + S2.4 foundation tier cross-refs in §18 + S3.1 §16 LOCK criterion split + S3.2 boundary `interaction.*` enumeration. New deferrals INT-D10 + INT-D11.
- **Drift watchpoints: 10 → 8 active** (2 RESOLVED in this commit). Remaining 8 watchpoints: GR-D8 / CST-D1 / LX-D5 (already locked at Stage 4) / HER-D8 / HER-D9 / CHR-D9 / WA_006 over-extension / B2 RealityManifest envelope / EF-Q2.
- **Lock continues:** still claimed for commit 2 (PL_005 closure pass) → 3-7 (PL_005b/c + PL_006 cleanup + closures) → 8 (final release). 4 lock-claim+release cycles total per planned commit cadence.

---

## 2026-04-26 — EVT-V slot alignment review: 4 drift watchpoints resolved (EF-Q3 + PF-Q1 + MAP-Q1 + CSC-Q2)

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — EVT-V slot alignment review per user direction "E"); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `03_validator_pipeline_slots.md`:
    - **Inserted Stage 3.5 group** between existing Stage 3 (A6 sanitize) and Stage 4 (lex_check) — preserves locked LX-D5 numbering. 4 sub-stages: 3.5.a entity_affordance (EF_001) · 3.5.b place_structural (PF_001) · 3.5.c map_layout (MAP_001) · 3.5.d cell_scene (CSC_001). Order = "fail-fast common-case-first; specific checks last."
    - **New section "Stage 3.5 sub-stage applicability"** — per-sub-stage predicate table specifying when each runs vs early-exits (e.g., entity_affordance applies to EVT-T1 with entity targets; map_layout applies to Travel events; cell_scene applies to write events modifying cell state).
    - **New section "Soft-override mechanism"** — INTERNAL to entity_affordance validator (Stage 3.5.a); PL_005 InteractionKindSpec declares `tolerates_destroyed`/`tolerates_suspended` per kind; pipeline downstream sees pass/fail only.
    - **New section "Stage → rule_id namespace matrix"** — onboarding lookup table mapping each stage to its rule_id prefix + V1 namespace count + V1+ reservations. Total 44+ V1 rule_ids in entity/place/map/csc namespaces alone (Stage 3.5 group).
    - **Post-commit side-effects table:** added 2 new entries — PlaceDestroyed cascade (PF_001 §6.1) + EntityLifecycle HolderCascade (EF_001 §6.1).
    - **Drift Resolutions table:** 4 new RESOLVED entries (EF-Q3 / PF-Q1 / MAP-Q1 / CSC-Q2) with cross-ref to Stage 3.5 sub-stages.
    - **Status note** at top of file updated to reflect alignment review completion.
  - `01_feature_ownership_matrix.md` Drift Watchpoints table: 4 watchpoints struck-through with RESOLVED markers cross-referencing Stage 3.5.a/b/c/d in `03_validator_pipeline_slots.md`.
- **No `02_extension_contracts.md` changes** — no new namespaces or schemas; alignment review is pure ordering decision.
- **Reason:** 4 drift watchpoints (EF-Q3 + PF-Q1 + MAP-Q1 + CSC-Q2) all referenced `_boundaries/03_validator_pipeline_slots.md` alignment review for resolution. Foundation tier 4/4 CANDIDATE-LOCK milestone (commit 3e9d6bb) made all 4 ready for slot resolution. User direction "E" approved Q1-Q6 sub-decision defaults: ordering entity→place→map→cell (fail-fast); preserve existing stage numbering (LX-D5 still stage 4); per-sub-stage applicability rules; soft-override INTERNAL to entity_affordance; cascade-triggers POST-COMMIT; rule_id prefix matrix added.
- **Architectural pattern locked:** "structural validators run as Stage 3.5 group between A6 sanitize and lex_check" — cheaper than lex (lookup + invariant check vs axiom evaluation); fail-fast principle (reject malformed-world-state references before semantic Lex check). Each sub-stage has applicability predicate (early-exit when not relevant to event kind). Soft-override is a PER-RULE_ID property handled INTERNAL to validator; pipeline downstream sees pass/fail only.
- **Drift watchpoints: 14 → 10 active** (4 RESOLVED in this commit). Remaining 10 watchpoints unrelated to validator slot ordering (GR-D8 / CST-D1 / LX-D5 already locked / HER-D8 / HER-D9 / CHR-D9 / WA_006 over-extension already mitigated / B2 RealityManifest envelope / EF-Q2 / PF-Q4 / MAP-Q3 — wait counts may differ; see updated matrix).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — Foundation tier 4/4 milestone: MAP_001 + CSC_001 closure passes → CANDIDATE-LOCK

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — combined closure pass for MAP_001 + CSC_001 to complete foundation tier 4/4 CANDIDATE-LOCK milestone); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - `map_layout` row: status DRAFT → **CANDIDATE-LOCK 2026-04-26**; AC count updated 10 → 11
    - `cell_scene_layout` row: status DRAFT → **CANDIDATE-LOCK 2026-04-26**; AC count noted 11
    - `EVT-T4 LayoutBorn` (MAP_001) row: status note CANDIDATE-LOCK 2026-04-26
    - `EVT-T8 Forge:EditMapLayout` (MAP_001) row: status note CANDIDATE-LOCK 2026-04-26
    - `EVT-T4 SceneLayoutBorn` (CSC_001) row: status note CANDIDATE-LOCK 2026-04-26 + Phase 3 S2.6 ensure_cell_scene_layout RPC pattern noted
    - `EVT-T8 Forge:EditCellScene` (CSC_001) row: status note CANDIDATE-LOCK 2026-04-26
- **No `02_extension_contracts.md` changes** — namespaces stable post Phase 3 (map.* 13 V1; csc.* 9 V1; both unchanged at closure pass).
- **Files modified outside `_boundaries/`** (recorded for closure-pass auditability):
  - `features/00_map/MAP_001_map_foundation.md`:
    - Header status DRAFT → **CANDIDATE-LOCK 2026-04-26**
    - §15 acceptance criteria: AC-MAP-7 expanded (covers both `connection_distance_invalid` + new `connection_duration_invalid` rule_ids); AC-MAP-9 expanded (covers V1 asset None + new defensive `asset_pipeline_not_active_v1` rule); new **AC-MAP-11** added for `tier_field_mismatch` coverage (mirror PF entity_type_mismatch pattern). AC count 10 → 11.
    - §17 readiness checklist: closure-pass walk-through line added; CANDIDATE-LOCK box ticked
  - `features/00_map/_index.md`: Active cleared, folder closure status → **CLOSED for V1 design 2026-04-26**, MAP_001 row updated with full feature description reflecting Phase 3 + closure-pass state (13 V1 rule_ids, 11 ACs, 16 deferrals)
  - `features/00_cell_scene/CSC_001_cell_scene_composition.md`:
    - Header status DRAFT → **CANDIDATE-LOCK 2026-04-26**
    - §17 readiness checklist: closure-pass walk-through line added (0 rule_id mismatches at closure — Phase 3 cleanup proactively aligned ACs to new rule_ids); CANDIDATE-LOCK box ticked
    - **No AC tightening at closure** — Phase 3 cleanup already expanded AC-CSC-3 + AC-CSC-7 + added AC-CSC-11 with new rule_id coverage. Closure pass found no mismatches (cleaner trajectory than EF_001 closure which discovered 3; mirrors PF_001 closure which found 0).
  - `features/00_cell_scene/_index.md`: Active cleared, folder closure status → **CLOSED for V1 design 2026-04-26**, CSC_001 row updated with full feature description (9 V1 rule_ids, 11 ACs, 13 deferrals)
- **Reason:** Combined closure pass per user direction (C — both passes). MAP_001 closure walked AC-MAP-1..10 against §1.4 namespace (13 V1 post Phase 3); found 3 ACs needed expansion to cover Phase 3 added rule_ids (`connection_duration_invalid` from S1.2; `asset_pipeline_not_active_v1` from S1.3; `tier_field_mismatch` from S1.1 — covered via new AC-MAP-11). CSC_001 closure walked AC-CSC-1..11 against §1.4 namespace (9 V1 post Phase 3); found **0 rule_id mismatches** because Phase 3 cleanup proactively aligned ACs (AC-CSC-3 already covered `zone_empty_fallback_used`; AC-CSC-11 already covered `layer3_occupant_set_changed` V1+ reservation). MAP closure-pass mirrored EF_001 closure pattern (3 mismatches found); CSC closure-pass mirrored PF_001 closure pattern (0 mismatches; AC tightening only).
- **Foundation tier 4/4 CANDIDATE-LOCK milestone achieved:**

  | Foundation | Status | Aggregate | AC count | rule_ids V1 |
  |---|---|---|---|---|
  | EF_001 Entity Foundation | CANDIDATE-LOCK | entity_binding | 10 | 10 |
  | PF_001 Place Foundation | CANDIDATE-LOCK | place | 10 | 12 |
  | MAP_001 Map Foundation | **CANDIDATE-LOCK** | map_layout | 11 | 13 |
  | CSC_001 Cell Scene Composition | **CANDIDATE-LOCK** | cell_scene_layout | 11 | 9 |

  Coverage: WHO (EF) + WHERE-semantic (PF) + WHERE-visual-graph (MAP) + WHAT-inside-cell (CSC). 4 foundations compose cleanly without overlap. PCS_001 (when designed) builds on complete foundation tier; spawn flow per CSC_001 §15.1 ensure_cell_scene_layout pattern.

- **Total at CANDIDATE-LOCK after this commit cycle:** 17 features (15 prior + MAP + CSC promotions). Foundation tier 4/4 closed; domain folders prior closed (WA: 5 / NPC: 2 / PLT: 3); PL folder open (PL_005 series + PL_006 DRAFT).
- **Drift watchpoints:** 14 active (unchanged; closure-pass found no new drift).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — CSC_001 Phase 3 review cleanup (Severity 1+2+3) + lazy-cell fix S2.5 + 1 new V1 rule_id

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — CSC_001 Phase 3 cleanup post DRAFT commit 23b03d9); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `csc.*` rule-id list expanded 8 V1 → **9 V1**. Added 2026-04-26 Phase 3:
    - `csc.zone_empty_fallback_used` (Phase 3 S2.1 — engine-internal log signal when canonical fallback chain triggers because primary hint zone is empty)
  - V1+ reservation also added: `csc.layer3_occupant_set_changed` (Phase 3 S2.2 — V1 logged-only race-detection signal; V1+ may promote to user-facing reject)
  - No `01_feature_ownership_matrix.md` changes (rule_ids documented in extension contracts only; aggregate ownership unchanged).
- **Files modified outside `_boundaries/`** (recorded for cleanup auditability):
  - `features/00_cell_scene/CSC_001_cell_scene_composition.md`:
    - **§3.1 (S1.1 / S1.5 / S2.7 / S2.8):** zone_catalog typed (was untyped `serde_json::Value`; now `HashMap<String, Vec<TileCoord>>`); procedural_seed JSON serialization documented as string (JS precision); ProceduralParams V1 defaults documented (`{ table_count: 4, density: 0.6, fireplace_side: East }` with `Default` impl); prompt_template_version field added for cache invalidation.
    - **§4.3 (S1.3 / S3.4):** explicit blake3 hash for skeleton selection (was `hash_u64`); V1+ PlaceType extension fallback semantics documented.
    - **§5.1 + §5.2 (S1.2 / S1.4):** Rust idiomatic clamp (`value.clamp(min, max)`); explicit `ChaCha8Rng::seed_from_u64` import for replay-determinism (was undefined `SeededRng`).
    - **§6.4 (S2.2):** PC race condition policy — capture occupant_snapshot_hash at LLM call start; verify unchanged at write commit; abort + log `csc.layer3_occupant_set_changed` if changed; canonical fallback already in place from §15.1 lazy-create.
    - **§6.5 (S2.1):** empty-zone fallback chain via `fallback_chain_for(entity_id, kind)` per-entity priority list (e.g., counter:on → table_1:on → center_floor:open). New rule_id `csc.zone_empty_fallback_used` for ops observability. `center_floor:open` is universal last-resort guarantee (Layer 2 invariant always populates ≥ 1 tile).
    - **§7.4 (S3.1 / S2.4 / S2.8):** explicit `cache_key_layer_4` algorithm with blake3 + canonical_json_bytes + occupant_set_hash via sorted-by-entity_id + prompt_template_version; Layer 4 cross-session replay-determinism documented as BEST-EFFORT V1 (in-memory LRU; persistent cache via CSC-D11 V1+).
    - **§8 (S2.4 / S2.8):** replay-determinism table updated — Layer 4 best-effort V1 caveat; prompt_template_version inclusion in both Layer 3 + Layer 4 cache keys.
    - **§12 (S3.2):** provider-registry JWT contract specified — `produce: ["LlmCall"]` + `llm_call_kind: "csc.layer3_zones" | "csc.layer4_narration"` + V1+ `llm_call_budget` (CSC-D3 dependency).
    - **§14 (S1.5):** cross-service handoff JSON example — procedural_seed as STRING with explicit note about JS Number.MAX_SAFE_INTEGER precision constraint.
    - **§15.1 (S2.6):** sequence ordering fix — `ensure_cell_scene_layout(cell_id)` RPC fires during PL_001 §13 step ⑤ (BEFORE MemberJoined), guaranteeing layout exists by subscribe time. Eliminates subscribe-trigger ambiguity.
    - **§16 (S3.5):** AC tightening — AC-CSC-3 expanded with 3 variants (normal / counter-too-small / extreme-degenerate); AC-CSC-7 expanded with 4 sub-tests (cache hit / occupant invalidation / prompt_version invalidation / LRU eviction); AC-CSC-10 clarified per S2.3; **new AC-CSC-11** for PC race condition coverage.
    - **§10.2 (S3.3 / S2.3):** RejectReason table reframed — "Soft-override eligible" column → "Visibility" column (engine-internal vs write-time-validator categories); placetype_no_skeleton_v1 explicitly clarified as defensive ceiling (V1 should never fire). Added `csc.zone_empty_fallback_used` row.
    - **§17 readiness checklist:** Phase 3 cleanup line ticked with full summary; rule_id count updated 8 → 9 V1; AC count updated 10 → 11.
  - `features/04_play_loop/PL_001b_continuum_lifecycle.md` §16.3 lazy cell creation: **CRITICAL FIX (Phase 3 S2.5)** — added `ensure_cell_scene_layout(...)` callee + write cell_scene_layout row + emit EVT-T4 SceneLayoutBorn alongside the existing place_row + map_layout_row creations. Same pattern as MAP_001 Phase 3 S2.6 fix. Prior to this commit, lazy-cells via PC `/travel` to undeclared cells would create channel + place + map_layout but NOT cell_scene_layout → next frontend cell scene render → invariant violation.
- **Reason:** CSC_001 Phase 3 adversarial review (mirror EF/PF/MAP cleanup pattern post-DRAFT) caught 13 defects across 3 severity tiers. User approved Option A (apply all). Severity 1 = Rust correctness + structural defects (5 fixes); Severity 2 = design gaps (8 fixes incl. real lazy-cell map_layout creation bug); Severity 3 = clarifications + cross-feature consistency (5 fixes consolidated within other groupings).
- **Most architecturally significant:** S2.1 (empty-zone fallback chain — closes correctness hole in canonical default; AC-CSC-3 invariant now provable in degenerate cases) + S2.5 (lazy-cell `cell_scene_layout` creation — real runtime bug, mirrors MAP_001 Phase 3 S2.6) + S2.6 (subscribe-trigger ambiguity → eager-create-on-PC-entry pattern).
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_cell_scene slot still tracked as CSC-Q2 watchpoint (joins EF-Q3 + PF-Q1 + MAP-Q1 in single alignment review).
- **Drift watchpoints unchanged** (14 active; Phase 3 cleanup resolves under-specified items inline rather than adding watchpoints).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — CSC_001 Cell Scene Composition feature registered (4-layer architecture; closes V1 foundation tier)

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — CSC_001 Cell Scene Composition DRAFT, 4-layer architecture validated by v3→v4 demo pivot evidence per user direction "design now"); commit (this turn) `[boundaries-lock-claim+release]`
- **New folder + catalog created** (outside `_boundaries/`):
  - `features/00_cell_scene/_index.md` (foundation tier folder index — sibling of `00_entity/` + `00_place/` + `00_map/`)
  - `features/00_cell_scene/CSC_001_cell_scene_composition.md` (790 lines under 800 cap; 20 sections including 4-layer architecture in §4-§7)
  - `catalog/cat_00_CSC_cell_scene_composition.md` (CSC-1..CSC-25 catalog entries; owns `CSC-*` namespace; CSC-A1 architectural axiom recorded)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - **New aggregate:** `cell_scene_layout` (T2 / Channel-cell scope; cell-tier only V1). Owned by **CSC_001 Cell Scene Composition** (DRAFT 2026-04-26). Owns 4-layer composition pipeline (skeleton + procedural + LLM zones + LLM narration); each layer's failure mode bounded with canonical fallback; cell scene always renders V1.
    - **Schema/envelope ownership new rows (2):**
      - EVT-T4 System sub-type `SceneLayoutBorn` owned by CSC_001 (emitted at first cell entry / RealityManifest bootstrap; one per cell-tier channel)
      - EVT-T8 Administrative sub-shape `Forge:EditCellScene` owned by CSC_001 (5 edit kinds V1: ChangeSkeleton/RerollSeed/ForceLayer3Refresh/ForceLayer4Refresh/ResetToCanonicalDefaults)
    - **RealityManifest ownership row updated:** CSC_001 added as OPTIONAL V1 contributor (`scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>`)
    - **RejectReason namespace prefix table:** added `csc.*` → CSC_001
    - **Stable-ID prefix ownership:** new row for `CSC-*` (foundation tier; CSC-A* axioms / CSC-D* deferrals / CSC-Q* open questions)
    - **Drift watchpoints:** added **CSC-Q2** (validator slot ordering — extends EF-Q3 + PF-Q1 + MAP-Q1; single alignment review pass for all 4 watchpoints)
  - `02_extension_contracts.md`:
    - §2 RealityManifest current shape: added `scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>` OPTIONAL V1 field with note (per-cell author override; engine fallback when absent; unknown SkeletonId logs `csc.skeleton_not_found`)
    - §1.4 RejectReason namespace prefix table: added `csc.*` owned by CSC_001 with 8 V1 rule_ids enumerated (skeleton_not_found / invalid_zone_assignment / zone_overlap / actor_on_non_walkable / item_on_non_placeable / entity_missing_from_assignment / layer3_retry_exhausted / placetype_no_skeleton_v1) + 3 V1+ reservations (skeleton_invalid / procedural_density_too_high / narration_unsafe_content)
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_cell_scene slot tracked as CSC-Q2 watchpoint (joins EF-Q3 + PF-Q1 + MAP-Q1 in single alignment review).
- **Reason:** v3→v4 demo pivot at `_ui_drafts/CELL_SCENE_v1..v4` (committed 0e4a230) validated 4-layer architecture: v3 LLM-as-grid-generator approach failed (Qwen 3.6 35B-A3B: 30,000 reasoning tokens, hit 4K limit, 0 successful outputs); v4 LLM-as-zone-classifier succeeded (2,471 total tokens including reasoning, all 6 entities placed correctly, validators passed attempt 1). **12.7× cost reduction** with higher reliability. Architectural axiom CSC-A1 captures lesson: LLM tasks confined to categorical (Layer 3) + creative (Layer 4); spatial coordinate manipulation handled by deterministic engine code (Layer 1+2). 17 sub-decisions locked at Phase 0 CLARIFY before draft (folder placement / single feature with 4 internal layers / cell_scene_layout aggregate / V1 only Tavern + default_generic_room fallback / V1 fixtures only / named zone catalog / LLM JSON contract with retry / free-form narration / lazy-cached / blake3 seed determinism / 4 layer failure mode chains / RealityManifest scene_skeleton_overrides / 8 csc.* rule_ids).
- **Closes V1 foundation tier completeness:** 4 foundation features now in flight (EF + PF + MAP + CSC) covering WHO + WHERE-semantic + WHERE-visual + WHAT-inside-cell. PCS_001 (when designed) builds on this complete foundation; spawn flow per CSC_001 §15.1 lazy first-entry sequence.
- **Total at CANDIDATE-LOCK after this commit cycle remains:** 15 features (EF + PF + 13 prior). CSC_001 enters DRAFT; future Phase 3 review + closure pass → CANDIDATE-LOCK promotion would bring foundation tier to 4/4 closed.
- **Drift watchpoints:** 13 → 14 active (CSC-Q2 added).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — MAP_001 Phase 3 review cleanup (Severity 1 + 2 + 3) + 3 new V1 rule_ids + lazy-cell map_layout fix

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — MAP_001 Phase 3 cleanup post DRAFT commit c7b75a6); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `map.*` rule-id list expanded 10 V1 → **13 V1**. Added 2026-04-26 Phase 3:
    - `map.tier_field_mismatch` (denormalized `tier` field doesn't match channel's actual tier in DP hierarchy; mirror of PF entity_type_mismatch Phase 3 fix; S1.1)
    - `map.connection_duration_invalid` (default_fiction_duration.value == 0 = teleport-without-intent prevention; S1.2)
    - `map.asset_pipeline_not_active_v1` (V1 defensive write-time reject for non-None ImageAssetRef; rule retired when MAP_002 V1+30d lands; S1.3)
  - No matrix changes (rule_ids documented in extension contracts only; aggregate ownership unchanged).
- **Files modified outside `_boundaries/`** (recorded for cleanup auditability):
  - `features/00_map/MAP_001_map_foundation.md`:
    - **§3.1 (S1.1 / S1.2 / S1.3 / S2.1):** ChannelTier denorm validation rule explicit (mirror PF entity_type Phase 3 fix); duration > 0 invariant; V1 author-write of non-None asset_ref defensive reject. Cell-tier composition note added (forward ref to §12.1).
    - **§2 (S2.4):** FictionDuration cross-ref to PL_001 §3.1 + invariant note.
    - **§4 (S3.4):** Hidden ConnectionKind V1 limitation note — functionally Public V1; visual styling differentiator only; V1+ MAP-D10 activates per-PC discovery.
    - **§5 (S3.1 / S2.3):** Reality root viewport explicit definition (no parent; top-level UI canvas 0..=1000 × 0..=1000). New "Lazy-cell auto-position policy V1" subsection with deterministic golden-angle spiral (replay-safe per EVT-A9; NOT random; clamped 50..950 with margin).
    - **§7.1 (S3.3):** New "Default icon emoji map V1" subsection formalizing emoji per PlaceType (10 cells: 🏠 🍵 🏪 ⛩️ 🛠️ 🏛️ 🛤️ 🔀 🌲 🕳️) + per non-cell ChannelTier (4: 🌍 🏯 🗺️ 🏘️) + 4 StructuralState visual treatments (Pristine / Damaged / Destroyed / Restored). Validates demo `MAP_GUI_v1.html` mapping; spec is authoritative.
    - **§8 (S2.2):** New "Known V1 limitations" boxout — 7 V1 constraints (cell-to-cell flat duration / Hidden ≡ Public / Locked always rejects / no V1 pathfinding / no V1 fog-of-war / no V1 method matrix / asset slots None V1) each with V1+ unblock cross-ref. Authors warned not to work around limitations in V1.
    - **§9 (S1.1 / S1.2 / S1.3 / S3.2):** Added 3 new V1 rule_ids with full Vietnamese reject copy. Added note on `map.asset_review_pending` V1+ prefix (V1 never fires).
    - **§12.1 (S2.1):** New "Cell-tier composition flow" subsection — V1 dual-subscription pattern (Subscription A on map_layout for visual; Subscription B on PF_001 place for semantic + cell connections). Frontend composes both at client side. V1+ MAP-D16 unified `read_map_view(channel_id) → MapViewDTO` API at world-service for round-trip optimization.
    - **§14.3 (S2.5):** canon_ref None narrator fallback footnote (mirror PF_001 §6 step 11) — falls back to `(ChannelTier-default + ConnectionKind-default)` phrasing; LLM AssemblePrompt receives endpoint contexts for prose interpolation.
    - **§16 (S1.4 / S2.1):** Added 2 new deferrals — MAP-D15 (typed URI + closed-enum mime_type V1+30d MAP_002 implementation; security-relevant when MAP_002 populates) · MAP-D16 (unified read_map_view API V1+30d profiling).
    - **§18 readiness checklist:** Phase 3 cleanup line ticked with full summary; rule_id count updated 10 → 13 V1; deferral count 14 → 16; CANDIDATE-LOCK still pending closure pass.
  - `features/04_play_loop/PL_001b_continuum_lifecycle.md` §16.3 lazy cell creation: **CRITICAL FIX (S2.6)** — added `derive_lazy_map_layout(...)` callee + `write map_layout row` + `emit EVT-T4 LayoutBorn` alongside the existing place_row creation. Prior to this commit, lazy-cells via PC `/travel` to undeclared cells would create channel + place row but NOT map_layout row → AC-MAP-1 invariant violated at runtime → `map.missing_layout_decl` would fire on subsequent map UI open. Real runtime bug closed.
- **Reason:** MAP_001 Phase 3 adversarial review (mirror EF_001 + PF_001 cleanup pattern post-DRAFT) caught 13 defects across 3 severity tiers. User approved Option A (apply all). Severity 1 = Rust correctness + structural defects (4 fixes); Severity 2 = design gaps (6 fixes incl. real lazy-cell map_layout creation bug); Severity 3 = clarifications + cross-feature consistency (4 fixes).
- **Most architecturally significant:** S2.1 cell-tier composition (chose V1 dual-subscription frontend pattern over V1+ unified server-merge API; explicit MAP-D16 reservation) + S2.6 lazy-cell map_layout fix (real runtime bug closed before any consumer feature attempted lazy-cell flow).
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_map_layout slot still tracked as MAP-Q1 watchpoint (joins EF-Q3 + PF-Q1 in single alignment review).
- **Drift watchpoints unchanged** (13 active; Phase 3 cleanup resolves under-specified items inline).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — MAP_001 Map Foundation feature registered (sibling of EF_001 + PF_001; closes map UI + Travel cost gaps)

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — MAP_001 Map Foundation DRAFT, Option C max scope per user direction "design now"); commit (this turn) `[boundaries-lock-claim+release]`
- **New folder + catalog created** (outside `_boundaries/`):
  - `features/00_map/_index.md` (foundation tier folder index — sibling of `features/00_entity/` + `features/00_place/`)
  - `features/00_map/MAP_001_map_foundation.md` (586 lines under 800 cap; 19 sections)
  - `catalog/cat_00_MAP_map_foundation.md` (MAP-1..MAP-26 catalog entries; owns `MAP-*` namespace)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - **New aggregate:** `map_layout` (T2 / Channel scope; covers all tiers continent through cell). Owned by **MAP_001 Map Foundation** (DRAFT 2026-04-26). 5-variant ChannelTier closed enum + author-positioned absolute u32 (0..=1000) per-tier viewport + Option<TierMetadata> conditional + 5-variant MapConnectionKind matching PF_001 + distance_units + default_fiction_duration + 3 image asset slots V1 schema-only + 4-variant AssetSource + 3-variant AssetReviewState. Composes with PF_001 at cell tier.
    - **Schema/envelope ownership new rows (2):**
      - EVT-T4 System sub-type `LayoutBorn` owned by MAP_001 (emitted at canonical bootstrap; runs after PF_001 PlaceBorn at cell tier per PL_001 §16.2 step ordering)
      - EVT-T8 Administrative sub-shape `Forge:EditMapLayout` owned by MAP_001 (joins existing Charter*/Succession*/MortalityAdminKill/Forge:EditPlace registry)
    - **RealityManifest ownership row updated:** MAP_001 added as required-V1 contributor (`map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults`)
    - **RejectReason namespace prefix table:** added `map.*` → MAP_001
    - **Stable-ID prefix ownership:** new row for `MAP-*` (foundation tier)
    - **Drift watchpoints:** added **MAP-Q1** (validator slot ordering — extends EF-Q3 + PF-Q1) + **MAP-Q3** (Examine of non-cell-tier map node — extends PF-Q4 PL_005 ExamineTarget extension)
  - `02_extension_contracts.md`:
    - §2 RealityManifest current shape: added `map_layout: Vec<MapLayoutDecl>` + `travel_defaults: TravelDefaults` REQUIRED V1 fields with invariant note (every channel must have layout decl; cell-tier has tier_metadata=None + connections=[]; non-cell has full schema)
    - §1.4 RejectReason namespace prefix table: added `map.*` owned by MAP_001 with 10 V1 rule_ids enumerated (missing_layout_decl / duplicate_layout / position_out_of_bounds / connection_target_unknown / cross_tier_connection_disallowed / invalid_tier_metadata / asset_ref_unresolved / asset_review_pending / connection_distance_invalid / self_referential_connection) + 3 V1+ reservations (cross_reality_layout / layout_too_dense / connection_method_unsupported)
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_map_layout slot tracked as MAP-Q1 watchpoint (joins EF-Q3 + PF-Q1 in single alignment review).
- **Light PL_001b §16.2 reopen** (folded into this commit):
  - Reality activation flow: added step ①d writing map_layout rows from `manifest.map_layout` + EVT-T4 LayoutBorn emission per channel + cell-to-layout coverage validation; step ①e writing travel_defaults; step ①f (former step d) entity_binding now references both place + map_layout rows. Lazy-cell path (§16.3) must also create map_layout row alongside place row.
- **Reason:** user identified map UI as next gap after EF + PF foundation. Pattern: web game with node-link graph (Tiên Nghịch / EVE Online / Stellaris drill-down). User explicitly chose Option C (new sibling foundation feature; not extending PF_001) to avoid reopening just-locked PF_001. Demo at `_ui_drafts/MAP_GUI_v1.html` (commit before this) validated approach. Space-game pattern (distance + canonical Travel duration on each edge) approved Q11-a + Q12-a + Q14-a + Q15-b — removes ambiguity on PC's freely-proposed `fiction_duration_proposed`. Image asset architecture approved Q5-a + Q6-a — V1 schema reservations with V1+ MAP_002 phased pipeline (AuthorUploaded V1+30d, PlayerUploaded V1+60d, LlmGenerated V2+).
- **Closes V1 spawn-readiness gap** for the foundation tier: 3 foundation features now complete (EF_001 + PF_001 + MAP_001). PCS_001 (when designed) + future Item + future EnvObject + future TVL_001 + future MAP_002 all build on locked foundation.
- **Drift watchpoints:** 11 → 13 active (MAP-Q1 + MAP-Q3 added; MAP-Q4 inherited from PF §6 hint-only; MAP-Q5 internal to MAP_001).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PF_001 Place Foundation closure pass → CANDIDATE-LOCK

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — PF_001 closure pass after Phase 3 cleanup commit eec8d5b); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - `place` row: status DRAFT → **CANDIDATE-LOCK 2026-04-26**; notes updated to reflect Phase 3 + closure-pass refinements (bidirectional hint-only V1 / cascade-only-on-Destroyed / 4-step cascade ordering / fixture-seed author-declared-vs-materialized split / §15 AC precision-tightening on AC-PF-7/8/9/10)
    - `EVT-T4 PlaceBorn` sub-type row: status note CANDIDATE-LOCK 2026-04-26
    - `EVT-T8 Forge:EditPlace` sub-shape row: status note CANDIDATE-LOCK 2026-04-26 + AC-PF-8 atomicity-test reference
- **No `02_extension_contracts.md` changes** — `place.*` namespace already at 12 V1 + 4 V1+ from Phase 3; closure-pass had 0 rule_id mismatches (Phase 3 caught those proactively).
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_place_structural slot still tracked as PF-Q1 watchpoint.
- **Files modified outside `_boundaries/`** (recorded here for closure-pass auditability):
  - `features/00_place/PF_001_place_foundation.md`:
    - Header status DRAFT → **CANDIDATE-LOCK 2026-04-26**
    - §15 acceptance criteria: AC-PF-7 / AC-PF-8 / AC-PF-9 / AC-PF-10 precision-tightened with explicit references to Phase 3 contract changes (cascade 4-step ordering with PlaceDestroyed signal in step 2 / 3-write-transaction atomicity scope / PL_005 ExamineTarget cross-feature blocker explicit / seed_uid computed-not-declared model with 2-clone determinism test)
    - §18 readiness checklist: closure-pass walk-through line added; CANDIDATE-LOCK box ticked
  - `features/00_place/_index.md`: Active cleared, folder closure status → **CLOSED for V1 design 2026-04-26**, PF_001 row updated to CANDIDATE-LOCK with full feature description reflecting Phase 3 + closure-pass state
- **Reason:** §15 acceptance walk-through (per closure-pass discipline established for WA / NPC / PLT / EF folders) verified all 10 ACs against §9 V1 namespace. Unlike EF_001 closure pass (which discovered 3 missing rule_ids), Phase 3 cleanup proactively caught all rule_id additions — closure pass had ZERO rule_id mismatches. However, 4 ACs needed precision tightening because Phase 3 contract changes (cascade 4-step ordering / PlaceDestroyed signal / 3-write-transaction atomicity / computed-vs-declared seed_uid) hadn't propagated into AC text. Tightening done; closure pass complete.
- **Closure-pass coverage analysis** (recorded for future reference):
  - 10 ACs map to V1-testable scenarios; 4 needed Phase-3-induced tightening (AC-PF-7 / 8 / 9 / 10)
  - 6 V1 rule_ids not standalone-AC'd (`duplicate_place` / `unknown_place` / `connection_private` / `connection_hidden` / `no_reverse_connection` / `fixture_seed_uid_collision` / `self_referential_connection`) — covered implicitly via integration tests (same pattern as EF_001 closure pass; not every rule_id needs its own AC)
  - Cross-feature blockers explicitly tracked: AC-PF-9 cannot run V1 until PL_005 closure pass adds `ExamineTarget` extension (PF-Q4 watchpoint)
- **Closes V1 place foundation design.** Downstream impact:
  - **PCS_001** (when designed): brief `features/06_pc_systems/00_AGENT_BRIEF.md` will gain §4.4d mandatory PF_001 reading at next agent spawn (deferred to PCS_001 design start)
  - **PL_005 Interaction** (DRAFT): closure pass will fold in `ExamineTarget = Entity(EntityId) | Place(PlaceId)` discriminator (PF-Q4)
  - **PL_005c integration** (DRAFT): §V1-scope Strike Destructive cascade extends to call PF_001 cascade trigger
  - **NPC_001 Cast** (CANDIDATE-LOCK): `npc.current_region_id` cell-tier channel cross-references PlaceId 1:1 V1
  - **WA_003 Forge** (CANDIDATE-LOCK): `Forge:EditPlace` sub-shape now part of registry; Forge UI may extend in future
- **Drift watchpoints unchanged** (11 active; PF-Q1 + PF-Q4 still tracked).
- **Total at CANDIDATE-LOCK after this pass:** 15 features across 6 closed folders (EF: 1 · **PF: 1** · WA: 5 · PL: 3 · NPC: 2 · PLT: 3) — foundation tier (EF + PF) now complete + 4 domain folders.
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PF_001 Phase 3 review cleanup (Severity 1 + 2 + 3) + PlaceDestroyed sub-shape + CLOSED-ENUM-EXEMPT unification

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — PF_001 Phase 3 review cleanup, Severity 1+2+3 per user direction "A"); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md` EVT-T3 Derived sub-types row: extended to register **PF_001 PlaceDestroyed dedicated cascade-trigger sub-shape** (occupants list with deterministic sort; consumer features subscribe explicitly for cross-feature cascade contracts) alongside the standard `aggregate_type=place` delta sub-type. Pattern note added: cross-feature cascade-trigger sub-shapes reduce implicit coupling vs generic delta-filtering subscribe.
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `place.*` rule-id list expanded 11 V1 → **12 V1 + 4 V1+ reservations**. Added 2026-04-26 Phase 3: `place.self_referential_connection` (write-time reject when ConnectionDecl.to_place == place_id; AC-PF coverage). V1+ reservation added: `place.connection_gate_unresolved` (V1+ stricter gate validation; V1 collapses into connection_target_unknown).
- **Files modified outside `_boundaries/`** (recorded here for cleanup auditability):
  - `features/00_place/PF_001_place_foundation.md`:
    - **§3.1 (S1.1 / S1.3 / S1.4 / S3.2):** PlaceId newtype gains `impl From<ChannelId>` + `impl From<PlaceId>` + `impl AsRef<ChannelId>` for ergonomic hot-path conversion (avoids `.0` peppering at every Travel resolver / scene-roster / LLM AssemblePrompt site). EnvObjectSeedDecl/EnvObjectSeed split: author-declared form drops `seed_uid` field; world-service computes `seed_uid = UUID v5(reality_id, place_id, slot_id)` at materialization. ConnectionDecl `gate_seed_uid` renamed to `gate_slot_id` (author references slot_id; world-service resolves to seed_uid at write-time). New schema-policy subsection for `narrative_drift`: V1 freeform JSONB with explicit "no server-side schema validation V1" + "consumers SHOULD treat as opaque to LLM" guidance + V1+30d deferral PF-D13.
    - **§4 (S3.1):** Tavern row fixture-kind list typo fix — "Counter (sign as Door subtype if signage)" replaced with explicit "Sign (tavern signage)" + "Wall (for fireplace area)". Sign is its own EnvObjectKind, not a Door subtype.
    - **§6 (S2.2 / S3.4 / S3.5):** bidirectional flag clarified as **HINT-ONLY V1** (no mirror declaration written; Travel resolver reads both endpoint connections; PF-D14 deferral for write-time mirror optimization V1+30d). Travel-connection-resolver helper signature added: `pub async fn resolve_travel_connection(ctx, from_place, to_place) -> Result<ConnectionDecl, PlaceError>`. Resolution algorithm expanded to 11 explicit steps including step 9 (read reverse endpoint for bidirectional hint check) + step 11 (canon_ref None narrator fallback to PlaceType + ConnectionKind default phrasing).
    - **§7 (S2.1 / S2.6):** Cascade scope explicit — fires ONLY on transitions ending in Destroyed (Pristine/Damaged/Restored → Destroyed); other transitions do NOT auto-propagate (composability rule). Cascade order specified as 4-step deterministic sequence: (1) place state delta, (2) PlaceDestroyed signal with occupants sorted by (entity_type_discriminator, entity_id_uuid_bytes), (3) consumer cascades (PCS_001 / NPC_001 mortality in occupant order; held items drop per EF_001 §6.1), (4) PF cell-resident cascade (EnvObjects + Items at cell). Atomic batch with deterministic internal ordering for replay-determinism per EVT-A9.
    - **§8 (S1.3):** Fixture seed model split: EnvObjectSeedDecl (author-declared) vs EnvObjectSeed (materialized with computed seed_uid). Canonical instantiation flow updated to 6 steps including explicit "world-service computes seed_uid" step. Connection gate resolution via gate_slot_id added.
    - **§9 (S2.4 / S2.5):** Added `place.self_referential_connection` rule_id (V1) + `place.connection_gate_unresolved` (V1+ reservation). New EVT-T3 sub-shape `PlaceDestroyed` registered with full Rust shape (place_id + occupants with deterministic sort + trigger_reason 4-variant enum + fiction_time). `PlaceDestructionReason` enum: InteractionDestructive / AdminEdit / ScheduledCatastrophe / NarrativeCanonization.
    - **§15 (S3.3):** AC-PF-3 CI lint annotation unified to repo-wide `// CLOSED-ENUM-EXEMPT: <reason>` (NOT feature-prefixed) for closed-enum exhaustiveness discipline; namespace fragmentation avoided as new closed enums land.
    - **§16 (S1.2):** Added 3 new deferrals — PF-D12 (BookCanonRef shared-schema registration; envelope owner unspecified; should land alongside future IF_001 RealityManifest infrastructure feature) · PF-D13 (narrative_drift per-PlaceType opinionated schemas; V1+30d profiling) · PF-D14 (bidirectional flag write-time mirror optimization; V1+30d profiling).
    - **§18 readiness checklist:** Phase 3 cleanup line ticked with full summary; CANDIDATE-LOCK still pending closure pass.
  - `features/00_entity/EF_001_entity_foundation.md` AC-EF-1: CI lint annotation updated `EF-EXHAUSTIVE-EXEMPT` → unified `CLOSED-ENUM-EXEMPT` (cross-feature consistency for closed-enum exhaustiveness discipline; original namespace deprecated in favor of repo-wide convention).
  - `features/04_play_loop/PL_001b_continuum_lifecycle.md` §16.3: lazy-cell derivation policy expanded with explicit `derive_lazy_place(...)` defaults — PlaceType=Wilderness (most permissive), canon_ref=knowledge-service lookup OR AuthorCreated{LazyCellExpansion}, structural_state=Pristine, narrative_drift={}, connections=[ONE auto-added Public bidirectional back-reference to source_cell only], fixture_seed=[], display_name from prettify_path(leaf). Closes S2.3 spec gap.
- **Reason:** PF_001 Phase 3 adversarial review (mirror EF_001 cleanup pattern post-DRAFT) caught 14 defects across 3 severity tiers. User approved Option A (apply all). Severity 1 = Rust correctness + structural defects (4 fixes); Severity 2 = design gaps (6 fixes); Severity 3 = clarifications + cross-feature consistency (5 fixes). Most architecturally significant: S2.5 chose dedicated `PlaceDestroyed` cascade-trigger sub-shape over generic delta-filtering subscribe — explicit signal contract reduces implicit coupling between PF_001 + PCS_001 + NPC_001.
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_place_structural slot still tracked as PF-Q1 watchpoint (extends EF-Q3); physical slot ordering pending alignment review.
- **Drift watchpoints unchanged** (11 active; Phase 3 cleanup resolves under-specified items inline).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PF_001 Place Foundation feature registered (sibling of EF_001; closes spawn-empty-place gap)

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — PF_001 Place Foundation DRAFT, Option C max scope per user direction "place foundation trước spawn PC/NPC"); commit (this turn) `[boundaries-lock-claim+release]`
- **New folder + catalog created** (outside `_boundaries/`):
  - `features/00_place/_index.md` (foundation tier folder index — sibling of `features/00_entity/`)
  - `features/00_place/PF_001_place_foundation.md` (600 lines under 800 cap; 19 sections)
  - `catalog/cat_00_PF_place_foundation.md` (PF-1..PF-24 catalog entries; owns `PF-*` namespace)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - **New aggregate:** `place` (T2 / Channel-cell scope) — semantic place identity 1:1 with cell channels. Owned by **PF_001 Place Foundation** (DRAFT 2026-04-26). 10-variant PlaceType + 5-variant ConnectionKind + 4-state StructuralState + 11-variant EnvObjectKind + fixture-seed deterministic instantiation. Cascades into EF_001 §6.1 on Destroyed transition.
    - **Schema/envelope ownership new rows (2):**
      - EVT-T4 System sub-type `PlaceBorn` owned by PF_001 (emitted at canonical bootstrap + V1+ runtime spawn)
      - EVT-T8 Administrative sub-shape `Forge:EditPlace` owned by PF_001 (joins existing Charter*/Succession*/MortalityAdminKill registry)
    - **RealityManifest ownership row updated:** PF_001 added as required-V1 contributor (`places: Vec<PlaceDecl>`)
    - **RejectReason namespace prefix table:** added `place.*` → PF_001
    - **Stable-ID prefix ownership:** new row for `PF-*` (foundation tier; PF-A* axioms / PF-D* deferrals / PF-Q* open questions) owned by cat_00_PF_place_foundation.md
    - **Drift watchpoints:** added **PF-Q1** (validator slot ordering — extends EF-Q3) + **PF-Q4** (Place addressability: ExamineTarget discriminator vs EntityId variant — requires PL_005 closure-pass extension)
  - `02_extension_contracts.md`:
    - §2 RealityManifest current shape: added `places: Vec<PlaceDecl>` field with REQUIRED V1 invariant (every cell-tier channel must have a corresponding PlaceDecl; cells without decl reject `place.missing_decl`). Higher-tier channels MUST NOT have place rows V1.
    - §1.4 RejectReason namespace prefix table: added `place.*` owned by PF_001 with 11 V1 rule_ids enumerated (missing_decl / duplicate_place / invalid_structural_transition / unknown_place / connection_target_unknown / connection_locked / connection_private / connection_hidden / no_reverse_connection / fixture_seed_uid_collision / invalid_place_type_for_channel_tier) + 3 V1+ reservations (scheduled_decay_collision / cross_reality_connection / procedural_generation_rejected).
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_place_structural slot tracked as PF-Q1 watchpoint (extends EF-Q3); physical slot ordering pending alignment review.
- **Light PL_001 reopen** (folded into this commit per atomic discipline):
  - `features/04_play_loop/PL_001_continuum.md` §3.2 scene_state: `notable_props` semantics clarified — V1 freeform strings still supported; V1+ may reference EnvObjectIds for addressable fixtures (PF_001 fixture-seed is the SEMANTIC source; notable_props is the RUNTIME ambient layer).
  - `features/04_play_loop/PL_001b_continuum_lifecycle.md` §16.1 RealityManifest snippet: added `places: Vec<PlaceDecl>` field. §16.2 reality activation flow: added step ①c writing place rows + canonical EnvObject instantiation (deterministic UUID v5) + cell-to-place coverage validation. §16.3 lazy cell creation: added "every lazy cell must also create a place row derived from canon_ref" invariant.
- **Reason:** user identified Place foundation as next V1 gap after Entity foundation. Three concrete gaps closed: (1) Spawn mechanically possible but narratively empty — PL_001 cells had only ambient state, no semantic identity for LLM scene narration when actors arrive; (2) EF_001 EnvObject variant orphaned — no feature owned the canonical seed entry point for EnvObjects, despite EF_001 declaring `EnvObject(EnvObjectId)` V1; (3) Time-lapse undefined — no feature owned "places evolve when fiction-time advances or in-fiction events propagate". User direction "đi sâu thiết kế từ đầu" → Option C max scope. 11 sub-decisions locked at CLARIFY phase before draft (PlaceType 10 V1 / ConnectionKind 5 V1 / StructuralState 4-state / EnvObjectKind 11 V1 / fixture-seed deterministic UUID v5 / RealityManifest required extension / etc.).
- **Closes V1 spawn-readiness gap** for the foundation tier: PCS_001 (when designed) + NPC_001 + future Item + future EnvObject all build on locked PF_001 contract. PCS_001 brief at `features/06_pc_systems/00_AGENT_BRIEF.md` will be updated post-PF_001-LOCK to add §4.4d mandatory PF_001 reading.
- **Drift watchpoints:** 9 → 11 active (PF-Q1 + PF-Q4 added).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — EF_001 Entity Foundation closure pass → CANDIDATE-LOCK

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — EF_001 closure pass after Phase 3 cleanup commit 734dcd7); commit (this turn) `[boundaries-lock-claim+release]`
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - `entity_binding` row: status DRAFT → **CANDIDATE-LOCK 2026-04-26**; §14 acceptance: 10 scenarios AC-EF-1..10 noted
    - `entity_lifecycle_log` row: status DRAFT → **CANDIDATE-LOCK 2026-04-26**; LifecycleReasonKind enum updated (split AdminRestore → AutoRestoreOnCellLoad + AdminRestoreFromRemoved + new HolderCascade); EF-D10 archiving deferral noted
    - `EntityKind trait` schema row: updated to reflect Phase 3 trait shape split (4 body-only methods + new EntityBindingExt with 2 binding-side methods); status note CANDIDATE-LOCK 2026-04-26
    - `EVT-T4 EntityBorn` row: status note CANDIDATE-LOCK 2026-04-26
  - `02_extension_contracts.md` §1.4 RejectReason namespace: `entity.*` rule-id list expanded 7 V1 → **10 V1 + 2 V1+ reservations**. Added 2026-04-26 closure pass: `duplicate_binding` (primary-key violation; AC-EF-2) · `entity_type_mismatch` (denorm field doesn't match variant tag; AC-EF-3) · `lifecycle_log_immutable` (DP append_only enforcement wrapped in entity.* namespace; AC-EF-9). V1+ reservations: `cyclic_holder_graph` (when container/embedded enforcement lands EF-D3/D4) · `cross_reality_reference` (when multiverse portals land EF-D6).
- **No `03_validator_pipeline_slots.md` changes** — EVT-V_entity_affordance slot still tracked as EF-Q3 watchpoint; physical slot ordering pending alignment review.
- **Files modified outside `_boundaries/`** (recorded here for closure-pass auditability; full edits within EF_001 ownership):
  - `features/00_entity/EF_001_entity_foundation.md`:
    - Header status DRAFT → **CANDIDATE-LOCK 2026-04-26**
    - §8 RejectReason policy table: 7 V1 rule_ids expanded to 10 V1 with full Vietnamese reject copy + 2 V1+ reservation row
    - §14 acceptance criteria: 3 ACs (AC-EF-1 / AC-EF-8 / AC-EF-10) precision-tightened with explicit § grounding citations and atomicity scope clarifications; 3 ACs (AC-EF-2 / AC-EF-3 / AC-EF-9) rule_ids resolved against expanded §8 namespace
    - §17 readiness checklist: CANDIDATE-LOCK box ticked; closure-pass walk-through line added
  - `features/00_entity/_index.md`: Active cleared, folder closure status → **CLOSED for V1 design 2026-04-26**, EF_001 row updated to CANDIDATE-LOCK
- **Reason:** §14 acceptance walk-through (per closure-pass discipline established for WA / NPC / PLT folders) caught 3 AC rule_id mismatches (entity.duplicate_binding / entity.entity_type_mismatch / entity.lifecycle_log_immutable not in §8 V1 namespace) + 3 ACs needed precision tightening (AC-EF-1 lint specificity / AC-EF-8 timing scope / AC-EF-10 atomicity scope). All resolved by §8 namespace expansion + AC text tightening. Foundation tier now ready for downstream consumption.
- **Closes V1 entity foundation design** for the 4 EntityType variants (Pc/Npc/Item/EnvObject). Downstream impact:
  - **PL_005 Interaction**: Item refs gap CLOSED — PL_005 V1 implementable against EF_001 contracts (entity_binding for Item locations + AffordanceFlag enforcement + entity.* RejectReason namespace). PL_005 closure pass can now proceed.
  - **PCS_001** (when designed): brief at `features/06_pc_systems/00_AGENT_BRIEF.md` §4.4b mandatory EF_001 reading already in place; PCS_001 agent (when spawned) builds on locked EF_001 contracts including EntityKind for Pc with full 6-affordance V1 default set.
  - **NPC_001 Cast** (CANDIDATE-LOCK): mechanical rename to entity_binding completed in commit 04607ea; ActorId stays in NPC_001 §2 as canonical actor-context type per EF_001 §5.1 sibling-types relationship.
  - **PL_006 Status Effects**: `actor_status` keying on ActorId clarified as NOT a drift trap per EF_001 §5.1; stays as designed.
- **Drift watchpoints unchanged** (9 active; EF-Q3 still pending validator slot alignment).
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — EF_001 Entity Foundation feature registered (object foundation; actor_binding → entity_binding transfer)

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7 — EF_001 Entity Foundation DRAFT, Option C max scope per user direction "object foundation trước PC/NPC/Item") at 2026-04-26 (after PL_006 Status Effects agent released); commit (this turn) `[boundaries-lock-claim+release]`
- **New folder + catalog created** (outside `_boundaries/`):
  - `features/00_entity/_index.md` (foundation tier folder index)
  - `features/00_entity/EF_001_entity_foundation.md` (546 lines — single file under 800 cap; 18 sections)
  - `catalog/cat_00_EF_entity_foundation.md` (EF-1..EF-18 catalog entries; owns `EF-*` namespace)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - **Aggregate ownership transfer:** `actor_binding` → `entity_binding` from PL_001 Continuum to **EF_001 Entity Foundation** (DRAFT 2026-04-26). Extended scope: 4 EntityType variants (Pc/Npc/Item/EnvObject) + 4-state LocationKind (InCell/HeldBy/InContainer/Embedded) + 4-state LifecycleState (Existing/Suspended/Destroyed/Removed) + per-instance affordance_overrides. PL_001 §3.6 reopens to reference EF_001 as new owner.
    - **New aggregate:** `entity_lifecycle_log` (T2 / Reality, append-only) — per-entity audit trail with 8 LifecycleReasonKind variants. Owned by EF_001.
    - **Schema/envelope ownership new rows (2):** EVT-T4 System sub-type `EntityBorn` owned by EF_001 + **EntityKind trait** (5 methods; PCS_001/NPC_001/future Item/future EnvObject implement; type_default_affordances() required no-default to force explicit declaration).
    - **EVT-T3 Derived sub-types row updated:** PL_001 owns fiction_clock/scene_state/participant_presence (actor_binding removed; now under EF_001 as entity_binding) + EF_001 owns entity_binding + entity_lifecycle_log.
    - **RejectReason namespace prefix table:** added `entity.*` → EF_001.
    - **Stable-ID prefix ownership:** new row for `EF-*` (foundation tier; EF-A* axioms / EF-D* deferrals / EF-Q* open questions) owned by cat_00_EF_entity_foundation.md.
    - **Drift watchpoints:** CST-D1 row updated to cross-ref EF-Q2 (npc.current_region_id may migrate to entity_binding post-EF_001) + new **EF-Q3** row (validator slot ordering EVT-V_entity_affordance vs EVT-V_lex).
  - `02_extension_contracts.md` §1.4 RejectReason namespace prefix table: added `entity.*` owned by EF_001 with 7 V1 rule_ids enumerated (entity_destroyed / entity_removed / entity_suspended / affordance_missing / invalid_entity_type / invalid_lifecycle_transition / unknown_entity).
- **No `03_validator_pipeline_slots.md` changes in this commit** — EVT-V_entity_affordance slot insertion deferred to slot-table alignment review (tracked as EF-Q3 watchpoint). EF_001 §11 declares the slot conceptually; physical slot ordering to be locked in alignment pass.
- **Sweeping mechanical rename `actor_binding` → `entity_binding`** across 10 files (42 occurrences):
  - `features/04_play_loop/PL_001_continuum.md` (12 refs; §3.6 reopen — PL_001 now references EF_001 as owner)
  - `features/04_play_loop/PL_001b_continuum_lifecycle.md` (6 refs)
  - `features/04_play_loop/PL_002_command_grammar.md` (1 ref)
  - `features/04_play_loop/PL_005_interaction.md` (2 refs)
  - `features/04_play_loop/PL_005c_interaction_integration.md` (2 refs)
  - `features/05_npc_systems/NPC_001_cast.md` (10 refs; CANDIDATE-LOCK feature — pure mechanical rename, no design content change)
  - `features/05_npc_systems/NPC_002_chorus.md` (2 refs; CANDIDATE-LOCK feature — same)
  - `features/06_pc_systems/00_AGENT_BRIEF.md` (3 refs; brief updated incl. §4 Required reading addition)
  - `07_event_model/03_event_taxonomy.md` (2 refs)
- **Reason:** user identified V1 design gap during planning post-PL_006: PL_005 Interaction defers Item aggregate "refs only V1" but Strike/Give/Use all reference Item as tool/target → not V1-implementable without Item entity model. ActorId enum (NPC_001 §2) covers Pc+Npc only; Items + EnvObjects unaddressable. Per-feature ad-hoc lifecycle invention (drift trap WA_006 originally hit). User direction "đi sâu vào thiết kế từ đầu để phát hiện vấn đề từ sớm" → Option C max scope. 8 sub-decisions locked: Q1 4 EntityId variants V1 / Q2 4-state LocationKind / Q3 4-state LifecycleState / Q4 closed AffordanceFlag enum + per-type defaults / Q5 Concrete aggregates + EntityKind trait (NOT full ECS — preserves "feature owns its aggregate" boundary discipline) / Q6 hard-reject + per-kind soft-override (Examine tolerates Destroyed) / Q7 single file (split EF_001b only if crosses 700 lines; current 546) / Q8 new catalog cat_00_EF_entity_foundation.md owns EF-* namespace.
- **Process note on CANDIDATE-LOCK feature touch:** NPC_001 + NPC_002 are CANDIDATE-LOCK; this commit modifies them ONLY for the actor_binding → entity_binding mechanical rename (no design-content change). Per matrix "When ownership changes" protocol, transfers require updating both giving (PL_001) + receiving (EF_001) feature docs + downstream references. Mechanical sweep across 10 files is structural refactor, not redesign.
- **Closes V1 design gap** for PL_005 Item references (entity addressability) + ActorId scope-creep + per-feature lifecycle drift. PCS_001 brief updated to add EF_001 to required reading; PCS_001 agent (when spawned) builds on EF_001 contracts.
- **Drift watchpoints:** 8 → 9 active (EF-Q3 added); CST-D1 cross-refs EF-Q2.
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PL_006 Status Effects feature registered (status foundation)

- **Lock claim:** main session (PL_006 Status Effects feature design — status foundation per user direction "status foundation?") at 2026-04-26 (after closure-pass agent released); commit `a39d880` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md` "Aggregate ownership" section: added `actor_status` row owned by **PL_006 Status Effects** (T2/Reality; cross-actor PC+NPC; per-(reality, actor_id) row holds `Vec<StatusInstance>`; owns `StatusFlag` closed-set enum V1=4 kinds Drunk/Exhausted/Wounded/Frightened; V1+ kinds reserved; Apply/Dispel via PL_005 Interaction OutputDecl with `aggregate_type=actor_status`; V1+30d auto-expire via Scheduled:StatusExpire Generator).
  - `02_extension_contracts.md` §1.4 RejectReason namespace prefix table: added `status.*` owned by PL_006 Status Effects.
- **Reason:** user direction prioritized "status foundation" as Option A among 3 V1 gap candidates (PL_006 Status Effects vs PO_001 PC Creation vs Knowledge Accrual). Foundation discipline rationale: PCS_001 brief §S5 has `pc_stats_v1_stub.status_flags: Vec<StatusFlag>` but never defines enum; without PL_006, PCS_001 + future NPC_003 would each invent ad-hoc enums (drift trap WA_006 originally hit before thin-rewrite). PL_006 owns enum + lifecycle ONCE; consumers reference. **Cross-actor uniformity** (D6 sub-decision): single `actor_status` aggregate covers PC + NPC. **Stack policies per flag** (D8.3 in feature doc): Drunk=Sum / Exhausted=ReplaceIfHigher / Wounded=Sum / Frightened=ReplaceIfHigher. **V1 simplification** (D5 sub-decision): Apply + Dispel manual only; auto-expire deferred to V1+30d scheduler.
- **PL_006 deliverable:** new `features/04_play_loop/PL_006_status_effects.md` (462 lines under 500-line soft cap), 18 sections covering Domain concepts (StatusFlag closed enum + StatusInstance + StatusSource + Stack policies) + Event-model mapping (no new EVT-T*; T3 apply/dispel + T5 V1+30d auto-expire) + 1 new aggregate + DP primitives + Capability + Subscribe pattern (UI invalidation + Chorus SceneRoster context) + Pattern choices + Failure UX (`status.*` namespace) + Cross-service handoff (inherits PL_005 §10 pattern) + 4 sequences (Apply Drunk / Apply Exhausted / Dispel via /sleep / V1+30d auto-expire deferred) + 7 V1-testable acceptance scenarios + 8 deferrals (STA-D1..D8) + cross-references + readiness.
- **Closes V1 vertical-slice gap:** Use:wine outcome locked (AC-STA-1); Strike intents Stun/Restrain unblocked V1+; PCS_001 + NPC_003 reference shared StatusFlag enum without drift.
- **Drift watchpoints unchanged** (8 still active; no new boundary review items)
- **Lock release:** at end of PL_006 commit (this turn)

---

## 2026-04-26 — Closure-pass status promotions: PL_002 + NPC + PLT folders

- **Lock claim:** main session 2026-04-26 (Claude Opus 4.7, this conversation — closure pass continuation) at 2026-04-26 (after PL_005 agent released); commit `[boundaries-lock-claim+release]` (this turn)
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `tool_call_allowlist` row: PL_002 Grammar status → **CANDIDATE-LOCK 2026-04-25**; §13 acceptance: 10 scenarios
    - `npc_reaction_priority` row: NPC_002 Chorus status → **CANDIDATE-LOCK 2026-04-26**; §14 acceptance: 10 scenarios (SPIKE_01 turn 5 reproducibility verified)
    - `chorus_batch_state` row: NPC_002 Chorus status → **CANDIDATE-LOCK 2026-04-26**
    - `npc` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**; §14 acceptance: 10 scenarios
    - `npc_session_memory` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `npc_pc_relationship_projection` (R8 import) row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `npc_node_binding` row: NPC_001 Cast status → **CANDIDATE-LOCK 2026-04-26**
    - `lex_config` row: WA_001 Lex status → **CANDIDATE-LOCK 2026-04-25** (date stamp added; status was set in WA closure pass)
    - `actor_contamination_decl` / `actor_contamination_state` / `world_stability` rows: WA_002 Heresy status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `forge_audit_log` row: WA_003 Forge status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `coauthor_grant` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**; §14 acceptance: 10 scenarios AC-CHR-1..10
    - `coauthor_invitation` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**
    - `ownership_transfer` row: PLT_002 Succession status → **CANDIDATE-LOCK 2026-04-25**; PLT_002b lifecycle split noted; §14 acceptance: 10 scenarios AC-SUC-1..10
    - `mortality_config` row: WA_006 Mortality status → **CANDIDATE-LOCK 2026-04-25** (date stamp added)
    - `meta_user_pending_invitations` row: PLT_001 Charter status → **CANDIDATE-LOCK 2026-04-25**
- **No other boundary files modified** — `02_extension_contracts.md` unchanged (PL_005 agent already added `interaction.*`); `03_validator_pipeline_slots.md` unchanged (no slot changes from closure pass).
- **Reason:** sequential closure passes (Q1-Q5 across PL_002 / NPC / PLT folders) brought 6 additional features to **CANDIDATE-LOCK** status with §13/§14 acceptance criteria. Boundary matrix updated to reflect new statuses + acceptance scenario counts. PL_005 Interaction (DRAFT 2026-04-26 by parallel agent) is intentionally NOT included in this status promotion; PL_005 is in DRAFT and will be CANDIDATE-LOCK'd in a separate future closure pass.
- **Closure pass summary** (mirrored from feature folder `_index.md` files):
  - **PL folder (04_play_loop):** PL_001/001b Continuum CANDIDATE-LOCK (boundary-tightened) · PL_002 Grammar CANDIDATE-LOCK 2026-04-25 (§13: 10 scenarios) · PL_005/005b/005c Interaction DRAFT 2026-04-26 (parallel agent)
  - **NPC folder (05_npc_systems):** CLOSED for V1 design 2026-04-26 — NPC_001 Cast CANDIDATE-LOCK 2026-04-26 (§14: 10 scenarios AC-CST-1..10) · NPC_002 Chorus CANDIDATE-LOCK 2026-04-26 (§14: 10 scenarios AC-CHO-1..10 incl. SPIKE_01 turn 5 reproducibility)
  - **PLT folder (10_platform_business):** PLT_001 Charter CANDIDATE-LOCK 2026-04-25 (§14: 10 scenarios AC-CHR-1..10) · PLT_002/002b Succession CANDIDATE-LOCK 2026-04-25 (§14: 10 scenarios AC-SUC-1..10)
  - **Total at CANDIDATE-LOCK after this pass:** 13 features across 4 closed folders (WA: 5 · PL: 3 · NPC: 2 · PLT: 3) — full V1 design surface for these folders
- **Sibling work landed in same window** (informational, not part of this lock claim):
  - 07_event_model agent: Phase 1-6 LOCKED + Option C redesign + EVT-G* Generator Framework (own changelog entries above)
  - PL_005 Interaction agent: PL_005/005b/005c DRAFT 2026-04-26 (own changelog entry above)
  - PCS_001 PC substrate brief seeded at `features/06_pc_systems/00_AGENT_BRIEF.md` for parallel agent (no boundary-folder edits required for brief seeding)
- **Drift watchpoints unchanged** (8 still active; status promotions don't introduce new drift)
- **Lock release:** at end of this commit (`[boundaries-lock-claim+release]`)

---

## 2026-04-26 — PL_005 Interaction feature registered

- **Lock claim:** main session (PL_005 Interaction feature design — core gameplay primitive) at 2026-04-26; commit `990eea3` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md` "Schema/envelope ownership" section, EVT-T1 Submitted sub-types row: added **PL_005 Interaction** owns 5 V1 sub-types (`Interaction:Speak` / `Interaction:Strike` / `Interaction:Give` / `Interaction:Examine` / `Interaction:Use`); V1+ kinds (Collide/Shoot/Cast/Embrace/Threaten) reserved.
  - `02_extension_contracts.md` §1.4 RejectReason namespace prefix table: added `interaction.*` owned by PL_005 Interaction.
- **Reason:** PL_005 Interaction is the core gameplay primitive (4-role pattern + ProposedOutputs/ActualOutputs split + 5 V1 InteractionKinds) per user direction "core của gameplay". Phase 0 deliverable approved with defaults: B1 NPC mortality deferred to NPC_003 future + V1 placeholder · B2 Item aggregate deferred V1 (refs only) · B3 self-output simple (agent in direct_targets) · B4 atomic outputs (world-rule WA_001 Lex derives ActualOutputs at validator stage) · B5 catalog placement = `features/04_play_loop/PL_005_interaction.md` · B6 phase plan accepted. **Zero new aggregates V1** (deliberate scope discipline; references existing aggregates from PL_001/NPC_001/PCS_001/WA_001/WA_006/PL_002).
- **PL_005 deliverable:** new `features/04_play_loop/PL_005_interaction.md` (491 lines under 500-line soft cap), 19 sections covering Domain concepts + Event-model mapping + Aggregate inventory (zero new V1) + DP primitives + Capability + Subscribe pattern + Pattern choices + Failure UX + Cross-service handoff (CausalityToken chain) + 5 sequences (Speak/Strike/Give/Examine/Use) + 6 acceptance criteria scenarios + 9 deferrals (INT-D1..D9) + cross-references + readiness checklist.
- **Closes original-goal context** for "interaction" core gameplay: provides the dispatch contract that turns user input into committed canonical events with role-typed inputs + world-rule-derived outputs + downstream cascade hooks.
- **Drift watchpoints unchanged** (8 still active; no new boundary review items)
- **Lock release:** at end of PL_005 commit (this turn)

---

## 2026-04-25 (late evening, post-closure) — 07_event_model Phase 6 Generation Framework

- **Lock claim:** event-model agent (Phase 6 Generator Framework + Coordinator service spec) at 2026-04-25 (late evening, post-folder-closure reopening); commit `03560eb` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - Stable-ID prefix table EVT-* row extended: added `EVT-P1`/`P3`/`P4`/`P5`/`P6`/`P8` active markers + `EVT-P2`/`P7`/`P9`/`P10`/`P11` `_withdrawn` markers (catching up from Option C earlier this session); added `EVT-V1..V7` / `EVT-L1..L19` / `EVT-S1..S6` numeric ranges as Phase 3-4 reflection; **added new `EVT-G1..G6` namespace** for Phase 6 Generation Framework
    - Schema/envelope ownership table: added new **Generator Registry** row (Phase 6 EVT-G1) — declares ownership pattern: 07_event_model owns the registry framework; per-feature owns specific generators with composite `logical_id` + blake3 `registry_uuid`; Coordinator runs in-process per channel-writer (no new service binary V1)
- **No other boundary files modified** — `02_extension_contracts.md` unchanged (extension contracts are about cross-feature schemas; Generator Registry is its own concept); `03_validator_pipeline_slots.md` unchanged (validators are distinct from generators)
- **Reason:** user identified post-Option-C systematic-management gap for event generation. Original Phase 1-5 had axiom-level coverage (EVT-A9 RNG determinism + EVT-A12 (f) extensibility) but lacked operational framework. User picked Option C ("đi sâu vào thiết kế cái này để nếu có sai thì chưa cháy kịp thời ngay từ bây giờ") — full framework + Coordinator service design at design phase to fail-fast before V1+30d implementation. 5 sub-decisions D6.1-D6.5 approved (in-process per channel-writer / composite+UUID ID / both static+runtime cycle detection / tiered capacity / new EVT-G* prefix).
- **Phase 6 deliverable:** new `07_event_model/12_generation_framework.md` (343 lines, 6 sections covering EVT-G1 Registry + EVT-G2 5-source typed taxonomy + EVT-G3 cycle detection + EVT-G4 capacity governance + EVT-G5 Coordinator spec + EVT-G6 extension procedure). Deployment: in-process per channel-writer (zero new service binary V1; matches DP-Ch26 pattern). 6 failure modes that fragmented per-feature generation would hit are explicitly addressed.
- **Closes original-goal #4** ("generate event theo điều kiện + xác suất") at systematic level. EVT-A12 extension point (f) "new generation rule" operationalized with 6-step procedure.
- **Drift watchpoints unchanged** (8 still active; no new boundary review items)
- **Lock release:** at end of Phase 6 commit (this turn)

---

## 2026-04-25 (late evening) — 07_event_model Option C redesign Phase 1

- **Lock claim:** event-model agent (07_event_model Option C redesign) at 2026-04-25 (late evening); commit `66ce219` `[boundaries-lock-claim]`
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - Stable-ID prefix table row for EVT-* updated to enumerate active vs `_withdrawn` IDs (T1/T3/T4/T5/T6/T8 active; T2/T7/T9/T10/T11 `_withdrawn` per I15) + EVT-A1..A12 active
    - Schema/envelope ownership table: renamed `EVT-T8 AdminAction` → `EVT-T8 Administrative` (reframe per Option C)
    - Schema/envelope ownership table: added 3 new rows for sub-type ownership of newly-active categories — **EVT-T1 Submitted sub-types** (PL_001/PL_002 own PCTurn; NPC_001/NPC_002 own NPCTurn; future quest-engine owns QuestOutcome) · **EVT-T3 Derived sub-types** (sub-discriminator = `aggregate_type`; PL_001/NPC_001/PL_002 own respective aggregates; calibration sub-shapes absorbed from former EVT-T7) · **EVT-T5 Generated sub-types** (gossip aggregator owns BubbleUp:RumorBubble; world-rule-scheduler owns Scheduled:NPCRoutine + Scheduled:WorldTick V1+30d; quest-engine owns Scheduled:QuestTrigger; combat owns RNG-based generators)
- **Files NOT modified in this lock:** `02_extension_contracts.md` (TurnEvent envelope §1 + AdminAction §4 already at correct mechanism level — no changes needed; only category-name reference "AdminAction → Administrative" implied in §4 cross-ref, but §4 itself unchanged); `03_validator_pipeline_slots.md` (unchanged — already mechanism-level)
- **Reason:** event-model agent's Option C redesign reframed Event Model from feature-specific taxonomy (T1 PlayerTurn / T2 NPCTurn / T7 CalibrationEvent / T9 QuestBeat / T10 NPCRoutine / T11 WorldTick) to mechanism-level taxonomy (T1 Submitted / T3 Derived / T4 System / T5 Generated / T6 Proposal / T8 Administrative). 8 existing axioms preserved (A4/A7/A8 reframed wording; A1/A2/A3/A5/A6 preserved); 4 new axioms added (A9 probabilistic generation determinism · A10 event as universal source of truth · A11 sub-type ownership discipline · A12 extensibility framework). Original Phase 1 commit `ce6ea97` superseded by the redesign commit (this turn).
- **EVT-T2/T7/T9/T10/T11 retirement rationale:** each was mechanically identical to (or a sub-shape split of) one of the active mechanism categories — T2 NPCTurn merged into T1 Submitted as sub-type (only actor variant differs); T7 CalibrationEvent merged into T3 Derived (calibration is a Derived event from FictionClock advance); T9 QuestBeat split (Trigger → T5 Generated, Advance → T3 Derived, Outcome → T1 Submitted); T10 NPCRoutine + T11 WorldTick both merged into T5 Generated (different sub-types via Scheduled:* prefix).
- **Feature doc citation updates** (in same redesign commit):
  - `features/04_play_loop/PL_002_command_grammar.md` §2.5 — citations updated to active EVT-T* IDs + sub-types
  - `features/05_npc_systems/NPC_001_cast.md` §2.5 — EVT-T2 references redirected to EVT-T1 sub-type=NPCTurn
  - `features/05_npc_systems/NPC_002_chorus.md` §2.5 — EVT-T2 references redirected to EVT-T1 sub-type=NPCTurn
- **Drift watchpoints unchanged** (8 still active; ownership identifiers updated)
- **Lock release:** at end of redesign commit (this turn)

---

## 2026-04-25 (evening) — WA folder closure: ownership matrix update

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25 (evening); released at end of this commit
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `forge_audit_log` row: WA_003 status PROVISIONAL → **CANDIDATE-LOCK**; reframed note (patterns extractable, V2+ optimization not boundary fix); §14 acceptance noted
    - `mortality_config` row: WA_006 status updated to **CANDIDATE-LOCK** (thin-rewrite from 730 → 403 lines closure pass); §12 acceptance noted
    - `pc_mortality_state` row: removed PROVISIONAL/over-extended note; cleanly attributes to PCS_001 (mechanics fully handed off from WA_006 in closure pass)
- **No other boundary files modified** in this pass (extension contracts §1.4 RejectReason namespace prefixes already correct; validator pipeline §6.1 unchanged; ID prefix table unchanged)
- **Reason:** WA folder closure pass (commit f436e60) brought all 5 WA features to CANDIDATE-LOCK with acceptance criteria. Boundary folder updated to reflect new statuses + clean handoffs to mechanics owners (PCS_001 / 05_llm_safety / PL_001/002 / NPC_001/002).
- **WA folder closure summary** (mirrored from `features/02_world_authoring/_index.md`):
  - WA_001 Lex CANDIDATE-LOCK (656 lines, §14: 10 scenarios)
  - WA_002 Heresy root CANDIDATE-LOCK (597 lines)
  - WA_002b Heresy lifecycle NEW + CANDIDATE-LOCK (277 lines, §14: 10 scenarios)
  - WA_003 Forge CANDIDATE-LOCK (798 lines, §14: 10 scenarios; reframed pattern-reuse not boundary violation)
  - WA_006 Mortality CANDIDATE-LOCK (403 lines thin-rewrite; §12: 6 scenarios)
  - Total: 5 docs, ~2,730 lines, all under 800-line cap
- **Drift watchpoints unchanged** (8 still active; HER-D8/D9/LX-D5 all still tracked; WA_006 over-extension watchpoint resolved by thin-rewrite)
- **Lock release:** at end of this commit

---

## 2026-04-25 (afternoon) — WA boundary shrink: ownership matrix update

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25 (afternoon)
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `coauthor_grant`, `coauthor_invitation` → owner WA_004 → **PLT_001 Charter** (formerly WA_004; relocated 2026-04-25)
    - `ownership_transfer` → owner WA_005 → **PLT_002 Succession** (formerly WA_005)
    - `meta_user_pending_invitations` → owner WA_004 → **PLT_001 Charter** (formerly WA_004)
    - `forge_audit_log` consumers list updated (PLT_001 + PLT_002 + WA_006 instead of WA_004/005/006)
    - WA_003 Forge marked PROVISIONAL with note about future cross-cutting extraction
    - `RejectReason` namespace prefix table expanded — added `canon_drift.*`, `capability.*`, `parse.*`, `chorus.*`, `forge.*`, `charter.*`, `succession.*`; "Pending Path A tightening" replaced with "Path A applied 2026-04-25 (commit f7c0a54)"
    - `ForgeEditAction`, capability JWT, EVT-T8 sub-shapes — owner attributions for Charter/Succession updated WA_004/005 → PLT_001/002
    - Stable-ID prefix ownership rows: `CHR-D*`/`CHR-Q*` owner WA_004 → PLT_001; `SUC-D*`/`SUC-Q*` owner WA_005 → PLT_002
    - Drift watchpoint `CHR-D9`: owner WA_004 → PLT_001
  - `02_extension_contracts.md`: same pattern across §1.4 RejectReason table, §3 capability JWT, §4 EVT-T8 sub-shapes — all WA_004/005 references re-attributed to PLT_001/002
- **Drift watchpoints unchanged** (8 still active; ownership identifiers updated)
- **No new contracts added** — pure ownership re-attribution
- **Reason:** post-WA boundary review concluded WA's original intent ("validate rules of reality + detect paradox + allow controlled bypass") doesn't cover identity/account concerns. WA_004 Charter + WA_005 Succession relocated to `10_platform_business/` (commit 4be727d); WA_003 Forge marked PROVISIONAL pending future cross-cutting pattern extraction; WA_006 Mortality already PROVISIONAL from prior review (commit de9cf1a). WA folder shrinks from 6 to 3 active features (WA_001 Lex, WA_002 Heresy, WA_003 Forge PROVISIONAL) + 1 PROVISIONAL marker (WA_006).
- **Lock release:** at end of this commit

---

## 2026-04-25 — Folder seeded

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25
- **Files created:**
  - `_LOCK.md` (single-writer mutex)
  - `00_README.md` (purpose, rules, how-to-use)
  - `01_feature_ownership_matrix.md` (initial entries for 11 designed features: PL_001/001b/002, NPC_001/002, WA_001..006)
  - `02_extension_contracts.md` (TurnEvent envelope §1, RealityManifest §2, capability JWT §3, EVT-T8 sub-shapes §4)
  - `03_validator_pipeline_slots.md` (proposed EVT-V* ordering pending event-model Phase 3 lock)
  - `99_changelog.md` (this file)
- **Initial drift watchpoints captured (8):** GR-D8, CST-D1, LX-D5, HER-D8, HER-D9, CHR-D9, WA_006 over-extension, B2 RealityManifest envelope
- **Reason:** post-WA_006 boundary review (2026-04-25) revealed boundary issues across the 11 features designed in one work session; a mutex'd boundary folder is the long-term fix
- **Lock release:** at end of seeding commit
