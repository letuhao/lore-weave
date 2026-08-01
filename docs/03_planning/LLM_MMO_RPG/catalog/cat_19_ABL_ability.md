<!-- CHUNK-META
source: design-track manual seed 2026-07-26
chunk: cat_19_ABL_ability.md
namespace: ABL-*
generated_by: hand-authored (namespace catalog seed at ABL_001 DRAFT)
-->

## ABL — Abilities (the activatable-effect catalogue)

> Catalog for `features/19_ability/`. Created **2026-07-26** with the namespace itself.
> Owns the `ABL-*` stable-ID namespace **and the `EffectOp` shared effect vocabulary**.
>
> | Sub-prefix | What |
> |---|---|
> | `ABL-A*` | Axioms (locked invariants) |
> | `ABL-Q*` | Locked decisions |
> | `ABL-D*` | Deferrals |
> | `ABL-V*` | Validators |
> | `AC-ABL-*` | Acceptance criteria |

### Why this namespace exists outside `18_combat`

Combat is the loudest consumer of abilities, not the only one — PL_005's out-of-combat `Use` calls the
same catalogue. Homing it in `18_combat` would make out-of-combat ability use depend on the combat
feature; homing it in `00_progression` would put an *activatable effect* inside a doc that deliberately
owns only *competence values* (PROG_001 §1: no level, no power rating). Same reasoning that gave DF07 its
own home rather than extending PROG_001.

### The naming trap this namespace defuses

PROG_001's `ProgressionType::Skill` and COMB_001's `Skill` verb are **different things with the same
word**, and the combat concept notes conflated them (*"V1 skills come from PROG_001 skill kinds"*). They
cannot: a progression kind is **a number that grows** (`swordsmanship: 8`); an ability is **an effect you
fire** (`rising_dragon_cut`). Taking the sentence literally left `skill_id` with no declaring type and
`combat.skill_unknown` with nothing to check. **ABL-A1** is the fix; COMB_001 keeps the player-facing verb
name `Skill`, which now takes an `AbilityId`.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| ABL-1 | **ABL-A1** Ability ≠ progression kind (the vocabulary fix) | ✅ | V1 | PROG | [ABL_001 §2](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-2 | `AbilityDecl` — RealityManifest catalogue (optional; a reality may have none) | ✅ | V1 | — | [ABL_001 §3](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-3 | **`EffectOp`** — closed 11-variant dispatch vocabulary; **one owner, many producers** | ✅ | V1 | RES, PL_006 | [ABL_001 §4.1](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-4 | **`PowerTerm`** — changes damage without emitting a number; substitutes into COMB_001 §4 step 1 | ✅ | V1 | DF07, COMB-4 | [ABL_001 §4.3](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-5 | Op-resolution rules — one hit roll per (ability, target); death halts semantics | ✅ | V1 | COMB-4 | [ABL_001 §4.1](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-6 | Closed 6-variant `TargetRule` + Chebyshev range/LoS (resolves `skill.range`) | ✅ | V1 | TG-3 | [ABL_001 §5](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-7 | `ForceMove` (push / pull / swap), engine-resolved along the Chebyshev line | ✅ | V1 | TG-2 | [ABL_001 §5.3](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-8 | **ABL-A4** derived known-set — zero aggregates, threshold-gated by PROG_001 | ✅ | V1 | PROG, AIT | [ABL_001 §6](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-9 | Costs (RES_001 vitals) + encounter-ephemeral cooldowns | ✅ | V1 | RES, COMB-2 | [ABL_001 §7](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-10 | `duration_rounds` ⇄ fiction-time conversion out of combat | ✅ | V1 | PL_006, PL_001 | [ABL_001 §7.3](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-11 | **ABL-A6** driver-bounded selection — the LLM picks from a pre-filtered set it cannot extend | ✅ | V1 | AGT-A2/A3 | [ABL_001 §8.2](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-12 | `ModifyThreat` op (COMB_003 owns the table) | ✅ | V1 | THR-1 | [ABL_001 §4.1](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-13 | `SeverBinding` op — the Binding Contest's ability path; fires at defeat finalisation | ✅ | V1+ | SPO-7/8 | [COMB_004 §16.5](../features/18_combat/COMB_004_loot_and_spoils.md) |
| ABL-14 | **`VitalRestore { u32 }`** — harm unrepresentable by type; closes the law-chain bypass | ✅ | V1 | COMB-4 | [ABL_001 §4.2](../features/19_ability/ABL_001_ability_foundation.md) |
| ABL-15 | AoE shapes (blast / cone / line) | 📦 | V1+ | COMB_002 §11 | ABL-D1 |
| ABL-16 | Channelled / multi-round abilities | 📦 | V1+ | needs interrupt model | ABL-D2 |
| ABL-17 | Reaction / counter abilities | 📦 | V1+ | COMB_002 §11 retaliation | ABL-D3 |
| ABL-18 | Ability trees / explicit unlock spend | 📦 | V1+30d | needs a spend ledger | ABL-D4 |
| ABL-19 | Out-of-combat cooldowns | 📦 | V1+ | needs TDIL binding | ABL-D5 |
| ABL-20 | Elemental typing on abilities | 📦 | V1+ | DF7-D2 slots | ABL-D8 |
| ABL-21 | Summon / pet abilities | 📦 | V2+ | SPN-D4/D5 | ABL-D7 |
| ABL-22 | Offensive non-HP vital drain | 📦 | V1+ | no V1 consumer | ABL-D12 |
| ABL-23 | Player- / LLM-authored abilities | 🚫 | **never** | ABL-A2 | arbitrary code inside the determinism envelope |

**Legend:** ✅ designed · 📦 deferred · 🚫 out of scope by axiom.

### `EffectOp` — the shared vocabulary (ABL-Q9/Q10)

`EffectOp` is a **cross-feature contract**: owned here, produced by ABL abilities, PL_007 item
use-effects, and (V1+) Lex / quests / crafting — the same one-owner-many-producers shape as DF07's
`StatModifier`.

**PL_007's `UseEffectDecl` retires into it.** The merge was resolved as a **defect, not a preference**:
the two enums had diverged within 24 hours, and `VitalDelta { amount: i32 }` in *both* docs was a
**damage-law-chain bypass** — a signed vital write reachable from `UseItem` skips COMB_001 §4's chain,
takes no hit roll, accrues no COMB_003 threat, and ignores both COMB_001 Q4's disparity cap and COMB_006's
PvP predicate. Fixed by `VitalRestore { u32 }` + **`ABL-V9`** (every point of vital reduction passes the
law-chain).

> ⚠ **Outstanding:** the one-line PL_007 §7.1 change (`pub type UseEffectDecl = EffectOp;`) belongs to
> that doc's owner. The *decision* is made and registered; only the edit is pending.

### Cross-references

- Feature doc — [`ABL_001_ability_foundation.md`](../features/19_ability/ABL_001_ability_foundation.md)
- Folder index — [`features/19_ability/_index.md`](../features/19_ability/_index.md)
- Combat family — [`cat_18_COMB_combat.md`](cat_18_COMB_combat.md)
- Boundary registration — [`_boundaries/99_changelog.md`](../_boundaries/99_changelog.md) (2026-07-26 entry)
- Audit finding closed — [`12_module_coverage_audit.md`](../12_module_coverage_audit.md) AUD-F10
