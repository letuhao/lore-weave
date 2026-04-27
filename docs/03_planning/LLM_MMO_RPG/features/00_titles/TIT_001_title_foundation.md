# TIT_001 — Title Foundation

> **Category:** TIT — Title Foundation (foundation tier; Tier 5 Actor Substrate post-FF_001 + FAC_001 + REP_001; closes the political-rank triangle)
> **Catalog reference:** [`catalog/cat_00_TIT_title_foundation.md`](../../catalog/cat_00_TIT_title_foundation.md) (owns `TIT-*` stable-ID namespace)
> **Status:** DRAFT 2026-04-27 — All 10 critical scope questions LOCKED via 4-batch deep-dive 2026-04-27 zero revisions. Companion documents: [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q10 LOCKED matrix §10) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (CK3 + Wuxia hybrid V1 anchor reference materials).
>
> **i18n compliance:** Conforms to RES_001 §2 cross-cutting i18n contract — all stable IDs English `snake_case` / `PascalCase`; all user-facing strings `I18nBundle`.
> **V1 testable acceptance:** 10 scenarios AC-TIT-1..10 (§10).
> **Resolves:** FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial; runtime gating V1+ alongside REP-D1) + WA_006 sect-leader-death cascade gap (V1 full).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

Per user direction 2026-04-27 post CULT_001 V2+ defer (commit d57fb7fc): TIT_001 picked as next-priority because "small foundation feature; closes REP/FAC/FF triangle with title inheritance".

Without TIT_001, V1 cannot ship:
- Wuxia sect-master succession (FAC-D6 unresolved)
- Imperial dynasty heir succession (FF-D8 unresolved)
- Sect/cartel/imperial-court political role tracking distinct from FAC_001 generic role grants
- Cross-aggregate cascade on title-holder death (WA_006 sect-leader-death gap unresolved)
- Min-rep-gated political appointments (REP-D9 schema unsupported)

TIT_001 establishes the per-(actor, title) holding substrate for political/social rank with succession rules.

### V1 minimum scope (per Q1-Q10 LOCKED in CONCEPT_NOTES §10)

- **1 NEW sparse aggregate** (Q1 A LOCKED): `actor_title_holdings` (T2/Reality, sparse per-(actor, title_id) edge)
- **2 RealityManifest extensions** (both OPTIONAL V1 per composability discipline): `canonical_titles: Vec<TitleDecl>` + `canonical_title_holdings: Vec<TitleHoldingDecl>`
- **Discriminated `TitleBinding` enum** (Q2 B LOCKED): `Faction(FactionId)` / `Dynasty(DynastyId)` / `Standalone` (3 V1 variants)
- **`SuccessionRule` enum** (Q3 A LOCKED): `Eldest` (FF_001 dynasty traversal) / `Designated` (canonical declaration + Forge:DesignateHeir) / `Vacate` V1 + `FactionElect` V1+ (DIPL_001 V2+ dependency)
- **V1 schema-reserved `min_reputation_required`** (Q4 C LOCKED): TitleDecl.min_reputation_required: Option<MinRepGate> field active; runtime validator V1+ alongside REP-D1 runtime delta milestone
- **Per-title `MultiHoldPolicy`** (Q5 C LOCKED): `Exclusive` / `StackableUnlimited` / `StackableMax(N)` (default StackableUnlimited if omitted)
- **Heir designation V1** (Q6 C LOCKED): canonical seed declaration via TitleHoldingDecl.designated_heir + runtime override via Forge:DesignateHeir admin sub-shape
- **Immediate cross-aggregate cascade on title-holder death** (Q7 A LOCKED): synchronous validator C-rule fires on WA_006 mortality EVT-T3
- **TitleAuthorityDecl** (Q8 A + narrative_hint LOCKED): `faction_role_grant: Option<FactionRoleGrant>` (V1 active) + `narrative_hint: I18nBundle` (V1 active LLM persona briefing) + `lex_axiom_unlock_refs: Vec<AxiomDeclRef>` (V1 schema-reserved per Q10)
- **Per-title `VacancySemantic`** (Q9 D LOCKED): `PersistsNone` (default) / `Disabled` / `Destroyed`
- **V1 schema-reserved `lex_axiom_unlock_refs`** (Q10 B LOCKED): TitleAuthorityDecl.lex_axiom_unlock_refs: Vec<AxiomDeclRef> field active V1; validator activates V1+ via WA_001 closure pass adding 5-companion-fields uniformly (race + ideology + faction + reputation + title)
- **1 EVT-T4 System sub-type** `TitleGranted { actor_id, title_id, granted_at_fiction_ts, granted_via }` (canonical seed + runtime active V1)
- **3 EVT-T8 Administrative sub-shapes** `Forge:GrantTitle` + `Forge:RevokeTitle` + `Forge:DesignateHeir` (V1 active)
- **1 EVT-T3 Derived sub-type** `TitleSuccessionTriggered { from_actor_id, to_actor_id: Option<ActorId>, title_id, trigger_reason, fiction_ts }` (sparse; V1 active on cascade)
- **1 EVT-T1 Narrative sub-type** `TitleSuccessionCompleted { actor_id, title_id, fiction_ts }` (narrative milestone for LLM)
- **7 V1 reject rules** in `title.*` namespace + 5 V1+ reservations
- **TIT-* stable-ID prefix**

### V1 NOT shipping (deferred per Q-decisions)

