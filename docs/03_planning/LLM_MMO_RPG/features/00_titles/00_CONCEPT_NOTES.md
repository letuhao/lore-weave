# TIT_001 Title Foundation — Concept Notes

> **Status:** Q-LOCKED 2026-04-27 — 4-batch deep-dive complete; all 10 Qs LOCKED zero revisions; transitions to DRAFT 2/4 commit immediately following this lock.
> **Companion docs:** [`_index.md`](_index.md) (folder index) + [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (reference materials)
> **Stable-ID prefix:** `TIT-*` (anticipated)
> **Catalog:** `catalog/cat_00_TIT_title_foundation.md` (planned at DRAFT 2/4 commit)

---

## §1 — User framing (post FF/FAC/REP closure)

User direction 2026-04-27: post CULT_001 V2+ defer (commit d57fb7fc), TIT_001 picked as next-priority because:
- "small foundation feature; closes REP/FAC/FF triangle with title inheritance"
- "~3-4 commit cycle"

**Why TIT_001 NOW (vs deferring like CULT_001):**

Unlike CULT_001 which violates PROG-A1 axiom (engine cannot fix progression schema), TIT_001 introduces a NEW aggregate semantic that doesn't already exist in PROG_001. Title is **NOT a progression** — it's a discrete grant/hold relationship with succession rules. Distinct from:

- **PROG_001 Stage progression** — title doesn't accrue raw_value through training; it's granted atomically by reality/Forge/heir-rule
- **FAC_001 actor_faction_membership** — title may be faction-bound BUT a faction can have many roles (disciple/elder/master) while a title is typically singleton (one sect-master per sect)
- **REP_001 actor_faction_reputation** — title is a discrete holding, not a continuous score; rep gates title-grant V1 but doesn't replace it

**Author-declared per-reality discipline (per PROG-A1 spirit):**
TIT_001 itself doesn't hardcode title names. Each reality declares own title list:
- Wuxia reality: "掌门 Sect Master" / "长老 Elder" / "皇帝 Emperor" / "族长 Family Patriarch" / "侠客 Wandering Hero"
- Modern reality: "President" / "CEO" / "Senator" / "Governor"
- D&D reality: "King" / "Lord" / "Knight" / "Baron"
- Sci-fi reality: "Admiral" / "Senator" / "Governor of Sector X"

Same engine schema; different content per reality. Follows PROG_001 + REP_001 + FAC_001 declaration discipline.

### What V1 ships

- **1 NEW sparse aggregate** — `actor_title_holdings` per-(actor, title_id) edge
- **2 RealityManifest extensions** — `canonical_titles: Vec<TitleDecl>` + `canonical_title_holdings: Vec<TitleHoldingDecl>` (both OPTIONAL V1; sandbox/freeplay realities may have empty title list)
- **1 EVT-T4** — `TitleGranted` (canonical seed only V1; runtime via cascade or Forge V1+)
- **3 EVT-T8 AdminAction** — `Forge:GrantTitle` + `Forge:RevokeTitle` + `Forge:DesignateHeir` (full Forge admin authoring V1)
- **1 EVT-T3 Derived** — `TitleSuccessionTriggered` (sparse; on title-holder death or explicit revoke)
- **1 EVT-T1 Narrative** — `TitleSuccessionCompleted` (narrative milestone for LLM)
- **Cross-aggregate validator C-rule** — title_holder dies → cascade succession check
- **`title.*` namespace** (~5-7 V1 reject rules + V1+ reservations)
- **TIT-* stable-ID prefix**

### What V1 NOT shipping (deferred per anticipated Q-decisions)

- **FactionElect SuccessionRule active** — V1+ when DIPL_001 procedural voting ships
- **Lex axiom requires_title hook active** — V1+ WA_001 closure pass adds 5-companion-fields uniformly
- **Vassalage hierarchy** (CK3 baron→count→duke→king→emperor) — V2+ separate TIT_002
- **Multi-axis title taxonomy** (CK3 Prestige + Piety + Renown) — V2+ alongside REP-D5
- **Cross-reality title migration via WA_002 Heresy** — V2+
- **Title decay over fiction-time** (CK3 prestige decay) — V2+ if needed
- **Quest reward = title grant** — V2+ 13_quests integration
- **Title stack policy beyond cap=N** (e.g., "lord of 3 different lands") — Q5 V1 decides cap

---

## §2 — Worked examples

### §2.1 Wuxia 3-title scenario (PRIMARY V1 reference)

Reality: Đông Phong Cõi (DongPhong realm) — Wuxia reality with 5 sects + imperial court.

Author declares 12 titles in `canonical_titles`:

| title_id | display_name | binding | succession_rule | min_rep | authority |
|---|---|---|---|---|---|
| `emperor_dongphong` | "Hoàng Đế Đông Phong" | Standalone | Designated (Forge or pre-declared heir) | None | grants imperial-axiom-unlock V1+ |
| `crown_prince_dongphong` | "Thái Tử Đông Phong" | Dynasty(`imperial_li_dynasty`) | Eldest (FF_001 traversal) | None | succeeds emperor on death |
| `imperial_grand_marshal` | "Đại Nguyên Soái" | Faction(`imperial_army`) | Designated by emperor | Honored+ rep with imperial_court | grants role=marshal in imperial_army |
| `donghai_sect_master` | "Đông Hải Đạo Cốc Chưởng Môn" | Faction(`donghai_dao_coc`) | Designated by current master OR FactionElect (V1+) | Honored+ rep with donghai_dao_coc | grants role=master in donghai_dao_coc |
| `donghai_grand_elder` | "Đông Hải Đại Trưởng Lão" | Faction(`donghai_dao_coc`) | Designated by sect master | Revered+ rep | grants role=grand_elder |
| `family_patriarch_li` | "Lý Gia Gia Trưởng" | Dynasty(`lineage_li`) | Eldest (FF_001 traversal) | None | grants family-decision authority V1+ |
| `family_patriarch_zhao` | "Triệu Gia Gia Trưởng" | Dynasty(`lineage_zhao`) | Eldest | None | (mirror) |
| `wandering_hero_titled` | "Đại Hiệp" | Standalone | Vacate (no auto; achievement-only) | Revered+ rep with imperial_court OR donghai_dao_coc | pure honor V1; LLM uses for narrative |
| `assassin_blackwind` | "Hắc Phong Sát Thủ" | Faction(`blackwind_assassins`) | Designated by current title-holder | None (rep N/A — secret faction) | grants role=top_assassin |
| ... 3 more titles | ... | ... | ... | ... | ... |

Initial canonical seed in `canonical_title_holdings`:
- Lý Minh PC holds: `donghai_grand_elder` (granted at PC creation per origin-pack)
- NPC Lý Lão Tổ holds: `donghai_sect_master` (canonical 50-year holder)
- NPC Lý Đại Hoàng holds: `emperor_dongphong` + `crown_prince_dongphong` blank (no heir yet — Forge admin must designate)
- NPC Lý Đại Tướng Quân holds: `imperial_grand_marshal`
- NPC Lý Tổ holds: `family_patriarch_li`

V1 narrative usage:
- LLM persona briefing for Lý Lão Tổ reads: "Đông Hải Đạo Cốc Chưởng Môn, faction master of donghai_dao_coc, age 187, soul cultivation: Hóa Thần realm, current member count 234"
- Lý Minh meeting Lý Lão Tổ: NPC_001 AssemblePrompt includes Lý Lão Tổ's title context for greeting protocol (Đệ tử must greet Chưởng Môn formally)
- Lý Lão Tổ dies of old age (WA_006 mortality EVT-T3) → TIT_001 cross-aggregate validator cascades → SuccessionRule = Designated → check Lý Lão Tổ's designated heir → if exists + still alive + has Honored+ rep with donghai_dao_coc → emit `TitleSuccessionTriggered` EVT-T3 + `TitleSuccessionCompleted` EVT-T1 narrative event → new master = designated heir → Lý Lão Tổ's `donghai_sect_master` holding row removed → designated heir's row created

### §2.2 Modern political-rank scenario

Reality: Modern Saigon 2026 — Modern reality with police-vs-criminal-orgs setup.

Author declares 8 titles:
- `vietnam_president` (Standalone; Designated by parliament Forge V1; vacate on death)
- `prime_minister` (Standalone; Designated; vacate)
- `district_chief_q1` (Faction(`saigon_government`); Designated by mayor; ~1-year-term V1+ if term-limit field added)
- `cartel_boss_red_dragon` (Faction(`red_dragon_cartel`); Designated by previous boss OR FactionElect V1+; secret faction so rep N/A)
- `cartel_lieutenant_north` (Faction(`red_dragon_cartel`); Designated by boss)
- `judge_district_4` (Faction(`saigon_judiciary`); Designated by appointment; min Honored rep with saigon_judiciary)
- `senator` (Standalone; Designated by election V1+ FactionElect; ~6-year term V1+)
- `mayor_saigon` (Faction(`saigon_government`); Designated by election V1+ FactionElect; vacate)

Initial canonical seed: 8 NPCs hold respective titles at reality bootstrap.

V1 narrative usage: Police Detective Smith (PC) investigating cartel_lieutenant_north must navigate cartel hierarchy; LLM uses title for power dynamics narration.

### §2.3 D&D noble-knight scenario

Reality: Forgotten Realms — D&D reality with feudal kingdoms.

Author declares 15 titles:
- `king_cormyr` (Standalone; Eldest dynasty traversal)
- `crown_prince_cormyr` (Dynasty(`obarskyr_dynasty`); Eldest)
- `duke_arabel` (Faction(`cormyr_realm`); Eldest dynasty + min Honored rep with cormyr_realm)
- `count_arabel_subdivision` (vassal of duke_arabel; V2+ vassalage hierarchy)
- `lord_lord_lord` (Standalone; Designated by king or duke)
- `knight_purple_dragon` (Faction(`cormyr_purple_dragons`); Designated by knight-master; min Friendly+ rep)
- `archmage_war_wizards` (Faction(`war_wizards`); Designated by elder council; min Honored+ rep)
- `high_priest_lathander` (Faction(`temple_of_lathander`); Designated; min Honored+ rep + Lathander deity affinity V2+)
- ... 7 more knight + lord titles ...

Worked sequence: King dies → SuccessionRule = Eldest → FF_001 dynasty.current_head_actor_id traversal → Crown Prince Tonyn (Lý Minh PC, 22 years old) becomes king → `king_cormyr` holding migrates to PC → if PC has Honored+ rep with cormyr_realm proceed; else reject `title.succession.rep_too_low` (V1+ rep gating, V1 schema-reserved).

---

## §3 — Domain concepts (anticipated)

### §3.1 TitleDecl (RealityManifest declaration)

```rust
pub struct TitleDecl {
    pub title_id: TitleId,
    pub display_name: I18nBundle,
    pub description: I18nBundle,
    pub binding: TitleBinding,                            // Q2 — Faction / Dynasty / Standalone
    pub succession_rule: SuccessionRule,                  // Q3 — Eldest / Designated / Vacate / V1+ FactionElect
    pub min_reputation_required: Option<MinRepGate>,      // Q4 — schema active V1; runtime gating V1+
    pub authority_decl: TitleAuthorityDecl,               // Q8 — what title GRANTS mechanically
    pub multi_hold_policy: MultiHoldPolicy,               // Q5 — exclusive vs stackable
    pub vacancy_semantic: VacancySemantic,                // Q9 — persists None / disabled / destroyed
}

pub enum TitleBinding {                                   // Q2
    Faction(FactionId),                                   // sect-master / guild-leader / cartel-boss
    Dynasty(DynastyId),                                   // emperor / family-patriarch
    Standalone,                                           // wandering hero / honor title / unaffiliated
}

pub enum SuccessionRule {                                 // Q3
    Eldest,                                               // FF_001 dynasty traversal
    Designated,                                           // current holder Forge:DesignateHeir; or canonical pre-declared
    Vacate,                                               // no auto-succession; manual re-grant
    // V1+ FactionElect (procedural vote; depends on DIPL_001 V2+)
}

pub struct MinRepGate {                                   // Q4
    pub faction_id: FactionId,
    pub min_tier: ReputationTier,                         // e.g., Honored+
}

pub struct TitleAuthorityDecl {                           // Q8
    pub faction_role_grant: Option<FactionRoleGrant>,     // V1 active — FAC_001 role binding
    pub lex_axiom_unlock_refs: Vec<AxiomDeclRef>,         // V1+ schema-reserved; V1+ WA_001 closure
    pub narrative_hint: I18nBundle,                       // V1 — LLM uses in persona briefing
}

pub struct FactionRoleGrant {
    pub faction_id: FactionId,
    pub role_id: FactionRoleId,                           // sect-master title grants role=master in faction
}

pub enum MultiHoldPolicy {                                // Q5
    Exclusive,                                            // emperor: only 1 holder per reality
    StackableUnlimited,                                   // generic: actor can hold multiple
    StackableMax(u8),                                     // e.g., max 3 noble titles per actor (CK3 pattern)
}

pub enum VacancySemantic {                                // Q9
    PersistsNone,                                         // title persists with current_holder=None; revivable
    Disabled,                                             // title disabled until Forge re-grants
    Destroyed,                                            // RealityManifest entry removed (rare; for fallen-empire titles)
}

pub struct TitleId(pub String);                           // e.g., "donghai_sect_master"
pub struct DynastyId = FF_001 dynasty.dynasty_id;
pub struct FactionRoleId = FAC_001 actor_faction_membership.role_id;
```

### §3.2 actor_title_holdings aggregate (sparse per-(actor, title))

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_title_holdings", tier = "T2", scope = "reality")]
pub struct ActorTitleHolding {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,
    pub title_id: TitleId,
    pub granted_at_fiction_ts: i64,
    pub granted_via: GrantSource,
    pub designated_heir: Option<ActorRef>,                // for Designated SuccessionRule; null otherwise
    pub schema_version: u32,                              // V1 = 1
}

pub enum GrantSource {
    CanonicalSeed,                                        // declared in RealityManifest at bootstrap
    ForgeAdmin,                                           // Forge:GrantTitle
    SuccessionCascade,                                    // auto-grant on previous holder death
    // V1+ QuestReward { quest_id }
    // V1+ FactionElectVote { vote_event_id }
}
```

### §3.3 Cross-aggregate validator (title-holder death → succession cascade)

Pseudocode:
```pseudo
on WA_006 mortality EVT-T3 actor_dies(actor_ref):
  // Find all title holdings by this actor
  let titles_held = actor_title_holdings.filter(holder=actor_ref);
  
  for holding in titles_held:
    let title_decl = reality.canonical_titles[holding.title_id];
    let next_holder = match title_decl.succession_rule {
      Eldest => find_eldest_in_dynasty(holding.title_id, title_decl.binding),
      Designated => holding.designated_heir,
      Vacate => None,
    };
    
    // Check eligibility (rep gating V1+ schema-reserved)
    if let Some(heir) = next_holder {
      if title_decl.min_reputation_required.is_some() {
        // V1+ check rep tier; V1 skip with schema-reserved field
        // V1: proceed; V1+ verify rep >= min_tier
      }
      
      // Emit succession events
      emit TitleSuccessionTriggered { from: actor_ref, to: heir, title_id, fiction_ts };
      // Apply: remove old holding row, create new holding row
      delete holding;
      insert ActorTitleHolding { actor_ref: heir, title_id, granted_at_fiction_ts: now, granted_via: SuccessionCascade, ... };
      emit TitleSuccessionCompleted { actor_ref: heir, title_id, fiction_ts } [EVT-T1 narrative];
    } else {
      // Vacate or no eligible heir
      emit TitleSuccessionTriggered { from: actor_ref, to: None, title_id, fiction_ts };
      // Apply vacancy semantic
      match title_decl.vacancy_semantic {
        PersistsNone => delete holding, // title still in canonical_titles; no holder
        Disabled => mark title disabled,
        Destroyed => remove from canonical_titles,
      }
    }
```

---

## §4 — Boundary intersections with locked features

| Locked feature | TIT_001 V1 interaction |
|---|---|
| **EF_001 Entity Foundation** | Reads ActorId source-of-truth |
| **FF_001 Family Foundation** | Reads dynasty.current_head_actor_id for Eldest succession; reads family_node.parent_actor_ids for traversal |
| **FAC_001 Faction Foundation** | Reads actor_faction_membership.role_id (TitleAuthorityDecl.faction_role_grant); writes actor_faction_membership on title-grant (Forge:GrantTitle may auto-grant role) |
| **REP_001 Reputation Foundation** | Reads actor_faction_reputation tier for min_reputation_required gate (V1 schema-active; V1+ runtime active) |
| **RES_001 Resource Foundation** | I18nBundle pattern (display_name + description multi-language) |
| **PROG_001 Progression Foundation** | (TBD Q-decision) — does title require min progression tier? E.g., "Sect Master requires Hóa Thần realm cultivation". Could use derives_from-style read of ProgressionInstance.current_tier. V1 might add `min_progression_tier: Option<ProgressionTierGate>` to TitleDecl OR defer to V1+ |
| **ACT_001 Actor Foundation** | actor_core canonical_traits — TBD if title appears here as hint OR purely in actor_title_holdings (Q1 decision) |
| **PCS_001 PC Substrate** | PC creation form may set initial title via origin-pack default; V1+ |
| **WA_001 Lex** | V1+ AxiomDecl.requires_title hook (5-companion-fields uniformly per WA_001 closure pass) |
| **WA_003 Forge** | 3-write atomic Forge admin pattern for GrantTitle/RevokeTitle/DesignateHeir + forge_audit_log |
| **WA_006 Mortality** | Title-holder death → TIT_001 cross-aggregate succession cascade C-rule |
| **NPC_001 Cast** | persona AssemblePrompt reads actor_title_holdings (V1 persona briefing includes titles) |
| **NPC_002 Chorus** | V1+ Tier 4 priority modifier (titled NPCs get attention) |
| **PL_005 Interaction** | V1+ titled-actor narrative carries title context (Speak/Strike) |
| **AIT_001 AI Tier** | NpcTrackingTier.tier_hint should reflect title-holder priority (titled NPCs are usually Major/Minor not Untracked) |
| **TDIL_001 Time Dilation** | actor_clocks unaffected by TIT_001; titles don't have time dimension V1 (V2+ term-limited titles use fiction-time bounds) |
| **EVT_model EVT-A11** | Aggregate-Owner discipline: TIT_001 owns actor_title_holdings; only TIT_001 emits EVT-T3/T4/T8 sub-shapes |
| **EVT_model EVT-T1** | TitleSuccessionCompleted narrative event for LLM |
| **EVT_model EVT-T3** | TitleSuccessionTriggered derived event |
| **EVT_model EVT-T4** | TitleGranted system event (canonical seed + Forge admin) |
| **EVT_model EVT-T8** | Forge:GrantTitle + Forge:RevokeTitle + Forge:DesignateHeir admin sub-shapes |

---

## §5 — Gap analysis (10 dimensions across 4 grouped concerns)

### Concern A: Aggregate model + binding scope (Q1 + Q2)

**Q1**: Aggregate model — per-(actor, title) edge sparse vs per-title singleton current_holder
- (A) `actor_title_holdings` sparse — easier multi-title actor; better for rare hold ("Lý Minh holds both Sect Elder + Family Patriarch"); matches REP_001 + FAC_001 pattern
- (B) `title_state` singleton (per-title; current_holder + previous_holder_log) — easier "who holds this title?" lookup; cleaner for unique titles; doesn't scale to multi-hold
- (C) Both — projection between them (V1+ adds `title_state` projection from `actor_title_holdings`)

Pre-recommendation: **(A)** matches established REP/FAC sparse-edge pattern; multi-hold is realistic V1.

**Q2**: Title binding scope — title can be bound to faction (sect-master) / dynasty (emperor) / actor-only (standalone honor)?
- (A) 3-axis optional refs: optional faction_ref + optional dynasty_ref + optional standalone (allows hybrid like emperor of multi-dynasty but unusual)
- (B) Discriminated `enum TitleBinding { Faction(FactionId) / Dynasty(DynastyId) / Standalone }` — cleaner V1; mutually exclusive
- (C) None binding required (always Standalone V1; faction/dynasty links V1+)

Pre-recommendation: **(B)** Discriminated 3-variant enum — clean discrete semantics matching rest of LoreWeave enum patterns.

### Concern B: Succession + heir-designation (Q3 + Q6 + Q7)

**Q3**: SuccessionRule V1 variants count
- (A) 3 V1 + 1 V1+: Eldest / Designated / Vacate V1; FactionElect V1+ (DIPL_001 dependency)
- (B) 4 V1 (incl FactionElect with Forge author-trigger placeholder)
- (C) 2 V1 minimum: Eldest / Designated only

Pre-recommendation: **(A)** 3 V1 + 1 V1+ — Vacate covers "no auto-succession" cases (achievement-only titles like "Đại Hiệp"); FactionElect needs DIPL_001 procedural voting (V2+).

**Q6**: Heir designation timing/who
- (A) Title-holder Forge command anytime (Forge:DesignateHeir; admin-only in V1; runtime title-holder V1+)
- (B) Author-only V1 (RealityManifest declares heir at canonical seed); V1+ runtime title-holder Forge
- (C) Both V1 — author canonical declaration + Forge admin override anytime

Pre-recommendation: **(C)** Both — author canonical declaration covers initial state; Forge admin override covers runtime narrative-driven heir change.

**Q7**: Cross-aggregate succession trigger timing
- (A) Immediate cascade on WA_006 mortality EVT-T3 (same turn; titlebearer dies → succession fires same turn)
- (B) Day-boundary Generator scan (deferred 1 turn for batch; matches RES_001 4 generators sequencing)
- (C) Forge admin manual trigger only V1 (no auto-cascade V1)

Pre-recommendation: **(A)** Immediate cascade — political succession is narrative-critical; delayed succession breaks story flow ("Emperor died; nation has no leader for 1 fiction-day" feels wrong).

### Concern C: Reputation/progression gating (Q4 + Q10)

**Q4**: Min reputation gating active V1 (REP-D9 deferral resolution)
- (A) V1 active (TIT-A1 axiom): title_grant + ongoing-hold both validated against rep
- (B) V1+ deferred (matches REP-D9 originally V1+)
- (C) V1 schema-reserved (field exists on TitleDecl but validator V1+; runtime grant skips check)

Pre-recommendation: **(C)** V1 schema-reserved — TitleDecl.min_reputation_required field declarable V1; validator V1+ alongside REP-D1 runtime delta milestone (when rep can change runtime, gating becomes meaningful). V1 canonical seed declarations describe intent; runtime enforcement V1+.

**Q10**: V1+ requires_title Lex axiom timing
- (A) V1+ active — full Lex hook integration in this commit (large scope creep)
- (B) V1 schema-reserved (TitleAuthorityDecl.lex_axiom_unlock_refs field exists but validator V1+ via WA_001 closure pass)
- (C) V1+ entirely (no schema reservation; adds at WA_001 closure pass)

Pre-recommendation: **(B)** V1 schema-reserved — keeps WA_001 closure pass clean (5-companion-fields uniform addition: race + ideology + faction + reputation + title); V1 TitleAuthorityDecl supports field declaration without validator.

### Concern D: Multi-hold + authority + vacancy (Q5 + Q8 + Q9)

**Q5**: Multi-title cap per actor V1
- (A) Unlimited V1 (StackableUnlimited default; each TitleDecl can override)
- (B) Cap 1 V1 (matches FAC-Q2 single-faction-membership pattern; conservative)
- (C) Per-title author-declared MultiHoldPolicy (Exclusive / StackableUnlimited / StackableMax(N)) V1

Pre-recommendation: **(C)** per-title MultiHoldPolicy — emperor=Exclusive (only 1 emperor per reality); generic noble titles=StackableUnlimited; CK3-style noble cap=StackableMax(3). Most flexible V1; defaults to StackableUnlimited if not declared.

**Q8**: Title authority — what title GRANT mechanically
- (A) FAC_001 role grant (delegates to FactionRoleId; sect-master title grants role=master in faction; Sets actor_faction_membership.role_id)
- (B) Lex axiom unlock (V1+ WA_001 requires_title hook gates abilities/actions)
- (C) Both V1 — title grants role + axiom unlock (large scope)
- (D) Pure honor V1 (no mechanical grant; LLM uses for narrative); FAC role + Lex axiom V1+

Pre-recommendation: **(A) + V1 narrative_hint** — FAC role grant active V1 (sect-master IS sect role=master; tightly coupled per wuxia); narrative_hint string for LLM persona briefing; Lex axiom V1+ via Q10 schema-reserved.

**Q9**: Vacancy semantics
- (A) PersistsNone — title persists in canonical_titles with current_holder=None; revivable when eligible heir appears
- (B) Disabled — title persists but flagged disabled; Forge re-grant required
- (C) Destroyed — RealityManifest entry removed (rare; "fallen empire" titles)
- (D) Per-title author-declared (VacancySemantic enum on TitleDecl)

Pre-recommendation: **(D)** per-title VacancySemantic — emperor of fallen empire = Destroyed; sect-master between elders = PersistsNone; achievement-only "Đại Hiệp" = PersistsNone (achievement can be re-earned by others); modern senate seat = PersistsNone (election fills it).

---

## §6 — Q1-Q10 critical scope questions (for batched deep-dive)

| # | Question | Options | Pre-rec |
|---|---|---|---|
| Q1 | Aggregate model — actor-edge vs per-title singleton | A (actor_title_holdings sparse) / B (title_state singleton) / C (both) | A |
| Q2 | Title binding scope | A (3-axis optional refs) / B (Discriminated enum) / C (Standalone-only V1) | B |
| Q3 | SuccessionRule V1 variants count | A (3 V1 + 1 V1+) / B (4 V1) / C (2 V1 min) | A |
| Q4 | Min reputation gating active V1 | A (V1 active) / B (V1+ deferred) / C (V1 schema-reserved) | C |
| Q5 | Multi-title cap per actor V1 | A (Unlimited) / B (Cap 1) / C (Per-title MultiHoldPolicy) | C |
| Q6 | Heir designation timing/who | A (Forge runtime) / B (Author canonical-only) / C (Both) | C |
| Q7 | Cross-aggregate succession trigger timing | A (Immediate cascade) / B (Day-boundary batch) / C (Forge manual V1) | A |
| Q8 | Title authority — what title GRANTS mechanically | A (FAC role grant) / B (Lex axiom V1+) / C (Both V1) / D (Pure honor + Lex V1+) | A + narrative_hint |
| Q9 | Vacancy semantics | A (PersistsNone) / B (Disabled) / C (Destroyed) / D (Per-title author) | D |
| Q10 | V1+ requires_title Lex axiom timing | A (V1+ active) / B (V1 schema-reserved) / C (V1+ entirely) | B |

**Q-decision philosophy:** V1 minimum scope; schema-additive seams V1; runtime enforcements V1+; per-reality content discipline preserved. Batched 5-Q approach (Q1+Q2 / Q3+Q6+Q7 / Q4+Q10 / Q5+Q8+Q9 — 4 batches OR all-at-once ALL-batch).

---

## §7 — V1 reject rules (`title.*` namespace; anticipated)

| rule_id | Trigger | Vietnamese display |
|---|---|---|
| `title.declared.unknown` | TitleHoldingDecl references title_id not in canonical_titles | "Tước hiệu không xác định" |
| `title.binding.faction_unknown` | TitleDecl.binding = Faction(faction_id) but faction_id not in canonical_factions | "Tước hiệu gắn với tổ chức không tồn tại" |
| `title.binding.dynasty_unknown` | TitleDecl.binding = Dynasty(dynasty_id) but dynasty_id not in canonical_dynasties (FF_001) | "Tước hiệu gắn với gia tộc không tồn tại" |
| `title.holding.actor_unknown` | actor_ref in canonical_title_holdings not in canonical_actors (EF_001) | "Người giữ tước hiệu không xác định" |
| `title.holding.multi_hold_violation` | actor holds >MultiHoldPolicy.max(N) titles after grant | "Vượt quá số tước hiệu được phép giữ" |
| `title.holding.exclusive_violation` | Multiple actors hold Exclusive title concurrently | "Tước hiệu độc tôn đã có người khác giữ" |
| `title.succession.heir_invalid` | Designated heir not in canonical_actors OR dead at succession time | "Người kế thừa không hợp lệ" |

V1+ reservations:
- `title.grant.rep_too_low` — V1+ runtime rep gating (alongside REP-D1)
- `title.grant.progression_tier_too_low` — V1+ progression gating (if Q-decision adds)
- `title.lex_axiom.unknown` — V1+ requires_title axiom validation
- `title.faction_election.invalid_vote` — V1+ FactionElect SuccessionRule
- `title.cross_reality_mismatch` — V2+ Heresy migration

---

## §8 — Reference materials slot

User-provided sources: pending. Reference games surveyed in [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md):
- CK3 (PRIMARY — title hierarchy + 8 succession laws)
- Bannerlord (lord titles separate from clan)
- Game of Thrones / political fantasy (king/regent/heir)
- Wuxia novels (sect-leader 掌门 / emperor 皇帝 / family-head 族长 — primary canon)
- Imperator: Rome (senate titles)
- Stellaris (ruler-traits)
- World of Warcraft (achievement titles)
- Dwarf Fortress (noble succession)
- D&D 5e (noble background features)

---

## §9 — Status

- **Created:** 2026-04-27 by main session
- **Phase:** CONCEPT 2026-04-27 — Phase 0 capture
- **Status target:** Q1-Q10 LOCKED → DRAFT 2/4 commit (~600-800 lines TIT_001_title_foundation.md + boundary updates + catalog seed + WITH `[boundaries-lock-claim]`)
- **Companion docs:**
  - [`_index.md`](_index.md) (folder index)
  - [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) (reference materials)

## §10 — Q-LOCKED matrix (4-batch deep-dive 2026-04-27)

All 10 Qs LOCKED via 4-batch deep-dive 2026-04-27 (zero revisions; all pre-recommendations approved).

| Q | LOCKED decision | Variant | Justification |
|---|---|---|---|
| Q1 | **A — `actor_title_holdings` sparse per-(actor, title_id)** | Edge aggregate | Matches REP_001 / FAC_001 / IDF actor_*_assignment sparse-edge pattern; multi-hold trivial; sparse storage cheap (~3-5 V1) |
| Q2 | **B — Discriminated `enum TitleBinding { Faction(FactionId) / Dynasty(DynastyId) / Standalone }`** | 3-variant enum | Type-safe; impossible invalid combos; matches LoreWeave enum patterns (FactionKind / ReputationTier) |
| Q3 | **A — 3 V1 + 1 V1+** | `Eldest` / `Designated` / `Vacate` V1; `FactionElect` V1+ DIPL_001 dependency | Vacate distinct from VacancySemantic::Disabled (no auto-succession ever); FactionElect needs procedural vote V2+ |
| Q4 | **C — V1 schema-reserved min_reputation_required** | TitleDecl.min_reputation_required: Option<MinRepGate> field exists; validator V1+ alongside REP-D1 runtime delta milestone | Stable schema V1; zero migration to V1+ activation; partial RESOLVES REP-D9 |
| Q5 | **C — Per-title `MultiHoldPolicy`** | Exclusive / StackableUnlimited / StackableMax(N) | Author declares per-title; emperor=Exclusive, generic=StackableUnlimited, CK3-cap=StackableMax(3); default StackableUnlimited |
| Q6 | **C — Both author canonical + Forge admin runtime override** | TitleHoldingDecl.designated_heir field V1 + Forge:DesignateHeir admin sub-shape V1 | Covers canonical-bootstrap + runtime narrative-driven heir change; both wuxia + D&D + modern need both |
| Q7 | **A — Immediate cascade on WA_006 mortality EVT-T3** | Cross-aggregate validator C-rule fires synchronously | Political succession is narrative-critical; matches WA_006 mortality_state + vital_pool cascade pattern; RESOLVES WA_006 sect-leader-death cascade gap |
| Q8 | **A + narrative_hint — FAC role grant V1 + LLM narrative_hint** | TitleAuthorityDecl: `faction_role_grant: Option<FactionRoleGrant>` (V1 active) + `narrative_hint: I18nBundle` (V1 active) + `lex_axiom_unlock_refs: Vec<AxiomDeclRef>` (V1 schema-reserved per Q10) | Wuxia canonical (sect-master IS sect role=master); Standalone titles use narrative_hint only; cross-aggregate effect via 3-write atomic Forge pattern |
| Q9 | **D — Per-title `VacancySemantic`** | PersistsNone / Disabled / Destroyed | Different titles need different semantics; PersistsNone default; Destroyed for fallen empires; Disabled for election offices |
| Q10 | **B — V1 schema-reserved lex_axiom_unlock_refs** | TitleAuthorityDecl.lex_axiom_unlock_refs: Vec<AxiomDeclRef> field exists V1; validator V1+ via WA_001 closure pass adding 5-companion-fields uniformly (race + ideology + faction + reputation + title) | Mirror Q4 schema-reserved pattern; decouples TIT_001 V1 from WA_001 closure pass timing |

**Schema-stable / activation-deferred discipline (Q4 + Q10):** TIT_001 V1 declares all cross-feature gate fields stably; activation happens at consumer feature's milestone (REP-D1 runtime delta + WA_001 closure pass). Zero migration V1 → V1+.

**Per-title author-declared policy discipline (Q5 + Q8 + Q9):** Each TitleDecl carries own MultiHoldPolicy + TitleAuthorityDecl + VacancySemantic. Most flexible V1 design; covers wuxia + D&D + modern + sci-fi reality use cases.
