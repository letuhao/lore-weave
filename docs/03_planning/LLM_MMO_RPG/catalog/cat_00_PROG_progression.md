<!-- CHUNK-META
source: design-track manual seed 2026-04-26
chunk: cat_00_PROG_progression.md
namespace: PROG-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## PROG — Progression Foundation (foundation tier; 6th foundation feature; multi-genre dynamic progression substrate)

> Foundation-level catalog. Owns `PROG-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `PROG-A*` | Axioms (locked invariants) |
> | `PROG-D*` | Per-feature deferrals (V1+30d / V2 / V3 phases) |
> | `PROG-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**PROG-A1 (Author-configurable per-reality schema):** Engine cannot fix progression schema; modern social ≠ tu tiên cultivation ≠ traditional D&D. Author declares ProgressionKindDecl per reality. Empty schema = sandbox/freeplay reality with no progression (valid V1).

**PROG-A2 (No level / no chiến lực):** No central "level" attribute. No automatic power-rating sum. Each ProgressionKind is independent measurement. Combat outcomes derive from RELEVANT specific attributes/skills, not aggregate.

**PROG-A3 (Unified ProgressionKind ontology):** Attribute / Skill / Stage share invariants (non-transferable + growth-driven + capped + actor-scoped + author-declared). Single `actor_progression` aggregate with type discriminator. Pattern matches PL_006 unified actor_status.

**PROG-A4 (Quantum-observation NPC model):** PCs eager Generator iteration; Tracked NPCs lazy materialization on observation; Untracked NPCs = no aggregate (future AI Tier feature). Schrödinger pattern solves billion-NPC scaling.

**PROG-A5 (Body-or-soul progression discriminator):** Each ProgressionKind declares `body_or_soul` for xuyên không cross-reality stat translation. Body progressions follow body; Soul progressions follow soul. Default Body.

**PROG-A6 (Hybrid combat damage V1):** LLM proposes damage_amount within engine-bounded range derived from PROG_001 stats. Silent clamp on out-of-range (preserves narrative flow). Full chaos-backend law chain V1+ DF7-equivalent.

