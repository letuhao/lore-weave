# IDF_005 — Ideology Foundation

> **Conversational name:** "Ideology" (IDL). Tier 5 Actor Substrate Foundation feature owning per-reality `IdeologyId` closed-set + per-actor `actor_ideology_stance: Vec<(IdeologyId, FervorLevel)>` (multi-stance V1 per IDL-Q2 LOCKED — actor may hold multiple ideologies with varying fervor; matches wuxia syncretism Lý Minh holds Đạo + Phật + Nho) + Lex axiom gate hook (`AxiomDecl.requires_ideology`).
>
> **Distinct from IDF_004 Origin:** Origin = **immutable birth-context**; Ideology = **mutable belief stance** (PC can convert; ONLY mutable IDF aggregate).
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** DRAFT 2026-04-26 (Q-decisions IDL-Q1..Q13 locked; IDL-Q13 NEW per POST-SURVEY-Q3 — free V1 conversion; cost V1+ via IDL-D11)
> **Stable IDs:** `IDL-A*` axioms · `IDL-D*` deferrals · `IDL-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types); [WA_001 Lex AxiomDecl](../02_world_authoring/WA_001_lex.md); [IDF_004 default_ideology_refs](IDF_004_origin.md); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** future PCS_001 (PC creation form); NPC_001/`NPC_NNN` (NPC canonical seed); V1+ tenet system (IDL-D1); V1+ sect/order/giáo phái membership (IDL-D2); V1+ ideology-conflict opinion drift (IDL-D3); V1+ conversion cost mechanic (IDL-D11 NEW).
> **Event-model alignment:** Apply/Drop/AdjustFervor events = EVT-T3 Derived. Forge admin = EVT-T8 Administrative. No new EVT-T*.

---

## §1 User story (Wuxia syncretism canonical)

A Wuxia reality bootstraps with 5 ideologies: Đạo / Phật / Nho / pure-martial / animism.

1. **Lý Minh** (PC, Idealist Cultivator from Yến Vũ Lâu) — stance=[(Đạo, Light), (Phật, Light), (Nho, Moderate)]. Wuxia syncretism — multi-stance allowed per IDL-Q2 LOCKED.
2. **Du sĩ** (NPC, scholar) — stance=[(Đạo, Devout)]. Single Daoist devout.
3. **Tiểu Thúy** (NPC, innkeeper daughter) — stance=[]. Atheist via empty Vec per IDL-Q8 LOCKED.
4. **Lão Ngũ** (NPC, innkeeper) — stance=[]. Pragmatic merchant; no ideology.
5. **Hypothetical Buddhist monk** (V1+ NPC) — stance=[(Phật, Devout)]. Strong Buddhist commitment.
6. **Hypothetical Ma đạo cult leader** (V1+ NPC) — stance=[(animism, Zealous), (Đạo, Light)] inverted hierarchy.

**LM01 conversion event** (V1 mutable per IDL-Q11 LOCKED):
- Story-event: Lý Minh experiences Buddhist enlightenment → Apply (Phật, Devout) + Drop (Đạo, Light)
- 2-step Apply/Drop (NOT auto-Drop per IDL-Q3 LOCKED)
- Audit log: Convert reason `Convert { from: Some(ideology_dao) }` per IDL-Q10 LOCKED
- V1 mechanically free (no cost) per **IDL-Q13 LOCKED** (POST-SURVEY-Q3); V1+ cost mechanic IDL-D11

**This feature design specifies:** the closed-set `IdeologyId` per reality declared in `RealityManifest.ideologies`; the per-actor `actor_ideology_stance` aggregate (Vec<IdeologyStanceEntry>); the multi-stance V1 model with FervorLevel 5-level; the Apply/Drop/AdjustFervor events; the V1+ Lex axiom gate hook; the rejection UX with Vietnamese reject copy in `ideology.*` namespace.

After this lock: every actor has deterministic ideology stance (possibly empty); IDF_004 default_ideology_refs seed Light fervor at canonical seed; V1+ WA_001 closure adds AxiomDecl.requires_ideology gate at Stage 4 lex_check.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **IdeologyId** | `pub struct IdeologyId(pub String);` typed newtype | Opaque per-reality. Closed-set declared in RealityManifest. |
| **IdeologyDecl** | Author-declared per-reality entry | display_name (I18nBundle) + parent_ideology_id (V1+ hierarchy schema slot per IDL-Q4 LOCKED) + lex_axiom_tags (Vec<String> for V1+ Lex gate per IDL-Q5 LOCKED) + canon_ref. |
| **FervorLevel** | Closed enum 5-level: `None / Light / Moderate / Devout / Zealous` | Order-comparable per IDL-Q1 LOCKED. None = ideology removed (Drop event); typically NOT stored — removal = absent from Vec. |
| **actor_ideology_stance** | T2 / Reality aggregate; per-(reality, actor_id) row holds `Vec<IdeologyStanceEntry>` | **ONLY mutable IDF aggregate** per IDL-Q11 LOCKED. Apply/Drop/AdjustFervor events. ActorId source = EF_001 §5.1. Synthetic actors forbidden V1 (IDL-Q12 LOCKED). |
| **IdeologyStanceEntry** | `{ ideology_id, fervor, adopted_at_turn, adopted_reason }` | Audit per stance change. |
| **IdeologyChangeReason** | Closed enum: `CanonicalSeed / OriginPackDefault / Convert { from: Option<IdeologyId> } / Abandon { reason: String } / DriftFromOrigin / AdminOverride { reason: String }` | Per IDL-Q10 LOCKED — single Convert with from-Optional handles bidirectional + atheist-to-Daoist case. |

**Cross-feature consumers:**
- WA_001 Lex (V1+ closure) — `AxiomDecl.requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>` axiom-gate at Stage 4 lex_check
- IDF_004 Origin — `actor_origin.default_ideology_refs` seed actor_ideology_stance at canonical seed (Light fervor per IDL-Q9 LOCKED)
- V1+ NPC_002 — ideology-conflict opinion drift (IDL-D3)
- V1+ FAC_001 Faction Foundation — sect/order memberships consume ideology (IDL-D2)

---

## §2.5 Event-model mapping

| Path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Apply ideology stance | **EVT-T3 Derived** | `aggregate_type=actor_ideology_stance`, delta_kind=`ApplyIdeology` | Aggregate-Owner role | Causal-ref REQUIRED |
| Drop ideology stance | **EVT-T3 Derived** | delta_kind=`DropIdeology` | Aggregate-Owner role | Causal-ref REQUIRED |
| AdjustFervor | **EVT-T3 Derived** | delta_kind=`AdjustFervor` | Aggregate-Owner role | Causal-ref REQUIRED |
| Forge admin override | **EVT-T8 Administrative** | `Forge:EditIdeologyStance { actor_id, edit_kind, before, after, reason }` | Forge role (WA_003) | AC-IDL-9 atomicity |

**Closed-set proof:** all paths use active EVT-T* (T3 / T8). No new EVT-T*.

---

## §3 Aggregate inventory

### 3.1 `actor_ideology_stance` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_ideology_stance", tier = "T2", scope = "reality")]
pub struct ActorIdeologyStance {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub stances: Vec<IdeologyStanceEntry>,         // multi-stance V1 per IDL-Q2 LOCKED
    pub last_modified_at_turn: u64,
    pub schema_version: u32,
}

pub struct IdeologyStanceEntry {
    pub ideology_id: IdeologyId,
    pub fervor: FervorLevel,
    pub adopted_at_turn: u64,
    pub adopted_reason: IdeologyChangeReason,
}

pub enum FervorLevel {
    None,        // 0 — ideology removed (Drop event); typically NOT stored
    Light,       // 1 — nominal observance
    Moderate,    // 2 — practiced
    Devout,      // 3 — central to identity
    Zealous,     // 4 — single-minded
}

pub enum IdeologyChangeReason {
    CanonicalSeed,
    OriginPackDefault,
    Convert { from: Option<IdeologyId> },
    Abandon { reason: String },
    DriftFromOrigin,
    AdminOverride { reason: String },
}
```

