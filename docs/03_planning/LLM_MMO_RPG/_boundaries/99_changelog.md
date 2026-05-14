# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

---

## 2026-05-14 — GEO_002 POL_001 Political Layer Generator DRAFT + /review-impl 2-pass fix cycle (V1+30d activation feature; Phase 0 D1-D7 LOCKED; HIGH-1..HIGH-4 + 12 MED + 3 LOW resolved)

- **Lock CLAIMED + RELEASED** in single cycle (combined `[boundaries-lock-claim+release]` commit pattern — DRAFT + /review-impl 1st pass + /review-impl 2nd pass + MED batch + LOW batch all in this commit, mirroring GEO_001 fix-cycle precedent).
- **Trigger:** user picked option 3 from SESSION_HANDOFF next-step recommendations (`GEO_002 POL_001 Political Layer Generator design — V1+30d schedule; activates GEO_001 political layer fields`). Phase 0 sub-decisions D1-D7 proposed with recommended defaults; user replied `1` = approve all 7 with defaults. DRAFT landed; user invoked `/review-impl` → 3 HIGH issues caught + fixed inline → user invoked `/review-impl` 2nd pass → 1 HIGH (introduced by 1st-pass HIGH-3 fix) + 12 MED + 3 LOW caught → user replied `tiếp tục đi` (= "proceed / fix all") → all 16 findings batch-applied → ready for commit.
- **/review-impl 4 HIGH findings + fixes (applied inline in this commit):**
  1. **HIGH-1** — CreativeSeed.schema_version 2 → 3 bump (POL_001 adds 3 additive fields; per I14 + GEO_001b 1→2 precedent, additive field-sets bump version). Propagated to §3 doc + LLM-authoring template version bump v1.tmpl → v2.tmpl note.
  2. **HIGH-2** — PoliticalSeedMode::Canonical semantic conflict across §4.1 / §5.1 / AC-POL-3. Aligned all 3 to: Canonical = NO procedural seeds; canonical-province flood-fill covers entire continent; canonical_state_decl_index assignments derive state membership directly (no algorithmic state flood-fill).
  3. **HIGH-3** — Procedural state-formation "greedy clustering" was algorithmically ambiguous (EVT-A9 replay-determinism violation). Pinned to deterministic graph-connected-component clustering on orphan provinces via TerrainCost path ≤ max_state_radius + geometric-distance pre-filter (MED-10 cost-envelope optimization). Per-stage RNG sub-streaming added (MED-3 1st pass).
  4. **HIGH-4** *(introduced by HIGH-3 fix)* — Stage 5 procedural state naming created circular dependency with stage 8 (state.name needs culture_tag, culture_tag needs state.member_provinces). Severed via culture-agnostic V1+30d naming `{centroid_province.name}_State_{6-hex-of-state-id}`; culture-aware Markov-chain naming deferred V2+ as new POL-D13.
- **/review-impl 12 MED findings + fixes (applied inline in this commit):**
  - **MED-1** — SetCultureRegion empty cell_ids → reject `geography.set_culture_region_empty` + POL-V16 validator + AC-POL-16
  - **MED-2** — SetCultureRegion new-CultureRegion hearth_cell deterministic via `MIN(cell_ids by GeoCellId)` (replaces order-dependent "first cell")
  - **MED-3** — SplitProvince partition_count<2 separated into dedicated reject `geography.split_partition_min_2` + POL-V17 validator + AC-POL-17 (distinct user-facing error from partition_cap_exceeded for >8)
  - **MED-4** — TransferProvinceToState same-state → reject `geography.transfer_self_target` + POL-V18 validator + AC-POL-18
  - **MED-5** — No CreateState / DestroyState V1+30d deferred to V2+ via new POL-D14 (paired with POL-D2 T6 NarrativePoliticalEdit Generator since LLM-proposed political evolution often co-occurs with state creation/extinction); V1+30d civil-war breakaway scenarios use `(SplitProvince → TransferProvinceToState)` chain referencing pre-canonical-declared States
  - **MED-6** — Capability migration plan for POL ship: auth-service one-shot migration auto-grants `can_edit_political_geography` to all current `can_edit_geography` holders; PLT_001 `forge.roles_version` bump; cohort-style rollout (staging→production 24h soak)
  - **MED-7** — CultureTag tiebreaker pinned to `as_canonical_str() -> &str` byte-wise lexicographic order (CultureTag opaque-V1 representation pinned via this method)
  - **MED-8** — Canonical mode with 0 canonical_provinces → reject `geography.canonical_mode_no_seeds` (degenerate world) + POL-V19 validator + AC-POL-19
  - **MED-9** — canonical_state.capital_province ↔ canonical_province.canonical_state cross-reference asymmetry → reject `geography.canonical_state_province_mismatch` + POL-V20 validator + AC-POL-20
  - **MED-10** — HIGH-3 clustering O(V²) cost-envelope clarified + geometric-distance pre-filter optimization documented + CI gate (synthetic-orphan stress test with V=500 verifies <500ms wall-clock)
  - **MED-11** — HIGH-1 wording precision: actual cross-version data path governed by `generator_pipeline_version` pin (GEO_001 §3 MED-4) — pre-POL realities never run stage 5/8 regardless of CreativeSeed version they hold. Schema_version compat matters only at fresh bootstrap.
  - **MED-12** — Stage 8 `political_seed_substream(b"stage8_*")` clarified as RESERVED for V2+ extensions; stage 8 V1+30d has no RNG consumer (deterministic flood-fill + Vec-order tiebreaker + CultureTag.as_canonical_str tiebreaker)
- **/review-impl 3 LOW findings + fixes (applied inline in this commit):**
  - **LOW-1** — All 4 apply_delta function signatures changed from `Result<(), DeltaApplyError>` to `()` (consistency with GEO_001 §7; DeltaApplyError was referenced but never defined)
  - **LOW-2** — AC-POL-21 added: island-state coverage (water-isolated land mass with capital; Ocean=∞ TerrainCost preserves island as separate state cluster)
  - **LOW-3** — "Parallel Dijkstra" wording → "multi-source Dijkstra" (clarified single priority queue seeded with every ProvinceSeed at cost 0)
- **Process lesson — 2-pass /review-impl maturity model:**
  1st pass caught 3 HIGH issues; 2nd pass caught 1 NEW HIGH issue (introduced by 1st-pass HIGH-3 fix — fix-introduced regression) + 12 MED + 3 LOW that 1st pass had missed. Validates the CLAUDE.md Phase 9 + handoff discipline: POST-REVIEW alone rubber-stamps; /review-impl is a distinct mental mode; **iterating /review-impl until 0 HIGH findings is the right loop**. The 2nd pass caught HIGH-4 specifically because HIGH-3's fix referenced "stage 8 backreference" which is the kind of cross-stage circular dep that requires fresh adversarial reading post-fix. Pattern locked for future foundation-feature decision-locking.
- **Status outcome:** GEO_002 DRAFT is V1+30d-implementation-ready with all surfaced issues addressed. Remaining work for V1+30d implementation phase: `world-service/geography-generator` political layer Rust module + auth-service capability migration job + chat-service S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` extension with state_name + culture_tag fields + CI gates (replay-determinism + apply_delta total-function + HIGH-3 clustering V=500 stress test + canonical-JSON normalization inherited).
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim → release (Owner reverted to None)
  - `01_feature_ownership_matrix.md`: `world_geometry` row owner annotation extended with POL_001 V1+30d activation context (pipeline stages 5+8 activation, GeographyDeltaKind 5 V1 → 9 with V1+30d active, capability `can_edit_political_geography`, namespace extension, Phase 0 D1-D7 LOCKED summary). No new aggregate (POL_001 V1+30d populates GEO_001's existing fields).
  - `02_extension_contracts.md`: §1.4 `geography.*` row extended with POL_001 V1+30d 15 rule_ids (5 schema-level + 10 user-facing) + capability addition note + GeographyDeltaKind closed-enum bump R3 additive (5 V1 + 4 V1+30d active) + CreativeSeed v2 additive fields + lifted `geography.layer_activation_deferred_v1` for political layer specifically + 1 new V2+ reservation; §2 RealityManifest GeographyDeltaKind comment block updated to reflect 5 V1 + 4 V1+30d + 1 V2+ enum count
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_geography/GEO_002_political_layer.md` (NEW, 695 lines): single DRAFT cycle; sections §1 Why + §2 Domain concepts + §2.5 Event-model mapping (NO new EVT-T*; reuses GEO_001 EVT-T3/T8 registrations) + §3 Schema activation (no new aggregate; extends GeographyDeltaKind closed enum 5 V1 → 5 V1 + 4 V1+30d active per R3 additive; Vec<ProvincePartition> payload for SplitProvince) + §4 Closed enums (PoliticalSeedMode 3-variant + SeedSource 2-variant + SeedScope 3-variant) + §5 Pipeline stages 5 + 8 algorithm detail (priority-queue flood-fill from canonical seeds + procedural fallback per POL-D2 hybrid; CultureBarrier ≠ TerrainCost rationale) + §6 CreativeSeed authoring additive fields within v2 (political_seed_mode + canonical_states + procedural_density) + §7 apply_delta total-function for 4 V1+30d DeltaKinds + §8 15 validator slots (POL-V1..POL-V15) + §9 DP primitives + capability JWT addition + §10 Composition with siblings + §11 RealityManifest extension (no new field; absorbs via creative_seed v2) + §12 Failure UX 15 rule_ids + §13 Cross-service handoff + §14 Multiverse inheritance (inherits GEO_001 §9 unchanged) + §15 5 sequences (hybrid bootstrap / Forge MergeProvinces / Forge SetCultureRegion / Forge SplitProvince / cycle reject) + §16 15 V1+30d-testable acceptance scenarios AC-POL-1..15 + §17 12 deferrals POL-D1..D12 + §18 5 open questions POL-Q1..Q5 + §19 cross-refs + §20 implementation readiness
  - `features/00_geography/_index.md`: GEO_002 row added; coordination note updated for POL_001 V1+30d composition
  - `catalog/cat_00_GEO_geography_foundation.md`: NEW POL_001 sub-section with 24 catalog entries (POL-1..POL-24) under the existing `GEO-*` namespace (POL-* is sub-prefix per consistent foundation pattern); GEO-21 catalog placeholder upgraded marker added (📦 → 📦 DRAFT)
