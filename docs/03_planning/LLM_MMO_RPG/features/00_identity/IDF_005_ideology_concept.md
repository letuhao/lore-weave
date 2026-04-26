# IDF_005 — Ideology Foundation (CONCEPT)

> **Conversational name:** "Ideology" (IDL). Tier 5 Actor Substrate Foundation feature owning per-reality `IdeologyId` closed-set enum (in-fiction belief systems — Đạo / Phật / Nho / pure-martial / animism / atheist / etc.) + per-actor `actor_ideology_stance: Vec<(IdeologyId, FervorLevel)>` (multi-stance V1 — actor may hold multiple ideologies with varying fervor) + Lex axiom gate hook (`AxiomDecl.requires_ideology` field).
>
> **Distinct from IDF_004 Origin:** Origin is **immutable birth-context**; Ideology is **mutable belief stance** (PC can convert; NPC's stance evolves per story events).
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CONCEPT 2026-04-26
> **Stable IDs:** `IDL-A*` axioms · `IDL-D*` deferrals · `IDL-Q*` open questions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md); [WA_001 Lex AxiomDecl](../02_world_authoring/WA_001_lex.md) (ideology gate at Stage 4); [IDF_004 Origin default_ideology_refs](IDF_004_origin_concept.md) (suggestion ref); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** PCS_001 (PC creation form); NPC_001/003 (NPC canonical seed ideology); V1+ tenet system (ideology declares behavioral tenets); V1+ sect/order/giáo phái membership (faction system); V1+ ideology-conflict opinion drift; V2+ missionary mechanic.

---

## §1 Concept summary

Every actor (PC + NPC) has an **ideology stance** — possibly empty (atheist actor), possibly multi-stance (Wuxia world common: actor holds Đạo + Phật + Nho with varying fervor). Ideology gates Lex axioms (Daoist may cultivate qigong; Buddhist-monk gate "không sát sinh"; Confucian gate "lễ với cấp trên"). Mutable lifecycle — convert events / fervor drift / abandonment supported V1+.

**V1 must-ship:**
- Closed-set `IdeologyId` per reality (3-7 ideologies typical; reality-specific)
- Per-actor `actor_ideology_stance` aggregate (T2/Reality scope) holding `Vec<(IdeologyId, FervorLevel)>`
- Multi-stance V1 (actor may hold multiple ideologies simultaneously)
- `IdeologyDecl` declarative metadata: display_name (I18nBundle) + parent_ideology_id (V1+ hierarchy) + canon_ref + lex_axiom_tags
- Lex axiom gate hook: `AxiomDecl.requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>` (V1+ at WA_001 closure pass)
- Convert event audit log (V1 Apply / Drop ideology changes record audit)
- RealityManifest extension `ideologies: Vec<IdeologyDecl>` REQUIRED V1
- Reality presets:
  - **Wuxia/Tiên Hiệp** (5 ideologies): Đạo (Daoism) / Phật (Buddhism) / Nho (Confucianism) / pure-martial (võ-only, no spiritual) / animism (folk spirits) / atheist (none — the empty Vec)
  - **Modern** (3): secular_humanism / theist (generic) / atheist
  - **Sci-fi** (3): post_religious / corporate_ethics / cosmic_nihilism

**V1+ deferred:**
- Tenet system (ideology declares behavioral tenets gating actions) (IDL-D1)
- Sect / order / giáo phái membership (faction system) (IDL-D2)
- Ideology-conflict opinion drift (Buddhist + butcher = -opinion) (IDL-D3)
- Missionary / proselytize mechanic (V2+)
- Ideology evolution (Đạo → Phật conversion path) (V1+)
- Hierarchical ideology (Mahayana Phật vs Theravada Phật vs Zen Phật) (V1+ via parent_ideology_id)

---

## §2 Domain concepts (proposed)

| Concept | Maps to | Notes |
|---|---|---|
| **IdeologyId** | Stable-ID newtype `String` (e.g., `ideology_dao`, `ideology_phat`, `ideology_atheist`) | Opaque per-reality. Closed-set declared in RealityManifest. |
| **IdeologyDecl** | Author-declared per-reality entry | display_name (I18nBundle) + parent_ideology_id (V1+ hierarchy) + lex_axiom_tags (Vec<String> for V1+ Lex gate) + canon_ref. |
| **FervorLevel** | Closed enum 5-level: `None / Light / Moderate / Devout / Zealous` | Order-comparable. Light = nominal observance; Moderate = practiced; Devout = central to identity; Zealous = single-minded. None = ideology removed (Drop event). |
| **actor_ideology_stance** | T2 / Reality aggregate; per-(reality, actor_id) row holds `Vec<(IdeologyId, FervorLevel)>` | Generic for PC + NPC. V1 multi-stance allowed; mutable via Apply/Drop/AdjustFervor events. |
| **IdeologyChangeReason** | Closed enum: `CanonicalSeed / OriginPackDefault / Convert / Abandon / DriftFromOrigin / AdminOverride` | Audit log reason for stance change. |