- T2 + RealityScoped
- One row per `(reality_id, actor_id)`; every actor has stance row (atheist = empty Vec per IDL-Q8 LOCKED) except Synthetic forbidden V1
- **MUTABLE V1** via Apply/Drop/AdjustFervor events with audit (IDL-Q11 LOCKED)
- V1 free conversion per IDL-Q13 LOCKED; cost mechanic IDL-D11 V1+

### 3.2 `IdeologyDecl`

```rust
pub struct IdeologyDecl {
    pub ideology_id: IdeologyId,
    pub display_name: I18nBundle,
    pub parent_ideology_id: Option<IdeologyId>,    // V1+ hierarchy (Mahayana Phật parent = Phật)
    pub lex_axiom_tags: Vec<String>,               // V1+ Lex gate
    pub canon_ref: Option<GlossaryEntityId>,
}
```

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `actor_ideology_stance` | T2 | T2 | Reality | ~0.5-1 per turn (Lex gate V1+ + UI badge + V1+ opinion drift) | ~0.01 per turn (Apply/Drop/AdjustFervor — rare conversion events) | Per-actor across reality lifetime; mutable but rare. |

---

## §5 DP primitives

### 5.1 Reads
- `dp::read_projection_reality::<ActorIdeologyStance>(ctx, actor_id)` — Lex gate + UI + V1+ drift