- **Decisions applied (Phase 0 D1-D7; user approved all 7 with defaults via `1`):**
  1. **POL-D1** scope — politics + culture in one POL_001 (NOT split into POL_002 culture-only feature). Rationale: stage 5 + stage 8 share `political_seed` + share priority-queue flood-fill algorithm + share canonical-author declarations; splitting fragments the seed-share contract.
  2. **POL-D2** capital seed source — Hybrid (canonical takes priority + procedural fills remainder). Wuxia worlds need exact canonical state placement; algorithmic worlds need automatic seeding. Mirrors GEO_001's deterministic-base + delta-overlay discipline.
  3. **POL-D3** state formation — flood-fill from canonical_states capital seeds + procedural fallback for orphan provinces.
  4. **POL-D4** province ↔ state cardinality — allow stateless provinces V1+30d via `Province.state_id: Option<StateId>`. Frontier / disputed / no-man's-land is a genuine wuxia/strategy pattern (giang hồ, jianghu).
  5. **POL-D5** culture × political relationship — independent overlays with cross-reference. `province.culture_tag: Option<CultureTag>` dominant-culture summary; `culture_regions: Vec<CultureRegion>` full overlay.
  6. **POL-D6** DeltaKind V1+ scope — all 4 V1+30d active (MergeProvinces + SplitProvince + TransferProvinceToState + SetCultureRegion). Symmetric set covers admin canonization needs.
  7. **POL-D7** namespace — share `geography.*` (extend GEO_001's namespace; no separate `political.*` carved). POL is intrinsic to geography substrate; mirrors GEO_001b's `authoring.*` carve-only-when-genuinely-separate discipline.
- **Cumulative outcome (post 2-pass /review-impl):**
  - GEO_002 POL_001 catalog established (24 entries; POL-1..POL-24); design surface declared end-to-end at ~745 lines (under 800 hard cap; +50 from /review-impl fixes); status DRAFT-WITH-FIX-CYCLE awaiting acceptance test integration (LOCK criterion: ≥15 of 21 AC-POL-1..21 pass against world-service POL reference impl).
  - **20 V1+30d rule_ids** added under shared `geography.*` namespace (15 from DRAFT + 5 from /review-impl 2nd-pass MED batch); total namespace count 13 V1 GEO_001 + 20 V1+30d POL_001 = 33 V1+30d when POL ships. `geography.layer_activation_deferred_v1` lifted for political layer specifically at POL ship.
  - `GeographyDeltaKind` closed-enum bump 5 V1 → 5 V1 + 4 V1+30d active + 1 V2+ reservation + 2 V2+ reservations new (CreateState/DestroyState per POL-D14). Per R3 additive — V1 readers reject unknown V1+30d variants gracefully via existing `geography.delta_kind_v1plus_inactive` reject path; V1+30d code lifts the gate at POL ship.
  - Capability addition: `can_edit_political_geography` JWT claim — Tier 1 ImpactClass=Destructive per S5; additive to existing `can_edit_geography`; one-shot migration auto-grants to all current `can_edit_geography` holders at POL ship (per MED-6 fix).
  - **CreativeSeed schema_version bumps 2 → 3** (per HIGH-1 fix) — POL_001 adds 3 additive fields (political_seed_mode + canonical_states + procedural_density) mirroring GEO_001b's 1→2 precedent for additive evolution. LLM authoring template version bumps v1.tmpl → v2.tmpl with CreativeSeed v3 schemars-generated JSON Schema.
  - 20 POL-V* validators (POL-V1..POL-V20) — 15 from DRAFT + 5 from /review-impl 2nd-pass MED batch (POL-V16..POL-V20 for set_culture_region_empty + split_partition_min_2 + transfer_self_target + canonical_mode_no_seeds + canonical_state_province_mismatch).
  - 21 V1+30d-testable acceptance scenarios AC-POL-1..21 — 15 from DRAFT + 6 from /review-impl 2nd-pass coverage batch (AC-POL-16..21 covering MED-1/3/4/8/9 rejects + LOW-2 island state).
  - 14 deferrals POL-D1..D14 — 12 from DRAFT + 2 from /review-impl batch (POL-D13 culture-aware procedural state naming per HIGH-4 + POL-D14 CreateState/DestroyState V2+ per MED-5).
  - No new aggregate; POL_001 populates GEO_001's existing `world_geometry` fields via pipeline stage 5/8 activation + 4 V1+30d DeltaKinds.

---

## 2026-05-14 — SPIKE_04 D-S04-1..5 approval batch (5 sub-decisions applied)

- **Lock CLAIMED + RELEASED** in single cycle (combined `[boundaries-lock-claim+release]` pattern).
- **Trigger:** SPIKE_04 GEO procgen + authoring validation (2026-05-13 commit `b25cfb92`) surfaced 5 sub-decisions D-S04-1..5 for user approval before V1 implementation phase. User picked option 1 = approve all 5 with recommended defaults. Apply now; commit.
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim → release (Owner reverted to None)
  - `02_extension_contracts.md` §1.4: `authoring.*` row updated — 8 V1 rule_ids → **10 V1 rule_ids** (D-S04-1 + D-S04-2 added; V1+ reservation count unchanged at 4)
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_geography/GEO_001b_authoring_flow.md`: §8 validation pipeline step 3 split into 3a/3b/3c (cap / uniqueness / cycle detection); §12 namespace count 8 V1 → 10 V1; §15 acceptance count 10 → 12 (AC-AUTHOR-11 + AC-AUTHOR-12 added); §16 deferrals adds GEO-AUTHOR-D11
  - `features/00_geography/GEO_001_world_geometry.md`: §5 pipeline determinism note extends D-S04-3 strict-IEEE compile flag discipline; §7 ContentSafetyGate annotation extends D-S04-4 scrub-regardless policy
- **Decisions applied:**
  1. **D-S04-1** (canonical_settlements + culture_hints name uniqueness) → reject duplicates via NEW `authoring.duplicate_canonical_name`. Validator step 3b runs case-sensitive LocalizedName.default-field match across canonical_settlements[].name + naming_style_ref uniqueness across culture_hints[]. LLM re-prompted with error context "remove duplicate" on retry.
  2. **D-S04-2** (SpatialPreference::NearSettlement cycle detection) → reject cycles via NEW `authoring.spatial_preference_cycle`. Validator step 3c builds DAG from NearSettlement references; DFS with white/gray/black coloring detects cycles (direct A↔B + indirect A→B→C→A). LLM re-prompted with error context "break cycle by anchoring one settlement to a non-NearSettlement preference".
  3. **D-S04-3** (floating-point determinism) → strict-IEEE mode V1 (`-ffp-contract=off` for C/C++ deps; Rust default IEEE-754 + `#[deny(clippy::float_arithmetic)]` outside generator module; NO SIMD-vectorized reductions). Fixed-point V1+ if drift surfaces in CI snapshot tests per SPIKE_04 GAP-S2.B. GEO_001 §5 pipeline determinism note extended.
  4. **D-S04-4** (admin Forge reason PII scrubbing) → scrub regardless of in-fiction context per existing §12X.L7 admin discipline. Named characters like "Tiểu Long Nữ" go through the same regex scrubber as personal data. Defense in depth. GEO_001 §7 ContentSafetyGate annotation extended.
  5. **D-S04-5** (`intended_producer` audit field on fallback) → V1+30d as new GEO-AUTHOR-D11 deferral. V1 records final producer only; V1+30d adds Option<AuthoringProducer> intended_producer field on AuthoringMetadata for audit fidelity when fallback fires (e.g., KnowledgeServiceExtracted V1 → LlmGenerated{grounding: None} on knowledge-service unavailable per AC-AUTHOR-10).
- **Cumulative outcome:**
  - 5 sub-decisions locked; 2 new V1 reject rule_ids (`authoring.duplicate_canonical_name` + `authoring.spatial_preference_cycle`); 1 new V1+30d deferral (GEO-AUTHOR-D11); 2 new acceptance scenarios (AC-AUTHOR-11 + AC-AUTHOR-12); 2 schema policy clarifications (strict-IEEE float + scrub-regardless PII)
  - **GEO_001 + GEO_001b schema is now ready for V1 implementation phase commitment.** The remaining MED-severity GAPs (S1.A schemars build pipeline + S2.A HashMap normalize + S2.B float determinism + S2.C canonical JSON + S2.D cross-platform + S3.E SettlementId blake3-derive + S4.K multi-continent fork orchestration) are all implementation-phase CI gates or build pipeline tasks — they don't require user-approval rounds but DO need to land in V1 impl phase as CI gates before any production reality bootstraps.
  - **Process lesson reinforced:** SPIKE_04 is the first design-track artifact that triggered a successful sub-decision approval round. Walk-through-validation → surface ambiguity → user-approval batch → apply → done. This is the maturity model for design-track decision-locking moving forward.

---

## 2026-05-13 — GEO_001b CreativeSeed Authoring Flow DRAFT + GEO_001 HookScope Option C bug fix (write-side cycle)

- **Lock CLAIMED + RELEASED** in single cycle (combined `[boundaries-lock-claim+release]` commit pattern).
- **Trigger:** user deep-discussion question "how do LLMs work in this geography generation? are we already define an in/out contract that LLM friendly?". Honest answer surfaced: GEO_001 defined post-pipeline READ contract (prompt-assembly grounding §6) well, but pre-pipeline WRITE contract (LLM produces CreativeSeed) was hand-waved with 7 gaps. User picked composite answer: **fix C** (HookScope bug fix in GEO_001 inline) + **do B** (new sibling GEO_001b for full LLM authoring contract). Best-of-both: immediate schema bug fixed + comprehensive write-side design as separate sibling per two-file split precedent (PL_001+001b / WA_002+002b).
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim → release (Owner reverted to None)
  - `01_feature_ownership_matrix.md`: `world_geometry` owner annotation extended with write-side cycle history (Option C HookScope bug fix + Option B GEO_001b sibling reference); cross-link to write-side contract
  - `02_extension_contracts.md`: §1.4 NEW `authoring.*` row (GEO_001b owner; 8 V1 rule_ids + 4 V1+ reservations); §2 RealityManifestGeographyExtension block extended with `authoring_metadata: Option<AuthoringMetadata>` + AuthoringProducer 5-variant comment + AuthoringMetadata struct shape + SpatialPreference 14-variant enum reservation + schema_version 1→2 migration plan
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_geography/GEO_001_world_geometry.md`: Option C HookScope bug fix — RegionalLoreHook.scope now uses PRE-materialization HookScope enum (SettlementByName/PositionRegion/Archetype + V1+ KnowledgeEntityRef reservation) instead of post-materialization GeoCellId/SettlementId/ProvinceId; AC-GEO-11 added verifying scope resolution; §15 acceptance count 10→11; forward reference to GEO_001b §6.5 + SpatialPreference V1+ migration note added (lines 738 → 748)
  - **NEW** `features/00_geography/GEO_001b_authoring_flow.md` (537 lines): write-side authoring contract; 19 sections; declares AuthoringProducer + SpatialPreference + AuthoringMetadata + AuthoringSession (BFF-held) + S9-registered LlmAuthoringTemplate + multi-turn iteration loop + validation pipeline + producer abstraction + RealityManifest extension + CreativeSeed schema_version 1→2 plan + `authoring.*` reject namespace + 10 V1-testable AC-AUTHOR-1..10
  - `features/00_geography/_index.md`: GEO_001b row added; folder now has 2 features (GEO_001 + GEO_001b)
  - `catalog/cat_00_GEO_geography_foundation.md`: 16 NEW catalog entries GEO-AUTHOR-1..GEO-AUTHOR-16 (AuthoringProducer / SpatialPreference / schema migration / S9 template / AuthoringMetadata / BFF session state / iteration loop / validation / namespace / RealityManifest extension / knowledge-service grounding V1+ / producer abstraction / AzgaarFmgJson V1+ / V1+30d enhancements / V2+ collaboration / V2+ position deprecation)

### 7 write-side gaps surfaced and resolved

| # | Gap | Resolution |
|---|---|---|
| 1 | **HookScope bug** (CHICKEN-AND-EGG) — RegionalLoreHook.scope used GeoCellId/SettlementId/ProvinceId, but those IDs don't exist at CreativeSeed-creation time (they materialize FROM CreativeSeed) | Option C fix inline in GEO_001 §6: new HookScope enum with SettlementByName(LocalizedName) + PositionRegion{center, radius} + Archetype variants; resolution happens post-stage-6 (settlements) and post-stage-1 (positions) |
| 2 | **LLM prompt template implicit** — S9 mandates every LLM call goes through a registered template; world authoring is an LLM intent we hadn't registered | GEO_001b §5: S9 template at `contracts/prompt/templates/world_authoring/v1.tmpl` with 8-section structure per §12Y.L3; CI fixtures per §12Y.L9 |
| 3 | **Schema-constrained generation not mandated** — without OpenAI structured outputs / vLLM grammar mode, LLM produces JSON that fails validators | GEO_001b §5.3: schema-constrained generation REQUIRED per V1 contract; creative_seed.v2.schema.json generated from Rust struct via schemars at build time |
| 4 | **Position fields ask LLM to do geometry (its weakness)** — `(f32, f32)` coords cluster, axis-align, fail | GEO_001b §4.2: SpatialPreference 14-variant closed enum (Northern/Coastal/Highland/NearBiome/NearCulture/NearSettlement/ExplicitPosition/Any); CreativeSeed.schema_version 1→2 additive migration; V1+ LLM-authored worlds use SpatialPreference, V1 Manual/Imported can use ExplicitPosition |
| 5 | **Multi-turn iteration loop undocumented** — author intent → LLM proposes → author edits → LLM regenerates → author approves had no contract | GEO_001b §7: BFF-held AuthoringSession with bounded N=10 iterations + N=3 retry per iteration + S6 cost cap inherited from S6-D2 + 24h session TTL; AuthorAction 4-variant (Accept/RejectAndRetry/EditManually/Cancel) |
| 6 | **knowledge-service grounding missing** — book canon should ground LLM output, not LLM hallucination | GEO_001b §6: KnowledgeGrounding struct + KnowledgeServiceExtracted producer V1 schema-reserved; V1+ activation when knowledge-service ships per CLAUDE.md `101_DATA_RE_ENGINEERING_PLAN.md`; [WORLD_CANON] section hydrated with ≤200 entities × ~30 tokens |
| 7 | **Non-LLM authoring not first-class** — manual form / import / knowledge-extracted treated as afterthoughts | GEO_001b §4.1 + §9: AuthoringProducer 5-variant (LlmGenerated V1 + AuthorManual V1 + Imported V1+ + KnowledgeServiceExtracted V1+ + Hybrid V1); producer abstraction means procgen pipeline doesn't care which producer made the CreativeSeed |

### Cumulative outcome

- **HookScope bug** (Option C) fixed inline; AC-GEO-11 added (now 11 acceptance scenarios in GEO_001).
- **GEO_001b sibling** (Option B) covers full LLM authoring contract — 537 lines; under 800 hard cap; comparable to MAP_001=714 / WA_003=798 sibling pattern.
- **CreativeSeed schema_version 1 → 2 additive migration** plan locked; V1 implementations stay valid; V1+ LLM-authored worlds use SpatialPreference; V2+ may deprecate position_normalized if uptake is universal.
- **No new aggregate introduced** — BFF-held UX state; per-iteration LLM cost in S6 user_cost_ledger; final accepted CreativeSeed durable record via existing GeographyBorn payload (additive `authoring_metadata` field per I14).
- **Producer abstraction** preserves V1 single-cell SPIKE_01 (uses AuthorManual; no LLM dependency) AND supports canon-faithful Tang/Song dynasty authoring (ExplicitPosition escape hatch) AND enables V1+ knowledge-service grounding without re-design.
- **Process lesson reinforced**: even after /review-impl fix cycle, deep-discussion surfaced a 7-gap write-side hole that the post-pipeline READ contract had masked. Read-contract correctness ≠ write-contract correctness. Both sides need independent governance discipline.

---

## 2026-05-13 — GEO_001 fix cycle (post-/review-impl adversarial pass; 11 issues resolved)

- **Lock CLAIMED + RELEASED** in single cycle (combined `[boundaries-lock-claim+release]` commit; mirrors prior DRAFT-cycle pattern). 2-hour TTL.
- **Trigger:** user invoked `/review-impl` after GEO_001 DRAFT POST-REVIEW signaled completion. Adversarial pass found 11 real issues that the POST-REVIEW had rubber-stamped: 3 HIGH (schema-correctness / validator-implementability / fork-correctness) + 5 MED (event taxonomy / boundary registration / algorithm gap / version contract / aggregate convention / closed-enum drift) + 3 LOW (invariant placement / field redundancy / struct-shape opacity). User picked Option A: fix all 11 now.
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim → release (Owner reverted to None)
  - `01_feature_ownership_matrix.md`: `world_geometry` row Tier×Scope updated to "T2/Channel (continent per MAP-2 ChannelTier per HIGH-2 fix)"; full 11-fix list appended to owner annotation; rule_id count updated 10→13 V1 + 4→3 V1+ reservations
  - `02_extension_contracts.md`: §1.4 `geography.*` row rewritten with 13 V1 rule_ids + fix-cycle change manifest; §4 EVT-T8 sub-shapes table gains `Forge:EditGeographyDelta { continent_channel_id, delta_kind, delta_payload, prev_delta_id }` row (MED-1 fix — the boundary registration gap /review-impl caught)
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_geography/GEO_001_world_geometry.md`: 11 fixes applied + 3 sequence sections compressed (lines 799 → 738; net -61 lines despite +26 lines of fix content because §14 sequence rewriting saved 63 lines)

### 11 fixes applied via /review-impl

| # | Severity | Concern | Fix landed |
|---|---|---|---|
| 1 | HIGH-1 | Post-`SetBiomeOverride` schema incoherence (biomes/river_flux/is_coast desync) | V1 admits **only land-↔-land transitions**; water↔land rejects new rule_id `geography.biome_override_water_transition_v1` (V1+ when full biome+water-network re-derivation lands per new GEO-D13). Land-↔-land deltas recompute `is_coast` + `river_flux` for affected neighborhood (≤12 cells; scope-bounded) — coherence guaranteed for post-delta `(biomes, river_flux, is_coast)` triple. |
| 2 | HIGH-2 | `channel.level_name == "continent"` validator unimplementable (free-form DP-Ch1 string) | §3 rule rewritten: `channel MUST satisfy MAP-2 ChannelTier::Continent (mapped from DP-Ch1 level_name per MAP_001 §3 enum)`. Explicit dependency on locked MAP-2 closed-enum prevents validator ambiguity across `level_name` string conventions. |
| 3 | HIGH-3 | `GeographyDelta.id` namespace ambiguity (breaks fork correctness if misread) | §3 rule added: `delta_id is monotonic PER world_geometry aggregate row` (per `(reality_id, continent_channel_id)`). Forks start fresh sequences from post-`GeographyForkInherited` `last_delta_event_id`; sibling realities' delta_id values may collide across rows without interaction. |
| 4 | MED-1 | `Forge:EditGeographyDelta` not registered in `_boundaries/02_extension_contracts.md` §4 EVT-T8 sub-shapes table | Row added to §4 table; the missing registration is now closed (this was the actual boundary-discipline gap that /review-impl caught). |
| 5 | MED-2 | `ForkGeographyInherit` wrong event category (claimed EVT-T8 Administrative with `Forge:` prefix but producer is DP-Internal SnapshotForker = system actor) | Reclassified EVT-T8 Administrative → EVT-T4 System; renamed `Forge:ForkGeographyInherit` → `GeographyForkInherited` (no `Forge:` prefix; lives in EVT-T4 sub-types registry alongside GeographyBorn, NOT §4). |
| 6 | MED-3 | Lake-vs-Ocean discrimination requires global topology (described local-only function in §5 stage 4) | Stage 4 split into 3 sub-stages 4a/4b/4c. **4a:** hydraulic erosion → river_flux. **4b:** water-network connected-components flood-fill from border water cells → `is_in_ocean_component` tag (Ocean) vs isolated water (Lake). **4c:** BiomeKind via `(climate, heightmap, river_flux, is_in_ocean_component, is_coast)` mapping function with explicit Ocean vs Lake discrimination. |
| 7 | MED-4 | `generator_pipeline_version` upcaster contract underspecified (silent migration risk) | §3 rule added: world_geometry row pinned to its `pipeline_version` at GeographyBorn for lifetime; mid-life upgrades **FORBIDDEN**; new realities adopt latest. R3 upcasters apply ONLY to additive `schema_version` field-shape evolution, never to algorithm versions. Upgrade attempts reject `geography.pipeline_version_mismatch` (promoted V1+ reservation → V1 active). |
| 8 | MED-5 | Aggregate-level `schema_version` field missing per I14 convention | Added `pub schema_version: u32` to WorldGeometry struct (V1 = 1). Distinct from `generator_pipeline_version` per fix #7. |
| 9 | MED-6 | `SetResourceOverride` in V1 enum but V2+ semantics (closed-enum discipline drift) | Dropped from V1 GeographyDeltaKind enum (6 V1 → 5 V1); moved to V1+ reservation alongside MergeProvinces/SplitProvince/etc. V1 Forge UI no longer surfaces SetResourceOverride as a choice. |
| 10 | LOW-1 | `GeoCellId == array-index` invariant documented in comment but not in §3 validator rules | §3 rule added: for all `i in 0..cells.len()`, `cells[i].id == GeoCellId(i as u32)`; out-of-order or sparse vectors reject new rule_id `geography.cell_id_index_violation`. Enforced at GeographyBorn + every delta apply touching cells. |
| 11 | LOW-2 | `applied_at_fiction_time` clock source ambiguous (TDIL composition) | Field DROPPED from GeographyDelta struct. Replay determinism doesn't need it — triggering EVT-T8 event already carries wall-time via S4 MetaWrite audit + continent fiction_clock at event_id. Comment in struct documents the drop. |
| 12 | LOW-3 | `RegionalLoreHook` / `NamingStyleDecl` / `CanonicalSettlementDecl` shapes opaque | All 3 structs declared in §6 (post-CultureHint block). `Settlement` struct gains `canon_ref: Option<BookCanonRef>` field — was being dropped on materialization from `CanonicalSettlementDecl.canon_ref`. |

### Cumulative outcome

- **Schema lock now genuinely lockable.** 3 HIGH issues that would have surfaced as V1 implementation bugs caught at design time.
- **Foundation tier boundary discipline restored.** MED-1 closed; §4 EVT-T8 sub-shapes registry is now the SSOT GEO_001 cites and writes to.
- **Strategy substrate readiness preserved.** V1+ POL_001 / SET_001 / ROUTE_001 / V2+ STRAT_001 still consume locked layers as read-only inputs — no migration regression introduced by fix cycle.
- **GEO_001 main doc** at 738 lines (was 799 pre-fix DRAFT); §14 sequence compression bought enough budget for 11 fixes + 3 new V1 rule_ids + 3 new struct declarations.
- **Process lesson reinforced (CLAUDE.md Phase 9 note):** POST-REVIEW signaled completion despite real architectural gaps; `/review-impl` did the work POST-REVIEW couldn't — author blindness persisted even with the "re-read from disk" ritual. POST-REVIEW + /review-impl are NOT redundant; they are distinct mental modes per the foundation discipline.

---

## 2026-05-13 — GEO_001 World Geometry Foundation DRAFT — new 7th foundation feature single-cycle claim+release

- **Lock CLAIMED + RELEASED** in single cycle (combined `[boundaries-lock-claim+release]` commit pattern; mirrors RES_001 + PROG_001 single-cycle closure precedent)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 4-hour TTL → reverted to None at end of cycle; _Last released_ entry with GEO_001 single-cycle summary
  - `01_feature_ownership_matrix.md`: new `world_geometry` aggregate row added under aggregate ownership section (line ~69 — appended at end before `---` Schema/envelope ownership separator); T2/Channel-continent scope; owner GEO_001
  - `02_extension_contracts.md`: §1.4 RejectReason namespace adds `geography.*` row (10 V1 rule_ids + 4 V1+ reservations); §2 RealityManifestSchema=1 extended with `continent_geometries: Vec<ContinentGeometryDecl>` OPTIONAL field + ContinentGeometryDecl + CreativeSeed + GeographyDelta comment block + downstream composition annotations
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_geography/GEO_001_world_geometry.md`: **NEW** 799-line DRAFT design doc (under 800-line soft cap; foundation-tier precedent comparable to MAP_001=714 lines)
  - `features/00_geography/_index.md`: **NEW** folder index documenting GEO_001 + future GEO_002..GEO_007 (POL_001 / SET_001 / ROUTE_001 / V2+ resource generator / multi-continent / author-supplied geometry mode) + 6-foundation-feature composition discipline
  - `catalog/cat_00_GEO_geography_foundation.md`: **NEW** catalog entry owning `GEO-*` namespace (`GEO-A*` axioms · `GEO-D*` deferrals · `GEO-Q*` open questions); 28 catalog entries (GEO-1..GEO-28) spanning V1 schema + V1 populated layers + V1+ generator activation + V2+ strategy substrate

### Phase 0 corrections applied during this cycle

Two findings during Phase 0 read-prep changed the planned placement:

1. **WA folder CLOSED for V1 design** (2026-04-25 closure pass). `features/02_world_authoring/_index.md` post-closure rules explicitly exclude multi-aggregate features and "designing the runtime mechanics here." Initial proposed placement `WA_007_world_map.md` retracted; WA is for thin per-reality config overrides (pvp_consent / voice_mode_lock / session_caps / etc.) — single aggregate, ~150-400 lines, mechanics elsewhere. Not the shape of a geometric substrate with internal layered structure.

2. **MAP_001 already exists** (CANDIDATE-LOCK 2026-04-26) in `features/00_map/`. Owns `map_layout` aggregate for visual UI graph layer (per-channel positions + image asset slots + navigable edges for node-link drill-down rendering, Tiên Nghịch / EVE Online / Stellaris pattern). MAP_001 is NOT the procedural geographic substrate — it's the visual rendering layer. The two compose without overlap: MAP_001 visual SSOT + GEO_001 geometric SSOT + PF_001 cell-semantic SSOT.

3. **Foundation tier (`00_*` folders) exists** post-SESSION_HANDOFF cutoff. 12 foundation feature folders (00_actor / 00_cell_scene / 00_entity / 00_faction / 00_family / 00_identity / 00_map / 00_place / 00_progression / 00_reputation / 00_resource / 00_titles) — GEO_001 joins this tier as the 7th foundation feature (after EF + PF + MAP + CSC + RES + PROG closed 2026-04-27).

User picked Option A from Phase 0 correction: new `00_geography/` foundation folder with `GEO-*` namespace.

### 7 sub-decisions LOCKED via single Phase 0 deep-dive

| ID | Decision | Rationale |
|---|---|---|
| **D1** | ChannelScoped at continent channel (NOT RealityScoped) | Matches DP-Ch1 channel hierarchy; multi-continent realities have multiple maps; archipelago + mainland + sky-island patterns need multiple meshes anyway |
| **D2** | Single `world_geometry` aggregate per continent with internal layered structure | One aggregate (geometry / climate / biome V1 populated + political / settlement / route / culture / resource V1 schema-reserved). Atomic regen of base; layer-level versioning via delta-overlay. Alternative (split into 3-4 aggregates) creates more boundary complexity + more joins for strategy queries |
| **D3** | Deterministic-base + delta-overlay editability (open question #2 from survey) | Base regenerates from `(seed, creative_seed, pipeline_version)` reproducibly; admin Forge canonization appends ordered `GeographyDelta`; replay = base + deltas. Genuinely novel work — no Azgaar-style tool does this V1. Alternative (destructive regenerate per Azgaar default) jitters every position on edit, breaks save state, loses canon edits |
| **D4** | Single Voronoi mesh with water-cell tags (open question #1 from survey) | Water cells flagged via heightmap < threshold OR biome ∈ {Ocean, Lake, River}; sea zones derived by clustering connected water cells; naval adjacency derived. Matches Azgaar. V2+ Paradox-style separate land/sea graphs with explicit straits tracked GEO-D6 if strategy gameplay needs explicit naval chokepoints |
| **D5** | Cells AND provinces (two-tier granularity) | ~10k Voronoi cells as raw geometry (terrain queries, scene placement, fine pathing); provinces are named cell-clusters with strategic role. Strategy queries on provinces; exploration / scene queries on cells. Both surfaces preserved |
| **D6** | Explicit FK from channel to map element | continent_channel.metadata.world_map_id; country_channel.metadata.state_id; district_channel.metadata.province_id; town_channel.metadata.burg_id. Map data references channel IDs back where bidirectional. Strategy queries `state.armies` join through this. Alternative (implicit name/position lookup) brittle under rename |
| **D7** | Inherit by reference, deltas don't cascade | Snapshot fork (MV6) copies `(seed, creative_seed, deltas_at_fork_point)`. New deltas in child reality stay local. Parent → child propagation only for L1/L2 canon updates (matches §M4 propagation pattern); same delta-overlay machinery as D3 handles this. Alternative (deep-copy on fork) doubles storage per fork |

### Strategy substrate readiness for future STRAT_001 V2+

V1 schema reserves ALL layers strategy needs (provinces / states / settlements / routes / culture / resources). V1+ POL_001 / SET_001 / ROUTE_001 generators activate fields via additive schema-stable / activation-deferred discipline (mirrors PO-A8 + PROG-A schema patterns). V2+ STRAT_001 consumes locked layers as read-only inputs — schema-frozen by V1 lock; no migration when strategy phase opens. **Pre-investment in strategy substrate without pre-implementation: pays compound interest at strategy phase entry.**

### Algorithmic baseline (world-map landscape survey 2026-05-13)

- **Patel dual-mesh** (Apache 2.0; `redblobgames.com/x/2312-dual-mesh/`) — Voronoi cell graph substrate; canonical reference; clean Rust port path
- **O'Leary "Generating fantasy maps"** (MIT; `mewo2.com/notes/terrain/`) — erosion + flux + river tracing + city scoring single-page algorithm
- **Azgaar Fantasy Map Generator algorithm blog** (MIT; `azgaar.wordpress.com/`) — Voronoi/heightmap/biomes/burgs/states/routes pipeline-by-pipeline write-up
- LLM-image-to-map approaches (arXiv 2407.09013 + 2410.15644 + AriGraph IJCAI 2025) REJECTED for strategy gameplay use — produce images not structured graphs; cannot back adjacency-correctness or regeneration-stability requirements

Survey confirmed: **nothing strictly better appeared 2024-2025**. The Patel/O'Leary/Azgaar 2010-2018 algorithm stack remains state-of-the-art for *structured* fantasy world geometry. GEO_001 §5 8-stage pipeline implements this baseline with V1 stages 1-4 substantive + V1+ stages 5-8 activation slots.

---

## 2026-04-27 — PO_001 Player Onboarding CANDIDATE-LOCK closure commit 4/4 — final lock release + cross-feature deferral RESOLVED annotations

- **Lock RELEASED** — 4-commit cycle complete (wireframes Phase 0 19855a5b + 4c4fd6d7 + Phase 0 backend kickoff 9245666c + DRAFT 2/4 4106410c + Phase 3 cleanup 3/4 f41077f4 + closure 4/4 this commit); single combined `[boundaries-lock-release]` commit
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner reverted to None; _Last released_ entry with full 4-commit cycle summary
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/03_player_onboarding/PO_001_player_onboarding.md`: status header DRAFT → CANDIDATE-LOCK; §14 Status section updated (Phase: CANDIDATE-LOCK; LOCK target after AC-PO-1..12 V1-testable scenarios + chat-service integration + auth-service email/password flow validated)
  - `features/03_player_onboarding/_index.md`: folder closure status COMPLETE; CANDIDATE-LOCK status row populated với full 4-commit chain
  - `features/06_pc_systems/PCS_001_pc_substrate.md`: PCS-D1 marked ✅ RESOLVED 2026-04-27 by PO_001 V1; PCS-D10 marked ✅ RESOLVED 2026-04-27 by PO_001 V1
  - `catalog/cat_06_PCS_pc_systems.md`: PCS-D1 + PCS-D10 rows updated với V1 RESOLVED annotation

### Cross-feature deferrals RESOLVED at this commit

| Deferral | Source | Resolution |
|---|---|---|
| **PCS-D1** ✅ FULL V1 | PCS_001 PC Substrate | V1+ runtime login flow PC creation → PO_001 V1 RESOLVES via Forge:CompleteOnboarding orchestrating Forge:RegisterPc + Forge:BindPcUser cascade through 14-feature chain per PO-C1 |
| **PCS-D10** ✅ FULL V1 | PCS_001 PC Substrate | V1+ PO_001 Player Onboarding integration → PO_001 V1 RESOLVES via 3-mode UI flow (Mode A Canonical PC + Mode B Custom 8-step + Advanced + AI Assistant + Mode C Xuyên Không Arrival) consuming PCS_001 primitives |

### PO_001 4-commit cycle summary

| # | Commit | What |
|---|---|---|
| 0a/4 | 19855a5b Wireframes Phase 0 | FE-first HTML mockup — 8 main screens (landing/reality select/path choice/3 modes/confirm/first turn) + shared wuxia ink-wash + reality-themed accent CSS + index navigation hub |
| 0b/4 | 4c4fd6d7 Wireframes Power-User Mode | Advanced Settings (~46 V1 fields edit grid) + AI Character Assistant full-screen modal + ACTOR_SETTINGS_AUDIT.md inventory + Mode B 3-level UX integration |
| 1/4 | 9245666c Phase 0 backend kickoff | concept notes (~428 lines; user framing + worked examples + 14-feature integration audit + Q1-Q10 with pre-recommendations) + reference survey (~309 lines; 9-system formalized: BG3 PRIMARY + Cyberpunk + Disco Elysium + AI Dungeon + NovelAI + FFXIV + Lost Ark + Pathfinder + Persona) + folder _index.md update |
| 2/4 | 4106410c DRAFT | PO_001_player_onboarding.md spec ~862 lines + cat_03_PO_player_onboarding.md catalog seed (8 axioms PO-A1..A8 + 24 V1 entries PO-1..PO-24 + 12 V1+/V2/V2+ entries PO-25..PO-36 + 12 deferrals PO-D1..D12 + 6 cross-aggregate consistency rules PO-C1..C6) + boundary updates (01_feature_ownership_matrix.md actor_user_session aggregate row + RejectReason namespace + PO-* stable-ID prefix; 02_extension_contracts.md §1.4 onboarding.* namespace + §2 RealityManifest 2 OPTIONAL V1 extensions) + 99_changelog.md DRAFT entry + concept notes Q-LOCKED matrix + _index.md status update + `[boundaries-lock-claim]` |
| 3/4 | f41077f4 Phase 3 cleanup | Validator pipeline slots PO-C1..C6 / C30-C35 registration (NEW namespace row + 6 cross-aggregate consistency rules; total V1 reject rules count 154 → 161; C30 is SECOND RUNTIME cascade C-rule post P4 commit). Zero drift detected — spec internally consistent. Lock STAYS CLAIMED. |
| 4/4 | (this commit) closure | Status DRAFT → CANDIDATE-LOCK; cross-feature RESOLVED annotations on PCS-D1 + PCS-D10 (PCS_001 spec + catalog); folder _index.md COMPLETE; lock RELEASED via `[boundaries-lock-release]`. |

### V1 Summary

- **1 NEW sparse aggregate** — actor_user_session (T2/Reality, sparse per-(actor, session))
- **2 RealityManifest extensions** — onboarding_config + canonical_pcs ref list (both OPTIONAL V1)
- **5 new event sub-types** — 3 EVT-T8 (CompleteOnboarding V1 active + 2 V1+30d schema) + 1 EVT-T1 (OnboardingCompleted) + 1 EVT-T3 (OnboardingDraftUpdated V1+30d)
- **6 cross-aggregate consistency rules** PO-C1..C6 (global C30-C35; C30 RUNTIME cascade unique pattern)
- **8 axioms** PO-A1..A8
- **12 V1 acceptance scenarios** AC-PO-1..12 + 4 V1+ deferred
- **12 deferrals** PO-D1..D12
- **PO-* stable-ID prefix**

### Discipline observed across 4-commit cycle

- **FE-first design discipline (PO-A1)** — UX validated via wireframes Phase 0 (12 files HTML/CSS/MD) BEFORE backend feature spec; user direction "thiết kế FE trước - thảo luận FE sau đó chúng ta quyết định draft html trước khi đi sâu vào thiết kế tính năng" honored
- **Per-reality author-declared discipline (PO-A6)** — mirrors PROG-A1 + REP_001 + FAC_001 + TIT_001 author-discipline
- **3-mode onboarding architecture (PO-A2)** — Canonical (BG3 Origin) + Custom (BG3 + Cyberpunk lifepath) + XuyenKhong (Disco Elysium amnesia + wuxia)
- **3-level Mode B UX progression (PO-A3)** — Basic Wizard + Advanced Settings + AI Character Assistant
- **AI Character Assistant V1 active (PO-A4)** — chat-service + LiteLLM + knowledge-service constraint awareness
- **PC creation cascade orchestration (PO-A5 + PO-C1)** — synchronous 14-feature chain on Forge:CompleteOnboarding same turn (joins existing C1-C29 + C30-C35 = 35 cross-aggregate consistency rules total post this commit)
- **Schema-stable / activation-deferred V1+ discipline (PO-A8)** — mirrors TIT-A8 + REP_001 deferred-validator pattern
- **3-write atomic Forge admin pattern reused** (consistent with WA_003 / FAC_001 / REP_001 / ACT_001 / PCS_001 / TIT_001 / DF05_001 prior)
- **No new substrate required** — V1 consumes 14 locked features as DECLARATIVE inputs

### V1 unchanged for other features

This commit is purely additive per I14 invariant. Pure documentation closure annotations + status promotion. No changes to existing aggregates / EVT sub-shapes / RealityManifest fields owned by other features (beyond marking PCS-D1 + PCS-D10 RESOLVED). PROG_001 / RES_001 / IDF_001..005 / FF_001 / FAC_001 / REP_001 / TIT_001 / ACT_001 / PCS_001 / AIT_001 / TDIL_001 / DF05_001 status unchanged.

### CANDIDATE-LOCK → LOCK gate

PO_001 transitions to LOCK when:
- AC-PO-1..12 V1-testable scenarios pass integration tests against Wuxia + Modern + D&D reality fixtures
- chat-service integration validated (AI Character Assistant LLM calls succeed; constraint awareness verified)
- auth-service email/password flow validated (account creation + JWT issuance + onboarding flow E2E)
- Forge:CompleteOnboarding 14-feature cascade validated (14 events emit correctly same turn; OnboardingCompleted EVT-T1 reaches LLM scene narration)

### NEW priority candidates post PO_001 CANDIDATE-LOCK

| Candidate | Justification |
|---|---|
| **DIPL_001 Diplomacy Foundation V2+** | Inter-faction politics; consumes FAC + REP + V1+ FactionElect TIT-D1 |
| **AI-controls-PC-offline activation** | Cross-ref ACT-D1; chorus_metadata sparse PC V1+ activation |
| **DRAFT closure passes for remaining DRAFT features** | Promote DRAFT → CANDIDATE-LOCK; resolve §20.2 deferred follow-ups |
| **SPIKE_01 turn 5 integration test design** | First end-to-end turn pipeline test; validates 6 foundations + 9 Tier 5 substrate + DF05 + PO_001 = 17 features integrated |
| **V1+30d milestone batch** | REP-D1 runtime reputation milestone activates TIT-D2 + REP-D9 + PO-D3 (auto-save) simultaneously |
| **V1+30d implementation phase** | Begin actual coding (services scaffold + frontend implementation following wireframes) |

User to pick next priority post this commit.

---

## 2026-04-27 — PO_001 Phase 3 cleanup commit 3/4 — validator pipeline slots PO-C1..C6 / C30-C35 registration

- **Lock STAYS CLAIMED** — Phase 3 cleanup commit; release at closure 4/4 commit
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: lock claim active (no claim/release change this commit)
  - `03_validator_pipeline_slots.md`:
    - **NEW row** in §"Tier 5 Actor Substrate namespaces" — onboarding.* (7 V1 + 5 V1+ reservations)
    - Total V1 reject rules count updated: 154 → 161 (added 7 PO rules)
    - **NEW 6 rows** in §"Stage 0 canonical seed cross-aggregate consistency rules" — C30 (PO-C1) RUNTIME PC creation cascade orchestration + C31-C35 (PO-C2..C6) canonical seed bootstrap-time validators
  - `99_changelog.md`: this entry top-anchored

### Phase 3 self-review verdict

**Zero drift detected** in PO_001 spec post DRAFT 2/4 commit `4106410c`:
- AC count: §1 declares "12 V1 testable acceptance scenarios" → §10 has exactly 12 (AC-PO-1..12) ✓
- Reject rule count: §1 declares "7 V1 + 5 V1+ reservations" → §8.1 has 7 V1 rules + §8.2 has 5 V1+ reservations ✓
- Catalog entries: catalog declares "24 V1 catalog entries" → §11 V1 Minimum Delivery Summary matches ✓
- Cross-feature deferrals: §1 + §13.1 + catalog §coordination notes consistent on PCS-D1 + PCS-D10 (full V1 RESOLVES) ✓

No pseudocode reject rules referenced outside §8.1 V1 list (unlike TIT_001 Phase 3 which had 2 missing rules). PO_001 spec internally consistent at DRAFT 2/4 commit time.

### Validator pipeline slots boundary doc updated

Following established TIT_001 + DF05_001 Phase 3 pattern, PO_001 V1 cross-aggregate consistency rules registered in `03_validator_pipeline_slots.md`:

**RUNTIME cascade rule added (C30; second runtime cascade C-rule post P4 commit; first was C18 TIT-C1):**
- **C30 (PO-C1)**: PC creation cascade orchestration. Forge:CompleteOnboarding EVT-T8 triggers synchronous 14-feature chain same turn (PCS_001 → ACT_001 → EF_001 → IDF_001..005 → FF_001 → FAC_001 → REP_001 → TIT_001 V1+ → PROG_001 → RES_001 → TDIL_001 → SR11 → emit OnboardingCompleted EVT-T1). No reject; cascade applies all events atomically; per-feature reject rules fire if individual stage validation fails.

**Stage 0 canonical seed bootstrap rules added (C31-C35; mirror prior C2-C29 patterns):**
- **C31 (PO-C2)**: OnboardingConfigDecl.canonical_pcs subset of canonical_actors[kind=Pc] at RealityManifest bootstrap
- **C32 (PO-C3)**: OnboardingConfigDecl.default_spawn_cell ∈ RealityManifest.places (cell-tier)
- **C33 (PO-C4)**: Mode B/C draft_data per-feature schema validation (delegates to per-feature validators across 11 fields)
- **C34 (PO-C5)**: PC cap=1 V1 per actor_user_session.user_id (matches PCS-C13)
- **C35 (PO-C6)**: Mode A canonical PC binding — actor.user_id_init must be None at bind time

C30 is RUNTIME (every Forge:CompleteOnboarding admin event), unlike C31-C35 (canonical seed bootstrap). Joins existing C18 (TIT-C1) as second runtime cascade C-rule registered post P4 commit.

### Impact summary

- 7 V1 reject rules in onboarding.* namespace (no count change from DRAFT 2/4)
- Total V1 reject rules across engine: 161 (was 154; added 7 PO rules)
- 6 new cross-aggregate consistency rules in `03_validator_pipeline_slots.md` (C30-C35; total now 35 rules)
- All PO_001 spec/catalog/boundary docs internally consistent post Phase 3

### V1 unchanged for other features

This commit is purely additive per I14 invariant. Pure validator pipeline slots registration. No changes to existing aggregates / EVT sub-shapes / RealityManifest fields owned by other features.

### Next steps

- **Commit 4/4 CANDIDATE-LOCK closure**: status DRAFT → CANDIDATE-LOCK + cross-feature RESOLVED annotations on PCS-D1 + PCS-D10 source docs (PCS_001 spec + catalog) + folder _index.md COMPLETE + `[boundaries-lock-release]`

---

## 2026-04-27 — PO_001 Player Onboarding DRAFT 2/4 — first user-visible feature post-foundation closure (single `[boundaries-lock-claim]` commit; release at closure 4/4)

- **Lock CLAIMED** — PO_001 DRAFT 2/4 commit; release at closure 4/4 commit per established 4-commit cycle (wireframes Phase 0 + Phase 0 backend kickoff + DRAFT 2/4 + Phase 3 + closure)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim active
  - `01_feature_ownership_matrix.md`:
    - **NEW row** — `actor_user_session` aggregate (T2/Reality, sparse per-(actor, session)); registers PO-A1..A8 axioms summary + Q1-Q10 LOCKED + 3-mode architecture + 3-level UX progression Mode B + AI Character Assistant V1 active + 14-feature cascade orchestration PO-C1 + cross-feature deferral resolutions (PCS-D1 + PCS-D10)
    - **RejectReason namespace registry** — added `onboarding.*` → PO_001
    - **Stable-ID prefix ownership** — added `PO-*` row (first user-visible feature post-foundation closure)
  - `02_extension_contracts.md`:
    - **§1.4 onboarding.* namespace** — 7 V1 reject rule_ids (reality_unauthorized + mode_unsupported + draft_invalid + pc_cap_exceeded + canonical_pc_unavailable + spawn_cell_unauthorized + user_already_has_pc) + 5 V1+ reservations (draft_resume_failed / oauth_provider_invalid / ai_assistant_unavailable / tutorial_step_invalid / cross_reality_migration_unsupported_v1); all Q1-Q10 LOCKED matrix summary
    - **§2 RealityManifest extensions** — 2 OPTIONAL V1 fields: `onboarding_config: Option<OnboardingConfigDecl>` + `canonical_pcs: Vec<ActorRef>` (subset of canonical_actors[kind=Pc]); full OnboardingConfigDecl shape documented (modes_enabled 3-variant + canonical_pcs ref list + ai_assistant_enabled bool + default_spawn_cell + V1+ schema-reserved onboarding_skin + tutorial_steps)
  - `99_changelog.md`: this entry top-anchored
- **Files created/modified outside `_boundaries/`:**
  - `features/03_player_onboarding/PO_001_player_onboarding.md` (NEW; ~700 lines): full spec — §1 Purpose & V1 minimum scope + §2 Domain concepts (OnboardingConfigDecl + actor_user_session + 14-feature cascade pseudocode + AI Assistant flow) + §3 Aggregates + §4 RealityManifest extensions + §5 Events (T8/T1/T3) + §6 AI Character Assistant + §7 Cross-aggregate validator (PC creation cascade) + §8 V1 reject rules + §9 Sequence diagrams (3 modes — Canonical + Custom + XuyenKhong) + §10 Acceptance Criteria (12 V1 + 4 V1+ deferred) + §11 V1 Minimum Delivery Summary + §12 Deferrals Catalog (PO-D1..D12) + §13 Cross-references + §14 Status
  - `catalog/cat_03_PO_player_onboarding.md` REPLACED (legacy archived multiverse content from `FEATURE_CATALOG.ARCHIVED.md` superseded by new PO_001 design): 8 axioms PO-A1..A8 + 24 V1 catalog entries (PO-1..PO-24) + 12 V1+/V2/V2+ entries (PO-25..PO-36) + 12 deferrals (PO-D1..PO-D12) + 6 cross-aggregate consistency rules (PO-C1..PO-C6) + cross-feature integration map covering 14 features
  - `features/03_player_onboarding/_index.md`: status row update CONCEPT → DRAFT
  - `features/03_player_onboarding/00_CONCEPT_NOTES.md`: status header update Q-LOCKED 2026-04-27; §10 Q-LOCKED matrix populated with all 10 LOCKED decisions zero revisions

### Background

User-driven 4-batch Q-deep-dive 2026-04-27 LOCKED all 10 critical scope questions zero revisions:

- **Batch 1/4 Q1+Q2+Q3** (mode architecture + AI Assistant timing): Q1 A 3 modes V1 (Canonical+Custom+XuyenKhong) / Q2 A 3-level Custom PC (Basic+Advanced+AI Assistant) / Q3 A AI Assistant V1 active (chat-service+knowledge-service)
- **Batch 2/4 Q4+Q5+Q6** (account + multi-PC + reality switcher): Q4 A email+password V1; OAuth V1+ / Q5 A cap=1 V1 per PCS-A9 LOCKED / Q6 A locked-in per session V1; mid-session V2+
- **Batch 3/4 Q7+Q8** (persistence + device support): Q7 A all-or-nothing V1; auto-save V1+30d / Q8 A desktop-only V1; mobile V1+30d
- **Batch 4/4 Q9+Q10** (first turn + tutorial): Q9 A immediate spawn cell drop-in / Q10 A inline tooltips minimal V1; richer tutorial V1+30d

FE-first approach validated UX direction via wireframes Phase 0 commits (19855a5b + 4c4fd6d7) BEFORE backend feature spec — 12 HTML/CSS/MD files demonstrating concrete UI; 46 V1 actor settings audited across 14 features.

### Cross-feature deferrals RESOLVED post PO_001 CANDIDATE-LOCK (closure 4/4)

- **PCS-D1** (PCS_001): V1+ runtime login flow PC creation → V1 RESOLVES (full active via Forge:CompleteOnboarding orchestrating Forge:RegisterPc + Forge:BindPcUser cascade)
- **PCS-D10** (PCS_001): V1+ PO_001 Player Onboarding integration → V1 RESOLVES (full active via 14-feature cascade orchestration PO-C1)

### V1 minimum delivery summary

- **1 NEW sparse aggregate** — actor_user_session (T2/Reality, sparse per-(actor, session))
- **2 RealityManifest extensions** — onboarding_config (OPTIONAL V1) + canonical_pcs ref list
- **3 EVT-T8 sub-shapes** — Forge:CompleteOnboarding (V1 active) + Forge:CreateOnboardingDraft + Forge:UpdateOnboardingDraft (V1 schema-reserved; V1+30d active per PO-D3)
- **1 EVT-T1** — OnboardingCompleted narrative milestone (LLM scene narration context)
- **1 EVT-T3** — OnboardingDraftUpdated (V1 schema-reserved; V1+30d active per PO-D3)
- **1 cross-aggregate validator PO-C1** (PC creation cascade orchestration; synchronous 14-feature chain on Forge:CompleteOnboarding) + 5 schema validators PO-C2..C6
- **7 V1 reject rules** in `onboarding.*` namespace + 5 V1+ reservations
- **12 V1 acceptance scenarios** AC-PO-1..12 + 4 V1+ deferred
- **12 deferrals** (PO-D1..D12)
- **PO-* stable-ID prefix**

### V1 unchanged for other features

This commit is purely additive per I14 invariant. No changes to existing aggregates / EVT sub-shapes / RealityManifest fields owned by other features. PROG_001 / RES_001 / IDF_001..005 / FF_001 / FAC_001 / REP_001 / TIT_001 / ACT_001 / PCS_001 / AIT_001 / TDIL_001 / DF05_001 status unchanged.

### Discipline observed

- **FE-first design discipline (PO-A1)** — UX validated via wireframes BEFORE backend spec
- **Per-reality author-declared discipline (PO-A6)** — mirrors PROG-A1 + REP_001 + FAC_001 author-discipline
- **3-mode onboarding architecture (PO-A2)** — Canonical (BG3 Origin) + Custom (BG3 + Cyberpunk lifepath) + XuyenKhong (Disco Elysium amnesia + wuxia)
- **3-level Mode B UX progression (PO-A3)** — Basic Wizard + Advanced Settings + AI Character Assistant
- **AI Character Assistant V1 active (PO-A4)** — chat-service + LiteLLM + knowledge-service constraint awareness
- **PC creation cascade orchestration (PO-A5 + PO-C1)** — synchronous 14-feature chain on Forge:CompleteOnboarding same turn (joins existing C1-C29 cross-aggregate consistency rules from prior commits)
- **Schema-stable / activation-deferred V1+ discipline (PO-A8)** — actor_user_session.onboarding_draft + 2 EVT-T8 sub-shapes schema-reserved V1
- **3-write atomic Forge admin pattern reused** (consistent with WA_003 / FAC_001 / REP_001 / ACT_001 / PCS_001 / TIT_001 prior)
- **No new substrate required** — V1 consumes 14 locked features as DECLARATIVE inputs

### Next steps

- **Commit 3/4 Phase 3 cleanup**: self-review fixes + downstream coordination notes + validator pipeline slots PO-C1..C6 / C30-C35 registration
- **Commit 4/4 CANDIDATE-LOCK closure**: final lock + RESOLVES PCS-D1 + PCS-D10 declarations + `[boundaries-lock-release]`

---

## 2026-04-27 — RES_001 Resource Foundation CANDIDATE-LOCK closure pass (FOUNDATION TIER 6/6 COMPLETE)

- **Lock CLAIMED + RELEASED** — single combined `[boundaries-lock-claim+release]` commit. DRAFT 2026-04-26 → TDIL closure-pass-extension Q4 day-boundary → turn-boundary semantic applied at TDIL DRAFT `bdc8d8e1` → CANDIDATE-LOCK closure pass (this commit).
- **Phase 3 + AC walkthrough:** §14 AC-RES-1..10 walked; all 10 V1-testable acceptance scenarios concrete + verifiable; no drift detected post-TDIL closure-pass-extension.
- **6 open questions RESOLVED at closure as deferrals to consumer feature closures:**
  - **RES-Q1** (Default vital_pool VitalProfile per-actor-class) → deferred to **PCS_001 + NPC_001 first-design-pass**; PCS_001 already CANDIDATE-LOCK 2026-04-27 `af025ebb`; NPC_001 CANDIDATE-LOCK; both consume `vital_pool` aggregate via standard pattern.
  - **RES-Q2** (Cell stockpile overflow handling) → drop (production halts at cap per Q4 + Q2c LOCKED); user-facing I18nBundle message `cell_production_halted_storage_full` with default English `"storage full, production paused"` + Vietnamese translation `"kho đầy, sản xuất tạm dừng"`.
  - **RES-Q3** (Trade reciprocity Give-kind vs dedicated Trade kind) → deferred to **PL_005 closure pass**; PL_005 owns interaction-kind ontology; RES_001 V1 OutputDecl pattern supports both (schema-additive either way).
  - **RES-Q4** (food-priority determinism) → V1 default author-declared `consumable_priority` (RealityManifest extension OPTIONAL); fallback to declaration-order in `resource_kinds` if author empty. Deterministic per replay-determinism invariant.
  - **RES-Q5** (i18n cross-cutting audit timing) → deferred to **i18n cross-cutting commit** (engine-wide migration); RES_001 V1 introduces I18nBundle pattern locally per §2; existing Vietnamese hardcoded reject copy V1 functional + cosmetic-only migration.
  - **RES-Q6** (`social_initial_distribution` PC vs NPC scope) → PC + NPC both (HashMap<ActorRef, i64> covers both, no schema change); PC starting Reputation default = 0. REP_001 CANDIDATE-LOCK 2026-04-27 owns PC reputation runtime gating V1+.
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None; full closure summary in _Last released_ entry
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_resource/RES_001_resource_foundation.md`: status header DRAFT 2026-04-26 → CANDIDATE-LOCK 2026-04-27 with closure pass rationale + RES-Q1..Q6 marked RESOLVED + §18 Status block updated
  - `features/00_resource/_index.md`: Active RES_001 DRAFT → empty (folder closure 2026-04-27); folder closure status Open → COMPLETE 2026-04-27 with foundation tier 6/6 confirmation

### RES_001 final summary

- **Status:** CANDIDATE-LOCK 2026-04-27
- **Foundation tier 6/6 COMPLETE** — RES_001 was the final DRAFT foundation feature; with this closure: EF + PF + MAP + CSC + RES + PROG all CANDIDATE-LOCK 2026-04-27
- **Substrate:** value flow through entities (HP/Stamina/lương thực, currency, materials, items, cell-production, town-economy, trade) — simulation/strategy core enabler
- **5 ResourceKind categories V1:** Vital / Consumable / Currency / Material / SocialCurrency (V1+30d Item / V2 Recipe / V3 Knowledge+Influence reserved)
- **2 aggregates:** `vital_pool` (T2/Reality, body-bound, actor-only, NON-TRANSFERABLE) + `resource_inventory` (T2/Reality, portable, EntityRef-any)
- **3 V1 sinks:** food consumption + cell maintenance cost + trade buy-sell spread
- **4 V1 Generators (per TDIL closure-pass-extension shifted to per-turn fire):** CellProduction (channel-bound) + NPCAutoCollect (channel-bound; V1+30d lazy migration via PROG-D19) + CellMaintenance (channel-bound) + HungerTick (actor-bound; reads body_clock per BodyOrSoul)
- **Reject rule_ids:** 12 V1 in `resource.*` namespace + V1+ reservations
- **RealityManifest extensions:** 9 OPTIONAL V1 (all engine-defaulted; sandbox/freeplay valid with empty default)
- **i18n cross-cutting pattern introduced:** English `snake_case` stable IDs + `I18nBundle` user-facing strings (engine-wide standard); RejectReason envelope extended with `user_message: I18nBundle` field (NEW contract §2.3)
- **Acceptance criteria:** 10 V1-testable AC-RES-1..10
- **Deferrals:** 27 across V1+30d/V2/V3 (RES-D1..D27)

### Cross-feature closure-pass-extensions applied (history)

| Source | Effect on RES_001 | When |
|---|---|---|
| TDIL_001 DRAFT promotion (`bdc8d8e1`) | Q4 4-Generator day-boundary → per-turn fire elapsed-time parameter; channel-bound vs actor-bound clock-source matrix per TDIL-A4 (CellProduction/NPCAutoCollect/CellMaintenance read channel `wall_clock`; HungerTick reads actor `body_clock`); cross-realm production correctly handled by elapsed-time multiplication; PROG-D19 NPC eager auto-collect → lazy migration V1+30d preserved | 2026-04-27 (DRAFT phase mechanical revision) |

### Downstream impacts §17.2 status

Most §17.2 downstream items already applied via subsequent closure-pass commits before RES_001 CANDIDATE-LOCK:

| Feature | Update applied | Status |
|---|---|---|
| PL_006 | Hungry V1 promotion + magnitude semantics 1/4/7 thresholds | ✅ applied via subsequent closure |
| WA_006 | §6.5 MortalityCauseKind catalog with `Starvation` | ✅ applied via subsequent closure |
| PL_005 | §9.1 harvest sub-intent + trade flow registration | ✅ applied via subsequent closure |
| EF_001 | §3.1 cell_owner + inventory_cap + EntityRef fields | ✅ applied via subsequent closure |
| PCS_001 | brief §4.4f + §S8 xuyên không body-substitution | ✅ applied via PCS_001 CANDIDATE-LOCK `af025ebb` |
| 07_event_model | 4 EVT-T5 + 2 EVT-T3 RES_001 sub-types registered | ✅ applied via subsequent commits |
| WA_003 Forge | 4 AdminAction sub-shapes (EditCellProducerProfile + EditPriceDecl + EditCellMaintenanceCost + GrantInitialResources) | 🟡 partial — V1+30d follow-on |
| NPC_001 | NPC owner auto-collect Generator + NPC consumption tick + VitalProfile NPC-class declarations | 🟡 partial — V1+30d follow-on |
| PL_001 Continuum | RejectReason.user_message: I18nBundle field per §2.3 | 🟡 partial — i18n cross-cutting commit |
| i18n cross-cutting audit | Migrate existing Vietnamese hardcoded reject copy to I18nBundle | 🟡 deferred to dedicated cross-cutting commit |

### NEW priority candidates post RES closure (FOUNDATION TIER COMPLETE)

1. **PO_001 Player Onboarding** — V1-blocking; Phase 0 wireframes committed `19855a5b` + `4c4fd6d7`; concept-notes + Q-deep-dive pending
2. **DF5 implementation scaffold** — `contracts/api/session/v1/` (~600 LoC traits + DTOs + ContractTestSuite ~30 scenarios) + `services/session-service/src/adapters/lru_distill.rs` LruDistillProvider V1 backend
3. **SPIKE_01 turn 5 integration test design** — DF5 + TDIL + AIT + PROG + RES all CANDIDATE-LOCK now (foundation + architecture-scale all closed); can validate full V1 vertical slice in concrete scenario
4. **V1+30d milestone activations across foundations** — RES-D1..D5 (PC inventory cap + decay/spoilage RES_002 + per-cell price variance + equipment wear + hydration loop) + PROG-D1..D5 (cultivation method declarations + Item ActorRef as progression owner + cross-reality stat translation rules + atrophy + offline mode)
5. **i18n cross-cutting commit** — engine-wide migration of Vietnamese hardcoded reject copy to I18nBundle pattern (PL_006 / NPC_001 / NPC_002 / PL_002 / WA_*); cosmetic; doesn't block V1 functionality

### Foundation tier closure status

- ✅ EF_001 Entity Foundation — CANDIDATE-LOCK
- ✅ PF_001 Place Foundation — CANDIDATE-LOCK
- ✅ MAP_001 Map Foundation — CANDIDATE-LOCK
- ✅ CSC_001 Cell Scene Composition — CANDIDATE-LOCK
- ✅ RES_001 Resource Foundation — **CANDIDATE-LOCK 2026-04-27 (THIS commit)**
- ✅ PROG_001 Progression Foundation — CANDIDATE-LOCK 2026-04-27 (`15d20036`; just preceded)

### Architecture-scale tier closure status (companion summary)

- ✅ ACT_001 Actor Foundation — CANDIDATE-LOCK 2026-04-27
- ✅ AIT_001 AI Tier Foundation — CANDIDATE-LOCK 2026-04-27
- ✅ TDIL_001 Time Dilation Foundation — CANDIDATE-LOCK 2026-04-27

**🎉 V1 substrate tier (foundation 6/6 + architecture-scale 3/3) closure COMPLETE 2026-04-27.** Next priority: PO_001 Player Onboarding (V1-blocking UI flow consuming all 9 substrate features).

---

## 2026-04-27 — PROG_001 Progression Foundation CANDIDATE-LOCK closure pass

- **Lock CLAIMED + RELEASED** — single combined `[boundaries-lock-claim+release]` commit. DRAFT 2026-04-26 → 5 NEW deferrals D33..D37 cross-cultivation extensibility audit `b20c4dcb` → CULT_001 V2+ entirely deferred `d57fb7fc` → TDIL closure-pass-extension Q3f day-boundary → turn-boundary semantic applied at TDIL DRAFT `bdc8d8e1` → CANDIDATE-LOCK closure pass (this commit).
- **Phase 3 + AC walkthrough:** §16 AC-PROG-1..12 walked; all 12 V1-testable acceptance scenarios concrete + verifiable; no drift detected post-cross-cultivation extensibility audit.
- **5 open questions RESOLVED at closure as deferrals to consumer feature closures:**
  - **PROG-Q1** (initial schema authoring touchpoint — CanonicalActorDecl vs separate per-actor file?) → deferred to **PCS_001 + NPC_001 first-design-pass** (consumer features own seed-time authoring UX); PROG_001 V1 schema-stable for both patterns.
  - **PROG-Q2** (eager Generator vs offline mode for inactive realm cultivation) → V1 default eager Generator per-turn (TDIL-A3); V1+30d offline mode `OfflineCultivationMode` enum on RealityManifest deferred (cap on accumulated turns + LLM summary on first observation).
  - **PROG-Q3** (BodyOrSoul auto-derivation from kind name vs author-mapping) → V1 auto-derive (heuristic: kind name contains "soul/qi/spiritual/cultivation/dao" → Soul; otherwise Body); V1+30d `BodyOrSoulOverride` field on ProgressionKindDecl deferred for author explicit control.
  - **PROG-Q4** (i18n bundle ownership — PROG_001 vs cross-cutting commit?) → deferred to **i18n cross-cutting feature closure** (engine-wide commit; PROG_001 V1 uses I18nBundle pattern locally per RES_001 precedent; future cross-cutting refactor schema-additive).
  - **PROG-Q5** (Tier discriminator on actor_progression vs separate aggregate ownership) → deferred to **future AI Tier feature closure** (AIT_001 owns NpcTrackingTier ontology; PROG_001 §3.1 reserves `tracking_tier: Option<NpcTrackingTier>` field; AIT_001 CANDIDATE-LOCK 2026-04-27 `da4b0cf1` activates Major/Minor populated).
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None; full closure summary in _Last released_ entry
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_progression/PROG_001_progression_foundation.md`: status header DRAFT 2026-04-26 → CANDIDATE-LOCK 2026-04-27 with closure pass rationale (PROG-Q1..Q5 deferred to consumer features; cross-cultivation extensibility audit findings preserved)
  - `features/00_progression/_index.md`: Active PROG_001 DRAFT → empty (folder closure 2026-04-27); folder closure status Open → COMPLETE 2026-04-27 with foundation tier 6/6 confirmation

### PROG_001 final summary

- **Status:** CANDIDATE-LOCK 2026-04-27
- **Foundation tier 6/6 COMPLETE** — PROG_001 was 6th and final V1 foundation feature; foundation tier closure: EF + PF + MAP + CSC + RES (closure pending next) + PROG all CANDIDATE-LOCK
- **Substrate:** dynamic per-reality attribute + skill + stage/cultivation systems (modern social-life game / tu tiên cultivation / traditional RPG / sandbox-no-progression — all from same engine substrate)
- **7 axioms:** PROG-A1..A7 (per-reality schema / no-level-no-chiến-lực / unified ProgressionKind ontology / quantum-observation NPC model / BodyOrSoul discriminator / hybrid combat damage V1 / English IDs + I18nBundle)
- **Catalog entries:** 26 V1 (PROG-1..PROG-26) + 5 V1+30d (PROG-27..PROG-31) + 6 V2/V3+ (PROG-32..PROG-37) + 5 cross-cultivation extensibility V1+30d/V2 (PROG-38..PROG-42) = 42 total
- **Reject rule_ids:** 7 V1 in `progression.*` namespace + 6 V1+ reservations
- **RealityManifest extensions:** 4 OPTIONAL V1 (progression_kinds + class_defaults + actor_overrides + strike_formula); empty default = sandbox/freeplay valid
- **Aggregate:** `actor_progression` (T2/Reality; owner=Actor V1; Item V1+30d reserved; tracking_tier reserved field activated by AIT_001)
- **Acceptance criteria:** 12 V1-testable AC-PROG-1..12

### Cross-feature closure-pass-extensions applied (history)

| Source | Effect on PROG_001 | When |
|---|---|---|
| Cross-cultivation extensibility audit (`b20c4dcb`) | 5 NEW V1+30d/V2 deferrals D33..D37 (all schema-additive per I14): cross-actor TrainingSource + RawValueDecrement active + derives_from cross-feature source + BreakthroughCondition::KarmaThreshold + RebirthBonusDecl. Pre-emptive future-proofing for ANY per-reality cultivation system | 2026-04-27 (post-DRAFT) |
| CULT_001 V2+ deferral (`d57fb7fc`) | PROG-A1 axiom preservation; CULT_001 reframed as template/convention library (non-engine; out-of-features/); PROG_001 V1 substrate already sufficient for 11-cultivation-system audit | 2026-04-27 (post-D33..D37) |
| TDIL_001 DRAFT promotion (`bdc8d8e1`) | Q3f day-boundary → turn-boundary semantic per TDIL-A3 per-turn O(1) Generator; Scheduled:CultivationTick reads body_clock/soul_clock per BodyOrSoul | 2026-04-27 (DRAFT phase mechanical revision) |
| AIT_001 CANDIDATE-LOCK (`da4b0cf1`) | tracking_tier field activated: Option<NpcTrackingTier> (None V1) → Major/Minor populated post-AIT activation; Schrödinger pattern (PROG-A4) preserved with PCs eager + Tracked NPCs lazy | 2026-04-27 (CANDIDATE-LOCK) |

### Cross-cultivation extensibility audit verdict

11-cultivation-system survey (Cầu Ma body refining / Tiên Nghịch realms / Mo Dao Zu Shi 魔修 / Lifespan-burning System / Mị ma song tu / đa phúc đa tử family / Rebirth of God Emperor / Heart demon 心魔 karma / Đấu Phá pet bond / 御剑 sword spirit / kiếm hiệp neigong-waigong) verified PROG_001 future-proof: **3 NATIVELY V1, 3 already-reserved (PROG-D2 + Q6b Item ActorRef + PROG-D10 ActorClassMatch), 5 require NEW deferrals D33..D37** — all schema-additive per I14 invariant; **zero PROG_001 redesign needed** for ANY per-reality cultivation system.

### NEW priority candidates post PROG closure

1. **RES_001 DRAFT closure pass** — last remaining foundation tier closure; consumed TDIL-A3 already at TDIL DRAFT bdc8d8e1; Q4 day-boundary → turn-boundary semantic preserved; awaiting Phase 3 + CANDIDATE-LOCK promotion
2. **PO_001 Player Onboarding** — V1-blocking; Phase 0 wireframes committed `19855a5b` + `4c4fd6d7`; concept-notes + Q-deep-dive pending
3. **DF5 implementation scaffold** — `contracts/api/session/v1/` (~600 LoC traits + DTOs + ContractTestSuite ~30 scenarios) + `services/session-service/src/adapters/lru_distill.rs` LruDistillProvider V1 backend
4. **SPIKE_01 turn 5 integration test design** — DF5 + TDIL + AIT + PROG all CANDIDATE-LOCK now; can validate multi-channel + multi-session + tier-eligibility + cultivation-tick mechanics in concrete scenario
5. **V1+30d milestone activations** — PROG-D1 (cultivation method declarations / sect-specific progression) + PROG-D2 (Item ActorRef as progression owner) + PROG-D3 (cross-reality stat translation rules) + PROG-D4 (atrophy lazy at materialization) + PROG-D5 (offline mode `OfflineCultivationMode`)

### Foundation tier closure status

- ✅ EF_001 Entity Foundation — CANDIDATE-LOCK
- ✅ PF_001 Place Foundation — CANDIDATE-LOCK
- ✅ MAP_001 Map Foundation — CANDIDATE-LOCK
- ✅ CSC_001 Cell Scene Composition — CANDIDATE-LOCK
- 🟡 RES_001 Resource Foundation — DRAFT (closure pending; **NEXT**)
- ✅ PROG_001 Progression Foundation — **CANDIDATE-LOCK 2026-04-27 (THIS commit)**

---

## 2026-04-27 — AIT_001 AI Tier CANDIDATE-LOCK closure pass

- **Lock CLAIMED + RELEASED** — single combined `[boundaries-lock-claim+release]` commit. DRAFT 88404f08 → CANDIDATE-LOCK closure pass (TDIL closure-pass-extension §7.5 O(1) revision applied at TDIL DRAFT bdc8d8e1; DF5 closure-pass-extension annotation 5e9233d8 already applied).
- **Phase 3 + AC walkthrough:** §16 AC-AIT-1..12 walked; all 12 acceptance scenarios concrete + testable.
- **2 open questions RESOLVED at closure:**
  - **AIT-Q1** (Stage 2 LLM-flavor synthesis prompt structure) → deferred to PL_005 closure as new **AIT-D21 V1+30d**; PL_005 owns trigger (Examine/Speak/Strike target = Untracked NPC fires Stage 2 synthesis); prompt structure designed at PL_005 closure pass alongside other LLM-call patterns; token budget per call ~500 tokens.
  - **AIT-Q2** (UntrackedRuntimeState ephemeral storage location) → marked **OUT-OF-SCOPE** for AIT_001; pure DP-engineering choice; deferred to DP-team closure (06_data_plane); recommended starter: session memory cache (in-process per session-service) since Untracked discard at session-end per Q6 LOCKED; Redis Streams ephemeral V2+ if cross-service Untracked observation needed.
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None; full closure summary in _Last released_ entry
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/16_ai_tier/AIT_001_ai_tier_foundation.md`: status header DRAFT → CANDIDATE-LOCK with closure pass rationale + AIT-Q1/Q2 strikethrough RESOLVED annotations
  - `features/16_ai_tier/_index.md`: folder closure status Open → COMPLETE 2026-04-27

### AIT_001 final summary

- **Status:** CANDIDATE-LOCK 2026-04-27
- **Architecture-scale:** 3-tier NPC architecture for billion-NPC scaling + Schrödinger / quantum-observation pattern
- **10 axioms:** AIT-A1..A10 (3-tier architecture / quantum-observation / deterministic Untracked / hybrid 2-stage / daily rotation / author-required tier / NpcId stable / tier-aware actions / tier-aware AssemblePrompt budget / i18n)
- **Catalog entries:** 27 V1 (AIT-1..AIT-27) + 7 V1+30d/V2 deferrals (AIT-28..AIT-34) = 34 total
- **Reject rule_ids:** 8 V1 (canonical_tier_required + capacity_exceeded + density_exceeded + template_invalid + action_forbidden_for_tier + untracked_cannot_initiate + promotion_target_not_observed + untracked_role_unknown) + 4 V1+ reservations
- **RealityManifest extensions:** 5 OPTIONAL V1 (tier_capacity_caps + untracked_templates + cell_untracked_density + tier_roster_caps + minor_behavior_scripts)
- **Acceptance criteria:** 12 V1-testable AC-AIT-1..12

### Cross-feature closure-pass-extensions applied (history)

| Source | Effect on AIT_001 | When |
|---|---|---|
| TDIL_001 DRAFT promotion (`bdc8d8e1`) | §7.5 Tracked NPC lazy materialization revised: per-day replay → O(1) elapsed-time computation per TDIL-A3 + TDIL-A7 (cross-realm observation 1 calculation regardless of magnitude — preserves billion-NPC scale) | 2026-04-27 (DRAFT phase) |
| DF05_001 CANDIDATE-LOCK + closure-pass-extensions cascade (`5e9233d8`) | AIT-A8 capability matrix annotated as ground-truth for DF5-A6 tier eligibility; DF5-A8 per-cell session capacity coordinates with TierCapacityCaps; MemoryProvider capability gate consumer; AIT-D7 V1+30d Untracked promotion path interacts with `/chat @untracked` | 2026-04-27 (post-DF5 cascade) |

### Cross-feature closure-pass-extensions consumed by AIT_001 at DRAFT

| Target | AIT_001 effect | Status |
|---|---|---|
| NPC_001 Cast | REQUIRED `tracking_tier` field on CanonicalActorDecl + tier-aware persona assembly | ✅ applied via ACT_001 unification cascade `d12a86f0` |
| NPC_002 Chorus | tier filter in priority calculation (Major full / Minor low / Untracked excluded) | ✅ applied via DF05 closure-pass cascade `5e9233d8` |
| PL_005 Interaction | AIT-V1 TierActionValidator slot reference + Untracked target handling + Stage 2 synthesis hook AIT-D21 V1+30d | ✅ applied via DF05 closure-pass cascade `5e9233d8` |
| WA_003 Forge | Add `Forge:PromoteUntrackedToTracked` AdminAction sub-shape | ✅ applied via DF05 closure-pass cascade `5e9233d8` |
| PROG_001 | tracking_tier field documentation update | ✅ existing PROG_001 §3.1 reserves the field; activation V1 |
| PL_001 Continuum | Session lifecycle hooks for AIT discard | ✅ implicit via DF5 close cascade per `5e9233d8` |

### NEW priority candidates post AIT closure (Architecture-scale closure COMPLETE)

1. **PROG_001 + RES_001 DRAFT closure passes** — both adopted TDIL-A3 per-turn O(1) Generator semantic at TDIL DRAFT; awaiting Phase 3 + CANDIDATE-LOCK
2. **PO_001 Player Onboarding** — V1-blocking; Phase 0 wireframes committed `19855a5b`; concept-notes pending
3. **DF5 implementation scaffold** — `contracts/api/session/v1/` (~600 LoC traits + DTOs + ContractTestSuite ~30 scenarios) + `services/session-service/src/adapters/lru_distill.rs` LruDistillProvider V1 backend
4. **SPIKE_01 turn 5 integration test design** — DF5 + TDIL + AIT all CANDIDATE-LOCK now; can validate multi-channel + multi-session + tier-eligibility mechanics in concrete scenario
5. **V1+ milestone activations** — AIT-D1 (auto-promotion via significance) + AIT-D2 (demotion) + AIT-D7 (LLM-propose-promotion) + AIT-D21 (Stage 2 synthesis prompt) — all V1+30d items

### Architecture-scale tier closure status

- ✅ ACT_001 Actor Foundation — CANDIDATE-LOCK 2026-04-27 (a1ce3c8a)
- ✅ AIT_001 AI Tier Foundation — **CANDIDATE-LOCK 2026-04-27 (THIS commit)**
- ✅ TDIL_001 Time Dilation Foundation — CANDIDATE-LOCK 2026-04-27 (261391ab; just preceded)
- 🟡 PROG_001 Progression Foundation — DRAFT (closure pending; consumed TDIL-A3)
- 🟡 RES_001 Resource Foundation — DRAFT (closure pending; consumed TDIL-A3)

---

## 2026-04-27 — TDIL_001 Time Dilation CANDIDATE-LOCK closure pass

- **Lock CLAIMED + RELEASED** — single combined `[boundaries-lock-claim+release]` commit. DRAFT bdc8d8e1 → CANDIDATE-LOCK closure pass.
- **No Phase 3 drift detected** — cross-feature closure-pass-extensions to PROG_001 / RES_001 / AIT_001 already applied at DRAFT promotion via `bdc8d8e1`. AC-TDIL-1..10 walkthrough verified all 10 acceptance scenarios concrete + testable.
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None; full closure summary in _Last released_ entry
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/17_time_dilation/TDIL_001_time_dilation_foundation.md`: status header DRAFT → CANDIDATE-LOCK with closure pass rationale (Phase 3 detected no drift; AC walkthrough verified)
  - `features/17_time_dilation/_index.md`: folder closure status Open → COMPLETE 2026-04-27

### TDIL_001 final summary

- **Status:** CANDIDATE-LOCK 2026-04-27
- **Architecture-scale:** 4-clock relativity model (realm + actor + soul + body) with Convention B time_flow_rate semantic
- **10 axioms:** TDIL-A1..A10 (Convention B / 4-clock model / per-turn O(1) Generator / channel-bound vs actor-bound / atomic travel / per-realm turn streams / cross-realm O(1) / worldline monotonicity / replay-deterministic / xuyên không clock-split)
- **Catalog entries:** 17 V1 (TDIL-1..TDIL-17) + 6 V1+30d (TDIL-18..23) + 4 V2/V3+ (TDIL-24..27) = 27 total
- **Reject rule_ids:** 4 V1 (rate_out_of_bounds + invalid_initial_clocks + mid_turn_channel_cross_forbidden + past_clock_edit_forbidden) + 6 V1+30d reservations
- **RealityManifest extensions:** 5 OPTIONAL V1 (time_flow_rate on MAP_001 MapLayoutDecl + time_flow_rate_override on PF_001 PlaceDecl + actor_clocks aggregate + InitialClocksDecl on CanonicalActorDecl + DilationChamberDecl V1+30d)
- **Acceptance criteria:** 10 V1-testable AC-TDIL-1..10
- **Cross-feature closure-pass-extensions applied at DRAFT (`bdc8d8e1`):** PROG_001 Q3f + RES_001 Q4 + AIT_001 §7.5 day-boundary → turn-boundary (mechanical revision per TDIL-A3 per-turn O(1) semantic)

### 4 user-raised concerns RESOLVED

| Concern (user 2026-04-27) | Resolution |
|---|---|
| Tu tiên cultivation rate mismatch (newbie vs 元嬰 incompatible same-clock) | TDIL-A2 4-clock model; per-actor `actor_clocks.body_clock` allows different cultivation pace per actor |
| Multi-realm time variance (Tây Du Ký 天上一日人間一年) | TDIL-A1 Convention B time_flow_rate; Tây Du Ký heaven channel time_flow_rate ≈ 0.0027 (1 wall-day = 365 fiction-days at heaven; mortal channel = 1.0 baseline) |
| Time chambers (Dragon Ball 精神時光屋) | TDIL-A1 cell-tier `time_flow_rate_override` on PF_001 PlaceDecl (REPLACE semantic, NOT multiply); chamber cell time_flow_rate = 365.0 (1 wall-day = 365 fiction-days inside) |
| PvP newbie-gank prevention | TDIL-A1 + TDIL-A6 per-realm turn streams — high-tier elder must spend their proper time at newbie zones (cannot exploit faster channels for free turns); economic disincentive |

### NEW priority candidates post TDIL closure

1. **AIT_001 CANDIDATE-LOCK closure** (next immediate; defer AIT-Q1 + AIT-Q2 to NPC_001 closure / DP engineering respectively)
2. **PROG_001 + RES_001 DRAFT closure passes** (both have closure-pass-extensions from TDIL applied; awaiting Phase 3 + CANDIDATE-LOCK)
3. **PO_001 Player Onboarding** (V1-blocking; Phase 0 wireframes committed `19855a5b`)
4. **DF5 implementation scaffold** (`contracts/api/session/v1/` + `services/session-service/`)
5. **SPIKE_01 turn 5 integration test design** (validate DF5 + TDIL multi-channel mechanics)

---

## 2026-04-27 — DF05 closure-pass-extensions cascade — 13 consumer feature specs annotation

- **Lock CLAIMED + RELEASED** — single combined `[boundaries-lock-claim+release]` commit (mirror TIT_001 closure-pass pattern for cross-feature deferral RESOLVED batches)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None; full closure-pass cascade summary in _Last released_
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`** (13 consumer feature specs):

| Feature | Magnitude | Integration point |
|---|---|---|
| `features/04_play_loop/PL_001_continuum.md` | MEDIUM | §13 Travel sequence cascades into session-service for cell-leave; DF5-A4 anchor invariant trigger |
| `features/04_play_loop/PL_002_command_grammar.md` | LOW | `/chat @actor` + `/leave` V1 commands added; rate-limit serves as anti-spam per Q4-D4 |
| `features/04_play_loop/PL_005_interaction.md` | LOW-MEDIUM | EVT-T1 PCTurn/NPCTurn schema-additive `session_id: Option<SessionId>` field V1+30d; DF5-V1..V4 validator slots |
| `features/05_npc_systems/NPC_001_cast.md` | MEDIUM | NPC eligibility check (Q4-D1 reputation-gated) + DF5-V4 TierEligibilityValidator + MemoryProvider trait import per §16 SDK |
| `features/05_npc_systems/NPC_002_chorus.md` | LOW | Turn-ordering within session_id scope; tier-aware persona via MemoryProvider; multi-PC V2+ via DF5-D1 |
| `features/05_npc_systems/NPC_003_desires.md` | LOW | V1 read-only consumer; V2+ desire-driven session creation via DF5-D7 |
| `features/00_actor/ACT_001_actor_foundation.md` | MEDIUM | actor_session_memory R8 PRIMARY post-close store; POV-distill cache in EVT-T3 SessionPovDistill payload per Q12-D1; Q7 cross-session bleed; LruDistillProvider V1 backend consumes R8 LRU |
| `features/00_reputation/REP_001_reputation_foundation.md` | LOW | 8-tier ReputationTier consumed by Q4-D1 consent; Wuxia I18n labels reused for refusal template Q4-D3 |
| `features/02_world_authoring/WA_003_forge.md` | LOW | 9 NEW V1 AdminAction sub-shapes registered (CreateSession/CloseSession/KickFromSession/EditActorSessionMemory/RegenSessionDistill/PurgeActorSessionMemory/AnonymizePcInSessions/BulkRegenSessionDistill/BulkPurgeStaleSessions); 3-write atomic pattern preserved |
| `features/02_world_authoring/WA_006_mortality.md` | LOW | V1+30d PC-dies-in-session cascade (NEW LeftReason::Killed variant); Q6-D5 death = freeze; actor_dies EVT-T3 cascade additive consumer |
| `features/16_ai_tier/AIT_001_ai_tier_foundation.md` | LOW-MEDIUM | AIT-A8 capability matrix = ground-truth for DF5-A6 tier eligibility; DF5-A8 capacity coordinates with TierCapacityCaps; MemoryProvider capability gate; AIT-D7 V1+30d Untracked promotion interacts |
| `features/06_pc_systems/PCS_001_pc_substrate.md` | MEDIUM | pc_user_binding.current_session: Option<SessionId> consumer; body_memory feeds prompt-assembly via MemoryProvider trait; per-PC active-session lookup; DF5-C1 cross-aggregate validator |
| `features/00_place/PF_001_place_foundation.md` | LOW | Cell-tier session capacity ≤50 V1 (DF5-A8); cell display "N active conversations" V1+30d cosmetic; DF5-C2 cell-tier-only verifies via §5 |

### Closure-pass discipline preserved

- **Annotation-only** — no architectural changes to any consumer feature
- **CANDIDATE-LOCK / DRAFT status PRESERVED** for all 13 specs (no reopens; pure additive `> **⚠ CLOSURE-PASS-EXTENSION 2026-04-27 — DF05_001 ...**` header annotations after the title line)
- **No new aggregates / EVT-T sub-types / RealityManifest extensions** in this commit (those landed in DF05_001 cycle commit 2/4 5d5dddd3)
- **No new reject rule_ids** in this commit (those landed in commit 2/4 + Phase 3 cleanup 60536f19)
- **Mirror TIT_001 cross-feature deferral RESOLVED pattern** — closure-pass-extensions cascade after CANDIDATE-LOCK release

### Cross-feature integration map (the 13 specs annotated)

```
DF05_001 Session/Group Chat (CANDIDATE-LOCK 71a60346)
    │
    ├── Play loop (3 specs):
    │   ├── PL_001 Continuum — cell-leave cascade
    │   ├── PL_002 Grammar — /chat + /leave commands
    │   └── PL_005 Interaction — session_id field + validators
    │
    ├── Inhabitants (5 specs):
    │   ├── NPC_001 Cast — eligibility + MemoryProvider trait
    │   ├── NPC_002 Chorus — turn-ordering within session
    │   ├── NPC_003 Desires — V1 read; V2+ desire-driven
    │   ├── ACT_001 Actor — actor_session_memory R8 primary
    │   └── PCS_001 PC Substrate — body_memory + active-session lookup
    │
    ├── Authoring + Cross-cutting (3 specs):
    │   ├── REP_001 Reputation — 8-tier consent gating reuse
    │   ├── WA_003 Forge — 9 V1 AdminAction sub-shapes
    │   └── WA_006 Mortality — V1+30d PC-dies-in-session
    │
    └── Engine + Place (2 specs):
        ├── AIT_001 AI Tier — capability matrix + tier capacity coordination
        └── PF_001 Place — cell-tier session capacity tracking
```

(Boundary registries already updated in DF05_001 cycle commit 2/4: 07_event_model EVT-T sub-types + RealityManifest canonical_sessions + 01_feature_ownership_matrix.md aggregates + 02_extension_contracts.md §1.4 + §2 + 03_validator_pipeline_slots.md namespace matrix + C26-C29 cross-aggregate rules. EM-7 Reality Close already covers session cascade per existing reality close logic.)

### NEW priority candidates post DF5 closure-pass-extensions

1. **PO_001 Player Onboarding** (V1-blocking; folder placeholder; consumes PCS_001 PCS-D1 runtime login + DF05_001 session lifecycle)
2. **Architecture-scale closure** — TDIL_001 + AIT_001 still DRAFT (Phase 3 + CANDIDATE-LOCK closure pending)
3. **DF5 implementation scaffold** — `contracts/api/session/v1/` (~600 LoC traits + DTOs + ContractTestSuite ~30 scenarios) + `services/session-service/src/adapters/lru_distill.rs` LruDistillProvider V1 backend + CI lint rule blocking adapter imports outside service
4. **SPIKE_01 turn 5 integration test design** (DF05_001 enables — multi-session memory verification)
5. **DRAFT closure passes** for PROG_001 / RES_001 / AIT_001 / TDIL_001
6. **DIPL_001 Diplomacy** V2+ (consumes FAC_001 + REP_001 + V1+ FactionElect TIT-D1)

---

## 2026-04-27 — DF05 Session/Group Chat CANDIDATE-LOCK closure commit 4/4 — final lock release

- **Lock RELEASED** — 4-commit cycle COMPLETE: Phase 0 0080b533 + commit 1/4 745e9f6e + DRAFT 2/4 5d5dddd3 + Phase 3 cleanup 3/4 60536f19 + closure 4/4 this commit; single combined `[boundaries-lock-release]` commit
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner reverted to None; _Last released_ entry with full 4-commit cycle summary
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/DF/DF05_session_group_chat/DF05_001_session_foundation.md`: status header DRAFT → CANDIDATE-LOCK with closure pass rationale (Phase 3 4 fixes + AC walkthrough complete)
  - `features/DF/DF05_session_group_chat/_index.md`: folder closure status COMPLETE; DRAFT cycle 4-commit chain populated; NEW priority candidates listed (16 closure-pass-extensions + 2 NEW directories scaffold + V1+30d implementation phase)

### V1-blocking biggest unknown RESOLVED

DF05 was marked V1-blocking biggest unknown 2026-04-25 in placeholder. After 2026-04-27 closure cycle:
- Architecture pivoted from initial single-session-per-cell (rejected) to multi-session-per-cell sparse model
- Q1-Q12 ALL LOCKED via 4-batch deep-dive (zero revisions)
- §16 SDK Architecture LOCKED — versioned contract + swappable backends
- 14 V1 reject rule_ids registered in `session.*` namespace
- 11 invariants DF5-A1..A11 codified
- 4 cross-aggregate consistency rules DF5-C1..C4 (global C26-C29)
- 25 V1-testable AC scenarios + 5 worked sequences
- 17 deferrals to V1+30d / V2 / V3 / V3+
- 48 catalog entries DF5-1..DF5-48

### Cross-feature deferrals RESOLVED at this commit

| Deferral | Source | Resolution |
|---|---|---|
| PC-D1 (multi-PC parties) | PCS / DF placeholder | Redirected to V2 multi-PC join via DF5-D1 (separate from V1 solo RP scope) |
| PC-D2 (PvP consent) | PCS / DF placeholder | V2 deferred via DF5-D3 (depends on DF4 World Rules consent flow) |
| PC-D3 (no global chat) | PCS / DF placeholder | RESOLVED architecturally — multi-session-per-cell sparse model precludes "global chat" concept (each session is explicit social act with isolated participants) |
| B4 PARTIAL (multi-NPC turn arbitration) | catalog/cat_05_NPC | RESOLVED via NPC_002 Chorus integration in DF5_001 (existing NPC_002 turn-ordering integrated into session lifecycle) |
| V1-blocking biggest unknown | SESSION_HANDOFF agenda | RESOLVED — DF05 promoted CANDIDATE-LOCK 2026-04-27; remaining V1-blocking concerns now cluster around PO_001 + Architecture-scale closure (TDIL/AIT) |

### NEW priority candidates post DF5_001 CANDIDATE-LOCK

1. **PO_001 Player Onboarding** (consumes PCS_001 PCS-D1 runtime login flow + DF5_001 session lifecycle) — V1-blocking; folder placeholder only; concept-notes pending
2. **Architecture-scale closure** — TDIL_001 + AIT_001 still DRAFT (both have promotion gate ✅ Met but Phase 3 cleanup + CANDIDATE-LOCK closure pending)
3. **DF5 closure-pass-extensions** — 16 cross-feature follow-up commits cascading to PL_002 + PL_005 + NPC_001..003 + ACT_001 + REP_001 + WA_003 + WA_006 + AIT_001 + PCS_001 + PL_001 + PF_001 + EM-7 + 07_event_model + RealityManifest (each adds session_id reference field / tier check / persona-assembly trait import / etc.)
4. **DF5 implementation scaffold** — `contracts/api/session/v1/` directory + 7 files (~600 LoC traits + DTOs + ~30 contract test scenarios) + `services/session-service/` initial structure (V1 LruDistillProvider) + CI lint rule blocking adapter imports outside service
5. **DIPL_001 Diplomacy Foundation** V2+ (consumes FAC_001 + REP_001 + V1+ FactionElect TIT-D1)
6. **AI-controls-PC-offline activation** (cross-ref ACT-D1)
7. **DRAFT closure passes** for PROG_001 / RES_001 / AIT_001 / TDIL_001 (all DRAFT pending CANDIDATE-LOCK closure)
8. **SPIKE_01 turn 5 integration test design** (DF5_001 enables this — multi-session memory + session_participation cascades verifiable)

### Cycle plan COMPLETE

- ✅ Phase 0 (commit 0080b533): concept-notes Q-LOCKED + SDK LOCKED
- ✅ Commit 1/4 (745e9f6e): `[boundaries-lock-claim]` lock + cycle plan
- ✅ Commit 2/4 (5d5dddd3): DRAFT promotion + boundary register + catalog seed
- ✅ Commit 3/4 (60536f19): Phase 3 cleanup — 4 fixes (LeftReason 6→7 + 14th rule + boundary consistency + AC walkthrough)
- ✅ Commit 4/4 (THIS): `[boundaries-lock-release]` CANDIDATE-LOCK closure — final lock release + cross-feature deferral RESOLVED annotations

---

## 2026-04-27 — DF05 Session/Group Chat DRAFT cycle commit 3/4 — Phase 3 cleanup

- **Phase 3 cleanup applied** — self-review walkthrough surfaced 4 issues; all fixed
- **Files modified within `_boundaries/`:**
  - `02_extension_contracts.md`: §1.4 session.* row updated 13 V1 → 14 V1 (Phase 3 cleanup added participant_already_joined defensive write-time validator)
  - `03_validator_pipeline_slots.md`: namespace matrix session.* updated 13 V1 → 14 V1; Total V1 reject rules updated ~153 → ~154
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/DF/DF05_session_group_chat/DF05_001_session_foundation.md`:
    - §3.2 LeftReason enum: 6 variants → 7 (added DisconnectTimeout V1 distinct from Inactive V1+30d auto-detect)
    - §2 Domain concepts table: LeftReason updated 6 V1 → 7 V1
    - §13.2 grace_timeout_fired pseudocode: now uses LeftReason::DisconnectTimeout (V1 disconnect grace expired) NOT Inactive (V1+30d in-session activity auto-detect — different concept)
    - §21.1 V1 reject rule_ids: 13 → 14 (added session.participant_already_joined for defensive write-time validation on session_participation Born composite key duplicate)

### Phase 3 cleanup findings

1. **LeftReason enum mismatch** — V1 disconnect grace timeout (Q10-D1 LOCKED) used `LeftReason::Inactive`, but Inactive comment said "V1+30d auto-detect" (DF5-D4 in-session activity stall). These are TWO distinct concepts conflating one variant. Fix: split into DisconnectTimeout (V1; wall-clock 30s grace expired) + Inactive (V1+30d; in-session activity auto-detect via DF5-D4).
2. **participant_already_joined missing from V1 rule list** — §3.2 referenced `session.participant_already_joined` for composite key (session_id, actor_id) duplicate writes, but §21.1 listed only 13 V1 rules. Fix: added as 14th rule. Defensive write-time validator on session_participation Born — distinct from actor_busy_in_other_session (different session) AND closed_session_immutable (Closed session). Covers the rare case where same actor attempts to join SAME active session twice.
3. **Boundary file consistency** — 02_extension_contracts.md §1.4 session.* row + 03_validator_pipeline_slots.md namespace matrix updated to reflect 14 V1.
4. **AC-DF5-1..25 walkthrough verified** — all 25 acceptance scenarios reference concrete validators / events / rule_ids. No additional ACs needed for Phase 3 fixes (DisconnectTimeout reason captured in AC-DF5-15 LeftReason audit; participant_already_joined defensive — manual test path documented in §21.1).

### Cycle plan continuation

- ✅ Phase 0 (commit 0080b533): concept-notes Q-LOCKED + SDK LOCKED
- ✅ Commit 1/4 (745e9f6e): `[boundaries-lock-claim]` lock + cycle plan
- ✅ Commit 2/4 (5d5dddd3): DRAFT promotion + boundary register + catalog seed
- ✅ Commit 3/4 (THIS): Phase 3 cleanup — 4 fixes
- 🟡 Commit 4/4 (next): `[boundaries-lock-release]` CANDIDATE-LOCK closure

---

## 2026-04-27 — DF05 Session/Group Chat DRAFT cycle commit 2/4 — DRAFT promotion + boundary register

- **DRAFT promoted** — `DF05_001_session_foundation.md` ~1446 lines (25 sections incl. §16 SDK Architecture)
- **Catalog seed created** — `catalog/cat_18_DF5_session_group_chat.md` (DF5-A1..A11 axioms + 48 catalog entries DF5-1..DF5-48; 33 V1 + 4 V1+30d + 11 V2/V2+/V3/V3+ deferrals)
- **Files modified within `_boundaries/`:**
  - `01_feature_ownership_matrix.md`:
    - 2 NEW Aggregate ownership rows: `session` (T2/Reality) + `session_participation` (T2/Reality, sparse per-(session, actor))
    - NEW EVT-T4 System sub-type row: `SessionBorn` (DF05_001-owned)
    - NEW EVT-T8 Administrative sub-shapes row: 9 V1 Forge AdminActions (CreateSession + CloseSession + KickFromSession + EditActorSessionMemory + RegenSessionDistill + PurgeActorSessionMemory + AnonymizePcInSessions + BulkRegenSessionDistill + BulkPurgeStaleSessions)
    - NEW EVT-T3 Derived sub-types row: `aggregate_type=session` (Born/ClosingTransition/ClosedTransition) + `aggregate_type=session_participation` (Born/Update LeftTransition) + POV-distill cache `aggregate_type=actor_session_memory` SessionPovDistill payload (Q12-D1 LOCKED full JSON V1; cache invalidation per Q12-D2; replay reads cache per Q12-D3)
    - RejectReason namespace prefixes row updated: appended `session.* → DF05_001`
    - NEW Stable-ID prefix row: `DF5-*` (V1-blocking biggest unknown RESOLVED 2026-04-27; multi-session-per-cell sparse architecture)
  - `02_extension_contracts.md`:
    - §1.4 NEW `session.*` namespace row: 13 V1 reject rule_ids (duplicate_session_id / participant_cap_exceeded / cell_session_overload / actor_not_eligible_untracked / actor_busy_in_other_session / npc_refused / invalid_state_transition / empty_participant_list_invalid / anchor_must_be_pc / cross_channel_participation_forbidden / closed_session_immutable / distill_cache_version_mismatch / cell_session_creation_rate_limited) + 5 V1+ reservations (cross_reality_session / npc_only_session_disallowed / session_resume_disallowed / summary_corruption_detected / distill_quota_exceeded)
    - §2 NEW `canonical_sessions: Vec<CanonicalSessionDecl>` RealityManifest extension OPTIONAL V1 (sparse opt-in for V1+ author-scripted set-piece sessions)
  - `03_validator_pipeline_slots.md`:
    - §"Tier 5 Actor Substrate namespaces" matrix updated: NEW `session.*` row (13 V1 + 5 V1+; Stage 0 canonical seed + Stage 1 runtime + Stage 7 Forge admin + Stage 8 close cascade + cross-aggregate cascades C26-C29)
    - §"Stage 0 canonical seed cross-aggregate consistency rules" — 4 NEW rules C26-C29: C26 (DF5-C1) anchor_pc_id MUST be PC kind / C27 (DF5-C2) channel_id MUST be cell-tier / C28 (DF5-C3) per-cell session capacity ≤50 V1 / C29 (DF5-C4) per-actor one Active session V1
    - Total V1 reject rules: ~140 → ~153 (+13 DF5)
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/DF/DF05_session_group_chat/DF05_001_session_foundation.md` (NEW; 1446 lines)
  - `features/DF/DF05_session_group_chat/_index.md`: status CONCEPT COMPLETE → DRAFT (commit 2/4 of 4-commit cycle)
  - `catalog/cat_18_DF5_session_group_chat.md` (NEW; DF5-A1..A11 axioms + 48 catalog entries)

### Cycle plan continuation

- ✅ Phase 0 (commit 0080b533): concept-notes Q-LOCKED + SDK LOCKED
- ✅ Commit 1/4 (745e9f6e): `[boundaries-lock-claim]` lock + cycle plan
- ✅ Commit 2/4 (THIS): DRAFT promotion + boundary register + catalog seed
- 🟡 Commit 3/4 (next): Phase 3 cleanup — AC-DF5-1..25 walkthrough + typo fixes + thin-section expansion
- ⏳ Commit 4/4: `[boundaries-lock-release]` CANDIDATE-LOCK closure

---

## 2026-04-27 — DF05 Session/Group Chat DRAFT cycle commit 1/4 — lock claim

- **Lock CLAIMED** — `[boundaries-lock-claim]` start of DF05 4-commit cycle (Phase 0 0080b533 preceded; this is commit 1/4)
- **TTL:** 4-hour (expires 2026-04-28T02:00:00Z)
- **Owner:** main session 2026-04-27
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner DF05 claim + Expected work full description + Expires at 4h TTL
  - `99_changelog.md`: this entry top-anchored

### Cycle plan post-claim

- **Commit 2/4 (next)** — DRAFT promotion + boundary register: author `DF05_001_session_foundation.md` spec ~1180 lines + `cat_18_DF5_session_group_chat.md` catalog seed + `_boundaries/01_feature_ownership_matrix.md` + `_boundaries/02_extension_contracts.md` §1.4 + §2 + `_boundaries/03_validator_pipeline_slots.md` + `99_changelog.md` entry + `features/DF/DF05_session_group_chat/_index.md` status DRAFT promoted
- **Commit 3/4** — Phase 3 cleanup: self-review walk through AC-DF5-1..N + fix typos + expand thin sections + `99_changelog.md` entry
- **Commit 4/4** — `[boundaries-lock-release]` CANDIDATE-LOCK closure: `_LOCK.md` Owner None + final cycle summary + `_index.md` DRAFT → CANDIDATE-LOCK + `99_changelog.md` release entry

### Concept-notes preceded (Phase 0 0080b533)

- 4-batch Q-deep-dive Q1-Q12 ALL LOCKED 2026-04-27 zero revisions
- §15 SDK Architecture LOCKED (3-layer + 5 migration patterns + contract test suite)
- 11 invariants DF5-A1..A11 proposed
- Multi-session-per-cell sparse architecture (vs initial single-session-per-cell rejected)
- 16 cross-feature closure-pass-extensions queued (PL_002 + PL_005 + NPC_001..003 + ACT_001 + REP_001 + WA_003 + WA_006 + AIT_001 + PCS_001 + PL_001 + PF_001 + EM-7 + 07_event_model + RealityManifest) + 2 NEW directories (contracts/api/session/v1/ + services/session-service/)

---

## 2026-04-27 — TIT_001 Title Foundation CANDIDATE-LOCK closure commit 4/4 — final lock release + cross-feature deferral RESOLVED annotations

- **Lock RELEASED** — 4-commit cycle complete (Phase 0 f9e7600f + DRAFT 2/4 9456a446 + Phase 3 cleanup 3/4 2c00400f + closure 4/4 this commit); single combined `[boundaries-lock-release]` commit
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner reverted to None; _Last released_ entry with full 4-commit cycle summary
  - `99_changelog.md`: this entry top-anchored
- **Files modified outside `_boundaries/`:**
  - `features/00_titles/TIT_001_title_foundation.md`: status header DRAFT → CANDIDATE-LOCK; §14 Status section updated (Phase: CANDIDATE-LOCK; LOCK target after AC-TIT-1..10 V1-testable scenarios + V1+ TIT-D2/TIT-D3 ship; 4-commit cycle COMPLETE)
  - `features/00_titles/_index.md`: folder closure status COMPLETE; feature list TIT_001 row populated with full V1 spec summary + 4-commit chain
  - `features/00_family/FF_001_family_foundation.md`: FF-D8 marked ✅ RESOLVED 2026-04-27 by TIT_001 V1 (CANDIDATE-LOCK); description updated (TIT_001 V1 RESOLVES via SuccessionRule::Eldest + per-title VacancySemantic + cross-aggregate validator TIT-C1)
  - `features/00_faction/FAC_001_faction_foundation.md`: FAC-D6 marked ✅ RESOLVED 2026-04-27 by TIT_001 V1 (CANDIDATE-LOCK); FF-D8 jointly RESOLVED; description updated (TIT_001 V1 RESOLVES via SuccessionRule::Designated + TitleBinding::Faction cross-validation + TitleAuthorityDecl.faction_role_grant atomic role update via 3-write atomic pattern + TIT-C1 cross-aggregate cascade)
  - `features/00_reputation/REP_001_reputation_foundation.md`: REP-D9 marked ✅ V1 PARTIAL RESOLVED 2026-04-27 by TIT_001 V1 (CANDIDATE-LOCK; runtime gating remains V1+ alongside REP-D1); description updated (schema-active V1; runtime validator V1+ alongside REP-D1 runtime delta milestone; TIT-D2 simultaneous activation; Schema-stable / activation-deferred V1+ discipline TIT-A8)
  - `catalog/cat_00_REP_reputation_foundation.md`: REP-D9 row updated with V1 PARTIAL RESOLVED annotation

### Cross-feature deferrals RESOLVED at this commit

| Deferral | Source | Resolution |
|---|---|---|
| **FF-D8** ✅ FULL V1 | FF_001 Family Foundation | Title inheritance rules + heir succession → TIT_001 V1 RESOLVES via SuccessionRule::Eldest reading FF_001 dynasty.current_head_actor_id traversal + per-title VacancySemantic (PersistsNone/Disabled/Destroyed) + cross-aggregate validator TIT-C1 cascades synchronously on WA_006 mortality EVT-T3 same turn |
| **FAC-D6** ✅ FULL V1 (FF-D8 jointly) | FAC_001 Faction Foundation | Sect succession rules → TIT_001 V1 RESOLVES via SuccessionRule::Designated for sect-master + master-disciple succession + TitleBinding::Faction(faction_id) cross-validates against canonical_factions + TitleAuthorityDecl.faction_role_grant atomically updates actor_faction_membership.role_id on title-grant via 3-write atomic pattern + TIT-C1 cross-aggregate cascade. V1+ FactionElect SuccessionRule remains deferred via TIT-D1 alongside DIPL_001 V2+ procedural voting. |
| **REP-D9** ✅ V1 PARTIAL (runtime gating V1+ alongside REP-D1) | REP_001 Reputation Foundation | V1+ TIT_001 title-grant requires min rep → TIT_001 V1 PARTIAL RESOLVES via TitleDecl.min_reputation_required: Option<MinRepGate> field schema-active V1 per Q4 C LOCKED (declarations stored at canonical seed + Forge admin); runtime validator V1+ alongside REP-D1 runtime delta milestone (when REP_001 ships runtime gameplay delta events, TIT-D2 runtime min_rep validator activates simultaneously). Schema-stable / activation-deferred V1+ discipline (TIT-A8). |
| **WA_006 sect-leader-death cascade gap** ✅ FULL V1 | FAC_001 _index.md kernel touchpoint | Sect-leader death triggers V1+ TIT_001 succession → TIT_001 V1 RESOLVES via TIT-C1 cross-aggregate validator C-rule (registered as global C18 in `03_validator_pipeline_slots.md`; FIRST RUNTIME cascade C-rule registered post P4 commit). Synchronous same-turn cascade on WA_006 mortality EVT-T3 actor_dies; emits TitleSuccessionTriggered EVT-T3 + TitleGranted EVT-T4 (if heir) + TitleSuccessionCompleted EVT-T1 narrative milestone; atomic FAC_001 actor_faction_membership.role_id update if TitleAuthorityDecl.faction_role_grant Some. |

### TIT_001 4-commit cycle summary

| # | Commit | What |
|---|---|---|
| 1/4 | f9e7600f Phase 0 | Folder structure (`features/00_titles/`) + concept notes (~450 lines; Q1-Q10 placeholder) + reference survey (~400 lines; CK3 + Wuxia hybrid V1 anchor; 9-system survey: CK3/Bannerlord/GoT/Wuxia novels canon/Imperator Rome/Stellaris/WoW/Dwarf Fortress/D&D 5e) + index. NO boundary lock. |
| 2/4 | 9456a446 DRAFT | TIT_001_title_foundation.md spec (~739 lines; 14 sections) + cat_00_TIT_title_foundation.md catalog seed (8 axioms TIT-A1..A8 + 22 V1 catalog entries TIT-1..22 + 12 V1+/V2/V2+ entries TIT-23..34 + 12 deferrals TIT-D1..D12 + 8 cross-aggregate consistency rules TIT-C1..C8 + cross-feature integration map) + boundary updates (01_feature_ownership_matrix.md actor_title_holdings aggregate row + 4 EVT sub-type rows TitleGranted T4 / Forge admin T8 / TitleSuccessionTriggered T3 / TitleSuccessionCompleted T1 / RejectReason namespace title.* / TIT-* stable-ID prefix; 02_extension_contracts.md §1.4 title.* namespace 7 V1 + §2 RealityManifest 2 OPTIONAL V1 extensions canonical_titles + canonical_title_holdings) + 99_changelog.md DRAFT entry + concept notes Q-LOCKED matrix populated zero revisions + _index.md status update CONCEPT → DRAFT + `[boundaries-lock-claim]`. |
| 3/4 | 2c00400f Phase 3 cleanup | Drift fixes (added 2 missing reject rules `title.binding.faction_membership_required` + `title.binding.dynasty_membership_required` referenced in §6.2 + §9.1 pseudocode; updated count 7 V1 → 9 V1 across spec + catalog + boundary docs) + 03_validator_pipeline_slots.md TIT registration (NEW namespace row + 8 cross-aggregate consistency rules C18-C25; C18 is FIRST RUNTIME cascade C-rule post P4 commit; total V1 reject rules count 138 → 140; rule application discipline updated). Lock STAYS CLAIMED. |
| 4/4 | (this commit) closure | Status DRAFT → CANDIDATE-LOCK; cross-feature RESOLVED annotations on FF-D8/FAC-D6/REP-D9-partial source docs + WA_006 cascade gap closure note; folder _index.md COMPLETE; lock RELEASED via `[boundaries-lock-release]`. |

### V1 Summary

- **1 NEW sparse aggregate** — actor_title_holdings (T2/Reality, sparse per-(actor, title_id) edge)
- **2 RealityManifest extensions** — canonical_titles + canonical_title_holdings (both OPTIONAL V1)
- **6 new event sub-types** — 1 EVT-T4 + 3 EVT-T8 + 1 EVT-T3 + 1 EVT-T1 narrative
- **9 V1 reject rules** in title.* namespace + 5 V1+ reservations
- **8 cross-aggregate consistency rules** TIT-C1..C8 (global C18-C25; C18 RUNTIME cascade unique pattern)
- **8 axioms** TIT-A1..A8
- **10 V1 acceptance scenarios** AC-TIT-1..10 + 4 V1+ deferred
- **12 deferrals** TIT-D1..D12
- **TIT-* stable-ID prefix**

### Discipline observed across 4-commit cycle

- **Schema-stable / activation-deferred V1+ discipline (TIT-A8)** preserved across spec + catalog + boundary docs
- **Per-reality author-declared discipline (TIT-A1)** mirrors PROG-A1 + REP_001 + FAC_001
- **3-layer separation discipline (TIT-A4)**: TIT_001 ≠ FAC_001 actor_faction_membership ≠ REP_001 actor_faction_reputation
- **Per-title author-declared policy (TIT-A5)**: MultiHoldPolicy + TitleAuthorityDecl + VacancySemantic
- **Cross-aggregate cascade pattern (TIT-C1)**: title-holder death → synchronous succession cascade same turn via WA_006 mortality EVT-T3 (FIRST RUNTIME cascade C-rule registered post P4 commit)
- **3-write atomic Forge admin pattern** reused (consistent with WA_003 / FAC_001 / REP_001 / ACT_001 / PCS_001 prior)

### V1 unchanged for other features

This commit is purely additive per I14 invariant. Pure documentation closure annotations + status promotion. No changes to existing aggregates / EVT sub-shapes / RealityManifest fields owned by other features (beyond marking deferrals RESOLVED). PROG_001 / RES_001 / IDF_001..005 / FF_001 / FAC_001 / REP_001 / ACT_001 / PCS_001 / AIT_001 / TDIL_001 status unchanged.

### CANDIDATE-LOCK → LOCK gate

TIT_001 transitions to LOCK when:
- AC-TIT-1..10 V1-testable scenarios pass integration tests against Wuxia + Modern + D&D reality fixtures
- V1+ TIT-D2 runtime min_rep validator ships (alongside REP-D1)
- V1+ TIT-D3 requires_title Lex axiom validator ships (alongside WA_001 closure pass adding 5-companion-fields uniformly)

### NEW priority candidates post TIT_001 CANDIDATE-LOCK

| Candidate | Justification |
|---|---|
| **PO_001 Player Onboarding** | UI flow consumes PCS_001 primitives Forge:RegisterPc + Forge:BindPcUser per PCS-D1; resolves "V1 character creation" gap |
| **DIPL_001 Diplomacy Foundation V2+** | Inter-faction politics; consumes FAC + REP + V1+ FactionElect (TIT-D1); enables war/treaty/alliance dynamics |
| **AI-controls-PC-offline activation** | Cross-ref ACT-D1; chorus_metadata sparse PC V1+ activation; "PC continues offline" pattern |
| **DRAFT closure passes for PROG_001 / RES_001 / AIT_001 / TDIL_001** | Promote DRAFT → CANDIDATE-LOCK; resolve §20.2 deferred follow-ups |
| **SPIKE_01 turn 5 integration test design** | First end-to-end turn pipeline test; validates 6 foundations + 9 Tier 5 features integrated (now including TIT_001) |

User to pick next priority post this commit.

---

## 2026-04-27 — TIT_001 Phase 3 cleanup commit 3/4 — drift fixes + validator pipeline slots TIT-C1..C8 / C18-C25 registration

- **Lock STAYS CLAIMED** — Phase 3 cleanup commit; release at closure 4/4 commit
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: lock claim active (no claim/release change this commit)
  - `01_feature_ownership_matrix.md`: actor_title_holdings row updated (7 V1 → 9 V1 reject rules with Phase 3 added 2 binding-membership-required rules)
  - `02_extension_contracts.md`: §1.4 title.* namespace updated 7 V1 → 9 V1 (added binding.faction_membership_required + binding.dynasty_membership_required for canonical seed + Forge:GrantTitle binding-actor membership validation)
  - `03_validator_pipeline_slots.md`:
    - **NEW row** in §"Tier 5 Actor Substrate namespaces" — title.* (9 V1 + 5 V1+ reservations)
    - Total V1 reject rules count updated: 138 → 140 (added 2 TIT rules)
    - **NEW 8 rows** in §"Stage 0 canonical seed cross-aggregate consistency rules" — C18 (TIT-C1) RUNTIME cascade synchronously on WA_006 mortality EVT-T3 + C19-C25 (TIT-C2..C8) canonical seed bootstrap-time validators
    - Rule application discipline updated with TIT-specific notes (C18 is RUNTIME cascade not bootstrap; C19-C25 mirror earlier patterns)
  - `99_changelog.md`: this entry
- **Files modified outside `_boundaries/`:**
  - `features/00_titles/TIT_001_title_foundation.md`: §8.1 V1 rule_ids updated 7 → 9 (added binding.faction_membership_required + binding.dynasty_membership_required); §1 V1 minimum scope summary updated 7 → 9; §11 V1 Minimum Delivery Summary updated 7 → 9
  - `catalog/cat_00_TIT_title_foundation.md`: TIT-18 entry updated 7 V1 → 9 V1 with Phase 3 cleanup note

### Background

Phase 3 cleanup self-review pass identified drift in TIT_001 §6.2 Forge admin pseudocode — referenced 2 reject rules NOT in §8.1 V1 namespace list:
- `title.binding.faction_membership_required` (referenced in §6.2 + §9.1 canonical seed bootstrap; not in §8.1 V1 list)
- `title.binding.dynasty_membership_required` (same problem)

Validation logic was correct (canonical seed §9.1 + Forge admin §6.2 both check binding-actor faction/dynasty membership) but reject rules weren't formally registered. Phase 3 fix: ADD the 2 rules to V1 namespace (option chosen over removing checks; preserving canonical seed validation discipline).

### Validator pipeline slots boundary doc updated

Following P4 closure-pass-extension pattern (commit 379f5b40), TIT_001 V1 cross-aggregate consistency rules registered in `03_validator_pipeline_slots.md`:

**Stage 0 canonical seed bootstrap rules added (C19-C25; mirror prior C2-C17 patterns):**
- C19 (TIT-C2): TitleHoldingDecl + Forge:GrantTitle title_id ∈ canonical_titles
- C20 (TIT-C3): actor_id ∈ canonical_actors
- C21 (TIT-C4): TitleBinding::Faction(faction_id) → faction_id ∈ canonical_factions
- C22 (TIT-C5): TitleBinding::Dynasty(dynasty_id) → dynasty_id ∈ canonical_dynasties
- C23 (TIT-C6): MultiHoldPolicy compliance per actor (StackableMax(N) cap)
- C24 (TIT-C7): Exclusive policy compliance per title (only 1 holder concurrently)
- C25 (TIT-C8): designated_heir alive at succession cascade time

**RUNTIME cascade rule added (C18; UNIQUE pattern — first runtime cascade C-rule registered post P4 commit):**
- C18 (TIT-C1): title-holder death (WA_006 mortality EVT-T3 actor_dies) → synchronous succession cascade same turn (per Q7 A LOCKED); cascade applies SuccessionRule (Eldest FF_001 / Designated heir / Vacate); emits TitleSuccessionTriggered EVT-T3 + TitleGranted EVT-T4 (if heir) + TitleSuccessionCompleted EVT-T1 narrative; atomic FAC_001 actor_faction_membership.role_id update if TitleAuthorityDecl.faction_role_grant Some

C18 is RUNTIME (every WA_006 actor_dies), unlike C1-C17 + C19-C25 (canonical seed bootstrap). Discipline note: rule application discipline section updated to clarify the runtime vs bootstrap distinction.

### Impact summary

- 9 V1 reject rules in title.* namespace (was 7); 5 V1+ reservations unchanged
- Total V1 reject rules across engine: 140 (was 138)
- 8 new cross-aggregate consistency rules in `03_validator_pipeline_slots.md` (C18-C25; total now 25 rules)
- All TIT_001 spec/catalog/boundary docs internally consistent post Phase 3

### V1 unchanged for other features

This commit is purely additive per I14 invariant. Pure documentation drift fix + validator pipeline slots registration. No changes to existing aggregates / EVT sub-shapes / RealityManifest fields owned by other features.

### Next steps

- **Commit 4/4 CANDIDATE-LOCK closure**: final lock + RESOLVES FF-D8/FAC-D6/REP-D9-partial/WA_006-cascade-gap declarations + `[boundaries-lock-release]`

---

## 2026-04-27 — TIT_001 Title Foundation DRAFT 2/4 — boundary updates + catalog seed + namespace registration (single `[boundaries-lock-claim]` commit; release at closure 4/4)

- **Lock CLAIMED** — TIT_001 DRAFT 2/4 commit; release at closure 4/4 commit per established 4-commit cycle (Phase 0 + DRAFT 2/4 + Phase 3 + closure)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim active
  - `01_feature_ownership_matrix.md`:
    - **NEW row** — `actor_title_holdings` aggregate (T2/Reality, sparse per-(actor, title_id) edge); registers TIT-A1..A8 axioms summary + Q1-Q10 LOCKED + 3-layer separation discipline + TIT-C1 cross-aggregate validator + cross-feature deferral resolutions (FF-D8 / FAC-D6 / REP-D9 partial / WA_006 sect-leader-death cascade gap)
    - **NEW EVT-T4 row** — TitleGranted system event (canonical seed + Forge admin + SuccessionCascade V1)
    - **NEW EVT-T8 row** — Forge:GrantTitle + Forge:RevokeTitle + Forge:DesignateHeir admin sub-shapes (3 V1)
    - **NEW EVT-T3 row** — TitleSuccessionTriggered derived event (sparse on cascade)
    - **NEW EVT-T1 row** — TitleSuccessionCompleted narrative milestone (LLM)
    - **RejectReason namespace registry** — added `title.*` → TIT_001
    - **Stable-ID prefix ownership** — added `TIT-*` row (foundation tier — Tier 5 Actor Substrate post-FF/FAC/REP; closes the political-rank triangle)
  - `02_extension_contracts.md`:
    - **§1.4 title.* namespace** — 7 V1 reject rule_ids (declared.unknown / binding.faction_unknown / binding.dynasty_unknown / holding.actor_unknown / holding.multi_hold_violation / holding.exclusive_violation / succession.heir_invalid) + 5 V1+ reservations (grant.rep_too_low / grant.progression_tier_too_low / lex_axiom.unknown / faction_election.invalid_vote / cross_reality_mismatch); all Q1-Q10 LOCKED matrix summary
    - **§2 RealityManifest extensions** — 2 OPTIONAL V1 fields: `canonical_titles: Vec<TitleDecl>` + `canonical_title_holdings: Vec<TitleHoldingDecl>`; full TitleDecl shape documented (TitleBinding 3-variant + SuccessionRule 3 V1 + 1 V1+ + MinRepGate schema-reserved + TitleAuthorityDecl with faction_role_grant V1 active + narrative_hint V1 active + lex_axiom_unlock_refs V1 schema-reserved + MultiHoldPolicy 3-variant + VacancySemantic 3-variant)
  - `99_changelog.md`: this entry
- **Files created/modified outside `_boundaries/`:**
  - `features/00_titles/TIT_001_title_foundation.md` (NEW; ~700 lines): full spec — §1 Purpose & V1 minimum scope + §2 Domain concepts (TitleDecl + TitleHoldingDecl + actor_title_holdings shapes) + §3 Aggregates + §4 RealityManifest extensions + §5 Events (T4/T3/T1) + §6 Forge Admin sub-shapes + §7 Cross-aggregate validator (succession cascade) + §8 V1 reject rules + §9 Sequence diagrams (canonical seed bootstrap + Forge admin grant + succession cascade on death) + §10 Acceptance Criteria (10 V1 + 4 V1+ deferred) + §11 V1 Minimum Delivery Summary + §12 Deferrals Catalog (TIT-D1..D12) + §13 Cross-references + §14 Status
  - `catalog/cat_00_TIT_title_foundation.md` (NEW): catalog seed with TIT-A1..A8 axioms + 22 V1 entries (TIT-1..22) + 12 V1+/V2/V2+ entries (TIT-23..34) + 12 deferrals (TIT-D1..D12) + 8 cross-aggregate consistency rules (TIT-C1..C8) + cross-feature integration map
  - `features/00_titles/_index.md`: status row update CONCEPT → DRAFT
  - `features/00_titles/00_CONCEPT_NOTES.md`: status header update Q-LOCKED 2026-04-27; §10 Q-LOCKED matrix populated with all 10 LOCKED decisions zero revisions

### Background

User-driven 4-batch Q-deep-dive 2026-04-27 LOCKED all 10 critical scope questions zero revisions (highly disciplined):

- **Batch 1/4 Q1+Q2** (foundational schema): Q1 A actor_title_holdings sparse per-(actor, title_id) edge / Q2 B Discriminated TitleBinding 3-variant enum (Faction(FactionId) / Dynasty(DynastyId) / Standalone)
- **Batch 2/4 Q3+Q6+Q7** (succession + heir designation + cascade timing): Q3 A 3 V1 SuccessionRule (Eldest FF_001 dynasty traversal / Designated canonical+Forge / Vacate) + 1 V1+ FactionElect DIPL_001 V2+ dependency / Q6 C Both author canonical declaration + Forge admin runtime override / Q7 A Immediate cascade synchronously on WA_006 mortality EVT-T3 actor_dies
- **Batch 3/4 Q4+Q10** (cross-feature schema seams REP_001 + WA_001): Q4 C V1 schema-reserved min_reputation_required (TitleDecl.min_reputation_required Option<MinRepGate> field active V1; runtime validator V1+ alongside REP-D1 runtime delta milestone) / Q10 B V1 schema-reserved lex_axiom_unlock_refs (TitleAuthorityDecl.lex_axiom_unlock_refs Vec<AxiomDeclRef> field active V1; validator V1+ via WA_001 closure pass adding 5-companion-fields uniformly: race + ideology + faction + reputation + title)
- **Batch 4/4 Q5+Q8+Q9** (multi-hold + authority + vacancy): Q5 C Per-title MultiHoldPolicy author-declared (Exclusive / StackableUnlimited default / StackableMax(N)) / Q8 A + narrative_hint TitleAuthorityDecl V1 active fields: faction_role_grant Option<FactionRoleGrant> + narrative_hint I18nBundle + lex_axiom_unlock_refs schema-reserved per Q10 / Q9 D Per-title VacancySemantic author-declared (PersistsNone default / Disabled / Destroyed)

### Cross-feature deferrals RESOLVED post TIT_001 CANDIDATE-LOCK (closure 4/4)

- **FF-D8** (FF_001): Title inheritance rules + heir succession → V1 RESOLVES (full active via SuccessionRule::Eldest reading dynasty.current_head_actor_id traversal)
- **FAC-D6** (FAC_001): Sect succession rules → V1 RESOLVES (full active via SuccessionRule::Designated + sect-master title binding to FactionId)
- **REP-D9** (REP_001): V1+ TIT_001 title-grant requires min rep → V1 PARTIAL RESOLVES (TitleDecl.min_reputation_required schema active V1; runtime gating V1+ alongside REP-D1)
- **WA_006 sect-leader-death cascade gap** (FAC_001 _index.md kernel touchpoint): Sect-leader death triggers V1+ TIT_001 succession → V1 RESOLVES (full active via TIT-C1 cross-aggregate validator C-rule joining existing C1-C17 from P4 commit)

### V1 minimum delivery summary

- **1 NEW sparse aggregate** — actor_title_holdings (T2/Reality, sparse per-(actor, title_id) edge)
- **2 RealityManifest extensions** — canonical_titles + canonical_title_holdings (both OPTIONAL V1 per composability discipline)
- **1 EVT-T4** TitleGranted (canonical seed + runtime active V1)
- **3 EVT-T8** Forge:GrantTitle + Forge:RevokeTitle + Forge:DesignateHeir (V1 active)
- **1 EVT-T3** TitleSuccessionTriggered (sparse on cascade)
- **1 EVT-T1** TitleSuccessionCompleted (narrative milestone for LLM)
- **1 cross-aggregate validator** TIT-C1 (immediate cascade on WA_006 mortality EVT-T3 actor_dies same turn) + 7 schema validators TIT-C2..C8
- **7 V1 reject rules** in `title.*` namespace + 5 V1+ reservations
- **10 V1 acceptance scenarios** AC-TIT-1..10 + 4 V1+ deferred
- **12 deferrals** (TIT-D1..D12)
- **TIT-* stable-ID prefix**

### V1 unchanged for other features

This commit is purely additive per I14 invariant. No changes to existing aggregates / EVT sub-shapes / RejectReason rules / RealityManifest fields owned by other features. PROG_001 / RES_001 / IDF_001..005 / FF_001 / FAC_001 / REP_001 / ACT_001 / PCS_001 / AIT_001 / TDIL_001 status unchanged.

### Discipline observed

- **Schema-stable / activation-deferred V1+ discipline (TIT-A8)**: TIT_001 V1 declares cross-feature gate fields stably (REP min_reputation_required + WA_001 lex_axiom_unlock_refs); activation V1+ via consumer feature milestone. Zero migration V1 → V1+. Mirror pattern from PROG_001 deferred-validator approach.
- **Per-reality author-declared discipline (TIT-A1)**: Engine schema generic; reality declares own title list (Wuxia 掌门/族长/皇帝 / Modern President/CEO / D&D King/Knight). Mirrors PROG-A1 + REP_001 + FAC_001 author-discipline.
- **3-layer separation discipline (TIT-A4)**: TIT_001 actor_title_holdings ≠ FAC_001 actor_faction_membership ≠ REP_001 actor_faction_reputation. Distinct shapes; distinct semantics; distinct queries; distinct LLM authoring prompts.
- **Per-title author-declared policy (TIT-A5)**: Each TitleDecl carries own MultiHoldPolicy + TitleAuthorityDecl + VacancySemantic; covers wuxia + D&D + modern + sci-fi reality use cases.
- **Cross-aggregate cascade pattern (TIT-C1)**: Title-holder death triggers synchronous succession cascade same turn via WA_006 mortality EVT-T3. Joins existing C1-C17 cross-aggregate consistency rules from P4 commit. Matches WA_006 mortality_state + vital_pool cascade pattern.

### Next steps

- **Commit 3/4 Phase 3 cleanup**: self-review fixes + downstream coordination notes
- **Commit 4/4 CANDIDATE-LOCK closure**: final lock + RESOLVES FF-D8/FAC-D6/REP-D9-partial/WA_006-cascade-gap; `[boundaries-lock-release]`

---

## 2026-04-27 — CULT_001 V2+ ENTIRELY DEFERRED (self-correction; PROG-A1 axiom preservation; single `[boundaries-lock-claim+release]` commit)

- **Lock CLAIMED + RELEASED** in single combined commit — pure documentation correction; zero schema/aggregate/EVT change
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim + release in single commit
  - `99_changelog.md`: this entry
- **Files modified outside `_boundaries/`:**
  - `features/00_progression/PROG_001_progression_foundation.md`:
    - **§14.15 REWRITTEN** — heading changed from "Future CULT_001 Cultivation Foundation (V1+ priority per IDF roadmap)" to "CULT_001 Cultivation Foundation — V2+ ENTIRELY DEFERRED (2026-04-27 stress-test correction)"; full rationale section added (PROG-A1 axiom citation + 9-system realm-hierarchy comparison + 4 sub-sections §14.15.1 V1 cultivation realities mechanism / §14.15.2 V2+ CULT_001 reframing as template library / §14.15.3 stress-test verdict 11-system audit / §14.15.4 V1 sufficiency guarantee)
    - **§20.3 future-features list updated** — CULT_001 entry rewritten from "V1+ extension; PROG_001 V1 sufficient for tu tiên without CULT_001" to "V2+ ENTIRELY DEFERRED" with reframed scope (template/convention library only) + cross-reference to §14.15
  - `catalog/cat_00_PROG_progression.md`:
    - **Coordination/discipline notes section** — added CULT_001 V2+ entirely deferred bullet documenting stress-test correction + PROG-A1 axiom + 11-system audit + V2+ template-library reframing + downstream propagation note (REP_001/FAC_001/FF_001/IDF/AIT_001/TDIL_001 references "V1+ CULT_001" become "V2+ CULT_001" naturally; deferral semantics unchanged)

### Background — what triggered the self-correction

User question 2026-04-27 (after PROG-D33..D37 commit b20c4dcb): *"tôi quên mất là chúng ta sai rồi — CULT_001 đang fix stage nhưng mỗi reality có cách tu luyện khác nhau, cảnh giới và chỉ số sức mạnh mỗi cảnh giới cũng khác nhau?"*

Tôi đã propose CULT_001 V1 với:
- "7-realm × 4-stage taxonomy (Ngưng Khí → Vấn Đỉnh)" — HARDCODED Tiên Nghịch realms vào engine
- "Spirit Root (Linh Căn) 5-element Kim/Mộc/Thủy/Hỏa/Thổ" — HARDCODED Đông Á ngũ hành
- "I18nBundle realm names — Vietnamese cultivation names" — HARDCODED genre labels

Đây là **violation of PROG-A1 axiom** ("Engine cannot fix progression schema; modern social ≠ tu tiên cultivation ≠ traditional D&D. Author declares ProgressionKindDecl per reality. Empty schema = sandbox/freeplay reality with no progression valid V1").

### 11-system stress-test verdict — different realities have different cultivation systems

Each reality declares own cultivation hierarchy + stat axes + power scaling per-reality, NOT engine-fixed:

- **Tiên Nghịch (Xian Ni)**: 12 realms (Ngưng Khí → Vấn Đỉnh → Âm Hư + Dương Thực transition → Khuy Niết → Tịnh Niết → Toái Niết) + Step 4 Đạp Thiên 9-tier extension
- **Đấu Phá Thương Khung**: 9-tier (Đấu Giả → Đấu Sư → Đấu Linh → Đấu Vương → Đấu Hoàng → Đấu Tông → Đấu Tôn → Đấu Thánh → Đấu Đế)
- **Phàm Nhân Tu Tiên Truyện**: 8-tier (Luyện Khí → Trúc Cơ → Kết Tinh → Nguyên Anh → Hóa Thần → Luyện Hư → Đại Thừa → Độ Kiếp)
- **Tru Tiên (Zhu Xian)**: dual-axis sword-cultivation + spirit-cultivation
- **Cầu Ma (Renegade Immortal sequel)**: Body Ancient parallel-axis to Qi cultivation
- **Thế Giới Hoàn Mỹ**: Dragon Transformation Realm hierarchy
- **Kim Dung wuxia (kiếm hiệp)**: 1st rate / 2nd rate / 3rd rate experts (no realms; no immortality)
- **Modern realities**: XP + Level only (no cultivation)
- **Sci-fi cyberpunk**: cybernetic implant tiers, AI assimilation ranks (no qi)

PROG_001 V1 substrate ALREADY handles ALL of these via per-reality `ProgressionKindDecl` + `TierDecl` (flat list bijection for 2D realm+stage) + `I18nBundle` (per-locale realm names) + `derives_from` (Spirit Root → cultivation rate) + `BreakthroughCondition` (item + location + mentor + time-window) + canonical_traits (Spirit Root attribute) + cross-aggregate validators (lifespan-realm coupling). NO new feature needed V1.

### Decision

**CULT_001 V2+ entirely deferred.** Reframed as **template/convention library** (non-engine, out-of-features/ folder):
- Pre-built `ProgressionKindDecl` templates for common genres (TienNghiPath12 / DauPhaPath9 / PhamNhanPath8 / KimDungWuxia3Rate / ModernLevelOnly / SciFiCyberRanks)
- Authoring design guide markdown for reality authors writing custom cultivation
- Convention catalog (standardized canonical_traits field naming if author opts-in)
- Cross-cutting helper utilities (MultiMethodPolicy, lifespan-realm coupling, tribulation event templates) — emerge from V1 author feedback NOT engine prescription

**No engine schema/aggregates/EVTs/namespace.** NOT a foundation/Tier-5+ feature.

### What's preserved (committed b20c4dcb still valid)

PROG-D33..D37 cross-cultivation extensibility deferrals committed b20c4dcb stand UNCHANGED — they future-proof PROG_001 against ANY per-reality cultivation system authors might invent V1+, regardless of CULT_001 existence. Specifically:
- PROG-D33 V1+30d: Cross-actor TrainingSource (dual cult / demonic absorb / master-pet / family-bond) — applies to per-reality declarations
- PROG-D34 V1+30d: RawValueDecrement active (drain/leech for cauldron mechanics + lifespan-burn) — per-reality
- PROG-D35 V2: derives_from cross-feature source (FF/FAC/REL state → rate multiplier) — per-reality
- PROG-D36 V1+30d: BreakthroughCondition::KarmaThreshold variant (heart demon karma gating) — per-reality
- PROG-D37 V2: RebirthBonusDecl RealityManifest extension (rebirth cumulative per-death bonus) — per-reality

### Downstream propagation (not blocking; natural decay)

25 docs reference "CULT_001 V1+ priority" or similar across REP_001 / FAC_001 / FF_001 / IDF_001..005 / AIT_001 / TDIL_001 / catalog files / concept notes / reference surveys. These references remain VALID with semantic change "V1+ → V2+" — the deferral concept (CULT_001 ships later) is unchanged; only the timing label updates. Mass-rewrite NOT performed in this commit (would be churn for naturally-out-of-date references). Each downstream doc updates organically when its closure pass / next-priority commit fires.

PROG_001 §14.15 + §20.3 + cat_00_PROG_progression.md are the AUTHORITATIVE sources for CULT_001 boundary clarity; all downstream docs defer to these for current status.

### V1 PROG_001 behavior unchanged

Pure documentation correction. Zero schema change. PROG_001 status remains DRAFT. No LOCK promotion. No new aggregate/EVT/namespace.

### Next priority (post this commit)

CULT_001 was the listed "next priority" in multiple folder closure roadmaps. With V2+ defer, next priority candidates:

| Candidate | Justification | Readiness |
|---|---|---|
| **TIT_001 Title Foundation** | Heir succession via FF_001 + FAC_001 + min REP_001 rep; pre-recommended in REP_001/FAC_001 closure changelogs | Foundation 6/6 + Tier 5 ACT_001/PCS_001/IDF/RES/REP/FAC/FF complete; ready |
| **PO_001 Player Onboarding** | UI flow consumes PCS_001 primitives Forge:RegisterPc + Forge:BindPcUser per PCS-D1; resolves "V1 character creation" gap | Pre-recommended in PCS_001 folder closure roadmap; ready |
| **DIPL_001 Diplomacy Foundation** | Inter-faction politics V1+ priority; consumes FAC_001 + REP_001 | Tier 5+ scope; ready |
| **AI-controls-PC-offline activation** | Cross-ref ACT-D1; chorus_metadata sparse PC V1+ activation | Schema-additive only; ready |
| **PROG_001 / RES_001 / AIT_001 / TDIL_001 closure passes** | Promote DRAFT → CANDIDATE-LOCK; resolves §20.2 deferred follow-ups | Ongoing closure-pass discipline |
| **SPIKE_01 turn 5 integration test** | First end-to-end turn pipeline test; validates 6 foundations + 8 Tier 5 features integrated | Integration test design phase |

User to pick next priority post this commit.

---

## 2026-04-27 — PROG_001 closure-pass-extension: 5 NEW deferrals D33..D37 for cross-cultivation extensibility (single `[boundaries-lock-claim+release]` commit)

- **Lock CLAIMED + RELEASED** in single combined commit — small additive deferral catalog growth; no V1 behavior change; no PROG_001 LOCK boundary touch (PROG_001 status DRAFT)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim + release in single commit
  - `99_changelog.md`: this entry
- **Files modified outside `_boundaries/`:**
  - `features/00_progression/PROG_001_progression_foundation.md`:
    - **§1 V1 NOT shipping table** — APPENDED 5 new rows (PROG-D33..D37)
    - **§18 Deferrals Catalog** — header updated `PROG-D1..D30` → `PROG-D1..D37`; PROG-D33/D34/D36 added to V1+30d category; PROG-D35/D37 added to V2 category
    - **NEW §18.1** "PROG-D33..D37 cross-cultivation extensibility audit (2026-04-27 closure-pass-extension)" — documents 5 gap-filling deferrals + 11-system stress-test verdict + 3 NATIVELY-supported V1 systems + 1 already-reserved V1+30d (PROG-D2) + 1 already-reserved V1+30d (Q6b Item ActorRef) + 1 covered by FAC_001+PROG-D10 (sect ActorClassMatch)
  - `catalog/cat_00_PROG_progression.md`:
    - APPENDED 5 new catalog rows PROG-38..42 after PROG-37 (V3+ ResourceBound)
    - Section header updates: V1+30d count 5 → 8 (PROG-27..31 + 38-40); V2+ count 6 → 8 (PROG-32..37 + 41-42)

### Background

User-driven CULT_001 stress-test pre-audit 2026-04-27: BEFORE locking CULT_001 as thin specialization layer on top of PROG_001 (per PROG_001 §14.15 boundary clarity "CULT_001 is a SUB-FEATURE of PROG_001 (V1+ extension); not a competing foundation"), user requested verification that PROG_001's design is future-proof against exotic cultivation systems beyond standard tu tiên realm progression.

Web survey + analysis covered 11 cultivation systems from xianxia/xuanhuan/wuxia genre:
1. Body cultivation parallel-axis (Cầu Ma 求魔 Wang Lin Ancient Body / Hoàn Mỹ 完美世界 Chen Dong)
2. Wuxia neigong/waigong (kiếm hiệp internal/external martial arts; Shaolin/Wudang/Wudang sect philosophy)
3. Dual cultivation (Mị ma song tu / yin-yang / charm demon / Su Yang dual-cultivation novels)
4. Family/clan cultivation (đa phúc đa tử — many-wives-many-sons cultivation tropes)
5. Rebirth cultivation (chết trùng sinh — Rebirth of the God Emperor / Villainous Rebirth / Path of Lazy Immortal)
6. Lifespan-burn cultivation (Cultivation Too Hard / Lifespan Burning System / Cultivation: I Can Steal Lifespan from Spirit Beasts)
7. Demonic cultivation 魔修 (Wei Wuxian Mo Dao Zu Shi cauldron / human cauldron mechanics)
8. Heart demon / karma cultivation (心魔 / 功德 / 业力 — Inner Demon Tribulation)
9. Alchemy / Talisman / Array cultivation (orthogonal axes 丹道 / 符箓 / 阵法)
10. Pet/beast bond cultivation (Đấu Phá Pokemon-like beast tier cultivation)
11. Sword spirit / 御剑 cultivation (Cultivation of Weapon Spirits / artifact-spirit growth)

### Verdict

**PROG_001 design IS future-proof.** Stress-test results:
- ✅ **3 NATIVELY supported V1**: body cultivation parallel-axis (multiple ProgressionKindDecls + BodyOrSoul=Body each); alchemy/talisman/array orthogonal axes (multiple ProgressionKindDecls); lifespan-burn one-actor self-sacrifice (Action interaction_kind + cross-aggregate hook to actor_core.lifespan_remaining)
- ✅ **2 already-reserved V1+30d** (no new deferral): demonic tribulation/deviation 走火入魔 → PROG-D2; sword-spirit / artifact growth → Q6b PROG_001 §3.1 Item ActorRef reserved
- ✅ **1 covered by FAC_001 + PROG-D10**: wuxia neigong/waigong sect martial arts via FAC_001 sect membership + ActorClassMatch condition deferred V1+30d
- ⚠️ **5 require NEW deferrals (D33..D37; all schema-additive per I14 invariant — zero PROG_001 redesign)**:
  - PROG-D33 V1+30d: Cross-actor `TrainingSource::CrossActor` (dual cult / demonic absorb / master-pet / family-bond)
  - PROG-D34 V1+30d: `ProgressionDeltaKind::RawValueDecrement` active (drain/leech for cauldron mechanics + lifespan-burn)
  - PROG-D35 V2: `derives_from` cross-feature source (FF_001/FAC_001/REL_001 state → rate multiplier; family-count-multiplies-power)
  - PROG-D36 V1+30d: `BreakthroughCondition::KarmaThreshold` variant (heart demon karma gating)
  - PROG-D37 V2: `RebirthBonusDecl` RealityManifest extension (rebirth cumulative per-death bonus)

### Discipline / rationale for adding deferrals NOW (vs CULT_001 closure-pass propagation later)

Per user direction 2026-04-27: "nên làm A từ bây giờ — để sau này có thêm hệ thống tu luyện mới thì cũng giảm khả năng refactor của PROG_001". Pre-emptive registration of 5 deferrals reduces future refactor risk because:
1. **Visible in PROG_001 catalog** — future agents reading PROG_001 see all extensibility gaps documented up-front
2. **Cross-feature audit trail** — each deferral cites cultivation system + novel reference for context
3. **Schema-additive only** — no V1 behavior change; PROG_001 LOCK boundary preserved
4. **CULT_001 + future cultivation features (REBIRTH_001 / KARMA_001) inherit clean foundation** — extensions follow already-documented seams, not retroactive patches

### V1 PROG_001 behavior unchanged

This commit does NOT modify any V1 PROG_001 mechanism, schema, or aggregate. Pure documentation growth (deferral catalog + audit findings). PROG_001 status remains DRAFT (unchanged); no LOCK promotion; no closure pass on PROG_001 itself.

### Cross-feature impact (none V1; all V1+)

- CULT_001 V1+ may reference PROG-D33..D37 in its DRAFT for clarity but is NOT blocked by them
- WA_001 Lex axiom hook may reference PROG-D36 (KarmaThreshold) when V1+ karma feature ships
- WA_006 Mortality may reference PROG-D37 (RebirthBonusDecl) when V2 rebirth feature ships
- FAC_001 + REP_001 + REL_001 (V1+) may reference PROG-D35 when cross-feature derives_from V2 ships
- Future REBIRTH_001 / KARMA_001 / DUAL_CULT_001 features inherit pre-documented seams

### Next priority post this commit

CULT_001 Cultivation Foundation Phase 0 kickoff (per user direction 2026-04-27 "tiếp theo tới CULT_001 wuxia"). CULT_001 proceeds as thin specialization layer on PROG_001 + ACT_001 + RES_001 + IDF_001..005 + FAC_001 + REP_001 + PCS_001 + TDIL_001 + AIT_001 + FF_001. Q-deep-dive 8 questions (Q1 2D realm+stage encoding via tier_id bijection / Q2 Cultivation Method as separate ProgressionKindId / Q3 Spirit Root + Aptitude on actor_core canonical_traits / Q4 Lifespan coupling cross-aggregate validator C-rule / Q5 V1 realm scope 7 First Step / Q6 Breakthrough trigger LLM-narrated V1 / Q7 Multi-method cap=1 V1 / Q8 Deviation V1 schema-reserved). 4-commit cycle estimated. Reference materials confirmed: chaos-actor-module/jindan-stats-bundle (Tiên Nghịch 12-realm hierarchy + Stage Early/Mid/Late/Peak + 7 Kim Đan primary stats + exponential B^r scaling) + chaos-backend-service/race-core (Tinh 5 constitutional stats + Talent system + Racial Element Integration via Element-Core registry pattern).

---

## 2026-04-27 — P4 Cross-feature consistency validator rules + Tier 5 namespace registry update (single `[boundaries-lock-claim+release]` commit)

- **Lock CLAIMED + RELEASED** in single combined commit — P4 closure-pass-extension; small additive update to validator pipeline slots boundary doc
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim + release in single commit
  - `03_validator_pipeline_slots.md`:
    - **EXPANDED** §"Stage → rule_id namespace matrix" with 14 NEW Tier 5 namespace entries (resource/race/language/personality/origin/ideology/family/faction/progression/reputation/actor/pc/ai_tier/time_dilation); shows V1 rule counts + V1+ reservations + validation timing (Stage 0 canonical seed + Stage 3.5 + Forge admin + V1+ runtime per namespace)
    - Stage 0 row updated to reference NEW §"Stage 0 canonical seed cross-aggregate consistency rules"
    - **NEW SECTION** "Stage 0 canonical seed cross-aggregate consistency rules" documenting 17 cross-aggregate rules (C1-C17) with owner-feature attribution + reject rule references
  - `99_changelog.md`: this entry

### Background

P4 audit gap discovered in main session 2026-04-27 audit "actor canonical seed init readiness review":
- Cross-aggregate consistency rules at canonical seed not explicitly documented (C1 actor_core.current_region_id ↔ entity_binding.scope_id; C2 spawn_cell ∈ places; C3 glossary_entity_id ∈ canon)
- ACT_001 + PCS_001 + AIT_001 + TDIL_001 namespaces not added to validator pipeline matrix (~87+ V1 reject rules across 14 Tier 5 features absent from registry)

### What's documented

**14 namespaces added to Stage → rule_id matrix** (Tier 5 substrate):
- resource.* (RES_001) — 12 V1 + 3 V1+
- race.* / language.* / personality.* / origin.* / ideology.* (IDF_001..005) — 19 V1 + 15 V1+ total
- family.* (FF_001) — 8 V1 + 4 V1+
- faction.* (FAC_001) — 8 V1 + 4 V1+
- progression.* (PROG_001) — 7 V1 + 6 V1+
- reputation.* (REP_001) — 6 V1 + 4 V1+
- actor.* (ACT_001) — 8 V1 + 3 V1+ (P2 LOCKED added spawn_cell_unknown + glossary_entity_unknown)
- pc.* (PCS_001) — 7 V1 + 3 V1+
- ai_tier.* (AIT_001) — 8 V1 + 4 V1+
- time_dilation.* (TDIL_001) — 4 V1 + 6 V1+30d

**Total V1 reject rules across engine:** ~131 rules (~44 LLM-output pipeline Stage 3.5+ + ~87 Tier 5 substrate Stage 0 + Forge admin).

**17 cross-aggregate consistency rules at Stage 0 canonical seed** (NEW §):
- C1: actor_core.current_region_id ↔ entity_binding.scope_id (cell-tier; implicit V1 via shared spawn_cell field per P2 LOCKED; explicit V1+ if drift)
- C2: spawn_cell ∈ RealityManifest.places (P2 LOCKED 2026-04-27 — actor.spawn_cell_unknown)
- C3: glossary_entity_id ∈ knowledge-service canon (P2 LOCKED 2026-04-27 — actor.glossary_entity_unknown)
- C4: actor_origin.native_language ∈ RealityManifest.languages (IDF_002 + IDF_004)
- C5: actor_origin.default_ideology_refs ∈ RealityManifest.ideologies
- C6: actor_origin.birthplace_channel ∈ RealityManifest.places
- C7: actor_faction_membership.faction_id ∈ canonical_factions
- C8: actor_faction_membership ideology binding (resolves IDL-D2 per FAC_001 Q LOCKED)
- C9: actor_faction_reputation references (FAC_001 + EF_001)
- C10: actor_progression.kind_id ∈ progression_kinds
- C11: PcBodyMemory languages ∈ RealityManifest.languages (PCS_001 + IDF_002 cross-feature)
- C12: PcBodyMemory references ∈ knowledge-service canon (PCS_001 + knowledge-service)
- C13: V1 cap=1 PC per reality (PCS-A9 + Q9 LOCKED)
- C14: actor_chorus_metadata sparse population matches ActorKind (chorus_metadata Some ↔ NPC V1; None ↔ PC V1; ACT-A4)
- C15: mortality_config.mode = RespawnAtLocation V1 forbidden (PCS-D2 not active V1; reject pc.respawn_unsupported_v1)
- C16: actor_clocks initialization from body_memory canonical (TDIL_001 + PCS_001 + ACT_001)
- C17: AIT_001 tier_hint at canonical seed (NpcTrackingTier validation + capacity caps ≤20 Major / ≤100 Minor)

### Rule application discipline LOCKED

- Stage 0 schema validation runs at canonical seed bootstrap + Forge admin events
- Each rule's owner feature is responsible for validation logic
- Cross-reference rules belong to FIRST feature in dependency direction (e.g., IDF_004 owns C4 since actor_origin is IDF_004's aggregate)
- C1 implicit V1 via shared spawn_cell source field (P2 LOCKED); explicit V1+ if drift detected

### Closes P4 audit gap

P4 audit gap from main session 2026-04-27 audit (actor canonical seed init readiness review) now CLOSED:
- ✅ Cross-aggregate consistency rules explicitly documented (17 rules C1-C17)
- ✅ Tier 5 namespaces registered in validator pipeline matrix (14 namespaces)
- ✅ ACT_001 validator slot reflected (Stage 0 canonical seed cross-aggregate; not new pipeline stage)
- ✅ Total V1 rule registry: ~131 reject rules across engine

### Audit completion summary

Main session 2026-04-27 actor canonical seed init readiness audit closed with all 4 priorities resolved:
- P1 ACT_001 type lockdown (commit 40e853a) — ActorMood multi-axis + FlexibleState typed + GreetingObligation + PriorityTierHint
- P2 ACT_001 spawn_cell + glossary_entity_id (commits 079976c + f4d0258) — Phase 1 + Phase 2 BOTH applied
- P3 PCS_001 PC Substrate (commits 3c76f33 + 5c34b93 + 67b53cd + 7e3218e + af025eb) — 4-commit cycle complete
- P4 Cross-feature validator rules (this commit) — Tier 5 namespace registry + Stage 0 cross-aggregate consistency rules

NEW V1+ priorities post-P1+P2+P3+P4: PO_001 Player Onboarding + AI-controls-PC-offline + PCS-D2 Respawn flow + PCS-D7 A6 canon-drift detector + CULT_001 Cultivation Foundation (wuxia genre) + TIT_001 Title Foundation (heir succession) + DIPL_001 Diplomacy Foundation (V2+).

---

## 2026-04-27 — PCS_001 closure pass → CANDIDATE-LOCK + lock RELEASE (commit 4/4 FINAL)

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 2026-04-27 → None (RELEASE after 4-commit PCS_001 cycle)
  - `01_feature_ownership_matrix.md`:
    - 2 PCS_001 aggregate rows: DRAFT → **CANDIDATE-LOCK 2026-04-27 closure pass 4/4** (pc_user_binding + pc_mortality_state)
- **PCS_001 status header** in `PCS_001_pc_substrate.md`: DRAFT → CANDIDATE-LOCK 2026-04-27 (4-commit cycle complete)
- **PCS_001 §20 status transition note** updated to reflect CANDIDATE-LOCK 4/4
- **`features/06_pc_systems/_index.md` PCS_001 row** updated: status CANDIDATE-LOCK + 4-commit cycle reference
- **`features/06_pc_systems/_index.md` folder status:** OPEN → COMPLETE 2026-04-27

### PCS_001 FOUNDATION FOLDER MILESTONE SUMMARY (4 commits across single lock-cycle)

Files created (cumulative across 4 commits):
- features/06_pc_systems/_index.md (folder index; updated to COMPLETE)
- features/06_pc_systems/00_CONCEPT_NOTES.md (Q1-Q10 LOCKED + V1 scope finalized; 6-batch deep-dive 2026-04-27 reasoning)
- features/06_pc_systems/01_REFERENCE_GAMES_SURVEY.md (Phase 0 commit 3c76f33; 10 game references + Wuxia novel canon)
- features/06_pc_systems/PCS_001_pc_substrate.md (~900 line DRAFT spec; §1-§20 sections; 10 V1 AC; 10 deferrals)
- catalog/cat_06_PCS_pc_systems.md (PCS_001 DRAFT appendage with PCS-A1..A10 axioms + PCS-D1..D10 deferrals + PCS-11..PCS-20 V1 catalog entries; existing PCS-1..PCS-10 historical entries preserved)

Boundary expansions (commits 2/4 + 4/4):
- 2 NEW PCS_001-owned aggregates (pc_user_binding + pc_mortality_state)
- 1 NEW EVT-T4 System sub-type (PcRegistered)
- 5 NEW EVT-T8 Administrative sub-shapes (Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState)
- 3 V1 active EVT-T3 Derived delta_kinds (DyingTransition + DeathTransition + GhostTransition); 3 V1+ reserved (RespawnTransition + ResurrectionTransition + GhostDispersedTransition)
- 1 NEW EVT-T1 Submitted sub-type (PcTransmigrationCompleted; renamed from PcXuyenKhongCompleted per user direction; schema V1; emission V1+)
- 1 NEW namespace: `pc.*` (7 V1 rules + 3 V1+ reservations)
- 2 NEW RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init; REQUIRED V1 for kind=Pc)
- PCS-* stable-ID prefix already registered (line 148 catalog-file-per-category list); cat_06_PCS_pc_systems.md formalized with PCS-A1..A10 axioms

Q-LOCKED summary (Q1-Q10 LOCKED via 6-batch deep-dive 2026-04-27 user "approve" across all batches; 1 REFINEMENT + 1 RENAME):
- Q1 (A): PcId(Uuid) mirror NpcId + DP-A12 module-private constructor
- Q2 (A): Single pc_user_binding aggregate
- Q3 (C): Canonical seed + Forge admin V1; runtime login V1+ via PO_001 PCS-D1
- Q4 (B): Defer pc_stats_v1_stub V1+ — PROG_001 + RES_001 + PL_006 cover stats
- Q5 ⚠ REFINEMENT (D): Full PcBodyMemory schema with native_skills/motor_skills V1 empty Vec reserved
- Q6 (A): Full 4-variant LeakagePolicy V1
- Q7 (A): Full 4-state pc_mortality_state V1; V1+ Respawn flow + Resurrection deferred PCS-D2
- Q8 (A): V1 strict single-reality; V2+ Heresy via WA_002 (universal substrate discipline)
- Q9 (C): V1 cap=1 PC per reality via row count Stage 0 schema validator; V1+ relax via RealityManifest.max_pc_count Optional (PCS-D3); FAC_001 Q2 REVISION pattern
- Q10 (A): Single event PcTransmigrationCompleted; PCS_001 EVT-T1 owns; TDIL_001 actor_clocks subscribes per TDIL §10 clock-split contract

3-layer architectural model post-ACT_001 (PCS-A1..A10):
- L1 Identity (ACT_001 actor_core; PCS_001 reads)
- L2 Capability/Kind (ActorId::Pc variant; PCS_001 owns PcId newtype)
- L3 PC-specific (PCS_001 owns pc_user_binding + pc_mortality_state)

Cross-feature deferrals RESOLVED:
- **WA_006 §6 closure pass pc_mortality_state aggregate handoff** → ✅ RESOLVED via PCS_001 §3.2

Phase 3 cleanup applied (commit 3/4 7e3218e) — 5 fixes:
- S1.1 §3.1: PcBodyMemory::native_default constructor helper for native PC fallback
- S1.2 §11 sequence: extended Stage 0 schema validation flow with V1 cap=1 + mortality_config validation + body_memory_init fallback semantics
- S1.3 §15: clarified "Schema active V1 / Emission V1+" semantic distinction
- S1.4 §16 AC-PCS-3: SPIKE_01 turn 5 literacy slip AC scope clarified (V1 schema verification; V1+ A6 detection)
- S1.5 §7 subscribe pattern: V1+ AI-controls-PC-offline cross-reference (ACT-D1)

V1 quantitative summary:
- 2 PCS_001 aggregates (pc_user_binding + pc_mortality_state)
- 1 EVT-T4 + 5 EVT-T8 + 3 V1 EVT-T3 + 3 V1+ EVT-T3 + 1 EVT-T1
- 7 V1 reject rules (pc.* namespace) + 3 V1+ reservations
- 2 RealityManifest CanonicalActorDecl additive fields
- PcBodyMemory schema (SoulLayer + BodyLayer + LeakagePolicy 4-variant)
- MortalityStateValue 4-state schema + 6-variant TransitionTrigger
- 10 V1 AC + 4 V1+ deferred + 10 deferrals (PCS-D1..PCS-D10)
- ~900 line DRAFT spec
- 4-commit cycle complete

NEW V1+ priorities post-PCS_001:
- **PO_001 Player Onboarding** — UI flow consumes PCS_001 primitives (Forge:RegisterPc + Forge:BindPcUser per PCS-D1)
- **AI-controls-PC-offline V1+** — activates ACT_001 actor_chorus_metadata for PC when offline (cross-ref ACT-D1; pc_user_binding.current_session = None trigger)
- **PCS-D2 Respawn flow** — Dying → Alive transition activation (V1 Dying state FROZEN)
- **PCS-D7 A6 canon-drift detector** — body_memory.{soul, body}.knowledge_tags integration for SPIKE_01 turn 5 literacy slip detection (05_llm_safety V1+)
- **PCS-D5 NPC body-substitution** — V1+ shared body_memory schema (cross-ref ACT-D5)

---

## 2026-04-27 — PCS_001 PC Substrate DRAFT promotion + boundary register (commit 2/4)

- **Lock CLAIMED** at start of this commit (`[boundaries-lock-claim]`); release deferred to commit 4/4 closure pass per PCS_001 4-commit cycle
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-27 (PCS_001 DRAFT 2/4 promotion + boundary register; 5h TTL)
  - `01_feature_ownership_matrix.md`:
    - 2 NEW aggregate rows: pc_user_binding + pc_mortality_state (BOTH PCS_001-owned; pc_mortality_state with WA_006 §6 closure pass handoff RESOLVED)
    - PRESERVED: 4 existing aggregates (pc_user_binding REPLACES old "(when designed)" stub; pc_mortality_state REPLACES old WA_006-handoff stub)
    - 1 NEW EVT-T4 sub-type entry: PcRegistered (PCS_001 owner)
    - 5 NEW EVT-T8 sub-shape entries: Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState (PCS_001 owner; uses WA_003 forge_audit_log)
    - 1 NEW EVT-T3 entry: pc_mortality_state delta_kinds (DyingTransition + DeathTransition + GhostTransition V1 active; RespawnTransition + ResurrectionTransition + GhostDispersedTransition V1+ reserved)
    - 1 NEW EVT-T1 sub-type entry: PcTransmigrationCompleted (renamed from PcXuyenKhongCompleted per user direction 2026-04-27; English type name; schema active V1; emission V1+ deferred PCS-D-N)
    - RealityManifest envelope row UPDATED: PCS_001 CanonicalActorDecl additive fields (body_memory_init Option<PcBodyMemory> + user_id_init Option<UserId>; REQUIRED V1 for kind=Pc; sparse PC-only)
    - RejectReason namespace: appended `pc.*` → PCS_001
    - PCS-* stable-ID prefix: already registered (line 148 catalog-file-per-category list); cat_06_PCS_pc_systems.md updated this commit with PCS-A1..A10 axioms + PCS-D1..D10 deferrals + PCS-11..PCS-20 V1 catalog entries
  - `02_extension_contracts.md`:
    - §1.4 namespace registration: `pc.*` (7 V1 rules + 3 V1+ reservations)
    - §2 RealityManifest CanonicalActorDecl additive fields documented (body_memory_init + user_id_init REQUIRED for kind=Pc V1) + V1+ max_pc_count Optional reservation note (PCS-D3)
  - `99_changelog.md`: this entry

### PCS_001 DRAFT MILESTONE SUMMARY (commit 2/4 of 4-commit cycle)

Files created/modified outside `_boundaries/` (commit 2/4):
- features/06_pc_systems/_index.md (DRAFT row updated; PCS_001 active)
- features/06_pc_systems/00_CONCEPT_NOTES.md (already at Q-LOCKED status; commit 1/4 5c34b93)
- features/06_pc_systems/01_REFERENCE_GAMES_SURVEY.md (Phase 0 commit 3c76f33)
- features/06_pc_systems/PCS_001_pc_substrate.md (~900 line DRAFT spec — NEW THIS COMMIT)
- catalog/cat_06_PCS_pc_systems.md (PCS_001 DRAFT appendage with PCS-A1..A10 + PCS-D1..D10 + PCS-11..PCS-20 entries)

Boundary expansions (commit 2/4):
- 2 NEW PCS_001-owned aggregates (pc_user_binding + pc_mortality_state)
- 1 NEW EVT-T4 System sub-type (PcRegistered)
- 5 NEW EVT-T8 Administrative sub-shapes (Forge:RegisterPc + Forge:BindPcUser + Forge:EditPcUserBinding + Forge:EditBodyMemory + Forge:EditPcMortalityState)
- 3 V1 active EVT-T3 Derived delta_kinds (DyingTransition + DeathTransition + GhostTransition); 3 V1+ reserved (RespawnTransition + ResurrectionTransition + GhostDispersedTransition)
- 1 NEW EVT-T1 Submitted sub-type (PcTransmigrationCompleted; schema V1; emission V1+)
- 1 NEW namespace: `pc.*` (7 V1 rules + 3 V1+ reservations)
- 2 NEW RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init); REQUIRED V1 for kind=Pc

