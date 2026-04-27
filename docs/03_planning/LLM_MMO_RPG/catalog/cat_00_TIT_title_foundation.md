<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_00_TIT_title_foundation.md
namespace: TIT-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## TIT — Title Foundation (foundation tier; Tier 5 Actor Substrate post-FF_001 + FAC_001 + REP_001; per-(actor, title) political/social rank holding with succession rules)

> Foundation-level catalog. Owns `TIT-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `TIT-A*` | Axioms (locked invariants) |
> | `TIT-D*` | Per-feature deferrals (V1+ / V2 / V2+ phases) |
> | `TIT-Q*` | Open questions (closure pass items) |
> | `TIT-C*` | Cross-aggregate consistency rules |

### Core architectural axioms

**TIT-A1 (Per-reality author-declared):** Engine cannot fix title schema; wuxia ≠ D&D ≠ modern ≠ sci-fi. Author declares TitleDecl per reality. Empty canonical_titles = sandbox/freeplay reality with no titles (valid V1). Mirrors PROG-A1 + REP_001 + FAC_001 author-discipline.

**TIT-A2 (Sparse storage):** actor_title_holdings is sparse per-(actor, title_id) edge aggregate. Only declared/granted holdings get rows. Wuxia V1 typical: ~5-15 rows per reality. Matches REP-A2 + FAC_001 actor_faction_membership pattern.

**TIT-A3 (Title ≠ FAC role; complementary not duplicative):** TIT_001 owns per-(actor, title) political/social rank with succession; FAC_001 owns per-(actor, faction) operational role within faction. Title-grant CAN trigger FAC role grant atomically (3-write pattern) when TitleAuthorityDecl.faction_role_grant is Some.

**TIT-A4 (3-layer separation discipline post-REP_001 alignment):** TIT_001 actor_title_holdings (per-(actor, title) political/social rank with succession) ≠ FAC_001 actor_faction_membership (per-(actor, faction) operational role) ≠ REP_001 actor_faction_reputation (per-(actor, faction) bounded standing). Distinct shapes; distinct semantics; distinct queries; distinct LLM authoring prompts. NPC_001 persona AssemblePrompt + NPC_002 Chorus consume ALL THREE for political/social context.

**TIT-A5 (Per-title author-declared policy):** Each TitleDecl carries own MultiHoldPolicy (Q5 C) + TitleAuthorityDecl (Q8 A) + VacancySemantic (Q9 D). Most flexible V1 design; covers wuxia + D&D + modern + sci-fi reality use cases.

**TIT-A6 (Synthetic actor forbidden V1):** Synthetic actors cannot hold titles per established universal substrate discipline (matches IDF + FF + FAC + REP + RES + PROG + ACT + PCS). V1+ may relax IF admin/system-faction title needed (defer to real use case).

**TIT-A7 (Cross-reality strict V1):** Title declarations valid only within their reality_id; V2+ Heresy migration per TIT-D9. Reject `title.cross_reality_mismatch` V2+ reservation.

**TIT-A8 (Schema-stable / activation-deferred V1+ discipline):** TIT_001 V1 declares cross-feature gate fields stably (REP min_reputation_required + WA_001 lex_axiom_unlock_refs); activation happens at consumer feature's milestone (REP-D1 runtime delta + WA_001 closure pass). Zero migration V1 → V1+. Pattern matches PROG_001 deferred-validator approach.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| TIT-1 | `actor_title_holdings` aggregate (T2/Reality, sparse — per-(actor, title_id) edge) | ✅ | V1 | EF-1, FAC-1, FF-1, DP-A14 | [TIT_001 §3.1](../features/00_titles/TIT_001_title_foundation.md#31-actor_title_holdings-t2--reality-scope--primary) |
| TIT-2 | `TitleDecl` shape (RealityManifest declaration) | ✅ | V1 | TIT-1, RES-23 (i18n) | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-3 | `TitleBinding` enum (3-variant Faction/Dynasty/Standalone) | ✅ | V1 | TIT-2, FAC-1, FF-1 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-4 | `SuccessionRule` enum (3 V1: Eldest/Designated/Vacate; V1+ FactionElect) | ✅ | V1 | TIT-2, FF-1 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-5 | `MultiHoldPolicy` enum (3 V1: Exclusive/StackableUnlimited/StackableMax(N); per-title author-declared) | ✅ | V1 | TIT-2 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-6 | `VacancySemantic` enum (3 V1: PersistsNone/Disabled/Destroyed; per-title author-declared) | ✅ | V1 | TIT-2 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-7 | `TitleAuthorityDecl` (faction_role_grant V1 + narrative_hint I18nBundle V1 + lex_axiom_unlock_refs V1 schema-reserved) | ✅ | V1 | TIT-2, FAC-1 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-8 | `MinRepGate` (V1 schema-reserved; runtime validator V1+ alongside REP-D1) | ✅ schema | V1 | TIT-2, REP-1 | [TIT_001 §2.1](../features/00_titles/TIT_001_title_foundation.md#21-titledecl-realitymanifest-declaration-shape) |
| TIT-9 | `TitleHoldingDecl` shape (canonical seed; designated_heir Option<ActorId>) | ✅ | V1 | TIT-2, EF-1 | [TIT_001 §2.2](../features/00_titles/TIT_001_title_foundation.md#22-titleholdingdecl-realitymanifest-canonical-seed) |
| TIT-10 | `GrantSource` enum (CanonicalSeed / ForgeAdmin / SuccessionCascade V1; V1+ QuestReward / FactionElectVote) | ✅ | V1 | TIT-1 | [TIT_001 §2.3](../features/00_titles/TIT_001_title_foundation.md#23-actor_title_holdings-aggregate-t2--reality-scope-sparse) |
| TIT-11 | EVT-T4 System sub-type — `TitleGranted { actor_id, title_id, granted_at_fiction_ts, granted_via }` | ✅ | V1 | EVT-A11, TIT-1 | [TIT_001 §5.1](../features/00_titles/TIT_001_title_foundation.md#51-evt-t4-system-sub-type--titlegranted) |
| TIT-12 | EVT-T8 AdminAction sub-shapes — `Forge:GrantTitle` + `Forge:RevokeTitle` + `Forge:DesignateHeir` | ✅ | V1 | TIT-1, WA-3 (forge_audit_log) | [TIT_001 §6](../features/00_titles/TIT_001_title_foundation.md#6--forge-admin-sub-shapes-q6-c--q8-a-locked) |
| TIT-13 | EVT-T3 Derived sub-type — `TitleSuccessionTriggered { from_actor_id, to_actor_id, title_id, trigger_reason, fiction_ts }` | ✅ | V1 | EVT-A11, TIT-1 | [TIT_001 §5.2](../features/00_titles/TIT_001_title_foundation.md#52-evt-t3-derived-sub-type--titlesuccessiontriggered) |
| TIT-14 | EVT-T1 Narrative sub-type — `TitleSuccessionCompleted { actor_id, title_id, fiction_ts }` (LLM milestone) | ✅ | V1 | EVT-A11, TIT-1 | [TIT_001 §5.3](../features/00_titles/TIT_001_title_foundation.md#53-evt-t1-narrative-sub-type--titlesuccessioncompleted) |
| TIT-15 | RealityManifest 2 OPTIONAL V1 extensions (canonical_titles + canonical_title_holdings) | ✅ | V1 | TIT-2, TIT-9 | [TIT_001 §4](../features/00_titles/TIT_001_title_foundation.md#4--realitymanifest-extensions) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| TIT-16 | Cross-aggregate validator C-rule — TIT-C1: title-holder death (WA_006 mortality EVT-T3) → synchronous succession cascade same turn | ✅ | V1 | WA_006, TIT-1, TIT-4 | [TIT_001 §7](../features/00_titles/TIT_001_title_foundation.md#7--cross-aggregate-validator-q7-a-locked--immediate-cascade-on-wa_006-mortality-evt-t3) |
| TIT-17 | Atomic 3-write pattern for Forge admin (actor_title_holdings + EVT emit + forge_audit_log + optional FAC role update) | ✅ | V1 | WA-3, FAC-1 | [TIT_001 §6.2](../features/00_titles/TIT_001_title_foundation.md#62-3-write-atomic-pattern) |
| TIT-18 | RejectReason `title.*` namespace (9 V1 rule_ids + 5 V1+ reservations; Phase 3 cleanup 2026-04-27 added `title.binding.faction_membership_required` + `title.binding.dynasty_membership_required`) | ✅ | V1 | RES-* (i18n contract) | [TIT_001 §8](../features/00_titles/TIT_001_title_foundation.md#8--v1-reject-rules-title-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| TIT-19 | RESOLVES FF-D8 (title inheritance + heir succession via dynasty.current_head_actor_id traversal) | ✅ | V1 | FF-* | [TIT_001 §13.1](../features/00_titles/TIT_001_title_foundation.md#131-resolves-cross-feature-deferrals) |
| TIT-20 | RESOLVES FAC-D6 (sect succession rules via SuccessionRule::Designated + sect-master title binding to FactionId) | ✅ | V1 | FAC-* | [TIT_001 §13.1](../features/00_titles/TIT_001_title_foundation.md#131-resolves-cross-feature-deferrals) |
| TIT-21 | PARTIAL RESOLVES REP-D9 (TitleDecl.min_reputation_required schema-active V1; runtime gating V1+ alongside REP-D1) | ✅ schema | V1 | REP-* | [TIT_001 §13.1](../features/00_titles/TIT_001_title_foundation.md#131-resolves-cross-feature-deferrals) |
| TIT-22 | RESOLVES WA_006 sect-leader-death cascade gap via TIT-C1 cross-aggregate validator | ✅ | V1 | WA_006 | [TIT_001 §13.1](../features/00_titles/TIT_001_title_foundation.md#131-resolves-cross-feature-deferrals) |
| TIT-23 | V1+30d — Runtime min_reputation_required validator (TIT-D2; alongside REP-D1) | 📦 | V1+ | TIT-8, REP-D1 | [TIT_001 §1 V1 NOT shipping](../features/00_titles/TIT_001_title_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| TIT-24 | V1+30d — requires_title Lex axiom validator (TIT-D3; WA_001 closure pass 5-companion-fields uniform) | 📦 | V1+ | TIT-7, WA_001 closure pass | [TIT_001 §1 V1 NOT shipping](../features/00_titles/TIT_001_title_foundation.md#v1-not-shipping-deferred-per-q-decisions) |
| TIT-25 | V1+30d — 8 CK3 succession law variants (gender + partition; TIT-D5) | 📦 | V1+ | TIT-4 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-26 | V1+30d — Origin-pack default_titles declaration (TIT-D10; IDF_004 OriginPack additive) | 📦 | V1+ | IDF_004 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-27 | V1+30d — title_state per-title singleton projection (TIT-D12; if filter scan limiting) | 📦 | V1+ | TIT-1 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-28 | V2 — SuccessionRule::FactionElect active (TIT-D1; DIPL_001 procedural vote) | 📦 | V2 | DIPL_001 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-29 | V2 — Quest reward = title grant (TIT-D8; 13_quests integration) | 📦 | V2 | QST_001 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-30 | V2 — Multi-axis title taxonomy (TIT-D11; CK3 Prestige + Piety + Renown alongside REP-D5) | 📦 | V2 | REP-D5 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-31 | V2+ — Vassalage hierarchy TIT_002 (TIT-D4; CK3 baron→count→duke→king→emperor) | 📦 | V2+ | TIT_002 separate feature | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-32 | V2+ — Term-limited titles (TIT-D6; Imperator consul fiction-time bound) | 📦 | V2+ | TDIL_001 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-33 | V2+ — Title decay over fiction-time (TIT-D7; CK3 prestige decay) | 📦 | V2+ | TDIL_001 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |
| TIT-34 | V2+ — Cross-reality title migration via WA_002 Heresy (TIT-D9) | 📦 | V2+ | WA_002 | [TIT_001 §12](../features/00_titles/TIT_001_title_foundation.md#12--deferrals-catalog-tit-d1tit-d12) |

### Per-feature deferrals (TIT-D*)

| Deferral | Description | Phase |
|---|---|---|
| TIT-D1 | V2 — SuccessionRule::FactionElect active (DIPL_001 procedural vote dependency) | V2 |
| TIT-D2 | V1+30d — Runtime min_reputation_required validator (alongside REP-D1 runtime delta milestone) | V1+ |
| TIT-D3 | V1+30d — requires_title Lex axiom validator (WA_001 closure pass adding 5-companion-fields uniformly: race + ideology + faction + reputation + title) | V1+ |
| TIT-D4 | V2+ — Vassalage hierarchy (CK3 baron→count→duke→king→emperor 5-level tree); TIT_002 separate feature | V2+ |
| TIT-D5 | V1+30d — 8 CK3 succession law variants (gender variants agnatic/cognatic/enatic; partition Confederate/High Partition; Open Succession) | V1+ |
| TIT-D6 | V2+ — Term-limited titles (Imperator consul 1-year fiction-time bound; requires TDIL_001 fiction-time API) | V2+ |
| TIT-D7 | V2+ — Title decay over fiction-time (CK3 prestige decay; requires TDIL_001) | V2+ |
| TIT-D8 | V2 — Quest reward = title grant (13_quests integration; QST_001 dependency) | V2 |
| TIT-D9 | V2+ — Cross-reality title migration via WA_002 Heresy | V2+ |
| TIT-D10 | V1+30d — Origin-pack default_titles declaration (IDF_004 OriginPack additive field) | V1+ |
| TIT-D11 | V2 — Multi-axis title taxonomy (CK3 Prestige + Piety + Renown alongside REP-D5 multi-axis reputation schema migration) | V2 |
| TIT-D12 | V1+30d — title_state per-title singleton projection (if actor_title_holdings filter scan proves limiting at scale; AI Tier billion-NPC scenario) | V1+ |

### Cross-aggregate consistency rules (TIT-C*)

| Rule | Description | Owner-feature | Trigger | Reject rule |
|---|---|---|---|---|
| TIT-C1 | Title-holder death triggers synchronous succession cascade same turn | TIT_001 (consumer of WA_006 mortality EVT-T3) | WA_006 mortality_state transition Alive → Dying / Dead | (no reject; cascade applies VacancySemantic when ineligible) |
| TIT-C2 | Stage 0 schema validator: title_id ∈ canonical_titles | TIT_001 | RealityManifest bootstrap + Forge:GrantTitle | `title.declared.unknown` |
| TIT-C3 | Stage 0 schema validator: actor_id ∈ canonical_actors | TIT_001 | RealityManifest bootstrap + Forge:GrantTitle | `title.holding.actor_unknown` |
| TIT-C4 | Stage 0 schema validator: TitleBinding::Faction(fid) → fid ∈ canonical_factions | TIT_001 | RealityManifest bootstrap | `title.binding.faction_unknown` |
| TIT-C5 | Stage 0 schema validator: TitleBinding::Dynasty(did) → did ∈ canonical_dynasties (FF_001) | TIT_001 | RealityManifest bootstrap | `title.binding.dynasty_unknown` |
| TIT-C6 | Stage 0 schema validator: actor count per (actor_ref) respects MultiHoldPolicy | TIT_001 | RealityManifest bootstrap + Forge:GrantTitle + SuccessionCascade | `title.holding.multi_hold_violation` |
| TIT-C7 | Stage 0 schema validator: actor count per (title_id) respects Exclusive policy | TIT_001 | RealityManifest bootstrap + Forge:GrantTitle + SuccessionCascade | `title.holding.exclusive_violation` |
| TIT-C8 | Stage 0 schema validator: designated_heir alive at succession time | TIT_001 | SuccessionCascade fires | `title.succession.heir_invalid` (or sets new_holder=None + trigger_reason=HeirIneligible) |

### Open questions (TIT-Q*)

NONE V1. All Q1-Q10 LOCKED via 4-batch deep-dive 2026-04-27 zero revisions:
- Q1 A LOCKED (actor_title_holdings sparse)
- Q2 B LOCKED (Discriminated TitleBinding)
- Q3 A LOCKED (3 V1 + 1 V1+ SuccessionRule)
- Q4 C LOCKED (V1 schema-reserved min_reputation_required)
- Q5 C LOCKED (Per-title MultiHoldPolicy)
- Q6 C LOCKED (Both author canonical + Forge runtime DesignateHeir)
- Q7 A LOCKED (Immediate cascade on WA_006 mortality EVT-T3)
- Q8 A + narrative_hint LOCKED (FAC role grant + LLM narrative_hint + V1 schema-reserved Lex axiom)
- Q9 D LOCKED (Per-title VacancySemantic)
- Q10 B LOCKED (V1 schema-reserved lex_axiom_unlock_refs)

### Cross-feature integration map

| Feature | Direction | Integration |
|---|---|---|
| EF_001 Entity Foundation | TIT_001 reads | ActorId source-of-truth for actor_title_holdings.actor_ref |
| FF_001 Family Foundation | TIT_001 reads | dynasty.current_head_actor_id for Eldest succession; family_node.parent_actor_ids fallback |
| FF_001 Family Foundation | TIT_001 RESOLVES | FF-D8 (title inheritance rules + heir succession; full V1) |
| FAC_001 Faction Foundation | TIT_001 reads | canonical_factions for TitleBinding::Faction validation |
| FAC_001 Faction Foundation | TIT_001 writes | actor_faction_membership.role_id atomically on title-grant via TitleAuthorityDecl.faction_role_grant (3-write atomic per WA_003) |
| FAC_001 Faction Foundation | TIT_001 RESOLVES | FAC-D6 (sect succession rules; full V1) |
| REP_001 Reputation Foundation | TIT_001 references schema | TitleDecl.min_reputation_required: Option<MinRepGate> active V1 |
| REP_001 Reputation Foundation | TIT_001 PARTIAL RESOLVES | REP-D9 (V1 schema-active; runtime gating V1+ alongside REP-D1) |
| RES_001 Resource Foundation | TIT_001 conforms | I18nBundle pattern (display_name + description + narrative_hint multi-language) |
| PROG_001 Progression Foundation | TIT_001 distinguishes | Title NOT a progression (PROG-A1 author-discipline preserved); no min_progression_tier gating V1 (reality author handles via Forge admin) |
| ACT_001 Actor Foundation | TIT_001 reads | actor_core ActorRef source; titles appear in NPC_001 persona via TitleAuthorityDecl.narrative_hint |
| PCS_001 PC Substrate | TIT_001 consumes V1+ | Origin-pack-driven canonical_title_holdings for PC creation (V1+ via PO_001) |
| WA_001 Lex | TIT_001 V1 schema-reserves | TitleAuthorityDecl.lex_axiom_unlock_refs field; validator V1+ via WA_001 closure pass adding 5-companion-fields uniformly (race + ideology + faction + reputation + title) |
| WA_003 Forge | TIT_001 reuses | 3-write atomic Forge admin pattern + forge_audit_log; closure folds 3 sub-shapes into ForgeEditAction enum |
| WA_006 Mortality | TIT_001 RESOLVES | Sect-leader-death cascade gap (TIT-C1 cross-aggregate validator; full V1) |
| NPC_001 Cast | TIT_001 consumed by | persona AssemblePrompt reads actor_title_holdings; LLM persona briefing includes titles via narrative_hint I18nBundle |
| NPC_002 Chorus | TIT_001 consumed by V1+ | Tier 4 priority modifier reads actor_title_holdings (titled NPCs prioritized; rare) |
| PL_005 Interaction | TIT_001 consumed by V1+ | titled-actor narrative carries title context (Speak/Strike actions) |
| AIT_001 AI Tier | TIT_001 coordinates | title-holders typically NpcTrackingTier::Major or ::Minor (rare for Untracked) |
| TDIL_001 Time Dilation | TIT_001 not affected V1 | Titles unaffected by time dilation V1; V2+ term-limited titles use fiction-time bounds (TIT-D6) |
| 07_event_model EVT-A11 | TIT_001 conforms | Aggregate-Owner discipline; only TIT_001 emits actor_title_holdings EVT-T3/T4/T8/T1 sub-shapes |
| Future PO_001 Player Onboarding | TIT_001 consumed by V1+ | UI flow uses TIT_001 origin-pack default_titles for initial PC title (TIT-D10) |
| Future DIPL_001 Diplomacy V2+ | TIT_001 consumed by V2+ | title-holder identity for treaty-signing authority; FactionElect SuccessionRule (TIT-D1) |
| Future CULT_001 V2+ template library | TIT_001 referenced | CultivationRealmDecl templates may declare title-grant per realm tier (V2+) |
| Future 13_quests V2+ | TIT_001 consumed by V2+ | Quest reward = title grant (TIT-D8) |

### V1 minimum delivery

22 V1 catalog entries (TIT-1..22 all ✅ V1; TIT-8 + TIT-21 schema-active V1 + runtime V1+). Foundation tier — Tier 5 Actor Substrate post-FF_001 + FAC_001 + REP_001; closes the political-rank triangle.

### V1+30d deferrals (TIT-23..27)

5 V1+30d items planned for the 30-day fast-follow window after V1 ship. Most schema reservations already in place — zero schema migration cost (per TIT-A8 schema-stable / activation-deferred discipline).

### V2 deferrals (TIT-28..30)

3 V2 deferrals tied to feature dependencies (DIPL_001 / QST_001 / multi-axis reputation REP-D5).

### V2+ deferrals (TIT-31..34)

4 V2+ deferrals tied to vassalage hierarchy (TIT_002 separate feature) + time-bound titles (TDIL_001 V2+ scope) + Heresy migration (WA_002).

### Coordination / discipline notes

- **Foundation tier extension (2026-04-27):** TIT_001 closes the political-rank triangle with FF_001 + FAC_001 + REP_001; not part of original 6/6 foundation tier (PROG_001 closed that 2026-04-26). TIT_001 is post-foundation Tier 5 Actor Substrate.
- **3-layer separation discipline (TIT-A4):** TIT_001 ≠ FAC_001 actor_faction_membership ≠ REP_001 actor_faction_reputation. NPC_002 Chorus + NPC_001 persona AssemblePrompt + LLM consume all three for political/social context.
- **Per-title author-declared policy (TIT-A5):** Each TitleDecl carries own MultiHoldPolicy + TitleAuthorityDecl + VacancySemantic. Most flexible V1 design.
- **Schema-stable / activation-deferred (TIT-A8):** TIT_001 V1 declares cross-feature gate fields stably (REP min_rep + WA_001 axiom unlock); activation V1+ via consumer feature milestone (REP-D1 runtime delta + WA_001 closure pass). Zero migration.
- **Cross-aggregate cascade (TIT-C1):** Title-holder death triggers synchronous succession cascade same turn via WA_006 mortality EVT-T3. Joins existing C1-C17 cross-aggregate consistency rules from P4 commit.
- **Resolves 4 V1+ deferrals (TIT-19..22):** FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial; runtime V1+) + WA_006 sect-leader-death cascade gap (full V1). Substantial cross-feature seam consolidation in single feature.
- **3 cross-feature deferrals downstream (V1+30d):** WA_001 closure pass adds 5-companion-fields uniformly (race + ideology + faction + reputation + title); REP-D1 runtime delta milestone activates TIT-D2 runtime min_rep validator; IDF_004 OriginPack additive default_titles field for PO_001 V1+ consumption.