| Feature | Defer to | Why |
|---|---|---|
| `SuccessionRule::FactionElect` active | V2+ DIPL_001 (TIT-D1) | Q3 — depends procedural voting feature |
| Runtime min_reputation_required validator | V1+ alongside REP-D1 (TIT-D2) | Q4 — schema active V1; runtime V1+ |
| `requires_title` Lex axiom validator | V1+ via WA_001 closure pass (TIT-D3) | Q10 — 5-companion-fields uniform addition with WA_001 closure |
| Vassalage hierarchy (CK3 baron→count→duke→king→emperor) | V2+ TIT_002 (TIT-D4) | Large schema; V1 keeps flat per-title list |
| 8 CK3 succession law variants (gender + partition variants) | V1+ enrichment (TIT-D5) | V1 ships 3 variants; CK3-equivalent variants V1+ if needed |
| Term-limited titles (Imperator consul 1-year) | V2+ (TIT-D6) | Requires fiction-time bound; V1 titles "until death/revoke" |
| Title decay over fiction-time (CK3 prestige decay) | V2+ (TIT-D7) | Most LoreWeave titles static-until-death |
| Quest reward = title grant | V2+ 13_quests (TIT-D8) | QST_001 dependency |
| Cross-reality title migration via WA_002 Heresy | V2+ (TIT-D9) | Heresy V2+ priority |
| Origin-pack default_titles declaration | V1+ enrichment (TIT-D10) | IDF_004 OriginPack additive field |
| Multi-axis title taxonomy (CK3 Prestige + Piety + Renown) | V2+ alongside REP-D5 (TIT-D11) | Multi-axis V2+ scope |
| `title_state` per-title singleton projection | V1+ if author requests (TIT-D12) | Q1 (C) — projection-on-demand from actor_title_holdings |

---

## §2 — Domain concepts

### §2.1 TitleDecl (RealityManifest declaration shape)

Each reality declares own title list per PROG-A1 author-discipline. No engine-fixed titles.

```rust
pub struct TitleDecl {
    pub title_id: TitleId,                                // author-declared stable ID (e.g., "donghai_sect_master")
    pub display_name: I18nBundle,                         // i18n per RES_001 §2
    pub description: I18nBundle,
    pub binding: TitleBinding,                            // Q2 B LOCKED — Faction / Dynasty / Standalone
    pub succession_rule: SuccessionRule,                  // Q3 A LOCKED — Eldest / Designated / Vacate; FactionElect V1+
    pub min_reputation_required: Option<MinRepGate>,      // Q4 C LOCKED — schema active V1; runtime validator V1+
    pub authority_decl: TitleAuthorityDecl,               // Q8 A + narrative_hint LOCKED
    pub multi_hold_policy: MultiHoldPolicy,               // Q5 C LOCKED — Exclusive / StackableUnlimited / StackableMax(N)
    pub vacancy_semantic: VacancySemantic,                // Q9 D LOCKED — PersistsNone / Disabled / Destroyed
}

pub enum TitleBinding {                                   // Q2 B LOCKED
    Faction(FactionId),                                   // sect-master / cartel-boss / guild-leader
    Dynasty(DynastyId),                                   // emperor / family-patriarch
    Standalone,                                           // wandering hero / honor title / unaffiliated
}

pub enum SuccessionRule {                                 // Q3 A LOCKED — 3 V1 + 1 V1+
    Eldest,                                               // FF_001 dynasty traversal eldest living member
    Designated,                                           // canonical TitleHoldingDecl.designated_heir + Forge:DesignateHeir runtime
    Vacate,                                               // no auto-succession; manual re-grant required
    // V1+ FactionElect (procedural vote; depends on DIPL_001 V2+) — TIT-D1
}

pub struct MinRepGate {                                   // Q4 C LOCKED schema-active V1
    pub faction_id: FactionId,
    pub min_tier: ReputationTier,                         // e.g., Honored+
    // Validator activates V1+ alongside REP-D1 runtime delta milestone (TIT-D2)
    // V1: declarations stored; runtime grant/hold skips check
}

pub struct TitleAuthorityDecl {                           // Q8 A + narrative_hint LOCKED
    pub faction_role_grant: Option<FactionRoleGrant>,     // V1 active — atomic FAC_001 role grant on title-grant
    pub narrative_hint: I18nBundle,                       // V1 active — LLM persona briefing + dialogue context
    pub lex_axiom_unlock_refs: Vec<AxiomDeclRef>,         // V1 schema-reserved (Q10 B LOCKED); validator V1+ via WA_001 closure pass — TIT-D3
}

pub struct FactionRoleGrant {                             // Q8 A LOCKED — couples to FAC_001 role
    pub faction_id: FactionId,                            // MUST equal TitleBinding::Faction(this) when binding is Faction
    pub role_id: FactionRoleId,                           // FAC_001 actor_faction_membership.role_id
}

pub enum MultiHoldPolicy {                                // Q5 C LOCKED — per-title author-declared
    Exclusive,                                            // only 1 holder per reality (emperor / king / sect-master typical)
    StackableUnlimited,                                   // default; generic noble titles; no cap
    StackableMax(u8),                                     // CK3-style cap (e.g., max 3 noble titles per actor)
}

pub enum VacancySemantic {                                // Q9 D LOCKED — per-title author-declared
    PersistsNone,                                         // title persists with no holder; revivable on next eligible heir or Forge re-grant (DEFAULT)
    Disabled,                                             // title persists with disabled flag; Forge re-grant required to revive (election offices)
    Destroyed,                                            // RealityManifest entry removed (fallen empire / dynasty extinction)
}

pub struct TitleId(pub String);                           // namespaced stable ID
pub struct AxiomDeclRef(pub String);                      // V1 schema-reserved; references WA_001 AxiomDecl (V1+ resolves)
```

### §2.2 TitleHoldingDecl (RealityManifest canonical seed)

```rust
pub struct TitleHoldingDecl {
    pub actor_id: ActorId,                                // EF_001 source-of-truth
    pub title_id: TitleId,                                // MUST be in canonical_titles
    pub designated_heir: Option<ActorId>,                 // Q6 C LOCKED — canonical declaration
                                                          // Some only when title_decl.succession_rule == Designated
                                                          // None for Eldest (FF_001 traversal) / Vacate
    pub initial_grant_reason: I18nBundle,                 // narrative reason for initial holding
}
```

### §2.3 actor_title_holdings aggregate (T2 / Reality scope; sparse)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_title_holdings", tier = "T2", scope = "reality")]
pub struct ActorTitleHolding {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,                              // PC + NPC; Synthetic forbidden V1 per TIT-A6
    pub title_id: TitleId,                                // MUST be in canonical_titles
    pub granted_at_fiction_ts: i64,
    pub granted_via: GrantSource,
    pub designated_heir: Option<ActorRef>,                // sparse Some; None for Eldest/Vacate
    pub schema_version: u32,                              // V1 = 1
}

