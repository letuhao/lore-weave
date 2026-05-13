<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_00_REP_reputation_foundation.md
namespace: REP-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## REP — Reputation Foundation (foundation tier; Tier 5 Actor Substrate post-FAC_001; per-(actor, faction) bounded standing)

> Foundation-level catalog. Owns `REP-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `REP-A*` | Axioms (locked invariants) |
> | `REP-D*` | Per-feature deferrals (V1+ / V2 phases) |
> | `REP-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**REP-A1 (Bounded score):** Score is i16 clamped to [-1000, +1000] at write boundary; engine clamps silently on Forge admin overflow attempts (preserves narrative flow per Q3 LOCKED). i16 storage minimal; sparse storage trivial cost.

**REP-A2 (Sparse storage):** Missing row = implicit Neutral (0). Engine reads `unwrap_or(0)` per Q2 + Q4 LOCKED. V1+ lazy-create row on first delta touch (Q2-(C) deferred enrichment). Wuxia V1 ~3 declared rep rows; AI Tier billion-NPC scaling = touched-only.

**REP-A3 (Engine-fixed tier mapping):** 8-tier `ReputationTier` thresholds engine-fixed V1 (Hated -1000..-501 / Hostile -500..-251 / Unfriendly -250..-101 / Neutral -100..+100 / Friendly +101..+250 / Honored +251..+500 / Revered +501..+900 / Exalted +901..+1000); FactionDecl.rep_tier_overrides V1+ enrichment (REP-D4) provides per-faction display label customization, NOT threshold customization.

**REP-A4 (3-layer separation discipline):** REP_001 actor_faction_reputation (per-(actor, faction) bounded standing) ≠ RES_001 SocialCurrency::Reputation (per-actor unbounded global "danh tiếng" sum) ≠ NPC_001 npc_pc_relationship_projection (per-(NPC, PC) personal opinion). Distinct shapes; distinct semantics; distinct queries; distinct LLM authoring prompts. NPC_002 Chorus consumes ALL THREE for priority resolution (Tier 2 + Tier 4 + Tier 5).

**REP-A5 (V1 canonical seed + Forge only):** V1 events: ReputationBorn (canonical seed) + Forge:SetReputation + Forge:ResetReputation. Runtime gameplay delta + cascade + decay V1+ per Q5+Q6+Q7 V1+ runtime reputation milestone (all 3 enrichments coupled coherently).

**REP-A6 (Synthetic actor forbidden V1):** Synthetic actors cannot have reputation rows per Q9 LOCKED (universal substrate discipline; matches IDF + FF + FAC + RES + PROG). V1+ may relax IF admin/system-faction reputation needed (defer to real use case).