Q-LOCKED summary (Q1-Q10 LOCKED via 6-batch deep-dive 2026-04-27 user "approve" across all batches; 1 REFINEMENT + 1 RENAME):
- Q1 (A): PcId(Uuid) mirror NpcId + DP-A12 module-private constructor
- Q2 (A): Single pc_user_binding aggregate (user_id + current_session + body_memory + last_login + last_xuyenkhong)
- Q3 (C): Canonical seed + Forge admin V1 (Forge:RegisterPc + Forge:BindPcUser); runtime login V1+ via PO_001 PCS-D1
- Q4 (B): Defer pc_stats_v1_stub V1+ — PROG_001 + RES_001 + PL_006 cover stats
- Q5 ⚠ REFINEMENT (D): Full PcBodyMemory schema with native_skills/motor_skills V1 empty Vec reserved
- Q6 (A): Full 4-variant LeakagePolicy V1 (NoLeakage / SoulPrimary / BodyPrimary / Balanced)
- Q7 (A): Full 4-state pc_mortality_state V1 (Alive/Dying/Dead/Ghost); V1 active death transitions; V1+ Respawn flow + Resurrection deferred PCS-D2
- Q8 (A): V1 strict single-reality; V2+ Heresy via WA_002 (universal substrate discipline)
- Q9 (C): V1 cap=1 PC per reality via row count Stage 0 schema validator; V1+ relax via RealityManifest.max_pc_count Optional (PCS-D3); FAC_001 Q2 REVISION pattern
- Q10 (A): Single event PcTransmigrationCompleted (renamed from PcXuyenKhongCompleted per user direction); PCS_001 EVT-T1 owns; TDIL_001 actor_clocks subscribes per TDIL §10 clock-split contract