pub enum GrantSource {
    CanonicalSeed,                                        // declared in RealityManifest at bootstrap
    ForgeAdmin,                                           // Forge:GrantTitle V1
    SuccessionCascade,                                    // auto-grant on previous holder death V1
    // V1+ QuestReward { quest_id }                       // TIT-D8
    // V1+ FactionElectVote { vote_event_id }             // TIT-D1
}
```

**Sparse storage:** only actors holding titles get rows. Wuxia preset typical V1: ~5-12 holding rows (1 emperor + 1 crown prince + 5 sect-masters + 5 elders + 2 family patriarchs = 14 rows).

---

## §3 — Aggregates (Q1 A LOCKED)

### §3.1 `actor_title_holdings` (T2 / Reality scope) — PRIMARY

**Scope:** T2/Reality (per DP-A14). Sparse per-(actor, title_id) edge — only declared holdings get rows.
**Owner:** TIT_001 Title Foundation.
**Tracking model:** Eager — all holdings always materialized; sparse storage discipline keeps row count low (~5-15 V1 wuxia preset).

### §3.2 Why split into separate aggregate vs extending FAC_001 actor_faction_membership

Per Q1 A LOCKED — actor_title_holdings sparse won over (B) per-title singleton + (C) both:

- **(B) per-title singleton REJECTED**: Multi-hold case (Lý Minh holds 2+ titles) requires Vec<actor_ref> field, breaking singleton semantic. Doesn't match established sparse-edge pattern (REP_001 / FAC_001 / IDF actor_*_assignment).
- **(C) both REJECTED V1**: Projection adds V1 complexity without clear benefit V1 (~5-15 holdings V1; filter scan acceptable). V1+ reservation TIT-D12 if needed.
- **(A) actor_title_holdings sparse WINS**: matches REP_001 actor_faction_reputation + FAC_001 actor_faction_membership + IDF actor_*_assignment pattern. Multi-hold trivial. Sparse storage cheap.

### §3.3 Why split from FAC_001 actor_faction_membership

Title ≠ membership role:
- **FAC_001 role** = operational position within faction (disciple / elder / master); many actors share role; faction internal
- **TIT_001 title** = political/social rank (sect-master / emperor / family-patriarch); often singleton; reality-wide; succession rules apply

Title-grant CAN trigger FAC_001 role grant via `TitleAuthorityDecl.faction_role_grant` (Q8 A LOCKED) — atomic 3-write pattern (actor_title_holdings + actor_faction_membership.role_id + forge_audit_log).

### §3.4 Storage scope discipline

Reality-scoped index by `(actor_ref, title_id) → ActorTitleHolding`. Read-side projections V1+:
- `holdings_by_title` for "who holds title X?" queries (V1+ TIT-D12 if filter scan proves limiting)
- `holdings_by_actor` for "what titles does actor X hold?" — V1 indexed by actor_ref

**Multi-hold validation:** Stage 0 schema validator counts rows per actor_ref; rejects `title.holding.multi_hold_violation` if violates declared MultiHoldPolicy.

**Exclusive validation:** Stage 0 schema validator counts rows per title_id; rejects `title.holding.exclusive_violation` if Exclusive title has >1 holder concurrently.

---

## §4 — RealityManifest extensions

### §4.1 Fields added by TIT_001

Registered in `_boundaries/02_extension_contracts.md` §2:

```rust
RealityManifest {
    // ... existing fields per Continuum / NPC_001 / WA_001 / WA_002 / WA_006 / PF_001 / MAP_001 / CSC_001 / RES_001 / NPC_003 / IDF_001..005 / FF_001 / PROG_001 / FAC_001 / REP_001 / ACT_001 / PCS_001 ...
    
    // ─── TIT_001 extensions (added 2026-04-27 DRAFT) ───
    
    /// Author-declared titles per reality.
    /// OPTIONAL V1 — empty Vec valid for sandbox/freeplay realities (no titles).
    /// Wuxia preset typical: ~12 titles (5 sect-masters + 5 elders + 1 emperor + 1 crown prince).
    /// Modern preset typical: ~8 titles (president + senators + cartel bosses + judges).
    /// D&D preset typical: ~15 titles (king + dukes + counts + lords + knights + archmage + high priest).
    pub canonical_titles: Vec<TitleDecl>,
    
    /// Initial title holdings at canonical seed.
    /// OPTIONAL V1 — empty Vec valid (titles declared but vacant initially; Forge admin grants V1).
    /// Each TitleHoldingDecl: { actor_id, title_id, designated_heir, initial_grant_reason }.
    /// Validator: Stage 0 cross-aggregate consistency rule TIT-C1 (title_id ∈ canonical_titles).
    pub canonical_title_holdings: Vec<TitleHoldingDecl>,
}
```

### §4.2 Default values (engine fallback)

If author provides empty arrays:
- `canonical_titles: []` → reality has NO titles. LLM falls back to NPC_001 flexible_state for political-rank narrative description.
- `canonical_title_holdings: []` → all declared titles vacant initially; Forge admin grants V1 active.

### §4.3 Per-reality opt-in (composability)

Authors can omit TIT fields entirely (sandbox/freeplay realities); titles are opt-in per reality. Per `_boundaries/02_extension_contracts.md` §2 rule 4 — composability.

---

## §5 — Events (per EVT-A11 sub-type ownership)

### §5.1 EVT-T4 System sub-type — `TitleGranted`

```rust
pub struct TitleGranted {
    pub actor_id: ActorId,
    pub title_id: TitleId,
    pub granted_at_fiction_ts: i64,
    pub granted_via: GrantSource,                         // CanonicalSeed / ForgeAdmin / SuccessionCascade V1
}
```

Emitted at:
- Canonical seed bootstrap (RealityBootstrapper) — one per declared TitleHoldingDecl row
- Runtime via Forge:GrantTitle admin
- Runtime via SuccessionCascade (cross-aggregate validator C-rule)

### §5.2 EVT-T3 Derived sub-type — `TitleSuccessionTriggered`

```rust
pub struct TitleSuccessionTriggered {
    pub from_actor_id: ActorId,                           // previous holder (deceased or revoked)
    pub to_actor_id: Option<ActorId>,                     // new holder; None if Vacate or no eligible heir
    pub title_id: TitleId,
    pub trigger_reason: SuccessionTriggerReason,
    pub fiction_ts: i64,
    pub source_event_id: u64,                             // causal-ref per EVT-A6 (typically WA_006 mortality EVT-T3)
}

