<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_16_AIT_ai_tier.md
namespace: AIT-*
generated_by: hand-authored (architecture-scale catalog seed)
-->

## AIT — AI Tier (architecture-scale; 3-tier NPC architecture for billion-NPC scaling; quantum-observation lazy materialization)

> Architecture-scale catalog. NOT a foundation tier feature (foundation 6/6 closed at PROG_001). AIT_001 is Tier 5+ Actor Substrate scaling/architecture feature. Owns `AIT-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `AIT-A*` | Axioms (locked invariants) |
> | `AIT-D*` | Per-feature deferrals (V1+30d / V2 / V3 phases) |
> | `AIT-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**AIT-A1 (3-tier NPC architecture):** NPCs split into PC + Major + Minor + Untracked tiers per Q1 LOCKED. PC = always tracked + full agency. Major = limited count + LLM-driven. Minor = moderate count + rule-based scripted. Untracked = ephemeral + LLM/RNG-generated per session + discarded.

**AIT-A2 (Quantum-observation principle):** NPC state stale-until-observed (Schrödinger pattern; consistent with PROG_001 Q4 REVISED). PCs eager Generator; Tracked NPCs lazy materialization on observation; Untracked NPCs = no aggregate (semantic absence).

**AIT-A3 (Deterministic Untracked generation):** Untracked NpcId + stats + names derive from `blake3(reality_id || cell_id || fiction_day || slot_index)`. Replay-safe per EVT-A9.

**AIT-A4 (Hybrid 2-stage generation):** Stage 1 template+RNG (cheap, deterministic, at cell-entry) + Stage 2 LLM-flavor (lazy, on first interaction, cached per session). Bounded LLM cost.

**AIT-A5 (Daily Untracked rotation):** Same fiction-day re-entry → same Untracked (deterministic). New day → different Untracked (natural crowd rotation). Discard at cell-leave + session-end.

**AIT-A6 (Author-required canonical tier):** Canonical NPCs (author-declared in RealityManifest) MUST have `tracking_tier` explicitly chosen (Major or Minor). Untracked NEVER in canonical_actor_decl.

**AIT-A7 (NpcId stable at promotion):** Forge promotion (Untracked → Tracked) preserves blake3-derived NpcId. Persona crystallizes into NPC_001 npc core.

**AIT-A8 (Tier-aware action availability):** PC/Major full PL_005 range; Minor scripted-only (Speak canned + Use training + passive Examine target); Untracked target-only (cannot initiate).

**AIT-A9 (Tier-aware AssemblePrompt budget):** PC/Major FullPersona; Minor CondensedPersona; Untracked SummaryLine. Roster caps per tier with aggregate overflow format.