3-layer architectural model post-ACT_001 (PCS-A1..A10):
- L1 Identity (ACT_001 actor_core; PCS_001 reads)
- L2 Capability/Kind (ActorId::Pc variant; PCS_001 owns PcId newtype)
- L3 PC-specific (PCS_001 owns pc_user_binding + pc_mortality_state)

Cross-feature deferrals RESOLVED (commit 4/4 closure will note):
- WA_006 §6 closure pass pc_mortality_state aggregate handoff → ✅ RESOLVED via PCS_001 §3.2

V1 quantitative summary:
- 2 PCS_001 aggregates (pc_user_binding + pc_mortality_state)
- 1 EVT-T4 + 5 EVT-T8 + 3 V1 EVT-T3 + 3 V1+ EVT-T3 + 1 EVT-T1 (schema V1 / emission V1+)
- 7 V1 reject rules (pc.* namespace) + 3 V1+ reservations
- 2 RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init); REQUIRED V1 for kind=Pc
- PcBodyMemory schema (SoulLayer + BodyLayer + LeakagePolicy 4-variant)
- MortalityStateValue 4-state schema + 6-variant TransitionTrigger
- 10 V1 AC + 4 V1+ deferred + 10 deferrals (PCS-D1..PCS-D10)
- ~900 line DRAFT spec
- 4-commit cycle (Phase 0 3c76f33 + Q-LOCKED 1/4 5c34b93 + DRAFT 2/4 this commit + Phase 3 3/4 + closure+release 4/4)