pub enum SuccessionTriggerReason {
    HolderDeceased,                                       // V1 active — primary trigger via WA_006 cascade
    HolderRevoked,                                        // V1 active — Forge:RevokeTitle admin
    HeirIneligible,                                       // V1 active — designated heir died or doesn't meet criteria
    NoEligibleHeir,                                       // V1 active — Vacate semantic or empty dynasty
    // V1+ FactionVoteCompleted — TIT-D1
}
```

### §5.3 EVT-T1 Narrative sub-type — `TitleSuccessionCompleted`

```rust
pub struct TitleSuccessionCompleted {
    pub actor_id: ActorId,                                // new holder
    pub title_id: TitleId,
    pub fiction_ts: i64,
}
```

V1 active — narrative milestone event for LLM (similar to PcTransmigrationCompleted pattern). Emission on every successful succession (after TitleSuccessionTriggered + role grant + state update commit). LLM uses for dramatic narration ("Lý Minh kế nhiệm Đông Hải Đạo Cốc Chưởng Môn").

---

## §6 — Forge Admin sub-shapes (Q6 C + Q8 A LOCKED)

### §6.1 EVT-T8 Administrative sub-shapes V1

3 V1 sub-shapes per Q-decisions:

```rust
// Forge:GrantTitle — V1 active per Q6 C LOCKED (Forge admin runtime grant)
pub struct ForgeGrantTitle {
    pub actor_id: ActorId,
    pub title_id: TitleId,
    pub designated_heir: Option<ActorId>,                 // for Designated SuccessionRule
    pub reason: I18nBundle,
}

// Forge:RevokeTitle — V1 active (admin removal of title from holder)
pub struct ForgeRevokeTitle {
    pub actor_id: ActorId,
    pub title_id: TitleId,
    pub reason: I18nBundle,
    pub trigger_succession: bool,                         // V1: true → cascades succession; false → vacancy per VacancySemantic
}

// Forge:DesignateHeir — V1 active per Q6 C LOCKED (runtime heir change)
pub struct ForgeDesignateHeir {
    pub actor_id: ActorId,                                // current title holder
    pub title_id: TitleId,
    pub new_heir: Option<ActorId>,                        // None = clear designation (revert to no-heir state)
    pub reason: I18nBundle,
}
```

### §6.2 3-write atomic pattern

Per WA_003 Forge admin pattern (3-write atomic per established TIT-D / FAC_001 / REP_001 discipline):

```pseudo
on Forge:GrantTitle(admin, actor_id, title_id, designated_heir, reason):
  // Validation
  reject_if title_id ∉ canonical_titles → `title.declared.unknown`
  reject_if title_decl.binding == Faction(fid) && actor not in faction.fid → `title.binding.faction_membership_required`
  reject_if title_decl.binding == Dynasty(did) && actor not in dynasty.did → `title.binding.dynasty_membership_required`
  reject_if title_decl.multi_hold_policy.exclusive && exists holding(_, title_id) → `title.holding.exclusive_violation`
  reject_if title_decl.multi_hold_policy.cap_n && count(holdings(actor_id, *)) >= n → `title.holding.multi_hold_violation`
  // Q4 C V1 schema-reserved: V1 skips runtime rep check; V1+ activates alongside REP-D1
  
  // Atomic 3-write transaction
  WRITE 1: insert ActorTitleHolding { actor_ref: actor_id, title_id, granted_at_fiction_ts: now, granted_via: ForgeAdmin, designated_heir }
  WRITE 2: emit TitleGranted EVT-T4 + (if title_decl.authority_decl.faction_role_grant) atomically update actor_faction_membership.role_id
  WRITE 3: append forge_audit_log entry
  
  // Optional: emit TitleSuccessionCompleted EVT-T1 narrative milestone if this is a succession-style grant
