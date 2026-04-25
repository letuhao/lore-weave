# WA_001 — Lex (Per-Reality World Rules)

> **Conversational name:** "Lex" (LX). Per-reality declaration of physics + ability + energy axioms — what is allowed to exist and to be done in this reality. The DATA + VALIDATOR. Author UI to edit Lex is deferred to WA_002 Axiom Editor; this feature locks the underlying schema, validator slot, and reject UX.
>
> **Category:** WA — World Authoring
> **Status:** DRAFT 2026-04-25
> **Catalog refs:** **DF4 World Rules** (sub-feature: physics/ability/energy axioms only). Sibling DF4 sub-features (death model PC-B1, PvP consent PC-D2, voice mode lock C1-D3, session caps H3-NEW-D1, queue policy S7-D6, disconnect policy SR11-D4, turn fairness SR11-D7, time model MV12-D6) live in separate WA_* docs to be designed later. WA_002 Axiom Editor (author UI) is forward-link only.
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 RealityManifest (Lex extends the manifest), [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) §15 rejection path (Lex rejection follows the same shape), [05_llm_safety/](../../05_llm_safety/) A6 canon-drift (sibling validator, not Lex)
> **Resolves:** the "world-rule + forbidden-knowledge" question raised after PL_003 relocation. **Companion feature:** WA_002 Forbidden Knowledge & Cross-Reality Contamination (separate file, designed later) — Lex does NOT design contamination semantics.

---

## §1 User story (concrete)

Three realities, three Lex configs:

**Reality 1 — Thần Điêu Đại Hiệp (wuxia):**
- Energy system: `Qi` (nội công)
- Allowed abilities: `{ Qigong, SwordArts, KhinhCong, Healing, Alchemy_TCM }`
- Forbidden abilities: `{ MagicSpells, Firearms, Mechtech, Cybernetics, FTL_Travel }`
- Transmigration: `author-declared` (delegated to WA_002, not Lex)

If PC tries to cast a Fireball spell ("Hỏa cầu thuật!") in cell `yen_vu_lau`:
- A6 canon-drift might also flag — but Lex catches it FIRST as a hard axiom violation
- world-service rejects with `RejectReason::WorldRuleViolation { rule_id: "lex.ability_forbidden", detail: "Trong thế giới này, ma pháp không tồn tại; không thể thi triển 'Hỏa cầu thuật'." }`
- `TurnEvent` commits with `outcome=Rejected` per PL_002 §15 / PL_001 §15 contract; `turn_number` does NOT advance

**Reality 2 — 19th-century Earth (sci-fi-ish):**
- Energy system: `None`
- Allowed: `{ Firearms, Mechtech_Era_Appropriate, Chemistry, BasicMedicine }`
- Forbidden: `{ Qigong, MagicSpells, FTL_Travel, Cybernetics }`

PC tries to do qigong → Lex rejects with `lex.ability_forbidden` + Vietnamese copy "Trong thế giới này không có khí công."

**Reality 3 — Permissive narrative reality (default):**
- Energy: `None`
- Allowed: `{}` (empty)
- Forbidden: `{}` (empty)
- Net effect: **Lex passes through everything.** No hard axiom check. A6 canon-drift still runs (catches narrative inconsistencies), but Lex is a no-op. This is the V1 default — most realities ship without explicit Lex configuration.

**SPIKE_01 turn 5 (literacy slip):** Lý Minh quotes 《Đạo Đức Kinh chú》. Lex check: is "quote a book" an ability? NO — quoting is mundane. Lex passes. A6 canon-drift catches the slip as "PC body-knowledge inconsistency". Lex and A6 are SIBLING validators with NON-OVERLAPPING jurisdiction.