Lock CLAIMED this commit; release deferred to commit 4/4 closure pass.

---

## 2026-04-27 — ACT_001 Phase 2 P2 closure-pass-extension — CanonicalActorDecl spawn_cell + glossary_entity_id ADD (single `[boundaries-lock-claim+release]` commit)

- **Lock CLAIMED + RELEASED** in single combined commit — small additive P2 closure-pass-extension; no new aggregate; no new EVT sub-type; no new namespace; just additive fields + 2 V1 reject rules
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claim + release in single commit
  - `02_extension_contracts.md`:
    - §2 CanonicalActorDecl shape (post-unify): ADD 2 REQUIRED V1 fields:
      * `pub spawn_cell: ChannelId` — initial cell location (cell-tier channel from RealityManifest.places); cross-validated at canonical seed; populates ActorCore.current_region_id at bootstrap; EF_001 EntityBorn cell_id sourced from this field
      * `pub glossary_entity_id: GlossaryEntityId` — actor's primary glossary entry (DISTINCT from core_beliefs_ref); populates ActorCore.glossary_entity_id at bootstrap
    - §1.4 `actor.*` namespace: 6 V1 → 8 V1 rules (ADD `actor.spawn_cell_unknown` + `actor.glossary_entity_unknown`); V1+ reservations unchanged at 3
  - `99_changelog.md`: this entry