```

---

## §7 — Cross-aggregate validator (Q7 A LOCKED — immediate cascade on WA_006 mortality EVT-T3)

### §7.1 Succession cascade C-rule

Registered in `_boundaries/03_validator_pipeline_slots.md` Stage 0+ canonical seed cross-aggregate consistency rules (joins existing C1-C17 from P4 commit; new rule TIT-C1):

**TIT-C1 (cross-aggregate succession cascade):** Title-holder death (WA_006 mortality EVT-T3 actor_dies) triggers TIT_001 succession cascade synchronously same turn. Owner: TIT_001. Trigger source: WA_006 mortality_state transition Alive → Dying / Dead.

### §7.2 Cascade pseudocode

```pseudo
on WA_006 mortality EVT-T3 actor_dies(actor_ref, fiction_ts, source_event_id):
  // Find all title holdings by deceased actor
  let titles_held = actor_title_holdings.filter(actor_ref=actor_ref);
  
  for holding in titles_held:
    let title_decl = reality.canonical_titles[holding.title_id];
    let new_holder = match title_decl.succession_rule {
      Eldest => find_eldest_in_dynasty(holding.title_id, title_decl.binding),
      Designated => holding.designated_heir,
      Vacate => None,
      // V1+ FactionElect — TIT-D1
    };
    
    let trigger_reason = match new_holder {
      Some(_) => HolderDeceased,
      None if title_decl.succession_rule == Vacate => NoEligibleHeir,
      None => NoEligibleHeir,  // designated heir invalid/dead; Eldest empty dynasty
    };
    
    // Validate eligibility (Q4 C schema-reserved V1; runtime rep check V1+)
    if let Some(heir) = new_holder {
      // V1: skip min_reputation_required runtime check (V1+ alongside REP-D1)
      // V1: validate heir is alive
      if !is_actor_alive(heir):
        new_holder = None;
        trigger_reason = HeirIneligible;
    }
    
    // Emit TitleSuccessionTriggered EVT-T3
    emit TitleSuccessionTriggered {
      from_actor_id: actor_ref,
      to_actor_id: new_holder,
      title_id: holding.title_id,
      trigger_reason,
      fiction_ts,
      source_event_id,
    };
    
    // Apply state changes
    delete actor_title_holdings(holding);
    
    if let Some(heir) = new_holder {
      // Insert new holding
      insert ActorTitleHolding {
        actor_ref: heir,
        title_id: holding.title_id,
        granted_at_fiction_ts: fiction_ts,
        granted_via: SuccessionCascade,
        designated_heir: None,  // new heir must designate own successor V1+
      };
      
      // Emit TitleGranted EVT-T4
      emit TitleGranted { actor_id: heir, title_id: holding.title_id, granted_at_fiction_ts: fiction_ts, granted_via: SuccessionCascade };
      
      // Atomic FAC role transfer if title.authority_decl.faction_role_grant
      if let Some(role_grant) = title_decl.authority_decl.faction_role_grant:
        update actor_faction_membership(actor_ref=heir, faction_id=role_grant.faction_id, role_id=role_grant.role_id);
        // 3-write atomic per WA_003 Forge pattern (no Forge admin trigger; cascade-internal)
      
      // Emit TitleSuccessionCompleted EVT-T1 narrative
      emit TitleSuccessionCompleted { actor_id: heir, title_id: holding.title_id, fiction_ts };
    } else {
      // Apply VacancySemantic
      match title_decl.vacancy_semantic {
        PersistsNone => {
          // Holding deleted; title persists in canonical_titles; revivable
          // No additional action
        },
        Disabled => {
          // Holding deleted; flag title disabled (V1+ TitleDecl.disabled bool field reserved)
          mark_title_disabled(holding.title_id);
        },
        Destroyed => {
          // RealityManifest entry removed
          remove canonical_titles[holding.title_id];
          // V1+ Forge:RemoveTitle admin sub-shape if needed (TIT-D# reservation)
        }
      }
    }
```

### §7.3 Determinism per EVT-A9

Cascade is fully deterministic — no RNG V1. Replay determinism preserved.

---

## §8 — V1 reject rules (`title.*` namespace)

### §8.1 V1 rule_ids (registered in `_boundaries/02_extension_contracts.md` §1.4)

7 V1 rule_ids:

| rule_id | Trigger | Vietnamese display (i18n bundle) |
|---|---|---|
| `title.declared.unknown` | TitleHoldingDecl or Forge:GrantTitle references title_id not in canonical_titles | "Tước hiệu không xác định" |
| `title.binding.faction_unknown` | TitleDecl.binding = Faction(faction_id) but faction_id not in canonical_factions | "Tước hiệu gắn với tổ chức không tồn tại" |
| `title.binding.dynasty_unknown` | TitleDecl.binding = Dynasty(dynasty_id) but dynasty_id not in canonical_dynasties (FF_001) | "Tước hiệu gắn với gia tộc không tồn tại" |
| `title.holding.actor_unknown` | actor_ref in canonical_title_holdings or Forge:GrantTitle not in canonical_actors (EF_001) | "Người giữ tước hiệu không xác định" |
| `title.holding.multi_hold_violation` | actor holds >MultiHoldPolicy.max(N) titles after grant | "Vượt quá số tước hiệu được phép giữ" |
| `title.holding.exclusive_violation` | Multiple actors hold Exclusive title concurrently | "Tước hiệu độc tôn đã có người khác giữ" |
| `title.succession.heir_invalid` | Designated heir not in canonical_actors OR dead at succession time | "Người kế thừa không hợp lệ" |

### §8.2 V1+ reservations

- `title.grant.rep_too_low` — V1+ runtime rep gating activation alongside REP-D1 (TIT-D2)
- `title.grant.progression_tier_too_low` — V1+ if cultivation-tier gating added (deferred; not committed)
- `title.lex_axiom.unknown` — V1+ requires_title axiom validation via WA_001 closure pass (TIT-D3)
- `title.faction_election.invalid_vote` — V1+ FactionElect SuccessionRule (TIT-D1)
- `title.cross_reality_mismatch` — V2+ Heresy migration (TIT-D9)

### §8.3 RejectReason envelope conformance

TIT_001 conforms to RES_001 §2.3 i18n contract — `RejectReason.user_message: I18nBundle` carries multi-language text. V1 ships I18nBundle from day 1.

---

## §9 — Sequence diagrams

### §9.1 Canonical seed bootstrap (Wuxia 12-title example)

```pseudo
RealityBootstrapper(reality_id):
  // Existing bootstrap order (per PL_001 §16): WA_001 Lex → ... → IDF → FF → FAC → REP → ACT → PCS → ...
  
  // TIT_001 bootstrap (after FAC_001 + REP_001 ready)
  for title_decl in reality.canonical_titles:
    validate title_decl:
      - title_id unique within reality
      - binding refs validate (Faction → canonical_factions; Dynasty → canonical_dynasties)
      - authority_decl.faction_role_grant.role_id ∈ FAC_001 RoleDecl(faction_id)
    // No event emitted at TitleDecl validation; structural only
  
  for holding_decl in reality.canonical_title_holdings:
    validate holding_decl:
      - title_id ∈ canonical_titles → else `title.declared.unknown`
      - actor_id ∈ canonical_actors → else `title.holding.actor_unknown`
      - if title_decl.binding == Faction(fid): actor must have membership in fid
      - if title_decl.binding == Dynasty(did): actor must have lineage in did (FF_001)
      - designated_heir validations (must be in canonical_actors if Some)
      - multi_hold check per actor
      - exclusive check per title
    
    insert ActorTitleHolding { actor_ref, title_id, granted_at_fiction_ts: starting_fiction_time, granted_via: CanonicalSeed, designated_heir }
    emit TitleGranted EVT-T4 { actor_id, title_id, granted_at_fiction_ts: starting_fiction_time, granted_via: CanonicalSeed }
    
    // Atomic FAC role grant if authority_decl.faction_role_grant
    if let Some(role_grant) = title_decl.authority_decl.faction_role_grant:
      update actor_faction_membership(actor_id, faction_id=role_grant.faction_id, role_id=role_grant.role_id)