**This feature design specifies:** the closed set of axiom kinds; the per-reality declaration shape (extending RealityManifest); the validator slot in EVT-V*; the rejection UX; the V1-default-permissive semantics; coordination with WA_002 (which adds contamination model on top).

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Axiom** | Boolean assertion: `(AxiomKind, allowed: bool)` | V1: closed-set kind enum + boolean. V2+: AllowedWithBudget (for WA_002 contamination). |
| **AxiomKind** | Closed enum of categories Lex understands | See §6 for V1 closed set. New kinds require schema bump (LX-S* series, future). |
| **LexConfig** | Per-reality bag of `Vec<Axiom>` + `default_disposition: Disposition` | One aggregate per reality. |
| **Disposition** | `enum Disposition { Permissive, Restrictive }` — what happens to an action whose AxiomKind is NOT explicitly listed | Permissive (V1 default): unlisted = allowed. Restrictive: unlisted = forbidden. |
| **AbilityClassification** | The output of "what AxiomKind does THIS proposed action belong to?" | Computed at validate time by Lex. Inputs: TurnEvent payload + (V2+) actor capabilities. |
| **EnergyKind** | Closed enum: `{ Qi, Mana, SpellSlots, Aether, Stamina, Other(String), None }` | The reality's "what powers abilities" axis. Most realities use exactly one. |
| **LexViolation** | Rejection-path data attached to RejectReason::WorldRuleViolation | Contains AxiomKind + Vietnamese reject copy + ops detail. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

Lex is a **validator slot**, not an event producer. It does NOT emit events directly.

| Lex output | EVT-T* impact |
|---|---|
| Pass through | No event impact; the proposed event continues through the EVT-V* pipeline |
| Reject (LexViolation) | The proposed event commits with `outcome=Rejected` per PL_001 §15 / PL_002 §15. EVT-T* category unchanged (still EVT-T1 PlayerTurn or EVT-T2 NPCTurn). `turn_number` does NOT advance. |
| (V2+ via WA_002) Allowed-with-budget | Side-effect: WA_002 increments contamination counter via EVT-T3 AggregateMutation. Out of scope for WA_001. |

Lex itself is invisible in the EVT-T* taxonomy — it's a pre-commit gate. Its existence is documented in `07_event_model/05_validator_pipeline.md` (Phase 3 of event-model agent, not yet locked) as one of the validator stages.

---

## §3 Aggregate inventory

**One** new aggregate. Lex is small.

### 3.1 `lex_config`

```rust
#[derive(Aggregate)]
#[dp(type_name = "lex_config", tier = "T2", scope = "reality")]
pub struct LexConfig {
    pub reality_id: RealityId,                          // (also from key — singleton per reality)
    pub schema_version: u32,                            // for additive evolution
    pub default_disposition: Disposition,               // Permissive (V1 default) | Restrictive
    pub energy_system: EnergyKind,                      // Qi | Mana | SpellSlots | Aether | Stamina | Other(...) | None
    pub axioms: Vec<Axiom>,                             // explicit declarations
    pub last_authored_at: Timestamp,                    // for audit
    pub last_authored_by: AuthorRef,                    // who edited (book author or admin)
}

pub struct Axiom {
    pub kind: AxiomKind,
    pub allowed: bool,                                  // V1 hard yes/no
    pub note: Option<String>,                           // author-supplied rationale (for audit; not user-facing)
}

pub enum Disposition {
    Permissive,                                         // unlisted AxiomKind = allowed
    Restrictive,                                        // unlisted AxiomKind = forbidden
}

// AxiomKind: closed enum, see §6
```

- T2 + RealityScoped: small (<10 KB per reality typical), per-reality singleton, durable.
- Read every turn validation (cache hit >95%; ~5ms per check).
- Written by author UI (WA_002, future) or RealityManifest seed at bootstrap.
- One row per reality; identified by `reality_id` (singleton like PL_001 `fiction_clock`).

### 3.2 References (no other new aggregates)

- **`reality_registry`** (per `02_storage/C03_meta_registry_ha.md`) — meta-layer for reality ownership; Lex stores its config in the reality's own DB, NOT the meta registry.
- **`fiction_clock`** (PL_001 §3.1) — Lex MAY consume time for time-gated axioms in V2+ (e.g., "magic only available after fiction-day Y"); V1 doesn't.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `lex_config` | T2 | T2 | Reality | ~1/turn (cached >95%) | ~0 hot path; rare on author edits | Per-reality singleton; durable; eventual-consistency on author edit OK (5-min cache TTL acceptable). |