**Cross-feature consumers:**
- WA_001 Lex (V1+ closure) — `requires_ideology` axiom gate at Stage 4 lex_check
- IDF_004 Origin — origin pack proposes default ideology refs at canonical seed (per ORG-Q5)
- NPC_002 §6 priority + opinion drift (V1+) — ideology-conflict modifier (IDL-D3)
- V1+ faction system — sect/order membership constraints
- PCS_001 (V1+) — PC creation form selects initial stance

---

## §3 Aggregate inventory (proposed)

### 3.1 `actor_ideology_stance` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_ideology_stance", tier = "T2", scope = "reality")]
pub struct ActorIdeologyStance {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub stances: Vec<IdeologyStanceEntry>,         // multi-stance V1
    pub last_modified_at_turn: u64,
    pub schema_version: u32,
}

pub struct IdeologyStanceEntry {
    pub ideology_id: IdeologyId,
    pub fervor: FervorLevel,
    pub adopted_at_turn: u64,                      // when this stance was adopted
    pub adopted_reason: IdeologyChangeReason,
}

pub enum FervorLevel {
    None,        // ideology removed (Drop event); typically NOT stored — removal = absent from Vec
    Light,       // nominal observance
    Moderate,    // practiced
    Devout,      // central to identity
    Zealous,     // single-minded
}

pub enum IdeologyChangeReason {
    CanonicalSeed,                          // RealityBootstrapper
    OriginPackDefault,                      // IDF_004 default_ideology_refs seeded
    Convert { from: Option<IdeologyId> },   // PC/NPC story conversion
    Abandon { reason: String },             // dropped a previously-held ideology
    DriftFromOrigin,                        // V1+ slow drift events
    AdminOverride { reason: String },       // Admin force-edited
}
```

- T2 + RealityScoped
- One row per `(reality_id, actor_id)` (every actor MUST have stance row, even if `stances: vec![]` for atheist)
- V1 mutable via Apply/Drop/AdjustFervor events with audit

### 3.2 `IdeologyDecl`

```rust
pub struct IdeologyDecl {
    pub ideology_id: IdeologyId,
    pub display_name: I18nBundle,
    pub parent_ideology_id: Option<IdeologyId>,    // V1+ hierarchy (Mahayana Phật parent = Phật)
    pub lex_axiom_tags: Vec<String>,               // V1+ Lex gate (e.g., ["qigong", "spirit_sense"] for Đạo)
    pub canon_ref: Option<GlossaryEntityId>,
}
```

---

## §4 Tier+scope (DP-R2 — proposed)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `actor_ideology_stance` | T2 | T2 | Reality | ~0.5-1 per turn (Lex gate at Stage 4 + UI badge + V1+ opinion drift) | ~0.01 per turn (Apply/Drop/AdjustFervor — rare conversion events) | Per-actor across reality lifetime; eventual consistency OK; mutable but rare. |

---

## §5 Cross-feature integration (proposed)

### 5.1 Lex axiom gate (V1+ at WA_001 closure)

`AxiomDecl` extended with `requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>` (companion to `requires_race` from IDF_001). When set, Stage 4 lex_check reads agent's `actor_ideology_stance` and rejects if no stance entry meets the requirement (matching IdeologyId AND fervor ≥ specified).

```rust
// WA_001 extension (proposed; lock-claim required at WA_001 closure pass for V1+ ideology gate)
pub struct AxiomDecl {
    // ... existing fields ...
    pub requires_race: Option<Vec<RaceId>>,                          // IDF_001 V1+
    pub requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>,   // IDF_005 V1+ (this feature)
}
```

V1 schema: optional fields present but V1 always None (no ideology-gated axioms shipped V1). V1+ first ideology-gated axiom (e.g., qigong restricted to Đạo Devout-or-higher) demonstrates the gate.

### 5.2 Origin default seeding (per IDF_004 ORG-Q5)

At canonical seed (RealityBootstrapper or PC creation), if `actor_origin.default_ideology_refs` is non-empty, `actor_ideology_stance.stances` initialized with each `IdeologyId` at default fervor (V1 = Light). Per-actor canonical seed may override.

V1: Light fervor default at origin seed; canonical seed may set explicit Moderate/Devout/Zealous.

### 5.3 Multi-stance semantics

V1 supports multi-stance — Wuxia common: Lý Minh stance = [(Đạo, Light), (Phật, Light), (Nho, Moderate)] (Confucian-leaning Daoist with mild Buddhist sympathy). Lex axiom `requires_ideology=[(Đạo, Moderate)]` would REJECT (LM01's Đạo fervor = Light, not Moderate).

Conflict: if reality has explicitly conflicting ideologies (V1+ feature), Apply/Drop events may auto-Drop conflicting stances. V1: NO conflict checking — actors freely hold contradictory ideologies (matching real-world syncretism).

### 5.4 Convert event flow

```rust
// User flow: PC LM01 converts from primarily Đạo to primarily Phật
1. UI / Forge admin issues Apply Ideology event:
   ApplyIdeology { ideology_id: ideology_phat, fervor: Devout, reason: Convert { from: Some(ideology_dao) } }