```

### §9.2 Forge admin grant sequence

```pseudo
Forge:GrantTitle(admin, actor_id, title_id, designated_heir?, reason):
  Stage 0 schema validation:
    - admin has Forge capability per DP-K9
    - title_id ∈ canonical_titles
    - actor_id ∈ canonical_actors AND actor.alive
    - binding constraints (faction membership / dynasty lineage)
    - multi_hold_policy violation check
    - exclusive_policy violation check
  
  Atomic 3-write:
    1. insert ActorTitleHolding { actor_ref: actor_id, title_id, granted_at_fiction_ts: now, granted_via: ForgeAdmin, designated_heir }
    2. emit TitleGranted EVT-T4 { actor_id, title_id, granted_at_fiction_ts: now, granted_via: ForgeAdmin }
       + if authority_decl.faction_role_grant: atomic update actor_faction_membership
    3. append forge_audit_log entry
  
  // Optional narrative milestone
  if context indicates "this is a succession" (admin reason field hints):
    emit TitleSuccessionCompleted EVT-T1 { actor_id, title_id, fiction_ts: now }
```

### §9.3 Succession cascade on title-holder death (PRIMARY V1 flow)

```pseudo
WA_006 mortality_state transition Alive → Dead for actor_X (sect master Lý Lão Tổ):
  WA_006 emits EVT-T3 actor_dies { actor_ref: actor_X, fiction_ts, source_event_id }
  
  Validator pipeline Stage 0+ TIT-C1 (cross-aggregate cascade) fires synchronously:
  
  TIT_001.handle_actor_dies(actor_X, fiction_ts, source_event_id):
    titles_held_by_X = actor_title_holdings.filter(actor_ref=actor_X)
    // Lý Lão Tổ holds: donghai_sect_master + donghai_grand_elder
    
    for each title in titles_held_by_X:
      apply succession per §7.2 cascade pseudocode
      // donghai_sect_master:
      //   - succession_rule: Designated
      //   - Lý Lão Tổ.designated_heir = Lý Tử (top disciple)
      //   - Lý Tử is alive → new_holder = Lý Tử
      //   - emit TitleSuccessionTriggered { from: Lý Lão Tổ, to: Lý Tử, title: donghai_sect_master, reason: HolderDeceased }
      //   - delete old holding; insert new holding
      //   - emit TitleGranted { actor: Lý Tử, title: donghai_sect_master, via: SuccessionCascade }
      //   - update actor_faction_membership(Lý Tử, donghai_dao_coc, role: master)
      //   - emit TitleSuccessionCompleted EVT-T1 narrative milestone
      // donghai_grand_elder:
      //   - succession_rule: Designated
      //   - Lý Lão Tổ.designated_heir = None (no successor designated for elder title)
      //   - new_holder = None; trigger_reason = NoEligibleHeir
      //   - emit TitleSuccessionTriggered { from: Lý Lão Tổ, to: None, title: donghai_grand_elder, reason: NoEligibleHeir }
      //   - delete holding
      //   - apply VacancySemantic (PersistsNone default) → title persists; revivable
      //   - NO TitleSuccessionCompleted (no new holder)
  
  All operations within same turn — narrative continuity preserved.