No T0/T1/T3 in this feature.

- No T0: rule-set persists across restarts.
- No T1: not high-churn; not session-scoped.
- No T3: author edits don't need atomicity with other aggregates; eventual consistency on cache propagation is fine.

---

## §5 DP primitives this feature calls

### 5.1 Reads

```rust
let lex = dp::read_projection_reality::<LexConfig>(
    ctx,
    LexConfigId::singleton(reality_id),
    wait_for=None,
    causality_timeout=None,
).await?;
```

Performed once per turn validate; cached for 5 minutes per world-service node (acceptable staleness for author edits).

### 5.2 Writes

```rust
// At RealityManifest bootstrap (PL_001 §16.2 t3_write_multi extension)
dp::t2_write::<LexConfig>(ctx, LexConfigId::singleton(reality_id), LexDelta::Initialize { ... }).await?;

// At author-driven edit (WA_002 future)
dp::t2_write::<LexConfig>(ctx, LexConfigId::singleton(reality_id), LexDelta::EditAxiom { kind, allowed, note }).await?;
```

Author edits emit invalidation broadcast (DP-X*) so all world-service nodes pick up new config within ≤100 ms.

---

## §6 Closed-set AxiomKind (V1)

Lex understands a closed set of axiom categories. New kinds require an LX-S* schema bump (locked-decision entry, additive only per foundation I14).

```rust
pub enum AxiomKind {
    // ─── Ability classes ───
    Qigong,                                 // wuxia inner power; channel ki to enhance
    SwordArts,                              // wuxia weapon mastery (jian-fa, dao-fa)
    KhinhCong,                              // wuxia lightness skill (rooftop running, water-walking)
    Healing,                                // restore HP/state via touch / herb / spell
    Alchemy_TCM,                            // herbal medicine, traditional alchemy
    Alchemy_Western,                        // gold-from-lead, transmutation
    MagicSpells,                            // mana-cost incantations
    DivineFavor,                            // god-granted miracles
    Necromancy,                             // raise dead, soul manipulation
    Firearms,                               // gunpowder weapons
    Mechtech_Era_Appropriate,               // pre-industrial machinery
    Mechtech_Modern,                        // post-industrial machinery
    Cybernetics,                            // body-mod, augmentations
    Bioengineering,                         // genetic mod, bio-printing
    FTL_Travel,                             // faster-than-light movement
    Time_Manipulation,                      // any temporal abilities
    Reality_Warping,                        // god-tier ability-to-edit-reality
    PsionicAbilities,                       // mind powers without external energy

    // ─── Catch-alls ───
    Other(String),                          // free-form for kinds not in V1 closed set;
                                            // discouraged — prefer adding explicit variants via schema bump
}
```

V1 ships with the 17 above + `Other(String)`. The `Other` escape hatch exists for V1 prototype iteration; V2 expects most realities to fit into the explicit kinds.

### 6.1 EnergyKind (separate dimension)