### 5.2 Writes
- `dp::t2_write::<ActorIdeologyStance>(ctx, actor_id, ApplyIdeologyDelta { ideology_id, fervor, reason })` — Apply
- `dp::t2_write::<ActorIdeologyStance>(ctx, actor_id, DropIdeologyDelta { ideology_id, reason })` — Drop
- `dp::t2_write::<ActorIdeologyStance>(ctx, actor_id, AdjustFervorDelta { ideology_id, new_fervor })` — adjust

### 5.3 Subscriptions
- UI invalidation via DP-X

### 5.4 Capability
- `produce: [Derived]` + `write: actor_ideology_stance @ T2 @ reality`
- `produce: [Administrative]` + sub-shape `Forge:EditIdeologyStance`

---

## §6 Capability requirements

Standard pattern (matches IDF_001-004).

---

## §7 Subscribe pattern

UI invalidation via DP-X. NPC_002 reads at SceneRoster build.

---

## §8 Pattern choices

### 8.1 5-level FervorLevel V1 (IDL-Q1 LOCKED)
None enables explicit drop semantic; Light enables nominal observance.

### 8.2 Multi-stance V1 (IDL-Q2 LOCKED)
Wuxia syncretism is reality requirement (Lý Minh holds Đạo + Phật + Nho — verified by classic wuxia novels). Single-stance forces Modern-bias.

### 8.3 Apply/Drop/AdjustFervor V1 (IDL-Q3 LOCKED)
Granular events enable audit history. Replace = V1+ shorthand.

### 8.4 parent_ideology_id schema slot V1 (IDL-Q4 LOCKED)
Mahayana/Zen/Theravada V1+ split likely needed; schema slot avoids migration.

### 8.5 lex_axiom_tags string list V1 (IDL-Q5 LOCKED)
Same as IDF_001 RAC-Q5; tags evolve with WA_001.

### 8.6 RealityManifest `ideologies` REQUIRED V1 (IDL-Q6 LOCKED)
Every reality has belief landscape (atheist-only is still declared landscape).

### 8.7 No conflict checking V1 (IDL-Q7 LOCKED)
Actors freely hold syncretic ideologies; conflict checking V1+ enrichment.

### 8.8 Atheist = empty Vec V1 (IDL-Q8 LOCKED)
Atheist = absence; explicit entry forces tautology.

### 8.9 Auto-seed Light fervor V1 (IDL-Q9 LOCKED)
Frictionless default from IDF_004.default_ideology_refs; canonical seed override always available.

### 8.10 Single Convert with from-Optional (IDL-Q10 LOCKED)
Conversions are bidirectional; Optional From handles atheist-to-Daoist case.

### 8.11 Mutable V1 Apply/Drop (IDL-Q11 LOCKED)
**ONLY mutable IDF aggregate.** Reflects reality where conversion happens.

### 8.12 Synthetic actor forbidden V1 (IDL-Q12 LOCKED)
Matches IDF_001/003/004.