```

---

## §10 — Acceptance Criteria

10 V1-testable scenarios. Each must pass deterministically per EVT-A9 replay.

### AC-TIT-1 — Author declares title schema; RealityManifest validates
- Setup: RealityManifest with canonical_titles containing 3 TitleDecls (1 emperor Standalone Eldest Exclusive PersistsNone; 1 sect-master Faction(donghai_dao_coc) Designated Exclusive PersistsNone with faction_role_grant role=master; 1 wandering hero Standalone Vacate StackableUnlimited PersistsNone with no faction_role_grant)
- Action: bootstrap reality
- Expected: TIT-V1 schema validator passes; canonical_titles populated; canonical_title_holdings empty Vec valid

### AC-TIT-2 — Canonical seed grants title with FAC role
- Setup: canonical_title_holdings = [{ actor_id: Lý Lão Tổ, title_id: donghai_sect_master, designated_heir: Lý Tử, ... }]; donghai_sect_master has authority_decl.faction_role_grant = (donghai_dao_coc, master)
- Action: bootstrap
- Expected: insert ActorTitleHolding row; emit TitleGranted EVT-T4 (granted_via: CanonicalSeed); atomic update actor_faction_membership(Lý Lão Tổ, donghai_dao_coc, role: master); 3-write atomic transaction commits

### AC-TIT-3 — Forge admin grants title
- Setup: NPC Lý Tử eligible for crown_prince title (Dynasty(imperial_li_dynasty); Eldest succession; Exclusive)
- Action: Forge:GrantTitle(admin, Lý Tử, crown_prince, designated_heir=None, reason)
- Expected: actor_title_holdings row inserted; TitleGranted EVT-T4 emitted; forge_audit_log entry appended; 3-write atomic

### AC-TIT-4 — Multi-hold violation rejected
- Setup: Lý Tử already holds crown_prince title; admin attempts to grant a second Exclusive title imperial_grand_marshal (also Exclusive)
- Action: Forge:GrantTitle(admin, Lý Tử, imperial_grand_marshal)
- Expected: reject `title.holding.multi_hold_violation` (or `exclusive_violation` depending on which constraint trips first); no row inserted; no event emitted

### AC-TIT-5 — Designated succession on holder death
- Setup: Lý Lão Tổ holds donghai_sect_master with designated_heir=Lý Tử (alive)
- Action: WA_006 emits actor_dies for Lý Lão Tổ
- Expected: TIT-C1 cascade fires synchronously; Lý Lão Tổ's holding deleted; Lý Tử's new holding inserted; emit TitleSuccessionTriggered (from: Lý Lão Tổ, to: Lý Tử, reason: HolderDeceased); emit TitleGranted (granted_via: SuccessionCascade); atomic actor_faction_membership update for Lý Tử; emit TitleSuccessionCompleted EVT-T1 narrative

### AC-TIT-6 — Eldest succession on emperor death (FF_001 traversal)
- Setup: Emperor Lý Đại Hoàng holds emperor_dongphong with succession_rule=Eldest; Crown Prince Lý Hoàng Tử = eldest living son in imperial_li_dynasty
- Action: WA_006 emits actor_dies for Lý Đại Hoàng
- Expected: cascade fires; FF_001 dynasty traversal returns Lý Hoàng Tử; emit TitleSuccessionTriggered (to: Lý Hoàng Tử); emit TitleGranted; emit TitleSuccessionCompleted

### AC-TIT-7 — Vacate succession on holder revoke
- Setup: NPC holds wandering_hero_titled (succession_rule=Vacate; VacancySemantic=PersistsNone)
- Action: Forge:RevokeTitle(admin, NPC, wandering_hero_titled, trigger_succession=true, reason)
- Expected: holding deleted; emit TitleSuccessionTriggered (to: None, reason: HolderRevoked); apply PersistsNone (no new holder); title persists in canonical_titles; NO TitleSuccessionCompleted

### AC-TIT-8 — Designate heir runtime
- Setup: Lý Lão Tổ holds donghai_sect_master with designated_heir=Lý Tử
- Action: Forge:DesignateHeir(admin, Lý Lão Tổ, donghai_sect_master, new_heir=Lý Phụng, reason)
- Expected: actor_title_holdings row updated (designated_heir: Lý Tử → Lý Phụng); forge_audit_log entry; no other side effects (no EVT-T1/T3 emit)

### AC-TIT-9 — Heir invalid at succession
- Setup: Lý Lão Tổ holds donghai_sect_master with designated_heir=Lý Tử; Lý Tử died earlier (mortality_state=Dead)
- Action: WA_006 emits actor_dies for Lý Lão Tổ
- Expected: cascade fires; eligibility check fails (heir not alive); new_holder=None, trigger_reason=HeirIneligible; emit TitleSuccessionTriggered (to: None, reason: HeirIneligible); apply VacancySemantic::PersistsNone; NO new holding inserted; NO TitleSuccessionCompleted

### AC-TIT-10 — Destroyed vacancy on dynasty extinction
- Setup: Emperor of Fallen Dynasty title declared with succession_rule=Eldest + VacancySemantic=Destroyed; emperor dies; FF_001 dynasty has no living members
- Action: WA_006 emits actor_dies for emperor
- Expected: cascade fires; dynasty traversal returns None; emit TitleSuccessionTriggered (to: None, reason: NoEligibleHeir); apply VacancySemantic::Destroyed; canonical_titles entry REMOVED (RealityManifest mutated); NO TitleSuccessionCompleted

### V1+ deferred AC

- **AC-TIT-V1+1**: V1+ FactionElect succession (DIPL_001 procedural vote integration; TIT-D1)
- **AC-TIT-V1+2**: V1+ runtime min_reputation_required validator (alongside REP-D1; TIT-D2)
- **AC-TIT-V1+3**: V1+ requires_title Lex axiom validator (WA_001 closure pass; TIT-D3)
- **AC-TIT-V1+4**: V2+ vassalage hierarchy succession (TIT_002; TIT-D4)

---

## §11 — V1 Minimum Delivery Summary

| Element | V1 spec |
|---|---|
| Aggregates | 1 (`actor_title_holdings`) |
| RealityManifest extensions | 2 OPTIONAL (canonical_titles + canonical_title_holdings) |
| TitleBinding variants | 3 V1 (Faction / Dynasty / Standalone) |
| SuccessionRule variants | 3 V1 (Eldest / Designated / Vacate) + 1 V1+ FactionElect |
| MultiHoldPolicy variants | 3 V1 (Exclusive / StackableUnlimited / StackableMax(N)) |
| VacancySemantic variants | 3 V1 (PersistsNone / Disabled / Destroyed) |
| EVT-T4 sub-types | 1 (TitleGranted) |
| EVT-T8 sub-shapes | 3 (Forge:GrantTitle / RevokeTitle / DesignateHeir) |
| EVT-T3 sub-types | 1 (TitleSuccessionTriggered) |
| EVT-T1 sub-types | 1 (TitleSuccessionCompleted narrative) |
| Cross-aggregate validators | 1 (TIT-C1 succession cascade on WA_006 mortality) |
| RejectReason rule_ids | 7 V1 + 5 V1+ reservations |
| Acceptance scenarios | 10 V1 + 4 V1+ deferred |
| Stable-ID prefix | TIT-* |
| Cross-feature deferrals resolved | FF-D8 (full V1) + FAC-D6 (full V1) + REP-D9 (V1 partial) + WA_006 sect-leader-death cascade gap (full V1) |

---

## §12 — Deferrals Catalog (TIT-D1..TIT-D12)

**V1+30d (fast-follow):**
- TIT-D2 Runtime min_reputation_required validator (alongside REP-D1)
- TIT-D3 requires_title Lex axiom validator (WA_001 closure pass; 5-companion-fields uniform addition)
- TIT-D5 8 CK3 succession law variants (gender + partition variants)
- TIT-D10 Origin-pack default_titles (IDF_004 OriginPack additive)
- TIT-D12 title_state per-title singleton projection (if filter scan proves limiting)

**V2 (Economy/Strategy module-tier):**
- TIT-D1 SuccessionRule::FactionElect active (DIPL_001 procedural vote)
- TIT-D8 Quest reward = title grant (13_quests integration)
- TIT-D11 Multi-axis title taxonomy (CK3 Prestige + Piety + Renown; alongside REP-D5)

**V2+ (Heresy / Strategy):**
- TIT-D4 Vassalage hierarchy (TIT_002 separate feature)
- TIT-D6 Term-limited titles (Imperator consul fiction-time bound)
- TIT-D7 Title decay over fiction-time
- TIT-D9 Cross-reality title migration via WA_002 Heresy

---

## §13 — Cross-references

### §13.1 Resolves cross-feature deferrals

- **FF-D8** (FF_001): Title inheritance rules + heir succession → V1 RESOLVES (full active via SuccessionRule::Eldest reading dynasty.current_head_actor_id traversal)
- **FAC-D6** (FAC_001): Sect succession rules → V1 RESOLVES (full active via SuccessionRule::Designated + sect-master title binding to FactionId)
- **REP-D9** (REP_001): V1+ TIT_001 title-grant requires min rep → V1 PARTIAL RESOLVES (TitleDecl.min_reputation_required schema active; runtime gating V1+ alongside REP-D1)
- **WA_006 sect-leader-death cascade gap** (FAC_001 _index.md): Sect-leader death triggers V1+ TIT_001 succession → V1 RESOLVES (full active via TIT-C1 cross-aggregate validator)

### §13.2 Cross-feature integration

- **EF_001 Entity Foundation** — TIT_001 reads ActorId source-of-truth for actor_title_holdings.actor_ref
- **FF_001 Family Foundation** — TIT_001 reads dynasty.current_head_actor_id for SuccessionRule::Eldest traversal; reads family_node.parent_actor_ids for fallback chain
- **FAC_001 Faction Foundation** — TIT_001 reads canonical_factions for TitleBinding::Faction validation; writes actor_faction_membership.role_id atomically on title-grant via TitleAuthorityDecl.faction_role_grant
- **REP_001 Reputation Foundation** — TIT_001 declares MinRepGate V1; runtime validator activates V1+ alongside REP-D1
- **RES_001 Resource Foundation** — TIT_001 conforms to I18nBundle pattern (display_name + description + narrative_hint)
- **PROG_001 Progression Foundation** — V1: no progression-tier gating (per PROG-A1 author-discipline; reality author can declare via Forge admin enforcement); V1+ if cultivation-tier gating ships
- **ACT_001 Actor Foundation** — TIT_001 reads ActorRef source from actor_core; V1: title appears in NPC_001 persona briefing via TitleAuthorityDecl.narrative_hint
- **PCS_001 PC Substrate** — V1: PC creation form may set initial title via origin-pack-driven canonical_title_holdings (V1+ runtime via PO_001 Player Onboarding)
- **WA_001 Lex** — V1+ AxiomDecl.requires_title hook integration (5-companion-fields uniform addition: race + ideology + faction + reputation + title); TIT_001 V1 schema-reserves lex_axiom_unlock_refs
- **WA_003 Forge** — TIT_001 V1 reuses 3-write atomic Forge admin pattern + forge_audit_log
- **WA_006 Mortality** — TIT_001 V1 active TIT-C1 cross-aggregate cascade on actor_dies EVT-T3
- **NPC_001 Cast** — V1: persona AssemblePrompt reads actor_title_holdings; NPC briefing includes titles via I18nBundle narrative_hint
- **NPC_002 Chorus** — V1+: Tier 4 priority modifier reads actor_title_holdings (titled NPCs prioritized; rare)
- **PL_005 Interaction** — V1+: titled-actor narrative carries title context (Speak/Strike actions; LLM uses for dialogue)
- **AIT_001 AI Tier** — TIT_001 V1: title-holders typically NpcTrackingTier::Major or ::Minor (rare for Untracked); cross-feature coordination via AIT_001 tier_hint
- **TDIL_001 Time Dilation** — TIT_001 V1: titles unaffected by time dilation V1; V2+ term-limited titles use fiction-time bounds (TIT-D6)
- **EVT_model EVT-A11** — TIT_001 owns actor_title_holdings; only TIT_001 emits EVT-T3/T4/T8/T1 sub-shapes per Aggregate-Owner discipline

### §13.3 V1+ downstream features

- **PO_001 Player Onboarding** — V1+ UI flow uses TIT_001 origin-pack default_titles for initial PC title (TIT-D10)
- **DIPL_001 Diplomacy V2+** — uses TIT_001 title-holder identity for treaty-signing authority; V1+ FactionElect (TIT-D1)
- **CULT_001 V2+ template library** — CultivationRealmDecl templates may declare title-grant per realm tier (V2+ "Hóa Thần grants Đại Trưởng Lão sect-elder title")
- **13_quests V2+** — quest reward = title grant (TIT-D8)

---

## §14 — Status

- **Created:** 2026-04-27 by main session
- **Phase:** DRAFT 2026-04-27 — Q1-Q10 LOCKED via 4-batch deep-dive zero revisions
- **Status target:** CANDIDATE-LOCK after Phase 3 review cleanup + closure pass + downstream coordination notes
- **Companion docs:**
  - [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept + Q1-Q10 LOCKED matrix §10)
  - [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (CK3 + Wuxia hybrid V1 anchor)
  - [`catalog/cat_00_TIT_title_foundation.md`](../../catalog/cat_00_TIT_title_foundation.md) (axioms + entries + deferrals)
  - [`_index.md`](_index.md) (folder index)
- **4-commit cycle:**
  - 1/4 Phase 0 (commit f9e7600f) — concept notes + reference survey + index
  - 2/4 DRAFT (this commit) — TIT_001_title_foundation.md spec + boundary updates + catalog seed; WITH `[boundaries-lock-claim]`
  - 3/4 Phase 3 cleanup (next commit) — self-review fixes + downstream coordination notes
  - 4/4 CANDIDATE-LOCK closure (next commit) — final lock + RESOLVES FF-D8/FAC-D6/REP-D9-partial/WA_006-cascade-gap; `[boundaries-lock-release]`