Independent of ability kinds. A reality may have `EnergyKind::None` (no energy system, like 19th-century Earth) but still allow `Firearms` (which doesn't require energy). Or have `EnergyKind::Mana` and require it for `MagicSpells`.

```rust
pub enum EnergyKind {
    Qi,                                     // wuxia
    Mana,                                   // standard fantasy
    SpellSlots,                             // D&D Vancian magic
    Aether,                                 // alchemical / classical Greek
    Stamina,                                // physical exertion (universal; usually combined with another)
    Other(String),
    None,                                   // "no energy concept exists" — most-permissive default for sci-fi realities
}
```

V1 doesn't use EnergyKind for validation — it's metadata for V2+ when WA_002 contamination model + ability-cost model lands. Authors declare it now so future features have structured data.

---

## §7 Validator pipeline integration (slot in EVT-V*)

Lex is one stage in the EVT-V* validator pipeline (event-model agent's Phase 3 — not yet locked, but the slot is reserved here).

### 7.1 Slot ordering (proposed)

```text
EVT-V* pipeline (per EVT-A5 fixed-order, no skips):

  schema validate
    │
  capability check (DP-K9)
    │
  A5 intent classification (PL_002 / PL-15)
    │
  A6 injection defense — input layer (PL_002 / PL-19)
    │
★ lex_check (THIS FEATURE) ★
    │
  A6 injection defense — output layer (PL_002 / PL-20)
    │
  canon-drift check (A6 / catalog NPC-6)
    │
  causal-ref integrity (per EVT-A6)
    │
  commit (advance_turn or t2_write per outcome)
```

Lex sits BEFORE the A6 output filter and canon-drift because:
- Lex is a hard physics axiom check; cheaper than the LLM-output canon-drift pass
- Failing Lex early avoids wasting A6 / canon-drift compute
- Lex rejection produces a deterministic copy (§9), not LLM-generated; predictable UX

### 7.2 Lex validator algorithm

```text
fn lex_check(proposed_event: &TurnEvent, lex: &LexConfig) -> Result<(), LexViolation> {
    // Step 1: classify the proposed action
    let ability_kinds = classify_action(proposed_event);
        // Returns Vec<AxiomKind>; empty if action is mundane (e.g., "PC sips tea").
        // For LLM-output proposals, classification is done by deterministic content-tag function
        // (NOT LLM — same pattern as PL_003 §11 trigger_tags extraction).

    if ability_kinds.is_empty() {
        return Ok(());  // mundane action, no Lex check applies
    }

    // Step 2: per kind, check axiom
    for kind in ability_kinds {
        let axiom = lex.axioms.iter().find(|a| a.kind == kind);
        let allowed = match (axiom, lex.default_disposition) {
            (Some(a), _)                          => a.allowed,
            (None, Disposition::Permissive)       => true,
            (None, Disposition::Restrictive)      => false,
        };
        if !allowed {
            return Err(LexViolation {
                axiom_kind: kind,
                rule_id: format!("lex.ability_forbidden.{}", kind.as_str()),
                detail_vi: vietnamese_copy_for(kind),
                detail_en: english_copy_for(kind),
            });
        }
    }

    Ok(())
}

pub struct LexViolation {
    pub axiom_kind: AxiomKind,
    pub rule_id: String,
    pub detail_vi: String,
    pub detail_en: String,
}
```

### 7.3 `classify_action`

Deterministic function (NOT LLM) mapping a TurnEvent payload to a set of AxiomKinds:

- Examines `TurnEvent.command_kind` + `TurnEvent.action_kind` + `TurnEvent.narrator_text`
- Uses a content-tag dictionary (similar to PL_003 §11 trigger_tags): map keyword/phrase → AxiomKind
- V1: dictionary-based, ~200-500 entries
- V2+: may incorporate LLM-tagged classification with confidence threshold; V1 stays deterministic

Content-tag dictionary entries example:
```yaml
# excerpt from lex_classification_v1.yaml
- pattern: ["Hỏa cầu thuật", "fireball", "spell:.*"]
  kinds: [MagicSpells]
- pattern: ["nội công", "qigong", "khí công"]
  kinds: [Qigong]
- pattern: ["khinh công", "lightness skill"]
  kinds: [KhinhCong]
- pattern: ["súng", "rifle", "gunpowder"]
  kinds: [Firearms]
```

Maintained as a Lex sub-resource (separate file `lex_classification_v1.yaml`); editable via author UI (WA_002) but for V1 ships hardcoded.

---

## §8 Pattern choices

### 8.1 V1 = hard YES/NO only (locked)

V1 axioms are boolean. No budgets, no tiers, no fiction-time-gated axioms. Reasons:

- 90%+ of realities only need YES/NO (wuxia world has magic? NO; sci-fi world has qi? NO).
- The transmigrator/contamination case (which DOES need budgets) is WA_002's territory.
- Locking V1 to YES/NO keeps Lex small and validator wall-clock <5ms per check.

V2+ adds: `AllowedWithBudget(BudgetSpec)` axiom variant. Time-gated axioms (`AllowedAfter(FictionTimeTuple)`). All deferred to WA_002 / V2+.

### 8.2 Default disposition = Permissive (locked V1)

If a reality doesn't declare a `LexConfig`, Lex acts as a no-op (everything passes). This is the V1 default.

Why: most V1 realities are narrative-genre (not hard physics-genre). Author can't anticipate every ability someone might propose; Permissive lets the LLM and A6 canon-drift handle the long tail.

If author wants a strict reality, they explicitly set `default_disposition: Restrictive` + declare the allowed axioms.

### 8.3 Lex rejects EARLY (locked) — before A6 output filter

Lex runs after input-side A6 (sanitize) but before output-side A6 (filter) and canon-drift. Reason:

- Lex is cheap (~5 ms) and deterministic; running it early avoids paying canon-drift LLM cost on already-doomed proposals.
- A6 input-side sanitize runs first because Lex's `classify_action` reads `narrator_text` — needs sanitized input.

### 8.4 Classification is deterministic (locked V1)

`classify_action` is a regex/keyword dictionary, NOT an LLM call. Reason:

- LLM-classified axioms would be non-deterministic (replay reproducibility broken; SPIKE_01 obs#5-style hard).
- Dictionary has clear failure mode (missed match → kinds=empty → Lex passes through to canon-drift, where A6 catches it).
- V2+ may add LLM-classification as a SECOND layer with confidence threshold, but the deterministic layer remains primary.

### 8.5 Axiom edits are non-retroactive (locked)

If author flips `MagicSpells` from `allowed=true` to `allowed=false` mid-reality:
- Future proposals are checked against the new config.
- Past committed events (NPC who already cast a fireball) are NOT retroactively invalidated. They're canon by virtue of being committed.
- This matches PL_001 / EVT-A1 immutable-event-log semantics.

V2+ may add: author-action "purge events of kind X" via S5 admin override + DF8 canon-fork. Out of scope for V1.

---

## §9 Failure-mode UX

Per AxiomKind, locked Vietnamese + English reject copy:

| AxiomKind | rule_id | Vietnamese (PC) | English (ops) |
|---|---|---|---|
| `MagicSpells` | `lex.ability_forbidden.magic_spells` | "Trong thế giới này, ma pháp không tồn tại." | "MagicSpells forbidden by reality Lex" |
| `Qigong` | `lex.ability_forbidden.qigong` | "Thế giới này không có khí công." | "Qigong forbidden by reality Lex" |
| `Firearms` | `lex.ability_forbidden.firearms` | "Thời này chưa có súng." | "Firearms forbidden by reality Lex" |
| `FTL_Travel` | `lex.ability_forbidden.ftl_travel` | "Không thể di chuyển nhanh hơn ánh sáng trong thế giới này." | "FTL_Travel forbidden by reality Lex" |
| `Reality_Warping` | `lex.ability_forbidden.reality_warping` | "Thế giới này không thể bị thay đổi bằng ý chí." | "Reality_Warping forbidden by reality Lex" |
| `Necromancy` | `lex.ability_forbidden.necromancy` | "Người chết không thể sống lại trong thế giới này." | "Necromancy forbidden by reality Lex" |
| ...remaining V1 kinds... | `lex.ability_forbidden.<kind>` | (per kind) | (per kind) |
| `Other("foo")` | `lex.ability_forbidden.other` | "Hành động này không phù hợp với thế giới này." | `Other(foo) forbidden by reality Lex` |
| (default disposition = Restrictive, unlisted kind) | `lex.unlisted_kind_restrictive` | "Hành động này chưa được công nhận trong thế giới này." | `unlisted axiom kind X under Restrictive default` |

UI on rejection:
- Modal toast: Vietnamese reject copy + suggestion ("Thử /look hoặc /verbatim?")
- Audit log: rule_id + axiom_kind + proposed_event_id + classification_match
- No retry penalty: PC may immediately submit a different action

V2+ adds: i18n beyond Vietnamese (English UI, Chinese for wuxia realities) — copy keys live in `i18n_lex_copy` resource per PL_002 pattern.

---

## §10 Cross-service handoff

Lex runs entirely in-process within world-service. No new service-to-service hops.

```text
(EVT-V* validator pipeline running in world-service consumer)
    proposed_event arrives from LLM proposal bus
    │
    ▼
    schema → capability → A5 intent → A6 sanitize
    │
    ▼
   ★ lex_check (in-process call) ★
    1. dp::read_projection_reality::<LexConfig>(ctx, ...)  [cached]
    2. classify_action(proposed_event)  [in-process, deterministic]
    3. for each kind: check axiom; on first violation, return Err(LexViolation)
    │
    ▼
   on Pass: continue pipeline → A6 filter → canon-drift → commit
   on Reject: emit TurnEvent { outcome: Rejected { reason: WorldRuleViolation { rule_id, detail } } } via t2_write per PL_002 §15
```

Wall-clock budget: ~5 ms p99 (1 cache-hit read + 1 dictionary classification + ≤17 axiom comparisons).

### 10.1 Coordination with event-model agent (Phase 3)

Lex is a slot in EVT-V*. The event-model agent's Phase 3 (`05_validator_pipeline.md`) will define:
- Slot ordering (we propose §7.1)
- Standard `EventValidator` trait shape
- Failure-mode contract (we provide LexViolation; agent maps to standard EVT-V* error type)

This feature design provides the slot's CONTENT (axiom check). Slot SHAPE is event-model agent's territory. Drift watchpoint LX-D5 if our proposed slot ordering disagrees with what the agent locks.

### 10.2 Coordination with WA_002 (companion feature)

WA_002 Forbidden Knowledge & Cross-Reality Contamination will:
- Add `AllowedWithBudget(BudgetSpec)` variant to `Axiom.allowed` field (currently `bool`; will become an enum)
- Add a NEW validator slot AFTER Lex: `contamination_check`
- Use `LexConfig.energy_system` to determine whether contamination is even meaningful (a `None`-energy reality + transmigrator-with-mana = harder boundary than `Mana` + `Aether` blend)

WA_001 reserves the upgrade path: `Axiom.allowed: bool` field will become `Axiom.allowance: Allowance` enum in WA_002. V1 schema is `LexSchema = 1`; WA_002 ships `LexSchema = 2` with additive field per foundation I14.

---

## §11 Sequence: hard reject (PC tries to cast Fireball in TĐĐH)

```text
PC types: "Lý Minh giơ tay, hét: Hỏa cầu thuật!"
    │
    ▼
gateway → roleplay-service:
  A5 → Intent::FreeNarrative (confidence 0.95)
  PL-4 prompt: assemble + LLM stream
  LLM: "Lý Minh giơ tay lên, hô lớn 'Hỏa cầu thuật!' — ánh lửa đỏ rực sáng cháy lên..."
  emit LLMProposal (EVT-T6) with narrator_text
    │
    ▼
world-service consumer:
  schema validate ✓
  capability check ✓
  A5 cross-check ✓
  A6 sanitize ✓
    │
    ▼
  ★ lex_check ★:
    read LexConfig(reality=tdd_h):
      energy_system: Qi
      axioms: [
        { Qigong: allowed=true },
        { SwordArts: allowed=true },
        { MagicSpells: allowed=false },     ← match
        { Firearms: allowed=false },
        ...
      ]
      default_disposition: Restrictive
    classify_action:
      narrator_text contains "Hỏa cầu thuật" → matches dict pattern → kinds=[MagicSpells]
    check axiom MagicSpells: allowed=false
    return Err(LexViolation {
      axiom_kind: MagicSpells,
      rule_id: "lex.ability_forbidden.magic_spells",
      detail_vi: "Trong thế giới này, ma pháp không tồn tại.",
      detail_en: "MagicSpells forbidden by reality Lex"
    })
    │
    ▼
world-service rejection path (PL_002 §15):
  build TurnEvent {
    actor: pc_id,
    intent: Speak,
    narrator_text: None,                    // discard LLM output
    outcome: Rejected { reason: WorldRuleViolation {
      rule_id: "lex.ability_forbidden.magic_spells",
      detail: "Trong thế giới này, ma pháp không tồn tại."
    } },
    fiction_duration_proposed: 0,
    idempotency_key: K, ...
  }
  dp::t2_write::<TurnEvent>(ctx, channel, event_id, payload)
    → turn_number stays at N
    → causality_token returned
    │
    ▼
gateway → UI:
  HTTP 200 OK with body {
    outcome: Rejected,
    reason: { kind: "world_rule_violation",
              rule_id: "lex.ability_forbidden.magic_spells",
              detail: "Trong thế giới này, ma pháp không tồn tại." },
    turn_number: N (unchanged),
    fiction_time: <unchanged>
  }

UI renders:
  ⚠ Lý Minh hô vô vọng — trong thế giới này, ma pháp không tồn tại.
```

**Verification:**
- `fiction_clock` not advanced (MV12-D11 ✓)
- `turn_number` not advanced (PL_001 §15 ✓)
- Rejected event committed for audit (operator can debug "why is PC bouncing?")
- A6 canon-drift NEVER ran (saved compute)
- LLM output discarded (would have been narratively coherent but axiomatically invalid)

---

## §12 Sequence: pass-through (PC qigong in TĐĐH)

```text
PC types: "Lý Minh ngồi xuống, vận khí, tập trung"
  → A5: FreeNarrative
  → LLM: "Lý Minh khoanh chân, vận nội công, hơi thở chậm rãi..."
  → emit LLMProposal
  ▼
world-service:
  ...all earlier validators pass...
  ★ lex_check ★:
    classify_action: matches "vận nội công" → kinds=[Qigong]
    check axiom Qigong: allowed=true ✓
    return Ok(())
  ▼
  A6 output filter ✓
  canon-drift ✓
  commit via advance_turn (Accepted)
  ▼
TurnEvent commits, turn_number advances, fiction_clock advances by 30s.
```

Lex is a no-op gate when ability is allowed. <5 ms overhead per turn.

---

## §13 Sequence: empty/permissive reality (anything passes)

```text
RealityManifest for Reality 3 (default permissive):
  no LexConfig declared → world-service falls back to Lex no-op
  OR
  LexConfig { default_disposition: Permissive, axioms: [], energy_system: None }

PC types: "Lý Minh dùng laser blaster bắn ma cà rồng"
  → LLM proposes narration
  → world-service:
       ★ lex_check ★:
         lex.axioms.is_empty() AND default_disposition=Permissive
         → no axiom matches; default Permissive → Ok(())
       continue pipeline
       A6 output filter MAY catch ("Vampire isn't in this reality's canon") via canon-drift
       Or accept and commit.
```

V1 default = "narrative reality" — Lex passes through, canon-drift does the heavy lifting. Author opts INTO Lex by declaring axioms.

---

## §14 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| LX-D1 | Per-actor exception system: PC declared as transmigrator gets MagicSpells allowed; standard PCs do not | **WA_002** Forbidden Knowledge & Cross-Reality Contamination |
| LX-D2 | Budget model: actor X gets 3 fireballs per fiction-day | **WA_002** |
| LX-D3 | Cascade-consequence on violation: world degradation events when budget exceeded | **WA_002** + EVT-T11 WorldTick |
| LX-D4 | Author UI to edit LexConfig at runtime (with consequence preview) | **WA_002** Axiom Editor (UI-layer) — separate from rule data |
| LX-D5 | Slot ordering in EVT-V* — agreement with event-model agent's Phase 3 | event-model agent Phase 3 (`05_validator_pipeline.md`) |
| LX-D6 | Time-gated axioms: "magic only available after fiction-day Y" | V2+; needs WA_002 budget primitives first |
| LX-D7 | LLM-classified action kinds (V2+ second classification layer with confidence threshold) | V2+ optimization |
| LX-D8 | EnergyKind validation: "this MagicSpell costs 50 mana; does PC have it?" | WA_003 (future) Energy/Cost Model — depends on PC stats system (DF7) |
| LX-D9 | i18n beyond Vietnamese for reject copy | Phase 5 ops + PL_002 i18n_command_copy resource pattern |
| LX-D10 | Author-purge of past events of forbidden kind (mid-reality axiom flip with retroactive cleanup) | DF8 canon-fork (V3+) |

---

## §15 Cross-references

- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — §16 RealityManifest extension point; §15 rejection path contract
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — §15 rejection sequence Lex follows; reject copy table format
- [05_llm_safety/](../../05_llm_safety/) — A6 canon-drift (sibling validator with non-overlapping jurisdiction)
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A3 (validated events for canonical writes), EVT-A5 (fixed validator order)
- [07_event_model/05_validator_pipeline.md] (Phase 3, not yet locked) — where Lex's slot will be formalized
- [03_multiverse/01_four_layer_canon.md](../../03_multiverse/) — L1/L2/L3/L4 canon layers; Lex axioms are L1 declarations per author intent
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella (this is a sub-feature)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — PC-A3, PC-B1, PC-D2, PC-E3, M3-D3, H3-NEW-D1, S7-D6, SR11-D4, SR11-D7, MV12-D6 (sibling DF4 sub-features for separate WA_* docs)
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — turn 5 literacy slip example (NOT a Lex case; A6 canon-drift territory)
- (Future) **WA_002 Forbidden Knowledge & Cross-Reality Contamination** — companion feature; not yet drafted

---

## §16 Implementation readiness checklist

- [x] **§2** Domain concepts (Axiom, AxiomKind, Disposition, EnergyKind, LexViolation)
- [x] **§2.5** EVT-T* mapping (validator, no events emitted; rejection path via PL_001/PL_002 §15)
- [x] **§3** Aggregate inventory (1 new: `lex_config`)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Closed-set AxiomKind V1 (17 explicit + Other(String)) + EnergyKind enum
- [x] **§7** Validator pipeline integration (slot ordering proposed; algorithm spec; classification deterministic V1)
- [x] **§8** Pattern choices (V1 hard YES/NO, Permissive default, classify deterministic, non-retroactive)
- [x] **§9** Per-AxiomKind reject copy table (Vietnamese + English)
- [x] **§10** Cross-service handoff (in-process; coordination with event-model + WA_002)
- [x] **§11** Sequence: hard reject (Fireball in wuxia)
- [x] **§12** Sequence: pass-through (qigong in wuxia)
- [x] **§13** Sequence: empty/permissive reality
- [x] **§14** Deferrals (LX-D1..D10)

**Deferred:** acceptance criteria (intentionally not in V1 of this doc).

**Status:** DRAFT 2026-04-25.

**Unblocks:** authors can declare reality axioms at bootstrap; world-service has a contract for the validator slot; WA_002 has a foundation to build contamination model on top.

**Drift watchpoint:** §7.1 slot ordering proposal needs reconciliation with event-model agent's Phase 3 EVT-V* lock. If they choose different ordering (e.g., Lex AFTER canon-drift), §7.1 + §11 sequences need update.

**Next** (when this doc locks): world-service implements `lex_check` validator + `classify_action` dictionary; RealityManifest extension at `02_storage` adds `LexConfigDecl` field; book-ingestion pipeline (knowledge-service) seeds default Lex per book genre. Vertical-slice target: SPIKE_01 reality boots with `LexConfig::default_for(WuxiaGenre)`; hypothetical /verbatim "Hỏa cầu thuật!" rejects with §11 sequence.