**PROG-A7 (English IDs + I18nBundle):** Conforms to RES_001 §2 cross-cutting i18n contract — stable IDs English; user-facing strings I18nBundle.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PROG-1 | `actor_progression` aggregate (T2/Reality, owner=Actor only V1; Item V1+30d reserved) | ✅ | V1 | EF-1, DP-A14 | [PROG_001 §3.1](../features/00_progression/PROG_001_progression_foundation.md#31-actor_progression-t2--reality--primary) |
| PROG-2 | `ProgressionType` enum (Attribute/Skill/Stage V1; ResourceBound V1+30d) | ✅ | V1 | PROG-1 | [PROG_001 §4.2](../features/00_progression/PROG_001_progression_foundation.md#42-progressiontype-enum) |
| PROG-3 | `BodyOrSoul` discriminator (Body/Soul/Both) for xuyên không cross-reality stat translation | ✅ | V1 | PROG-1, PCS-* | [PROG_001 §4.3](../features/00_progression/PROG_001_progression_foundation.md#43-bodyorsoul-discriminator-q1-new-for-xuyên-không) |
| PROG-4 | `ProgressionKindDecl` shape (RealityManifest declaration) | ✅ | V1 | PROG-2, PROG-3, RES-23 (i18n) | [PROG_001 §4.4](../features/00_progression/PROG_001_progression_foundation.md#44-progressionkinddecl-realitymanifest-declaration-shape) |
| PROG-5 | `derives_from` field — Skill ← Attribute training rate scaling V1 | ✅ | V1 | PROG-4 | [PROG_001 §4.5](../features/00_progression/PROG_001_progression_foundation.md#45-derives_from-v1-mechanics) |
| PROG-6 | `CurveDecl` enum (Linear / Log / Stage; flat tier list; per-tier WithinTierCurve override) | ✅ | V1 | PROG-4 | [PROG_001 §5.1](../features/00_progression/PROG_001_progression_foundation.md#51-curvedecl-enum) |
| PROG-7 | `TierDecl` + `BreakthroughCondition` (AtMax / AtMaxPlus / AuthorOnly) | ✅ | V1 | PROG-6, RES-6 (Consumable), PF-1 (PlaceType) | [PROG_001 §5.2-5.3](../features/00_progression/PROG_001_progression_foundation.md#52-tierdecl-stage-type) |
| PROG-8 | `CapRule` enum (SoftCap / HardCap / TierBased / Unbounded) + Q2j validity matrix | ✅ | V1 | PROG-4 | [PROG_001 §5.4-5.5](../features/00_progression/PROG_001_progression_foundation.md#54-caprule-enum) |
| PROG-9 | `TrainingRuleDecl` + `TrainingSource` enum (Action + Time V1; Mentor V1+30d / Quest V2) | ✅ | V1 | PROG-4, PL-5 (Action), EVT-G2 (Time) | [PROG_001 §6.1](../features/00_progression/PROG_001_progression_foundation.md#61-trainingruledecl) |
| PROG-10 | `TrainingCondition` enum (LocationMatch + StatusRequired + StatusForbidden V1) | ✅ | V1 | PROG-9, PF-1, PL-6 (StatusFlag) | [PROG_001 §6.1](../features/00_progression/PROG_001_progression_foundation.md#61-trainingruledecl) |
| PROG-11 | Action-driven training cascade — PL_005 hot-path post-validation indexed by InteractionKind | ✅ | V1 | PROG-9, PL-5 | [PROG_001 §6.2](../features/00_progression/PROG_001_progression_foundation.md#62-action-driven-training-cascade-q3i) |
| PROG-12 | Time-driven training Generator — `Scheduled:CultivationTick` (day-boundary; sequenced 5th after RES_001's 4) | ✅ | V1 | PROG-9, EVT-G6, RES-21 | [PROG_001 §12.1-12.2](../features/00_progression/PROG_001_progression_foundation.md#121-v1-generators) |
| PROG-13 | Hybrid observation-driven NPC model — PC eager + Tracked NPC lazy + Untracked = no aggregate | ✅ | V1 | PROG-1, future AI Tier feature | [PROG_001 §7](../features/00_progression/PROG_001_progression_foundation.md#7-hybrid-observation-npc-model-q4-revised-locked) |
| PROG-14 | Materialization computation V1 (per-day replay; conservative single-state assumption) | ✅ | V1 | PROG-13, EVT-A9 (replay determinism) | [PROG_001 §7.5](../features/00_progression/PROG_001_progression_foundation.md#75-materialization-computation) |
| PROG-15 | NO atrophy V1 (V1+ lazy-at-materialization; PROG-D5) | ✅ | V1 | PROG-14 | [PROG_001 §8](../features/00_progression/PROG_001_progression_foundation.md#8-atrophy-v1-q5-revised-locked) |
| PROG-16 | Hybrid combat damage formula — `StrikeFormulaDecl` with offense/defense terms + factors + post_damage_hooks | ✅ | V1 | PROG-1, RES-1 (vital_pool), PL-5 (Strike) | [PROG_001 §9](../features/00_progression/PROG_001_progression_foundation.md#9-combat-damage-formula-v1-q7-locked) |
| PROG-17 | Engine default formula (LLM proposes 1..=defender_hp/2 when no author declaration) | ✅ | V1 | PROG-16 | [PROG_001 §9.4](../features/00_progression/PROG_001_progression_foundation.md#94-default-formula-no-author-declaration) |
| PROG-18 | xuyên không BodyOrSoul rule application — body progressions follow body; soul progressions follow soul | ✅ | V1 | PROG-3, PCS_001 §S8 | [PROG_001 §10](../features/00_progression/PROG_001_progression_foundation.md#10-bodysoul--xuyên-không-integration-q1-new) |
| PROG-19 | RealityManifest 4 OPTIONAL V1 extensions (progression_kinds + class_defaults + actor_overrides + strike_formula) | ✅ | V1 | PROG-4, PROG-16 | [PROG_001 §11](../features/00_progression/PROG_001_progression_foundation.md#11-realitymanifest-extensions) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| PROG-20 | EVT-T3 sub-shapes — `ProgressionDelta` + `ActorProgressionMaterialized` + `BreakthroughAdvance` cascade-trigger | ✅ | V1 | EVT-A11, PROG-1 | [PROG_001 §12.5-12.6](../features/00_progression/PROG_001_progression_foundation.md#125-new-evt-t3-sub-shapes) |
| PROG-21 | EVT-T5 sub-type — `Scheduled:CultivationTick` (day-boundary; deterministic per EVT-A9) | ✅ | V1 | PROG-12, EVT-G2 | [PROG_001 §12.1-12.3](../features/00_progression/PROG_001_progression_foundation.md#121-v1-generators) |
| PROG-22 | EVT-T8 AdminAction sub-shapes — `Forge:GrantProgression` + `Forge:TriggerBreakthrough` | ✅ | V1 | PROG-1, WA-3 | [PROG_001 §14.12](../features/00_progression/PROG_001_progression_foundation.md#1412-wa_003-forge) |
| PROG-23 | PROG-V1..V4 validator slots (ProgressionDeltaValidator / BreakthroughConditionCheck / StrikeFormulaBoundsCheck / ProgressionSchemaValidator) | ✅ | V1 | PROG-1, PL-5, PROG-19 | [PROG_001 §13](../features/00_progression/PROG_001_progression_foundation.md#13-validator-chain) |
| PROG-24 | `progression.*` RejectReason namespace (7 V1 rule_ids + 6 V1+ reservations) | ✅ | V1 | PROG-1..23 | [PROG_001 §15.1](../features/00_progression/PROG_001_progression_foundation.md#151-progression-namespace-v1-registered-in-_boundaries02_extension_contractsmd-14) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| PROG-25 | `tracking_tier: Option<NpcTrackingTier>` field reserved (None V1; future AI Tier feature populates) | ✅ | V1 | PROG-13, future `16_ai_tier/` | [PROG_001 §3.1](../features/00_progression/PROG_001_progression_foundation.md#31-actor_progression-t2--reality--primary) |
| PROG-26 | DF7 PC Stats placeholder SUPERSEDED at PROG_001 DRAFT promotion | ✅ | V1 | DF7 placeholder | [PROG_001 §1](../features/00_progression/PROG_001_progression_foundation.md#1-purpose--v1-minimum-scope) |
| PROG-27 | V1+30d — DiscreteLevelup curve (D&D-style player point allocation) | 📦 | V1+ | PROG-6 | [PROG_001 §1 PROG-D1](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-28 | V1+30d — Failed breakthrough narrative event (走火入魔 cultivation deviation) | 📦 | V1+ | PROG-7 | [PROG_001 §1 PROG-D2](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-29 | V1+30d — Skill atrophy lazy-at-materialization | 📦 | V1+ | PROG-14 | [PROG_001 §8.2 PROG-D5](../features/00_progression/PROG_001_progression_foundation.md#82-v1-atrophy-mechanism-shape-lazy-at-materialization) |
| PROG-30 | V1+30d — Subsystem stacking (chaos-backend Contribution pattern lift) | 📦 | V1+ | PROG-1, chaos-backend reference | [PROG_001 §1 PROG-D6](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-31 | V1+30d — RES_001 NPC eager → lazy materialization alignment (PROG-D19) | 📦 | V1+ | PROG-13, RES_001 closure pass | [PROG_001 §7.6 PROG-D19](../features/00_progression/PROG_001_progression_foundation.md#76-res_001-alignment-concern-prog-d19-v130d) |
| PROG-32 | V1+ — DF7-equivalent full damage law chain (chaos-backend element multiplier + resistance + penetration + status chain) | 📦 | V1+ | PROG-16, chaos-backend reference | [PROG_001 §9.1 PROG-D24](../features/00_progression/PROG_001_progression_foundation.md#91-hybrid-v1-architecture) |
| PROG-33 | V2 — Trained Quest source (QST_001 dependency) | 📦 | V2 | QST_001 | [PROG_001 §1 PROG-D14](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-34 | V2 — NPC-to-NPC cascade during un-observed period | 📦 | V2 | PROG-13 | [PROG_001 §1 PROG-D21](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-35 | V3 — Realm-stage nested hierarchy (only if flat tier list proves limiting) | 📦 | V3 | PROG-7 | [PROG_001 §1 PROG-D7](../features/00_progression/PROG_001_progression_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| PROG-36 | V3 — Untracked → Tracked tier promotion (future AI Tier feature owns) | 📦 | V3 | future `16_ai_tier/` | [PROG_001 §7.2 PROG-D22](../features/00_progression/PROG_001_progression_foundation.md#72-future-ai-tier-feature-reservation) |
| PROG-37 | V3+ — `ResourceBound` ProgressionType (mana-pool style with consumption-per-use) | 📦 | V3+ | PROG-2 | [PROG_001 §4.2](../features/00_progression/PROG_001_progression_foundation.md#42-progressiontype-enum) |

### V1 minimum delivery

26 V1 catalog entries (PROG-1..26 all ✅ V1). Foundation tier closure: 6/6 V1 foundation features when PROG_001 lands DRAFT (EF/PF/MAP/CSC/RES/PROG).

### V1+30d deferrals (PROG-27..31)

5 V1+30d items planned for the 30-day fast-follow window after V1 ship. Most schema reservations already in place — zero schema migration cost.

### V2+ deferrals (PROG-32..37)

6 V2/V3 deferrals tied to **DF7-equivalent** full combat (PROG-32) + future feature dependencies (CULT_001 / AI Tier / QST_001).

### Coordination / discipline notes

- **Foundation tier completion 6/6 (2026-04-26):** PROG_001 closes V1 foundation tier. WHO (EF) + WHERE-semantic (PF) + WHERE-graph (MAP) + WHAT-inside-cell (CSC) + WHAT-flows-through-entity (RES) + **HOW-actors-grow (PROG)** all DRAFT or higher.
- **Sibling boundary discipline:** Numeric attribute/skill/stage values + curves + caps + training rules stay in PROG_001. Vital pools (HP/Stamina/Mana) stay in RES_001 (transient state, not progression). Status modifiers (Drunk/Wounded) stay in PL_006 (temporary). Combat damage formulas stay in PROG_001 §9 V1; full chain V1+ DF7-equivalent. Ownership stays in EF_001. Transfer mechanics stay in PL_005.
- **Quantum-observation NPC model** (PROG-A4): PCs eager + Tracked NPCs lazy + Untracked = no aggregate. Solves billion-NPC scaling. Future AI Tier feature owns 3-tier semantics.
- **chaos-backend reference** (PROG-30 / PROG-32): actor-core Subsystem→Contribution pattern V1+30d lift; combat damage law chain V1+ DF7-equivalent.
- **Tier 5 Actor Substrate Foundation coexistence**: PROG_001 + IDF_001..005 + FF_001 all in foundation tier; coordinate per V1+30d Subsystem stacking when stat modifiers integrate.
- **DF7 PC Stats placeholder SUPERSEDED**: PROG_001 V1 covers all actors (not just PC); DF7-V1+ becomes "Combat Damage Formulas Full" sub-feature.
- **17+ downstream impact items** tracked in [PROG_001 §20.2](../features/00_progression/PROG_001_progression_foundation.md#202-deferred-follow-up-commits-downstream-features) for follow-up commits.
