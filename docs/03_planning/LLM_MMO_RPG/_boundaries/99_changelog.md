# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

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