**REP-A7 (Cross-reality strict V1):** Reputation rows valid only within their reality_id; V2+ Heresy migration per Q8 LOCKED. Reject `reputation.cross_reality_mismatch` V2+ reservation slot.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| REP-1 | `actor_faction_reputation` aggregate (T2/Reality, sparse — per-(actor, faction) bounded standing) | ✅ | V1 | EF-1, FAC-1, DP-A14 | [REP_001 §3.1](../features/00_reputation/REP_001_reputation_foundation.md#31-actor_faction_reputation-t2--reality-scope--primary) |
| REP-2 | `ReputationTier` enum (8-variant Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted; display layer; not stored) | ✅ | V1 | REP-1 | [REP_001 §2](../features/00_reputation/REP_001_reputation_foundation.md#2-domain-concepts) |
| REP-3 | Asymmetric tier thresholds (engine-fixed) | ✅ | V1 | REP-2 | [REP_001 §2](../features/00_reputation/REP_001_reputation_foundation.md#2-domain-concepts) |
| REP-4 | Wuxia I18n display labels (Đại nghịch / Nghịch tặc / Kẻ thù / Người lạ / Đệ tử / Trưởng lão / Tôn sư / Đại Thánh nhân) | ✅ | V1 | REP-2, RES-23 (i18n contract) | [REP_001 §2](../features/00_reputation/REP_001_reputation_foundation.md#2-domain-concepts) |
| REP-5 | Sparse storage discipline + V1+ lazy-create | ✅ | V1 | REP-1 | [REP_001 §3.1](../features/00_reputation/REP_001_reputation_foundation.md#31-actor_faction_reputation-t2--reality-scope--primary) |
| REP-6 | Score clamping at write boundary (silent) | ✅ | V1 | REP-1 | [REP_001 §3.1](../features/00_reputation/REP_001_reputation_foundation.md#31-actor_faction_reputation-t2--reality-scope--primary) |
| REP-7 | Always Neutral (0) default V1; V1+ hybrid alongside Q6 cascade (REP-D16) | ✅ | V1 | REP-1, REP-D16 | [REP_001 §8.4](../features/00_reputation/REP_001_reputation_foundation.md#84-always-neutral-0-v1-v1-hybrid-alongside-q6-cascade-q4-revision-locked) |
| REP-8 | EVT-T4 System sub-type — `ReputationBorn { actor_id, faction_id, initial_score }` (canonical seed only) | ✅ | V1 | EVT-A11, REP-1 | [REP_001 §2.5](../features/00_reputation/REP_001_reputation_foundation.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| REP-9 | EVT-T8 AdminAction sub-shapes — `Forge:SetReputation` + `Forge:ResetReputation` | ✅ | V1 | REP-1, WA-3 (forge_audit_log) | [REP_001 §13-14](../features/00_reputation/REP_001_reputation_foundation.md#13-sequence-forge-admin-setreputation-v1-active) |
| REP-10 | EVT-T3 Derived sub-types reserved V1+ — Delta + CascadeDelta + DecayTick (3 delta_kinds for `aggregate_type=actor_faction_reputation`) | ⚠ V1+ | V1+ | EVT-A11, REP-1 | [REP_001 §2.5](../features/00_reputation/REP_001_reputation_foundation.md#25-event-model-mapping-per-07_event_model-evt-t1t11) |
| REP-11 | RealityManifest extension `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` (OPTIONAL V1; sparse opt-in) | ✅ | V1 | REP-1 | [REP_001 §11](../features/00_reputation/REP_001_reputation_foundation.md#11-sequence-canonical-seed-wuxia-3-declared-rep) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| REP-12 | RejectReason `reputation.*` namespace (6 V1 + 4 V1+ reservations) | ✅ | V1 | RES-* (i18n contract) | [REP_001 §9](../features/00_reputation/REP_001_reputation_foundation.md#9-failure-mode-ux) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| REP-13 | 3-layer separation discipline (REP_001 ≠ RES_001 SocialCurrency ≠ NPC_001 NpcOpinion) | ✅ | V1 | RES-7 (SocialCurrency), CST-1 (NpcOpinion) | [REP_001 §1](../features/00_reputation/REP_001_reputation_foundation.md#1-user-story-wuxia-3-declared-rep--modern--v1-runtime) |
| REP-14 | RESOLVES FAC-D7 (per-(actor, faction) reputation projection separate aggregate) | ✅ | V1 | FAC-* | [REP_001 §18](../features/00_reputation/REP_001_reputation_foundation.md#18-cross-references) |

### Per-feature deferrals (REP-D*)

| Deferral | Description | Phase |
|---|---|---|
| REP-D1 | V1+ runtime gameplay delta events (PL_005 Strike on faction member; etc.) | V1+ runtime reputation milestone (with REP-D2 + REP-D3) |
| REP-D2 | V1+ cascade rep via FAC_001 default_relations (FactionDecl.rep_cascade_config additive) | V1+ runtime reputation milestone |
| REP-D3 | V1+ decay over fiction-time (FactionDecl.rep_decay_per_week additive + DecayTick EVT-T3) | V1+ runtime reputation milestone |
| REP-D4 | V1+ author-declared per-faction tier display labels (FactionDecl.rep_tier_overrides) | V1+ enrichment |
| REP-D5 | V2+ multi-axis reputation (CK3 Prestige + Piety) — schema migration `score: HashMap<SocialKind, i16>` | V2+ |
| REP-D6 | V2+ cross-reality migration via WA_002 Heresy | V2+ |
| REP-D7 | V1+ NPC_002 Tier 4 priority modifier integration (rival-faction NPCs read REP_001) | V1+ enrichment |
| REP-D8 | V1+ WA_001 AxiomDecl.requires_reputation hook (faction-gated abilities require min rep tier) | V1+ enrichment |
| REP-D9 ✅ V1 PARTIAL RESOLVED 2026-04-27 by TIT_001 V1 | V1+ TIT_001 title-grant requires min rep | TitleDecl.min_reputation_required: Option<MinRepGate> field schema-active V1 per Q4 C LOCKED; runtime validator V1+ alongside REP-D1 runtime delta milestone (TIT-D2). Schema-stable / activation-deferred V1+ discipline (TIT-A8). |
| REP-D10 | V1+ CULT_001 sect cultivation method requires min rep | V1+ when CULT_001 ships |
| REP-D11 | V2+ DIPL_001 inter-faction war affects member rep cascade | V2+ when DIPL_001 ships |
| REP-D12 | V2+ quest reward = REP_001 rep delta (13_quests integration) | V2+ |
| REP-D13 | V1+ rep as currency (burn rep for favor; V2+ ECON feature) | V2+ ECON |
| REP-D14 | V1+ origin-pack default rep declaration (IDF_004 origin_pack.default_reputations) | V1+ enrichment |
| REP-D15 | V1+ rep history audit trail (separate aggregate vs event log query) | V1+ analytics |
| REP-D16 | V1+ Q4 hybrid default activation (Layer 2 membership-derived) — ships alongside REP-D2 cascade | V1+ runtime reputation milestone |
| REP-D17 | V1+ RES_001 cross-cutting cleanup per Q10 LOCKED — rename SocialCurrency::Reputation → Fame; 11_cross_cutting layer documentation; RES_001 closure-pass §-cross-reference | V1+ documentation |

### Open questions (REP-Q*)

NONE V1. All Q1-Q10 LOCKED via 5-batch deep-dive 2026-04-27 (1 REVISION on Q4 — Always Neutral V1; V1+ hybrid alongside Q6 cascade enrichment).

### Cross-feature integration map

| Feature | Direction | Integration |
|---|---|---|
| EF_001 Entity Foundation | REP_001 reads | ActorId source-of-truth (sibling pattern §5.1) |
| FAC_001 Faction Foundation | REP_001 reads | FactionId source-of-truth (§3.1); rep rows REQUIRE faction declared in canonical_factions |
| FAC_001 Faction Foundation | REP_001 RESOLVES | FAC-D7 (per-(actor, faction) reputation projection separate aggregate) |
| RES_001 Resource Foundation | REP_001 distinguishes | 3-layer separation discipline (REP-A4); REP_001 ≠ RES_001 SocialCurrency::Reputation |
| RES_001 Resource Foundation | REP_001 reads | I18nBundle pattern (§2.3) for tier display labels |
| NPC_001 Cast | REP_001 distinguishes | 3-layer separation discipline; REP_001 ≠ NPC_001 NpcOpinion |
| NPC_002 Chorus | REP_001 consumed by V1+ | Tier 4 priority modifier reads REP_001 for rival-faction NPCs (REP-D7) |
| WA_001 Lex | REP_001 consumed by V1+ | AxiomDecl.requires_reputation hook (REP-D8); WA_001 closure pass V1+ adds 4-companion-fields uniformly (race + ideology + faction + reputation) |
| WA_003 Forge | REP_001 reuses | forge_audit_log pattern (3-write atomic for SetReputation + ResetReputation) |
| 07_event_model EVT-A10 | REP_001 conforms | Event log = universal SSOT; no separate reputation_event_log aggregate |
| TIT_001 Title Foundation | REP_001 consumed by V1+ | Title-grant requires min rep with faction (REP-D9) |
| CULT_001 Cultivation Foundation | REP_001 consumed by V1+ | Sect cultivation method requires min rep (REP-D10) |
| DIPL_001 Diplomacy Foundation | REP_001 consumed by V2+ | Inter-faction war affects member rep cascade (REP-D11) |
| 13_quests | REP_001 consumed by V2+ | Quest reward = rep delta (REP-D12) |
| PCS_001 PC Substrate | REP_001 consumed by | PC creation form may set initial rep (V1+ default Neutral; V1+ origin-pack-driven via REP-D14) |