### Background

P2 audit gap discovered in main session 2026-04-27 deep-dive "actor canonical seed init readiness review":
- ActorCore §3.1 has `glossary_entity_id` + `current_region_id` fields (renamed from old `npc` schema)
- But CanonicalActorDecl shape post-unify was MISSING source fields
- Without these, RealityBootstrapper had no source-of-truth for "where does Du sĩ start?" or "what's Du sĩ's primary glossary entry?"

### Phase 1 P2 (commit 079976c — feature-folder + catalog)

Applied ACT_001 spec changes (no boundary lock needed):
- §3.1 ActorCore: clarified glossary_entity_id + current_region_id source fields
- §10 Cross-service handoff: extended Stage 0 schema validation rules + 7-row field-mapping table
- §11 Sequence: Wuxia 5-actor canonical seed example REVISED with explicit spawn_cell + glossary_entity_id
- §9 Failure-mode UX: 2 NEW V1 reject rules (spawn_cell_unknown + glossary_entity_unknown)
- §16 Boundary registrations: noted Phase 2 P2 follow-up needed
- catalog/cat_00_ACT_actor_foundation.md: ACT-20 entry for CanonicalActorDecl shape

### Phase 2 P2 (this commit — boundary §2)

Mechanical additive boundary update:
- §2 CanonicalActorDecl shape: ADD 2 fields (spawn_cell + glossary_entity_id; both REQUIRED V1)
- §1.4 actor.* namespace: ADD 2 V1 reject rules
- Closes P2 audit gap completely (Phase 1 + Phase 2 = full P2 resolution)

### Cross-feature impact

- EF_001 EntityBorn `cell_id` payload sourced from CanonicalActorDecl.spawn_cell at canonical seed (no API change to EF_001; just source clarification)
- PF_001 places cross-validated at canonical seed (reject `actor.spawn_cell_unknown` if spawn_cell ∉ RealityManifest.places)
- knowledge-service canon cross-validated at canonical seed (reject `actor.glossary_entity_unknown` if missing)
- ACT_001 ActorBorn carries actor_id + kind + traits_summary (unchanged)
- ACT_001 owner-service writes actor_core row populating glossary_entity_id + current_region_id from CanonicalActorDecl source fields

### V1 quantitative summary (ACT_001 post-Phase-2 P2)

- 4 ACT_001 aggregates (UNCHANGED)
- 8 V1 reject rules (`actor.*` namespace) + 3 V1+ reservations (was 6 V1; +2 from P2)
- RealityManifest CanonicalActorDecl shape: 11 V1 fields (was 9; +2 from P2)
- EF_001 EntityBorn cell_id source clarified (was implicit; now explicit from CanonicalActorDecl.spawn_cell)

P1 + P2 (now both complete) close the type definition + spawn_cell audit gaps. Remaining P-priorities:
- P4 cross-feature consistency validator rules + ACT_001 validator slot in 03_validator_pipeline_slots.md
- P3 PCS_001 PC Substrate cycle (BLOCKED gap from audit; biggest impact)

---

## 2026-04-27 — TDIL_001 Time Dilation Foundation DRAFT promotion + closure-pass cascade (single combined `[boundaries-lock-claim+release]` commit)