2. world-service emits Derived event on actor_ideology_stance:
   - Adds (ideology_phat, Devout) to stances
   - Optionally Drops (ideology_dao, Devout) → if `from: Some(...)` AND user wants exclusive switch, also Drop the old. V1: Apply does NOT auto-Drop; explicit Drop event needed.
3. Audit log: change reason recorded
4. V1+ Chorus Generator: NPC reactions to PC's conversion (V1+ butterfly cascade per PL_005c §5)
```

V1: Apply / Drop / AdjustFervor are 3 OutputDecl delta_kinds for actor_ideology_stance.

### 5.5 Reject UX (ideology.* namespace — proposed V1)

| rule_id | Stage | When |
|---|---|---|
| `ideology.unknown_ideology_id` | 0 schema | IdeologyId not in RealityManifest.ideologies |
| `ideology.lex_axiom_forbidden` | 4 lex_check (V1+) | Axiom requires_ideology unmet by actor's stance — V1+ first when ideology-gated axiom ships |
| `ideology.invalid_fervor_transition` | 7 world-rule | (V1+ — when fervor drift rules ship); V1 free transition |
| `ideology.duplicate_stance_entry` | 0 schema | Apply with IdeologyId already in stances (must use AdjustFervor instead) |

V1+ reservations: `ideology.tenet_violation` (V1+ tenet system); `ideology.sect_membership_required` (V1+ faction); `ideology.conflict_auto_drop_required` (V1+ conflict checking).

---

## §6 RealityManifest extension (proposed)

```rust
pub struct RealityManifest {
    // ... existing fields ...
    pub ideologies: Vec<IdeologyDecl>,    // NEW V1 from IDF_005
}
```

REQUIRED V1.

**Example RealityManifest excerpt (Wuxia preset):**

```rust
ideologies: vec![
    IdeologyDecl {
        ideology_id: "ideology_dao".to_string(),
        display_name: I18nBundle {
            default: "Daoism".to_string(),
            translations: HashMap::from([("vi", "Đạo"), ("zh", "道教")]),
        },
        parent_ideology_id: None,
        lex_axiom_tags: vec!["qigong".to_string(), "spirit_sense".to_string()],
        canon_ref: None,
    },
    IdeologyDecl {
        ideology_id: "ideology_phat".to_string(),
        display_name: I18nBundle {
            default: "Buddhism".to_string(),
            translations: HashMap::from([("vi", "Phật"), ("zh", "佛教")]),
        },
        parent_ideology_id: None,
        lex_axiom_tags: vec!["mind_body_cultivation".to_string()],
        canon_ref: None,
    },
    IdeologyDecl {
        ideology_id: "ideology_nho".to_string(),
        display_name: I18nBundle {
            default: "Confucianism".to_string(),
            translations: HashMap::from([("vi", "Nho"), ("zh", "儒家")]),
        },
        parent_ideology_id: None,
        lex_axiom_tags: vec![],   // Confucian = ethical not magical V1; V1+ may add tenet system
        canon_ref: None,
    },
    // ... 2 more (pure_martial, animism)
]
```

---

## §7 V1 acceptance criteria (preliminary)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-IDL-1** | Reality declares Wuxia 5-ideology preset; LM01 created at canonical seed with stance=[(Đạo, Light), (Phật, Light), (Nho, Moderate)] | actor_ideology_stance row committed; UI displays 3 badges with fervor levels |
| **AC-IDL-2** | NPC Du sĩ declared with stance=[(Đạo, Devout)] (single ideology at high fervor) | row committed |
| **AC-IDL-3** | NPC Lão Ngũ declared with stance=[] (atheist / pragmatic merchant) | row committed; empty stances Vec valid |
| **AC-IDL-4** | LM01 converts to Buddhism: Apply (Phật, Devout) + Drop (Đạo, Light) two-step | both events commit; stances now [(Phật, Devout), (Phật additional? no), (Nho, Moderate)] — Đạo entry dropped; audit log shows Convert {from: Some(ideology_dao)} reason |
| **AC-IDL-5** | LM01 attempts Apply (Đạo, Light) when already in stances | rejected with `ideology.duplicate_stance_entry` (must use AdjustFervor instead) |
| **AC-IDL-6** | Reject `ideology.unknown_ideology_id` when stance references unknown ID | rejected at Stage 0 |
| **AC-IDL-7** | (V1+) Lex axiom requires_ideology=[(Đạo, Moderate)]; LM01's stance has Đạo Light → rejected with `ideology.lex_axiom_forbidden` at Stage 4 | (V1+ acceptance — V1 ships gate stub but no axioms use it yet) |
| **AC-IDL-8** | I18nBundle resolves Đạo (Vietnamese) / Daoism (English) | display_name correctly localized |
| **AC-IDL-9** | IDF_004 default_ideology_refs=[ideology_dao] auto-seeds new actor with stance=[(ideology_dao, Light)] at canonical seed | post-bootstrap actor has Light fervor Đạo |

---

## §8 Open questions (CONCEPT — user confirm before DRAFT)

| ID | Question | Default proposal |
|---|---|---|
| **IDL-Q1** | FervorLevel — 5-level (current None/Light/Moderate/Devout/Zealous) vs 4-level (drop None/Light)? | **5-level V1** — None enables explicit "drop" semantic; Light enables nominal observance |
| **IDL-Q2** | Multi-stance V1 (current) vs single-stance V1 (one ideology per actor)? | **Multi-stance V1** — Wuxia syncretism is reality requirement (Lý Minh holds Đạo + Phật + Nho); single-stance forces Modern-bias |
| **IDL-Q3** | Stance change events V1 — Apply/Drop/AdjustFervor (current) vs single Replace event? | **Apply/Drop/AdjustFervor V1** — granular events enable audit history (when did LM01 abandon Đạo?); Replace is V1+ shorthand |
| **IDL-Q4** | parent_ideology_id hierarchy V1 — schema slot (current) vs defer V1+ entirely? | **Schema slot V1** — Mahayana/Zen/Theravada split likely needed within Wuxia 'Phật' V1+; schema slot avoids migration |
| **IDL-Q5** | lex_axiom_tags — list of strings (current) vs typed enum? | **List of strings V1** — same as IDF_001 RAC-Q5; tags evolve with WA_001 |
| **IDL-Q6** | RealityManifest `ideologies` REQUIRED V1 vs OPTIONAL with default empty? | **REQUIRED V1** — every reality has belief landscape (atheist-only is still a declared landscape) |
| **IDL-Q7** | Conflict checking V1 (auto-Drop conflicting ideologies) vs no conflict V1? | **No conflict V1** — actors freely hold syncretic ideologies; conflict checking V1+ enrichment |
| **IDL-Q8** | Atheist representation — empty Vec (current) vs explicit "ideology_atheist" entry? | **Empty Vec V1** — atheist = absence; explicit entry forces tautology. (Reality may still declare ideology_atheist for Modern reality if explicit treatment desired.) |
| **IDL-Q9** | Origin default seeding V1 — auto-seed Light fervor (current) vs no seeding (origin advisory only)? | **Auto-seed Light fervor V1** — frictionless default; canonical seed override always available |
| **IDL-Q10** | Convert reason from-tracking — `Convert { from: Option<IdeologyId> }` (current) vs separate event types Convert vs ColdAdoption? | **Single Convert with from-Optional V1** — conversions are bidirectional (could be from nothing); Optional From handles atheist-to-Daoist case |
| **IDL-Q11** | Mutation of actor_ideology_stance V1 — allowed (current per Apply/Drop) vs immutable like other IDF? | **Mutable V1 per Apply/Drop** — only IDF feature with mutability V1 because ideology IS lifecycle-mutable; matches reality where conversion happens |
| **IDL-Q12** | Synthetic actor ideology — required (Synthetic-default empty) vs forbidden? | **Forbidden V1** — Synthetic actors have no beliefs (matches IDF_003 PRS-Q11 + IDF_004 ORG-Q7) |

---

## §9 Deferrals (V1+ landing point)

| ID | Item | Defer to |
|---|---|---|
| **IDL-D1** | Tenet system (each ideology declares behavioral tenets — "không sát sinh" Buddhist; gating Strike actions) | V1+ when first reality with tenet content ships |
| **IDL-D2** | Sect / order / giáo phái membership (faction system) | V1+ Faction Foundation feature (separate from IDF) |
| **IDL-D3** | Ideology-conflict opinion drift (Buddhist + butcher = -opinion baseline) | V1+ NPC personality enrichment |
| **IDL-D4** | Missionary / proselytize mechanic | V2+ |
| **IDL-D5** | Ideology evolution (Đạo → Phật conversion path with story-events) | V1+ scheduler V1+30d + faction system |
| **IDL-D6** | Hierarchical ideology (Mahayana / Theravada / Zen Phật) via parent_ideology_id | V1+ when first reality needs split |
| **IDL-D7** | Conflict auto-Drop (apply Đạo Devout auto-drops conflicting `ideology_atheist`) | V1+ when conflict rules formalized |
| **IDL-D8** | Cross-reality ideology mapping (Wuxia Đạo ≠ Modern Daoism conceptually) | V2+ Heresy migration |
| **IDL-D9** | Per-tenet violation event flow (NPC sees PC violate Buddhist tenet → -opinion drift) | V1+ tenet system |
| **IDL-D10** | Fervor drift over time (slow drift Devout → Moderate from inactivity) | V1+ scheduler V1+30d |

---

## §10 Cross-references

**Foundation tier:**
- [`EF_001`](../00_entity/EF_001_entity_foundation.md) §5.1 — ActorId
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) §2.3 — I18nBundle

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race_concept.md) — race + ideology jointly gate Lex axioms (V1+); requires_race + requires_ideology are companion fields
- [`IDF_002 Language`](IDF_002_language_concept.md) — independent V1
- [`IDF_003 Personality`](IDF_003_personality_concept.md) — Pious archetype + Daoist/Buddhist ideology jointly affect NPC reactions (V1+ enrichment)
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — default_ideology_refs seed at canonical seed (per ORG-Q5)

**Consumers:**
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — V1+ closure: AxiomDecl.requires_ideology field
- Future PCS_001 — PC creation form
- NPC_001/003 — NPC canonical seed
- V1+ NPC_002 — ideology-conflict drift (IDL-D3)
- V1+ Faction Foundation — sect/order memberships consume ideology

**Boundaries (DRAFT registers):**
- `_boundaries/01_feature_ownership_matrix.md` — `actor_ideology_stance` aggregate
- `_boundaries/02_extension_contracts.md` §1.4 — `ideology.*` namespace (3 V1 rules + 3 V1+ reservations)
- `_boundaries/02_extension_contracts.md` §2 RealityManifest — `ideologies` extension

---

## §11 CONCEPT → DRAFT promotion checklist

Same pattern as IDF_001/002/003/004. Boundary registrations: `actor_ideology_stance` aggregate; `ideology.*` namespace (3 V1 rules); `ideologies: Vec<IdeologyDecl>` RealityManifest extension; Stable-ID prefix `IDL-*`.

**Cross-feature touch on DRAFT:**
- WA_001 closure pass FUTURE — `AxiomDecl.requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>` field added (V1 always None; V1+ axioms use)
- IDF_004 closure cross-ref `default_ideology_refs` seeding contract

**V1 special note (the ONLY mutable IDF aggregate):**

Among the 5 IDF features:
- IDF_001 Race — immutable V1
- IDF_002 Language — mostly immutable V1 (V1+ learning Apply)
- IDF_003 Personality — immutable V1
- IDF_004 Origin — immutable V1
- **IDF_005 Ideology — MUTABLE V1** via Apply/Drop/AdjustFervor events

This reflects the reality that ideology is a personal lifecycle property (PC can convert), while race/origin/personality are typically birth-fixed. Language is in-between (immutable in canonical seed practice; mutable V1+ via learning).