**AIT-A10 (English IDs + I18nBundle):** Conforms to RES_001 §2 cross-cutting i18n contract.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| AIT-1 | `NpcTrackingTier` 2-variant enum (Major / Minor); Untracked = no aggregate | ✅ | V1 | PROG-25 (tracking_tier field) | [AIT_001 §3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#3-npctrackingtier-enum-q1-locked) |
| AIT-2 | Author-required `tracking_tier` on CanonicalActorDecl | ✅ | V1 | NPC_001 closure pass | [AIT_001 §4.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#41-canonical-npc-tier-q2a) |
| AIT-3 | Forge `PromoteUntrackedToTracked` AdminAction | ✅ | V1 | WA_003 closure pass | [AIT_001 §4.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#43-forge-promotion-path-v1-q2c) |
| AIT-4 | Deterministic Untracked NpcId via blake3 seed | ✅ | V1 | EVT-A9 (replay determinism) | [AIT_001 §4.6](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#46-untracked-npcid-scoping-q2f) |
| AIT-5 | TierCapacityCaps RealityManifest field (defaults Major≤20 / Minor≤100) | ✅ | V1 | NPC_001 | [AIT_001 §4.8](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#48-tiercapacitycaps-q2h) |
| AIT-6 | Hybrid 2-stage Untracked generation (Stage 1 template+RNG / Stage 2 LLM-flavor lazy) | ✅ | V1 | LLM service / RNG-A9 | [AIT_001 §5](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#5-untracked-npc-generation-pipeline-q4q5q11-locked) |
| AIT-7 | UntrackedTemplateDecl per PlaceType (role list + name_pool + stat_ranges + appearance_hints) | ✅ | V1 | PF-1 (PlaceType), PROG-4 | [AIT_001 §5.2](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#52-untrackedtemplatedecl-q4b) |
| AIT-8 | Cell-entry generation timing with daily rotation | ✅ | V1 | EF-1 (entity_binding), EVT-G2 | [AIT_001 §5.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#53-generation-timing-q5a-d) |
| AIT-9 | EVT-T5 `Generated:UntrackedNpcSpawn` sub-type | ✅ | V1 | EVT-A11 | [AIT_001 §12.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#121-v1-generators) |
| AIT-10 | EVT-T5 `Generated:UntrackedNpcDiscarded` sub-type with 3 V1 reason variants | ✅ | V1 | EVT-A11 | [AIT_001 §12.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#121-v1-generators) |
| AIT-11 | NpcId stable at promotion (Q11a); persona crystallization | ✅ | V1 | NPC_001 | [AIT_001 §5.6](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#56-q11-promotion-preserves-npcid) |
| AIT-12 | Cell-leave + session-end discard policy | ✅ | V1 | PL_001 (session lifecycle) | [AIT_001 §6](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#6-discard-policy-v1-q6-locked) |
| AIT-13 | 4-tier × 4-capability behavior matrix | ✅ | V1 | PL-5 | [AIT_001 §7.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#71-capability-matrix) |
| AIT-14 | MinorBehaviorScript per actor_class (DialogueTemplate + ScheduledActionDecl + ReactionDecl) | ✅ | V1 | NPC-1 | [AIT_001 §7.2](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#72-minorbehaviorscript-pattern-q7b) |
| AIT-15 | NPC_002 Chorus tier filter (Major full / Minor low / Untracked excluded) | ✅ | V1 | NPC-7 | [AIT_001 §7.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#73-npc_002-chorus-tier-filter-q7e) |
| AIT-16 | DensityDecl V1 (fixed count + 12 cap + engine defaults per PlaceType) | ✅ | V1 | PF-1 | [AIT_001 §8](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#8-per-cell-type-untracked-density-q8-locked) |
| AIT-17 | Tier × InteractionKind matrix (Q9a) | ✅ | V1 | PL-5 | [AIT_001 §9.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#91-action--tier-matrix-q9a) |
| AIT-18 | AIT-V1 TierActionValidator at PL_005 pre-validation | ✅ | V1 | PL-5 closure pass | [AIT_001 §9.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#93-ait-v1-tieractionvalidator-q9e) |
| AIT-19 | Untracked target-only behaviors (Examine triggers Stage 2; Strike applies PROG_001 Q7 combat) | ✅ | V1 | PROG-16 (combat formula) | [AIT_001 §9.2](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#92-untracked-target-behavior-q9b) |
| AIT-20 | PromptDetail enum (FullPersona / CondensedPersona / SummaryLine / Hidden) | ✅ | V1 | NPC-1 | [AIT_001 §10.1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#101-promptdetail-enum) |
| AIT-21 | TierRosterCaps RealityManifest field (defaults 5 Full + 8 Condensed + 12 Summary; Aggregate overflow) | ✅ | V1 | NPC-1 | [AIT_001 §10.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#103-tierrostercaps-q12d) |
| AIT-22 | Tier-priority + Chorus-priority AssemblePrompt composition | ✅ | V1 | NPC-7 | [AIT_001 §10.4](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#104-assembleprompt-composition-q12c) |
| AIT-23 | EVT-T3 `TrackingTierTransition` cascade-trigger sub-shape | ✅ | V1 | EVT-A11 | [AIT_001 §12.4](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#124-new-evt-t3-cascade-trigger) |
| AIT-24 | EVT-T8 `Forge:PromoteUntrackedToTracked` AdminAction sub-shape | ✅ | V1 | WA-3 | [AIT_001 §4.3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#43-forge-promotion-path-v1-q2c) |
| AIT-25 | AIT-V1..V4 validator slots (TierAction / TierCapacity / Density / UntrackedTemplate validators) | ✅ | V1 | PL-5, RealityManifest | [AIT_001 §13](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#13-validator-chain) |
| AIT-26 | `ai_tier.*` RejectReason namespace (8 V1 rule_ids + 4 V1+ reservations) | ✅ | V1 | AIT-1..25 | [AIT_001 §15](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#15-rejectreason-rule_id-catalog) |
| AIT-27 | RealityManifest 5 OPTIONAL V1 extensions (tier_capacity_caps + untracked_templates + cell_untracked_density + tier_roster_caps + minor_behavior_scripts) | ✅ | V1 | AIT-5/7/16/21/14 | [AIT_001 §11](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#11-realitymanifest-extensions) |
| AIT-28 | V1+30d — Auto-promotion via significance threshold (AIT-D1) | 📦 | V1+ | AIT-3 | [AIT_001 §1 AIT-D1](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-29 | V1+30d — Demotion via Forge (AIT-D2) | 📦 | V1+ | AIT-3 | [AIT_001 §1 AIT-D2](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-30 | V1+30d — Causal-ref pin for Untracked persistence (AIT-D6) | 📦 | V1+ | AIT-12 | [AIT_001 §1 AIT-D6](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-31 | V1+30d — On-demand generation beyond cell-entry (AIT-D8) | 📦 | V1+ | AIT-8 | [AIT_001 §1 AIT-D8](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-32 | V1+30d — Minor scripted attacks + richer behavior (AIT-D18) | 📦 | V1+ | AIT-13/14 | [AIT_001 §1 AIT-D18](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-33 | V1+30d — RES_001 NPC eager → lazy migration alignment (PROG-D19 cross-feature) | 📦 | V1+ | RES_001 closure pass | [AIT_001 §14.8](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#148-res_001-resource-foundation) |
| AIT-34 | V2 — Legendary tier (DF Legends mode for fully-simulated historical figures) | 📦 | V2 | AIT-1 | [AIT_001 §1 AIT-D3](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-35 | V2 — Untracked-to-Untracked interactions (NPC-to-NPC during un-observed) | 📦 | V2 | AIT-13 | [AIT_001 §1 AIT-D11](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| AIT-36 | V3 — Faction tier collective entity | 📦 | V3 | FAC_001 | [AIT_001 §1 AIT-D4](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#v1-not-shipping-deferred-per-q-decisions) |

### V1 minimum delivery

27 V1 catalog entries (AIT-1..27 all ✅ V1). Architecture-scale companion to PROG_001 + NPC_001.

### V1+30d deferrals (AIT-28..33)

6 V1+30d items planned for the 30-day fast-follow window after V1 ship:
- Auto-promotion / Demotion / Causal-ref pin / On-demand generation / Minor scripted richer behavior / RES_001 alignment

### V2+ deferrals (AIT-34..36)

3 deferrals tied to V2 expansion (Legendary tier / Untracked-to-Untracked) and V3 (Faction tier — coordinates with future REP_001 / FAC_001 V3 expansion).

### Coordination / discipline notes

- **NOT a foundation:** Foundation tier remains 6/6 (closed at PROG_001). AIT_001 is architecture-scale.
- **PROG_001 tracking_tier activation:** AIT_001 DRAFT activates the field that PROG_001 §3.1 reserved as `Option<NpcTrackingTier>` (None V1 default → Major/Minor populated by author).
- **NPC_001 / WA_003 / PL_005 / NPC_002 / PL_001 closure passes** all required for AIT_001 V1 functionality (10 §20.2 downstream items).
- **chaos-backend reference** (cited via PROG_001 §2 i18n + PROG-D6 Subsystem stacking) — AIT_001 Stage 1 generation pattern echoes Stellaris pop generation.
- **Future feature interplay:** PCS_001 (PCs always None tier) / CULT_001 (Major-tier cultivation only) / FAC_001 (Tracked-only membership) / REP_001 (Tracked-only reputation) — AIT_001 ships orthogonal substrate; future features layer on.
- **i18n compliance** throughout per RES_001 §2 cross-cutting pattern.
- **20+ downstream impact items** tracked in [AIT_001 §20.2](../features/16_ai_tier/AIT_001_ai_tier_foundation.md#202-deferred-follow-up-commits-downstream-features) for follow-up commits.