- **Lock CLAIMED then RELEASED** in single combined commit (`[boundaries-lock-claim+release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-27 (claim) → None (release after combined commit)
  - `01_feature_ownership_matrix.md`:
    - NEW T2/Reality aggregate row `actor_clocks` (owner=Actor; ALWAYS-PRESENT V1; mirror actor_core pattern; 3 clocks i64: actor_clock + soul_clock + body_clock)
    - NEW stable-ID prefix row `TDIL-*` (TDIL_001 ownership)
  - `02_extension_contracts.md`:
    - §1.4 NEW namespace `time_dilation.*` (4 V1 rule_ids + 6 V1+30d reservations)
    - §2 RealityManifest INLINE field additions block (TDIL_001 extensions): MAP_001 MapLayoutDecl `time_flow_rate: f32` + PF_001 PlaceDecl `time_flow_rate_override: Option<f32>` + ACT_001 CanonicalActorDecl `initial_clocks: Option<InitialClocksDecl>`; NEW T2/Reality aggregate `actor_clocks` cited (NOT a RealityManifest field)
- **Files created:**
  - `features/17_time_dilation/TDIL_001_time_dilation_foundation.md` (~700 lines, 20 sections, 17 V1 catalog entries TDIL-1..17 + 6 V1+30d TDIL-18..23 + 4 V2/V3+ TDIL-24..27; 10 axioms TDIL-A1..A10; 10 V1 acceptance scenarios AC-TDIL-1..10; 4 V1 + 6 V1+30d RejectReason rule_ids)
  - `catalog/cat_17_TDIL_time_dilation.md` (27 entries; 17 V1 + 6 V1+30d + 4 V2/V3+; architecture-scale catalog seed)
- **Files modified outside `_boundaries/` (closure-pass cascade):**
  - `features/17_time_dilation/_index.md` — TDIL_001 status CONCEPT → DRAFT 2026-04-27; catalog reference activated
  - `features/17_time_dilation/00_CONCEPT_NOTES.md` — status SUPERSEDED → DRAFT 2026-04-27 (Q1-Q12 ALL LOCKED via 4-batch deep-dive)
  - `features/00_progression/PROG_001_progression_foundation.md` — closure-pass-extension notice: Q3f day-boundary Generator → per-turn O(1) per TDIL-A3 (Scheduled:CultivationTick reads body_clock or soul_clock per BodyOrSoul; PROG-D19 RES_001 alignment resolved)
  - `features/00_resource/RES_001_resource_foundation.md` — closure-pass-extension notice: Q4 day-boundary 4-Generators → per-turn O(1) per TDIL-A3 (channel-bound vs actor-bound matrix added; CellProduction/NPCAutoCollect/CellMaintenance read wall_clock; HungerTick reads body_clock)
  - `features/16_ai_tier/AIT_001_ai_tier_foundation.md` — closure-pass-extension notice: §7.5 Tracked NPC lazy materialization per-day replay → O(1) elapsed-time computation per TDIL-A3 + TDIL-A7 (cross-realm observation O(1) regardless of magnitude)
  - `features/06_pc_systems/00_AGENT_BRIEF.md` §S8 — TDIL_001 clock-split contract reference: xuyên không initializes new PC actor_clock=0 + soul_clock=source_a.soul_clock + body_clock=source_b.body_clock per TDIL_001 §8 (Q11 LOCKED)

### TDIL_001 architecture-scale feature MILESTONE SUMMARY

NOT a foundation tier feature (foundation 6/6 closed at PROG_001). TDIL_001 is **architecture-scale Tier 5+ Actor Substrate scaling/architecture feature** mirroring AIT_001 + ACT_001 pattern. Opt-in per reality:
- Modern social reality → no time dilation (default 1.0 everywhere; engine-canonical real-time)
- Tu tiên reality → rich time dilation config (heaven 0.0027× / Dragon Ball chamber 365× / per-cell overrides)

User concerns RESOLVED 2026-04-27:
1. **Cultivation rate mismatch** (newbie 練氣 vs 元嬰 elder same-clock) → ✅ RESOLVED via per-channel `time_flow_rate` + per-cell `time_flow_rate_override` + actor_clocks aggregate
2. **Multi-realm time variance** (Tây Du Ký 天上一日人間一年) → ✅ RESOLVED via per-channel `time_flow_rate` + per-realm turn streams (TDIL-A6)
3. **Time chambers** (Dragon Ball 精神時光屋 1 day = 1 year) → ✅ RESOLVED via cell-level `time_flow_rate_override` (REPLACE semantic)
4. **PvP newbie-gank prevention** → ✅ RESOLVED via Lex axiom (existing) + newbie-zone slow rate (high-tier wastes time visiting)

User architectural insights LOCKED 2026-04-27:
1. **Per-turn O(1) Generator semantic** (TDIL-A3) — corrects PROG/RES/AIT day-boundary lock; computation = base × elapsed × multiplier
2. **Atomic-per-turn travel** (TDIL-A5) — actor in EXACTLY ONE channel per turn; no mid-turn cross-channel
3. **Per-realm turn streams** (TDIL-A6) — heaven_clock independent from mortal_clock; idle channels frozen
4. **4-clock model** (TDIL-A2) — realm + actor + soul + body; soul/body separability enables xuyên không state preservation

Q-LOCKED summary (Q1-Q12 ALL LOCKED via 4-batch deep-dive 2026-04-27):
- Batch 1: Q1 (Convention B) + Q2 (4-clock model) + Q3 (channel + cell layering REPLACE)
- Batch 2: Q4 (per-turn O(1) Generator) + Q5 (atomic-per-turn travel)
- Batch 3: Q6 (clock-source matrix locked) + Q7 (atomic travel detail) + Q8 (cross-realm observation O(1))
- Batch 4: Q9 (LLM context dilation hint) + Q10 (replay determinism FREE) + Q11 (xuyên không clock-split) + Q12 (worldline monotonicity)

10 architectural axioms LOCKED (TDIL-A1..A10):
- TDIL-A1 Convention B time_flow_rate (proper time per wall time; range V1 [0.001, 1000.0])
- TDIL-A2 4-clock model (realm + actor + soul + body)
- TDIL-A3 Per-turn O(1) Generator semantic (replaces PROG/RES/AIT day-boundary)
- TDIL-A4 Channel-bound vs actor-bound generator discipline
- TDIL-A5 Atomic-per-turn travel
- TDIL-A6 Per-realm turn streams
- TDIL-A7 Cross-realm observation O(1)
- TDIL-A8 Worldline monotonicity (Forge past-clock edits FORBIDDEN PERMANENTLY V1+)
- TDIL-A9 Replay determinism FREE V1 (static rates + per-channel turn streams + atomic travel + monotonic clocks)
- TDIL-A10 Xuyên không clock-split (soul→soul; body→body; actor=0; twin paradox preserved)

V1 quantitative summary:
- 1 NEW T2/Reality aggregate (actor_clocks; ALWAYS-PRESENT V1; mirror actor_core pattern)
- 0 NEW EVT-T4 (clocks born inline with actor_core via existing ActorBorn — no separate ClocksBorn)
- 0 NEW EVT-T8 V1 (Forge:EditChannelTimeFlowRate + Forge:AdvanceChannelClock V1+30d per TDIL-D1 + TDIL-D2)
- 0 NEW EVT-T3 V1 (clock advancement is per-turn synchronous — not delta event)
- 1 NEW namespace: `time_dilation.*` (4 V1 rules + 6 V1+30d reservations)
- 1 NEW stable-ID prefix: `TDIL-*`
- 3 RealityManifest extensions (INLINE on existing structs — NOT new top-level fields): MapLayoutDecl.time_flow_rate + PlaceDecl.time_flow_rate_override + CanonicalActorDecl.initial_clocks
- 4 NEW validators (TDIL-V1..V4): AtomicTravel + RateBounds + InitialClocks + WorldlineMonotonicity
- 10 V1 AC (AC-TDIL-1..10) + 0 V1+ deferred (AC-TDIL coverage complete V1)
- 16 deferrals (TDIL-D1..TDIL-D16; 6 V1+30d active + 4 V2/V3+ + 6 long-tail)

Closure-pass mechanical revisions APPLIED (no semantic change to user-facing behavior):
- **PROG_001 Q3f**: DailyBoundary Generator → per-turn O(1); CultivationTick reads body_clock/soul_clock per BodyOrSoul
- **RES_001 Q4**: 4 day-boundary Generators → per-turn O(1); channel-bound vs actor-bound matrix added
- **AIT_001 §7.5**: per-day materialization replay → O(1) elapsed-time computation; cross-realm observation O(1) per TDIL-A7
- **PCS_001 §S8**: xuyên không clock-split contract reference (soul→soul_clock; body→body_clock; actor=0)

Einstein relativity origin VERIFIED PHYSICS-CORRECT (concept-notes §3 analysis):
- Convention B `time_flow_rate` = proper time τ per coordinate time t (matches Einstein SR/GR)
- 4-clock model generalizes twin paradox to soul/body separation (xuyên không)
- Worldline monotonicity (TDIL-A8) prevents closed timelike curves V1; CTC time-travel V2+ separate feature (TDIL-D8)
- Replay determinism FREE V1 (static rates + monotonic clocks)

NEW priority post-TDIL_001 DRAFT: PCS_001 PC Substrate kickoff (consumes 6 V1 foundations + IDF + FF + FAC + REP + PROG + ACT + AIT + TDIL clocks). Future V1+: CULT_001 Cultivation Foundation (wuxia-genre cultivation method binding to sect via FAC_001 + tu tiên rate via TDIL_001) / V2+ AGE feature (aging reads body_clock per TDIL-D6) / V2+ QST_001 cross-realm quest deadlines (TDIL-D7) / V2+ CTC time travel (TDIL-D8 separate feature) / V3+ DF7-equivalent Lorentz-aware combat (TDIL-D10).

---

## 2026-04-27 — ACT_001 closure pass → CANDIDATE-LOCK + lock RELEASE (commit 5/5 FINAL)

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 2026-04-27 → None (RELEASE after 5-commit ACT_001 cycle)
  - `01_feature_ownership_matrix.md`:
    - 4 ACT_001 aggregate rows: DRAFT → **CANDIDATE-LOCK 2026-04-27 closure pass 5/5**
- **ACT_001 status header** in `ACT_001_actor_foundation.md`: DRAFT → CANDIDATE-LOCK 2026-04-27 (5-commit cycle complete)
- **ACT_001 §19 status transition note** updated to reflect CANDIDATE-LOCK 5/5
- **`features/00_actor/_index.md` ACT_001 row** updated: status CANDIDATE-LOCK + 5-commit cycle reference
- **`features/00_actor/_index.md` folder status:** OPEN → COMPLETE 2026-04-27

### ACT_001 FOUNDATION FOLDER MILESTONE SUMMARY (5 commits across single lock-cycle)

Files created (cumulative across 5 commits):
- features/00_actor/_index.md (folder index; updated to COMPLETE)
- features/00_actor/00_CONCEPT_NOTES.md (Q1-Q6 LOCKED; 3-layer architectural model + 4-aggregate decomposition)
- features/00_actor/ACT_001_actor_foundation.md (~1000 line DRAFT spec; §1-§19 sections; 10 V1 AC; 10 deferrals)
- catalog/cat_00_ACT_actor_foundation.md (ACT-* namespace catalog; ACT-A1..A8 axioms + ACT-D1..D10 deferrals + 16 catalog entries)

Files modified (cascading closure-pass-extensions in commit 3/5 d12a86f):
- 02_storage/R08_npc_memory_split.md (schema split + rename forwarding note; main session attribution; additive)
- features/05_npc_systems/NPC_001_cast.md (closure-pass-extension forwarding note; 3 aggregate ownership transfer to ACT_001; npc_node_binding KEPT)
- features/05_npc_systems/NPC_002_chorus.md (read path migration; NpcOpinion::for_pc → ActorOpinion::for_target; chorus extends to AI-driven PCs V1+)
- features/05_npc_systems/NPC_003_desires.md (desires field path migration npc.desires → actor_chorus_metadata.desires; type rename DesireDecl)

Boundary expansions (commit 2/5 + 5/5):
- 4 NEW ACT_001-owned aggregates (replaces 3 R8-locked NPC_001 imports + adds 1 sparse extension)
- 2 NEW EVT-T4 System sub-types (ActorBorn + ActorChorusMetadataBorn)
- 4 NEW EVT-T8 Administrative sub-shapes (Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory)
- 2 V1 active EVT-T3 delta_kinds (Update on actor_actor_opinion + actor_session_memory; preserved from NPC_001 §13)
- V1+ EVT-T3 delta_kinds reserved (ActorControlSourceChange + bilateral V1+ patterns ACT-D2..D4)
- 1 NEW namespace: `actor.*` (6 V1 rules + 3 V1+ reservations)
- 1 NEW stable-ID prefix: `ACT-*`
- RealityManifest envelope ownership transfer (CanonicalActorDecl now ACT_001-owned) + chorus_metadata field additive

Q-LOCKED summary (Q1-Q6 LOCKED via main session deep-dive 2026-04-27 user "approve all but revise Q6 to (A) full unify all 3 now"; 2 REVISIONS):
- Q1 (C): NEW feature ACT_001 in features/00_actor/
- Q2 (A): Sequential — ACT_001 cycle → PCS_001 cycle on stable base
- Q3 ⚠ REVISION (NEW C): Rename to actor_chorus_metadata; own under ACT_001 substrate; sparse; future-proofs AI-controls-PC-offline V1+
- Q4 (B): Synthetic actors excluded V1
- Q5 (B): R08 update WITHIN cycle
- Q6 ⚠ REVISION (A) user-revised: Full unify all 3 opportunities NOW

3-layer architectural model LOCKED (ACT-A2):
- L1 Identity (actor_core; always present post-creation)
- L2 Capability/Kind (encoded in ActorId variant; stable)
- L3 Control source (DYNAMIC; sparse aggregate population)
  - Control = User → PC online → no actor_chorus_metadata row
  - Control = AI → NPC always V1; PC offline V1+ → actor_chorus_metadata row populated
  - Control = Engine → Synthetic → no narrative substrate V1

Cross-feature deferrals RESOLVED:
- **NPC_001 R8 import anomaly** (only Tier 5 substrate feature NOT per-actor unified pre-ACT_001) → ✅ RESOLVED via actor_core + actor_chorus_metadata split
- **npc_pc_relationship_projection one-directional** (only NPC→PC opinion) → ✅ RESOLVED via actor_actor_opinion bilateral
- **npc_session_memory NPC-scoped** (PC session memory fragmented in chat-service) → ✅ RESOLVED via actor_session_memory unified
- **npc.desires field misplacement** (L3 AI-drive metadata on per-NPC aggregate) → ✅ RESOLVED via actor_chorus_metadata ownership

Phase 3 cleanup applied (commit 4/5 d5ad7af) — 5 fixes:
- S1.1 §15 AC-ACT-1: Wuxia preset NO Synthetic; PC actor_core but NO actor_chorus_metadata V1
- S1.2 §3.1 ActorCore Renamed-from comment: current_session_id semantics + ActorMood range + preserved fields list
- S1.3 §11 sequence: validation flow detail (CanonicalActorDecl init fields → aggregate fields)
- S1.4 ACT-A4 axiom: sparse population is L3 control-state-driven (NOT L2 kind-driven)
- S1.5 §4 tier+scope: actor_chorus_metadata read frequency clarified (only when AI-driven actor in scene)

V1 quantitative summary:
- 4 ACT_001 aggregates (actor_core + actor_chorus_metadata sparse + actor_actor_opinion sparse bilateral + actor_session_memory)
- 1 NPC_001-kept aggregate (npc_node_binding only)
- 3 PCS_001-future aggregates (pc_user_binding + pc_mortality_state + pc_stats_v1_stub)
- 6 V1 reject rules (actor.* namespace) + 3 V1+ reservations
- 2 EVT-T4 + 4 EVT-T8 + 2 EVT-T3 sub-types
- 10 V1 AC (AC-ACT-1..10) + 4 V1+ deferred (AC-ACT-V1+1..V1+4)
- 10 deferrals (ACT-D1..ACT-D10)
- ~1000 line DRAFT spec
- 5-commit cycle (Phase 0 1c0d2d7 + DRAFT 2/5 74b2854 + closure-pass-extensions 3/5 d12a86f + Phase 3 4/5 d5ad7af + closure 5/5 this commit)

NEW V1+ priority post-ACT_001:
- **PCS_001 PC Substrate** — consumes ACT_001 stable base (actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory) + IDF + RES_001 + FF_001 + FAC_001 + REP_001 + PROG_001; owns pc_user_binding + pc_mortality_state + pc_stats_v1_stub; xuyên không body_memory in pc_user_binding; SPIKE_01 obs#5 literacy slip detection
- **AI-controls-PC-offline V1+ (ACT-D1)** — activates actor_chorus_metadata PC population when control source transitions User → AI
- **Multi-PC realities V1+ (ACT-D4)** — bilateral PC↔PC opinion via actor_actor_opinion
- **Sect rivalry NPC↔NPC drama V1+ (ACT-D3)** — bilateral NPC↔NPC opinion

---

## 2026-04-27 — ACT_001 Actor Foundation DRAFT promotion + boundary register (commit 2/5)

- **Lock CLAIMED** at start of this commit (`[boundaries-lock-claim]`); release deferred to commit 5/5 closure pass per ACT_001 5-commit cycle (large refactor; commit 2/5 boundary docs + commit 3/5 cascading closure-pass-extensions for R8 + NPC_001/002/003)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-27 (ACT_001 unification cycle; 4h TTL)
  - `01_feature_ownership_matrix.md`:
    - 4 NEW aggregate rows: actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory (ALL ACT_001-owned)
    - REMOVED: 3 NPC_001 R8 import rows (npc + npc_session_memory + npc_pc_relationship_projection) — REPLACED by ACT_001 unified equivalents above
    - PRESERVED: npc_node_binding (NPC_001-owned; closure-pass-extension note added 2026-04-27)
    - 2 NEW EVT-T4 sub-type entries: ActorBorn + ActorChorusMetadataBorn (ACT_001 owner)
    - 4 NEW EVT-T8 sub-shape entries: Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory (ACT_001 owner; uses WA_003 forge_audit_log)
    - 1 NEW EVT-T3 entry: 2 V1 active delta_kinds (Update on actor_actor_opinion + Update on actor_session_memory; preserved from NPC_001 §13 session-end derivation; renamed) + V1+ delta_kinds reserved (ActorControlSourceChange + bilateral V1+ patterns)
    - RealityManifest envelope row UPDATED: canonical_actors ownership transfers from PL_001+NPC_001 → ACT_001 + chorus_metadata field additive (ACT-D1 V1+ activation)
    - RejectReason namespace: appended `actor.*` → ACT_001
    - NEW stable-ID prefix: `ACT-*`
  - `02_extension_contracts.md`:
    - §1.4 namespace registration: `actor.*` (6 V1 rules + 3 V1+ reservations)
    - §2 RealityManifest CanonicalActorDecl ownership transferred to ACT_001 + chorus_metadata extension fields documented (kind-agnostic; sparse — Some for NPCs V1; None for PCs V1; V1+ AI-controls-PC-offline activation)
  - `99_changelog.md`: this entry

### ACT_001 DRAFT MILESTONE SUMMARY (commit 2/5 of 5-commit cycle)

Files created/modified outside `_boundaries/` (commit 2/5 only — commit 3/5 will do closure-pass-extensions for R8 + NPC_001/002/003):
- features/00_actor/_index.md (DRAFT row updated; ACT_001 active)
- features/00_actor/00_CONCEPT_NOTES.md (already at Q-LOCKED status; commit 1/5 1c0d2d7)
- features/00_actor/ACT_001_actor_foundation.md (~1000 line DRAFT spec — NEW THIS COMMIT)
- catalog/cat_00_ACT_actor_foundation.md (ACT-* namespace catalog; ACT-A1..A8 axioms + ACT-D1..D10 deferrals + 16 catalog entries — NEW THIS COMMIT)

Boundary expansions (commit 2/5):
- 4 NEW ACT_001-owned aggregates (replaces 3 R8-locked NPC_001 imports + adds 1 sparse extension)
- 2 NEW EVT-T4 System sub-types (ActorBorn + ActorChorusMetadataBorn)
- 4 NEW EVT-T8 Administrative sub-shapes (Forge:EditActorCore + Forge:EditChorusMetadata + Forge:EditActorOpinion + Forge:EditActorSessionMemory)
- 2 NEW EVT-T3 Derived delta_kinds active V1 (Update on actor_actor_opinion + actor_session_memory; preserved from NPC_001 §13)
- 1 NEW namespace: `actor.*` (6 V1 rules + 3 V1+ reservations)
- 1 NEW stable-ID prefix: `ACT-*`
- RealityManifest envelope ownership transfer (CanonicalActorDecl now ACT_001-owned)

Q-LOCKED summary (Q1-Q6 LOCKED via main session deep-dive 2026-04-27 user "approve all but revise Q6 to (A) full unify all 3 now"):
- Q1 (C): NEW feature ACT_001 Actor Foundation in features/00_actor/
- Q2 (A): Sequential — ACT_001 cycle → PCS_001 cycle on stable base
- Q3 ⚠ REVISION (NEW C): Rename npc_chorus_metadata → actor_chorus_metadata; own under ACT_001 substrate; sparse storage; future-proofs AI-controls-PC-offline V1+
- Q4 (B): Synthetic actors excluded V1 (universal substrate discipline)
- Q5 (B): 02_storage R08 update WITHIN ACT_001 cycle (deferred to commit 3/5)
- Q6 ⚠ REVISION (A) user-revised: Full unify all 3 opportunities NOW (actor_core + actor_chorus_metadata + actor_actor_opinion + actor_session_memory)

3-layer architectural model LOCKED (ACT-A2):
- L1 Identity (actor_core; always present post-creation)
- L2 Capability/Kind (encoded in ActorId variant; stable post-creation)
- L3 Control source (dynamic; sparse aggregate population)
  - Control = User → PC online → no actor_chorus_metadata row
  - Control = AI → NPC always; PC offline V1+ → actor_chorus_metadata row populated
  - Control = Engine → Synthetic → no narrative substrate V1

Cross-feature deferrals RESOLVED (commit 5/5 closure will note):
- **NPC_001 R8 import anomaly** — `npc` aggregate (per-NPC) was only Tier 5 substrate not unified per-actor → ✅ RESOLVED via actor_core + actor_chorus_metadata split
- **npc_pc_relationship_projection one-directional** — only NPC→PC opinion → ✅ RESOLVED via actor_actor_opinion bilateral
- **npc_session_memory NPC-scoped** — PC session memory fragmented in chat-service → ✅ RESOLVED via actor_session_memory unified

Cascading closure-pass-extensions DEFERRED to commit 3/5:
- 02_storage R08_npc_memory_split.md — schema split + rename
- features/05_npc_systems/NPC_001_cast.md — 3 aggregates ownership transfer + persona §6 update + AC names
- features/05_npc_systems/NPC_002_chorus.md — read paths updated (NpcOpinion::for_pc → ActorOpinion::for_target)
- features/05_npc_systems/NPC_003_desires.md — desires field ownership transfer + type rename

V1 quantitative summary:
- 4 ACT_001 aggregates (actor_core + actor_chorus_metadata sparse + actor_actor_opinion sparse bilateral + actor_session_memory)
- 1 NPC_001-kept aggregate (npc_node_binding only)
- 3 PCS_001-future aggregates (pc_user_binding + pc_mortality_state + pc_stats_v1_stub)
- 6 V1 reject rules (actor.* namespace) + 3 V1+ reservations
- RealityManifest CanonicalActorDecl ownership transfer + chorus_metadata fields additive
- 2 EVT-T4 System + 4 EVT-T8 Forge + 2 EVT-T3 Derived (V1 active; V1+ patterns reserved)
- 10 V1 AC + 4 V1+ deferred + 10 deferrals (ACT-D1..ACT-D10)
- ~1000 line DRAFT spec
- 5-commit cycle (Phase 0 1c0d2d7 + DRAFT 2/5 this commit + closure-pass-extensions 3/5 + Phase 3 4/5 + closure+release 5/5)

Next: commit 3/5 cascading closure-pass-extensions for R08 + NPC_001/002/003.

---

## 2026-04-27 — REP_001 closure pass → CANDIDATE-LOCK + lock RELEASE (commit 4/4 FINAL)

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 2026-04-27 → None (RELEASE after 4-commit REP_001 cycle)
  - `01_feature_ownership_matrix.md`:
    - `actor_faction_reputation` row: DRAFT → **CANDIDATE-LOCK 2026-04-27 closure pass 4/4**
- **REP_001 status header** in `REP_001_reputation_foundation.md`: DRAFT → CANDIDATE-LOCK 2026-04-27
- **REP_001 §19 status transition note** updated to reflect CANDIDATE-LOCK 4/4
- **`features/00_reputation/_index.md` REP_001 row** updated: status CANDIDATE-LOCK + 4-commit cycle reference
- **`features/00_reputation/_index.md` folder status:** OPEN → COMPLETE 2026-04-27

### REP_001 FOUNDATION FOLDER MILESTONE SUMMARY (4 commits across single lock-cycle)

Files created (cumulative across 4 commits + Phase 0):
- features/00_reputation/_index.md (folder index; updated to COMPLETE)
- features/00_reputation/00_CONCEPT_NOTES.md (Q1-Q10 LOCKED + V1 scope populated)
- features/00_reputation/01_REFERENCE_GAMES_SURVEY.md (14 game references: D&D 5e + WoW + Fallout: NV + Skyrim + CK3 + Bannerlord + Sands of Salzaar + Path of Wuxia + Stellaris + Pillars of Eternity + Tyranny + Mass Effect + Dragon Age + Wuxia novels — 10-dimension comparison table)
- features/00_reputation/REP_001_reputation_foundation.md (~625 line DRAFT spec; §1-§19 sections; 8 V1 AC; 17 deferrals)
- catalog/cat_00_REP_reputation_foundation.md (REP-* namespace catalog; REP-A1..A7 axioms + REP-D1..D17 deferrals + 14 catalog entries)

Boundary expansions:
- 1 NEW aggregate: `actor_faction_reputation` (T2/Reality, sparse — per-(actor, faction) bounded standing)
- 1 NEW EVT-T4 System sub-type: `ReputationBorn` (canonical seed only)
- 2 NEW EVT-T8 Administrative sub-shapes: `Forge:SetReputation` + `Forge:ResetReputation` (V1 active per Q5 LOCKED)
- 3 V1+ EVT-T3 delta_kinds reserved: Delta + CascadeDelta + DecayTick (V1+ runtime reputation milestone Q5+Q6+Q7 ships coherently together)
- 1 NEW namespace: `reputation.*` (6 V1 rules + 4 V1+ reservations)
- 1 NEW RealityManifest extension: `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (OPTIONAL V1; sparse opt-in)
- 1 NEW stable-ID prefix: `REP-*`

Q-LOCKED summary (Q1-Q10 LOCKED via 5-batch deep-dive 2026-04-27 user "approve" across all batches; 1 REVISION on Q4):
- Q1 (A): Materialized aggregate `actor_faction_reputation` (FAC_001 Q1 pattern)
- Q2 (A): Sparse storage + V1+ lazy-create on first delta touch
- Q3 (A): Bounded i16 [-1000, +1000] + 8-tier engine-fixed (asymmetric thresholds; Wuxia I18n labels)
- Q4 ⚠ REVISION (A): Always Neutral (0) V1 (vs initial hybrid (C)); V1+ hybrid via REP-D16 alongside Q6 cascade
- Q5 (B): Forge admin V1 + canonical seed V1; runtime gameplay V1+
- Q6 (A): No cascade V1; V1+ via REP-D2 (FactionDecl.rep_cascade_config)
- Q7 (A): No decay V1; V1+ via REP-D3 (FactionDecl.rep_decay_per_week)
- Q8 (A): V1 strict single-reality; V2+ Heresy via WA_002 (universal discipline)
- Q9 (A): Synthetic actor forbidden V1 (universal discipline)
- Q10 (A): Coexist with RES_001 SocialCurrency::Reputation via 3-layer separation discipline

Cross-feature deferral RESOLVED:
- **FAC-D7** (FAC_001) — Per-(actor, faction) reputation projection → ✅ RESOLVED via REP_001 actor_faction_reputation aggregate

3-layer separation discipline LOCKED (REP-A4 + Q10):
- L1 NPC_001 npc_pc_relationship_projection = per-(NPC, PC) personal opinion
- L2 RES_001 SocialCurrency::Reputation = per-actor unbounded global "danh tiếng" sum scalar
- L3 REP_001 actor_faction_reputation = per-(actor, faction) bounded standing per faction
- These three layers are COMPLEMENTARY, NOT duplicative; NPC_002 Chorus consumes ALL THREE for V1+ priority resolution (Tier 2 NPC opinion + Tier 4 V1+ rep + Tier 5 V1+ fame)

Phase 3 cleanup applied (commit 3/4 b321f74) — 7 fixes:
- S1.1 §1 Wuxia table: Du sĩ × Ma Tông score -100 → -300 (correctly maps to Hostile tier per Q3 thresholds)
- S1.2 §1 Wuxia defaults: clarified zero-row engine fallback semantics
- S1.3 §3.1 Mutability: tightened V1+ delta lazy-create cross-ref + V1+ runtime reputation milestone coherence note
- S1.4 §11 Sequence: fixed score -100 → -300 in canonical seed example + Authoring discipline guidance
- S1.5 §15 AC-REP-1: aligned with -300 corrected score
- S1.6 §15 AC-REP-2: fixed score=-100 example confusion + boundary case tests (-251 / -250)
- S1.7 §17 REP-D1/D2/D3: V1+ runtime reputation milestone coherent activation note

V1 quantitative summary:
- 1 aggregate (actor_faction_reputation sparse) — smaller than FAC_001's 2-aggregate scope
- 1 enum (ReputationTier 8-variant display layer; not stored)
- score: i16 in [-1000, +1000] (clamped silently per REP-A1)
- Asymmetric tier thresholds: Hated -1000..-501 / Hostile -500..-251 / Unfriendly -250..-101 / Neutral -100..+100 / Friendly +101..+250 / Honored +251..+500 / Revered +501..+900 / Exalted +901..+1000
- Wuxia I18n labels: Đại nghịch / Nghịch tặc / Kẻ thù / Người lạ / Đệ tử / Trưởng lão / Tôn sư / Đại Thánh nhân
- 6 V1 reject rule_ids in `reputation.*` namespace + 4 V1+ reservations
- 1 RealityManifest extension (canonical_actor_faction_reputations OPTIONAL — sparse; empty Vec valid)
- 2 EVT-T8 Forge sub-shapes + 1 EVT-T4 System sub-type
- 3 V1+ EVT-T3 delta_kinds reserved
- 8 V1 AC + 4 V1+ deferred + 17 deferrals (REP-D1..REP-D17)
- ~625 line DRAFT spec
- 4-commit cycle (Phase 0 6b7d931 + lock-Q 1/4 61e5019 + DRAFT 2/4 b2025a1 + Phase 3 3/4 b321f74 + closure+release 4/4 this commit)

NEW V1+ priority post-REP_001:
- **PCS_001 PC Substrate** — consumes IDF + RES_001 + FF_001 + FAC_001 + REP_001 + PROG_001 (PC creation form)
- **CULT_001 Cultivation Foundation** — wuxia-genre cultivation method binding to sect via FAC_001 (V1+ requires REP_001 min rep)
- **TIT_001 Title Foundation** — heir succession via FF_001 dynasty.current_head + FAC_001 sect_leader_role + min REP_001 rep
- **DIPL_001 Diplomacy Foundation** — V2+ inter-faction relations / treaties / wars (consumes FAC_001 + REP_001)
- **AIT_001 AI Tier Foundation** — already DRAFT 88404f0 (architecture-scale 3-tier NPC for billion-NPC scaling)

---

## 2026-04-27 — REP_001 Reputation Foundation DRAFT promotion + boundary register (commit 2/4)

- **Lock CLAIMED** at start of this commit (`[boundaries-lock-claim]`); release deferred to commit 4/4 closure pass per FAC_001 4-commit cycle pattern
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-27 (REP_001 DRAFT promotion + boundary register; 4h TTL)
  - `01_feature_ownership_matrix.md`:
    - 1 NEW aggregate row: `actor_faction_reputation` (REP_001 DRAFT 2026-04-27)
    - 1 NEW EVT-T4 sub-type entry: `ReputationBorn` (REP_001 owner)
    - 2 NEW EVT-T8 sub-shape entries: `Forge:SetReputation` + `Forge:ResetReputation` (REP_001 owner; uses WA_003 forge_audit_log)
    - 1 NEW EVT-T3 entry: 3 V1+ delta_kinds reserved for `aggregate_type=actor_faction_reputation` (Delta + CascadeDelta + DecayTick)
    - RealityManifest envelope row: appended `REP_001 Reputation Foundation (canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>, OPTIONAL V1, added 2026-04-27)`
    - RejectReason namespace row: appended `reputation.* → REP_001` (also ensured `race.* → IDF_001`, `language.*`, `personality.*`, `origin.*`, `ideology.*`, `family.*`, `faction.*`, `progression.*` listed for completeness)
    - Stable-ID prefix row: NEW `REP-*` entry (foundation tier — Tier 5 Actor Substrate post-FAC_001)
  - `02_extension_contracts.md`:
    - §1.4 namespace registration: `reputation.*` (6 V1 rules + 4 V1+ reservations)
    - §2 RealityManifest extension: `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (OPTIONAL V1; sparse opt-in)
  - `99_changelog.md`: this entry

### REP_001 DRAFT MILESTONE SUMMARY (commit 2/4 of 4-commit cycle)

Files created/modified outside `_boundaries/`:
- features/00_reputation/_index.md (DRAFT row updated; catalog reference added)
- features/00_reputation/00_CONCEPT_NOTES.md (already at Q-LOCKED status; commit 1/4 61e5019)
- features/00_reputation/01_REFERENCE_GAMES_SURVEY.md (Phase 0 commit 6b7d931)
- features/00_reputation/REP_001_reputation_foundation.md (~625 line DRAFT spec — NEW THIS COMMIT)
- catalog/cat_00_REP_reputation_foundation.md (REP-* namespace catalog; REP-A1..A7 axioms + REP-D1..D17 deferrals — NEW THIS COMMIT)

Boundary expansions:
- 1 NEW aggregate: `actor_faction_reputation` (T2/Reality, sparse — per-(actor, faction) bounded standing)
- 1 NEW EVT-T4 System sub-type: `ReputationBorn` (canonical seed only)
- 2 NEW EVT-T8 Administrative sub-shapes: `Forge:SetReputation` + `Forge:ResetReputation` (V1 active per Q5 LOCKED)
- 3 V1+ EVT-T3 delta_kinds reserved: Delta + CascadeDelta + DecayTick (V1+ runtime reputation milestone per Q5+Q6+Q7 V1+ enrichment)
- 1 NEW namespace: `reputation.*` (6 V1 rules + 4 V1+ reservations)
- 1 NEW RealityManifest extension: `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (OPTIONAL V1; sparse opt-in)
- 1 NEW stable-ID prefix: `REP-*`

Q-LOCKED summary (Q1-Q10 LOCKED via 5-batch deep-dive 2026-04-27 user "approve" across all batches; 1 REVISION on Q4):
- Q1 (A): Materialized aggregate `actor_faction_reputation` (FAC_001 Q1 pattern)
- Q2 (A): Sparse storage + V1+ lazy-create on first delta touch
- Q3 (A): Bounded i16 [-1000, +1000] + 8-tier engine-fixed (asymmetric thresholds; Wuxia I18n labels)
- Q4 ⚠ REVISION (A): Always Neutral (0) V1 (vs initial hybrid (C)); V1+ hybrid via REP-D16 alongside Q6 cascade
- Q5 (B): Forge admin V1 + canonical seed V1; runtime gameplay V1+
- Q6 (A): No cascade V1; V1+ via REP-D2 (FactionDecl.rep_cascade_config)
- Q7 (A): No decay V1; V1+ via REP-D3 (FactionDecl.rep_decay_per_week)
- Q8 (A): V1 strict single-reality; V2+ Heresy via WA_002 (universal discipline)
- Q9 (A): Synthetic actor forbidden V1 (universal discipline)
- Q10 (A): Coexist with RES_001 SocialCurrency::Reputation via 3-layer separation discipline

Cross-feature deferrals RESOLVED:
- **FAC-D7** (FAC_001) — Per-(actor, faction) reputation projection → ✅ RESOLVED via REP_001 actor_faction_reputation aggregate

3-layer separation discipline LOCKED (REP-A4 + Q10):
- L1 NPC_001 npc_pc_relationship_projection = per-(NPC, PC) personal opinion
- L2 RES_001 SocialCurrency::Reputation = per-actor unbounded global "danh tiếng" sum scalar
- L3 REP_001 actor_faction_reputation = per-(actor, faction) bounded standing per faction
- These three layers are COMPLEMENTARY, NOT duplicative; NPC_002 Chorus consumes ALL THREE for V1+ priority resolution

V1 quantitative summary:
- 1 aggregate (actor_faction_reputation sparse) — smaller than FAC_001's 2-aggregate scope
- 1 enum (ReputationTier 8-variant display layer; not stored)
- 6 V1 reject rule_ids in `reputation.*` namespace + 4 V1+ reservations
- 1 RealityManifest extension (canonical_actor_faction_reputations OPTIONAL — sparse; empty Vec valid)
- 2 EVT-T8 Forge sub-shapes + 1 EVT-T4 System sub-type
- 3 V1+ EVT-T3 delta_kinds reserved (Delta + CascadeDelta + DecayTick)
- 8 V1 AC + 4 V1+ deferred + 17 deferrals (REP-D1..REP-D17)
- ~625 line DRAFT spec
- 4-commit cycle (Phase 0 6b7d931 + lock-Q 1/4 61e5019 + DRAFT 2/4 this commit + Phase 3 3/4 + closure+release 4/4)

Next: commit 3/4 Phase 3 cleanup, then commit 4/4 closure pass + lock release. New V1+ priority post-REP_001: PCS_001 PC Substrate (consumes IDF + RES_001 + FF_001 + FAC_001 + REP_001 + PROG_001) OR CULT_001 Cultivation Foundation (wuxia-genre cultivation method binding to sect via FAC_001) OR TIT_001 Title Foundation (heir succession via FF_001 + FAC_001 + min REP_001 rep).

---

## 2026-04-26 — FAC_001 closure pass → CANDIDATE-LOCK + lock RELEASE (commit 4/4 FINAL)

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session → None (RELEASE after 4-commit FAC_001 cycle)
  - `01_feature_ownership_matrix.md`:
    - `faction` row: DRAFT → **CANDIDATE-LOCK 2026-04-26 closure pass 4/4**
    - `actor_faction_membership` row: DRAFT → **CANDIDATE-LOCK 2026-04-26 closure pass 4/4**
- **FAC_001 status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` FAC_001 row updated:** status CANDIDATE-LOCK + 4-commit cycle reference
- **`_index.md` folder status:** Open → COMPLETE 2026-04-26

### FAC_001 FOUNDATION FOLDER MILESTONE SUMMARY (4 commits across single lock-cycle)

Files created (cumulative across 4 commits + Phase 0):
- features/00_faction/_index.md (folder index; updated to COMPLETE)
- features/00_faction/00_CONCEPT_NOTES.md (Q1-Q10 LOCKED + V1 scope populated)
- features/00_faction/01_REFERENCE_GAMES_SURVEY.md (10-system market survey: Wuxia primary + grand-strategy + tabletop)
- features/00_faction/FAC_001_faction_foundation.md (~870 lines DRAFT spec)

Boundary expansions:
- 2 NEW aggregates: faction (T2/Reality sparse) + actor_faction_membership (T2/Reality)
- 2 NEW EVT-T4 sub-types: FactionBorn + FactionMembershipBorn
- 3 NEW EVT-T8 sub-shapes: Forge:RegisterFaction + Forge:EditFaction + Forge:EditFactionMembership
- 1 NEW namespace: faction.* (8 V1 rule_ids + 4 V1+ reservations)
- 2 NEW RealityManifest extensions: canonical_factions + canonical_faction_memberships (REQUIRED V1; sparse)
- 1 NEW Stable-ID prefix: FAC-*

Q1-Q10 LOCKED (per 49a17ed deep-dive; 3 REVISIONS):
- Q1 (A) 2 aggregates (faction sparse + actor_faction_membership)
- Q2 REVISION: Vec<T> schema V1 + V1 validator cap=1 (V1+ relax cap = NO migration)
- Q3 (A) Author-declared role taxonomy per FactionDecl
- Q4 REVISION: Numeric u16 only V1; named computed display
- Q5 (A) V1 static default_relations; V1+ DIPL_001 dynamic
- Q6 (A) master_actor_id field on actor_faction_membership; FF-D7 RESOLVED
- Q7 REVISION: Defer sworn brotherhood V1+ via FAC-D10 (NOT V1 schema slot)
- Q8 (A) V1 strict single-reality
- Q9 (A) Schema-present hook V1+; AxiomDecl.requires_faction reserved
- Q10 (A) Synthetic forbidden V1

Cross-feature integration RESOLVED:
- IDF_005 IDL-D2 → FAC_001 FactionDecl.requires_ideology validation (sect membership ideology binding)
- FF_001 FF-D7 → FAC_001 master_actor_id field (master-disciple sect lineage)

Cross-feature integration JOINTLY V1+:
- FF-D5 Marriage as faction alliance → V1+ FAC_001 + V1+ DIPL_001 (FAC-D3)
- FF-D6 Sworn brotherhood → V1+ FAC-D10 (NOT V1 schema slot)
- FF-D8 Title inheritance → V1+ TIT_001 reads FAC_001 + FF_001 (FAC-D6)

V1 quantitative summary:
- 2 aggregates V1 (faction sparse + actor_faction_membership)
- 6-variant FactionKind enum (Sect/Order/Clan/Guild/Coalition/Other)
- 3-variant RelationStance enum (Hostile/Neutral/Allied)
- 4-variant JoinReason enum (CanonicalSeed/PcCreation/NpcSpawn/AdminOverride)
- Vec<FactionMembershipEntry> with V1 cap=1 validator
- Author-declared roles per FactionDecl (RoleDecl: role_id + display_name + authority_level)
- Numeric u16 rank only V1; named computed display
- master_actor_id field
- NO sworn_bond_id field V1 (FAC-D10 V1+)
- Static default_relations HashMap<FactionId, RelationStance>
- 8 V1 reject rule_ids in faction.* + 4 V1+ reservations
- 2 RealityManifest extensions (canonical_factions + canonical_faction_memberships)
- 3 EVT-T8 Forge sub-shapes
- 2 EVT-T4 System sub-types (FactionBorn + FactionMembershipBorn)
- 7 EVT-T3 delta_kinds (V1+ runtime; V1 ships canonical seed only)
- 10 V1-testable AC-FAC-1..10 + 4 V1+ deferred
- 17 deferrals (FAC-D1..D17)
- ~870-line DRAFT spec

V1 reality presets coverage:
- Wuxia: 5 sects (Đông Hải Đạo Cốc / Tây Sơn Phật Tự / Ma Tông / Trung Nguyên Võ Hiệp / Tán Tu Đồng Minh) + Du sĩ membership
- Modern: 1-2 factions
- Sci-fi: deferred V1+

i18n: V1 ships I18nBundle from day 1 per RES_001 §2 contract.

CANDIDATE-LOCK → LOCK gate: AC-FAC-1..10 V1-testable scenarios pass integration tests against Wuxia + Modern reality fixtures + V1+ TIT_001 / REP_001 / CULT_001 / DIPL_001 ship.

NEW V1+ priority roadmap (locked order; per FAC_001 closure):
1. ✓ IDF folder closure (15 commits) DONE
2. ✓ FF_001 Family Foundation (4 commits) DONE
3. ✓ FAC_001 Faction Foundation (4 commits) DONE (this commit)
4. **REP_001 Reputation Foundation** (next post-IDF social tier; per-(actor, faction) rep projection)
5. PCS_001 PC substrate (BLOCKED on PROG_001 — DONE, but PCS_001 needs full integration design)
6. NPC_NNN mortality
7. CULT_001 Cultivation Foundation (wuxia-genre-specific; defer)

Drift watchpoints unchanged at 8 active.

Lock RELEASED at end of this commit.

---

## 2026-04-26 — FAC_001 Phase 3 cleanup (commit 3/4)

- Lock continues from commit 2/4
- No boundary changes (Phase 3 = internal documentation cleanup)
- 7 Phase 3 fixes applied: FactionId+RoleId typed newtypes confirmed + RelationStance opinion modifier values explicit + bidirectional sync explicit + empty memberships Vec valid + V1+ TIT_001 dependency noted + §15.4 LOCK criterion split + cross-feature deferral cross-references tightened
- §19 readiness checklist updated

---

## 2026-04-26 — FAC_001 Faction Foundation DRAFT promotion + boundary register (commit 2/4)

- **Lock claim:** main session 2026-04-26 (FAC_001 single-feature 4-commit cycle: lock-Q-decisions [done 49a17ed] + DRAFT [this] + Phase 3 + closure+release); this commit `[boundaries-lock-claim]`
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claimed by main session 2026-04-26 (FAC_001 DRAFT promotion cycle)
  - `01_feature_ownership_matrix.md`:
    - NEW row: `faction` aggregate (T2/Reality sparse, FAC_001 DRAFT 2026-04-26)
    - NEW row: `actor_faction_membership` aggregate (T2/Reality, FAC_001 DRAFT 2026-04-26)
    - EVT-T4 System sub-types: NEW `FactionBorn` + `FactionMembershipBorn` (FAC_001 owns; emitted at canonical seed)
    - EVT-T8 Administrative sub-shapes: NEW `Forge:RegisterFaction` + `Forge:EditFaction` + `Forge:EditFactionMembership` (FAC_001 owns; uses forge_audit_log)
    - Stable-ID prefix table: NEW `FAC-*` row (axioms / deferrals / decisions; catalog/cat_00_FAC_faction_foundation.md TBD)
  - `02_extension_contracts.md`:
    - §1.4 RejectReason namespace: NEW `faction.*` row with 8 V1 rule_ids (unknown_faction_id / unknown_role_id / multi_membership_forbidden_v1 [per Q2 REVISION cap=1] / master_cross_sect_forbidden / master_authority_violation / cyclic_master_chain / ideology_binding_violation [RESOLVES IDL-D2] / synthetic_actor_forbidden) + 4 V1+ reservations (cross_reality_mismatch / lex_axiom_forbidden / sworn_bond_unsupported_v1 / member_role_count_exceeded)
    - §2 RealityManifest: NEW `canonical_factions: Vec<FactionDecl>` + `canonical_faction_memberships: Vec<FactionMembershipDecl>` REQUIRED V1 (sparse storage allowed); 6-variant FactionKind closed enum (Sect/Order/Clan/Guild/Coalition/Other); 3-variant RelationStance (Hostile/Neutral/Allied)
- **FAC_001 file:** created `FAC_001_faction_foundation.md` (~870 lines DRAFT spec mirroring EF/PF/MAP/CSC/RES/IDF/FF pattern). 10 V1-testable AC-FAC-1..10 + 4 V1+ deferred. 17 deferrals FAC-D1..D17.
- **Q1-Q10 LOCKED** (per commit 49a17ed):
  - Q1 (A) 2 aggregates (faction sparse + actor_faction_membership)
  - Q2 REVISION: Vec<FactionMembershipEntry> schema V1 + V1 validator cap=1 (V1+ relax cap = NO schema migration)
  - Q3 (A) Author-declared role taxonomy per FactionDecl
  - Q4 REVISION: Numeric u16 only V1; named computed display
  - Q5 (A) V1 static default_relations; V1+ DIPL_001 dynamic
  - Q6 (A) master_actor_id field on actor_faction_membership; FF-D7 RESOLVED
  - Q7 REVISION: Defer sworn brotherhood V1+ via FAC-D10 (NOT V1 schema slot)
  - Q8 (A) V1 strict single-reality
  - Q9 (A) Schema-present hook V1+ (AxiomDecl.requires_faction reserved)
  - Q10 (A) Synthetic forbidden V1
- **Cross-feature deferrals RESOLVED:**
  - FF-D7 Master-disciple sect lineage → FAC_001 master_actor_id field
  - IDL-D2 Sect membership ideology binding → FAC_001 FactionDecl.requires_ideology
- **Cross-feature deferrals JOINTLY V1+:**
  - FF-D5 Marriage as faction alliance → V1+ FAC_001 + V1+ DIPL_001 (FAC-D3)
  - FF-D6 Sworn brotherhood → V1+ FAC-D10 (NOT V1 schema slot per Q7 REVISION)
  - FF-D8 Title inheritance → V1+ TIT_001 reads FAC_001 + FF_001 (FAC-D6)
- **Reason:** Tier 5 Actor Substrate Foundation post-IDF + post-FF_001 priority. FAC_001 resolves multiple V1+ deferrals from FF_001 + IDF_005. Single-feature lock cycle (3 commits remaining: this + Phase 3 + closure+release).
- **Drift watchpoints unchanged at 8 active.**
- **Lock continues:** still claimed for FAC_001 Phase 3 (commit 3/4) + closure pass (commit 4/4 with `[boundaries-lock-release]` prefix).

---

## 2026-04-27 — AIT_001 AI Tier Foundation DRAFT promotion (architecture-scale; 3-tier NPC architecture for billion-NPC scaling)

- **Lock claim:** main session 2026-04-27 (AIT_001 DRAFT promotion); single `[boundaries-lock-claim+release]` commit cycle
- **Files modified:** `_LOCK.md` (claim+release) + `01_feature_ownership_matrix.md` (AIT-* prefix) + `02_extension_contracts.md` §1.4 (`ai_tier.*` namespace 8 V1 + 4 V1+ rule_ids) + §2 (5 NEW OPTIONAL V1 RealityManifest extensions: tier_capacity_caps + untracked_templates + cell_untracked_density + tier_roster_caps + minor_behavior_scripts) + `99_changelog.md`
- **Files created:** `features/16_ai_tier/AIT_001_ai_tier_foundation.md` (~1300 lines / 21 sections / 12 AC / 21 deferrals) + `catalog/cat_16_AIT_ai_tier.md` (36 catalog entries)
- **Files updated in features:** `features/16_ai_tier/_index.md` (DRAFT row) + `features/16_ai_tier/00_CONCEPT_NOTES.md` §17 status DRAFT
- **All 12 Qs LOCKED** via 4-batch deep-dive 2026-04-26..27 (Q3 + Q10 implicit). 2-variant NpcTrackingTier (Major / Minor); Untracked = no aggregate (PROG_001 §3.1 semantic). Author-required tier on CanonicalActorDecl. Hybrid 2-stage Untracked generation (template+RNG Stage 1 / LLM-flavor Stage 2 lazy). Cell-entry timing with daily rotation. Forge promotion preserves NpcId. 4-tier × 4-capability behavior matrix. MinorBehaviorScript per actor_class. AIT-V1 TierActionValidator at PL_005 pre-validation. Tier-aware AssemblePrompt budget (5 Full + 8 Condensed + 12 Summary defaults; aggregate overflow).
- **Major architectural insights:** Quantum-observation NPC model (Schrödinger pattern; PROG_001 Q4 REVISED activated) + Stellaris pops vs named characters reference + future AI Tier feature reservation FULFILLED + i18n compliance throughout.
- **NEW EVT sub-types/shapes:** EVT-T5 `Generated:UntrackedNpcSpawn` + `Generated:UntrackedNpcDiscarded` (deterministic blake3 per EVT-A9); EVT-T3 cascade-trigger `TrackingTierTransition`; EVT-T8 `Forge:PromoteUntrackedToTracked`. AIT-V1..V4 validator slots.
- **PROG_001 tracking_tier field activated** (was Option<NpcTrackingTier> None V1; AIT_001 populates Major/Minor variants).
- **10 downstream impact items deferred:** HIGH (NPC_001 closure tier-aware / NPC_002 Chorus tier filter / PL_005 AIT-V1 + Untracked target / WA_003 PromoteUntrackedToTracked / PL_001 session lifecycle / 07_event_model registration); MEDIUM (PROG_001 doc update / EF_001 cascade hook); LOW (CSC_001 Layer 3); V1+30d (RES_001 PROG-D19 NPC eager → lazy migration).
- **Foundation tier remains 6/6** (closed at PROG_001). AIT_001 is architecture-scale Tier 5+ Actor Substrate scaling/architecture feature.
- **Cumulative deferrals AIT-D1..D21** (10 V1+30d / 5 V2 / 1 V3 + future feature coordination CULT_001 / REP_001 / FAC_001 expansion).
- **Drift watchpoints:** unchanged. ORG-* namespace alignment concern noted (cross-feature coordination at next IDF closure pass review).
- **Lock RELEASED** at end of this commit
- **Reason / handoff:** AIT_001 DRAFT activates billion-NPC scaling architecture. Quantum-observation principle implemented. PCS_001 PC Substrate parallel agent kickoff next priority. Future V1+ priorities: CULT_001 / REP_001. RES_001 V1+30d closure pass aligns PROG-D19.

---

## 2026-04-26 — PROG_001 Progression Foundation DRAFT promotion (6th V1 foundation; closes V1 foundation tier 6/6)

- **Lock claim:** main session 2026-04-26 (PROG_001 DRAFT promotion); single `[boundaries-lock-claim+release]` commit cycle
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner None → main session 2026-04-26 (PROG_001 DRAFT) → None at release
  - `01_feature_ownership_matrix.md`:
    - **NEW aggregate row:** `actor_progression` (T2/Reality, owner=Actor only V1; Item V1+30d reserved) — owned by PROG_001 DRAFT 2026-04-26
    - **NEW Stable-ID prefix:** `PROG-*` foundation tier (catalog/cat_00_PROG_progression.md created)
  - `02_extension_contracts.md` §1.4: NEW `progression.*` rule_id namespace (7 V1 + 6 V1+ reservations)
  - `02_extension_contracts.md` §2: 4 NEW OPTIONAL V1 RealityManifest extensions (progression_kinds + progression_class_defaults + progression_actor_overrides + strike_formula)
  - `99_changelog.md`: this entry
- **Files created within `features/00_progression/`:**
  - `PROG_001_progression_foundation.md` — DRAFT (this commit) — 21 sections / ~1700 lines / 12 V1-testable acceptance scenarios AC-PROG-1..12 / 30+ deferrals PROG-D1..D32 / 6 open questions PROG-Q1..Q6 (companion to existing CONCEPT_NOTES + REFERENCE_GAMES_SURVEY + CHAOS_BACKEND_REFERENCE)
- **Files modified within `features/00_progression/`:**
  - `_index.md`: replaced concept-row with DRAFT row; folder closure status updated
  - `00_CONCEPT_NOTES.md` §10: status DRAFT promoted (was CONCEPT awaiting lock)
- **Files created within `catalog/`:**
  - `cat_00_PROG_progression.md` — feature catalog with PROG-* namespace (37 catalog entries: 26 V1 ✅ + 5 V1+30d 📦 + 6 V2/V3 📦)
- **Q1-Q7 ALL LOCKED** via 6-batch deep-dive 2026-04-26 (full matrix in `00_CONCEPT_NOTES.md` §11):
  - Q1 Unified ProgressionKind + 3 types (Attribute/Skill/Stage) + BodyOrSoul + derives_from
  - Q6 NEW aggregate `actor_progression` (T2/Reality, owner=Actor)
  - Q2 3 V1 curve types (Linear/Log/Stage) + 4 CapRules + flat tier list + per-tier WithinTierCurve override + Q2j validity matrix
  - Q3 Action + Time training; day-boundary `Scheduled:CultivationTick` Generator (5th after RES_001's 4); 3 V1 TrainingConditions
  - Q4 REVISED **Hybrid observation-driven NPC model** (PCs eager + Tracked NPCs lazy + Untracked = no aggregate; future AI Tier feature owns 3-tier semantics)
  - Q5 REVISED NO atrophy V1; V1+ lazy at materialization (NOT Generator)
  - Q7 Hybrid combat damage V1 (LLM proposes within engine bounds; silent clamp); DF7-full V1+
- **Major architectural insights LOCKED:**
  - **Quantum-observation NPC model** (PROG-A4) — Schrödinger pattern; solves billion-NPC scaling
  - **Future AI Tier feature reservation** (`16_ai_tier/` placeholder) — 3-tier NPC architecture; user kickoff post PROG_001 DRAFT
  - **chaos-backend Subsystem pattern** lift candidate V1+30d (PROG-D6)
  - **DF7 PC Stats placeholder SUPERSEDED** at DRAFT (DF7-V1+ becomes "Combat Damage Formulas Full" sub-feature)
  - **RES_001 alignment concern** flagged (PROG-D19) — RES_001 NPC eager auto-collect inconsistent với quantum-observation; V1+30d closure pass migrates to lazy materialization
  - **i18n compliance** throughout (RES_001 §2 cross-cutting pattern)
  - **BodyOrSoul discriminator NEW** (PROG-A5) — xuyên không cross-reality stat translation hint
- **NEW EVT-T3 sub-shapes** (registered at next 07_event_model agent pass):
  - `ProgressionDelta { actor_ref, kind_id, delta_kind: RawValueIncrement / TierAdvance / TierRegress V1+ / DirectSet }`
  - `ActorProgressionMaterialized { actor_ref, materialized_at_fiction_ts, deltas: Vec<ProgressionDelta> }` (lazy-materialization batch wrapper)
  - `BreakthroughAdvance { actor_ref, kind_id, from_tier, to_tier }` (cascade-trigger)
- **NEW EVT-T5 sub-type:**
  - `Scheduled:CultivationTick` (day-boundary; sequenced 5th after RES_001's 4 Generators)
- **NEW EVT-T8 AdminAction sub-shapes:**
  - `Forge:GrantProgression` (DirectSet variant; author override)
  - `Forge:TriggerBreakthrough` (Forge-triggered breakthrough check)
- **NEW PROG-V1..V4 validator slots** (registered at `_boundaries/03_validator_pipeline_slots.md` next pass):
  - PROG-V1 ProgressionDeltaValidator
  - PROG-V2 BreakthroughConditionCheck
  - PROG-V3 StrikeFormulaBoundsCheck
  - PROG-V4 ProgressionSchemaValidator
- **9 downstream impact items deferred to follow-up commits** (per PROG_001 §20.2):
  - HIGH: WA_003 ForgeEditAction enum (2 new sub-shapes) / PCS_001 brief §4.4 + §S5 + §S8 update / PL_005 closure §9.1 cascade reference / 07_event_model agent registration
  - MEDIUM: NPC_001 closure §6 persona assembly + Tracked NPC lazy doc / DF7 placeholder retirement in `decisions/deferred_DF01_DF15.md`
  - LOW: PL_006 closure note Hungry≥4 forbid cultivation V1+ / WA_006 closure note progression reset on death V1+
  - V1+30d: RES_001 closure pass NPC eager → lazy migration (PROG-D19 alignment)
- **Future feature reservations:**
  - `features/16_ai_tier/` placeholder (3-tier NPC architecture; pending user kickoff)
  - CULT_001 Cultivation Foundation V1+ priority (per IDF folder closure roadmap; PROG_001 ships substrate sufficient for tu tiên without CULT_001; CULT_001 V1+ adds wuxia-specific extensions)
- **Foundation tier 6/6 COMPLETE 2026-04-26:** EF_001 (WHO) + PF_001 (WHERE-semantic) + MAP_001 (WHERE-graph) + CSC_001 (WHAT-inside-cell) + RES_001 (WHAT-flows-through-entity) + **PROG_001 (HOW-actors-grow)** all DRAFT or higher. Tier 5 Actor Substrate (IDF/FF) coexisting tier.
- **ORG-* namespace alignment concern noted:** `15_organization/` was V3 reserved with ORG-*; IDF_004 Origin Foundation also took ORG-*. Conflict; `15_organization/` may need rename (FAC-* per FF_001 closure changelog suggestion). Not PROG_001 scope; flagged for cross-feature coordination at next IDF closure pass review.
- **Drift watchpoints:** unchanged. PROG_001 doesn't introduce new watchpoints (Q1-Q7 fully resolved before DRAFT promotion via 6-batch deep-dive discipline).
- **Lock RELEASED** at end of this commit
- **Reason / handoff:** PROG_001 DRAFT closes V1 foundation tier (6/6). Q4 REVISED + Q5 REVISED via user-corrected quantum-observation principle (Schrödinger pattern); chaos-backend reference lifted (actor-core aggregation pattern V1+30d candidate; damage law chain V1+ DF7-equivalent). 30+ deferrals catalog spans V1+30d → V3 with future AI Tier feature placeholder. Next priorities: (a) follow-up commits for HIGH downstream items (WA_003 / PCS_001 brief / PL_005 closure / 07_event_model agent), (b) future AI Tier feature kickoff (`16_ai_tier/`), (c) PCS_001 PC Substrate parallel agent kickoff (brief now references 6 foundation features post-PROG_001), (d) push branch to origin (24+ commits ahead).

---

## 2026-04-26 — FF_001 closure pass → CANDIDATE-LOCK + lock RELEASE (commit 4/4 FINAL)

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session → None (RELEASE after 4-commit FF_001 cycle)
  - `01_feature_ownership_matrix.md`:
    - `family_node` row: DRAFT → **CANDIDATE-LOCK 2026-04-26 closure pass 4/4**
    - `dynasty` row: DRAFT → **CANDIDATE-LOCK 2026-04-26 closure pass 4/4**
- **FF_001 status header DRAFT → CANDIDATE-LOCK 2026-04-26**
- **`_index.md` FF_001 row updated:** status CANDIDATE-LOCK + 4-commit cycle reference
- **`_index.md` folder status:** Open → COMPLETE 2026-04-26

### FF_001 FOUNDATION FOLDER MILESTONE SUMMARY (4 commits across single lock-cycle)

Files created (cumulative):
- features/00_family/_index.md (folder index; updated to COMPLETE)
- features/00_family/00_CONCEPT_NOTES.md (Q1-Q8 LOCKED + V1 scope populated)
- features/00_family/01_REFERENCE_GAMES_SURVEY.md (8-system market survey)
- features/00_family/FF_001_family_foundation.md (~700 lines DRAFT spec)

Boundary expansions:
- 2 NEW aggregates: family_node (T2/Reality) + dynasty (T2/Reality sparse)
- 1 NEW EVT-T4 sub-type: FamilyBorn
- 2 NEW EVT-T8 sub-shapes: Forge:EditFamily + Forge:RegisterDynasty
- 1 NEW namespace: family.* (8 V1 rule_ids + 4 V1+ reservations)
- 2 NEW RealityManifest extensions: canonical_dynasties + canonical_family_relations (REQUIRED V1; sparse)
- 1 NEW Stable-ID prefix: FF-*

Q1-Q8 LOCKED (per 2db3fc2 deep-dive):
- Q1 (A) Separate family_node aggregate
- Q2 (B2) Explicit direct relations V1; extended computed V1+
- Q3 (A) Separate dynasty aggregate sparse
- Q4 (A) V1+ FAC_001 owns sect lineage
- Q5 (B) Materialized only; events in channel stream per EVT-A10 (REVISION: no separate family_event_log)
- Q6 (B) Adoption flag via 6-variant RelationKind enum
- Q7 (A) V1 strict single-reality
- Q8 (A) V1+ deferred bloodline traits

Cross-feature integration resolved:
- IDF_004 ORG-D12 lineage_id opaque V1 tag → FF_001 V1+ family_node + dynasty resolution
- WA_006 mortality death events → FF_001 EVT-T3 MarkDeceased on family_node
- V1+ NPC_002 family-cascade opinion drift hook reserved (FF-D10)
- V1+ TIT_001 Title Foundation hook reserved (FF-D8)
- V1+ RAC-D3 + V1+ CULT_001 bloodline trait inheritance hook reserved (FF-D1)

V1 quantitative summary:
- 2 aggregates V1 (revised down from initial 3 estimate per Q5)
- 6-variant RelationKind enum
- 8 V1 family.* rule_ids + 4 V1+ reservations
- 10 V1-testable AC-FF-1..10 + 4 V1+ deferred
- 12 deferrals (FF-D1..D12)
- ~700-line DRAFT spec

V1 reality presets coverage:
- Wuxia: Lý dynasty + 4 family_node rows (LM01 orphan + Tiểu Thúy/Lão Ngũ family + Du sĩ wandering)
- Modern: 0-1 dynasty + 3-5 family_node rows
- Sci-fi: deferred V1+

i18n: V1 ships I18nBundle from day 1 per RES_001 §2 contract.

CANDIDATE-LOCK → LOCK gate: AC-FF-1..10 V1-testable scenarios pass integration tests against Wuxia + Modern reality fixtures + WA_006 death cascade integration.

NEW V1+ priority roadmap (locked order; per IDF + FF_001 closure):
1. ✓ IDF folder closure (15 commits) — DONE
2. ✓ FF_001 Family Foundation (4 commits) — DONE (this commit)
3. **PCS_001 PC substrate** (next; consumes IDF + RES_001 + FF_001 + PROG_001-when-ready) — BLOCKED on PROG_001 by parallel agent
4. NPC_NNN mortality (mirrors PCS_001 mortality state machine)
5. FAC_001 Faction Foundation (sect/order/clan/guild; consumes IDF_004/005 + FF_001 dynasty)
6. REP_001 Reputation Foundation (per-(actor, faction) reputation)
7. CULT_001 Cultivation Foundation (wuxia-genre-specific; defer)

Drift watchpoints unchanged at 8 active.

Lock RELEASED at end of this commit.

---

## 2026-04-26 — FF_001 Phase 3 cleanup (commit 3/4)

- Lock continues from commit 2/4
- No boundary changes (Phase 3 = internal documentation cleanup)
- 6 Phase 3 fixes applied: DynastyId typed newtype + RelationKind sibling storage clarification + Marriage flow bidirectional sync explicit + WA_006 death flow one-way + AC-FF-9 refs preserved + §15.4 LOCK criterion split
- §19 readiness checklist updated

---

## 2026-04-26 — FF_001 Family Foundation DRAFT promotion + boundary register (commit 2/4)

- **Lock claim:** main session 2026-04-26 (FF_001 single-feature 4-commit cycle: lock-Q-decisions [done 2db3fc2] + DRAFT [this] + Phase 3 + closure+release); this commit `[boundaries-lock-claim]`
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: claimed by main session 2026-04-26 (FF_001 DRAFT promotion cycle)
  - `01_feature_ownership_matrix.md`:
    - NEW row: `family_node` aggregate (T2/Reality, FF_001 DRAFT 2026-04-26 — Tier 5 Actor Substrate post-IDF priority per IDF_004 ORG-D12)
    - NEW row: `dynasty` aggregate (T2/Reality sparse storage, FF_001 DRAFT)
    - EVT-T4 System sub-type ownership: NEW `FamilyBorn` (FF_001 owns; emitted alongside EF_001 EntityBorn at canonical seed)
    - EVT-T8 Administrative sub-shape ownership: NEW `Forge:EditFamily` + `Forge:RegisterDynasty` (FF_001 owns)
    - Stable-ID prefix table: NEW `FF-*` row (axioms / deferrals / decisions; catalog/cat_00_FF_family_foundation.md TBD)
  - `02_extension_contracts.md`:
    - §1.4 RejectReason namespace: NEW `family.*` row with 8 V1 rule_ids (unknown_actor_ref / unknown_dynasty_id / bidirectional_sync_violation / cyclic_relation / duplicate_relation / relation_kind_mismatch / deceased_target / synthetic_actor_forbidden) + 4 V1+ reservations (cross_reality_mismatch / cyclic_lineage_traversal / dynasty_extinction / adoption_consent_violation)
    - §2 RealityManifest: NEW `canonical_dynasties: Vec<DynastyDecl>` + `canonical_family_relations: Vec<FamilyRelationDecl>` REQUIRED V1 extensions; 6-variant RelationKind enum locked (BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling)
- **FF_001 file:** created `FF_001_family_foundation.md` (~700 lines DRAFT spec mirroring EF/PF/MAP/CSC/RES/IDF pattern). 10 V1-testable AC-FF-1..10 + 4 V1+ deferred. 12 deferrals FF-D1..D12.
- **Q1-Q8 LOCKED** (per commit 2db3fc2):
  - Q1 (A) Separate family_node aggregate
  - Q2 (B2) Explicit direct relations V1
  - Q3 (A) Separate dynasty aggregate (sparse)
  - Q4 (A) V1+ FAC_001 owns sect lineage; FF_001 = biological/adoption only
  - Q5 (B) Materialized only; events in channel stream per EVT-A10 (NO separate family_event_log)
  - Q6 (B) Adoption flag via 6-variant RelationKind enum
  - Q7 (A) V1 strict single-reality
  - Q8 (A) V1+ deferred bloodline traits (FF-D1)
- **Reason:** Tier 5 Actor Substrate Foundation post-IDF priority. FF_001 resolves IDF_004 lineage_id opaque V1 tag per ORG-D12. Wuxia critical (sect lineage / family inheritance / dynasty politics). Single-feature lock cycle (3 commits remaining: this + Phase 3 + closure+release).
- **Drift watchpoints unchanged at 8 active.**
- **Lock continues:** still claimed for FF_001 Phase 3 (commit 3/4) + closure pass (commit 4/4 with `[boundaries-lock-release]` prefix).

---

## 2026-04-26 — IDF folder 15/15 FINAL: IDF_005 closure pass → CANDIDATE-LOCK + lock RELEASE

- **Lock RELEASED** at end of this commit (`[boundaries-lock-release]`)
- **Files modified within `_boundaries/`:**
  - `_LOCK.md`: Owner main session 2026-04-26 → None (RELEASE after 15-commit cycle)
  - `01_feature_ownership_matrix.md` actor_ideology_stance row: DRAFT → **CANDIDATE-LOCK 2026-04-26 IDF folder closure 15/15 FINAL**
- **IDF_005 status header:** DRAFT → CANDIDATE-LOCK
- **`_index.md` IDF_005 row + folder status:** updated CANDIDATE-LOCK + folder closure COMPLETE
- **5/5 IDF features now CANDIDATE-LOCK** — Tier 5 Actor Substrate Foundation milestone

### IDF FOLDER CLOSURE MILESTONE SUMMARY (15 commits)

5 features at CANDIDATE-LOCK 2026-04-26:
- IDF_001 Race (commits 1-3): RaceId + 6-variant SizeCategory + race_assignment + races RealityManifest extension
- IDF_002 Language (commits 4-6): LanguageId distinct from LangCode + actor_language_proficiency 4-axis × 5-level + languages RealityManifest extension; SPIKE_01 turn 5 reproducibility gate
- IDF_003 Personality (commits 7-9): 12 V1 archetypes per POST-SURVEY-Q1 + actor_personality + 5-variant VoiceRegister + personality_archetypes RealityManifest extension; resolves PL_005b speaker_voice orphan ref + PL_005c INT-INT-D5
- IDF_004 Origin (commits 10-12): V1 minimal stub 4 fields + actor_origin + origin_packs OPTIONAL V1; ORG-D12 FF_001 V1+ HIGH priority
- IDF_005 Ideology (commits 13-15): ONLY mutable IDF aggregate + actor_ideology_stance multi-stance + ideologies REQUIRED V1; free V1 conversion per IDL-Q13 (POST-SURVEY-Q3); IDL-D11 cost mechanic V1+

Boundary expansions (cumulative across 15 commits):
- 5 NEW aggregates registered in 01_feature_ownership_matrix.md
- 5 NEW EVT-T8 sub-shapes (Forge:Edit{Race,Language,Personality,Origin,Ideology}*)
- 1 NEW EVT-T4 sub-type (RaceBorn for IDF_001)
- 5 NEW namespaces in 02_extension_contracts.md §1.4 (race.* / language.* / personality.* / origin.* / ideology.*) — total 19 V1 rule_ids + 15 V1+ reservations
- 5 NEW RealityManifest extensions in §2 (4 REQUIRED V1 + 1 OPTIONAL V1)
- 5 NEW Stable-ID prefixes (RAC-* / LNG-* / PRS-* / ORG-* / IDL-*)

Cross-feature integration resolved:
- PL_005b §2.1 speaker_voice orphan ref → resolved by IDF_003
- PL_005c INT-INT-D5 per-personality opinion modifier → resolved by IDF_003 opinion_modifier_table
- PL_005c §4 cross-cutting opinion calculation → V1+ formula: base + agent_personality_mod[recipient] + recipient_personality_mod[agent] + agent_race_mod[recipient] (V1+ RAC-D2) + agent_origin_mod[recipient] (V1+ ORG-D8) + agent_ideology_mod[recipient] (V1+ IDL-D3)

Total V1 acceptance scenarios: 50 (10 per feature × 5 features) + 12 V1+ deferred.
Total deferrals: 51 (RAC-D1..D11 + LNG-D1..D9 + PRS-D1..D7+D-NEW + ORG-D1..D12 + IDL-D1..D11).

Reality presets ship V1:
- Wuxia: 5 races / 4 languages / 12 archetypes (universal) / origin packs empty V1 / 5 ideologies
- Modern: 1 race / 3 languages / 12 archetypes / origin packs empty V1 / 3 ideologies
- Sci-fi: 3 races / 3 languages / 12 archetypes / origin packs empty V1 / 3 ideologies

i18n cross-cutting (RES_001 §2.3 I18nBundle): all 5 IDF features ship I18nBundle from day 1 for declarative names (greenfield; no legacy backfill per IDF-FOLDER-Q7).

NEW V1+ feature roadmap (locked priority order; per POST-SURVEY survey + IDF folder closure):
1. **FF_001 Family Foundation** — HIGH PRIORITY post-IDF (BEFORE PCS_001) per POST-SURVEY-Q4 + ORG-D12. Owns family_graph + dynasty + Birth/Marriage/Death/Divorce/Adoption events + family-driven opinion modifier. Wuxia REQUIRES (sect lineage / family inheritance / dynasty politics).
2. **PCS_001 PC substrate** — consumes IDF (Race/Language/Personality/Origin/Ideology) + RES_001 vital_pool + FF_001 family_graph. PC creation form selects from reality's allowed sets.
3. **NPC_NNN mortality** — replaces NPC_003 mortality references (NPC_003 was re-purposed to NPC Desires per `9068543`); mirrors PCS_001 mortality state machine pattern.
4. **FAC_001 Faction Foundation** — sect / order / clan / guild membership; depends on FF_001 + IDF_004/005.
5. **REP_001 Reputation Foundation** — per-(actor, faction) reputation projection; depends on FAC_001.
6. **CULT_001 Cultivation Foundation** — Wuxia-genre-specific mutable cultivation realm tier (per RAC-D11 / POST-SURVEY-Q5); defer until first non-SPIKE_01 wuxia content.

Society V1 ready (PCS+NPC+FF+FAC+REP) = ~44 commits across ~7-9 lock-cycles total.

Drift watchpoints unchanged at 8 active.

Lock RELEASED with `[boundaries-lock-release]` prefix at end of this commit.

---

## 2026-04-26 — IDF folder 14/15: IDF_005 Phase 3 cleanup

5 fixes (IdeologyId typed newtype confirmed + Synthetic exclusion + cross-feature seed flow + §15.4 LOCK split + IDL-D11 cost mechanic V1+ landing). No boundary changes.

---

## 2026-04-26 — IDF folder 13/15: IDF_005 Ideology Foundation DRAFT + boundary register

- Lock continues from commit 1/15
- `01_feature_ownership_matrix.md`: NEW row actor_ideology_stance (T2/Reality, IDF_005 DRAFT — **ONLY mutable IDF aggregate V1**); EVT-T8 Forge:EditIdeologyStance; IDL-* prefix
- `02_extension_contracts.md`: §1.4 ideology.* (3 V1 rules + 5 V1+); §2 RealityManifest ideologies REQUIRED V1
- IDF_005 file: renamed concept → DRAFT; full §1-§19 spec
- IDL-Q13 NEW LOCKED: free V1 conversion per POST-SURVEY-Q3
- IDL-D11 NEW: conversion cost mechanic V1+ (when scheduler V1+30d ships OR IDL-D3 ideology-conflict modifier ships)
- Multi-stance V1 per IDL-Q2 LOCKED (Wuxia syncretism)
- 10 V1-testable AC + 2 V1+ deferred; 11 deferrals (IDL-D1..D11)

---

## 2026-04-26 — IDF folder 12/15: IDF_004 closure pass → CANDIDATE-LOCK

4/5 IDF features now CANDIDATE-LOCK. Lock continues claimed for IDF_005 final cycle (commits 13-15).

---

## 2026-04-26 — IDF folder 11/15: IDF_004 Phase 3 cleanup

5 fixes (typed newtypes + Synthetic exclusion + cross-feature seed flow + §15.4 LOCK split + ORG-D12 FF_001 priority confirmed). No boundary changes.

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