### 8.13 Free V1 conversion (IDL-Q13 LOCKED per POST-SURVEY-Q3)
**No cost / no opinion penalty / no time-period V1.** Conversion mechanically free V1; narrative weight via story-events. Cost mechanic IDL-D11 V1+ (when scheduler ships V1+30d OR IDL-D3 ideology-conflict modifier ships, whichever first).

DRAFT documents: "V1 conversion is mechanically free; authors writing V1 content should treat conversions as plot points (story-weight) but expect mechanical free-form V1."

---

## §9 Failure-mode UX

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `ideology.unknown_ideology_id` | 0 schema | IdeologyId not in RealityManifest.ideologies | "Tư tưởng không tồn tại trong thế giới này." |
| `ideology.duplicate_stance_entry` | 0 schema | Apply with IdeologyId already in stances (must use AdjustFervor) | "Tư tưởng đã được giữ; dùng AdjustFervor để thay đổi mức độ." |
| `ideology.lex_axiom_forbidden` | **Stage 4 lex_check** (V1+) | Axiom requires_ideology unmet | (Lex-derived) — V1+ first axiom |
| `ideology.invalid_fervor_transition` | 7 world-rule (V1+) | (V1+ fervor drift rules) | (V1+ — V1 free transition) |

**`ideology.*` V1 rule_id enumeration** (3 V1 rules):

1. `ideology.unknown_ideology_id` — Stage 0
2. `ideology.duplicate_stance_entry` — Stage 0
3. `ideology.lex_axiom_forbidden` — Stage 4 (V1+ active; V1 reserved)

V1+ reservations: `ideology.tenet_violation` (V1+ tenet system IDL-D1); `ideology.sect_membership_required` (V1+ FAC_001); `ideology.conflict_auto_drop_required` (V1+ conflict checking); `ideology.invalid_fervor_transition` (V1+ fervor drift); `ideology.conversion_cost_unmet` (V1+ IDL-D11 cost mechanic).

---

## §10 Cross-service handoff

```
1. Canonical seed: IDF_004 owner-service emits actor_origin.default_ideology_refs;
   IDF_005 owner-service consumes and auto-creates Light fervor stances per IDL-Q9.

2. PC conversion (V1 free):
   PC LM01 enlightenment story-event:
   a. dp::t2_write::<ActorIdeologyStance>(ctx, LM01, ApplyIdeologyDelta {
        ideology_id: ideology_phat, fervor: Devout,
        reason: Convert { from: Some(ideology_dao) }
      }) → T1 Derived
   b. dp::t2_write::<ActorIdeologyStance>(ctx, LM01, DropIdeologyDelta {
        ideology_id: ideology_dao, reason: Abandon { reason: "Buddhist enlightenment" }
      }) → T2 Derived
   c. UI re-renders ideology badges

3. V1+ Lex axiom gate at Stage 4:
   AxiomDecl matched: { axiom_id: "qigong", requires_ideology: Some([(ideology_dao, Moderate)]) }
   a. Read actor_ideology_stance(LM01)
   b. Check stance entry exists with fervor ≥ Moderate for ideology_dao
   c. ✓ allow OR ✗ reject `ideology.lex_axiom_forbidden`
```

---

## §11 Sequence: Canonical seed (Wuxia syncretism)

```
For each canonical actor:
  Read IDF_004 actor_origin.default_ideology_refs:
    LM01: [ideology_dao, ideology_phat, ideology_nho]
  Auto-create stances at Light fervor per IDL-Q9 LOCKED:
    actor_ideology_stance.stances = [
      (ideology_dao, Light, AssignedReason::OriginPackDefault),
      (ideology_phat, Light, AssignedReason::OriginPackDefault),
      (ideology_nho, Light, AssignedReason::OriginPackDefault),
    ]
  Canonical seed override (from canonical actor declaration):
    LM01.stances[ideology_nho].fervor = Moderate (Confucian-leaning)
  
  → T1 Derived AdjustFervor (causal_refs to canonical seed event)
```

---

## §12 Sequence: Conversion (V1 free)

```
PC LM01 has Buddhist enlightenment story-event (V1 free per IDL-Q13):

Apply (ideology_phat, Devout):
  dp::t2_write::<ActorIdeologyStance>(ctx, LM01, ApplyIdeologyDelta {
    ideology_id: ideology_phat,
    fervor: Devout,
    reason: Convert { from: Some(ideology_dao) }
  }) → T1
  
  Stage 0 schema: ideology_phat exists in RealityManifest.ideologies ✓
                  ideology_phat NOT in current stances ✓ (no duplicate_stance_entry)
  
  Stages 1-9: pass
  
  Result: stances now [(ideology_dao, Light), (ideology_phat, Devout), (ideology_nho, Moderate)]

Drop (ideology_dao):
  dp::t2_write::<ActorIdeologyStance>(ctx, LM01, DropIdeologyDelta {
    ideology_id: ideology_dao,
    reason: Abandon { reason: "Buddhist enlightenment" }
  }) → T2
  
  Result: stances now [(ideology_phat, Devout), (ideology_nho, Moderate)]

UI badges: Đạo removed; Phật added with Devout fervor; Nho unchanged.

V1 NO opinion penalty / NO time-period delay (free conversion).
V1+ IDL-D11 cost mechanic when scheduler ships V1+30d.
```

---

## §13 Sequence: V1+ Lex axiom gate

```
PC LM01 attempts Use spell scroll @ Stage 4 lex_check (V1+):

  AxiomDecl matched: { axiom_id: "qigong_minor_healing",
                       requires_ideology: Some([(ideology_dao, Moderate)]) }
  
  a. dp::read_projection_reality::<ActorIdeologyStance>(ctx, LM01)
     → stances includes (ideology_dao, Light)  [hypothetical]
  b. Check fervor ≥ Moderate → Light < Moderate ✗
  c. REJECT with `ideology.lex_axiom_forbidden`
  
Vietnamese reject: "Đạo Light không đủ; cần Đạo Moderate trở lên."
```

---

## §14 Sequence: Forge admin override

```
Admin marks LM01 as fervent Daoist (story-event reveals true convictions):
  EVT-T8 Administrative: Forge:EditIdeologyStance {
    actor_id: LM01,
    edit_kind: AdjustFervor,
    before: (ideology_dao, Light),
    after: (ideology_dao, Devout),
    reason: "Story-event reveals concealed devout Daoist"
  }
  3-write atomic: actor_ideology_stance + EVT-T8 + forge_audit_log
```

---

## §15 Acceptance criteria

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-IDL-1** | LM01 canonical seed [(Đạo, Light), (Phật, Light), (Nho, Moderate)] | row committed; UI 3 badges with fervor |
| **AC-IDL-2** | Du sĩ canonical seed [(Đạo, Devout)] | row committed; single high-fervor badge |
| **AC-IDL-3** | Lão Ngũ canonical seed [] (atheist via empty Vec) | row committed; no badges |
| **AC-IDL-4** | LM01 converts to Buddhism: Apply (Phật, Devout) + Drop (Đạo, Light) — V1 free | both events commit; stances updated; audit shows Convert reason |
| **AC-IDL-5** | LM01 attempts Apply (Đạo, Light) when already in stances | rejected `ideology.duplicate_stance_entry` |
| **AC-IDL-6** | Reject `ideology.unknown_ideology_id` | Stage 0 reject |
| **AC-IDL-7** | (V1+) Lex axiom requires_ideology=[(Đạo, Moderate)]; LM01 Đạo Light → reject | V1+ rejected `ideology.lex_axiom_forbidden` |
| **AC-IDL-8** | I18nBundle resolves Đạo / Daoism / 道教 | display_name correctly localized |
| **AC-IDL-9** | IDF_004 default_ideology_refs auto-seed Light fervor at canonical seed | post-bootstrap LM01 has all 3 stances Light fervor before canonical override |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-IDL-V1+1** | Conversion cost mechanic — Apply (Phật, Devout) requires piety + opinion penalty + 6-month period | V1+ IDL-D11 (when scheduler V1+30d ships OR IDL-D3 ships) |
| **AC-IDL-V1+2** | Tenet system — Strike on innocent triggers Buddhist tenet violation | V1+ IDL-D1 |

### 15.3 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-IDL-10** | Forge admin override LM01.stances | EVT-T8 audit emitted; 3-write atomic |

### 15.4 Status transition

- DRAFT → CANDIDATE-LOCK: boundary registered.
- CANDIDATE-LOCK → LOCK: all AC-IDL-1..10 V1-testable scenarios pass.

---

## §16 Boundary registrations

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `actor_ideology_stance` aggregate (T2/Reality, IDF_005 DRAFT — **ONLY mutable IDF aggregate V1**)
   - EVT-T8: NEW `Forge:EditIdeologyStance` (IDF_005 owns)
   - Stable-ID prefix: NEW `IDL-*` row
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 `ideology.*` namespace: 3 V1 rule_ids + 5 V1+ reservations
   - §2 RealityManifest: NEW `ideologies: Vec<IdeologyDecl>` REQUIRED V1
3. `_boundaries/99_changelog.md`: append IDF folder 13/15 entry

---

## §17 Deferrals

| ID | Item | Defer to |
|---|---|---|
| **IDL-D1** | Tenet system (each ideology declares behavioral tenets — "không sát sinh" Buddhist; gating Strike actions) | V1+ first reality with tenet content |
| **IDL-D2** | Sect / order / giáo phái membership (faction system) | **V1+ FAC_001 Faction Foundation** (post-IDF + FF_001 priority) |
| **IDL-D3** | Ideology-conflict opinion drift (Buddhist + butcher = -opinion) | V1+ NPC personality enrichment |
| **IDL-D4** | Missionary / proselytize mechanic | V2+ |
| **IDL-D5** | Ideology evolution (Đạo → Phật conversion path with story-events) | V1+ scheduler V1+30d + faction system |
| **IDL-D6** | Hierarchical ideology (Mahayana / Theravada / Zen Phật) via parent_ideology_id | V1+ when first reality needs split |
| **IDL-D7** | Conflict auto-Drop (apply Đạo Devout auto-drops conflicting `ideology_atheist`) | V1+ when conflict rules formalized |
| **IDL-D8** | Cross-reality ideology mapping | V2+ Heresy migration |
| **IDL-D9** | Per-tenet violation event flow | V1+ tenet system |
| **IDL-D10** | Fervor drift over time (slow drift Devout → Moderate from inactivity) | V1+ scheduler V1+30d |
| **IDL-D11** (Phase 0 survey — POST-SURVEY-Q3) | Conversion cost mechanic — CK3-style piety cost + opinion penalty + 6-month period for ideology conversions; soft-cost variants (opinion-only without time period) also deferred | V1+ when EITHER (a) V1+30d scheduler service ships (enables time-period delay) OR (b) IDL-D3 ideology-conflict opinion modifier ships (enables opinion penalty), whichever first. V1 mechanically free per IDL-Q13. |

---

## §18 Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md)

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race.md) — race + ideology jointly gate Lex axioms (V1+ companion fields)
- [`IDF_002 Language`](IDF_002_language.md) — independent V1
- [`IDF_003 Personality`](IDF_003_personality.md) — Pious archetype + Daoist ideology jointly affect NPC reactions (V1+ enrichment)
- [`IDF_004 Origin`](IDF_004_origin.md) — default_ideology_refs seed at canonical seed

**Consumers:**
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — V1+ closure: AxiomDecl.requires_ideology field
- Future PCS_001 — PC creation form
- NPC_001/`NPC_NNN` — NPC canonical seed
- V1+ NPC_002 — ideology-conflict drift (IDL-D3)
- **V1+ FAC_001 Faction Foundation — sect/order memberships consume ideology** (IDL-D2; HIGH priority post-IDF closure)

---

## §19 Implementation readiness checklist

Complete per EF_001 pattern. 10 V1-testable AC + 2 V1+ deferred. 11 deferrals (IDL-D1..D11).

**V1 special note (the ONLY mutable IDF aggregate):**

Among 5 IDF features:
- IDF_001 Race — immutable V1
- IDF_002 Language — mostly immutable V1 (V1+ learning)
- IDF_003 Personality — immutable V1
- IDF_004 Origin — immutable V1
- **IDF_005 Ideology — MUTABLE V1** via Apply/Drop/AdjustFervor events

Reflects reality: ideology is personal lifecycle property (PC can convert); race/origin/personality are typically birth-fixed.

**Status transition:** DRAFT 2026-04-26 → CANDIDATE-LOCK after Phase 3 + closure pass → LOCK after AC-IDL-1..10 pass.
